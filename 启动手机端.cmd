@echo off
chcp 65001 >nul
title AI PPT Maker Mobile
cd /d "C:\Users\Administrator\Desktop\ai_ppt-main\mobile_app"
echo Starting AI PPT Maker Mobile...
echo Open http://YOUR-PC-IP:7862/?app=mobile-v2 on your phone or tablet.
echo Keep this window open while using the mobile app.
echo.
npm.cmd run preview
pause
