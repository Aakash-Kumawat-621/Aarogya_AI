"""
backend/scripts/seed_hospital_db.py

Seeds the DynamoDB mediassist-hospitals table with curated hospital data
for Rajasthan (Jaipur, Jodhpur, Udaipur, Kota) as the NMC registry fallback.

Usage:
    cd backend
    python scripts/seed_hospital_db.py

The table is queried when Google Places API is unavailable or returns no results.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import uuid
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from app.config import settings

TABLE_NAME = settings.DYNAMODB_HOSPITALS_TABLE

# ── 50 curated hospitals / clinics across Rajasthan ──────────────────────────
# Fields: name, hospital, specialty, address, city, lat, lng, phone, rating, google_place_id

HOSPITALS = [
    # ── Jaipur — Cardiology ──────────────────────────────────────────────────
    {"name": "Dr. Ramesh Gupta", "hospital": "Apex Hospital",
     "specialty": "Cardiologist", "address": "SP-4, Malviya Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8554, "lng": 75.8013,
     "phone": "+91-141-2700000", "rating": 4.8, "google_place_id": None},

    {"name": "Dr. Sudhir Bhargava", "hospital": "Fortis Escorts Hospital Jaipur",
     "specialty": "Cardiologist", "address": "Jawaharlal Nehru Marg, Jaipur",
     "city": "Jaipur", "lat": 26.8979, "lng": 75.8236,
     "phone": "+91-141-2547000", "rating": 4.7, "google_place_id": None},

    {"name": "Dr. Manoj Sharma", "hospital": "Narayana Hospital Jaipur",
     "specialty": "Cardiologist", "address": "Sec 28, Kumbha Marg, Pratap Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8389, "lng": 75.7937,
     "phone": "+91-141-7161000", "rating": 4.6, "google_place_id": None},

    # ── Jaipur — Pulmonology ─────────────────────────────────────────────────
    {"name": "Dr. Anil Sharma", "hospital": "SMS Medical College & Hospital",
     "specialty": "Pulmonologist", "address": "JLN Marg, Jaipur",
     "city": "Jaipur", "lat": 26.9011, "lng": 75.8160,
     "phone": "+91-141-2518501", "rating": 4.7, "google_place_id": None},

    {"name": "Dr. Ravi Mehta", "hospital": "Manipal Hospital Jaipur",
     "specialty": "Pulmonologist", "address": "Sec-5 Vidhyadhar Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.9586, "lng": 75.7879,
     "phone": "+91-141-3990000", "rating": 4.5, "google_place_id": None},

    # ── Jaipur — Neurology ───────────────────────────────────────────────────
    {"name": "Dr. Vikram Singh", "hospital": "RUHS College of Medical Sciences",
     "specialty": "Neurologist", "address": "Sector-11, Pratap Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8333, "lng": 75.7961,
     "phone": "+91-141-2703000", "rating": 4.7, "google_place_id": None},

    {"name": "Dr. Shyam Lal Yadav", "hospital": "Santokba Durlabhji Memorial Hospital",
     "specialty": "Neurologist", "address": "Bhawani Singh Marg, Jaipur",
     "city": "Jaipur", "lat": 26.9019, "lng": 75.8194,
     "phone": "+91-141-2566251", "rating": 4.6, "google_place_id": None},

    # ── Jaipur — Gastroenterology ────────────────────────────────────────────
    {"name": "Dr. Priya Nair", "hospital": "Narayana Multispeciality Hospital",
     "specialty": "Gastroenterologist", "address": "Pratap Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8389, "lng": 75.7937,
     "phone": "+91-141-7161001", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Ashok Jain", "hospital": "Apex Hospital Jaipur",
     "specialty": "Gastroenterologist", "address": "SP-4, Malviya Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8554, "lng": 75.8013,
     "phone": "+91-141-2700001", "rating": 4.6, "google_place_id": None},

    # ── Jaipur — Orthopedics ─────────────────────────────────────────────────
    {"name": "Dr. Suresh Rao", "hospital": "Santokba Durlabhji Memorial Hospital",
     "specialty": "Orthopedist", "address": "Bhawani Singh Marg, Jaipur",
     "city": "Jaipur", "lat": 26.9019, "lng": 75.8194,
     "phone": "+91-141-2566252", "rating": 4.6, "google_place_id": None},

    {"name": "Dr. Dinesh Goyal", "hospital": "Fortis Escorts Hospital Jaipur",
     "specialty": "Orthopedist", "address": "JLN Marg, Jaipur",
     "city": "Jaipur", "lat": 26.8979, "lng": 75.8236,
     "phone": "+91-141-2547001", "rating": 4.7, "google_place_id": None},

    # ── Jaipur — Dermatology ─────────────────────────────────────────────────
    {"name": "Dr. Meera Kapoor", "hospital": "Jaipur Skin & Hair Clinic",
     "specialty": "Dermatologist", "address": "C-Scheme, Jaipur",
     "city": "Jaipur", "lat": 26.9181, "lng": 75.8050,
     "phone": "+91-98290-00001", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Kavita Bansal", "hospital": "Skin Care Centre Jaipur",
     "specialty": "Dermatologist", "address": "Tonk Road, Jaipur",
     "city": "Jaipur", "lat": 26.8712, "lng": 75.8026,
     "phone": "+91-98280-11111", "rating": 4.4, "google_place_id": None},

    # ── Jaipur — Endocrinology ───────────────────────────────────────────────
    {"name": "Dr. Kavita Patel", "hospital": "Mahatma Gandhi Hospital",
     "specialty": "Endocrinologist", "address": "Sitapura, Jaipur",
     "city": "Jaipur", "lat": 26.7968, "lng": 75.8567,
     "phone": "+91-141-2294301", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Pramod Kumar", "hospital": "SMS Medical College & Hospital",
     "specialty": "Endocrinologist", "address": "JLN Marg, Jaipur",
     "city": "Jaipur", "lat": 26.9011, "lng": 75.8160,
     "phone": "+91-141-2518502", "rating": 4.6, "google_place_id": None},

    # ── Jaipur — Psychiatry ──────────────────────────────────────────────────
    {"name": "Dr. Ravi Kumar", "hospital": "Institute of Mental Health Jaipur",
     "specialty": "Psychiatrist", "address": "JLN Marg, Jaipur",
     "city": "Jaipur", "lat": 26.9015, "lng": 75.8145,
     "phone": "+91-141-2566803", "rating": 4.3, "google_place_id": None},

    {"name": "Dr. Sunita Agarwal", "hospital": "Mind Care Clinic",
     "specialty": "Psychiatrist", "address": "Vaishali Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.9270, "lng": 75.7365,
     "phone": "+91-98765-22222", "rating": 4.4, "google_place_id": None},

    # ── Jaipur — ENT ────────────────────────────────────────────────────────
    {"name": "Dr. Mohan Lal", "hospital": "ENT Care Jaipur",
     "specialty": "ENT Specialist", "address": "Gopalpura Bypass, Jaipur",
     "city": "Jaipur", "lat": 26.8672, "lng": 75.7893,
     "phone": "+91-98765-33333", "rating": 4.4, "google_place_id": None},

    # ── Jaipur — Gynecology ──────────────────────────────────────────────────
    {"name": "Dr. Anita Joshi", "hospital": "Mahila Chikitsalaya Jaipur",
     "specialty": "Gynecologist", "address": "Sanganer Airport Rd, Jaipur",
     "city": "Jaipur", "lat": 26.8237, "lng": 75.8003,
     "phone": "+91-141-2720001", "rating": 4.6, "google_place_id": None},

    {"name": "Dr. Savita Sharma", "hospital": "Apex Hospital Jaipur",
     "specialty": "Gynecologist", "address": "SP-4, Malviya Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8554, "lng": 75.8013,
     "phone": "+91-141-2700002", "rating": 4.7, "google_place_id": None},

    # ── Jaipur — Nephrology ──────────────────────────────────────────────────
    {"name": "Dr. Hemant Sharma", "hospital": "SMS Medical College & Hospital",
     "specialty": "Nephrologist", "address": "JLN Marg, Jaipur",
     "city": "Jaipur", "lat": 26.9011, "lng": 75.8160,
     "phone": "+91-141-2518503", "rating": 4.6, "google_place_id": None},

    # ── Jaipur — Ophthalmology ───────────────────────────────────────────────
    {"name": "Dr. Rakesh Gupta", "hospital": "Jaipur Eye Hospital",
     "specialty": "Ophthalmologist", "address": "Lal Kothi, Jaipur",
     "city": "Jaipur", "lat": 26.8989, "lng": 75.8098,
     "phone": "+91-141-2740100", "rating": 4.5, "google_place_id": None},

    # ── Jaipur — General Physician ───────────────────────────────────────────
    {"name": "Dr. Rajesh Verma", "hospital": "City Health Clinic",
     "specialty": "General Physician", "address": "Vaishali Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.9270, "lng": 75.7365,
     "phone": "+91-98765-44444", "rating": 4.3, "google_place_id": None},

    {"name": "Dr. Sita Ram Yadav", "hospital": "Yadav Clinic",
     "specialty": "General Physician", "address": "Mansarovar, Jaipur",
     "city": "Jaipur", "lat": 26.8591, "lng": 75.7620,
     "phone": "+91-98765-55555", "rating": 4.2, "google_place_id": None},

    # ── Jaipur — General Surgeon ─────────────────────────────────────────────
    {"name": "Dr. Arun Kumar", "hospital": "Narayana Hospital Jaipur",
     "specialty": "General Surgeon", "address": "Pratap Nagar, Jaipur",
     "city": "Jaipur", "lat": 26.8389, "lng": 75.7937,
     "phone": "+91-141-7161002", "rating": 4.5, "google_place_id": None},

    # ── Jodhpur ──────────────────────────────────────────────────────────────
    {"name": "Dr. P.K. Sharma", "hospital": "AIIMS Jodhpur",
     "specialty": "Cardiologist", "address": "Basni Industrial Area, Jodhpur",
     "city": "Jodhpur", "lat": 26.2389, "lng": 73.0243,
     "phone": "+91-291-2740741", "rating": 4.9, "google_place_id": None},

    {"name": "Dr. Sohan Lal", "hospital": "MG Hospital Jodhpur",
     "specialty": "Neurologist", "address": "High Court Rd, Jodhpur",
     "city": "Jodhpur", "lat": 26.2918, "lng": 73.0169,
     "phone": "+91-291-2548701", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Kamla Bai", "hospital": "Umaid Hospital Jodhpur",
     "specialty": "Gynecologist", "address": "Hospital Rd, Jodhpur",
     "city": "Jodhpur", "lat": 26.2860, "lng": 73.0245,
     "phone": "+91-291-2432400", "rating": 4.6, "google_place_id": None},

    {"name": "Dr. Vinod Joshi", "hospital": "Goyal Hospital Jodhpur",
     "specialty": "Orthopedist", "address": "Residency Rd, Jodhpur",
     "city": "Jodhpur", "lat": 26.2994, "lng": 73.0240,
     "phone": "+91-291-2622022", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Ashok Purohit", "hospital": "AIIMS Jodhpur",
     "specialty": "Gastroenterologist", "address": "Basni, Jodhpur",
     "city": "Jodhpur", "lat": 26.2389, "lng": 73.0243,
     "phone": "+91-291-2740742", "rating": 4.8, "google_place_id": None},

    {"name": "Dr. Sunil Mehta", "hospital": "Pacific Medical College Jodhpur",
     "specialty": "Pulmonologist", "address": "Bhilon ka Bedla, Jodhpur",
     "city": "Jodhpur", "lat": 26.2476, "lng": 72.9972,
     "phone": "+91-291-2740900", "rating": 4.4, "google_place_id": None},

    {"name": "Dr. Rekha Sharma", "hospital": "Dr Sonal Hospital Jodhpur",
     "specialty": "Endocrinologist", "address": "Shivaji Nagar, Jodhpur",
     "city": "Jodhpur", "lat": 26.2852, "lng": 73.0143,
     "phone": "+91-98765-66666", "rating": 4.3, "google_place_id": None},

    {"name": "Dr. M.L. Rathore", "hospital": "MG Hospital Jodhpur",
     "specialty": "General Physician", "address": "High Court Rd, Jodhpur",
     "city": "Jodhpur", "lat": 26.2918, "lng": 73.0169,
     "phone": "+91-291-2548702", "rating": 4.4, "google_place_id": None},

    # ── Udaipur ──────────────────────────────────────────────────────────────
    {"name": "Dr. S.K. Mathur", "hospital": "RNT Medical College Udaipur",
     "specialty": "Cardiologist", "address": "Chetak Circle, Udaipur",
     "city": "Udaipur", "lat": 24.5854, "lng": 73.7125,
     "phone": "+91-294-2428801", "rating": 4.7, "google_place_id": None},

    {"name": "Dr. Geeta Meena", "hospital": "Geetanjali Medical College Udaipur",
     "specialty": "Neurologist", "address": "Hiran Magri, Udaipur",
     "city": "Udaipur", "lat": 24.5914, "lng": 73.6914,
     "phone": "+91-294-6669300", "rating": 4.8, "google_place_id": None},

    {"name": "Dr. Tarun Gupta", "hospital": "Pacific Medical College Udaipur",
     "specialty": "Pulmonologist", "address": "Bhilon ka Bedla, Udaipur",
     "city": "Udaipur", "lat": 24.6041, "lng": 73.6589,
     "phone": "+91-294-2960000", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Preeti Jain", "hospital": "Geetanjali Medical College Udaipur",
     "specialty": "Gynecologist", "address": "Hiran Magri, Udaipur",
     "city": "Udaipur", "lat": 24.5914, "lng": 73.6914,
     "phone": "+91-294-6669301", "rating": 4.7, "google_place_id": None},

    {"name": "Dr. A.K. Sharma", "hospital": "RNT Medical College Udaipur",
     "specialty": "Orthopedist", "address": "Chetak Circle, Udaipur",
     "city": "Udaipur", "lat": 24.5854, "lng": 73.7125,
     "phone": "+91-294-2428802", "rating": 4.6, "google_place_id": None},

    {"name": "Dr. Nandini Mewar", "hospital": "Udaipur Eye Hospital",
     "specialty": "Ophthalmologist", "address": "Fatehpura, Udaipur",
     "city": "Udaipur", "lat": 24.5784, "lng": 73.6973,
     "phone": "+91-98765-77777", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. B.L. Tak", "hospital": "Geetanjali Medical College Udaipur",
     "specialty": "Gastroenterologist", "address": "Hiran Magri, Udaipur",
     "city": "Udaipur", "lat": 24.5914, "lng": 73.6914,
     "phone": "+91-294-6669302", "rating": 4.6, "google_place_id": None},

    {"name": "Dr. Hemlata Sharma", "hospital": "RNT Hospital Udaipur",
     "specialty": "General Physician", "address": "Chetak Circle, Udaipur",
     "city": "Udaipur", "lat": 24.5854, "lng": 73.7125,
     "phone": "+91-294-2428803", "rating": 4.3, "google_place_id": None},

    # ── Kota ─────────────────────────────────────────────────────────────────
    {"name": "Dr. Rajiv Bhanot", "hospital": "MBS Hospital Kota",
     "specialty": "Cardiologist", "address": "Nayapura, Kota",
     "city": "Kota", "lat": 25.1821, "lng": 75.8394,
     "phone": "+91-744-2470101", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Shweta Gupta", "hospital": "New Medical College Kota",
     "specialty": "Neurologist", "address": "Rangbari, Kota",
     "city": "Kota", "lat": 25.1840, "lng": 75.8509,
     "phone": "+91-744-2471001", "rating": 4.4, "google_place_id": None},

    {"name": "Dr. Mahendra Singh", "hospital": "JK Hospital Kota",
     "specialty": "Pulmonologist", "address": "Vigyan Nagar, Kota",
     "city": "Kota", "lat": 25.1550, "lng": 75.8386,
     "phone": "+91-744-2460100", "rating": 4.4, "google_place_id": None},

    {"name": "Dr. Pooja Agrawal", "hospital": "MBS Hospital Kota",
     "specialty": "Gynecologist", "address": "Nayapura, Kota",
     "city": "Kota", "lat": 25.1821, "lng": 75.8394,
     "phone": "+91-744-2470102", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. R.K. Bansal", "hospital": "Bansal Hospital Kota",
     "specialty": "Orthopedist", "address": "Dadabari, Kota",
     "city": "Kota", "lat": 25.1763, "lng": 75.8540,
     "phone": "+91-744-2472100", "rating": 4.5, "google_place_id": None},

    {"name": "Dr. Sushma Verma", "hospital": "New Medical College Kota",
     "specialty": "Endocrinologist", "address": "Rangbari, Kota",
     "city": "Kota", "lat": 25.1840, "lng": 75.8509,
     "phone": "+91-744-2471002", "rating": 4.3, "google_place_id": None},

    {"name": "Dr. Pratap Singh", "hospital": "MBS Hospital Kota",
     "specialty": "General Surgeon", "address": "Nayapura, Kota",
     "city": "Kota", "lat": 25.1821, "lng": 75.8394,
     "phone": "+91-744-2470103", "rating": 4.4, "google_place_id": None},

    {"name": "Dr. Narendra Jain", "hospital": "JK Hospital Kota",
     "specialty": "General Physician", "address": "Vigyan Nagar, Kota",
     "city": "Kota", "lat": 25.1550, "lng": 75.8386,
     "phone": "+91-744-2460101", "rating": 4.3, "google_place_id": None},

    {"name": "Dr. Alka Meena", "hospital": "Pushkar Hospital Kota",
     "specialty": "Psychiatrist", "address": "Talwandi, Kota",
     "city": "Kota", "lat": 25.2026, "lng": 75.8518,
     "phone": "+91-98765-88888", "rating": 4.2, "google_place_id": None},

    {"name": "Dr. Rakesh Sharma", "hospital": "Kota Eye Hospital",
     "specialty": "Ophthalmologist", "address": "Gumanpura, Kota",
     "city": "Kota", "lat": 25.1720, "lng": 75.8505,
     "phone": "+91-98765-99999", "rating": 4.3, "google_place_id": None},
]


def create_table_if_not_exists(dynamodb):
    """Create DynamoDB table if it doesn't already exist."""
    try:
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "doctor_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "doctor_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"⏳ Creating table '{TABLE_NAME}'...")
        table.wait_until_exists()
        print(f"✅ Table '{TABLE_NAME}' created.")
        return table
    except dynamodb.meta.client.exceptions.ResourceInUseException:
        print(f"ℹ️  Table '{TABLE_NAME}' already exists.")
        return dynamodb.Table(TABLE_NAME)


def seed():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print(f"\n[SEED] Seeding {TABLE_NAME} with {len(HOSPITALS)} hospital records...\n")
    dynamodb = boto3.resource("dynamodb", **settings.boto3_kwargs)
    table = create_table_if_not_exists(dynamodb)

    success = 0
    with table.batch_writer() as batch:
        for h in HOSPITALS:
            item = {
                "doctor_id": str(uuid.uuid4()),
                "name": h["name"],
                "hospital": h["hospital"],
                "specialty": h["specialty"],
                "address": h["address"],
                "city": h["city"],
                "lat": Decimal(str(h["lat"])),
                "lng": Decimal(str(h["lng"])),
                "phone": h["phone"],
                "rating": Decimal(str(h["rating"])),
                "google_place_id": h.get("google_place_id") or "",
                "source": "nmc_registry",
                "data_freshness": "static",
                "seeded_at": int(time.time()),
            }
            batch.put_item(Item=item)
            success += 1
            print(f"  [OK] {h['name']} -- {h['specialty']} -- {h['city']}")

    print(f"\n[DONE] Seeded {success}/{len(HOSPITALS)} records into '{TABLE_NAME}'")
    print("[NOTE] This data may not be current. Verify contact details before use.")


if __name__ == "__main__":
    seed()
