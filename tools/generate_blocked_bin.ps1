<#
.SYNOPSIS
  Downloads blocklists and generates blocked.bin for the ESP32 DNS adblocker.

.DESCRIPTION
  Fetches HaGeZi Multi PRO + HostsVN, parses unique domains, deduplicates
  subdomains, hashes with FNV-1a 64-bit, and writes a sorted binary file
  ready to upload to the ESP32.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path "$PSScriptRoot\.."
$FirmwareDir = "$RepoRoot\firmware"
$TmpDir = "$env:TEMP\adblock_gen"

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

Write-Host "Downloading HostsVN..."
curl.exe -sL --max-time 30 "https://raw.githubusercontent.com/bigdargon/hostsVN/master/hosts" -o "$TmpDir\hostsvn.txt"

Write-Host "Downloading HaGeZi Multi PRO..."
curl.exe -sL --max-time 30 "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt" -o "$TmpDir\hagezi_pro.txt"

Write-Host "Generating blocked.bin..."
& "$RepoRoot\.venv\Scripts\python.exe" "$PSScriptRoot\process_blocked.py" "$TmpDir" "$FirmwareDir"

Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
Write-Host "Done. blocked.bin written to $FirmwareDir"
