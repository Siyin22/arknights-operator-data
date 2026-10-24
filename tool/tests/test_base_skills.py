import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from archive_store import save_snapshot, snapshot_from_run, verified_current
from common import write_json
from operator_details import base_skills_for
from version_compare import compare, details_operator, git, load_snapshot
from test_updates import character, snapshot


def building_data():
    return {'rooms': {'TRADING': {'id': 512, 'name': '贸易站'}},
            'chars': {'char_a': {'buffChar': [{'buffData': [
                {'buffId': 'strong', 'cond': {'phase': 2, 'level': 1}},
                {'buffId': 'weak', 'cond': {'phase': 0, 'level': 1}}]}, {'buffData': []}]}},
            'buffs': {'weak': {'buffName': '物流·α', 'roomType': 512, 'description': '效率<@cc.vup>+20%</>'},
                      'strong': {'buffName': '物流专家', 'roomType': 512, 'description': '效率<@cc.vup>+35%</>'}}}


class BaseSkillTests(unittest.TestCase):
    def test_unlocks_upgrade_groups_and_patch_owner(self):
        data = building_data()
        result = base_skills_for('char_a', data, {}, 2, 90)
        self.assertEqual(len(result), 1)
        self.assertEqual([s['name'] for s in result[0]['levels']], ['物流·α', '物流专家'])
        self.assertEqual(result[0]['levels'][-1]['description'], '效率+35%')
        self.assertEqual(result[0]['levels'][-1]['room'], '贸易站')
        self.assertEqual(len(base_skills_for('char_a', data, {}, 0, 50)[0]['levels']), 1)
        patch = {'infos': {'char_a': {'tmplIds': ['char_a', 'char_form']}}}
        self.assertEqual(base_skills_for('char_form', data, patch, 2, 90), result)
        # An alter with a similar name must not inherit another operator's skills.
        with self.assertRaisesRegex(ValueError, '缺少干员'):
            base_skills_for('char_alter', data, patch, 2, 90)

    def test_unknown_facility_or_missing_buff_fails(self):
        data = building_data()
        data['buffs']['strong']['roomType'] = 999
        with self.assertRaisesRegex(ValueError, '未知后勤技能设施'):
            base_skills_for('char_a', data, {}, 2, 90)
        del data['buffs']['strong']
        with self.assertRaises(KeyError):
            base_skills_for('char_a', data, {}, 2, 90)

    def sample(self, root):
        run = snapshot(root, 'run', 'same-resource', {'char_a': character()})
        (run / 'raw/excel/data_version.txt').write_text('VersionControl:78.2.0', encoding='utf-8')
        write_json(run / 'json/building_data.json', building_data())
        return snapshot_from_run(run)

    def test_backfill_keeps_tag_and_does_not_create_fake_game_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'; enriched = self.sample(root)
            old = copy.deepcopy(enriched)
            old['operators']['char_a'].pop('baseSkills')
            save_snapshot(repo, old)
            tag = git(repo, 'rev-parse', '78.2.0')
            self.assertTrue(save_snapshot(repo, enriched)['enriched'])
            self.assertEqual(git(repo, 'rev-parse', '78.2.0'), tag)
            self.assertNotIn('baseSkills', git(repo, 'show', '78.2.0:operators/char_a.json'))
            self.assertEqual(load_snapshot(repo, '78.2.0'), enriched)
            self.assertEqual(verified_current(repo), enriched)
            self.assertFalse(save_snapshot(repo, enriched)['created'])
            # Later changes to base skills are ordinary data changes; the old supplement survives.
            later = copy.deepcopy(enriched)
            later['version']['official_version'] = '78.3.0'
            later['operators']['char_a']['baseSkills'][0]['levels'][0]['description'] = '效率+25%'
            save_snapshot(repo, later)
            before = load_snapshot(repo, '78.2.0')
            self.assertEqual(before, enriched)
            self.assertEqual(compare(before, later)['operators']['changed'], ['char_a'])
            self.assertEqual(verified_current(repo), later)

    def test_backfill_cannot_hide_a_hotfix_or_rewrite_recorded_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root / 'repo'; enriched = self.sample(root)
            old = copy.deepcopy(enriched); old['operators']['char_a'].pop('baseSkills')
            save_snapshot(repo, old)
            for field in ('battle', 'resource'):
                changed = copy.deepcopy(enriched)
                if field == 'battle': changed['operators']['char_a']['name'] = '被修改'
                else: changed['version']['resource_version'] = 'another-resource'
                with self.assertRaisesRegex(ValueError, '内容不同'):
                    save_snapshot(repo, changed)
            save_snapshot(repo, enriched)
            changed = copy.deepcopy(enriched)
            changed['operators']['char_a']['baseSkills'] = []
            with self.assertRaisesRegex(ValueError, '内容不同'):
                save_snapshot(repo, changed)

    def test_markdown_and_missing_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = self.sample(root)
            operator = data['operators']['char_a']
            output = '\n'.join(details_operator(operator))
            self.assertIn('#### 后勤技能', output)
            self.assertIn('贸易站', output)
            self.assertIn('效率+20%', output)
            (root / 'run/json/building_data.json').unlink()
            with self.assertRaisesRegex(ValueError, '后勤技能数据'):
                snapshot_from_run(root / 'run')


if __name__ == '__main__':
    unittest.main()
