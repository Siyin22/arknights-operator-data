import copy
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common import read_json, write_json
from export_updates import build_report, export, render_html, select_baseline
from operator_details import candidate, description, max_attributes


def character(name='测试干员'):
    return {'name': name, 'rarity': 5, 'profession': 1, 'subProfessionId': 'guard', 'isNotObtainable': False,
            'description': '阻挡两个敌人', 'phases': [
                {'maxLevel': 50, 'attributesKeyFrames': [{'level': 50, 'data': {'maxHp': 1000, 'atk': 200}}]},
                {'maxLevel': 90, 'attributesKeyFrames': [{'level': 1, 'data': {'atk': 300}},
                                                       {'level': 90, 'data': {'maxHp': 2000, 'atk': 500}}]}],
            'favorKeyFrames': [{'level': 0, 'data': {'atk': 0}}, {'level': 50, 'data': {'atk': 100}}],
            'potentialRanks': [{'description': '攻击力+25', 'buff': {'attributes': {'attributeModifiers': [
                {'attributeType': 1, 'formulaItem': 0, 'value': 25}]}}}],
            'skills': [{'skillId': 'skill_test'}], 'talents': []}


def module(owner, tmpl=None, badge=False):
    return {'charId': owner, 'tmplId': tmpl, 'type': 0 if badge else 1, 'uniEquipName': '测试模组',
            'typeName1': 'TEST', 'typeName2': 'X', 'unlockEvolvePhase': 1, 'unlockLevel': 60}


def snapshot(root, name, version, chars=None, equips=None, patch=None, success=True):
    run = root / name
    write_json(run / 'raw/version.json', {'versionId': version})
    (run / 'raw/excel').mkdir()
    (run / 'raw/excel/data_version.txt').write_text(version, encoding='utf-8')
    if success:
        write_json(run / 'success.json', {'completed_at': name})
    write_json(run / 'json/character_table.json', chars or {})
    write_json(run / 'json/char_patch_table.json', {'patchChars': patch or {}})
    write_json(run / 'json/building_data.json', {'rooms': {}, 'buffs': {},
               'chars': {cid: {'buffChar': []} for cid in {**(chars or {}), **(patch or {})}}})
    write_json(run / 'json/uniequip_table.json', {'equipDict': equips or {}, 'subProfDict': {'guard': {'subProfessionName': '测试分支'}}})
    write_json(run / 'json/skill_table.json', {'skill_test': {'levels': [
        {'name': '测试技能', 'description': '攻击提升{atk:0%}', 'blackboard': [{'key': 'atk', 'value': i / 10}],
         'duration': 20, 'skillType': 1, 'spData': {'spType': 1, 'spCost': 30, 'initSp': 10}}
        for i in range(1, 11)]}})
    write_json(run / 'json/battle_equip_table.json', {eid: {'phases': [
        {'equipLevel': level, 'attributeBlackboard': [{'key': 'atk', 'value': level * 10}], 'parts': [
            {'overrideTraitDataBundle': {'candidates': [
                {'requiredPotentialRank': 0, 'additionalDescription': '攻击提升{atk:0%}', 'blackboard': [{'key': 'atk', 'value': .1}]},
                {'requiredPotentialRank': 1, 'additionalDescription': '攻击提升{atk:0%}', 'blackboard': [{'key': 'atk', 'value': .2}]}]}}]}
        for level in range(1, 4)]} for eid, e in (equips or {}).items() if e['type'] != 0})
    return run


