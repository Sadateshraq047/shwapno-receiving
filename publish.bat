@echo off
cd /d "%~dp0"
git add index.html data
git commit -m "Update receiving data %date% %time%"
git push
if errorlevel 1 (
  echo.
  echo Publishing failed. If this is the first time, run setup_github_once.bat first.
) else (
  echo.
  echo Published. The website updates within a minute or two.
)
