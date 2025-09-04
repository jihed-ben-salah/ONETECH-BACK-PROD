# extraction_api (Django)

Lightweight Django REST API exposing the form extraction endpoint with enforced normalization (uap numeric, equipe Roman numerals I–X).

## Endpoints
- `GET /health/` -> `{ status: "ok", model: <gemini model> }`
- `POST /extract/` (multipart/form-data)
  - Fields:
    - `document_type`: one of existing categories (e.g. `defauts`, `kosu`, `npt`, `rebut` ...)
    - `file`: image file
  - Response: `{ status: "success", data: { ...extraction... } }`

## Local Run
1. (Optional) Create virtual env
2. Install deps: `pip install -r requirements.txt`
3. Export env vars (PowerShell example):
   ```powershell
   $env:GOOGLE_API_KEY = "YOUR_KEY"
   $env:DJANGO_SECRET_KEY = "change-me"
   $env:DEBUG = "true"
   python manage.py migrate
   python manage.py runserver 0.0.0.0:8000
   ```

## Deployment (Vercel)
- Ensure environment variables set in Vercel dashboard:
  - `GOOGLE_API_KEY`
  - `DJANGO_SECRET_KEY`
  - (optional) `GEMINI_MODEL`
- Deploy root of `extraction_api` folder.

Static files collected automatically not handled in this minimal setup; if you later add templates or admin use `python manage.py collectstatic` and include output.

## Normalization
Post-processing in `extraction/utils.py` guarantees:
- `header.uap` -> digits only (<=3 chars) else null.
- `header.equipe` -> Roman numeral I–X or null.

## Notes
- Reuses existing `extract_data_from_image` from parent project; expects repository root to contain the original extraction scripts.
- Adjust `ALLOWED_HOSTS` or security settings before production hardening.
