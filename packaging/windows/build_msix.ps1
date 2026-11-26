<#
.SYNOPSIS
  Construit le paquet Microsoft Store (.msix) de ClipRoll pour Windows x64.

.DESCRIPTION
  - Copie uniquement les fichiers commités (git archive HEAD) : jamais storage/ ni les clés.
  - Compile core/, agents/ et app.py en modules natifs (.pyd) avec Nuitka, plus ClipRoll.exe (petit lanceur sans console).
  - Embarque un CPython complet + les dépendances telles quelles dans python\ (pas de recompilation Nuitka).
  - Exclut volontairement `imageio-ffmpeg` du paquet MSIX (FFmpeg et Blender sont téléchargés
    depuis leurs sources officielles avec validation dans l'assistant au premier lancement).
  - Génère les icônes MSIX requises et emballe avec makeappx.exe.
  - Avec -SelfSign : signe avec un certificat local d'essai pour tester sur une VM Windows.
    Pour le Microsoft Store : uploader le .msix NON signé (le Store signe gratuitement).

.EXAMPLE
  .\packaging\windows\build_msix.ps1 -Version 0.1.0
  .\packaging\windows\build_msix.ps1 -Version 0.1.0 -SelfSign
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$Version,
    [string]$Edition = "public",
    [string]$IdentityName = "BriceMialon.Clipoa",
    [string]$Publisher = "CN=BriceMialon",
    [string]$PublisherDisplayName = "Brice Mialon",
    [string]$PythonVersion = "3.9",
    [switch]$SelfSign
)

$ErrorActionPreference = "Stop"

