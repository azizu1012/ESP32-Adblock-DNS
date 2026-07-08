$port = new-object System.IO.Ports.SerialPort "COM3",115200,None,8,One
$port.ReadTimeout = 1000
$port.Open()
Start-Sleep -Seconds 3

# Read initial serial buffer
$serial = ""
$tries = 0
while($tries -lt 10) {
    try { $serial += $port.ReadExisting() + "`n"; $tries=0 } catch { $tries++ }
    Start-Sleep -Milliseconds 200
}

Write-Host "=== INITIAL ==="
Write-Host $serial

# Start curl upload as a job
$curlJob = Start-Job -ScriptBlock {
    param($url, $file)
    curl -v --data-binary "@$file" $url --connect-timeout 30 --max-time 600 -H "Content-Type: application/octet-stream" 2>&1
} -ArgumentList "http://192.168.1.234/api/upload", "D:\AI_Projects\ESP32-Side-PRJ\firmware\blocked.bin"

# Monitor serial while curl runs
$serial2 = ""
$done = $false
$timeout = [datetime]::Now.AddSeconds(600)
while(!$done -and [datetime]::Now -lt $timeout) {
    try {
        $line = $port.ReadLine()
        $serial2 += $line + "`n"
        Write-Host $line
    } catch {
        $done = ($curlJob.State -ne "Running")
    }
}

# Wait for curl job
$curlResult = $curlJob | Wait-Job -Timeout 60 | Receive-Job
$curlJob | Remove-Job -Force

# Read any remaining serial
Start-Sleep -Seconds 2
try { $serial2 += $port.ReadExisting() } catch {}

$port.Close()

Write-Host "`n=== CURL OUTPUT ==="
Write-Host $curlResult
Write-Host "`n=== SERIAL DURING UPLOAD ==="
Write-Host $serial2
