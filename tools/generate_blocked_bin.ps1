$ErrorActionPreference = "Stop"
$tmpDir = "$env:TEMP\adblock_gen"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

Write-Host "Downloading HostsVN..."
curl.exe -sL --max-time 30 "https://raw.githubusercontent.com/bigdargon/hostsVN/master/hosts" -o "$tmpDir\hostsvn.txt"

Write-Host "Downloading HaGeZi Multi PRO..."
curl.exe -sL --max-time 30 "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt" -o "$tmpDir\hagezi_pro.txt"

Write-Host "Generating blocked.bin..."
& "D:\AI_Projects\ESP32-Side-PRJ\.venv\Scripts\python.exe" "D:\AI_Projects\ESP32-Side-PRJ\tools\process_blocked.py" "$tmpDir"

Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
Read-Host "Press Enter to exit"
