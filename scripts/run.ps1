$env:PYTHONUNBUFFERED="1"
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
