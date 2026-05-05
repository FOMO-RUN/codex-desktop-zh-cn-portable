$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Root "codex_desktop_zh_cn_windows.py"

function Find-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Exe = $python.Source
            Args = @()
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Exe = $py.Source
            Args = @("-3")
        }
    }

    return $null
}

$PythonCommand = Find-Python
if (-not $PythonCommand) {
    Write-Host "Python 3 was not found. Please install Python 3 or add it to PATH." -ForegroundColor Red
    Write-Host "Press Enter to exit."
    Read-Host | Out-Null
    exit 1
}

& $PythonCommand.Exe @($PythonCommand.Args) $Script --menu
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host ""
    Write-Host "Tool exited with code: $code" -ForegroundColor Red
    Write-Host "Press Enter to exit."
    Read-Host | Out-Null
}

exit $code
