import re
import boto3
import uuid
import logging
from botocore.exceptions import ClientError
from app.config import settings
from app.services.s3_service import upload_file, delete_file

logger = logging.getLogger(__name__)

def extract_prescription(image_bytes: bytes) -> dict:
    """Extracts text, medicines, and doctor info from a prescription image using AWS Textract."""
    # 1. Upload image to S3
    filename = f"prescription_{uuid.uuid4().hex}.jpg"
    try:
        s3_key = upload_file(image_bytes, filename, "image/jpeg")
    except Exception as e:
        logger.error(f"Failed to upload prescription to S3: {e}")
        return {"error": "upload_failed", "extraction_confidence": 0.0}

    # 2. Call Textract
    client = boto3.client("textract", **settings.boto3_kwargs)
    try:
        response = client.analyze_document(
            Document={"S3Object": {"Bucket": settings.S3_BUCKET_NAME, "Name": s3_key}},
            FeatureTypes=["FORMS", "TABLES"]
        )
    except ClientError as e:
        logger.error(f"Textract error: {e}")
        delete_file(s3_key)
        return {"error": "textract_failed", "extraction_confidence": 0.0}

    # Clean up S3 file immediately
    delete_file(s3_key)

    # 3. Parse response
    blocks = response.get("Blocks", [])
    
    raw_text_lines = []
    confidences = []
    doctor_name = "Unknown"
    diagnosis_text = ""
    medicines = []
    
    for block in blocks:
        if block["BlockType"] == "LINE":
            text = block.get("Text", "")
            raw_text_lines.append(text)
            if "Confidence" in block:
                confidences.append(block["Confidence"])
                
    raw_text = "\n".join(raw_text_lines)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    extraction_confidence = avg_confidence / 100.0

    if extraction_confidence < 0.5:
        return {
            "raw_text": raw_text,
            "medicines": [],
            "doctor_name": "Unknown",
            "diagnosis_text": "Unclear image",
            "extraction_confidence": extraction_confidence,
            "flag": "low_confidence"
        }

    # Heuristics for extraction
    for i, line in enumerate(raw_text_lines):
        upper_line = line.upper()
        
        # Doctor name heuristic
        if "DR." in upper_line and doctor_name == "Unknown":
            doctor_name = line
        elif i == 0 and doctor_name == "Unknown" and len(line.split()) <= 3:
            doctor_name = line
            
        # Diagnosis heuristic
        if "DIAGNOSIS" in upper_line or "C/O" in upper_line or "COMPLAINTS" in upper_line:
            diagnosis_text += line + " "
            
        # Medicines heuristic
        med_patterns = ["TAB", "CAP", "SYP", "INJ", "MG", "ML"]
        if any(pat in upper_line for pat in med_patterns):
            # Try to extract dosage
            dosage_match = re.search(r'\d+\s*(mg|ml|g|mcg)', upper_line, re.IGNORECASE)
            dosage = dosage_match.group(0) if dosage_match else "Unknown"
            
            # Try to extract frequency
            freq_patterns = [r'\b1-0-1\b', r'\b0-1-0\b', r'\b1-1-1\b', r'\bBD\b', r'\bTDS\b', r'\bOD\b', r'\bQID\b']
            frequency = "Unknown"
            for pat in freq_patterns:
                f_match = re.search(pat, upper_line, re.IGNORECASE)
                if f_match:
                    frequency = f_match.group(0)
                    break
                    
            name = line
            # Clean up dosage and frequency from the name
            name = re.sub(r'\d+\s*(mg|ml|g|mcg)', '', name, flags=re.IGNORECASE)
            for pat in ['1-0-1', '0-1-0', '1-1-1', 'BD', 'TDS', 'OD', 'QID']:
                name = re.sub(r'\b'+pat+r'\b', '', name, flags=re.IGNORECASE)
            name = name.strip()
            
            medicines.append({
                "name": name,
                "dosage": dosage,
                "frequency": frequency
            })

    return {
        "raw_text": raw_text,
        "medicines": medicines,
        "doctor_name": doctor_name.strip(),
        "diagnosis_text": diagnosis_text.strip(),
        "extraction_confidence": extraction_confidence
    }
