# Script tu dong cap nhat IP WAN cua ESP32 vao DNS Card Mang Windows

# Tu dong yeu cau quyen Administrator neu chua co
$myWindowsID = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$myWindowsPrincipal = New-Object System.Security.Principal.WindowsPrincipal($myWindowsID)
$adminRole = [System.Security.Principal.WindowsBuiltInRole]::Administrator

if (-not $myWindowsPrincipal.IsInRole($adminRole)) {
    $newProcess = New-Object System.Diagnostics.ProcessStartInfo "PowerShell"
    # Re-run current script with Admin privileges and Bypass policy
    $newProcess.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $newProcess.Verb = "runas"
    [System.Diagnostics.Process]::Start($newProcess)
    Exit
}

$domain = "esp32adblocker.duckdns.org"

Write-Host "Dang truy van IP moi nhat tu domain: $domain..."
try {
    # Lay danh sach dia chi IP cua ten mien
    $ips = [System.Net.Dns]::GetHostAddresses($domain)
    # Loc ra dia chi IPv4
    $ipv4 = $ips | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
    
    if ($ipv4) {
        $dns_ip = $ipv4.IPAddressToString
        Write-Host "Da tim thay IP WAN moi nhat: $dns_ip"
        
        # Lay card mang dang ket noi Internet (IPv4 active)
        $adapter = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | Select-Object -First 1
        
        if ($adapter) {
            Write-Host "Dang gan IP DNS $dns_ip vao Card mang: $($adapter.Name)..."
            # Thiet lap IP DNS cho card mang
            Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ServerAddresses $dns_ip
            Write-Host "Cap nhat DNS thanh cong!" -ForegroundColor Green
        } else {
            Write-Warning "Khong tim thay card mang dang hoat dong!"
        }
    } else {
        Write-Warning "Khong lay duoc IPv4 tu ten mien $domain!"
    }
} catch {
    Write-Error "Loi trong qua trinh phan giai hoac cap nhat DNS: $_"
}
