@echo off
call venv\Scripts\activate.bat

:loop
echo [supervisor] Starting server...
python run.py
echo [supervisor] Server stopped (exit code %ERRORLEVEL%). Restarting in 3 seconds...
timeout /t 3 /nobreak > nul
goto loop
