@echo off
setlocal
chcp 65001 > nul
title AI PPT Maker Uninstall Wizard

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%uninstall_ai_ppt_maker.ps1"

if not exist "%PS_SCRIPT%" (
  echo Missing uninstall script:
  echo %PS_SCRIPT%
  echo.
  pause
  exit /b 1
)

:menu
cls
echo ===============================================
echo          AI PPT Maker Uninstall Wizard
echo ===============================================
echo.
echo App folder:
echo %SCRIPT_DIR%
echo.
echo Choose what to remove:
echo.
echo   1. Remove user data only
echo      ^(API keys, config, job database, generated outputs in %%APPDATA%%^)
echo.
echo   2. Remove this app folder only
echo      ^(keep user data in %%APPDATA%%^)
echo.
echo   3. Remove everything
echo      ^(user data, portable data, and this app folder^)
echo.
echo   4. Cancel
echo.
set /p "CHOICE=Enter 1, 2, 3 or 4: "

if "%CHOICE%"=="1" goto remove_user_data
if "%CHOICE%"=="2" goto remove_app_dir
if "%CHOICE%"=="3" goto remove_everything
if "%CHOICE%"=="4" goto cancel
goto menu

:remove_user_data
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Force
goto done

:remove_app_dir
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -RemoveUserData:$false -RemoveAppDir -Force
goto done

:remove_everything
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -RemovePortableData -RemoveAppDir -Force
goto done

:cancel
echo.
echo Cancelled.
pause
exit /b 0

:done
echo.
echo Wizard finished.
pause
