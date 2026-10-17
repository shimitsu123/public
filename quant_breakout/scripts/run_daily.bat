@echo off
rem ── Windows 任务计划程序（タスクスケジューラ）用 ──────────────────────────
rem 关键：任务计划程序启动时的当前目录是 C:\Windows\System32，
rem 所以必须显式指定项目路径，并用 QBREAK_HOME 固定状态文件位置。

set "PROJ=D:\trading\quant_breakout"
set "QBREAK_HOME=D:\trading\var"
set "PY=python"

cd /d "%PROJ%"
"%PY%" run.py paper JP >> "%QBREAK_HOME%\logs\run_daily.out" 2>&1
if errorlevel 1 (
    echo [%date% %time%] 运行失败，返回码 %errorlevel% >> "%QBREAK_HOME%\logs\run_daily.out"
    exit /b %errorlevel%
)
