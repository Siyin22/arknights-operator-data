"""Readable battle details used by the incremental update report."""
import re

from common import read_json
from export_excel import PROF, SKILL_TYPE, SP_TYPE

ATTRS = {'maxHp': '生命上限', 'atk': '攻击', 'def': '防御', 'magicResistance': '法术抗性',
         'cost': '部署费用', 'blockCnt': '阻挡数', 'baseAttackTime': '基础攻击间隔',
         'respawnTime': '再部署时间', 'attackSpeed': '攻击速度'}
BOARD_ATTRS = dict(zip(('max_hp', 'atk', 'def', 'magic_resistance', 'cost', 'block_cnt',
                       'base_attack_time', 'respawn_time', 'attack_speed'), ATTRS))
POT_ATTRS = {0: 'maxHp', 1: 'atk', 2: 'def', 3: 'magicResistance', 4: 'cost',
             5: 'blockCnt', 7: 'attackSpeed', 8: 'baseAttackTime', 21: 'respawnTime'}


def number(value):
    return f'{round(value, 5):g}'


def description(text, board=None, extra=None):
    """Resolve game placeholders without evaluating expressions or trusting markup."""
    values = {v['key'].lower(): v.get('valueStr') if v.get('valueStr') is not None else v.get('value')
              for v in board or []}
    values.update(extra or {})

    def replace(match):
        key, _, fmt = match[1].partition(':')
        key = key.lower()
        sign = -1 if key.startswith('-') else 1
        value = values.get(key.lstrip('-+'))
        if value is None:
            return '【参数未提供：' + key + '】'
        if isinstance(value, str):
            return value
        value *= sign
        if fmt:
            percent = fmt.endswith('%')
            places = len(fmt.rstrip('%').partition('.')[2])
            return f'{value * (100 if percent else 1):.{places}f}' + ('%' if percent else '')
        return number(value)

    text = re.sub(r'<[^>]*>', '', text or '').replace('\\n', '\n')
    return re.sub(r'\{([^{}]+)\}', replace, text).strip()


def candidate(bundle, phase, level, rank):
    eligible = []
    for c in (bundle or {}).get('candidates') or []:
        cond = c.get('unlockCondition') or {}
        if ((cond.get('phase', 0), cond.get('level', 1)) <= (phase, level)
                and c.get('requiredPotentialRank', 0) <= rank):
            eligible.append(c)
    return max(eligible, key=lambda c: ((c.get('unlockCondition') or {}).get('phase', 0),
               (c.get('unlockCondition') or {}).get('level', 1), c.get('requiredPotentialRank', 0)), default={})


def max_attributes(char, rank=0, trust=True):
    phase = char['phases'][-1]
    frame = max(phase['attributesKeyFrames'], key=lambda x: x['level'])
    if frame['level'] != phase['maxLevel']:
        raise ValueError(f"{char['name']} 缺少满级属性关键帧")
    attrs = {k: frame['data'].get(k, 0) for k in ATTRS}
    favor = max(char.get('favorKeyFrames') or [{'level': 0, 'data': {}}], key=lambda x: x['level'])['data']
    if trust:
        for k in attrs:
            attrs[k] += favor.get(k, 0)
    for p in (char.get('potentialRanks') or [])[:rank]:
        for m in ((p.get('buff') or {}).get('attributes') or {}).get('attributeModifiers') or []:
            key = POT_ATTRS.get(m['attributeType'])
            if key is None or m['formulaItem'] != 0 or m.get('loadFromBlackboard'):
                raise ValueError(f"{char['name']} 存在尚未支持的潜能属性公式")
            attrs[key] += m['value']
    return {k: round(v, 5) for k, v in attrs.items()}


