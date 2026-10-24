"""Extract selected local gamedata TextAssets, preserving bundle provenance."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import UnityPy
import lz4ak


def operator_asset(rel):
    tables = ('character_table', 'char_patch_table', 'skill_table', 'uniequip_table', 'battle_equip_table', 'building_data')
    return rel.name == 'data_version.txt' or (rel.suffix == '.bytes' and rel.stem.startswith(tables))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--operators-only', action='store_true')
    args = ap.parse_args()
    lz4ak.install()
    root = args.game / 'Arknights_Data'
    base = root / 'StreamingAssets/AB/Windows'
    cache = root / 'PersistentData/Bundles'
    update_path = cache/'hot_update_list.json'
    if not update_path.exists():
        update_path = base/'hot_update_list.json'
    update = json.loads(update_path.read_text(encoding='utf-8'))
    files = {}
    for entry in update['abInfos']:
        logical = entry['name']
        if not logical.startswith('anon/'):
            continue
        if '..' in PurePosixPath(logical).parts:
            raise ValueError('Unsafe manifest path')
        p = cache/logical
        if not p.exists():
            p = base/logical
        if not p.exists():
            raise FileNotFoundError(f'Missing current bundle: {logical}')
        if p.stat().st_size != entry['abSize']:
            raise ValueError(f'Current bundle size mismatch: {logical}')
        files[logical] = p
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    errors = []
    for index, (logical, p) in enumerate(sorted(files.items())):
        try:
            env = UnityPy.load(str(p))
            count = 0
            for name, obj in env.container.items():
                name = name.replace('\\', '/')
                prefix = 'dyn/gamedata/'
                if not name.startswith(prefix) or obj.type.name != 'TextAsset':
                    continue
                rel = PurePosixPath(name[len(prefix):])
                if rel.is_absolute() or '..' in rel.parts:
                    raise ValueError('Unsafe container path')
                if rel.parts[0] not in ('excel', 'levels', 'battle') and rel.name != 'buff_table.bytes':
                    continue
                if args.operators_only and not operator_asset(rel):
                    continue
                asset = obj.read()
                data = asset.m_Script
                if isinstance(data, str):
                    data = data.encode('utf-8', 'surrogateescape')
                target = args.output / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if any(x['path'] == str(rel) and x['sha256'] != hashlib.sha256(data).hexdigest() for x in manifest):
                    raise ValueError(f'Conflicting asset: {rel}; select correct bundle version')
                target.write_bytes(data)
                manifest.append({'path':str(rel),'bundle':str(p),'logical_bundle':logical,
                                 'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                count += 1
            if count or index % 20 == 0:
                print(f'{index+1}/{len(files)} {logical}: {count} extracted', flush=True)
        except Exception as exc:
            errors.append({'bundle':str(p),'error':str(exc)})
            print(f'ERROR {logical}: {exc}', flush=True)
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'version.json').write_text(json.dumps({'versionId':update['versionId'],'manifest':str(update_path)},indent=2),encoding='utf-8')
    print(f'Extracted {len(manifest)} assets; {len(errors)} errors')
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
