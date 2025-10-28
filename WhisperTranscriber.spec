# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Get the path to the whisper package
whisper_path = os.path.join(os.getcwd(), 'whisper')
assets_path = os.path.join(whisper_path, 'assets')

# Collect all whisper assets including the large-v3 model
whisper_datas = []

# Add all assets from whisper/assets directory
if os.path.exists(assets_path):
    for item in os.listdir(assets_path):
        item_path = os.path.join(assets_path, item)
        if os.path.isfile(item_path):
            whisper_datas.append((item_path, 'whisper/assets'))

# Add normalizers data
normalizers_path = os.path.join(whisper_path, 'normalizers')
if os.path.exists(normalizers_path):
    for item in os.listdir(normalizers_path):
        if item.endswith('.json'):
            item_path = os.path.join(normalizers_path, item)
            whisper_datas.append((item_path, 'whisper/normalizers'))

# CRITICAL: Add FFmpeg as BINARY (not data) to preserve executable permissions
ffmpeg_binaries = []
ffmpeg_path = os.path.join(os.getcwd(), 'ffmpeg')
if os.path.exists(ffmpeg_path):
    ffmpeg_binaries.append((ffmpeg_path, '.'))
    print(f"✓ FFmpeg found and will be bundled: {ffmpeg_path}")
else:
    print(f"⚠ WARNING: FFmpeg not found at {ffmpeg_path}")

# Collect hidden imports
hidden_imports = [
    'whisper',
    'whisper.model',
    'whisper.audio',
    'whisper.decoding',
    'whisper.tokenizer',
    'whisper.transcribe',
    'whisper.timing',
    'whisper.utils',
    'whisper.normalizers',
    'whisper.normalizers.basic',
    'whisper.normalizers.english',
    'torch',
    'torchaudio',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'numpy',
    'numba',
    'numba.core',
    'numba.core.typing',
    'numba.core.typing.ctypes_utils',
    'regex',
    'tqdm',
    'more_itertools',
]

a = Analysis(
    ['transcriber_app.py'],
    pathex=[],
    binaries=ffmpeg_binaries,  # ✅ FFmpeg as binary to keep executable permissions
    datas=whisper_datas,
    hiddenimports=hidden_imports,
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
    [],
    exclude_binaries=True,
    name='WhisperTranscriber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # Let PyInstaller detect - avoids universal2 issues
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WhisperTranscriber',
)

app = BUNDLE(
    coll,
    name='Whisper Video Transcriber.app',
    icon=None,
    bundle_identifier='com.whisper.transcriber',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Audio/Video Files',
                'CFBundleTypeRole': 'Viewer',
                'LSItemContentTypes': [
                    'public.movie',
                    'public.audio',
                    'public.mpeg-4',
                    'com.apple.quicktime-movie',
                    'public.mp3',
                    'public.mpeg-4-audio',
                ],
                'LSHandlerRank': 'Default',
            }
        ],
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15.0',  # macOS Catalina or later (required for PyTorch)
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
    },
)
