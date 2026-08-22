param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$RdcPath,

    [string]$RenderDocExe = "C:\Program Files\RenderDoc\qrenderdoc.exe",

    [int]$WaitSeconds = 60
)

# Launch RenderDoc with a given .rdc, wait for the MCP bridge to answer.
# The extension must be installed and AlwaysLoad_Extensions enabled.

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RdcPath)) {
    Write-Error "Capture not found: $RdcPath"
    exit 1
}
if (-not (Test-Path -LiteralPath $RenderDocExe)) {
    Write-Error "qrenderdoc.exe not found: $RenderDocExe (pass -RenderDocExe)"
    exit 1
}

$full = (Resolve-Path -LiteralPath $RdcPath).Path

Write-Host "Launching RenderDoc: $RenderDocExe"
Write-Host "Capture: $full"

# Start RenderDoc detached. RenderDoc opens the file on startup.
Start-Process -FilePath $RenderDocExe -ArgumentList ('"{0}"' -f $full)

# Poll the bridge until it answers or we time out.
$py = "py"
$ping = Join-Path $PSScriptRoot "ping_bridge.py"
$deadline = (Get-Date).AddSeconds($WaitSeconds)

Write-Host "Waiting for MCP bridge (up to ${WaitSeconds}s)..."
while ($true) {
    & $py -3.13 $ping 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 2) {
        break
    }
    if ((Get-Date) -gt $deadline) {
        Write-Error "Timed out waiting for the MCP bridge. Check Tools > Manage Extensions > RenderDoc MCP Bridge is enabled."
        exit 1
    }
    Start-Sleep -Milliseconds 1000
}

Write-Host "Bridge is up. Final status:"
& $py -3.13 $ping
exit $LASTEXITCODE
