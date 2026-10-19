"""Standalone, standard-library comparison for the public data repository."""
import argparse
import html
import json
import re
import subprocess
from pathlib import Path


def git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                       encoding='utf-8', timeout=60)
    if p.returncode:
        raise ValueError(p.stderr.strip() or 'Git 操作失败')
    return p.stdout


def tags(repo):
    return [t for t in git(repo, 'tag', '--sort=version:refname').splitlines()
            if re.fullmatch(r'\d+\.\d+\.\d+', t)]


def load_snapshot(repo, tag):
    if tag not in tags(repo):
        raise ValueError('未找到已保存的官方版本：' + tag)
    # One git process per version, rather than one process for every operator.
    import io
    import tarfile
    data = subprocess.run(['git', '-C', str(repo), 'archive', 'refs/tags/' + tag], capture_output=True, timeout=60)
    if data.returncode:
        raise ValueError(data.stderr.decode('utf-8', errors='replace'))
    result = {'operators': {}, 'modules': {}}
    with tarfile.open(fileobj=io.BytesIO(data.stdout)) as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith('.json'):
                continue
            if member.name != 'version.json' and member.name.split('/')[0] not in ('operators', 'modules'):
                continue
            value = json.load(archive.extractfile(member))
            if member.name == 'version.json':
                result['version'] = value
            elif member.name.split('/')[0] in ('operators', 'modules'):
                result[member.name.split('/')[0]][Path(member.name).stem] = value
    # Client metadata can be added later without rewriting already published data tags.
    if not result['version'].get('client_version'):
        try:
            catalog = json.loads(git(repo, 'show', 'HEAD:version-info.json'))
            client = catalog.get(tag, {}).get('client_version')
            if client:
                result['version']['client_version'] = client
        except (ValueError, KeyError):
            pass
    return result


def version_label(version):
    return f"客户端 {version.get('client_version') or '未记录'} · 数据 {version['official_version']}"


def compare(before, after):
    result = {'before': before['version'] if before else None, 'after': after['version']}
    for category in ('operators', 'modules'):
        old = before[category] if before else {}
        new = after[category]
        result[category] = {
            'added': sorted(set(new) - set(old)) if before else [],
            'removed': sorted(set(old) - set(new)),
            'changed': sorted(k for k in old.keys() & new.keys() if old[k] != new[k])}
    return result


LABELS = {'maxHp': '生命上限', 'atk': '攻击', 'def': '防御', 'magicResistance': '法术抗性',
          'cost': '部署费用', 'blockCnt': '阻挡数', 'baseAttackTime': '基础攻击间隔（秒）',
          'respawnTime': '再部署时间（秒）', 'attackSpeed': '攻击速度', 'name': '名称',
          'description': '效果', 'trait': '特性', 'talents': '天赋', 'stats': '属性',
          'skills': '技能', 'levels': '等级', 'potential': '潜能', 'variants': '潜能档位',
          'modules': '模组', 'bonuses': '属性加成', 'effects': '效果', 'value': '数值',
          'initial': '初始技力', 'duration': '持续时间',
          'charges': '充能次数', 'trigger': '触发方式', 'recovery': '回复方式',
          'tokens': '召唤物', 'tokenBonuses': '召唤物加成', 'condition': '生效条件',
          'type': '类型', 'unlock': '解锁条件', 'special': '限定模式', 'level': '等级',
          'profession': '职业', 'branch': '分支', 'phase': '精英阶段', 'rarity': '星级'}


def changes(old, new, path=''):
    if old == new:
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for key in sorted(old.keys() | new.keys()):
            out += changes(old.get(key), new.get(key), path + '/' + LABELS.get(key, key))
        return out
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        out = []
        for index, (a, b) in enumerate(zip(old, new), 1):
            out += changes(a, b, path + '/' + str(index))
        return out
    return [(path.lstrip('/'), old, new)]


def value_text(value):
    if value is None:
        return '无'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def potential_details(p):
    """Resolve talent enhancements from consecutive potential variants, in talent-slot order."""
    result = []
    variants = p.get('variants', [])
    for i, label in enumerate(p.get('potential', [])):
        enhanced = []
        if '天赋' in label and i + 1 < len(variants):
            before = variants[i].get('talents', [])
            for j, talent in enumerate(variants[i + 1].get('talents', [])):
                if j >= len(before) or talent != before[j]:
                    enhanced.append(talent['name'] + '（提升后）：' + talent['description'])
        result.append('；'.join(enhanced) if enhanced else label)
    return result


def duration_text(value):
    return '持续时间 ' + value if re.fullmatch(r'\d+(?:\.\d+)?\s*秒', value) else value


