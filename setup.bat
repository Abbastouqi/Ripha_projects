@echo off
echo === SmartAttendance API Setup ===

python -m venv venv
call venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements.txt

if not exist .env (
    copy .env.example .env
    echo.
    echo  IMPORTANT: Edit .env and fill in your SUPABASE_URL and SUPABASE_KEY
    echo  Then run:  start.bat
) else (
    echo .env already exists.
)

echo.
echo Setup complete. Run  start.bat  to launch the API.
pause
