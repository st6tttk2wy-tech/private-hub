@echo off
chcp 65001 >nul
echo ========================================
echo   部署到 Railway
echo ========================================
echo.

cd /d F:\mimo

echo [1/3] 添加文件...
git add app.py wsgi.py Procfile requirements.txt .gitignore

echo [2/3] 提交更改...
set /p msg="请输入提交说明（直接回车使用默认说明）: "
if "%msg%"=="" set msg=更新网站
git commit -m "%msg%"

echo [3/3] 推送到GitHub...
git push origin master

echo.
echo ========================================
echo   部署完成！Railway将自动重新构建
echo ========================================
echo   Railway控制台: https://railway.com/dashboard
echo ========================================
pause
