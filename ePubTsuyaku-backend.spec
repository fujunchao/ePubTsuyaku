# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: ePubTsuyaku 后端 sidecar（onefile exe，供 Electron 外壳启动）。
#
# 构建命令（CI 中执行）：
#   pyinstaller ePubTsuyaku-backend.spec --noconfirm --distpath dist-backend --workpath build-backend
#
# 运行时目录约定由 Electron 通过环境变量注入（见 translator/webapp.py::_default_project_root）：
#   EPUB_TSUYAKU_DATA_DIR / EPUB_TSUYAKU_OUTPUT_DIR / EPUB_TSUYAKU_BOOKS_DIR

a = Analysis(
    ["webui.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("translator/templates", "translator/templates"),
        ("translator/static", "translator/static"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ePubTsuyaku-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
