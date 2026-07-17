@echo off
title CipherChat Git Save

echo ================================
echo      CipherChat Git Helper
echo ================================
echo.

git status

echo.
set /p msg=Enter commit message (leave blank for auto): 

if "%msg%"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set d=%%c-%%a-%%b
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set t=%%a-%%b
    set msg=chore: auto save %d% %t%
)

echo.
echo Adding files...
git add .

echo.
echo Committing...
git commit -m "%msg%"

echo.
choice /M "Push to GitHub"

if errorlevel 2 goto end

git push origin main

:end
echo.
echo Done!
pause