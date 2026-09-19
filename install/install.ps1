<#
.SYNOPSIS
    Installs Meridian Loom on Windows: a private Python runtime, the VS Code
    extension, an optional Premium licence, and a `meridian` command.

.DESCRIPTION
    What it does, in order (nothing else):
      1. finds Python 3.11+ and VS Code (or uses the ones you name);
      2. verifies the VSIX against a SHA256SUMS file next to it, if one exists;
      3. builds a PRIVATE virtual environment for Meridian's own dependencies
         under %LOCALAPPDATA%\MeridianLoom\runtime - it never installs into
         your system Python or a project environment;
      4. unpacks the sidecar sources and writes a `meridian` launcher;
      5. installs the extension into VS Code;
      6. installs a Premium licence if you supplied one;
      7. checks that the result works.

    It sends nothing anywhere. The only network use is pip downloading the
    pinned dependencies (unless -Wheelhouse is given, which makes it offline).

    Re-running is safe: an up-to-date runtime is kept, a changed one rebuilt.

.PARAMETER Vsix          Path to meridian-loom-*.vsix (default: newest next to this script or in ..\dist).
.PARAMETER Licence       Path to a .mlic Premium licence file to install.
.PARAMETER MachineWide   Install the licence for every account on this machine (needs an elevated prompt).
.PARAMETER Python        Python 3.11+ interpreter to build the runtime from.
.PARAMETER Code          VS Code command-line tool (code, code-insiders, codium, ...).
.PARAMETER NoExtension   Runtime and CLI only; do not touch VS Code (servers, CI, headless use).
.PARAMETER Wheelhouse    Folder of pre-downloaded wheels: install fully offline.
.PARAMETER IndexUrl      Alternative package index (internal mirror).
.PARAMETER Prefix        Install the runtime here instead of the default location.
.PARAMETER Force         Rebuild the runtime even if it looks current.
.PARAMETER DryRun        Show what would happen; change nothing.

.EXAMPLE
    .\install.ps1
.EXAMPLE
    .\install.ps1 -Licence C:\licences\acme.mlic
.EXAMPLE
    .\install.ps1 -NoExtension -Wheelhouse D:\wheels -Licence acme.mlic -MachineWide
