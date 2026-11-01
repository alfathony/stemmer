# Builds desktop\dist\Stemmer\Stemmer.exe and the installer
# desktop\dist\Stemmer-<version>-windows-x64-setup.exe.
# Needs: Python 3.11 venv at backend\.venv with backend + desktop requirements,
# Node.js, and Inno Setup 6 (iscc on PATH or in its default folder).
$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\.."
$Py = "$Root\backend\.venv\Scripts\python.exe"
$Version = if ($env:STEMMER_VERSION) { $env:STEMMER_VERSION } else { "0.1.0" }
$env:STEMMER_VERSION = $Version

# Both Demucs models must be downloaded once so they can be bundled.
foreach ($model in "htdemucs", "htdemucs_6s") {
  & $Py -c "from demucs.pretrained import get_model; get_model('$model')"
  if ($LASTEXITCODE) { throw "model download failed: $model" }
}

Push-Location "$Root\frontend"; npm run build; if ($LASTEXITCODE) { throw "frontend build failed" }; Pop-Location

Push-Location "$Root\desktop"
& $Py -m PyInstaller --noconfirm --clean --distpath "$Root\desktop\dist" --workpath "$Root\desktop\build" stemmer.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$Iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $Iscc) { $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $Iscc "/DAppVersion=$Version" "windows\stemmer.iss"
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Pop-Location

Get-ChildItem "$Root\desktop\dist\Stemmer-$Version-windows-x64-setup.exe" | Format-Table Name, @{n="MB"; e={[math]::Round($_.Length / 1MB)}}