# MSIX exige un numéro de version à 4 segments (X.Y.Z.0)
if ($Version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') {
    throw "Version invalide (attendu X.Y.Z ou X.Y.Z.W) : $Version"
}
$MsixVersion = if ($Version -match '^\d+\.\d+\.\d+$') { "$Version.0" } else { $Version }

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Dist = Join-Path $Root "dist"
$BuildDir = Join-Path ([System.IO.Path]::GetTempPath()) ("clipoa_msix_" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
$Src = Join-Path $BuildDir "src"
$Stage = Join-Path $BuildDir "stage"
$Out = Join-Path $BuildDir "out"

New-Item -ItemType Directory -Force -Path $Src, $Stage, $Out, $Dist | Out-Null

try {
    Write-Host "▸ Copie du code commité ($(git -C $Root rev-parse --short HEAD))" -ForegroundColor Magenta
    $tarFile = Join-Path $BuildDir "head.tar"
    git -C $Root archive --format=tar -o $tarFile HEAD
    tar -xf $tarFile -C $Src

    # Retire tout ce qui ne doit pas aller dans le paquet public
    foreach ($rel in @("tests", "docs", "site_public", "backups_multicomptes", "oauth_relay_worker.js", "cli.py", "packaging")) {
        $p = Join-Path $Src $rel
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
    Get-ChildItem -Path $Src -Include "*.command","*.md" -File | Remove-Item -Force

    # Retire imageio-ffmpeg des dépendances MSIX (pas de binaire FFmpeg GPL dans le paquet)
    $reqIn = Join-Path $Src "requirements.txt"
    $reqMsix = Join-Path $BuildDir "requirements-msix.txt"
    Get-Content $reqIn | Where-Object { $_ -notmatch '^\s*imageio-ffmpeg\b' } | Set-Content -Encoding UTF8 $reqMsix

    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) { throw "uv introuvable. Installe uv (https://docs.astral.sh/uv/)." }

    Write-Host "▸ Environnement Python $PythonVersion + Nuitka" -ForegroundColor Magenta
    $env:UV_PYTHON_PREFERENCE = "only-managed"
    & $uv python install $PythonVersion
    $BuildVenv = Join-Path $BuildDir "venv"
    & $uv venv --python $PythonVersion $BuildVenv
    $PyExe = Join-Path $BuildVenv "Scripts\python.exe"

    & $uv pip install --python $PyExe "nuitka>=2.5,<3" ordered-set zstandard
    & $uv pip install --python $PyExe -r $reqMsix

    Write-Host "▸ Compilation Nuitka (core/, agents/, clipoa_app)" -ForegroundColor Magenta
    Push-Location $Src
    try {
        New-Item -ItemType File -Force -Path "core\__init__.py", "agents\__init__.py" | Out-Null
        $nuitkaBase = @("-m", "nuitka", "--module", "--no-pyi-file", "--remove-output", "--output-dir=$Out", "--assume-yes-for-downloads")
        & $PyExe @nuitkaBase core --include-package=core --nofollow-import-to=core.blender_kit,core.tts_worker,core.cine_engine
        & $PyExe @nuitkaBase agents --include-package=agents
        Move-Item "app.py" "clipoa_app.py"
        & $PyExe @nuitkaBase clipoa_app.py

        # Supprime les .py compilés (garde blender_kit, tts_worker, cine_engine)
        Get-ChildItem -Path "core" -Filter "*.py" -File | Remove-Item -Force
        Get-ChildItem -Path "agents" -Filter "*.py" -File | Remove-Item -Force
        Remove-Item -Force "clipoa_app.py"
        Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
        Copy-Item (Join-Path $Out "*.pyd") -Destination $Src
    } finally {
        Pop-Location
    }

    Write-Host "▸ Compilation du lanceur ClipRoll.exe (sans fenêtre console)" -ForegroundColor Magenta
    # Le lanceur ne contient que la bibliothèque standard : compilation rapide. Les dépendances
    # ne passent PAS par Nuitka (plus de 2 h + échec sur la CI) : elles sont embarquées telles
    # quelles avec un CPython complet dans python\.
    & $PyExe -m nuitka --standalone --windows-console-mode=disable `
        --output-dir=$Stage --output-filename="ClipRoll.exe" `
        --assume-yes-for-downloads `
        (Join-Path $Root "packaging\windows\clipoa_stub.py")

    $DistDir = Join-Path $Stage "clipoa_stub.dist"
    if (-not (Test-Path (Join-Path $DistDir "ClipRoll.exe"))) {
        throw "ClipRoll.exe introuvable dans $DistDir"
    }

    Write-Host "▸ Python embarqué + dépendances (sans recompilation)" -ForegroundColor Magenta
    # Dossier du CPython de base du venv de build (ligne « home = » de pyvenv.cfg)
    $homeLine = Get-Content (Join-Path $BuildVenv "pyvenv.cfg") | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
    $PyHome = ($homeLine -split '=', 2)[1].Trim()
    if (-not (Test-Path (Join-Path $PyHome "python.exe"))) { throw "CPython de base introuvable ($PyHome)" }
    $PyDist = Join-Path $DistDir "python"
    Copy-Item -Recurse -Force $PyHome $PyDist
    $SitePkgs = Join-Path $PyDist "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $SitePkgs | Out-Null
    Get-ChildItem -Path (Join-Path $BuildVenv "Lib\site-packages") |
        Where-Object { $_.Name -notmatch '^(nuitka|Nuitka|ordered_set|zstandard|imageio_ffmpeg)' } |
        ForEach-Object { Copy-Item -Recurse -Force $_.FullName $SitePkgs }
    Get-ChildItem -Path $PyDist -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    if (-not (Test-Path (Join-Path $PyDist "pythonw.exe"))) { throw "pythonw.exe introuvable dans $PyDist" }

    Write-Host "▸ Code ClipRoll (modules compilés .pyd + fichiers)" -ForegroundColor Magenta
    Copy-Item (Join-Path $Root "packaging\windows\launcher.py") -Destination (Join-Path $Src "launcher.py")
    $AppDist = Join-Path $DistDir "app"
    Copy-Item -Recurse -Force $Src $AppDist

    # Vérification : l'app se charge avec le Python embarqué (sans démarrer le serveur)
    $env:CLIPOA_NO_AUTO_TOOLS = "1"
    & (Join-Path $PyDist "python.exe") -c "import sys; sys.path.insert(0, r'$AppDist'); import os; os.chdir(r'$AppDist'); import clipoa_app, core.platform_win; print('  ok', clipoa_app.app.name)"
    if ($LASTEXITCODE -ne 0) { throw "Le code ClipRoll ne se charge pas avec le Python embarqué." }
    Remove-Item Env:\CLIPOA_NO_AUTO_TOOLS

    # Métadonnées de release (edition + release.json)
    Set-Content -Encoding UTF8 -Path (Join-Path $AppDist "edition") -Value $Edition
    $commit = git -C $Root rev-parse --short HEAD
    $builtAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    @{
        version = $Version
        platform = "windows-x64"
        distribution = "msix"
        edition = $Edition
        commit = $commit
        built_at = $builtAt
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path (Join-Path $AppDist "release.json")

    Write-Host "▸ Génération des assets MSIX + AppxManifest.xml" -ForegroundColor Magenta
    $AssetsDir = Join-Path $DistDir "Assets"
    New-Item -ItemType Directory -Force -Path $AssetsDir | Out-Null
    $SrcIcon = Join-Path $Root "assets\brand\ClipRoll-Store-1024.png"
    & $PyExe -c @"
from PIL import Image, ImageDraw
from pathlib import Path
src = Path(r'$SrcIcon')
out = Path(r'$AssetsDir')
base = Image.open(src).convert('RGBA') if src.exists() else Image.new('RGBA', (256, 256), (255, 107, 107, 255))
sizes = {
    'StoreLogo.png': (50, 50),
    'Square44x44Logo.png': (44, 44),
    'Square150x150Logo.png': (150, 150),
    'Wide310x150Logo.png': (310, 150),
}
for name, (w, h) in sizes.items():
    canvas = Image.new('RGBA', (w, h), (20, 20, 28, 255))
    side = int(min(w, h) * 0.65)
    icon = base.resize((side, side), Image.Resampling.LANCZOS)
    canvas.alpha_composite(icon, ((w - side) // 2, (h - side) // 2))
    canvas.save(out / name)
"@

    $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "packaging\windows\AppxManifest.xml")
    $manifest = $manifest.Replace("{{IDENTITY_NAME}}", $IdentityName)
    $manifest = $manifest.Replace("{{PUBLISHER_DISPLAY_NAME}}", $PublisherDisplayName)
    $manifest = $manifest.Replace("{{PUBLISHER}}", $Publisher)
    $manifest = $manifest.Replace("{{VERSION}}", $MsixVersion)
    Set-Content -Encoding UTF8 -Path (Join-Path $DistDir "AppxManifest.xml") -Value $manifest

    # Recherche de makeappx.exe dans le Windows SDK
    $makeappx = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $makeappx) { throw "makeappx.exe introuvable (installe le Windows 10/11 SDK)." }

    $MsixOut = Join-Path $Dist "ClipRoll-$Version-x64.msix"
    if (Test-Path $MsixOut) { Remove-Item -Force $MsixOut }
    Write-Host "▸ Empaquetage MSIX ($MsixOut)" -ForegroundColor Magenta
    & $makeappx.FullName pack /d $DistDir /p $MsixOut /o

    if ($SelfSign) {
        Write-Host "▸ Signature locale d'essai (-SelfSign)" -ForegroundColor Magenta
        $signtool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
        if (-not $signtool) { throw "signtool.exe introuvable." }
        $cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher -KeyUsage DigitalSignature `
            -FriendlyName "ClipRoll Dev Test" -CertStoreLocation "Cert:\CurrentUser\My" `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
        $pfx = Join-Path $BuildDir "test.pfx"
        $pwd = ConvertTo-SecureString -String "clipoa-test" -Force -AsPlainText
        Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $pwd | Out-Null
        & $signtool.FullName sign /fd SHA256 /a /f $pfx /p "clipoa-test" $MsixOut
    }

    Write-Host "✓ Paquet prêt : $MsixOut" -ForegroundColor Green
} finally {
    Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
}
