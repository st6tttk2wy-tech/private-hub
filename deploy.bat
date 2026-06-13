@echo off
echo ========================================
echo   Deploy to Railway
echo ========================================
echo.

cd /d F:\mimo

echo [1/3] Adding files...
git add app.py wsgi.py Procfile requirements.txt .gitignore deploy.bat

echo [2/3] Committing...
set /p msg="Enter commit message (or press Enter for default): "
if "%msg%"=="" set msg=update website
git commit -m "%msg%"

echo [3/3] Pushing to GitHub...
git push origin master

echo.
echo ========================================
echo   Done! Railway will auto rebuild
echo ========================================
echo   https://railway.com/dashboard
echo ========================================
pause
