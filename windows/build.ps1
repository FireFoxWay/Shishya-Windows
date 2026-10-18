# Shishya for Windows - build the app folder and the installer.
#
#   powershell -ExecutionPolicy Bypass -File windows\build.ps1
#   powershell -ExecutionPolicy Bypass -File windows\build.ps1 -SkipInstaller
#
# What it makes, under -Out (default %LOCALAPPDATA%\ShishyaBuild):
#
#   Shishya\                 the app, exactly as it is installed
#     Shishya.exe            the launcher (C#, compiled here with the .NET
#                            Framework compiler every Windows has)
#     shishya.cmd            the terminal: shishya, shishya board, shishya ask ...
#     runtime\               an embeddable CPython with every package the
#                            panel and the clone need - nothing is installed
#                            on the machine, and nothing is fetched at run time
#     host\ vm\ clone\ web\  the source, the same files as the Mac build
#     seed\                  what a first run starts with: the demo catalogue
#                            and the demo files. Never shared\training - that is
#                            a real pharmacy's purchase history (see README).
#     INSTALLED              marks an installed copy: data goes to
#                            %LOCALAPPDATA%\Shishya\Data, not beside the program
#   Shishya-Setup-<ver>.exe  the installer (Inno Setup), per-user, no admin
#
# Why a short output path: an AppContainer refuses to start a program whose
# path is longer than Windows' old 260-character limit, and pip's deeper
# package folders get there quickly from a long checkout path.
#
# Needs: Python 3.12 (the py launcher) to drive pip, network access for the
# first build (packages and the embeddable runtime are cached after that),
# and Inno Setup 6 for the installer.

[CmdletBinding()]
param(
    [string]$Out = (Join-Path $env:LOCALAPPDATA "ShishyaBuild"),
    [string]$PythonVersion = "3.12.10",
    [string]$Version = "1.0.0",
    [switch]$SkipInstaller,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$App = Join-Path $Out "Shishya"
$Cache = Join-Path $Out "cache"
$Runtime = Join-Path $App "runtime"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

if ($Clean -and (Test-Path $App)) { Remove-Item -Recurse -Force $App }
New-Item -ItemType Directory -Force $App, $Cache | Out-Null

# --- 1. the runtime ----------------------------------------------------------
Step "runtime: embeddable CPython $PythonVersion"
$zip = Join-Path $Cache "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Invoke-WebRequest $url -OutFile $zip
}
if (-not (Test-Path (Join-Path $Runtime "python.exe"))) {
    Expand-Archive $zip -DestinationPath $Runtime -Force
}
# The embeddable build ignores PYTHONPATH and reads its search path from a
# ._pth file. Site-packages goes in; "import site" switches on .pth handling,
# which pywin32 and pythonnet rely on.
$short = ($PythonVersion -split "\.")[0..1] -join ""
$pth = Join-Path $Runtime "python$short._pth"
Set-Content $pth -Encoding ascii -Value @("python$short.zip", ".", "Lib\site-packages", "import site")
$site = Join-Path $Runtime "Lib\site-packages"
New-Item -ItemType Directory -Force $site | Out-Null

