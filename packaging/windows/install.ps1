<#
.SYNOPSIS
  Installateur ClipRoll pour Windows (option secondaire : téléchargement depuis le site web).

.DESCRIPTION
  Reproduit le comportement de packaging/install.sh sur Mac, sans droits administrateur :
  - Installe tout dans %LOCALAPPDATA%\Clipoa (aucun symlink requis).
  - Télécharge uv + Python 3.9 + dernière version de ClipRoll (vérifiée SHA-256).
  - Télécharge Blender (.zip officiel blender.org), FFmpeg (build officiel) et le modèle Whisper
    une seule fois dans data\runtime\ : les mises à jour automatiques ne les retéléchargent pas.
  - Crée un raccourci « ClipRoll » dans le menu Démarrer.

.EXAMPLE
  irm https://dl.clipoa.app/windows/install.ps1 | iex
  .\install.ps1 -Uninstall
#>
param(
    [string]$UpdateUrl = $env:CLIPOA_UPDATE_URL,
    [string]$HomeDir = $env:CLIPOA_HOME,
    [switch]$Uninstall,
    [switch]$Purge,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

if (-not $UpdateUrl) { $UpdateUrl = "__CLIPOA_UPDATE_URL__" }
if (-not $HomeDir) { $HomeDir = Join-Path $env:LOCALAPPDATA "Clipoa" }
$StartMenuLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\ClipRoll.lnk"
$UvVersion = "0.13.10"
$PyVersion = "3.9"

function Say([string]$Msg) { Write-Host "▸ $Msg" -ForegroundColor Magenta }
function Die([string]$Msg) { Write-Host "✗ $Msg" -ForegroundColor Red; exit 1 }

function Check-Sha256([string]$File, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -Path $File).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.Trim().ToLowerInvariant()) {
        Remove-Item -Force -ErrorAction SilentlyContinue $File
        Die "Fichier corrompu (empreinte SHA-256 différente) : $File"
    }
}

