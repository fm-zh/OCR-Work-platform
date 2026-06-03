@echo off
REM 啟動 OCR-Work-platform 後端 API（FastAPI / uvicorn）
cd /d "%~dp0"
python -m uvicorn app.main:app --port 8000
