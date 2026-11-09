@echo off
chcp 65001 >nul
title Feiyu Pet Demo Launcher
rem 双击本文件即可：从项目根启动本地服务器并自动打开网页 Demo
rem （必须从项目根启动，页面里的 ../assets/source-webm 才能找到素材）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start-demo.ps1"
if errorlevel 1 (
  echo.
  echo [!] Start failed. Please read the message above.
  pause
)