Step "runtime: packages"
$packages = @(
    "PySide6-Essentials==6.12.0", "PySide6-Addons==6.12.0", "PySide6-WebEngine==6.12.0.140",
    "openpyxl", "python-docx", "python-pptx", "pypdf",
    "numpy", "pandas", "matplotlib", "pillow",
    "comtypes", "pywebview", "pythonnet"
)
$marker = Join-Path $site ".shishya-packages"
$want = ($packages -join "`n")
if (-not (Test-Path $marker) -or (Get-Content $marker -Raw) -ne $want) {
    & py -3.12 -m pip install --disable-pip-version-check --no-warn-script-location `
        --upgrade --target $site --cache-dir (Join-Path $Cache "pip") @packages
    if ($LASTEXITCODE -ne 0) { throw "pip failed" }
    Set-Content $marker -Value $want -NoNewline
}

# Things the runtime never needs on a shop's laptop: compilers' headers, test
# suites, Qt's designer and QML tooling. Smaller download, smaller install.
Get-ChildItem $site -Recurse -Directory -Include "tests", "test", "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "pandas\\_libs" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
foreach ($dead in @("PySide6\designer.exe", "PySide6\linguist.exe", "PySide6\assistant.exe",
                    "PySide6\lupdate.exe", "PySide6\lrelease.exe", "PySide6\qmlls.exe",
                    "PySide6\include", "PySide6\examples", "PySide6\typesystems", "PySide6\glue")) {
    $p = Join-Path $site $dead
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

# Qt modules nothing here loads. PySide6 ships all of Qt - 3D, Charts,
# Multimedia with its own FFmpeg, Bluetooth, the QML control styles - and an
# installer three times the size it needs to be is a real cost on a shop's
# connection. What stays: Widgets (every app), WebEngine and what it links
# against (the browser), Svg, PrintSupport, Network. The check further down
# opens a window and a web page with what is left, so a cut too deep fails
# the build rather than an install.
Step "runtime: trim Qt"
$qt = Join-Path $site "PySide6"
$unused = @("Qt63D*", "Qt3D*", "Qt6Quick3D*", "QtQuick3D*", "Qt6Designer*", "QtDesigner*",
            "Qt6Charts*", "QtCharts*", "Qt6DataVisualization*", "QtDataVisualization*",
            "Qt6Graphs*", "QtGraphs*", "Qt6Multimedia*", "QtMultimedia*", "Qt6SpatialAudio*",
            "QtSpatialAudio*", "avcodec*", "avformat*", "avutil*", "swresample*", "swscale*",
            "Qt6Bluetooth*", "QtBluetooth*", "Qt6Nfc*", "QtNfc*", "Qt6Sensors*", "QtSensors*",
            "Qt6SerialPort*", "QtSerialPort*", "Qt6SerialBus*", "QtSerialBus*",
            "Qt6RemoteObjects*", "QtRemoteObjects*", "Qt6Scxml*", "QtScxml*",
            "Qt6StateMachine*", "QtStateMachine*", "Qt6TextToSpeech*", "QtTextToSpeech*",
            "Qt6VirtualKeyboard*", "Qt6QuickControls2*", "Qt6QuickDialogs2*",
            "Qt6QuickTemplates2*", "Qt6Labs*", "Qt6HttpServer*", "QtHttpServer*",
            "Qt6Location*", "QtLocation*", "Qt6ShaderTools*", "Qt6QuickTimeline*",
            "Qt6QuickParticles*", "Qt6Help*", "QtHelp*", "Qt6UiTools*", "QtUiTools*",
            "Qt6Test*", "QtTest*", "Qt6Sql*", "QtSql*", "Qt6Quick3DPhysics*")
foreach ($pattern in $unused) {
    Get-ChildItem $qt -Filter $pattern -File -ErrorAction SilentlyContinue | Remove-Item -Force
}
# Build-time only: type metadata, QML, debug and developer-tools resources,
# and every language's WebEngine strings but English.
foreach ($dir in @("metatypes", "qml", "scripts")) {
    $p = Join-Path $qt $dir
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
Get-ChildItem (Join-Path $qt "resources") -Filter "*debug*" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem (Join-Path $qt "resources") -Filter "*devtools*" -ErrorAction SilentlyContinue | Remove-Item -Force
$tr = Join-Path $qt "translations"
if (Test-Path $tr) {
    Get-ChildItem $tr -File | Remove-Item -Force
    Get-ChildItem (Join-Path $tr "qtwebengine_locales") -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "en-US.pak" } | Remove-Item -Force
}
foreach ($plugin in @("multimedia", "sensors", "sqldrivers", "qmltooling", "designer",
                      "renderers", "sceneparsers", "geometryloaders", "position",
                      "geoservices", "canbus", "texttospeech", "virtualkeyboard",
                      "assetimporters", "renderplugins", "help", "qmllint")) {
    $p = Join-Path $qt "plugins\$plugin"
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

# UI Automation's COM wrapper is generated on first use. Generate it now, into
# the runtime, so an installed copy never needs to write into its own folder.
Step "runtime: UI Automation bindings"
& (Join-Path $Runtime "python.exe") -I -B -c "import comtypes.client as c; c.GetModule('UIAutomationCore.dll'); import comtypes.gen.UIAutomationClient; print('ok')"
if ($LASTEXITCODE -ne 0) { throw "could not generate UI Automation bindings" }

# --- 2. the program ----------------------------------------------------------
Step "program files"
$skip = @("__pycache__", ".DS_Store", "*.pyc", ".venv", ".git")
foreach ($dir in @("host", "vm", "clone", "web", "windows")) {
    robocopy (Join-Path $Repo $dir) (Join-Path $App $dir) /MIR /XD __pycache__ .git launcher /XF *.pyc .DS_Store /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying $dir failed" }
}
foreach ($file in @("serve.py", "shishya", "shishya_win.pyw", "doctor.py", "README.md", "HANDBOOK.html")) {
    Copy-Item (Join-Path $Repo $file) $App -Force
}
Set-Content (Join-Path $App "INSTALLED") -Value "Data lives in %LOCALAPPDATA%\Shishya\Data." -Encoding ascii

Step "seed for a first run"
$seed = Join-Path $App "seed"
if (Test-Path $seed) { Remove-Item -Recurse -Force $seed }
New-Item -ItemType Directory -Force (Join-Path $seed "billing"), (Join-Path $seed "training") | Out-Null
$catalogue = Join-Path $Repo "shared\billing\catalogue.csv"
if (Test-Path $catalogue) { Copy-Item $catalogue (Join-Path $seed "billing") }
Copy-Item (Join-Path $Repo "demo-files\*") (Join-Path $seed "training")

Step "terminal command"
Set-Content (Join-Path $App "shishya.cmd") -Encoding ascii -Value @(
    "@echo off",
    "rem The terminal: shishya, shishya board, shishya sum FILE, shishya ask ""...""",
    """%~dp0runtime\python.exe"" -I -X utf8 ""%~dp0shishya"" %*"
)

# --- 3. the launcher ---------------------------------------------------------
Step "Shishya.exe"
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { throw "the .NET Framework C# compiler is missing ($csc)" }
$icon = Join-Path $Repo "windows\shishya.ico"
& $csc /nologo /target:winexe /optimize+ /platform:anycpu "/out:$(Join-Path $App 'Shishya.exe')" `
    "/win32icon:$icon" /reference:System.Windows.Forms.dll `
    (Join-Path $Repo "windows\launcher\Shishya.cs")
if ($LASTEXITCODE -ne 0) { throw "compiling the launcher failed" }

# --- 4. check it -------------------------------------------------------------
Step "check: the runtime imports what the panel and the clone need"
& (Join-Path $Runtime "python.exe") -I -B -c @"
import sys; sys.path[:0] = [r'$App', r'$App\host', r'$App\vm\shell', r'$App\vm', r'$App\clone']
import PySide6.QtWidgets, PySide6.QtWebEngineWidgets, openpyxl, docx, pptx, pypdf, pandas, matplotlib, PIL, comtypes, webview
import serve, winbox, winvm, broker, hands, screen, winhost, common, library, documents, codegen, checks, books, money
print('imports ok')
"@
if ($LASTEXITCODE -ne 0) { throw "the runtime is missing something" }

Step "check: a window and a web page still open after the trim"
$env:QT_QPA_PLATFORM = "offscreen"
$env:QTWEBENGINE_CHROMIUM_FLAGS = "--no-sandbox --disable-gpu"
& (Join-Path $Runtime "python.exe") -I -B -c @"
import sys
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)
QTableWidget(3, 3).show(); QLabel('ok').show()
view = QWebEngineView(); view.resize(400, 300); view.show()
view.loadFinished.connect(lambda ok: (print('web page loaded' if ok else 'web page FAILED'), app.exit(0 if ok else 3)))
view.setHtml('<h1>Shishya</h1>')
QTimer.singleShot(60000, lambda: (print('web page timed out'), app.exit(4)))
sys.exit(app.exec())
"@
$code = $LASTEXITCODE
Remove-Item Env:\QT_QPA_PLATFORM, Env:\QTWEBENGINE_CHROMIUM_FLAGS
if ($code -ne 0) { throw "Qt cannot open a window or a web page with the trimmed runtime ($code)" }

$size = (Get-ChildItem $App -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("app folder: {0} ({1:N0} MB)" -f $App, $size) -ForegroundColor Green

# --- the portable zip ---------------------------------------------------------
# The same app folder, zipped: unzip anywhere with a short path and run
# Shishya.exe. Nothing to install; data still goes to %LOCALAPPDATA%\Shishya\Data.
Step "portable zip"
$zipOut = Join-Path $Out "Shishya-$Version-portable.zip"
if (Test-Path $zipOut) { Remove-Item -Force $zipOut }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($App, $zipOut, [System.IO.Compression.CompressionLevel]::Optimal, $true)
Write-Host ("portable zip: {0} ({1:N0} MB)" -f $zipOut, ((Get-Item $zipOut).Length / 1MB)) -ForegroundColor Green

# --- 5. the installer --------------------------------------------------------
if ($SkipInstaller) { return }
Step "installer"
$iscc = @((Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
          (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
          (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 is not installed: winget install JRSoftware.InnoSetup" }
& $iscc /Q "/DAppDir=$App" "/DOutDir=$Out" "/DAppVersion=$Version" (Join-Path $Repo "windows\shishya.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
$setup = Join-Path $Out "Shishya-Setup-$Version.exe"
Write-Host ("installer: {0} ({1:N0} MB)" -f $setup, ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green
