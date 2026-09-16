"""
backend/app/modules/doctors/finder.py

Doctor finder using OpenStreetMap Overpass API (free, no key needed).

Priority chain:
  1. DynamoDB cache (24h TTL, key = condition_{lat:.2f}_{lng:.2f})
  2. OpenStreetMap Overpass API (free, no billing, good India coverage)
     - Queries healthcare nodes (hospital/clinic/doctor) within radius
     - Composite score: proximity-weighted (closer = higher)
     - Emergency cases: hospitals only, 5km radius
     - No results: double radius and retry once (up to 30km)
  3. NMC registry (seeded DynamoDB, 50km distance cap)
  4. Hardcoded Jaipur fallback (always works)
"""

import hashlib
import json
import logging
import math
import time
import urllib.parse
from decimal import Decimal
from typing import List, Optional

import httpx

from app.config import settings
from app.models.response_models import DoctorResult

logger = logging.getLogger(__name__)

OVERPASS_URL    = "https://overpass-api.de/api/interpreter"
CACHE_TABLE     = "mediassist-doctor-cache"
HOSPITALS_TABLE = settings.DYNAMODB_HOSPITALS_TABLE
CACHE_TTL_HOURS = 24


# ── Geometry ──────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ── DynamoDB cache ────────────────────────────────────────────────────────────

def _cache_key(condition: str, lat: float, lng: float) -> str:
    raw = f"{condition.lower()}_{lat:.2f}_{lng:.2f}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _get_dynamo_table(table_name: str):
    try:
        import boto3
        dynamo = boto3.resource("dynamodb", **settings.boto3_kwargs)
        return dynamo.Table(table_name)
    except Exception:
        return None


def _load_cache(condition: str, lat: float, lng: float) -> Optional[List[DoctorResult]]:
    try:
        table = _get_dynamo_table(CACHE_TABLE)
        if not table:
            return None
        key = _cache_key(condition, lat, lng)
        resp = table.get_item(Key={"cache_key": key})
        item = resp.get("Item")
        if not item or item.get("expires_at", 0) < int(time.time()):
            return None
        raw = json.loads(item["data"])
        return [DoctorResult(**d) for d in raw]
    except Exception as e:
        logger.debug(f"Cache load failed: {e}")
        return None


def _save_cache(condition: str, lat: float, lng: float, doctors: List[DoctorResult]) -> None:
    try:
        table = _get_dynamo_table(CACHE_TABLE)
        if not table:
            return
        key = _cache_key(condition, lat, lng)
        expires = int(time.time()) + CACHE_TTL_HOURS * 3600
        raw = json.dumps([d.dict() for d in doctors])
        table.put_item(Item={
            "cache_key": key,
            "condition": condition,
            "lat": Decimal(str(round(lat, 2))),
            "lng": Decimal(str(round(lng, 2))),
            "data": raw,
            "expires_at": expires,
        })
    except Exception as e:
        logger.debug(f"Cache save failed: {e}")


# ── OpenStreetMap Overpass API ────────────────────────────────────────────────

def _build_overpass_query(lat: float, lng: float, radius_m: int, emergency_only: bool) -> str:
    if emergency_only:
        return (
            f"[out:json][timeout:15];\n"
            f"(\n"
            f'  node["amenity"="hospital"](around:{radius_m},{lat},{lng});\n'
            f'  way["amenity"="hospital"](around:{radius_m},{lat},{lng});\n'
            f");\n"
            f"out center 20;"
        )
    return (
        f"[out:json][timeout:15];\n"
        f"(\n"
        f'  node["amenity"~"hospital|clinic|doctors"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"~"hospital|clinic|doctors"](around:{radius_m},{lat},{lng});\n'
        f'  node["healthcare"~"hospital|clinic|doctor|centre"](around:{radius_m},{lat},{lng});\n'
        f'  way["healthcare"~"hospital|clinic|doctor|centre"](around:{radius_m},{lat},{lng});\n'
        f");\n"
        f"out center 30;"
    )


def _composite_score(dist_km: float, radius_km: float) -> float:
    """Closer = higher score (0-1). OSM has no ratings so proximity-only."""
    return max(0.0, 1.0 - dist_km / max(radius_km, 1.0))


def _osm_name(tags: dict) -> str:
    return tags.get("name:en") or tags.get("name") or tags.get("official_name") or ""


