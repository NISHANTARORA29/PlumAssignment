"""
FastAPI Application with Supabase Integration
3 Endpoints: Register Member, Upload Documents, Get Results
"""
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
import tempfile
import shutil
from supabase import create_client, Client
from dotenv import load_dotenv

from document_processor import process_claim_documents
from adjudication_engine import ClaimAdjudicator

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="OPD Claim Adjudication API with Supabase",
    description="3-step claim processing with persistent database storage",
    version="2.0.0"
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("SUPABASE_URL and SUPABASE_KEY must be set in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize adjudicator
adjudicator = ClaimAdjudicator()

# Pydantic models
class MemberRegistration(BaseModel):
    member_id: str
    member_name: str
    member_join_date: str  # YYYY-MM-DD
    hospital: Optional[str] = None
    previous_claims_ytd: float = 0
    cashless_request: bool = False

# Helper function
def save_upload_file(upload_file: UploadFile) -> str:
    """Save uploaded file to temporary location"""
    try:
        suffix = os.path.splitext(upload_file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(upload_file.file, tmp)
            return tmp.name
    finally:
        upload_file.file.close()

# ============================================================================
# ENDPOINT 1: REGISTER MEMBER (Store in Supabase)
# ============================================================================
@app.post("/api/v1/members/register")
async def register_member(member: MemberRegistration):
    """
    Step 1: Register a member with all details in Supabase
    
    Request Body (JSON):
    {
        "member_id": "EMP010",
        "member_name": "Deepak Shah",
        "member_join_date": "2024-08-01",
        "hospital": "Apollo Hospitals",
        "previous_claims_ytd": 0,
        "cashless_request": true
    }
    """
    try:
        # Check if member already exists
        existing = supabase.table("members").select("*").eq("member_id", member.member_id).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail=f"Member ID '{member.member_id}' already exists")
        
        # Insert member into database
        member_data = {
            "member_id": member.member_id,
            "member_name": member.member_name,
            "member_join_date": member.member_join_date,
            "hospital": member.hospital,
            "previous_claims_ytd": member.previous_claims_ytd,
            "cashless_request": member.cashless_request
        }
        
        response = supabase.table("members").insert(member_data).execute()
        
        # Log audit
        audit_data = {
            "action_type": "member_registered",
            "member_id": member.member_id,
            "action_data": member_data
        }
        supabase.table("audit_log").insert(audit_data).execute()
        
        return JSONResponse(content={
            "status": "success",
            "message": "Member registered successfully in database",
            "member_id": member.member_id,
            "member_name": member.member_name,
            "registered_at": response.data[0]["registered_at"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# ============================================================================
# ENDPOINT 2: UPLOAD DOCUMENTS (Process and Store in Supabase)
# ============================================================================
@app.post("/api/v1/claims/upload")
async def upload_documents(
    member_id: str = Form(...),
    treatment_date: str = Form(...),  # YYYY-MM-DD
    prescription: UploadFile = File(...),
    bill: UploadFile = File(...),
    test_report: Optional[UploadFile] = File(None)
):
    """
    Step 2: Upload documents for a registered member
    
    Form Data:
    - member_id: EMP010
    - treatment_date: 2024-11-03
    - prescription: (file upload)
    - bill: (file upload)
    - test_report: (optional file upload)
    """
    temp_files = []
    
    try:
        # Check if member exists in database
        member_response = supabase.table("members").select("*").eq("member_id", member_id).execute()
        if not member_response.data:
            raise HTTPException(
                status_code=404, 
                detail=f"Member ID '{member_id}' not found. Please register member first."
            )
        
        member_info = member_response.data[0]
        
        # Log document uploads
        doc_upload_records = []
        
        # Save uploaded files
        prescription_path = save_upload_file(prescription)
        bill_path = save_upload_file(bill)
        temp_files.extend([prescription_path, bill_path])
        
        doc_upload_records.append({
            "document_type": "prescription",
            "original_filename": prescription.filename,
            "file_size_bytes": os.path.getsize(prescription_path),
            "upload_status": "processing"
        })
        
        doc_upload_records.append({
            "document_type": "bill",
            "original_filename": bill.filename,
            "file_size_bytes": os.path.getsize(bill_path),
            "upload_status": "processing"
        })
        
        document_paths = {
            "prescription": prescription_path,
            "bill": bill_path
        }
        
        if test_report:
            test_report_path = save_upload_file(test_report)
            document_paths["test_report"] = test_report_path
            temp_files.append(test_report_path)
            
            doc_upload_records.append({
                "document_type": "test_report",
                "original_filename": test_report.filename,
                "file_size_bytes": os.path.getsize(test_report_path),
                "upload_status": "processing"
            })
        
        # Process documents using OCR and AI
        print(f"Processing documents for member: {member_id}")
        claim_data = process_claim_documents(document_paths)
        
        # Prepare member info for adjudication
        member_adj_info = {
            "member_id": member_info["member_id"],
            "member_name": member_info["member_name"],
            "member_join_date": member_info["member_join_date"],
            "treatment_date": treatment_date,
            "previous_claims_ytd": member_info["previous_claims_ytd"],
            "previous_claims_same_day": 0,  # Can be calculated from recent claims
            "hospital": member_info.get("hospital"),
            "cashless_request": member_info.get("cashless_request", False),
            "preauth_obtained": False  # Can be added as parameter
        }
        
        # Extract claim amount from bill
        claim_amount = claim_data.get("bill", {}).get("total_amount", 0)
        member_adj_info["claim_amount"] = claim_amount
        
        # Run adjudication
        print(f"Running adjudication for claim amount: {claim_amount}")
        decision = adjudicator.adjudicate_claim(claim_data, member_adj_info)
        
        claim_id = decision["claim_id"]
        
        # ===== STORE IN DATABASE =====
        
        # 1. Insert claim record
        claim_record = {
            "claim_id": claim_id,
            "member_id": member_id,
            "treatment_date": treatment_date,
            "claim_amount": claim_amount,
            "decision": decision["decision"],
            "approved_amount": decision["approved_amount"],
            "confidence_score": decision["confidence_score"],
            "notes": decision["notes"]
        }
        supabase.table("claims").insert(claim_record).execute()
        
        # 2. Insert claim details
        claim_details_record = {
            "claim_id": claim_id,
            "rejection_reasons": decision["rejection_reasons"],
            "flags": decision["flags"],
            "copay_amount": decision["deductions"].get("copay", 0),
            "discount_amount": decision["deductions"].get("discount", 0),
            "network_discount": decision.get("network_discount", 0),
            "prescription_data": claim_data.get("prescription"),
            "bill_data": claim_data.get("bill"),
            "test_report_data": claim_data.get("test_reports", []),
            "raw_ocr_text": claim_data.get("raw_texts", {})
        }
        supabase.table("claim_details").insert(claim_details_record).execute()
        
        # 3. Insert document upload records
        for doc_record in doc_upload_records:
            doc_record["claim_id"] = claim_id
            doc_record["upload_status"] = "completed"
            doc_record["ocr_status"] = "completed"
            doc_record["processed_at"] = datetime.now().isoformat()
        
        supabase.table("document_uploads").insert(doc_upload_records).execute()
        
        # 4. Log audit
        audit_data = {
            "action_type": "claim_processed",
            "member_id": member_id,
            "claim_id": claim_id,
            "action_data": {
                "decision": decision["decision"],
                "claim_amount": claim_amount,
                "approved_amount": decision["approved_amount"]
            }
        }
        supabase.table("audit_log").insert(audit_data).execute()
        
        return JSONResponse(content={
            "status": "success",
            "message": "Documents uploaded and claim processed successfully",
            "claim_id": claim_id,
            "member_id": member_id,
            "member_name": member_info["member_name"],
            "decision": decision["decision"],
            "approved_amount": decision["approved_amount"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing claim: {str(e)}")
    
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass

# ============================================================================
# ENDPOINT 3: GET CLAIM RESULT (From Supabase)
# ============================================================================
@app.get("/api/v1/claims/{claim_id}/result")
async def get_claim_result(claim_id: str):
    """
    Step 3: Get the adjudication result for a claim from database
    
    Returns complete decision with approval/rejection details
    """
    try:
        # Fetch from view (joins claims + members + claim_details)
        response = supabase.table("v_claims_complete").select("*").eq("claim_id", claim_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Claim ID '{claim_id}' not found in database"
            )
        
        claim = response.data[0]
        
        # Format response
        result = {
            "claim_id": claim["claim_id"],
            "member_id": claim["member_id"],
            "member_name": claim["member_name"],
            "hospital": claim["hospital"],
            "treatment_date": claim["treatment_date"],
            "processed_at": claim["processed_at"],
            
            # Decision details
            "decision": claim["decision"],
            "confidence_score": float(claim["confidence_score"]) if claim["confidence_score"] else 0,
            "claim_amount": float(claim["claim_amount"]) if claim["claim_amount"] else 0,
            "approved_amount": float(claim["approved_amount"]) if claim["approved_amount"] else 0,
            
            # Additional info
            "rejection_reasons": claim["rejection_reasons"] or [],
            "flags": claim["flags"] or [],
            "notes": claim["notes"],
            
            "deductions": {
                "copay": float(claim["copay_amount"]) if claim["copay_amount"] else 0,
                "discount": float(claim["discount_amount"]) if claim["discount_amount"] else 0
            },
            
            # Extracted data
            "extracted_data": {
                "prescription": claim["prescription_data"],
                "bill": claim["bill_data"]
            }
        }
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# ============================================================================
# BONUS ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "OPD Claim Adjudication API with Supabase",
        "version": "2.0.0",
        "database": "Supabase PostgreSQL",
        "endpoints": {
            "1_register": "POST /api/v1/members/register",
            "2_upload": "POST /api/v1/claims/upload",
            "3_result": "GET /api/v1/claims/{claim_id}/result",
            "bonus_member_stats": "GET /api/v1/members/{member_id}/stats",
            "bonus_all_claims": "GET /api/v1/claims/all"
        }
    }

@app.get("/api/v1/members/{member_id}/stats")
async def get_member_stats(member_id: str):
    """Get statistics for a specific member"""
    try:
        response = supabase.table("v_member_stats").select("*").eq("member_id", member_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail=f"Member '{member_id}' not found")
        
        stats = response.data[0]
        
        return JSONResponse(content={
            "member_id": stats["member_id"],
            "member_name": stats["member_name"],
            "member_join_date": stats["member_join_date"],
            "hospital": stats["hospital"],
            "statistics": {
                "total_claims": stats["total_claims"],
                "approved_claims": stats["approved_claims"],
                "rejected_claims": stats["rejected_claims"],
                "total_claimed": float(stats["total_claimed"]) if stats["total_claimed"] else 0,
                "total_approved": float(stats["total_approved"]) if stats["total_approved"] else 0,
                "last_claim_date": stats["last_claim_date"]
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/v1/claims/all")
async def get_all_claims(limit: int = 50, offset: int = 0, decision: Optional[str] = None):
    """Get all claims with optional filtering"""
    try:
        query = supabase.table("v_claims_complete").select("*")
        
        if decision:
            query = query.eq("decision", decision.upper())
        
        response = query.order("processed_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return JSONResponse(content={
            "total": len(response.data),
            "limit": limit,
            "offset": offset,
            "claims": response.data
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)