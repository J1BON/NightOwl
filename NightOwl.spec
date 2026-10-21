# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("dist/index.html", "dist"),
    ("dist/assets", "dist/assets"),
    ("assets", "assets"),
]
binaries = []
hidden = collect_submodules("bridge") + ["clr", "pythonnet"]

for package in ("webview", "clr_loader", "pythonnet"):
    collected_datas, collected_binaries, collected_hidden = collect_all(package)
    datas += collected_datas
    binaries += collected_binaries
    hidden += collected_hidden

a = Analysis(
    ["nightowl.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
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
    name="NightOwl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/nightowl.ico",
    manifest="NightOwl.manifest",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NightOwl",
)
