# build_portable.ps1
# -------------------
# Builds the portable Windows version of ATP Analyzer into dist\ATP_Analyzer:
#
#   ATP_Analyzer\
#     ATP_Analyzer.bat   <- double-click this to start the app
#     python\            <- official embeddable Python + all dependencies
#     app\               <- backend\, frontend\, launcher.py, .streamlit\
#
# Why not a PyInstaller .exe: Windows Defender kept quarantining it as
# malware (a heuristic false positive on PyInstaller's packaging, even with
# a self-compiled bootloader). The embeddable Python from python.org ships a
# python.exe digitally signed by the Python Software Foundation, so there is
# no unsigned executable left to flag.
#
# Used by .github/workflows/build-windows.yml and by build_windows.bat.
# Needs internet access and any Python 3 with pip on PATH (only used to run
# pip; dependency wheels are picked for the embedded Python's version).
# Works in Windows PowerShell 5.1 and PowerShell 7.

param(
    # Must be a release python.org ships an "embed-amd64" zip for
    # (3.12.10 is the last 3.12 release with binaries).
    [string]$PythonVersion = "3.12.10",
    [string]$OutDir = "dist\ATP_Analyzer",
    [string]$HostPython = "python"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is very slow with the progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
$pyDir = Join-Path $OutDir "python"
$appDir = Join-Path $OutDir "app"
New-Item -ItemType Directory -Force -Path $pyDir, $appDir | Out-Null

# 1. Official embeddable Python, and refuse to continue unless python.exe is
#    validly signed (a tampered or wrong download would defeat the purpose).
Write-Host "==> Downloading embeddable Python $PythonVersion"
$zip = Join-Path ([IO.Path]::GetTempPath()) "python-$PythonVersion-embed-amd64.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath $pyDir -Force
$sig = Get-AuthenticodeSignature (Join-Path $pyDir "python.exe")
Write-Host "    python.exe signature: $($sig.Status) - $($sig.SignerCertificate.Subject)"
if ($sig.Status -ne "Valid") { throw "python.exe is not validly signed" }

# 2. The embeddable Python ignores PYTHONPATH and reads its search path from
#    pythonXY._pth: add site-packages and the app folder, and enable site.
$pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
Set-Content -Path $pth.FullName -Encoding ascii -Value @(
    ($pth.BaseName + ".zip"), ".", "Lib\site-packages", "..\app", "import site"
)

# 3. Dependencies, as Windows wheels for the EMBEDDED Python's version
#    (whatever Python runs pip here).
Write-Host "==> Installing dependencies"
$parts = $PythonVersion.Split(".")
$sitePackages = Join-Path $pyDir "Lib\site-packages"
& $HostPython -m pip install --no-warn-script-location --disable-pip-version-check `
    --only-binary=:all: --platform win_amd64 --implementation cp `
    --python-version "$($parts[0]).$($parts[1])" --abi "cp$($parts[0])$($parts[1])" `
    --target $sitePackages -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# App-local copies of the MSVC C++ runtime, in case a dependency's native
# module needs it and the target PC has no VC++ redistributable installed.
foreach ($dll in "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll") {
    $src = Join-Path $env:WINDIR "System32\$dll"
    if (Test-Path $src) { Copy-Item $src $pyDir }
}

# 4. The app itself, and the launcher.
Write-Host "==> Copying the app"
Copy-Item -Recurse backend, frontend, .streamlit -Destination $appDir
Copy-Item launcher.py -Destination $appDir
Get-ChildItem $appDir -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Set-Content -Path (Join-Path $OutDir "ATP_Analyzer.bat") -Encoding ascii -Value @(
    '@echo off',
    'title ATP Analyzer',
    'cd /d "%~dp0app"',
    '"%~dp0python\python.exe" launcher.py',
    'if errorlevel 1 pause'
)

# 5. Pre-compile the dependencies with the embedded interpreter itself, so
#    the first launch on the user's PC isn't slowed down by it. Errors here
#    (e.g. files meant for other Python versions) are harmless.
Write-Host "==> Pre-compiling"
& (Join-Path $pyDir "python.exe") -m compileall -q $sitePackages | Out-Null

Write-Host "==> Done: $OutDir\ATP_Analyzer.bat"
exit 0
