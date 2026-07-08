@echo off
title DNS AdBlocker - OFF

:: Self-elevate to Admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Reverting DNS to automatic (DHCP)...
netsh interface ip set dns name="Wi-Fi" source=dhcp
ipconfig /flushdns >nul
echo Done! DNS is back to default
timeout /t 2 >nul
