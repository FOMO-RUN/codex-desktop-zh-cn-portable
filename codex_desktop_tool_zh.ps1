$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Root "codex_desktop_zh_cn_windows.py"

function Invoke-CodexZhTool {
    param([string[]]$ArgsList)

    Write-Host ""
    python $Script @ArgsList
    $code = $LASTEXITCODE
    Write-Host ""
    if ($code -ne 0) {
        Write-Host "命令失败，退出码：$code" -ForegroundColor Red
    }
    Read-Host "按 Enter 返回菜单"
}

while ($true) {
    Clear-Host
    Write-Host "Codex Desktop zh-CN 便携中文化工具"
    Write-Host ""
    Write-Host "1. 生成 / 补丁 / 启动中文便携版"
    Write-Host "2. 强制重建中文便携版"
    Write-Host "3. 仅补丁现有便携版菜单"
    Write-Host "4. 创建快捷方式"
    Write-Host "5. 启动现有便携版"
    Write-Host "6. 显示路径和版本"
    Write-Host "7. 完全清理便携版文件"
    Write-Host "8. Dry-run 检查可补丁菜单字符串"
    Write-Host "0. 退出"
    Write-Host ""
    $choice = Read-Host "请选择"

    switch ($choice) {
        "1" { Invoke-CodexZhTool @("--launch") }
        "2" { Invoke-CodexZhTool @("--rebuild", "--launch") }
        "3" { Invoke-CodexZhTool @("--patch-menu") }
        "4" { Invoke-CodexZhTool @("--create-shortcuts") }
        "5" { Invoke-CodexZhTool @("--launch-existing") }
        "6" { Invoke-CodexZhTool @("--show-paths") }
        "7" { Invoke-CodexZhTool @("--full-clean") }
        "8" { Invoke-CodexZhTool @("--dry-run") }
        "0" { break }
        default {
            Write-Host "无效选择。" -ForegroundColor Yellow
            Start-Sleep -Seconds 1
        }
    }
}
