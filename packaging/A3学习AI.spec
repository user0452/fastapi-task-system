# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


packaging_root = Path(SPECPATH).resolve()
project_root = packaging_root.parent

a = Analysis(
    [str(packaging_root / 'competition_launcher.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / 'static'), 'static'),
        (str(project_root / 'alembic'), 'alembic'),
        (str(project_root / 'sql' / 'migrations'), 'sql/migrations'),
        (str(project_root / 'alembic.ini'), '.'),
        (str(project_root / '.env.example'), '.'),
    ],
    hiddenimports=['app.core.migrations'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'mypy', 'ruff', 'IPython', 'matplotlib', 'pandas', 'tensorflow', 'tkinter.test'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='A3学习AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='A3学习AI',
)