def skills_for(char, skills):
    result = []
    for index, ref in enumerate(char.get('skills') or [], 1):
        sid = ref.get('skillId')
        if not sid:
            continue
        source = skills[sid]['levels']
        levels = []
        # Normal operators: level 7 and masteries. Low-rarity skills: highest level only.
        for i in range(min(6, len(source) - 1), len(source)):
            s = source[i]
            sp = s.get('spData') or {}
            duration = s.get('duration', 0)
            duration_text = ('弹药制（见描述）' if s.get('durationType') == 1 else
                             '无限持续' if duration < 0 else number(duration) + ' 秒' if duration > 0 else
                             '被动' if s.get('skillType') == 0 else '即时 / 见描述')
            levels.append({'label': f'{i + 1}级' if i < 7 else '专精' + '一二三'[i - 7],
                           'description': description(s.get('description'), s.get('blackboard'), {'duration': duration}),
                           'trigger': SKILL_TYPE.get(s.get('skillType'), '未知触发方式'),
                           'recovery': SP_TYPE.get(sp.get('spType'), '特殊回复'),
                           'cost': sp.get('spCost', 0), 'initial': sp.get('initSp', 0),
                           'charges': sp.get('maxChargeTime', 1), 'duration': duration_text})
        result.append({'name': source[-1]['name'], 'index': index, 'levels': levels})
    return result


def bonuses(board):
    return [{'key': BOARD_ATTRS.get(v['key']), 'label': ATTRS.get(BOARD_ATTRS.get(v['key']), v['key']),
             'value': round(v['value'], 5)} for v in board or [] if v.get('value') is not None]


def module_effects(parts, phase, level, rank):
    result = []
    for part in parts:
        conditions = []
        for key in ('validInGameTag', 'validInMapTag'):
            tag = part.get(key)
            if tag:
                conditions.append({'roguelike': '集成战略', 'sandbox': '生息演算'}.get(str(tag), str(tag)))
        if part.get('isToken'):
            conditions.append('作用于召唤物')
        for field, label in [('overrideTraitDataBundle', '特性'), ('addOrOverrideTalentDataBundle', '天赋')]:
            bundle = part.get(field) or {}
            # Keep distinct talent/mode groups; potential variants within a group replace one another.
            groups = {}
            for c in bundle.get('candidates') or []:
                group = (c.get('talentIndex'), c.get('prefabKey'), tuple(c.get('validModeIndices') or []))
                groups.setdefault(group, []).append(c)
            for group in groups.values():
                c = candidate({'candidates': group}, phase, level, rank)
                pieces = [description(c.get(k), c.get('blackboard')) for k in
                          ('overrideDescripton', 'additionalDescription', 'upgradeDescription', 'description') if c.get(k)]
                if not pieces:
                    continue
                mode = c.get('validModeIndices')
                context = conditions + ([f'形态条件：{mode}'] if mode else [])
                result.append({'name': c.get('name') or label,
                               'description': '\n'.join(dict.fromkeys(pieces)), 'condition': ' · '.join(context)})
    return result


def base_skills_for(cid, building, patch, phase, level):
    owner = cid
    if owner not in building['chars']:
        # Alternate professions share the owner's base skills, not the skills of a namesake alter.
        owner = next((key for key, info in (patch.get('infos') or {}).items()
                      if cid in (info.get('tmplIds') or [])), cid)
    if owner not in building['chars']:
        raise ValueError('缺少干员后勤技能配置：' + cid)
    rooms = {room['id']: room['name'] for room in building['rooms'].values()}
    groups = []
    for group in building['chars'][owner].get('buffChar') or []:
        levels = []
        for ref in sorted(group.get('buffData') or [], key=lambda r: (r['cond']['phase'], r['cond']['level'])):
            buff = building['buffs'][ref['buffId']]
            cond = ref['cond']
            if (cond['phase'], cond['level']) > (phase, level):
                continue
            room = rooms.get(buff['roomType'])
            if not room:
                raise ValueError('未知后勤技能设施：' + str(buff['roomType']))
            levels.append({'id': ref['buffId'], 'name': buff['buffName'], 'room': room,
                           'unlock': '初始解锁' if cond == {'phase': 0, 'level': 1} else
                                     f"精英{cond['phase']} · {cond['level']}级",
                           'phase': cond['phase'], 'level': cond['level'],
                           'description': description(buff['description'])})
        if levels:
            groups.append({'levels': levels})
    return groups


