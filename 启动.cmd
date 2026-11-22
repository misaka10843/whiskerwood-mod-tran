@echo off
cd /d "%~dp0"
where pythonw.exe >nul 2>&1
if errorlevel 1 (
    python.exe app.pyw
    if errorlevel 1 pause
) else (
    start "" pythonw.exe "%~dp0app.pyw"
)
