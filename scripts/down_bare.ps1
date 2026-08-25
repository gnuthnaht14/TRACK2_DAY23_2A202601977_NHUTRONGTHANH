$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$pidFiles = @(
    (Join-Path $ProjectRoot "run/region-a.pid"),
    (Join-Path $ProjectRoot "run/region-b.pid"),
    (Join-Path $ProjectRoot "run/edge.pid")
)

foreach ($f in $pidFiles) {
    if (Test-Path $f) {
        $pid = (Get-Content $f -Raw).Trim()
        if ($pid -and $pid -match '^\d+$') {
            # SIGCONT then SIGKILL equivalent
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -Path $f -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "all stopped"