def _osm_phone(tags: dict) -> str:
    return tags.get("contact:phone") or tags.get("phone") or tags.get("contact:mobile") or ""


def _osm_address(tags: dict) -> str:
    parts = [tags.get(k, "") for k in ("addr:housenumber", "addr:street", "addr:suburb", "addr:city")]
    return ", ".join(p for p in parts if p) or tags.get("addr:full", "")


async def _search_overpass(
    lat: float,
    lng: float,
    radius_km: float,
    specialty: str,
    emergency_only: bool,
    top_k: int = 5,
) -> List[DoctorResult]:
    """Query OSM Overpass API for nearby medical facilities."""
    radius_m = int(radius_km * 1000)
    query = _build_overpass_query(lat, lng, radius_m, emergency_only)

    try:
        encoded = urllib.parse.urlencode({"data": query})
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "AarogyaAI/1.0 (medical assistant; contact: admin@aarogya.ai)",
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(OVERPASS_URL, content=encoded, headers=headers)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
    except Exception as e:
        logger.warning(f"Overpass API error: {e}")
        return []

    # Retry with double radius if no results (max 30km)
    if not elements and radius_km < 30:
        logger.info(f"Overpass: 0 results at {radius_km}km, expanding to {radius_km * 2}km")
        return await _search_overpass(lat, lng, radius_km * 2, specialty, emergency_only, top_k)

    results: List[DoctorResult] = []
    for el in elements:
        tags = el.get("tags", {})
        name = _osm_name(tags)
        if not name:
            continue

        el_lat = float(el.get("lat") or el.get("center", {}).get("lat") or lat)
        el_lng = float(el.get("lon") or el.get("center", {}).get("lon") or lng)
        dist_km = _haversine_km(lat, lng, el_lat, el_lng)

        results.append(DoctorResult(
            name=name,
            specialty=specialty,
            hospital=name,
            rating=4.0,
            distance_km=round(dist_km, 1),
            phone=_osm_phone(tags),
            address=_osm_address(tags),
            google_place_id=f"osm:{el.get('type', 'n')}/{el.get('id', '')}",
            is_open_now=None,
            source="openstreetmap",
            _score=_composite_score(dist_km, radius_km),
        ))

    results.sort(key=lambda d: d._score, reverse=True)
    return results[:top_k]


# ── NMC / DynamoDB registry fallback ─────────────────────────────────────────

def _query_nmc_fallback(specialty: str, lat: float, lng: float, top_k: int = 5) -> List[DoctorResult]:
    """Query seeded hospital table by specialty. Max 50km radius."""
    try:
        from boto3.dynamodb.conditions import Attr
        table = _get_dynamo_table(HOSPITALS_TABLE)
        if not table:
            return []
        resp = table.scan(FilterExpression=Attr("specialty").eq(specialty), Limit=50)
        items = resp.get("Items", [])
        doctors = []
        for item in items:
            dist_km = _haversine_km(lat, lng, float(item.get("lat", lat)), float(item.get("lng", lng)))
            if dist_km > 50:
                continue
            doctors.append(DoctorResult(
                name=item.get("name", "Unknown"),
                specialty=item.get("specialty", specialty),
                hospital=item.get("hospital", item.get("name", "Unknown")),
                rating=float(item.get("rating", 4.0)),
                distance_km=round(dist_km, 1),
                phone=item.get("phone", ""),
                address=item.get("address", ""),
                google_place_id=item.get("google_place_id") or None,
                is_open_now=None,
                source="nmc_registry",
            ))
        doctors.sort(key=lambda d: d.distance_km)
        return doctors[:top_k]
    except Exception as e:
        logger.warning(f"NMC fallback failed: {e}")
        return []


# ── Hardcoded last-resort fallback ────────────────────────────────────────────

