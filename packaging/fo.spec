# PyInstaller spec — builds a single self-contained `fo` binary.
#
#   pyinstaller packaging/fo.spec
#
# Produces dist/fo (dist/fo.exe on Windows) with Python and all dependencies
# bundled, so target machines need nothing installed.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("watchdog")
    + collect_submodules("file_organizer")
)

a = Analysis(
    ["fo.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="fo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
