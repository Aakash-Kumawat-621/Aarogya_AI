"""
backend/app/modules/doctors/finder.py

Queries DynamoDB aarogya-hospitals table for doctors matching the
required specialty. Returns top 3 by rating.

In Module 5, this will be augmented with Google Places live search
for real-time proximity matching.
"""

import logging
from typing import List

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from app.config import settings
from app.models.response_models import DoctorResult

logger = logging.getLogger(__name__)

# Fallback doctors used when DynamoDB query returns nothing
# (e.g. table not yet seeded, or specialty not found)
_FALLBACK_DOCTORS: dict[str, List[DoctorResult]] = {
    "Cardiologist": [
        DoctorResult(
            name="Dr. Ramesh Gupta",
            specialty="Cardiologist",
            hospital="Apollo Hospitals",
            rating=4.8,
            distance_km=2.5,
            phone="+91-98765-43210",
            address="21 Nehru Marg, New Delhi",
        ),
        DoctorResult(
            name="Dr. Sunita Sharma",
            specialty="Cardiologist",
            hospital="Fortis Healthcare",
            rating=4.7,
            distance_km=3.1,
            phone="+91-98765-00001",
            address="B-22 Sector 62, Noida",
        ),
    ],
    "Pulmonologist": [
        DoctorResult(
            name="Dr. Anil Mehta",
            specialty="Pulmonologist",
            hospital="Max Super Speciality Hospital",
            rating=4.6,
            distance_km=4.0,
            phone="+91-98765-11111",
            address="Press Enclave Marg, Saket, New Delhi",
        ),
    ],
    "Gastroenterologist": [
        DoctorResult(
            name="Dr. Priya Nair",
            specialty="Gastroenterologist",
            hospital="Medanta - The Medicity",
            rating=4.9,
            distance_km=6.2,
            phone="+91-98765-22222",
            address="CH Baktawar Singh Rd, Sector 38, Gurugram",
        ),
    ],
    "Neurologist": [
        DoctorResult(
            name="Dr. Vikram Singh",
            specialty="Neurologist",
            hospital="AIIMS Delhi",
            rating=4.9,
            distance_km=5.5,
            phone="+91-98765-33333",
            address="Sri Aurobindo Marg, Ansari Nagar, New Delhi",
        ),
    ],
    "Dermatologist": [
        DoctorResult(
            name="Dr. Meera Kapoor",
            specialty="Dermatologist",
            hospital="Skin & You Clinic",
            rating=4.5,
            distance_km=1.8,
            phone="+91-98765-44444",
            address="14 Connaught Place, New Delhi",
        ),
    ],
    "Orthopedist": [
        DoctorResult(
            name="Dr. Suresh Rao",
            specialty="Orthopedist",
            hospital="Manipal Hospitals",
            rating=4.7,
            distance_km=3.4,
            phone="+91-98765-55555",
            address="98 HAL Airport Road, Bangalore",
        ),
    ],
    "Endocrinologist": [
        DoctorResult(
            name="Dr. Kavita Patel",
            specialty="Endocrinologist",
            hospital="Kokilaben Dhirubhai Ambani Hospital",
            rating=4.8,
            distance_km=7.1,
            phone="+91-98765-66666",
            address="Rao Saheb Achutrao Patwardhan Marg, Mumbai",
        ),
    ],
    "General Physician": [
        DoctorResult(
            name="Dr. Rahul Verma",
            specialty="General Physician",
            hospital="City Health Clinic",
            rating=4.4,
            distance_km=0.8,
            phone="+91-98765-77777",
            address="12 MG Road, Pune",
        ),
        DoctorResult(
            name="Dr. Anita Joshi",
            specialty="General Physician",
            hospital="Care Well Hospital",
            rating=4.3,
            distance_km=1.2,
            phone="+91-98765-88888",
            address="45 Linking Road, Mumbai",
        ),
    ],
}


def find_doctors(specialty: str, top_k: int = 3) -> List[DoctorResult]:
    """
    Finds doctors for a given specialty.

    Priority:
      1. DynamoDB aarogya-hospitals table (seeded data)
      2. In-code fallback list (always works, even before seeding)

    Args:
        specialty: Specialist type e.g. "Cardiologist"
        top_k: Max number of doctors to return

    Returns:
        List of DoctorResult objects sorted by rating
    """
    # Try DynamoDB first
    try:
        dynamodb = boto3.resource("dynamodb", **settings.boto3_kwargs)
        table = dynamodb.Table(settings.DYNAMODB_HOSPITALS_TABLE)
        response = table.scan(
            FilterExpression=Attr("specialty").eq(specialty),
            Limit=20,
        )
        items = response.get("Items", [])
        if items:
            doctors = [
                DoctorResult(
                    name=item.get("name", "Unknown"),
                    specialty=item.get("specialty", specialty),
                    hospital=item.get("hospital", "Unknown"),
                    rating=float(item.get("rating", 4.0)),
                    distance_km=float(item.get("distance_km", 5.0)),
                    phone=item.get("phone", ""),
                    address=item.get("address", ""),
                )
                for item in items
            ]
            doctors.sort(key=lambda d: d.rating, reverse=True)
            logger.info(f"Found {len(doctors)} doctors from DynamoDB for {specialty}")
            return doctors[:top_k]
    except ClientError as e:
        logger.warning(
            f"DynamoDB doctor lookup failed: {e.response['Error']['Message']} "
            f"— using fallback list"
        )
    except Exception as e:
        logger.warning(f"Doctor lookup error: {e} — using fallback list")

    # Fallback to in-code list
    fallback = _FALLBACK_DOCTORS.get(specialty) or _FALLBACK_DOCTORS.get("General Physician", [])
    logger.info(f"Using fallback doctors for {specialty}")
    return fallback[:top_k]
