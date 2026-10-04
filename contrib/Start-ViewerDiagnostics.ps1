# Start a viewer with a traffic meter and per-session logs.
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
$logFile = Join-Path $logDirectory 'vncviewer.log'
$stateFile = Join-Path $logDirectory 'connection-state.log'
$previousTmp = $env:TMP
$previousTemp = $env:TEMP
$process = $null
try {
    if ($Instrumented) {
        $env:TMP = $logDirectory
        $env:TEMP = $logDirectory
        $sourceLog = $logFile
        $viewerArgs = @('-ShowStats', '-ConnectionDiagnostics', '-Log', '*:file:30')
    } else {
        # Stock 1.16.0 ignores TMP and writes file logs here. Its Windows
        # GUI executable also did not produce redirected stderr in testing.
        New-Item -ItemType Directory -Path 'C:\temp' -Force | Out-Null
        $sourceLog = 'C:\temp\vncviewer.log'
        $viewerArgs = @('-Log', '*:file:30,DesktopWindow:file:100,CConn:file:100')
    }
    Write-Host "Session logs: $logDirectory"
    Write-Host 'Connect normally. Keep this launcher running during the session.'
    $started = Get-Date
    $process = Start-Process -FilePath $ViewerPath -ArgumentList $viewerArgs -PassThru
    $sampleDue = Get-Date
    do {
        $exited = $process.WaitForExit(1000)
        if (-not $Instrumented -and (Test-Path -LiteralPath $sourceLog)) {
            $source = Get-Item -LiteralPath $sourceLog
            # Do not copy an older session's log while the connection dialog is open.
            if ($source.LastWriteTime -ge $started) {
                Copy-Item -LiteralPath $sourceLog -Destination $logFile -Force
            }
        }
        if (-not $exited -and (Get-Date) -ge $sampleDue) {
            $process.Refresh()
            $connections = @(netstat -ano -p tcp | Select-String "\s$($process.Id)$" |
                             ForEach-Object {$_.Line.Trim()})
            [ordered]@{
                time = (Get-Date -Format o)
                viewerPid = $process.Id
                responding = $process.Responding
                cpuSeconds = $process.TotalProcessorTime.TotalSeconds
                workingSetBytes = $process.WorkingSet64
                tcpConnections = $connections
            } | ConvertTo-Json -Compress | Add-Content -LiteralPath $stateFile
            $sampleDue = (Get-Date).AddSeconds(5)
        }
    } while (-not $exited)
    Write-Host "Logs saved: $logDirectory"
} finally {
    $env:TMP = $previousTmp
    $env:TEMP = $previousTemp
}
