@echo off
cd /d "%~dp0"
echo === One-time setup: installing the Python packages ===
python -m pip install pandas numpy sqlalchemy pymysql openpyxl
echo.
echo If you saw no red errors above, setup is done.
echo Next: double-click open_dashboard.bat to preview (demo data), then update_dashboard.bat for real data.
pause
