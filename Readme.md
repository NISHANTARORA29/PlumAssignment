🏥 Project Overview
An AI-powered automation tool that processes and adjudicates Outpatient Department (OPD) insurance claims. The system uses OCR and AI to extract data from medical documents, validates claims against policy terms, and makes intelligent approval/rejection decisions.
Live API: https://plumassignment.onrender.com

🎯 Features

Automated Document Processing: OCR + AI extraction from prescriptions, bills, and test reports
Intelligent Adjudication: Rule-based decision engine with 95%+ confidence scores
Policy Validation: Comprehensive checks for eligibility, coverage, limits, and exclusions
Fraud Detection: Pattern analysis for suspicious claims
Database Storage: Complete audit trail in Supabase PostgreSQL
RESTful API: 3 core endpoints + bonus analytics endpoints

📊 Database Schema
Tables
1. members
Stores member registration details
Tracks YTD claims (auto-updates via trigger)

2. claims
All claim submissions
Decision status and amounts
Links to member via foreign key

3. claim_details
Full adjudication results
Extracted document data (JSONB)
Deductions and rejection reasons

4. document_uploads
Metadata for all uploaded files
Processing status tracking

5. audit_log
Complete audit trail
All actions timestamped
Views
v_claims_complete: Joins claims + members + claim_details for API responses
v_member_stats: Aggregated statistics per member

Setup Instructions
Prerequisites

Python 3.11+
Tesseract OCR
Poppler (for PDF processing)
Supabase account
OpenAI API key

🚀 Deployment
Deployed on Render with automatic deploys from Git.
Live URL: https://plumassignment.onrender.com
Deployment Steps (Render)
Connect GitHub repository
Configure build settings:
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT

🛠️ Technology Stack
Backend
FastAPI: Modern Python web framework
Python 3.11: Core language
Uvicorn: ASGI server

AI/ML
OpenAI GPT-4: Document understanding and extraction
Tesseract OCR: Text extraction from images
pdf2image: PDF to image conversion

Database
Supabase: Managed PostgreSQL
PostgREST: Auto-generated REST API

Libraries
Pydantic: Data validation
python-dotenv: Environment management
python-multipart: File upload handling
Pillow: Image processing