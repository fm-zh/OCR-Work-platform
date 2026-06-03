@echo off
REM 啟動財報文件智慧辨識網頁（OCR Work Platform）
cd /d "%~dp0"
python -m streamlit run ocr_app.py --server.port 8502
