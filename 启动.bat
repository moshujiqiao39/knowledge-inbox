@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 start.py
  exit /b %errorlevel%
)
where python >nul 2>&1
if %errorlevel%==0 (
  python start.py
  exit /b %errorlevel%
)
echo Install Python 3.10 or newer, and tick "Add python.exe to PATH".
echo https://www.python.org/downloads/
pause
exit /b 1