if ($Uninstall) {
    Say "Désinstallation de ClipRoll…"
    if (Test-Path $StartMenuLnk) { Remove-Item -Force $StartMenuLnk }
    foreach ($sub in @("versions", "venv", "python", "tools", "bin", "current_version")) {
        $p = Join-Path $HomeDir $sub
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
    if ($Purge) {
        if (Test-Path $HomeDir) { Remove-Item -Recurse -Force $HomeDir }
        Say "Tout est effacé."
    } else {
        Say "ClipRoll est retiré. Tes vidéos et réglages restent dans $HomeDir\data."
    }
    exit 0
}

if ($UpdateUrl -notmatch '^(https://|http://(127\.0\.0\.1|localhost))') {
    Die "Adresse du serveur ClipRoll manquante ou non sécurisée ($UpdateUrl)."
}
$UpdateUrl = $UpdateUrl.TrimEnd("/")

foreach ($d in @("versions", "data\storage", "data\runtime", "data\logs", "data\updates", "tools\uv", "bin")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $HomeDir $d) | Out-Null
}
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("clipoa_inst_" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

try {
    # 1. uv
    $UvExe = Join-Path $HomeDir "tools\uv\uv.exe"
    if (-not (Test-Path $UvExe)) {
        Say "Téléchargement de l'installateur Python (uv $UvVersion)…"
        $uvUrl = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
        $uvZip = Join-Path $Tmp "uv.zip"
        Invoke-WebRequest -Uri $uvUrl -OutFile $uvZip
        $uvSha = (Invoke-WebRequest -Uri "$uvUrl.sha256").Content.Trim().Split()[0]
        Check-Sha256 $uvZip $uvSha
        Expand-Archive -Path $uvZip -DestinationPath (Join-Path $Tmp "uv") -Force
        $foundUv = Get-ChildItem -Path (Join-Path $Tmp "uv") -Recurse -Filter "uv.exe" | Select-Object -First 1
        Copy-Item $foundUv.FullName -Destination $UvExe -Force
    }
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $HomeDir "python"
    $env:UV_CACHE_DIR = Join-Path $HomeDir "data\cache\uv"
    $env:UV_PYTHON_PREFERENCE = "only-managed"

    # 2. Python + venv
    $PyExe = Join-Path $HomeDir "venv\Scripts\python.exe"
    if (-not (Test-Path $PyExe)) {
        Say "Installation de Python $PyVersion (dans $HomeDir)…"
        & $UvExe python install --no-bin $PyVersion | Out-Null
        & $UvExe venv --seed --python $PyVersion (Join-Path $HomeDir "venv") | Out-Null
    }

    # 3. Dernière version de ClipRoll
    Say "Recherche de la dernière version de ClipRoll…"
    $latest = Invoke-RestMethod -Uri "$UpdateUrl/latest.json"
    $Ver = [string]$latest.version
    if ($Ver -notmatch '^[0-9.]+$') { Die "Numéro de version invalide." }
    $PkgUrl = if ([string]$latest.url -match '^https?://') { [string]$latest.url } else { "$UpdateUrl/$($latest.url)" }
    $VerDir = Join-Path $HomeDir "versions\$Ver"

    if (Test-Path (Join-Path $VerDir "release.json")) {
        Say "ClipRoll $Ver est déjà installé."
    } else {
        Say "Téléchargement de ClipRoll $Ver…"
        $pkgZip = Join-Path $Tmp "clipoa.zip"
        Invoke-WebRequest -Uri $PkgUrl -OutFile $pkgZip
        Check-Sha256 $pkgZip ([string]$latest.sha256)
        $tmpVer = Join-Path $HomeDir "versions\.tmp-$Ver"
        if (Test-Path $tmpVer) { Remove-Item -Recurse -Force $tmpVer }
        Expand-Archive -Path $pkgZip -DestinationPath $tmpVer -Force
        Say "Installation des dépendances Python…"
        $lock = Join-Path $tmpVer "requirements.lock"
        if (Test-Path $lock) {
            & $UvExe pip install -q --require-hashes --python $PyExe -r $lock
        } else {
            & $UvExe pip install -q --python $PyExe -r (Join-Path $tmpVer "requirements.txt")
        }
        if (Test-Path $VerDir) { Remove-Item -Recurse -Force $VerDir }
        Move-Item $tmpVer $VerDir
    }

    # 4. Outils lourds conservés dans data\runtime (jamais retéléchargés aux mises à jour)
    $Runtime = Join-Path $HomeDir "data\runtime"
    if ($latest.blender_version) {
        $blMarker = Join-Path $Runtime "blender_version"
        $curBl = if (Test-Path $blMarker) { (Get-Content $blMarker -Raw).Trim() } else { "" }
        if ($curBl -ne [string]$latest.blender_version) {
            $blUrl = [string]$latest.blender_url
            if (-not $blUrl.StartsWith("https://download.blender.org/")) { Die "Adresse de Blender inattendue." }
            Say "Téléchargement de Blender $($latest.blender_version) (une seule fois)…"
            $blZip = Join-Path $Tmp "blender.zip"
            Invoke-WebRequest -Uri $blUrl -OutFile $blZip
            Check-Sha256 $blZip ([string]$latest.blender_sha256)
            $blTmp = Join-Path $Tmp "blender_ext"
            Expand-Archive -Path $blZip -DestinationPath $blTmp -Force
            $blExe = Get-ChildItem -Path $blTmp -Recurse -Filter "blender.exe" | Select-Object -First 1
            $blDest = Join-Path $Runtime "blender"
            if (Test-Path $blDest) { Remove-Item -Recurse -Force $blDest }
            Move-Item $blExe.Directory.FullName $blDest
            Set-Content -Encoding UTF8 -Path $blMarker -Value ([string]$latest.blender_version)
        }
    }

    if ($latest.whisper_revision) {
        $whDir = Join-Path $Runtime "models\faster-whisper-base"
        $whMarker = Join-Path $whDir ".clipoa_revision"
        $curWh = if (Test-Path $whMarker) { (Get-Content $whMarker -Raw).Trim() } else { "" }
        if ($curWh -ne [string]$latest.whisper_revision) {
            Say "Téléchargement du modèle Whisper (une seule fois)…"
            $env:HF_HUB_DISABLE_TELEMETRY = "1"
            & $PyExe -c "import sys; from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-base', revision=sys.argv[1], local_dir=sys.argv[2])" ([string]$latest.whisper_revision) $whDir
            Set-Content -Encoding UTF8 -Path $whMarker -Value ([string]$latest.whisper_revision)
        }
    }

    # Pointeur de version atomique (pas de symlink Windows requis)
    Set-Content -Encoding UTF8 -Path (Join-Path $HomeDir "current_version") -Value $Ver

    # 5. Lanceur serveur (boucle code 42 pour auto-MAJ) + raccourci Menu Démarrer sans console
    $ServerPs1 = Join-Path $HomeDir "bin\clipoa-server.ps1"
    @"
`$HomeDir = Split-Path -Parent (Split-Path -Parent `$MyInvocation.MyCommand.Path)
`$env:CLIPOA_LAUNCHER = "1"
`$env:CLIPOA_STORE_APP = "0"
`$env:CLIPOA_DATA_DIR = Join-Path `$HomeDir "data"
`$env:CLIPOA_PORT = if (`$env:CLIPOA_PORT) { `$env:CLIPOA_PORT } else { "8080" }
`$env:HF_HOME = Join-Path `$HomeDir "data\runtime\huggingface"
`$env:HF_HUB_DISABLE_TELEMETRY = "1"
`$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path `$HomeDir "data\runtime\ms-playwright"
`$env:CLIPOA_WHISPER_DIR = Join-Path `$HomeDir "data\runtime\models\faster-whisper-base"
`$Py = Join-Path `$HomeDir "venv\Scripts\pythonw.exe"
if (-not (Test-Path `$Py)) { `$Py = Join-Path `$HomeDir "venv\Scripts\python.exe" }
while (`$true) {
    `$ver = (Get-Content (Join-Path `$HomeDir "current_version") -Raw).Trim()
    `$appDir = Join-Path `$HomeDir "versions\`$ver"
    Set-Location `$appDir
    `$p = Start-Process -FilePath `$Py -ArgumentList "app.py" -WorkingDirectory `$appDir -WindowStyle Hidden -PassThru -Wait
    if (`$p.ExitCode -ne 42) { break }
}
"@ | Set-Content -Encoding UTF8 -Path $ServerPs1

    $LauncherVbs = Join-Path $HomeDir "bin\ClipRoll.vbs"
    @"
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$ServerPs1""", 0, False
"@ | Set-Content -Encoding ASCII -Path $LauncherVbs

    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($StartMenuLnk)
    $sc.TargetPath = "wscript.exe"
    $sc.Arguments = "`"$LauncherVbs`""
    $sc.WorkingDirectory = $HomeDir
    $sc.Description = "ClipRoll"
    $sc.Save()

    Say "ClipRoll $Ver est installé (Menu Démarrer → ClipRoll)."
    if (-not $NoOpen) {
        Start-Process "wscript.exe" -ArgumentList "`"$LauncherVbs`""
        Start-Sleep -Seconds 3
        Start-Process "http://localhost:8080"
    }
} finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