class UpdateTests(unittest.TestCase):
    def test_first_export_is_baseline_not_all_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = snapshot(Path(tmp), '01', 'v1', {'char_a': character()})
            summary = export(run)
            self.assertEqual(summary['status'], 'baseline')
            self.assertIsNone(summary['new_operators'])
            self.assertEqual(read_json(run / 'update-report.json')['operators'], [])
            self.assertIn('等待下一次版本更新', (run / '更新报告.html').read_text(encoding='utf-8'))

    def test_repeat_version_uses_previous_distinct_success_and_ignores_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = snapshot(root, '01', 'v1')
            snapshot(root, '02', 'v2', success=False)
            snapshot(root, '03', 'v2')
            current = snapshot(root, '04', 'v2')
            snapshot(root, '05', 'v3')
            self.assertEqual(select_baseline(current), old)

    def test_same_version_without_previous_version_stays_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot(root, '01', 'v1')
            current = snapshot(root, '02', 'v1')
            self.assertIsNone(select_baseline(current))

    def test_additions_join_existing_owners_and_patch_forms_excluding_badges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = character('老干员')
            hidden = character('预装干员'); hidden['isNotObtainable'] = True
            old = snapshot(root, '01', 'v1', {'char_old': original, 'char_hidden': hidden}, {'module_old': module('char_old')})
            changed = copy.deepcopy(original); changed['description'] = '已有干员改动'
            new = character('<新干员>')
            current = snapshot(root, '02', 'v2', {'char_old': changed, 'char_new': new, 'char_hidden': character('预装干员')},
                {'module_old': module('char_old'), 'module_new': module('char_old'),
                 'badge': module('char_new', badge=True), 'module_form': module('char_old', 'char_form')},
                {'char_form': character('另一职业形态')})
            report = build_report(current, old)
            self.assertEqual(set(report['added_operator_ids']), {'char_new', 'char_hidden', 'char_form'})
            self.assertEqual(set(report['added_module_ids']), {'module_new', 'module_form'})
            self.assertEqual({p['id'] for p in report['module_owners']}, {'char_old', 'char_form'})
            self.assertEqual(report['module_owners'][0]['modules'][0]['levels'][2]['bonuses'][0]['value'], 30)
            self.assertEqual(report['operators'][0]['skills'][0]['levels'][-1]['label'], '专精三')
            rendered = render_html(report)
            self.assertNotIn('<新干员>', rendered)
            self.assertIn('&lt;新干员&gt;', rendered)
            self.assertIn('攻击提升20%', rendered)

    def test_unchanged_export_has_no_additions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = snapshot(root, '01', 'v1', {'char_old': character()}, {'m': module('char_old')})
            current = snapshot(root, '02', 'v2', {'char_old': character()}, {'m': module('char_old')})
            report = build_report(current, old)
            self.assertEqual(report['added_operator_ids'], [])
            self.assertEqual(report['added_module_ids'], [])
            self.assertIn('本次没有新增模组', render_html(report))

    def test_max_level_trust_and_potential_are_additive(self):
        c = character()
        self.assertEqual(max_attributes(c)['atk'], 600)
        self.assertEqual(max_attributes(c, rank=1)['atk'], 625)
        self.assertEqual(max_attributes(c, trust=False)['atk'], 500)

    def test_description_resolves_percent_negative_case_and_linebreak(self):
        text = '<@ba.vup>{ATK:0%}</> / {-def:0%} / {duration:0.0}\\n{missing}'
        rendered = description(text, [{'key': 'atk', 'value': 2.3499999}, {'key': 'def', 'value': -.2}], {'duration': 1.5})
        self.assertEqual(rendered, '235% / 20% / 1.5\n【参数未提供：missing】')

    def test_talent_requires_both_phase_and_potential(self):
        bundle = {'candidates': [
            {'name': '初始', 'unlockCondition': {'phase': 1, 'level': 1}, 'requiredPotentialRank': 0},
            {'name': '精二', 'unlockCondition': {'phase': 2, 'level': 1}, 'requiredPotentialRank': 0},
            {'name': '高潜', 'unlockCondition': {'phase': 2, 'level': 1}, 'requiredPotentialRank': 3}]}
        self.assertEqual(candidate(bundle, 2, 90, 0)['name'], '精二')
        self.assertEqual(candidate(bundle, 2, 90, 5)['name'], '高潜')
        self.assertEqual(candidate(bundle, 1, 80, 5)['name'], '初始')


if __name__ == '__main__':
    unittest.main()
