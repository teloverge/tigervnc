# Start a separate viewer session with a traffic meter and persistent logs.
param(
    [string]$ViewerPath = 'D:\Apps\TigerVNC\vncviewer.exe',
    [switch]$Instrumented
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ViewerPath -PathType Leaf)) {
    throw "Viewer executable does not exist: $ViewerPath"
}
$session = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID
$logDirectory = Join-Path $env:LOCALAPPDATA "TigerVNC\diagnostics\$session"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$previousTmp = $env:TMP
$previousTemp = $env:TEMP
try {
    # TigerVNC's file logger writes vncviewer.log under TMP on Windows.
    $env:TMP = $logDirectory
    $env:TEMP = $logDirectory
    if ($Instrumented) {
        $viewerArgs = @('-ShowStats', '-ConnectionDiagnostics', '-Log', '*:file:30')
    } else {
        # Stock 1.16.0 already exposes a graph when DesktopWindow is at debug level.
        $viewerArgs = @('-Log', '*:file:30,DesktopWindow:file:100,CConn:file:100')
    }
    Write-Host "Viewer log: $logDirectory\vncviewer.log"
    Start-Process -FilePath $ViewerPath -ArgumentList $viewerArgs -Wait
} finally {
    $env:TMP = $previousTmp
    $env:TEMP = $previousTemp
}
