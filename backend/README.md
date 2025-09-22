# Backend - Water Quality File Upload & Extraction

## Setup

```bash
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1  # Windows PowerShell
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API
- POST `/api/upload` (multipart form-data, field `file`)

## Notes
- Stores uploads under `backend/storage/uploads`.
- Parses CSV/Excel via pandas; PDFs via pdfminer simple heuristics.
- Persists samples and metal concentrations in SQLite at `backend/storage/database.db` (auto-created).
