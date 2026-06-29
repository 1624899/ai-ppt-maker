param(
  [string]$AppName = "AI PPT Maker",
  [switch]$Clean,
  [switch]$OneFile
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$WebRoot = Join-Path $ProjectRoot "web_ui"
$DistRoot = Join-Path $ProjectRoot "dist"
$BuildRoot = Join-Path $ProjectRoot "build"
$BuildVenv = Join-Path $ProjectRoot ".venv-build"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
$EntryPoint = Join-Path $ProjectRoot "main.py"
$FrontendDist = Join-Path $WebRoot "dist"
$IconPath = Join-Path $ProjectRoot "packaging\windows\app.ico"

function Invoke-Step {
  param(
    [string]$Title,
    [scriptblock]$Action
  )
  Write-Host ""
  Write-Host "==> $Title" -ForegroundColor Cyan
  & $Action
}

function Assert-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Command not found: $Name. Please install it and retry."
  }
}

Push-Location $ProjectRoot
try {
  Invoke-Step "Check build environment" {
    Assert-Command "python"
    Assert-Command "npm"
  }

  if ($Clean) {
    Invoke-Step "Clean previous build outputs" {
      Remove-Item -LiteralPath $DistRoot -Recurse -Force -ErrorAction SilentlyContinue
      Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
      Remove-Item -LiteralPath $FrontendDist -Recurse -Force -ErrorAction SilentlyContinue
    }
  }

  Invoke-Step "Install frontend dependencies" {
    Push-Location $WebRoot
    try {
      if (Test-Path (Join-Path $WebRoot "package-lock.json")) {
        npm ci
      } else {
        npm install
      }
    } finally {
      Pop-Location
    }
  }

  Invoke-Step "Build frontend assets" {
    Push-Location $WebRoot
    try {
      npm run build
    } finally {
      Pop-Location
    }
  }

  Invoke-Step "Prepare isolated Python build environment" {
    if (-not (Test-Path $BuildPython)) {
      python -m venv $BuildVenv
    }
    & $BuildPython -m pip install --upgrade pip
    & $BuildPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt") pyinstaller
  }

  Invoke-Step "Package Windows executable" {
    $separator = [IO.Path]::PathSeparator
    $addData = @(
      "config.json${separator}.",
      "web_ui\dist${separator}web_ui\dist",
      "docs\readme-assets${separator}docs\readme-assets"
    )
    $args = @(
      "-m", "PyInstaller",
      "--noconfirm",
      "--clean",
      "--name", $AppName,
      "--distpath", $DistRoot,
      "--workpath", $BuildRoot,
      "--collect-all", "pptx",
      "--collect-all", "cv2"
    )
    foreach ($item in $addData) {
      $args += @("--add-data", $item)
    }
    if (Test-Path $IconPath) {
      $args += @("--icon", $IconPath)
    }
    if ($OneFile) {
      $args += "--onefile"
    }
    $args += $EntryPoint
    & $BuildPython @args
  }

  Invoke-Step "Build complete" {
    Write-Host "Output directory: $DistRoot" -ForegroundColor Green
    Write-Host "The packaged app stores user data in %APPDATA%\AI PPT Maker by default." -ForegroundColor Green
    Write-Host "Set PPT_SYSTEM_DATA_MODE=portable before launch to use portable data mode." -ForegroundColor Green
  }
} finally {
  Pop-Location
}
