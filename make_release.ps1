# make_release.ps1
# Packages the plugin into a KiCad PCM-compatible zip and prints the SHA256 and size
# to paste into metadata.json.
#
# Usage:
#   .\make_release.ps1 [-Version "1.0.0"]
#
# Output zip: .\dist\circuit-issues-outputjob-v<Version>.zip

param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$RepoRoot  = $PSScriptRoot
$PluginDir = "kicad_library_automation"   # folder name KiCad uses on install
$ZipName   = "circuit-issues-outputjob-v$Version.zip"
$DistDir   = Join-Path $RepoRoot "dist"
$ZipPath   = Join-Path $DistDir $ZipName
$StageDir  = Join-Path $env:TEMP "kicad_plugin_stage_$([System.Guid]::NewGuid().ToString('N'))"

# Files / folders to include in the package
$Include = @(
    "__init__.py",
    "metadata.json",
    "LICENSE",
    "config",
    "modules",
    "ui"
)

Write-Host "Staging plugin files..."
$null = New-Item -ItemType Directory -Path (Join-Path $StageDir $PluginDir) -Force

foreach ($item in $Include) {
    $src = Join-Path $RepoRoot $item
    $dst = Join-Path (Join-Path $StageDir $PluginDir) $item
    if (Test-Path $src -PathType Container) {
        Copy-Item -Recurse -Path $src -Destination $dst
    } elseif (Test-Path $src -PathType Leaf) {
        Copy-Item -Path $src -Destination $dst
    } else {
        Write-Warning "Skipping missing item: $item"
    }
}

# Create dist directory and zip
$null = New-Item -ItemType Directory -Path $DistDir -Force
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

Write-Host "Creating zip: $ZipPath"
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath

# Clean up staging dir
Remove-Item -Recurse -Force $StageDir

# Compute SHA256 and size
$Hash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLower()
$Size = (Get-Item $ZipPath).Length

Write-Host ""
Write-Host "Done! Update metadata.json versions entry with:"
Write-Host "  `"version`": `"$Version`","
Write-Host "  `"download_url`": `"https://github.com/merlinmag/Circuit-Issues-KiCad-OutputJob-Plugin/releases/download/v$Version/$ZipName`","
Write-Host "  `"download_sha256`": `"$Hash`","
Write-Host "  `"install_size`": $Size"
