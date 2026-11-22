param(
    [string] $Python = "python",
    [string] $Version = "0.0.0"
)

$ErrorActionPreference = "Stop"
if ($Version -notmatch '^(?:v)?(\d+\.\d+\.\d+)(?:[-+][0-9A-Za-z.-]+)?$') {
    throw "Version must look like v1.2.3 or v1.2.3-beta.1."
}
$fileVersion = $Matches[1]
$project = Split-Path -Parent $PSScriptRoot
$output = Join-Path $project "build"
$assets = Join-Path $output "release-assets"
$archive = Join-Path $assets "repak.zip"
$repakHash = "6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa"
New-Item -ItemType Directory -Force -Path $assets | Out-Null

if (-not (Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive).Hash -ne $repakHash) {
    Invoke-WebRequest -Uri "https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-pc-windows-msvc.zip" -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive).Hash -ne $repakHash) {
    throw "Repak archive SHA-256 mismatch."
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($archive)
try {
    $entry = $zip.Entries | Where-Object Name -eq "repak.exe"
    if (@($entry).Count -ne 1) { throw "Repak archive must contain one repak.exe." }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $assets "repak.bin"), $true)
} finally {
    $zip.Dispose()
}
foreach ($license in @("MIT", "APACHE")) {
    $licenseFile = Join-Path $assets "repak-LICENSE-$license.txt"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/trumank/repak/v0.2.3/LICENSE-$license" -OutFile $licenseFile
}

$nuitkaArgs = @(
    "--mode=onefile"
    "--enable-plugin=tk-inter"
    "--windows-console-mode=disable"
    "--msvc=latest"
    "--assume-yes-for-downloads"
    "--output-dir=$output"
    "--output-filename=WhiskerwoodModTranslator.exe"
    "--product-name=Whiskerwood Mod Translator"
    "--file-description=Whiskerwood Mod Translator"
    "--file-version=$fileVersion"
    "--product-version=$fileVersion"
    "--include-data-files=ue4ss_settings.lua=ue4ss_settings.lua"
    "--include-data-files=$assets/repak.bin=release-assets/repak.bin"
    "--include-data-files=$assets/repak-LICENSE-*.txt=release-assets/"
    "app.pyw"
)
Push-Location $project
try {
    & $Python -m nuitka @nuitkaArgs
    if ($LASTEXITCODE -ne 0) { throw "Nuitka failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}

$exe = Join-Path $output "WhiskerwoodModTranslator.exe"
$smoke = Join-Path $output ("smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $smoke | Out-Null
$testExe = Join-Path $smoke "WhiskerwoodModTranslator.exe"
Copy-Item -LiteralPath $exe -Destination $testExe
$process = Start-Process -FilePath $testExe -ArgumentList "--smoke-test" -WorkingDirectory $output -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(60000)) {
    Stop-Process -Id $process.Id
    throw "Packaged application smoke test timed out."
}
$report = Join-Path $smoke "data/smoke-test.json"
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) {
    throw "Packaged application smoke test failed (exit code $($process.ExitCode))."
}
Get-Content -LiteralPath $report
$sha = (Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant()
"$sha  WhiskerwoodModTranslator.exe" | Set-Content -LiteralPath "$exe.sha256" -Encoding ascii
