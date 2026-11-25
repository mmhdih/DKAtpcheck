@echo off
setlocal

echo === ATP Analyzer - portable Windows build ===
echo Builds dist\ATP_Analyzer: the official signed embeddable Python, the app,
echo and ATP_Analyzer.bat to start it. Needs internet and Python 3 with pip.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_portable.ps1"

if errorlevel 1 (
    echo.
    echo Build failed - check the messages above.
) else (
    echo.
    echo Build complete. Start the app with: dist\ATP_Analyzer\ATP_Analyzer.bat
    echo Copy the ENTIRE "dist\ATP_Analyzer" folder when distributing it.
)

pause
