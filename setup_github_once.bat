@echo off
cd /d "%~dp0"
echo === One-time GitHub setup ===
echo 1) Create an empty repository on github.com (no README). Copy its address, for example https://github.com/yourname/shwapno-receiving.git
echo 2) Paste the address below.
echo.
set /p REPO=Repository address:
git init
git branch -M main
git remote add origin %REPO%
git add .
git commit -m "First version of the receiving dashboard"
git push -u origin main
echo.
echo Last step, on github.com: open the repository, Settings, Pages, choose Deploy from a branch, branch main, folder (root), Save.
echo Your dashboard address will be https://YOURNAME.github.io/REPONAME/
pause
