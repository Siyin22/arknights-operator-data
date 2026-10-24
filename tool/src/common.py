"""Shared paths and local, atomic state handling."""
import hashlib
import json
import os
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
OUTPUT = APP / '导出结果'

def archive_directory(app):
    """Support both the original workspace and a checkout with tool/ beside data."""
    app = Path(app)
    parent = app.parent
    if app.name == 'tool' and (parent / '.git').exists() and (parent / 'version.json').is_file():
        return parent
    return app / '版本数据'


ARCHIVE = archive_directory(APP)
DEFAULT_GAME = Path(r'D:\Hypergryph Launcher\games\Arknights Game')
VERSION = '2.2.0'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def game_files(game):
    game = Path(game)
    return {'binary':game/'GameAssembly.dll',
            'metadata':game/'Arknights_Data/il2cpp_data/Metadata/global-metadata.dat'}


def find_game():
    candidates = []
    config = APP/'settings.json'
    if config.exists():
        try: candidates.append(Path(read_json(config)['game']))
        except (ValueError, KeyError, OSError): pass
    candidates += [DEFAULT_GAME]
    for drive in 'CDEFGH':
        candidates += [Path(f'{drive}:/Hypergryph Launcher/games/Arknights Game')]
    return next((p for p in candidates if all(f.exists() for f in game_files(p).values())), None)


def latest():
    try:
        data = read_json(OUTPUT/'latest.json')
        path = OUTPUT/data['folder']
        if path.resolve().parent == OUTPUT.resolve() and (path/'success.json').exists():
            return path
    except (ValueError, KeyError, OSError): pass
    return None
