"""Small, version-tagged Git history; no raw client assets or local paths are published."""
import copy
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from common import APP, read_json, write_json
from operator_details import build_profiles
from version_compare import compare, git, load_snapshot, markdown, tags, version_label

REPOSITORY = 'Siyin22/arknights-operator-module-data-tool'
PUBLIC_GITIGNORE = 'comparison/\n__pycache__/\n*.pyc\n.venv/\nwork/\nsettings.json\npipeline.lock\n启动错误.txt\n'
GENERATED = ('operators', 'modules', 'version.json', 'version-info.json', 'base-skills-history.json', 'README.md', '更新报告.md', '更新报告.html', 'compare.py', 'report_renderer.py', 'report_assets', '.gitignore', '.gitattributes')


def official_version(text):
    match = re.search(r'^VersionControl:\s*(\d+\.\d+\.\d+)\s*$', text, re.MULTILINE)
    if not match:
        raise ValueError('未找到官方 VersionControl 版本号，停止保存以免错误标记版本。')
    return match[1]


def snapshot_from_run(run):
    run = Path(run)
    if not (run / 'json/building_data.json').is_file():
        raise ValueError('缺少已解析的后勤技能数据，请重新提取。')
    data_version = (run / 'raw/excel/data_version.txt').read_text(encoding='utf-8-sig')
    version = official_version(data_version)
    result = {'version': {'format_version': 1, 'official_version': version,
                         'resource_version': read_json(run / 'raw/version.json')['versionId'],
                         'data_version': data_version.strip(), 'region': 'CN',
                         'attributes': '最高精英阶段、满级、满信赖；各潜能分别计算；不叠加模组与实战增益'},
              'operators': {}, 'modules': {}}
    for metadata_file in ('input.json', 'success.json'):
        if (run / metadata_file).is_file():
            metadata = read_json(run / metadata_file)
            client = metadata.get('client_version')
            if not client:
                match = re.search(r'\b(\d+\.\d+\.\d+)\b', metadata.get('client', ''))
                client = match[1] if match else None
            if client:
                result['version']['client_version'] = client
                break
    for profile in build_profiles(run / 'json'):
        profile.pop('sort', None)
        modules = profile.pop('modules')
        result['operators'][profile['id']] = profile
        for module in modules:
            module.update({'operator_id': profile['id'], 'operator_name': profile['name'],
                           'profession': profile['profession'], 'branch': profile['branch']})
            result['modules'][module['id']] = module
    return result


def load_current(repo):
    repo = Path(repo)
    return {'version': read_json(repo / 'version.json'),
            **{category: {p.stem: read_json(p) for p in (repo / category).glob('*.json')}
               for category in ('operators', 'modules')}}


def verified_current(repo):
    if git(repo, 'status', '--porcelain').strip():
        raise ValueError('版本仓库存在本地修改，请先处理后再提取。')
    current = load_current(repo)
    version = current['version']['official_version']
    # Presentation/metadata improvements may follow a version tag; game data must still match.
    git(repo, 'merge-base', '--is-ancestor', 'refs/tags/' + version, 'HEAD')
    if current != load_snapshot(repo, version):
        raise ValueError('当前数据与官方版本标签不一致，停止跳过提取。')
    return current


def initialize(repo, author='Siyin22', email='225679950+Siyin22@users.noreply.github.com'):
    repo = Path(repo); repo.mkdir(parents=True, exist_ok=True)
    if repo.name == '版本数据' and (repo.parent / '.git').exists():
        return  # Unified checkout: data and source share the root repository.
    if not (repo / '.git').exists():
        if any(repo.iterdir()):
            raise ValueError('版本仓库目录已有非 Git 文件，停止初始化。')
        git(repo, 'init', '-b', 'main')
        git(repo, 'config', 'user.name', author)
        git(repo, 'config', 'user.email', email)
        git(repo, 'config', 'core.autocrlf', 'false')
        git(repo, 'config', 'core.quotepath', 'false')


def report_html(before, after):
    from report_renderer import render_report
    return render_report(before, after, compare(before, after))


