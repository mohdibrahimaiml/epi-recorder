@echo off
REM Complete clean reinstall of EPI Viewer dependencies
SET "PATH=C:\Program Files\nodejs;%PATH%"

echo Cleaning old installation...
if exist node_modules rmdir /s /q node_modules
if exist package-lock.json del package-lock.json

echo.
echo Installing fresh dependencies...
npm cache clean --force
npm install

echo.
echo Installation complete!
pause

 