@echo off
title DNS AdBlocker - ON

:: Self-elevate to Admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Setting DNS to ESP32 AdBlocker (192.168.1.234)...
netsh interface ip set dns name="Wi-Fi" static 192.168.1.234
ipconfig /flushdns >nul
echo Done! DNS is now 192.168.1.234
timeout /t 2 >nul
