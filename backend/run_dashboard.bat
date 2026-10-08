@echo off
echo ========================================================
echo   Launching Project Quant - Institutional Terminal
echo ========================================================
call .\venv\Scripts\activate.bat
streamlit run dashboard.py
