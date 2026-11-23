@echo off
cd /d "%~dp0"
echo === Step 1 of 2: building the dashboard data from MySQL (pc2) ===
echo You will be asked for the MySQL password. Nothing is saved.
echo.
python build_receiving_data.py
if errorlevel 1 (
  echo.
  echo The build failed. Read the message above. Nothing was changed on GitHub.
  pause
  exit /b 1
)
echo.
echo === Step 2 of 2: publish ===
set /p PUB=Publish to GitHub now? (Y/N):
if /i "%PUB%"=="Y" call publish.bat
echo.
echo Finished. To check the result locally, double-click open_dashboard.bat
pause