def write_tree(directory, snapshot, before, versions, version_info=None, base_skill_history=None):
    directory = Path(directory)
    history_path = directory / 'base-skills-history.json'
    if base_skill_history is None:
        base_skill_history = read_json(history_path) if history_path.exists() else {}
    write_json(history_path, base_skill_history)
    for category in ('operators', 'modules'):
        (directory / category).mkdir(parents=True, exist_ok=True)
        for key, record in sorted(snapshot[category].items()):
            if not re.fullmatch(r'[a-zA-Z0-9_]+', key):
                raise ValueError('非法数据 ID：' + key)
            write_json(directory / category / (key + '.json'), record)
    write_json(directory / 'version.json', snapshot['version'])
    version_info = dict(version_info or {})
    for source in (before, snapshot):
        if source and source['version'].get('client_version'):
            version_info[source['version']['official_version']] = {'client_version': source['version']['client_version']}
    write_json(directory / 'version-info.json', version_info)
    (directory / '更新报告.md').write_text(markdown(before, snapshot), encoding='utf-8')
    (directory / '更新报告.html').write_text(report_html(before, snapshot), encoding='utf-8')
    shutil.copyfile(APP / 'src/version_compare.py', directory / 'compare.py')
    shutil.copyfile(APP / 'src/report_renderer.py', directory / 'report_renderer.py')
    shutil.copytree(APP / 'src/report_assets', directory / 'report_assets', dirs_exist_ok=True)
    (directory / '.gitignore').write_text(PUBLIC_GITIGNORE, encoding='utf-8')
    (directory / '.gitattributes').write_text('* text=auto eol=lf\n', encoding='utf-8')
    version = snapshot['version']['official_version']
    lines = ['# 明日方舟 · 干员与模组版本数据', '', f"**{version_label(snapshot['version'])}**（国服）。", '',
             f'[阅读本次更新报告](更新报告.md) · [查看所有官方版本](https://github.com/{REPOSITORY}/tags)', '',
             '工具源码与启动入口位于仓库根目录，首次使用请阅读 [安装说明](../安装说明.txt)。本目录保存当前数据与报告，Git 历史在仓库根目录。', '',
             '保存干员战斗资料、后勤技能与模组的可读数据。本目录始终是一套当前数据；旧版本保存在 Git 历史中，不按日期重复复制整套导出。', '',
             '| 内容 | 说明 |', '| --- | --- |',
             '| `operators/` | 每名干员一个 JSON，含职业形态；最高精英阶段、满级、满信赖，各潜能属性、天赋、技能七级及专精、后勤技能 |',
             '| `modules/` | 每个模组一个 JSON，含所属干员、各级属性与天赋/特性效果 |',
             '| `version.json` | 客户端版本、官方 VersionControl 数据版本与资源版本标识 |',
             '| `version-info.json` | 已核实的历史客户端版本补充信息，保持原有数据标签不变 |',
             '| `base-skills-history.json` | 同版本重新提取并核对后补齐的历史后勤技能；对比脚本读取时合并，不改写原标签 |',
             '| `更新报告.md` | 与上一已保存版本对比的新增、修改和移除；GitHub 可直接阅读 |',
             '| `更新报告.html` | 下载后离线阅读；按干员归组，模组自带无模组对照，支持干员与所选模组合并 PNG、批量 ZIP |',
             '| `compare.py` | 只需 Python 标准库，比较任意两个已保存版本 |', '',
             f"当前包含 {len(snapshot['operators'])} 个干员 / 职业形态、{len(snapshot['modules'])} 个模组。", '',
             '## 离线查看与图片导出', '',
             '下载并解压仓库后，用 Chrome 或 Edge 打开 `更新报告.html`。页面资源已内嵌，查看资料和导出图片均无需联网。', '',
             '可搜索当前版本中的任意干员或模组，选择潜能和技能等级，单独导出 PNG；也可加入清单后批量导出 ZIP，每项资料独立一张图片。', '',
             '干员卡片可勾选所属模组一起展示，合并导出 PNG；也可仅导出干员，或从模组旁单独导出对比图。清单保存加入时勾选的模组，导出时应用顶部潜能与技能选项。', '',
             '模组对比图显示同一数据版本、同一潜能的无模组特性与天赋，保留各级完整属性加成及效果。文字下半部的淡红色标记表示同一效果相较上一级新增或改写的文字，片段首尾的分隔标点不标记；追加描述不推断为替换后的完整天赋。', '',
             '更新报告按干员归组，每项变化分别标记；对照资料不计入新增。移除条目使用其所在旧版本的资料。', '',
             '本次新增干员默认勾选本次新增的所属模组；“导出本次资料”将它们合并成图，不重复导出已合并模组。老干员的新模组单独成图；取消勾选的模组恢复单独导出。', '',
             '报告及导出图片优先使用本机安装的“霞鹜文楷”（LXGW WenKai），缺少时回退到“微软雅黑”；仓库不包含字体文件。', '',
             '## 版本对比', '', 'GitHub 顶部的标签选择器可浏览指定版本，也可使用 Compare 查看两个标签的文件差异。', '',
             '克隆仓库后运行（把两个版本替换为仓库中已有标签）：', '',
             '```sh', 'python compare.py <旧官方版本> <新官方版本>', '```', '',
             '生成 `comparison/版本差异.html` 与 `comparison/版本差异.md`；不会改动当前数据。', '',
             '已保存版本：' + '、'.join(f'[{v}](https://github.com/{REPOSITORY}/tree/{v})' for v in versions), '',
             '## 数据口径', '',
             '版本号直接读取游戏 `data_version.txt` 的 `VersionControl`，不是工具版本或导出日期。',
             '客户端版本对应游戏程序和数据结构（如 2.7.81）；数据版本对应配置（如 78.2.0），同一客户端内可有多次数据更新。',
             '技能描述已经代入参数。属性不叠加模组和战斗中的天赋、技能增益；模组各级加成不累计。',
             '后勤技能显示满级已解锁的最终效果、设施和解锁条件；同组升级仅显示最终技能，JSON 保留各阶段记录。',
             '基于客户端可获取标记筛选干员；职业形态分别记录；默认职业证章不计作模组。',
             '对比范围是已保存版本之间的变化，首次保存仅建立基准。', '',
             '游戏数据与文本的相关权利归原权利人；本仓库为非官方的个人数据对照记录。',
             '页面结构参考 PRTS；图片导出使用 html2canvas 1.4.1（MIT），许可证保留在 report_assets/html2canvas.LICENSE。所有页面资源内嵌，导出无需联网。', '']
    (directory / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def save_snapshot(repo, snapshot):
    """Commit a complete pre-rendered snapshot, tag once, and never overwrite a version."""
    repo = Path(repo); initialize(repo)
    if git(repo, 'status', '--porcelain').strip():
        raise ValueError('版本仓库有未提交的修改，请先处理，避免覆盖本地编辑。')
    version = snapshot['version']['official_version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('非法官方版本号')
    versions = tags(repo)
    if version in versions:
        previous = load_snapshot(repo, version)
        if previous == snapshot:
            return {'version': version, 'created': False, 'repo': str(repo)}
        # A newly supported field can be backfilled from the identical resource snapshot.
        # All previously recorded data must remain byte-for-value equal; this is not a hotfix override.
        stripped = copy.deepcopy(snapshot)
        missing = [cid for cid, p in previous['operators'].items() if 'baseSkills' not in p]
        if missing and all('baseSkills' in p for p in snapshot['operators'].values()):
            for cid in missing:
                if cid in stripped['operators']:
                    stripped['operators'][cid].pop('baseSkills', None)
            if stripped == previous and load_current(repo)['version']['official_version'] == version:
                verified_current(repo)
                history_path = repo / 'base-skills-history.json'
                history = read_json(history_path) if history_path.exists() else {}
                history[version] = {'version': snapshot['version'],
                                    'operators': {cid: p['baseSkills'] for cid, p in snapshot['operators'].items()}}
                earlier = versions[:versions.index(version)]
                before = load_snapshot(repo, earlier[-1]) if earlier else None
                catalog = read_json(repo / 'version-info.json') if (repo / 'version-info.json').exists() else {}
                write_tree(repo, snapshot, before, versions, catalog, history)
                git(repo, 'add', '--', *GENERATED)
                git(repo, 'commit', '-m', '补齐国服数据 ' + version + ' 的后勤技能（保留原标签）')
                return {'version': version, 'created': False, 'enriched': True, 'repo': str(repo)}
        # Do not silently rewrite a published official-version tag.
        raise ValueError(f'官方版本 {version} 已保存，但内容不同。已保留本次临时数据；请核对是否为同号热修，不会覆盖历史标签。')
    if versions and tuple(map(int, version.split('.'))) < tuple(map(int, versions[-1].split('.'))):
        raise ValueError('当前游戏版本早于仓库最新版本，请先完成游戏更新。')
    before = load_snapshot(repo, versions[-1]) if versions else None
    with tempfile.TemporaryDirectory(prefix='arknights-snapshot-') as tmp:
        tree = Path(tmp)
        catalog = read_json(repo / 'version-info.json') if (repo / 'version-info.json').exists() else {}
        history = read_json(repo / 'base-skills-history.json') if (repo / 'base-skills-history.json').exists() else {}
        write_tree(tree, snapshot, before, versions + [version], catalog, history)
        for name in GENERATED:
            target = repo / name
            source = tree / name
            if source.is_dir():
                # Only stale, tracked data files in our two generated directories may be removed.
                target.mkdir(exist_ok=True)
                for old in target.glob('*.json'):
                    if not (source / old.name).exists():
                        old.unlink()
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copyfile(source, target)
    git(repo, 'add', '--', *GENERATED)
    git(repo, 'commit', '-m', '国服数据 ' + version)
    git(repo, 'tag', version)
    return {'version': version, 'created': True, 'repo': str(repo), 'changes': compare(before, snapshot)}


def save_run(run, repo):
    return save_snapshot(repo, snapshot_from_run(run))
