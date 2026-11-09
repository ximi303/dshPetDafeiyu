<#
.SYNOPSIS
    启动网页 Demo 本地服务器（推荐方式，避开 file:// 的路径与自动播放限制）

.DESCRIPTION
    在**项目根目录**启动 HTTP 服务，这样 demo-preview/index.html 里的
    `../assets/source-webm/...` 能正常映射到 assets 目录。
    启动后自动用默认浏览器打开 http://localhost:<端口>/demo-preview/

.PARAMETER Port
    端口，默认 8123

.EXAMPLE
    .\tools\start-demo.ps1
    .\tools\start-demo.ps1 -Port 9000
#>
param(
    [int]$Port = 8123
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot      # 项目根
Set-Location $root

# 找可用的 Python
$py = $null
foreach ($cand in @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source,
    "$env:USERPROFILE\.platformio\penv\Scripts\python.exe",
    (Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1).Source
)) {
    if ($cand -and (Test-Path $cand)) { $py = $cand; break }
}

if (-not $py) {
    Write-Host "✗ 未找到 Python，无法启动本地服务器" -ForegroundColor Red
    Write-Host "  可直接双击 demo-preview\index.html（file:// 方式）" -ForegroundColor Yellow
    exit 1
}

$url    = "http://localhost:$Port/demo-preview/"
$packs  = (Get-ChildItem 'assets\source-webm' -Recurse -Filter *.webm -ErrorAction SilentlyContinue).Count

Write-Host ""
Write-Host "  肥鱼养成机 · 网页 Demo" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host "  服务根目录  $root"
Write-Host "  访问地址    $url" -ForegroundColor Green
Write-Host "  素材段数    $packs 段" -ForegroundColor $(if ($packs -gt 0) { 'Green' } else { 'Red' })
if ($packs -eq 0) {
    Write-Host "  ⚠ assets\source-webm 为空，页面会以占位模式运行" -ForegroundColor Yellow
}
Write-Host "  停止服务    Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

Start-Process $url
& $py -m http.server $Port
