# ============================================================
#  ADHIKAAR - Demo Launcher
#  Right-click -> "Run with PowerShell"   (or:  powershell -ExecutionPolicy Bypass -File start_demo.ps1)
#  Brings up the DPDP engine on :8010 and a public Cloudflare URL.
#  Runs on port 8010 so it never clashes with the NCSA server on :8000.
# ============================================================
$backend = "D:\Adhikaar\backend"
Set-Location $backend
Write-Host ""
Write-Host "================ ADHIKAAR DEMO LAUNCHER ================" -ForegroundColor Green

# --- 1) Start the DPDP engine ---------------------------------
Write-Host "[1/2] Starting the DPDP engine (http://localhost:8010) ..." -ForegroundColor Cyan
Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8010" -WindowStyle Minimized
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try { if ((Invoke-WebRequest "http://127.0.0.1:8010/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $ready = $true; break } } catch {}
    Start-Sleep 2
}
if (-not $ready) { Write-Host "  Engine did not start - check the minimized python window." -ForegroundColor Red; Read-Host "Enter to exit"; exit 1 }
Write-Host "      engine ready (47 DPDP checks loaded)." -ForegroundColor Green

# --- 2) Open a public URL via Cloudflare ----------------------
Write-Host "[2/2] Opening a public URL via Cloudflare tunnel ..." -ForegroundColor Cyan
if (Test-Path "$backend\_tunnel.log") { Remove-Item "$backend\_tunnel.log" -Force }
Start-Process "$backend\cloudflared.exe" -ArgumentList "tunnel","--url","http://127.0.0.1:8010" `
    -RedirectStandardOutput "$backend\_tunnel.log" -RedirectStandardError "$backend\_tunnel_err.log" -WindowStyle Minimized
$pub = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 2
    foreach ($f in @("$backend\_tunnel.log","$backend\_tunnel_err.log")) {
        if (Test-Path $f) {
            $m = Select-String -Path $f -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $pub = $m.Matches[0].Value; break }
        }
    }
    if ($pub) { break }
}

Write-Host ""
Write-Host "=================== ADHIKAAR IS LIVE ===================" -ForegroundColor Green
Write-Host "  On this laptop : " -NoNewline; Write-Host "http://localhost:8010/Scanner.dc.html" -ForegroundColor White
if ($pub) { Write-Host "  Public (share) : " -NoNewline; Write-Host "$pub/Scanner.dc.html" -ForegroundColor Yellow }
else      { Write-Host "  Public URL not detected yet - open _tunnel.log or the cloudflared window." -ForegroundColor Red }
Write-Host "=======================================================" -ForegroundColor Green
Write-Host ""
Write-Host "NOTE: the public URL is NEW every launch. Share the one shown above." -ForegroundColor DarkYellow
Write-Host "Keep this window open. Pre-cache targets in another terminal with:" -ForegroundColor Gray
Write-Host "  cd $backend ; python adhikaar_precache.py http://localhost:8010 https://site1 https://site2" -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to STOP the demo (closes the engine + tunnel)"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*uvicorn*8010*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Stopped." -ForegroundColor Green
