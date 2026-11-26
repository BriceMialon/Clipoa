<#
.SYNOPSIS
  Fabrique une release Windows web (clipoa-<v>-windows-x64.zip + latest.json + install.ps1)
  à héberger sur Cloudflare R2 (option secondaire hors Microsoft Store).
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    [string]$Notes = "",
    [string]$Edition = "public",
    [Parameter(Mandatory=$true)]
    [string]$UpdateUrl,
    [string]$PythonVersion = "3.9",
    [string]$BlenderVersion = "5.3.0"
)

$ErrorActionPreference = "Stop"
$UpdateUrl = $UpdateUrl.TrimEnd("/")
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Dist = Join-Path $Root "dist"
$BuildDir = Join-Path ([System.IO.Path]::GetTempPath()) ("clipoa_winrel_" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
$Src = Join-Path $BuildDir "src"
$Out = Join-Path $BuildDir "out"
New-Item -ItemType Directory -Force -Path $Src, $Out, $Dist | Out-Null

try {
    $tarFile = Join-Path $BuildDir "head.tar"
    git -C $Root archive --format=tar -o $tarFile HEAD
    tar -xf $tarFile -C $Src
    foreach ($rel in @("tests", "docs", "site_public", "backups_multicomptes", "oauth_relay_worker.js", "cli.py", "packaging")) {
        $p = Join-Path $Src $rel
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
    Get-ChildItem -Path $Src -Include "*.command","*.md" -File | Remove-Item -Force

    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) { throw "uv introuvable." }
    $env:UV_PYTHON_PREFERENCE = "only-managed"
    & $uv python install $PythonVersion
    $BuildVenv = Join-Path $BuildDir "venv"
    & $uv venv --python $PythonVersion $BuildVenv
    $PyExe = Join-Path $BuildVenv "Scripts\python.exe"
    & $uv pip install --python $PyExe "nuitka>=2.5,<3" ordered-set zstandard
    & $uv pip install --python $PyExe -r (Join-Path $Src "requirements.txt")
    & $uv pip compile (Join-Path $Src "requirements.txt") --generate-hashes --python-version $PythonVersion --python-platform x86_64-pc-windows-msvc -o (Join-Path $Src "requirements.lock")

    Push-Location $Src
    try {
        New-Item -ItemType File -Force -Path "core\__init__.py", "agents\__init__.py" | Out-Null
        $nuitkaBase = @("-m", "nuitka", "--module", "--no-pyi-file", "--remove-output", "--output-dir=$Out", "--assume-yes-for-downloads")
        & $PyExe @nuitkaBase core --include-package=core --nofollow-import-to=core.blender_kit,core.tts_worker,core.cine_engine
        & $PyExe @nuitkaBase agents --include-package=agents
        Move-Item "app.py" "clipoa_app.py"
        & $PyExe @nuitkaBase clipoa_app.py
        Get-ChildItem -Path "core" -Filter "*.py" -File | Remove-Item -Force
        Get-ChildItem -Path "agents" -Filter "*.py" -File | Remove-Item -Force
        Remove-Item -Force "clipoa_app.py"
        Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
        Copy-Item (Join-Path $Out "*.pyd") -Destination $Src
    } finally {
        Pop-Location
    }

    @"
import os, threading, clipoa_app
if __name__ == "__main__":
    try:
        from core import tools_setup
        threading.Thread(target=tools_setup.auto_setup_on_launch, daemon=True).start()
    except Exception as e:
        print(f"Outils : {e}")
    clipoa_app.run_app(port=int(os.getenv("CLIPOA_PORT", "8080")))
"@ | Set-Content -Encoding UTF8 -Path (Join-Path $Src "app.py")

    Set-Content -Encoding UTF8 -Path (Join-Path $Src "edition") -Value $Edition
    @{
        version = $Version
        update_url = $UpdateUrl
        platform = "windows-x64"
        edition = $Edition
        commit = (git -C $Root rev-parse --short HEAD)
        built_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path (Join-Path $Src "release.json")

    $blMajor = ($BlenderVersion.Split(".")[0..1]) -join "."
    $blDir = "https://download.blender.org/release/Blender$blMajor"
    $blFile = "blender-$BlenderVersion-windows-x64.zip"
    $shaLines = (Invoke-WebRequest -Uri "$blDir/blender-$BlenderVersion.sha256").Content -split "`n"
    $blSha = ($shaLines | Where-Object { $_ -match "\s+\*?$([regex]::Escape($blFile))$" } | Select-Object -First 1).Trim().Split()[0]
    $whRev = (Invoke-RestMethod -Uri "https://huggingface.co/api/models/Systran/faster-whisper-base/revision/main").sha

    $PkgName = "clipoa-$Version-windows-x64.zip"
    $PkgPath = Join-Path $Dist $PkgName
    if (Test-Path $PkgPath) { Remove-Item -Force $PkgPath }
    Compress-Archive -Path (Join-Path $Src "*") -DestinationPath $PkgPath
    $PkgSha = (Get-FileHash -Algorithm SHA256 -Path $PkgPath).Hash.ToLowerInvariant()
    $PkgSize = (Get-Item $PkgPath).Length

    @{
        version = $Version
        platform = "windows-x64"
        url = $PkgName
        sha256 = $PkgSha
        size = $PkgSize
        notes = $Notes
        blender_version = $BlenderVersion
        blender_url = "$blDir/$blFile"
        blender_sha256 = $blSha
        whisper_revision = $whRev
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path (Join-Path $Dist "latest-windows.json")

    (Get-Content -Raw -Encoding UTF8 (Join-Path $Root "packaging\windows\install.ps1")).Replace("__CLIPOA_UPDATE_URL__", $UpdateUrl) |
        Set-Content -Encoding UTF8 -Path (Join-Path $Dist "install.ps1")

    Write-Host "✓ Release web Windows prête : $PkgPath" -ForegroundColor Green
} finally {
    Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
}
