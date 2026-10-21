@echo off
setlocal
cd /d "%~dp0"
set EXE=%LOCALAPPDATA%\Programs\NightOwl\NightOwl.exe
if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)
python -c "import webview" 1>nul 2>nul
if errorlevel 1 python -m pip install -r requirements.txt
if not exist "dist\index.html" (
  echo Build the NightOwl window first: npm install ^&^& npm run build
  pause
  exit /b 1
)
python -u -m bridge
if errorlevel 1 pause
