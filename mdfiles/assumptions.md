Document Processing

Docs must be clear, English, PDF/PNG/JPG, <10MB.
OCR + GPT must be available.
Assumes standard medical formats.
Unique member ID.
Waiting period from join date.
One policy per member.
No dependents or employment checks.

Supabase DB, JSONB.

No auth, no rate limiting.
Data Validation
Dates: YYYY-MM-DD.
Positive amounts only.
Loose name/date matching.
Business Logic
One claim per upload.
No edits/cancellations.
No family floater.
OCR/GPT errors assumed rare.
Unknown categories → consultation.
Unknown hospitals → non-network.

Security

HTTPS only.
Env vars for secrets.
No virus scanning.
PII stored raw.
Production Limits
Low traffic expected.
No caching, no autoscale.

