# ============================================================
#  ADHIKAAR - LIVE launcher (stable domain: https://adhikaar.services)
#  Right-click -> "Run with PowerShell"
#    (or:  powershell -ExecutionPolicy Bypass -File start_live.ps1)
#
#  Prereqs (ONE-TIME, see setup notes):
#    1. Domain adhikaar.services added to Cloudflare, GoDaddy nameservers -> Cloudflare.
#    2. cloudflared tunnel login
#    3. cloudflared tunnel create adhikaar      (then fill cf_config.yml)
#    4. cloudflared tunnel route dns adhikaar adhikaar.services
#       cloudflared tunnel route dns adhikaar www.adhikaar.services
#  After that, just run THIS script to go live on https://adhikaar.services
# ============================================================
$backend = "D:\Adhikaar\backend"
$cfg     = "$backend\cf_config.yml"
Set-Location $backend
Write-Host ""
Write-Host "================ ADHIKAAR LIVE (adhikaar.services) ================" -ForegroundColor Green

if ((Get-Content $cfg -Raw) -match "PASTE-TUNNEL-UUID-HERE") {
    Write-Host "  cf_config.yml still has placeholders - finish the one-time setup first" -ForegroundColor Red
    Write-Host "  (cloudflared tunnel create adhikaar, then paste the UUID + creds path into cf_config.yml)" -ForegroundColor Red
    Read-Host "Enter to exit"; exit 1
}

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

# --- 2) Run the NAMED Cloudflare tunnel (stable domain) -------
Write-Host "[2/2] Starting the named Cloudflare tunnel -> https://adhikaar.services ..." -ForegroundColor Cyan
Start-Process "$backend\cloudflared.exe" -ArgumentList "tunnel","--config","$cfg","run","adhikaar" `
    -RedirectStandardOutput "$backend\_live_tunnel.log" -RedirectStandardError "$backend\_live_tunnel_err.log" -WindowStyle Minimized
Start-Sleep 6

Write-Host ""
Write-Host "=================== ADHIKAAR IS LIVE ===================" -ForegroundColor Green
Write-Host "  On this laptop : " -NoNewline; Write-Host "http://localhost:8010/Scanner.dc.html" -ForegroundColor White
Write-Host "  Public (stable): " -NoNewline; Write-Host "https://adhikaar.services/Scanner.dc.html" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "  (If the public URL 502s for a minute, DNS is still propagating - wait and refresh.)" -ForegroundColor DarkYellow
Write-Host ""
Read-Host "Press Enter to STOP (closes the engine + tunnel)"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*uvicorn*8010*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Stopped." -ForegroundColor Green
