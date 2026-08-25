# make up-bare: 2 "region" + edge chay truc tiep bang uvicorn, KHONG can docker daemon.
# Dung khi Docker Desktop chua co/chua chay, va la duong cham diem cua --mock.

$ErrorActionPreference = "Stop"
# Dua tren vi tri script: scripts/up_bare.ps1 -> project root
$ProjectRoot = (Get-Item $MyInvocation.MyCommand.Path).Directory.Parent.FullName
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ReqTxt = Join-Path $ProjectRoot "requirements.txt"

# Tao .venv neu chua co
if (-not (Test-Path $VenvPython)) {
    Write-Host "Tao virtual environment (.venv)..."
    Set-Location $ProjectRoot
    uv venv --python 3.12
    uv pip install -r $ReqTxt
}

function Start-Region {
    param([string]$Region, [int]$Port)

    $pidFile = Join-Path $ProjectRoot "run/region-$Region.pid"

    $env:REGION = $Region
    $env:STATE_DIR = "$ProjectRoot/state/region-$Region"
    $env:WARMUP_SECONDS = if ($env:WARMUP_SECONDS) { $env:WARMUP_SECONDS } else { "6" }

    $proc = Start-Process -FilePath $VenvPython -ArgumentList "-m","uvicorn","serving.app:app","--host","127.0.0.1","--port",$Port,"--log-level","warning" `
        -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow
    $proc.Id | Out-File -FilePath $pidFile -Encoding utf8
    Write-Host "region-$Region pid=$($proc.Id) port=$Port"
}

function Start-Edge {
    $pidFile = Join-Path $ProjectRoot "run/edge.pid"

    $env:EDGE_TTL_SECONDS = if ($env:EDGE_TTL_SECONDS) { $env:EDGE_TTL_SECONDS } else { "5" }

    $proc = Start-Process -FilePath $VenvPython -ArgumentList "-m","uvicorn","edge.proxy:app","--host","127.0.0.1","--port","8080","--log-level","warning" `
        -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow
    $proc.Id | Out-File -FilePath $pidFile -Encoding utf8
    Write-Host "edge pid=$($proc.Id) port=8080"
}

# Khoi tao thu muc
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "run") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "reports") | Out-Null
"" | Out-File -FilePath (Join-Path $ProjectRoot "run/region-a.pid") -Encoding utf8
"" | Out-File -FilePath (Join-Path $ProjectRoot "run/region-b.pid") -Encoding utf8
"" | Out-File -FilePath (Join-Path $ProjectRoot "run/edge.pid") -Encoding utf8

Start-Region -Region "a" -Port 8001
Start-Region -Region "b" -Port 8002
Start-Edge

Write-Host "cho service len (toi da 10s)..."
$allUp = $true
$services = @(
    @{ Name = "region-a"; Port = 8001; Path = "/healthz" },
    @{ Name = "region-b"; Port = 8002; Path = "/healthz" },
    @{ Name = "edge";     Port = 8080; Path = "/edge/state" }
)

foreach ($svc in $services) {
    $up = $false
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$($svc.Port)$($svc.Path)" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) { $up = $true; break }
        } catch {
            # retry
        }
        Start-Sleep -Seconds 1
    }
    if ($up) {
        Write-Host "  $($svc.Name) (port $($svc.Port)): UP"
    } else {
        Write-Host "  $($svc.Name) (port $($svc.Port)): KHONG PHAN HOI -- xem run/$($svc.Name).log (co the cong da bi chiem)"
        $allUp = $false
    }
}

if (-not $allUp) {
    Write-Host "MOT SO SERVICE CHUA LEN -- doc log truoc khi chay drill"
    exit 1
}

$stateResp = Invoke-WebRequest -Uri "http://localhost:8080/edge/state" -UseBasicParsing -ErrorAction SilentlyContinue
Write-Host $stateResp.Content
