# -*- mode: python ; coding: utf-8 -*-
"""
build_windows.spec
--------------------
PyInstaller spec file for ATP Analyzer. Run this ON WINDOWS (PyInstaller
does not cross-compile):

    pip install -r requirements.txt
    pip install -r requirements-build.txt
    pyinstaller --noconfirm build_windows.spec

Output: dist/ATP_Analyzer/ATP_Analyzer.exe (onedir build — see README for
why onedir is preferred over --onefile for this app).

Using a .spec file (rather than long CLI flags) also sidesteps the
Windows-vs-Linux/macOS "--add-data" path separator difference (';' vs ':'),
since datas here are plain (source, dest) tuples.
"""
import os

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
    "matplotlib",
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
    # UPX compression is OFF on purpose: UPX-packed executables are one of
    # the most common reasons antivirus (incl. Windows Defender) flags and
    # quarantines PyInstaller apps as malware. The size saving isn't worth it.
    upx=False,
    console=True,  # set to False once you've confirmed everything works,
                   # to hide the console window behind the app
    icon=None,     # point this at a .ico file to set a custom app icon
    # Embed file/product metadata (Details tab in file Properties); bare
    # executables with no version resource look more suspicious to AV.
    version=os.path.join(SPECPATH, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ATP_Analyzer",
)