#>
[CmdletBinding()]
param(
    [string]$Vsix,
    [string]$Licence,
    [switch]$MachineWide,
    [string]$Python,
    [string]$Code,
    [switch]$NoExtension,
    [string]$Wheelhouse,
    [string]$IndexUrl,
    [string]$Prefix,
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$MinPython = [version]'3.11'
$ExtensionId = 'meridianloom.meridian-loom'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text)   { Write-Host "    ok: $Text" -ForegroundColor Green }
function Write-Note([string]$Text) { Write-Host "    $Text" }
function Stop-Install([string]$Text) { Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

function Invoke-Step([string]$Description, [scriptblock]$Action) {
    if ($DryRun) { Write-Note "[dry-run] would: $Description"; return }
    & $Action
}

# -- locations -----------------------------------------------------------------
if ($Prefix) { $Root = $Prefix } else { $Root = Join-Path $env:LOCALAPPDATA 'MeridianLoom' }
$RuntimeDir = Join-Path $Root 'runtime'
$VenvDir    = Join-Path $RuntimeDir 'venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$SidecarDir = Join-Path $Root 'sidecar'
$BinDir     = Join-Path $Root 'bin'
$StampFile  = Join-Path $RuntimeDir 'STAMP.json'

# -- 1. Python ------------------------------------------------------------------
function Test-PythonCandidate([string[]]$Command) {
    try {
        $exe = $Command[0]
        $rest = @()
        if ($Command.Length -gt 1) { $rest = $Command[1..($Command.Length - 1)] }
        $out = & $exe @rest -c "import sys; print('%d.%d.%d' % sys.version_info[:3]); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out -or $out.Count -lt 2) { return $null }
        $ver = [version]$out[0]
        if ($ver -lt $MinPython) { return $null }
        # The Microsoft Store "python.exe" stub is not a usable interpreter.
        if ($out[1] -match '\\WindowsApps\\' -and $out[1] -notmatch 'PythonSoftwareFoundation') { return $null }
        return [pscustomobject]@{ Version = $ver; Executable = $out[1] }
    } catch { return $null }
}

function Find-Python {
    if ($Python) {
        $found = Test-PythonCandidate @($Python)
        if (-not $found) { Stop-Install "$Python is not Python $MinPython or newer." }
        return $found
    }
    $candidates = @(
        @('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'),
        @('python3'), @('python')
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
        $found = Test-PythonCandidate $candidate
        if ($found) { return $found }
    }
    Stop-Install ("Python $MinPython or newer was not found. Install it (for example: " +
        "winget install Python.Python.3.12), then re-run this script, or pass -Python <path>.")
}

Write-Step 'Looking for Python'
$py = Find-Python
Write-Ok "Python $($py.Version) at $($py.Executable)"

# -- 2. VS Code + VSIX ----------------------------------------------------------
$CodeCmd = $null
$VsixPath = $null
if (-not $NoExtension) {
    Write-Step 'Looking for VS Code'
    $codeCandidates = @()
    if ($Code) { $codeCandidates += $Code }
    $codeCandidates += @('code', 'code-insiders', 'codium')
    $codeCandidates += (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\bin\code.cmd')
    foreach ($candidate in $codeCandidates) {
        $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($resolved) { $CodeCmd = $resolved.Source; break }
    }
    if (-not $CodeCmd) {
        Stop-Install ("VS Code's command-line tool was not found. Install VS Code from https://code.visualstudio.com/ " +
            "(tick 'Add to PATH'), pass -Code <path>, or use -NoExtension for a headless install.")
    }
    Write-Ok "VS Code CLI: $CodeCmd"

    if ($Vsix) { $VsixPath = (Resolve-Path $Vsix).Path } else {
        $searched = @($Here, (Join-Path $Here '..\dist'))
        foreach ($dir in $searched) {
            if (-not (Test-Path $dir)) { continue }
            $latest = Get-ChildItem -Path $dir -Filter 'meridian-loom-*.vsix' -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($latest) { $VsixPath = $latest.FullName; break }
        }
    }
    if (-not $VsixPath -or -not (Test-Path $VsixPath)) {
        Stop-Install 'No meridian-loom-*.vsix found. Pass -Vsix <path> (or -NoExtension).'
    }
    Write-Ok "package: $VsixPath"
} else {
    # The sidecar sources still come from the package.
    if ($Vsix) { $VsixPath = (Resolve-Path $Vsix).Path } else {
        foreach ($dir in @($Here, (Join-Path $Here '..\dist'))) {
            if (-not (Test-Path $dir)) { continue }
            $latest = Get-ChildItem -Path $dir -Filter 'meridian-loom-*.vsix' -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($latest) { $VsixPath = $latest.FullName; break }
        }
    }
    if (-not $VsixPath) { Stop-Install 'No meridian-loom-*.vsix found. Pass -Vsix <path>.' }
}

# -- 3. integrity ---------------------------------------------------------------
$SumsFile = Join-Path (Split-Path -Parent $VsixPath) 'SHA256SUMS'
if (Test-Path $SumsFile) {
    Write-Step 'Verifying the package checksum'
    $name = Split-Path -Leaf $VsixPath
    $line = Get-Content $SumsFile | Where-Object { $_ -match [regex]::Escape($name) } | Select-Object -First 1
    if (-not $line) {
        Write-Note "SHA256SUMS does not list $name; skipping."
    } else {
        $expected = ($line -split '\s+')[0].ToLowerInvariant()
        $actual = (Get-FileHash -Algorithm SHA256 -Path $VsixPath).Hash.ToLowerInvariant()
        if ($expected -ne $actual) { Stop-Install "Checksum mismatch for $name. Expected $expected, got $actual. Do not install this file." }
        Write-Ok 'SHA-256 matches'
    }
} else {
    Write-Note 'No SHA256SUMS next to the package; integrity not checked (see docs/DEPLOYMENT.md).'
}

# -- 4. runtime -----------------------------------------------------------------
Write-Step 'Preparing the private Python runtime'
$LockFile = Join-Path $Here 'requirements.lock'
$ReqFile = Join-Path $Here 'requirements.txt'
$UseLock = Test-Path $LockFile
$Requirements = if ($UseLock) { $LockFile } else { $ReqFile }
if (-not (Test-Path $Requirements)) { Stop-Install "Missing $ReqFile" }
$reqHash = (Get-FileHash -Algorithm SHA256 -Path $Requirements).Hash.ToLowerInvariant()
$stampWanted = "$reqHash|$($py.Version.Major).$($py.Version.Minor)"

$current = $false
if ((Test-Path $StampFile) -and (Test-Path $VenvPython) -and -not $Force) {
    try { $stamp = Get-Content $StampFile -Raw | ConvertFrom-Json; $current = ($stamp.key -eq $stampWanted) } catch { $current = $false }
}
if ($current) {
    Write-Ok "runtime is up to date ($VenvDir)"
} else {
    Invoke-Step "create $VenvDir and install $(Split-Path -Leaf $Requirements)" {
        if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
        New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
        & $py.Executable -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { Stop-Install 'Could not create the virtual environment.' }
        $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '-r', $Requirements)
        if ($UseLock) { $pipArgs += '--require-hashes' }
        if ($Wheelhouse) { $pipArgs += @('--no-index', '--find-links', $Wheelhouse) }
        elseif ($IndexUrl) { $pipArgs += @('--index-url', $IndexUrl) }
        Write-Note 'installing dependencies (this can take a few minutes)...'
        & $VenvPython @pipArgs
        if ($LASTEXITCODE -ne 0) {
            Stop-Install ('pip could not install the dependencies. Behind a proxy set HTTPS_PROXY; on an offline machine ' +
                'use -Wheelhouse <folder>; with an internal mirror use -IndexUrl <url>.')
        }
        (@{ key = $stampWanted; python = $py.Version.ToString(); installedAt = (Get-Date).ToUniversalTime().ToString('o') } |
            ConvertTo-Json) | Set-Content -Path $StampFile -Encoding ASCII
    }
    Write-Ok "runtime ready ($VenvDir)"
}

# -- 5. sidecar sources + launcher ---------------------------------------------
Write-Step 'Unpacking the sidecar and writing the meridian command'
$Temp = Join-Path ([System.IO.Path]::GetTempPath()) ("meridian-install-" + [guid]::NewGuid().ToString('N'))
try {
    Invoke-Step "unpack $VsixPath and copy extension/sidecar to $SidecarDir" {
        New-Item -ItemType Directory -Force -Path $Temp | Out-Null
        $zip = Join-Path $Temp 'package.zip'
        Copy-Item -Path $VsixPath -Destination $zip
        Expand-Archive -Path $zip -DestinationPath $Temp -Force
        $manifest = Get-Content (Join-Path $Temp 'extension\package.json') -Raw | ConvertFrom-Json
        $Script:PackageVersion = $manifest.version
        $target = Join-Path $SidecarDir $manifest.version
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -Recurse -Force -Path (Join-Path $Temp 'extension\sidecar\*') -Destination $target
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        $launcher = @(
            '@echo off',
            'rem Meridian Loom command line (generated by install.ps1)',
            "set PYTHONPATH=$target",
            "`"$VenvPython`" -m meridian_core.cli %*"
        ) -join "`r`n"
        Set-Content -Path (Join-Path $BinDir 'meridian.cmd') -Value $launcher -Encoding ASCII
        Write-Ok "sidecar $($manifest.version) at $target"
    }
} finally {
    if (Test-Path $Temp) { Remove-Item -Recurse -Force $Temp -ErrorAction SilentlyContinue }
}

# -- 6. extension ---------------------------------------------------------------
if (-not $NoExtension) {
    Write-Step 'Installing the VS Code extension'
    Invoke-Step "$CodeCmd --install-extension $VsixPath --force" {
        & $CodeCmd --install-extension $VsixPath --force
        if ($LASTEXITCODE -ne 0) { Stop-Install 'VS Code refused the extension. Is the version compatible (VS Code 1.95 or newer)?' }
    }
    Write-Ok 'extension installed'
}

# -- 7. licence -----------------------------------------------------------------
$Meridian = Join-Path $BinDir 'meridian.cmd'
if ($Licence) {
    Write-Step 'Installing the Premium licence'
    if (-not (Test-Path $Licence)) { Stop-Install "Licence file not found: $Licence" }
    $scope = 'user'
    if ($MachineWide) { $scope = 'machine' }
    Invoke-Step "meridian licence install $Licence --scope $scope" {
        & $Meridian licence install (Resolve-Path $Licence).Path --scope $scope
        if ($LASTEXITCODE -ne 0) {
            Stop-Install 'The licence was not installed (see the reason above). Community features are unaffected.'
        }
    }
} else {
    Write-Note 'No licence supplied: the free Community edition is active. Add one any time:'
    Write-Note '  meridian licence install <file.mlic>     (or "Meridian Loom: Licence" in VS Code)'
}

# -- 8. verify -------------------------------------------------------------------
Write-Step 'Checking the installation'
if ($DryRun) {
    Write-Note '[dry-run] no changes were made.'
} else {
    & $Meridian licence status
    $probe = & $VenvPython -c "import cryptography, yaml, jsonschema, langgraph, tree_sitter; print('runtime imports ok')" 2>&1
    if ($LASTEXITCODE -ne 0) { Stop-Install "The runtime cannot import its dependencies: $probe" }
    Write-Ok $probe
    Write-Host ''
    Write-Host 'Meridian Loom is installed.' -ForegroundColor Green
    if (-not $NoExtension) { Write-Host '  Reload VS Code, then open the Meridian Loom view (or run "Meridian Loom: Doctor").' }
    Write-Host "  Command line: $Meridian   (add $BinDir to PATH to type just: meridian)"
    if ($Prefix) {
        Write-Host "  Custom location: set VS Code setting meridian.python.interpreterPath to $VenvPython"
    }
}
