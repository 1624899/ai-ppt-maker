@echo off
setlocal
title AI PPT Maker Uninstall Launcher

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%uninstall_ai_ppt_maker.ps1"

if not exist "%PS_SCRIPT%" (
  echo Missing uninstall helper script:
  echo %PS_SCRIPT%
  echo.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Wizard
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Uninstall wizard exited with code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
