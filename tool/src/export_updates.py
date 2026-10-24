"""Compare successful local versions and export only newly available operators/modules."""
import argparse
import html
import json
from pathlib import Path

from common import read_json, write_json
from operator_details import ATTRS, build_profiles, number


def version_info(run):
    success = read_json(run / 'success.json') if (run / 'success.json').exists() else {}
    resource = read_json(run / 'raw/version.json')['versionId']
    data = (run / 'raw/excel/data_version.txt').read_text(encoding='utf-8-sig').strip()
    return {'folder': run.name, 'resource_version': resource, 'data_version': data,
            'completed_at': success.get('completed_at', '')}


def select_baseline(run):
    """Skip repeated exports of the same version, as well as failed/future runs."""
    current = version_info(run)
    candidates = []
    for path in run.parent.iterdir():
        if path == run or not (path / 'success.json').is_file():
            continue
        info = version_info(path)
        if current['completed_at'] and info['completed_at'] >= current['completed_at']:
            continue
        if (info['resource_version'], info['data_version']) == (current['resource_version'], current['data_version']):
            continue
        candidates.append((info['completed_at'] or path.name, path))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def available_records(source):
    chars = read_json(source / 'character_table.json')
    chars.update(read_json(source / 'char_patch_table.json').get('patchChars') or {})
    operators = {cid: c for cid, c in chars.items()
                 if cid.startswith('char_') and not c.get('isNotObtainable') and c.get('phases')}
    equips = read_json(source / 'uniequip_table.json')['equipDict']
    modules = {eid: e for eid, e in equips.items()
               if e.get('type') != 0 and (e.get('tmplId') or e['charId']) in operators}
    return operators, modules


def build_report(run, baseline):
    operators, modules = available_records(run / 'json')
    report = {'format_version': 1, 'current': version_info(run),
              'baseline': version_info(baseline) if baseline else None,
              'status': 'compared' if baseline else 'baseline',
              'snapshot_counts': {'operators': len(operators), 'modules': len(modules)},
              'added_operator_ids': [], 'added_module_ids': [], 'operators': [], 'module_owners': []}
    if baseline is None:
        return report
    old_operators, old_modules = available_records(baseline / 'json')
    new_chars = set(operators) - set(old_operators)
    new_modules = set(modules) - set(old_modules)
    owners = {modules[e].get('tmplId') or modules[e]['charId'] for e in new_modules}
    profiles = build_profiles(run / 'json', new_chars | owners, new_modules)
    report.update({'added_operator_ids': sorted(new_chars), 'added_module_ids': sorted(new_modules),
                   'operators': [p for p in profiles if p['id'] in new_chars],
                   'module_owners': [p for p in profiles if p['id'] in owners]})
    if len(report['operators']) != len(new_chars) or sum(len(p['modules']) for p in report['module_owners']) != len(new_modules):
        raise ValueError('新增条目与详情数量不一致，更新报告未完成。')
    return report


def escape(value):
    return html.escape(str(value), quote=True)


def paragraph(value, cls=''):
    return f'<p class="{cls}">{escape(value).replace(chr(10), "<br>")}</p>'


def stats_html(stats):
    return '<dl class="stats">' + ''.join(
        f'<div><dt>{label}</dt><dd>{number(stats[k])}{" 秒" if k in ("baseAttackTime", "respawnTime") else ""}</dd></div>'
        for k, label in ATTRS.items()) + '</dl>'


def variants_html(variants, render):
    return ''.join(f'<div class="potential-variant" data-rank="{rank}" data-max="{len(variants)}"'
                   f'{" hidden" if rank > 1 else ""}>{render(v)}</div>' for rank, v in enumerate(variants, 1))


def skill_html(skill):
    def level_html(level):
        meta = f"{level['label']} · {level['recovery']} / {level['trigger']} · 初始 {level['initial']} / 消耗 {level['cost']} 技力 · {level['duration']}"
        if level['charges'] > 1:
            meta += f" · 可充能 {level['charges']} 次"
        return paragraph(meta, 'meta') + paragraph(level['description'])
    extra = ''.join(level_html(v) for v in skill['levels'][:-1])
    return (f'<section class="skill"><h4>技能 {skill["index"]} · {escape(skill["name"])}</h4>'
            + level_html(skill['levels'][-1])
            + (f'<details><summary>查看七级 / 其他专精等级</summary>{extra}</details>' if extra else '') + '</section>')


