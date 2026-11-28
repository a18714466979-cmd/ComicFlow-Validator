param(
    [Parameter(Mandatory = $true)][string]$AppDirectory,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [Parameter(Mandatory = $true)][string]$Version
)

$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Expected a three-part version. Got $Version."
}
$application = (Resolve-Path -LiteralPath $AppDirectory).Path
$output = (New-Item -ItemType Directory -Path $OutputDirectory -Force).FullName
foreach ($file in @('Comic-Sequence-Studio.exe', 'Comic-Sequence-Studio-Worker.exe',
                    '_internal\VERSION.txt', '_internal\REVISION.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $application $file) -PathType Leaf)) {
        throw "The frozen application is missing $file."
    }
}
if ((Get-Content -LiteralPath (Join-Path $application '_internal\VERSION.txt') -Raw).Trim() -cne $Version) {
    throw 'The frozen application version does not match the installer version.'
}

$compiler = (Get-Command ISCC.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $compiler) {
    $knownPath = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    if (-not (Test-Path -LiteralPath $knownPath -PathType Leaf)) {
        throw 'Inno Setup 6 compiler ISCC.exe is required.'
    }
    $compiler = $knownPath
}

$installer = Join-Path $output "Comic-Sequence-Studio-$Version-Windows-x64-Setup.exe"
if (Test-Path -LiteralPath $installer) {
    throw "The output already exists: $installer"
}
& $compiler "/DAppVersion=$Version" "/DAppSource=$application" "/DOutputDirectory=$output" "$PSScriptRoot\installer.iss"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw 'Inno Setup did not produce an installer.'
}
Get-FileHash -Algorithm SHA256 -LiteralPath $installer
