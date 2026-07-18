@echo off
setlocal

echo === ATP Analyzer - Windows build ===

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building ATP_Analyzer.exe (this can take a few minutes)...
pyinstaller --noconfirm build_windows.spec

if exist "dist\ATP_Analyzer\ATP_Analyzer.exe" (
    echo.
    echo Build complete.
    echo Your app is at: dist\ATP_Analyzer\ATP_Analyzer.exe
    echo Copy the ENTIRE "dist\ATP_Analyzer" folder when distributing it ^
- the .exe alone will not run without the files next to it.
) else (
    echo.
    echo Build failed - check the messages above.
)

pause
