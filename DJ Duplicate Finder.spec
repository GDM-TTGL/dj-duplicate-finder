# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
ffmpeg_dir = root / 'ffmpeg'
required = [ffmpeg_dir / 'ffmpeg.exe', ffmpeg_dir / 'ffprobe.exe']
if any(not p.is_file() for p in required):
    raise SystemExit('Descarga primero los binarios FFmpeg Windows LGPL a ./ffmpeg.')
binaries = [(str(p), 'ffmpeg') for p in ffmpeg_dir.glob('*.dll')]
binaries += [(str(p), 'ffmpeg') for p in required]
datas = [(str(root / 'assets' / 'DJ_Duplicate_Finder.ico'), 'assets'),
         (str(root / 'assets' / 'DJ_Duplicate_Finder.png'), 'assets'),
         (str(root / 'assets' / 'refresh_taskbar_icon.ps1'), 'assets')]
a = Analysis([str(root / 'app.py')], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=[], hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='DJ Duplicate Finder', console=False,
          icon=str(root / 'assets' / 'DJ_Duplicate_Finder.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='DJ Duplicate Finder')
