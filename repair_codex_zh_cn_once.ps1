$ErrorActionPreference = 'Stop'

$patcher = 'D:\Temp\codex-desktop-zh-cn-portable\codex_desktop_zh_cn_windows.py'
$portableRoot = 'C:\Users\SiuaLee\AppData\Local\CodexZhCN\Codex'
$portableExe = Join-Path $portableRoot 'Codex.exe'
$logFile = 'C:\Users\SiuaLee\AppData\Local\CodexZhCN\repair-once.log'

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -LiteralPath $logFile -Value "[$ts] $Message" -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null
Set-Content -LiteralPath $logFile -Value '' -Encoding UTF8
Write-Log 'repair worker started'

for($i = 0; $i -lt 600; $i++) {
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -like 'C:\Users\SiuaLee\AppData\Local\CodexZhCN\Codex*'
    }
    if(-not $running) {
        Write-Log 'portable codex is fully closed, applying patch'
        break
    }
    Start-Sleep -Seconds 1
}

$stillRunning = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like 'C:\Users\SiuaLee\AppData\Local\CodexZhCN\Codex*'
}

if($stillRunning) {
    Write-Log 'timeout waiting for portable codex to exit'
    exit 2
}

& python $patcher --patch-menu *>> $logFile
if($LASTEXITCODE -ne 0) {
    Write-Log "patch failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Log 'patch applied, launching portable codex'
Start-Process -FilePath $portableExe -WorkingDirectory $portableRoot -ArgumentList '--lang=zh-CN'
Write-Log 'repair worker finished'