_HARDCODED: dict = {
    "Cardiologist": [
        dict(name="Apex Hospital Jaipur", hospital="Apex Hospital", rating=4.8, distance_km=2.5,
             phone="+91-141-2700000", address="SP-4, Malviya Nagar, Jaipur"),
        dict(name="Fortis Escorts Hospital", hospital="Fortis Escorts", rating=4.7, distance_km=3.2,
             phone="+91-141-2547000", address="JLN Marg, Jaipur"),
    ],
    "Pulmonologist": [
        dict(name="SMS Medical College & Hospital", hospital="SMS Hospital", rating=4.6, distance_km=3.5,
             phone="+91-141-2518501", address="JLN Marg, Jaipur"),
    ],
    "Neurologist": [
        dict(name="RUHS College of Medical Sciences", hospital="RUHS", rating=4.7, distance_km=5.0,
             phone="+91-141-2703000", address="Sector-11, Pratap Nagar, Jaipur"),
    ],
    "Gastroenterologist": [
        dict(name="Narayana Multispeciality Hospital", hospital="Narayana Hospital", rating=4.5, distance_km=4.2,
             phone="+91-141-7161000", address="Pratap Nagar, Jaipur"),
    ],
    "Orthopedist": [
        dict(name="Santokba Durlabhji Memorial Hospital", hospital="SD Hospital", rating=4.6, distance_km=2.8,
             phone="+91-141-2566251", address="Bhawani Singh Marg, Jaipur"),
    ],
    "Dermatologist": [
        dict(name="Skin Care Centre Jaipur", hospital="Skin Care Centre", rating=4.4, distance_km=1.5,
             phone="+91-98280-11111", address="C-Scheme, Jaipur"),
    ],
    "Endocrinologist": [
        dict(name="Mahatma Gandhi Hospital Jaipur", hospital="MG Hospital", rating=4.5, distance_km=6.0,
             phone="+91-141-2294301", address="Sitapura, Jaipur"),
    ],
    "Psychiatrist": [
        dict(name="Institute of Mental Health Jaipur", hospital="IMH Jaipur", rating=4.3, distance_km=4.5,
             phone="+91-141-2566803", address="JLN Marg, Jaipur"),
    ],
    "General Physician": [
        dict(name="Apex Hospital Jaipur", hospital="Apex Hospital", rating=4.8, distance_km=2.5,
             phone="+91-141-2700000", address="SP-4, Malviya Nagar, Jaipur"),
    ],
}


def _hardcoded_fallback(specialty: str, top_k: int) -> List[DoctorResult]:
    bucket = _HARDCODED.get(specialty) or _HARDCODED.get("General Physician", [])
    return [
        DoctorResult(
            name=d["name"], specialty=specialty, hospital=d["hospital"],
            rating=d["rating"], distance_km=d["distance_km"],
            phone=d["phone"], address=d["address"],
            google_place_id=None, is_open_now=None, source="fallback",
        )
        for d in bucket[:top_k]
    ]


# ── Public API ────────────────────────────────────────────────────────────────

async def find_doctors(
    condition: str,
    specialty: str,
    google_search_term: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    urgency: str = "low",
    emergency_dept: bool = False,
    top_k: int = 5,
) -> List[DoctorResult]:
    """
    Find doctors for a given condition.

    Priority: DynamoDB cache -> OpenStreetMap -> NMC registry -> hardcoded fallback.
    No external API key required.
    """
    has_location = lat is not None and lng is not None

    # Emergency: hospitals only, tighter radius
    radius_km = 15.0
    emergency_only = False
    if urgency.lower() == "emergency" and emergency_dept:
        emergency_only = True
        radius_km = 5.0

    # 1. DynamoDB cache
    if has_location:
        cached = _load_cache(condition, lat, lng)
        if cached:
            logger.info(f"Doctor results served from cache for {condition}")
            return cached[:top_k]

    # 2. OpenStreetMap Overpass (free)
    if has_location:
        try:
            doctors = await _search_overpass(lat, lng, radius_km, specialty, emergency_only, top_k)
            if doctors:
                _save_cache(condition, lat, lng, doctors)
                logger.info(f"OpenStreetMap returned {len(doctors)} results for {specialty}")
                return doctors
        except Exception as e:
            logger.warning(f"Overpass search error: {e} — falling back")

    # 3. NMC seeded registry (50km cap)
    if has_location:
        nmc = _query_nmc_fallback(specialty, lat, lng, top_k)
        if nmc:
            logger.info(f"NMC registry returned {len(nmc)} doctors for {specialty}")
            return nmc

    # 4. Hardcoded Jaipur fallback
    logger.info(f"Using hardcoded fallback for {specialty}")
    return _hardcoded_fallback(specialty, top_k)
