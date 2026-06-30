param(
  [string]$AppName = "AI PPT Maker",
  [string]$AppDir = "",
  [string]$DataDir = "",
  [bool]$RemoveUserData = $true,
  [switch]$RemovePortableData,
  [switch]$RemoveAppDir,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Resolve-DefaultDataDir {
  param([string]$Name)
  $base = [Environment]::GetFolderPath("ApplicationData")
  if ([string]::IsNullOrWhiteSpace($base)) {
    $base = Join-Path $env:USERPROFILE "AppData\Roaming"
  }
  return Join-Path $base $Name
}

function Resolve-ScriptAppDir {
  if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    return (Get-Location).Path
  }
  return $PSScriptRoot
}

function Test-ExpectedAppDir {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $false
  }
  $exePath = Join-Path $Path "$AppName.exe"
  $internalPath = Join-Path $Path "_internal"
  return (Test-Path -LiteralPath $exePath -PathType Leaf) -and (Test-Path -LiteralPath $internalPath -PathType Container)
}

function Remove-DirectorySafely {
  param(
    [string]$Path,
    [string]$Label
  )
  if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
    Write-Host "Skip missing $Label`: $Path"
    return
  }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $root = [IO.Path]::GetPathRoot($resolved)
  if ($resolved -eq $root -or $resolved.Length -le 6) {
    throw "Refusing to remove unsafe path: $resolved"
  }
  Write-Host "Remove $Label`: $resolved" -ForegroundColor Yellow
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Remove-AppDirectoryAfterExit {
  param([string]$Path)
  if (-not (Test-ExpectedAppDir $Path)) {
    throw "Refusing to remove app directory because it does not look like a packaged $AppName folder: $Path"
  }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $root = [IO.Path]::GetPathRoot($resolved)
  if ($resolved -eq $root -or $resolved.Length -le 6) {
    throw "Refusing to remove unsafe path: $resolved"
  }
  $cleanupScript = Join-Path ([IO.Path]::GetTempPath()) ("ai_ppt_maker_uninstall_{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
  $scriptContent = @"
Start-Sleep -Seconds 2
Remove-Item -LiteralPath '$($resolved.Replace("'", "''"))' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$($cleanupScript.Replace("'", "''"))' -Force -ErrorAction SilentlyContinue
"@
  Set-Content -LiteralPath $cleanupScript -Value $scriptContent -Encoding UTF8
  Write-Host "Schedule app directory removal after this window exits: $resolved" -ForegroundColor Yellow
  Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-WindowStyle",
    "Hidden",
    "-File",
    $cleanupScript
  ) -WindowStyle Hidden | Out-Null
}

function Stop-RunningApp {
  param([string]$Name)
  Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -eq $Name -or $_.ProcessName -eq ($Name -replace '\.exe$', '') } |
    Stop-Process -Force -ErrorAction SilentlyContinue
}

$resolvedAppDir = if ([string]::IsNullOrWhiteSpace($AppDir)) { Resolve-ScriptAppDir } else { $AppDir }
$resolvedDataDir = if ([string]::IsNullOrWhiteSpace($DataDir)) { Resolve-DefaultDataDir $AppName } else { $DataDir }
$portableDataDir = Join-Path $resolvedAppDir "data"

Write-Host ""
Write-Host "AI PPT Maker uninstall helper" -ForegroundColor Cyan
Write-Host "App directory : $resolvedAppDir"
Write-Host "User data     : $resolvedDataDir"
if ($RemovePortableData) {
  Write-Host "Portable data : $portableDataDir"
}
Write-Host ""

if (-not $Force) {
  $answer = Read-Host "Continue? Type YES to uninstall"
  if ($answer -ne "YES") {
    Write-Host "Cancelled."
    exit 0
  }
}

Stop-RunningApp $AppName

if ($RemoveUserData) {
  Remove-DirectorySafely -Path $resolvedDataDir -Label "user data"
}

if ($RemovePortableData) {
  Remove-DirectorySafely -Path $portableDataDir -Label "portable data"
}

if ($RemoveAppDir) {
  Remove-AppDirectoryAfterExit -Path $resolvedAppDir
}

Write-Host ""
Write-Host "Uninstall cleanup complete." -ForegroundColor Green
