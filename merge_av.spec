# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for merge_av.py
构建命令: pyinstaller merge_av.spec
"""

block_cipher = None

a = Analysis(
    ['merge_av.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'InquirerPy',
        'InquirerPy.base',
        'InquirerPy.base.control',
        'InquirerPy.prompts',
        'InquirerPy.prompts.input',
        'InquirerPy.prompts.confirm',
        'InquirerPy.prompts.number',
        'InquirerPy.prompts.list',
        'prompt_toolkit',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='merge_av',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
