# -*- mode: python ; coding: utf-8 -*-
"""
build_windows.spec
--------------------
PyInstaller spec file for ATP Analyzer. Run this ON WINDOWS (PyInstaller
does not cross-compile):

    pip install -r requirements.txt
    pip install pyinstaller
    pyinstaller --noconfirm build_windows.spec

Output: dist/ATP_Analyzer/ATP_Analyzer.exe (onedir build — see README for
why onedir is preferred over --onefile for this app).

Using a .spec file (rather than long CLI flags) also sidesteps the
Windows-vs-Linux/macOS "--add-data" path separator difference (';' vs ':'),
since datas here are plain (source, dest) tuples.
"""
from PyInstaller.utils.hooks import collect_all

datas = [("backend", "backend"), ("frontend", "frontend")]
binaries = []
hiddenimports = []

# Packages whose non-.py assets (Streamlit's static frontend build, compiled
# extensions, package metadata used for version checks, etc.) PyInstaller
# would otherwise miss if we only followed plain import statements.
COLLECT_ALL_PACKAGES = (
    "streamlit",
    "pandas",
    "numpy",
    "openpyxl",
    "python_calamine",
    "pydantic",
    "pydantic_settings",
    "fastapi",
    "uvicorn",
    "starlette",
)

for package in COLLECT_ALL_PACKAGES:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ATP_Analyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # set to False once you've confirmed everything works,
                   # to hide the console window behind the app
    icon=None,     # point this at a .ico file to set a custom app icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ATP_Analyzer",
)