def operator_html(p):
    def variant(v):
        return (stats_html(v['stats']) + '<h4>特性</h4>' + paragraph(v['trait']) + '<h4>天赋</h4>'
                + (''.join(f'<p><strong>{escape(t["name"])}</strong><br>{escape(t["description"]).replace(chr(10), "<br>")}</p>'
                           for t in v['talents']) or paragraph('无天赋')))
    result = (f'<article id="{escape(p["id"])}"><h3>{escape(p["name"])} <small>{p["rarity"]}★ · {escape(p["profession"])} / {escape(p["branch"])}</small></h3>'
              + paragraph(f"精英{p['phase']} · 满级 {p['level']} · 满信赖 · {p['position']} · {' / '.join(p['tags'])}", 'meta')
              + paragraph('以下属性含所选潜能；不叠加模组与战斗中的天赋、技能增益。', 'hint')
              + variants_html(p['variants'], variant)
              + ''.join(skill_html(s) for s in p['skills']))
    if not p['skills']:
        result += paragraph('无主动 / 被动技能。', 'hint')
    if p['potential']:
        result += '<details><summary>潜能提升</summary>' + ''.join(paragraph(f'潜能{i}：{s}') for i, s in enumerate(p['potential'], 2)) + '</details>'
    if p['tokens']:
        result += '<details><summary>关联召唤物（最高等级的基础属性）</summary>'
        for t in p['tokens']:
            result += f'<h4>{escape(t["name"])}</h4>' + stats_html(t['stats']) + paragraph(t['trait']) + ''.join(skill_html(s) for s in t['skills'])
        result += '</details>'
    return result + '</article>'


def bonus_text(values):
    return ' · '.join(v['label'] + ('+' if v['value'] >= 0 else '') + number(v['value']) for v in values) or '无额外属性加成'


def module_html(module):
    result = f'<section class="module"><h4>{escape(module["type"])} · {escape(module["name"])}</h4>'
    result += paragraph('解锁：' + module['unlock'] + (' · ' + module['special'] if module['special'] else ''), 'meta')
    if not module['levels']:
        return result + paragraph('本版本未提供该模组的战斗效果数据。', 'hint') + '</section>'
    result += '<div class="module-levels">'
    for level in module['levels']:
        result += f'<section><h5>{level["level"]} 级</h5>' + paragraph(bonus_text(level['bonuses']), 'bonus')
        for token in level['tokenBonuses']:
            result += paragraph(token['name'] + '：' + bonus_text(token['bonuses']), 'bonus')
        def effects_html(effects):
            return ''.join(paragraph(e['condition'], 'condition') + '<strong>' + escape(e['name']) + '</strong>' + paragraph(e['description'])
                           for e in effects) or paragraph('无额外文字效果。', 'hint')
        result += variants_html(level['effects'], effects_html) + '</section>'
    return result + '</div></section>'


def render_html(report):
    baseline = report['baseline']
    if baseline:
        intro = f"{baseline['resource_version']} → {report['current']['resource_version']}"
        status = f"新增 {len(report['operators'])} 名干员 · 新增 {len(report['added_module_ids'])} 个模组"
        body = '<h2>新增干员</h2>' + (''.join(operator_html(p) for p in report['operators']) or paragraph('本次没有新增可获取干员。', 'empty'))
        body += '<h2>新增模组</h2>'
        for p in report['module_owners']:
            body += (f'<article><h3>{escape(p["name"])} <small>{escape(p["profession"])} / {escape(p["branch"])}</small></h3>'
                     + ''.join(module_html(m) for m in p['modules']) + '</article>')
        if not report['added_module_ids']:
            body += paragraph('本次没有新增模组。', 'empty')
    else:
        intro = report['current']['resource_version']
        status = '当前版本已作为对比基准'
        body = ('<article><h2>等待下一次版本更新</h2>' + paragraph('尚无更早的成功版本，暂时无法判断哪些内容是新增。下次游戏更新后，点击“提取并对比更新”即可自动生成新增干员和模组的详细报告。')
                + paragraph(f"当前记录 {report['snapshot_counts']['operators']} 名可获取干员（含职业形态）、{report['snapshot_counts']['modules']} 个模组。", 'meta') + '</article>')
    navigation = ''.join(f'<a href="#{escape(p["id"])}">{escape(p["name"])}</a>' for p in report['operators'])
    data_notes = ('按客户端 ID 比较可获取干员（含职业形态）与非默认模组；之前不可获取、现在可获取的干员也列入。'
                  '已有条目的数值修改不计为新增。技能默认展开最高等级，其他等级可展开查看。模组各级是该级的完整加成，不逐级累加。')
    meta = '<details class="source"><summary>对比来源与说明</summary>' + paragraph(data_notes)
    meta += paragraph('当前：' + report['current']['folder'] + '\n' + report['current']['data_version'])
    if baseline:
        meta += paragraph('基准：' + baseline['folder'] + '\n' + baseline['data_version'])
    meta += paragraph('保留上一个版本的成功导出目录，后续对比需要读取其中的数据。报告离线可读，可单独复制。') + '</details>'
    template = Path(__file__).with_name('update_report.html').read_text(encoding='utf-8')
    return (template.replace('__VERSION__', escape(intro)).replace('__STATUS__', escape(status))
            .replace('__NAVIGATION__', navigation).replace('__BODY__', body + meta))


