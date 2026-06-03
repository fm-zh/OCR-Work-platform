@echo off
REM 啟動財報文件智慧辨識（進階版）
cd /d "%~dp0"
python -m streamlit run ocr_app_pro.py --server.port 8503
