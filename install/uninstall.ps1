<#
.SYNOPSIS
    Removes what install.ps1 installed. Lists by default; -Yes actually removes.

.DESCRIPTION
    Removes the VS Code extension, the private Python runtime, the unpacked
    sidecar and the `meridian` launcher. It does NOT touch:
      * your recorded evidence (each workspace's .meridian folder) - that is
        yours; to remove it use:  meridian uninstall --workspace <dir> --yes
        BEFORE running this script (it needs the launcher this script deletes);
      * your Premium licence, unless -PurgeLicence is given.

.PARAMETER Yes           Actually remove (without it, only lists what would go).
.PARAMETER Code          VS Code command-line tool.
.PARAMETER NoExtension   Leave the VS Code extension installed.
.PARAMETER Prefix        The custom location used at install time.
.PARAMETER PurgeLicence  Also remove installed licence files (per-user scope).
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [string]$Code,
    [switch]$NoExtension,
    [string]$Prefix,
    [switch]$PurgeLicence
)

$ErrorActionPreference = 'Stop'
$ExtensionId = 'meridianloom.meridian-loom'
if ($Prefix) { $Root = $Prefix } else { $Root = Join-Path $env:LOCALAPPDATA 'MeridianLoom' }
$LicenceDir = Join-Path $env:APPDATA 'MeridianLoom\licence'

Write-Host 'Meridian Loom uninstall' -ForegroundColor Cyan
$plan = @()
if (-not $NoExtension) { $plan += "VS Code extension $ExtensionId" }
if (Test-Path $Root)   { $plan += "folder $Root  (runtime, sidecar, meridian command)" }
if ($PurgeLicence -and (Test-Path $LicenceDir)) { $plan += "licence files in $LicenceDir" }
if ($plan.Count -eq 0) { Write-Host 'Nothing to remove.'; exit 0 }
$plan | ForEach-Object { Write-Host "  - $_" }
Write-Host '  (your recorded evidence in each workspace .meridian folder is kept)'

if (-not $Yes) {
    Write-Host ''
    Write-Host 'This was only a list. Re-run with -Yes to remove.' -ForegroundColor Yellow
    exit 0
}

if (-not $NoExtension) {
    $codeCmd = $null
    $candidates = @()
    if ($Code) { $candidates += $Code }
    $candidates += @('code', 'code-insiders', 'codium')
    foreach ($c in $candidates) {
        $r = Get-Command $c -ErrorAction SilentlyContinue
        if ($r) { $codeCmd = $r.Source; break }
    }
    if ($codeCmd) {
        & $codeCmd --uninstall-extension $ExtensionId
    } else {
        Write-Host 'VS Code CLI not found; uninstall the extension from the Extensions view.' -ForegroundColor Yellow
    }
}
if (Test-Path $Root) { Remove-Item -Recurse -Force $Root; Write-Host "removed $Root" }
if ($PurgeLicence -and (Test-Path $LicenceDir)) {
    Get-ChildItem $LicenceDir -Filter '*.mlic' | Remove-Item -Force
    Write-Host "removed licence files from $LicenceDir"
}
Write-Host 'Done. Restart VS Code to finish.' -ForegroundColor Green
