@echo off
cd /d "%~dp0"
echo Dashboard is running at http://localhost:8000/index.html
echo Keep this window open while you look at it. Close it (or press Ctrl+C) to stop.
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8000/index.html"
python -m http.server 8000
