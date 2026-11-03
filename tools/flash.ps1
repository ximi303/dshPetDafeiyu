# ============================================================
# ESP32 桌宠 —— 一键烧录脚本
#
# 解决的核心问题：
#   Windows 控制台默认代码页 936(GBK)，而 firmware/data/packs/ 下是中文目录名。
#   PlatformIO 打包 LittleFS 时要把每个文件名打到控制台，Python 用 GBK 编码
#   遇到生僻字就抛 UnicodeEncodeError，进程直接死掉 —— 表现为「卡住 5 分钟无反应」。
#   把 PYTHONIOENCODING 设为 utf-8 即可正常输出中文。
#
# 用法（在项目根目录或任意位置）：
#   .\tools\flash.ps1              # 烧固件 + 素材
#   .\tools\flash.ps1 -Target fw   # 只烧固件
#   .\tools\flash.ps1 -Target fs   # 只烧素材
#   .\tools\flash.ps1 -Port COM16  # 指定端口（默认 COM16）
# ============================================================

param(
    [ValidateSet('fw', 'fs', 'all')]
    [string]$Target = 'all',

    [string]$Port = 'COM16'
)

$ErrorActionPreference = 'Stop'

# ---- 关键：UTF-8，绕开 GBK 编码崩溃 ----
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
chcp 65001 | Out-Null
# PowerShell 自己的 Write-Host 也要切到 UTF-8，否则中文会显示成乱码
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$root = Split-Path -Parent $PSScriptRoot
$pio = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\pio.exe'

if (-not (Test-Path $pio)) {
    Write-Host "找不到 PlatformIO: $pio" -ForegroundColor Red
    Write-Host "请先安装：pip install platformio" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $root 'firmware\platformio.ini'))) {
    Write-Host "当前目录不像项目根：$root" -ForegroundColor Red
    exit 1
}

Write-Host "项目根: $root" -ForegroundColor DarkGray
Write-Host "端口  : $Port" -ForegroundColor DarkGray

Push-Location $root
$failed = $false

try {
    if ($Target -eq 'fw' -or $Target -eq 'all') {
        Write-Host "`n=== [1/2] 编译并烧录固件 ===" -ForegroundColor Cyan
        & $pio run -d firmware -t upload --upload-port $Port
        if ($LASTEXITCODE -ne 0) { throw "固件烧录失败" }
    }

    if ($Target -eq 'fs' -or $Target -eq 'all') {
        Write-Host "`n=== [2/2] 烧录素材分区（约 12MB，需 60~90 秒）===" -ForegroundColor Cyan
        Write-Host "提示：这一步没有逐行进度是正常的，请耐心等 SUCCESS" -ForegroundColor DarkGray
        & $pio run -d firmware -t uploadfs --upload-port $Port
        if ($LASTEXITCODE -ne 0) { throw "素材烧录失败" }
    }
}
catch {
    Write-Host "`n[失败] $_" -ForegroundColor Red
    $failed = $true
}
finally {
    Pop-Location
}

if ($failed) {
    Write-Host "`n排查建议：" -ForegroundColor Yellow
    Write-Host "  1. 确认 USB 线插在板子的 COM 口（不是 USB 口）"
    Write-Host "  2. 确认端口号：pio device list"
    Write-Host "  3. 若提示端口被占用，先关掉串口监视器"
    exit 1
}

Write-Host "`n[完成] 全部烧录成功" -ForegroundColor Green
