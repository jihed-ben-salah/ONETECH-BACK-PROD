# Extraction API

Minimal Django REST API for document extraction (Rebut, NPT, Kosu, Défauts).

## 1. Run Locally (Python)

Prerequisites:

- Python 3.11+
- Environment variables:
  - GOOGLE_API_KEY (required – Gemini key)

Setup:

```bash
cd extraction_api
python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# Linux/Mac
# source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# (No DB models needed, but migrate to satisfy Django)
python manage.py migrate

# Run
python manage.py runserver
```

Test:

```bash
curl http://127.0.0.1:8000/health/
```

## 2. Run with Docker

Build (from repository root that contains extraction_api/):

```bash
docker build -t extraction-api -f extraction_api/Dockerfile extraction_api
```

Run:

```bash
docker run -p 8000:8000 \
  -e GOOGLE_API_KEY=YOUR_KEY \
  -e DJANGO_SECRET_KEY=change-me \
  --name extraction_api \
  extraction-api
```

Test:

```bash
curl http://localhost:8000/health/
```

Stop & remove:

```bash
docker rm -f extraction_api
```

## 3. Endpoints

### GET /

Returns basic health (same as /health/ if configured).

### GET /health/

Response:

```json
{
  "status": "ok",
  "model": "gemini-2.5-pro"
}
```

### POST /extract/

Multipart form-data:

- document_type: one of Rebut | NPT | Kosu | Défauts | Defauts
- file: image (jpg/png)

cURL example:

```bash
curl -X POST http://localhost:8000/extract/ \
  -F "document_type=Rebut" \
  -F "file=@C:/path/to/image.jpg"
```

Sample success response (shape varies by document_type):

```json
{
  "status": "success",
  "data": {
    "document_type": "Rebut",
    "header": { "equipe": "IV", "date": null, "...": null },
    "items": [
      {
        "reference": "ABC123",
        "quantity": 4,
        "total_scrapped": 2
      }
    ],
    "notes": []
  },
  "remark": "Rebut extraction complete"
}
```

Error responses:

- 400: validation error / missing fields
- 500: internal failure (check GOOGLE_API_KEY)
- 415: wrong content type (must be multipart/form-data)

## 4. Supported document types

| document_type | Purpose                        |
| ------------- | ------------------------------ |
| Rebut         | Scrap declaration form         |
| NPT           | Downtime (Non Productive Time) |
| Kosu          | Productivity tracking          |
| Défauts       | Quality defects form           |

Alias: Defauts (ASCII) maps to Défauts internally.

## 5. Notes

- CORS currently allows all origins.
- Temporary files are stored in system temp directory.
- No persisted database content (SQLite only for Django internals).
