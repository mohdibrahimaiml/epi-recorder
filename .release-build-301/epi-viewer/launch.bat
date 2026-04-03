@echo off
REM EPI Viewer Direct Launcher
REM This launches Electron directly with the full path to node.js

SET "PATH=C:\Program Files\nodejs;%PATH%"

REM Reinstall electron to fix the corrupted module
echo Fixing Electron installation...
npm install --save-dev electron@latest --force

echo.
echo Launching EPI Viewer...
npm start

 