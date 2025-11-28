"""
Document Processing Module
Handles OCR extraction using Tesseract and AI-powered data extraction
"""
import pytesseract
from PIL import Image
import pdf2image
import openai
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

print("Loaded:", os.getenv("OPENAI_API_KEY"))
def extract_text_from_document(file_path):
    """
    Extract text from PDF or image using Tesseract OCR
    
    Args:
        file_path: Path to the document file
        
    Returns:
        str: Extracted text content
    """
    try:
        # Check file extension
        if file_path.lower().endswith('.pdf'):
            # Convert PDF to images
            images = pdf2image.convert_from_path(file_path)
            text = ""
            for image in images:
                text += pytesseract.image_to_string(image)
            return text
        else:
            # Process as image
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""


def extract_structured_data_with_ai(raw_text, document_type="prescription"):
    """
    Use OpenAI to extract structured data from raw OCR text
    
    Args:
        raw_text: Raw extracted text from document
        document_type: Type of document (prescription, bill, test_report)
        
    Returns:
        dict: Structured data extracted from document
    """
    
    prompts = {
        "prescription": """
        Extract the following information from this medical prescription:
        - doctor_name
        - doctor_reg (registration number)
        - patient_name
        - patient_age
        - diagnosis
        - medicines_prescribed (list)
        - tests_prescribed (list if any)
        - treatment_date
        
        Return ONLY a valid JSON object with these fields. If a field is not found, use null.
        """,
        
        "bill": """
        Extract the following information from this medical bill:
        - hospital_name
        - bill_number
        - bill_date
        - patient_name
        - consultation_fee (number)
        - diagnostic_tests (number)
        - test_names (list)
        - medicines (number)
        - pharmacy_charges (number)
        - dental_charges (number)
        - total_amount (number)
        - items (list of {name, amount})
        
        Return ONLY a valid JSON object with these fields. If a field is not found, use null.
        """,
        
        "test_report": """
        Extract the following information from this diagnostic test report:
        - lab_name
        - patient_name
        - test_date
        - tests_conducted (list)
        - doctor_referred_by
        
        Return ONLY a valid JSON object with these fields. If a field is not found, use null.
        """
    }
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a medical document data extraction expert. Extract information accurately and return valid JSON only."},
                {"role": "user", "content": f"{prompts.get(document_type, prompts['prescription'])}\n\nDocument Text:\n{raw_text}"}
            ],
            temperature=0.1,
            max_tokens=1000
        )
        
        # Extract JSON from response
        result = response.choices[0].message.content.strip()
        
        # Clean up response (remove markdown code blocks if present)
        result = result.replace("```json", "").replace("```", "").strip()
        
        # Parse JSON
        structured_data = json.loads(result)
        return structured_data
        
    except Exception as e:
        print(f"Error in AI extraction: {e}")
        return {}


def process_claim_documents(document_paths):
    """
    Process all claim documents and extract structured information
    + Auto-extract dental/medical procedures from raw text
    """

    claim_data = {
        "prescription": None,
        "bill": None,
        "test_reports": [],
        "raw_texts": {}
    }

    for doc_type, file_path in document_paths.items():
        if not file_path:
            continue

        print(f"Processing {doc_type}: {file_path}")

        # -------------------------------------------------
        # 1. RAW OCR TEXT
        # -------------------------------------------------
        raw_text = extract_text_from_document(file_path)
        claim_data["raw_texts"][doc_type] = raw_text

        # -------------------------------------------------
        # 2. AI STRUCTURED EXTRACTION
        # -------------------------------------------------
        structured_data = extract_structured_data_with_ai(raw_text, doc_type)

        # -------------------------------------------------
        # 3. ASSIGN STRUCTURED OUTPUT
        # -------------------------------------------------
        if doc_type == "prescription":
            claim_data["prescription"] = structured_data

            # ----------------------------------------------
            # AUTO-EXTRACT PROCEDURES FROM RAW TEXT
            # ----------------------------------------------
            raw_lower = raw_text.lower()
            procedures = []

            # Extract bullet-style procedure lines (common in prescriptions)
            # Example: "- Root canal treatment"
            proc_lines = re.findall(r"-\s*(.+)", raw_text, flags=re.IGNORECASE)
            for p in proc_lines:
                cleaned = p.strip()
                if cleaned:
                    procedures.append(cleaned)

            # Backup keyword-based extraction
            if "root canal" in raw_lower:
                procedures.append("Root Canal Treatment")
            if "whitening" in raw_lower:
                procedures.append("Teeth Whitening (Cosmetic)")
            if "scaling" in raw_lower:
                procedures.append("Scaling / Cleaning")
            if "filling" in raw_lower:
                procedures.append("Dental Filling")

            # Deduplicate (preserve order)
            procedures = list(dict.fromkeys(procedures))

            # Add procedures list to prescription section
            claim_data["prescription"]["procedures"] = procedures

        elif doc_type == "bill":
            claim_data["bill"] = structured_data

            # ----------------------------------------------
            # AUTO-CHECK BILL ITEMS FOR DENTAL SIGNALS
            # ----------------------------------------------
            items = structured_data.get("items", [])
            dental_terms = ["root canal", "whitening", "scaling", "filling"]

            for item in items:
                if "root canal" in item["name"].lower():
                    item.setdefault("category", "dental")
                if "whiten" in item["name"].lower():
                    item.setdefault("category", "cosmetic")
                if "scaling" in item["name"].lower():
                    item.setdefault("category", "dental")
                if "filling" in item["name"].lower():
                    item.setdefault("category", "dental")

        elif doc_type == "test_report":
            claim_data["test_reports"].append(structured_data)

    return claim_data



def validate_doctor_registration(reg_number):
    """
    Validate doctor registration number format
    Format: STATE_CODE/NUMBER/YEAR or AYUR/STATE/NUMBER/YEAR
    
    Args:
        reg_number: Doctor registration number
        
    Returns:
        bool: True if valid format
    """
    if not reg_number:
        return False
    
    # Pattern 1: Standard medical - XX/XXXXX/XXXX (State/Number/Year)
    pattern1 = r'^[A-Z]{2,4}/\d{4,6}/\d{4}$'

    pattern2 = r'^(AYUR|HOMEO|UNANI)/[A-Z]{2,4}/\d{4,6}/\d{4}$'

    return bool(re.match(pattern1, reg_number) or re.match(pattern2, reg_number))


def check_document_completeness(claim_data):
    missing = []
    
    if not claim_data.get("prescription"):
        missing.append("prescription")
    
    if not claim_data.get("bill"):
        missing.append("bill")

    return len(missing) == 0, missing



def check_document_completeness(claim_data):
    """
    Check if all required documents are present
    
    Args:
        claim_data: Structured claim data
        
    Returns:
        tuple: (is_complete: bool, missing_docs: list)
    """
    missing = []
    
    if not claim_data.get("prescription"):
        missing.append("prescription")
    
    if not claim_data.get("bill"):
        missing.append("bill")
    
    return len(missing) == 0, missing

    
    return bool(re.match(pattern1, reg_number) or re.match(pattern2, reg_number))


def check_document_completeness(claim_data):
    """
    Check if all required documents are present
    
    Args:
        claim_data: Structured claim data
        
    Returns:
        tuple: (is_complete: bool, missing_docs: list)
    """
    missing = []
    
    if not claim_data.get("prescription"):
        missing.append("prescription")
    
    if not claim_data.get("bill"):
        missing.append("bill")
    
    return len(missing) == 0, missing