def render_markdown(report):
    lines = ['# 明日方舟 · 更新报告', '', '当前资源版本：' + report['current']['resource_version']]
    if not report['baseline']:
        lines += ['', '当前版本已作为基准。尚无更早的成功版本，不能判断新增内容。下次版本更新后提取即可自动对比。']
        return '\n'.join(lines) + '\n'
    lines += ['对比资源版本：' + report['baseline']['resource_version'], '',
              f"新增 {len(report['operators'])} 名干员；新增 {len(report['added_module_ids'])} 个模组。", '',
              '属性采用最高精英阶段、满级、满信赖、一潜，不叠加模组或战斗增益。网页版可切换潜能。', '', '## 新增干员']
    if not report['operators']:
        lines += ['', '本次没有新增可获取干员。']
    for p in report['operators']:
        v = p['variants'][0]
        lines += ['', f"### {p['name']} · {p['rarity']}★ · {p['profession']} / {p['branch']}", '', f"精英{p['phase']} · 满级 {p['level']} · 满信赖",
                  '', ' / '.join(f'{label} {number(v["stats"][k])}' for k, label in ATTRS.items()), '', '特性：' + v['trait']]
        for t in v['talents']:
            lines += ['', t['name'] + '：' + t['description']]
        for s in p['skills']:
            lines += ['', f"#### 技能{s['index']} · {s['name']}"]
            for lev in reversed(s['levels']):
                lines += ['', f"**{lev['label']}** · {lev['recovery']} / {lev['trigger']} · 初始 {lev['initial']} / 消耗 {lev['cost']} 技力 · {lev['duration']}", '', lev['description']]
        if p['potential']:
            lines += ['', '潜能：'] + [f'- 潜能{i}：{s}' for i, s in enumerate(p['potential'], 2)]
    lines += ['', '## 新增模组']
    if not report['added_module_ids']:
        lines += ['', '本次没有新增模组。']
    for p in report['module_owners']:
        for m in p['modules']:
            lines += ['', f"### {p['name']} · {m['type']} · {m['name']}", '', '解锁：' + m['unlock'], m['special']]
            if not m['levels']:
                lines += ['本版本未提供该模组的战斗效果数据。']
            for lev in m['levels']:
                lines += ['', f"**{lev['level']}级** · {bonus_text(lev['bonuses'])}"]
                for t in lev['tokenBonuses']:
                    lines += ['', t['name'] + '：' + bonus_text(t['bonuses'])]
                for e in lev['effects'][0]:
                    lines += ['', (f"[{e['condition']}] " if e['condition'] else '') + e['name'] + '：' + e['description']]
    lines += ['', '对比基准目录：' + report['baseline']['folder'], '当前目录：' + report['current']['folder'],
              '已有条目的数值修改不计为新增；同一版本重复提取仍对比上一不同版本。']
    return '\n'.join(lines) + '\n'


def export(run, baseline=None, auto=True):
    run = Path(run).resolve()
    if auto and baseline is None:
        baseline = select_baseline(run)
    if baseline is not None:
        baseline = Path(baseline).resolve()
        if baseline == run or not (baseline / 'success.json').is_file():
            raise ValueError('对比基准必须是另一个成功导出目录。')
    report = build_report(run, baseline)
    write_json(run / 'update-report.json', report)
    for name, content in [('更新报告.html', render_html(report)), ('更新报告.md', render_markdown(report))]:
        target = run / name
        temp = target.with_suffix(target.suffix + '.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(target)
    summary = {'status': report['status'], 'file': '更新报告.html',
               'baseline_folder': baseline.name if baseline else None,
               'new_operators': len(report['operators']) if baseline else None,
               'new_modules': len(report['added_module_ids']) if baseline else None}
    write_json(run / 'update-summary.json', summary)
    print('更新报告已生成：' + json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    parser.add_argument('--baseline', type=Path, help='指定另一个成功导出目录；默认自动选取上一版本')
    args = parser.parse_args()
    export(args.run, args.baseline)
