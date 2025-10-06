# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['transcriber_app.py'],
    pathex=[],
    binaries=[],
    datas=[('whisper/assets', 'whisper/assets')],
    hiddenimports=['whisper', 'tkinter', 'whisper.utils', 'whisper.tokenizer', 'whisper.model', 'whisper.audio', 'whisper.timing', 'whisper.decoding', 'whisper.transcribe', 'whisper.normalizers', 'torch', 'torchvision', 'torchaudio', 'numba', 'subprocess', 'os', 'sys', 'whisper.assets'],
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
    name='transcriber_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
