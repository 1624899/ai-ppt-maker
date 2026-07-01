param(
  [string]$AppName = "AI PPT Maker",
  [string]$AppDir = "",
  [string]$DataDir = "",
  [bool]$RemoveUserData = $true,
  [switch]$RemovePortableData,
  [switch]$RemoveAppDir,
  [switch]$Force,
  [switch]$Wizard
)

$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
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
    Write-Host ("跳过不存在的{0}：{1}" -f $Label, $Path)
    return
  }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $root = [IO.Path]::GetPathRoot($resolved)
  if ($resolved -eq $root -or $resolved.Length -le 6) {
    throw ("拒绝删除不安全路径：{0}" -f $resolved)
  }
  Write-Host ("正在删除{0}：{1}" -f $Label, $resolved) -ForegroundColor Yellow
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Remove-AppDirectoryAfterExit {
  param([string]$Path)
  if (-not (Test-ExpectedAppDir $Path)) {
    throw ("拒绝删除程序目录：该路径不像打包后的 {0} 目录：{1}" -f $AppName, $Path)
  }
  $resolved = (Resolve-Path -LiteralPath $Path).Path
  $root = [IO.Path]::GetPathRoot($resolved)
  if ($resolved -eq $root -or $resolved.Length -le 6) {
    throw ("拒绝删除不安全路径：{0}" -f $resolved)
  }
  $cleanupScript = Join-Path ([IO.Path]::GetTempPath()) ("ai_ppt_maker_uninstall_{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
  $scriptContent = @"
Start-Sleep -Seconds 2
Remove-Item -LiteralPath '$($resolved.Replace("'", "''"))' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$($cleanupScript.Replace("'", "''"))' -Force -ErrorAction SilentlyContinue
"@
  Set-Content -LiteralPath $cleanupScript -Value $scriptContent -Encoding UTF8
  Write-Host ("已安排在当前窗口退出后删除程序目录：{0}" -f $resolved) -ForegroundColor Yellow
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

function Invoke-UninstallWizard {
  param(
    [string]$AppDirectory,
    [string]$UserDataDirectory,
    [string]$PortableDataDirectory
  )

  $Host.UI.RawUI.WindowTitle = "AI PPT Maker 卸载向导"

  while ($true) {
    Clear-Host
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "             AI PPT Maker 卸载向导" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host ("程序目录：{0}" -f $AppDirectory)
    Write-Host ("用户数据：{0}" -f $UserDataDirectory)
    Write-Host ("便携数据：{0}" -f $PortableDataDirectory)
    Write-Host ""
    Write-Host "请选择要清理的内容："
    Write-Host ""
    Write-Host "  1. 仅清理用户数据"
    Write-Host "     API 密钥、配置、任务数据库、AppData 中的生成结果"
    Write-Host ""
    Write-Host "  2. 仅删除当前程序目录"
    Write-Host "     保留 AppData 中的用户数据"
    Write-Host ""
    Write-Host "  3. 全部删除"
    Write-Host "     用户数据、便携数据和当前程序目录"
    Write-Host ""
    Write-Host "  4. 取消"
    Write-Host ""

    $choice = Read-Host "请输入 1、2、3 或 4"
    switch ($choice) {
      "1" {
        return [pscustomobject]@{
          RemoveUserData = $true
          RemovePortableData = $false
          RemoveAppDir = $false
        }
      }
      "2" {
        return [pscustomobject]@{
          RemoveUserData = $false
          RemovePortableData = $false
          RemoveAppDir = $true
        }
      }
      "3" {
        return [pscustomobject]@{
          RemoveUserData = $true
          RemovePortableData = $true
          RemoveAppDir = $true
        }
      }
      "4" {
        Write-Host ""
        Write-Host "已取消。"
        Read-Host "按 Enter 键关闭窗口"
        exit 0
      }
      default {
        Write-Host ""
        Write-Host "输入无效，请重新选择。" -ForegroundColor Yellow
        Start-Sleep -Seconds 1
      }
    }
  }
}

$resolvedAppDir = if ([string]::IsNullOrWhiteSpace($AppDir)) { Resolve-ScriptAppDir } else { $AppDir }
$resolvedDataDir = if ([string]::IsNullOrWhiteSpace($DataDir)) { Resolve-DefaultDataDir $AppName } else { $DataDir }
$portableDataDir = Join-Path $resolvedAppDir "data"

if ($Wizard) {
  $selection = Invoke-UninstallWizard -AppDirectory $resolvedAppDir -UserDataDirectory $resolvedDataDir -PortableDataDirectory $portableDataDir
  $RemoveUserData = [bool]$selection.RemoveUserData
  $RemovePortableData = [bool]$selection.RemovePortableData
  $RemoveAppDir = [bool]$selection.RemoveAppDir
  $Force = $true
  Clear-Host
}

Write-Host ""
Write-Host "AI PPT Maker 卸载辅助程序" -ForegroundColor Cyan
Write-Host ("程序目录：{0}" -f $resolvedAppDir)
Write-Host ("用户数据：{0}" -f $resolvedDataDir)
if ($RemovePortableData) {
  Write-Host ("便携数据：{0}" -f $portableDataDir)
}
Write-Host ""

if (-not $Force) {
  $answer = Read-Host "确认继续卸载？请输入 YES"
  if ($answer -ne "YES") {
    Write-Host "已取消。"
    exit 0
  }
}

Stop-RunningApp $AppName

if ($RemoveUserData) {
  Remove-DirectorySafely -Path $resolvedDataDir -Label "用户数据"
}

if ($RemovePortableData) {
  Remove-DirectorySafely -Path $portableDataDir -Label "便携数据"
}

if ($RemoveAppDir) {
  Remove-AppDirectoryAfterExit -Path $resolvedAppDir
}

Write-Host ""
Write-Host "卸载清理已完成。" -ForegroundColor Green

if ($Wizard) {
  Write-Host ""
  if ($RemoveAppDir) {
    Write-Host "程序目录会在此窗口关闭后继续删除。"
  } else {
    Read-Host "按 Enter 键关闭窗口"
  }
}