def build_profiles(source, operator_ids=None, module_ids=None):
    chars = read_json(source / 'character_table.json')
    patch = read_json(source / 'char_patch_table.json')
    chars.update(patch.get('patchChars') or {})
    building = read_json(source / 'building_data.json') if (source / 'building_data.json').exists() else None
    skills = read_json(source / 'skill_table.json')
    equips = read_json(source / 'uniequip_table.json')
    battles = read_json(source / 'battle_equip_table.json')
    by_char = {}
    for eid, equip in equips['equipDict'].items():
        if equip.get('type') == 0:
            continue  # Original class badges are not upgrade modules.
        by_char.setdefault(equip.get('tmplId') or equip['charId'], []).append((eid, equip))
    profiles = []
    for cid, c in chars.items():
        if not cid.startswith('char_') or c.get('isNotObtainable') or not c.get('phases'):
            continue
        if operator_ids is not None and cid not in operator_ids:
            continue
        phase, level = len(c['phases']) - 1, c['phases'][-1]['maxLevel']
        variants = []
        for rank in range(len(c.get('potentialRanks') or []) + 1):
            trait = candidate(c.get('trait'), phase, level, rank)
            talents = []
            for bundle in c.get('talents') or []:
                t = candidate(bundle, phase, level, rank)
                if t and not t.get('isHideTalent') and t.get('description'):
                    talents.append({'name': t.get('name') or '天赋', 'description': description(t['description'], t.get('blackboard'))})
            variants.append({'stats': max_attributes(c, rank), 'talents': talents,
                             'trait': description(trait.get('overrideDescripton') or c.get('description'), trait.get('blackboard'))})
        modules = []
        for eid, e in by_char.get(cid, []):
            if module_ids is not None and eid not in module_ids:
                continue
            levels = []
            for p in (battles.get(eid) or {}).get('phases') or []:
                levels.append({'level': p['equipLevel'], 'bonuses': bonuses(p.get('attributeBlackboard')),
                               'tokenBonuses': [{'name': (chars.get(tid) or {}).get('name', tid), 'bonuses': bonuses(bb)}
                                                for tid, bb in (p.get('tokenAttributeBlackboard') or {}).items()],
                               'effects': [module_effects(p.get('parts') or [], phase, level, rank) for rank in range(len(variants))]})
            modules.append({'id': eid, 'name': e['uniEquipName'], 'type': '-'.join(filter(None, [e.get('typeName1'), e.get('typeName2')])),
                            'unlock': f"精英{e.get('unlockEvolvePhase', 2)} · {e.get('unlockLevel', 0)}级",
                            'special': description(e.get('specialEquipDesc')), 'levels': levels})
        tokens = []
        token_ids = set((c.get('displayTokenDict') or {}).keys())
        token_ids.update(s['overrideTokenKey'] for s in c.get('skills') or [] if s.get('overrideTokenKey'))
        for tid in sorted(token_ids):
            t = chars.get(tid)
            if t and t.get('phases'):
                tokens.append({'name': t['name'], 'stats': max_attributes(t, trust=False),
                               'trait': description(t.get('description')), 'skills': skills_for(t, skills)})
        sub = (equips['subProfDict'].get(c.get('subProfessionId')) or {}).get('subProfessionName', c.get('subProfessionId'))
        profiles.append({'id': cid, 'name': c['name'], 'english': c.get('appellation') or '',
                         'rarity': c['rarity'] + 1, 'profession': PROF.get(c['profession'], str(c['profession'])),
                         'branch': sub, 'phase': phase, 'level': level, 'tags': c.get('tagList') or [],
                         'position': {1: '近战位', 2: '远程位', 3: '近战 / 远程位'}.get(c.get('position'), ''),
                         'sort': c.get('sortIndex', 0), 'variants': variants,
                         'potential': [description(p.get('description')) for p in c.get('potentialRanks') or []],
                         'skills': skills_for(c, skills), 'modules': modules, 'tokens': tokens})
        if building is not None:
            profiles[-1]['baseSkills'] = base_skills_for(cid, building, patch, phase, level)
    return sorted(profiles, key=lambda p: (-p['rarity'], -p['sort'], p['id']))
