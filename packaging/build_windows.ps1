# 在 Windows 上构建 mcl.exe 和安装包
$ErrorActionPreference = "Stop"
# 让原生命令（pyinstaller / ISCC）失败时也终止脚本
$PSNativeCommandUseErrorActionPreference = $true
Set-Location (Join-Path $PSScriptRoot "..")

$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }

# 版本号从包里读，Inno Setup 用同一个
$versionLine = Select-String -Path "mcl/__init__.py" -Pattern '__version__ = "([^"]+)"'
$env:MCL_VERSION = $versionLine.Matches[0].Groups[1].Value
Write-Host "mcl $env:MCL_VERSION"
& $python -m pip install --upgrade pip
& $python -m pip install ".[cli]" pyinstaller

if (Test-Path "gui/dist") {
    Remove-Item -Recurse -Force "mcl/webui_dist" -ErrorAction SilentlyContinue
    Copy-Item -Recurse "gui/dist" "mcl/webui_dist"
}

& $python -m PyInstaller packaging/windows/mcl.spec --noconfirm `
    --distpath dist --workpath build/pyinstaller

$iscc = $env:ISCC
if (-not $iscc) {
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) {
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install innosetup -y --no-progress
        $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    } else {
        throw "找不到 Inno Setup 的 ISCC.exe，请安装 Inno Setup 6 或设置环境变量 ISCC"
    }
}
& $iscc packaging/windows/installer.iss
Write-Host "完成：dist\mcl-setup.exe 和 dist\mcl.exe"
