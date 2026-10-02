"""Local media analysis and reversible quarantine. No network calls."""
from __future__ import annotations
import csv, hashlib, json, os, re, shutil, subprocess, tempfile, threading, uuid
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import numpy as np

EXTENSIONS = {'.mp3', '.mp4', '.m4a', '.wav', '.flac', '.aac', '.ogg', '.aiff'}
QUARANTINE = '_DJ_DUPLICADOS'
class Cancelled(Exception): pass

def check_cancel(event):
    if event is not None and event.is_set(): raise Cancelled()

def digest(path, event=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while block := f.read(1024 * 1024):
            check_cancel(event); h.update(block)
    return h.hexdigest()

def run_process(command, event=None, timeout=1800):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        # FFmpeg and ffprobe are console programs. Suppress their console window
        # on Windows while keeping captured output available for diagnostics.
        process_options = {}
        if os.name == 'nt':
            process_options['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        p = subprocess.Popen(command, stdout=out, stderr=err, **process_options)
        import time
        start = time.monotonic()
        try:
            while p.poll() is None:
                check_cancel(event)
                if time.monotonic() - start > timeout: raise RuntimeError('Tiempo máximo de análisis excedido')
                if event is not None: event.wait(.1)
                else: time.sleep(.1)
            out.seek(0); err.seek(0)
            if p.returncode: raise RuntimeError(err.read().decode(errors='replace')[-1000:])
            return out.read()
        finally:
            if p.poll() is None: p.kill(); p.wait()

@dataclass
class Media:
    path: Path
    sha: str
    size: int
    duration: float = 0
    bitrate: int = 0
    title: str = ''
    artist: str = ''
    version: str = ''
    video: bool = False
    pcm: str = ''
    features: object = field(default=None, repr=False)
    error: str = ''

@dataclass
class Match:
    a: Media
    b: Media
    kind: str
    score: float
    keep: Path

@dataclass
class Report:
    root: Path
    files: list
    matches: list
    errors: list

def version_label(name):
    terms = re.findall(r'\b(?:extended|remix|radio|intro|outro|clean|explicit|edit|instrumental|acapella|live|original)\b', name.lower())
    return ', '.join(sorted(set(terms)))

def extract_features(raw):
    samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
    # One spectral signature per half-second throughout the entire audio.
    n = 2048; hop = 5512
    if len(samples) < n: return np.empty((0, 32), dtype=np.float32)
    indices = np.arange(0, len(samples) - n + 1, hop)
    bins = np.unique(np.geomspace(1, n // 2 + 1, 33).astype(int))
    window = np.hanning(n)
    rows = []
    for offset in range(0, len(indices), 256):
        batch = indices[offset:offset + 256, None] + np.arange(n)
        power = np.abs(np.fft.rfft(samples[batch] * window)) ** 2
        bands = np.stack([power[:, lo:hi].mean(axis=1) for lo, hi in zip(bins[:-1], bins[1:])], axis=1)
        feat = np.log1p(bands * 100)
        feat -= feat.mean(axis=1, keepdims=True)
        norm = np.linalg.norm(feat, axis=1, keepdims=True)
        rows.append((feat / np.maximum(norm, 1e-8)).astype(np.float32))
    return np.concatenate(rows)

def similarity(a, b):
    if a is None or b is None or min(len(a), len(b)) < 10: return 0.0
    best = 0.0
    for shift in range(-4, 5):
        x = a[max(shift, 0):]; y = b[max(-shift, 0):]
        count = min(len(x), len(y))
        scores = np.sum(x[:count] * y[:count], axis=1)
        # Silence and static tonal content must not alone qualify as a match.
        active = (np.linalg.norm(x[:count], axis=1) > .5) & (np.linalg.norm(y[:count], axis=1) > .5)
        if active.sum() < 10: continue
        temporal = min(float(np.std(x[:count], axis=0).mean()), float(np.std(y[:count], axis=0).mean()))
        if temporal < .015: continue
        best = max(best, float(np.quantile(scores[active], .15)))
    return best

def inspect(path, acoustic, event):
    before = path.stat()
    m = Media(path, digest(path, event), before.st_size)
    if acoustic:
        try:
            meta = json.loads(run_process(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], event, 60))
            streams = meta.get('streams', []); audio = next(s for s in streams if s.get('codec_type') == 'audio')
            fmt = meta.get('format', {}); tags = {k.lower(): v for k, v in fmt.get('tags', {}).items()}
            m.duration = float(audio.get('duration') or fmt.get('duration') or 0)
            m.bitrate = int(audio.get('bit_rate') or (fmt.get('bit_rate') if not any(s.get('codec_type') == 'video' for s in streams) else 0) or 0)
            m.title = tags.get('title', ''); m.artist = tags.get('artist', '')
            m.video = any(s.get('codec_type') == 'video' for s in streams)
            # Reject unusually long media instead of unbounded PCM allocation.
            if m.duration <= 0 or m.duration > 7200: raise RuntimeError('Duración no válida o superior a 2 horas; solo SHA-256')
            raw = run_process(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '11025', '-f', 's16le', '-'], event)
            m.pcm = hashlib.sha256(raw).hexdigest(); m.features = extract_features(raw)
        except Cancelled: raise
        except Exception as exc: m.error = str(exc)
    m.version = version_label(path.stem + ' ' + m.title)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns): raise RuntimeError('El archivo cambió durante el análisis')
    return m

def scan(root, acoustic=True, progress=lambda s: None, event=None):
    root = Path(root).resolve()
    if not root.is_dir(): raise ValueError('Selecciona una carpeta existente')
    if acoustic and not all(shutil.which(x) for x in ('ffmpeg', 'ffprobe')): raise RuntimeError('Instala FFmpeg y ffprobe, o desactiva el análisis de audio')
    paths = []; errors = []
    def walk_error(e): errors.append(str(e))
    for folder, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        check_cancel(event)
        dirs[:] = sorted(d for d in dirs if d != QUARANTINE and not Path(folder, d).is_symlink())
        for name in sorted(names):
            p = Path(folder, name)
            if p.suffix.lower() in EXTENSIONS and not p.is_symlink(): paths.append(p)
    files = []
    for i, p in enumerate(paths):
        check_cancel(event); progress(f'Analizando {i+1}/{len(paths)}: {p.name}')
        try:
            m = inspect(p, acoustic, event); files.append(m)
            if m.error: errors.append(f'{p}: {m.error}')
        except Cancelled: raise
        except Exception as exc: errors.append(f'{p}: {exc}')
    matches = []
    # Candidate window by duration avoids acoustic comparisons of unrelated lengths.
    exact = {}
    for m in files: exact.setdefault(m.sha, []).append(m)
    for group in exact.values():
        if len(group) > 1:
            anchor = min(group, key=lambda m: (len(str(m.path)), str(m.path)))
            for other in group:
                if other is not anchor: matches.append(Match(anchor, other, 'Copia exacta', 1, anchor.path))
    ordered = sorted((m for m in files if m.features is not None), key=lambda m: m.duration)
    for i, a in enumerate(ordered):
        check_cancel(event); progress(f'Comparando audio {i+1}/{len(ordered)}')
        for b in ordered[i+1:]:
            check_cancel(event)
            if b.duration - a.duration > 2: break
            if a.sha == b.sha: continue
            score = 1 if a.pcm == b.pcm else similarity(a.features, b.features)
            if score < .965: continue
            kind = 'Audio probable · revisar'
            if a.pcm == b.pcm: kind = 'PCM mono igual · revisar'
            if a.version != b.version: kind = 'Versiones distintas · revisar'
            if a.video or b.video: kind = 'Audio de video · revisar imagen'
            keep = max((a, b), key=lambda m: (m.bitrate, m.size)).path
            matches.append(Match(a, b, kind, score, keep))
    return Report(root, files, matches, errors)

def write_csv(report, destination):
    with open(destination, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(['Archivo A', 'Archivo B', 'Tipo', 'Similitud técnica (no probabilidad)', 'Conservar sugerido', 'Bitrate A', 'Bitrate B'])
        def safe(s):
            s = str(s); return "'" + s if s.startswith(('=', '+', '-', '@', '\t', '\r')) else s
        for m in report.matches: w.writerow([safe(m.a.path), safe(m.b.path), m.kind, round(m.score, 4), safe(m.keep), m.a.bitrate, m.b.bitrate])

def save_journal(path, data):
    temporary = path.with_suffix('.tmp')
    with open(temporary, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)

def quarantine(report, selected):
    selected = {Path(p).resolve() for p in selected}
    known = {m.path: m for m in report.files}
    if not selected or not selected.issubset(known): raise ValueError('Selección no válida')
    for p in selected:
        if not any((m.a.path == p and m.b.path not in selected) or (m.b.path == p and m.a.path not in selected) for m in report.matches):
            raise ValueError('Debes conservar al menos una coincidencia directa de cada archivo')
    # Verify selected files AND retained counterparts before any move.
    related = selected | {p for m in report.matches if m.a.path in selected or m.b.path in selected for p in (m.a.path, m.b.path)}
    for p in related:
        if p.is_symlink() or not p.is_file() or digest(p) != known[p].sha: raise ValueError(f'Archivo cambiado o ausente: {p}. Vuelve a analizar.')
    base = report.root / QUARANTINE
    if base.is_symlink(): raise ValueError('La cuarentena no puede ser un enlace simbólico')
    session = base / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    session.mkdir(parents=True, exist_ok=False)
    journal = session / 'restaurar.json'
    data = {'version': 1, 'root': str(report.root), 'entries': []}
    for p in sorted(selected):
        target = session / 'archivos' / p.relative_to(report.root)
        data['entries'].append({'source': str(p), 'target': str(target), 'sha': known[p].sha, 'state': 'pending'})
    save_journal(journal, data)
    try:
        for entry in data['entries']:
            source, target = Path(entry['source']), Path(entry['target'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink() or digest(source) != entry['sha']: raise ValueError(f'Archivo cambiado: {source}')
            shutil.move(str(source), str(target))
            entry['state'] = 'moved'; save_journal(journal, data)
    except Exception as exc:
        raise RuntimeError(f'Movimiento interrumpido. Restaura con {journal}. {exc}') from exc
    return journal

def restore(journal):
    journal = Path(journal).resolve(); data = json.loads(journal.read_text(encoding='utf-8'))
    root = Path(data['root']).resolve(); count = 0
    if data.get('version') != 1 or not journal.is_relative_to(root / QUARANTINE): raise ValueError('Registro de restauración no válido')
    for entry in data['entries']:
        source, target = Path(entry['source']), Path(entry['target'])
        if not source.resolve().is_relative_to(root) or not target.resolve().is_relative_to(journal.parent / 'archivos'): raise ValueError('Ruta fuera de la sesión')
        # pending + target exists recovers a move completed just before a crash.
        if entry['state'] == 'restored' or not target.exists(): continue
        if source.exists() or source.is_symlink(): raise ValueError(f'No se sobrescribe: {source}')
        if target.is_symlink() or digest(target) != entry['sha']: raise ValueError(f'Cuarentena modificada: {target}')
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(source)); entry['state'] = 'restored'
        save_journal(journal, data); count += 1
    return count
