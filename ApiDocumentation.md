Base URL:
https://plumassignment.onrender.com

Auth: None
Formats: JSON + multipart/form-data
Rate Limiting: None
Status: MVP mode

🚀 Endpoints
1️⃣ Health Check

GET /
Returns basic service status.

2️⃣ Register Member

POST /api/v1/members/register
Register a user before filing claims.

Body (JSON):

{
  "member_id": "EMP010",
  "member_name": "Deepak Shah",
  "member_join_date": "2024-08-01",
  "hospital": "Apollo Hospitals",
  "previous_claims_ytd": 0,
  "cashless_request": true
}
Success:
Returns success + saved member info.

3️⃣ Upload Claim

POST /api/v1/claims/upload
Upload documents → OCR → AI extraction → Adjudication → Save result.

Form Fields:
member_id (string)
treatment_date (YYYY-MM-DD)
prescription (file)
bill (file)
test_report (optional file)
Files: PDF/JPG/PNG (max ~10MB each)

Returns:
claim_id
decision (APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW)
approved_amount
Processing takes ~15–30 sec.

4️⃣ Get Claim Result

GET /api/v1/claims/{claim_id}/result
Returns full breakdown:
decision
confidence
approved amount
deductions
extracted data (prescription + bill)
flags/rejections

5️⃣ Member Statistics

GET /api/v1/members/{member_id}/stats
Returns:
total claims
approved / rejected
totals claimed / approved
last claim date

6️⃣ List All Claims

GET /api/v1/claims/all
Query params:
limit (default 50)
offset (default 0)
decision = APPROVED | REJECTED | PARTIAL | MANUAL_REVIEW
Returns paginated claim summaries.

❌ Error Format
Every error returns:
{ "detail": "message" }


Common Codes:

400 — bad input
404 — not found
422 — validation fail
500 — server error