def details_operator(p):
    variant = p['variants'][0]
    lines = [f"### {p['name']} · {p['rarity']}★ · {p['profession']} / {p['branch']}", '',
             f"精英{p['phase']} · 满级 {p['level']} · 满信赖 · 一潜", '',
             ' / '.join(f'{LABELS.get(k,k)} {v:g}' for k, v in variant['stats'].items() if k != 'attackSpeed'), '',
             '#### 特性与天赋', '', '特性：' + variant['trait']]
    for talent in variant['talents']:
        lines += ['', talent['name'] + '：' + talent['description']]
    lines += ['', '#### 潜能', '']
    lines += ([f'- 潜能{i}：{v}' for i, v in enumerate(potential_details(p), 2)]
              or ['该干员无潜能提升。'])
    for skill in p['skills']:
        lines += ['', f"#### 技能{skill['index']} · {skill['name']}"]
        for lev in reversed(skill['levels']):
            lines += ['', f"{lev['label']} · {lev['recovery']} / {lev['trigger']} · 初始 {lev['initial']} / 消耗 {lev['cost']} 技力 · {duration_text(lev['duration'])}", '', lev['description']]
    return lines


def details_module(m):
    lines = [f"### {m['operator_name']} · {m['type']} · {m['name']}", '', '解锁：' + m['unlock']]
    if m['special']:
        lines += [m['special']]
    for level in m['levels']:
        lines += ['', f"#### {level['level']}级", '', ' / '.join(f"{b['label']} {b['value']:+g}" for b in level['bonuses'])]
        for token in level['tokenBonuses']:
            lines += ['', token['name'] + '：' + ' / '.join(f"{b['label']} {b['value']:+g}" for b in token['bonuses'])]
        for effect in level['effects'][0]:
            lines += ['', ('[' + effect['condition'] + '] ' if effect['condition'] else '') + effect['name'] + '：' + effect['description']]
    if not m['levels']:
        lines += ['', '本版本尚无该模组战斗效果数据。']
    return lines


def markdown(before, after):
    diff = compare(before, after)
    version = after['version']['official_version']
    lines = ['# 明日方舟 · 版本差异', '', ('对比：' + version_label(before['version']) + ' → ' + version_label(after['version'])) if before else '基准版本：' + version_label(after['version']),
             '', '干员采用满级、满信赖属性；本报告文字详情为一潜，JSON 同时保留各潜能档位。']
    if before is None:
        return '\n'.join(lines + ['', f"已保存 {len(after['operators'])} 个干员 / 职业形态、{len(after['modules'])} 个模组。", '',
                                  '这是首个已保存版本，尚无上一版本可供对比，不把全量数据计为新增。']) + '\n'
    for category, label in [('operators', '干员'), ('modules', '模组')]:
        section = diff[category]
        lines += ['', f"## {label}：新增 {len(section['added'])} · 修改 {len(section['changed'])} · 移除 {len(section['removed'])}"]
        for key in section['added']:
            lines += ['', '新增：', ''] + (details_operator(after[category][key]) if category == 'operators' else details_module(after[category][key]))
        for key in section['changed']:
            record = after[category][key]
            lines += ['', '### 修改：' + record['name'], '']
            for path, a, b in changes(before[category][key], record):
                lines += [f'- {path}', '  - 之前：' + value_text(a).replace('\n', ' / '), '  - 现在：' + value_text(b).replace('\n', ' / ')]
        for key in section['removed']:
            lines += ['', '移除：' + before[category][key]['name'] + '（' + key + '）']
        if not any(section.values()):
            lines += ['', '无变化。']
    return '\n'.join(lines) + '\n'


def html_report(text):
    blocks = []
    for line in text.splitlines():
        escaped = html.escape(line)
        heading = re.match(r'^(#{1,4}) (.*)', escaped)
        if heading:
            level = len(heading[1]); blocks.append(f'<h{level}>{heading[2]}</h{level}>')
        elif line:
            blocks.append('<p>' + escaped + '</p>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>明日方舟 · 版本差异</title><style>body{margin:0;background:#f3f6f5;color:#213b43;font:15px/1.9 "Microsoft YaHei",sans-serif}'
            'main{max-width:1000px;margin:32px auto;padding:28px;background:white;border-radius:12px}h1,h2{color:#087b72}h2{border-top:1px solid #ddd;padding-top:24px}'
            'h3{margin-top:28px}p{white-space:pre-wrap;overflow-wrap:anywhere}button{padding:10px;cursor:pointer}@media print{button{display:none}main{margin:0}}</style>'
            '<main><button onclick="window.print()">打印 / 保存 PDF</button>' + ''.join(blocks) + '</main></html>')


def write_comparison(repo, before_tag, after_tag, output):
    from report_renderer import render_report
    before = load_snapshot(repo, before_tag)
    after = load_snapshot(repo, after_tag)
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    text = markdown(before, after)
    (output / '版本差异.md').write_text(text, encoding='utf-8')
    (output / '版本差异.html').write_text(render_report(before, after, compare(before, after)), encoding='utf-8')
    return output / '版本差异.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='比较任意两个已保存的官方版本')
    parser.add_argument('before'); parser.add_argument('after')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path, default=Path('comparison'))
    args = parser.parse_args()
    print(write_comparison(args.repo, args.before, args.after, args.output))
