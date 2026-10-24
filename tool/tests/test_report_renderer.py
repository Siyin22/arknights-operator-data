import copy
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from report_renderer import render_report
from version_compare import compare


def payload(before, after):
    page = render_report(before, after, compare(before, after))
    return json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',
                               page, re.S)[1])


class ReportContextTests(unittest.TestCase):
    def sample(self):
        return {'version': {'official_version': '78.2.0'},
                'operators': {'char_a': {'id': 'char_a', 'name': '旧版干员',
                                         'variants': [{'talents': [{'description': '旧天赋'}]}]}},
                'modules': {'module_a': {'id': 'module_a', 'operator_id': 'char_a',
                                         'name': '旧模组'}}}

    def test_removed_module_retains_same_version_baseline_when_owner_changes(self):
        before = self.sample()
        after = copy.deepcopy(before)
        after['version']['official_version'] = '78.3.0'
        after['operators']['char_a']['variants'][0]['talents'][0]['description'] = '新版天赋'
        after['modules'].clear()
        result = payload(before, after)
        module = next(e for e in result['entries'] if e['category'] == 'modules')
        self.assertEqual(module['status'], 'removed')
        self.assertEqual(module['version'], before['version'])
        self.assertEqual(module['operator'], before['operators']['char_a'])
        self.assertNotEqual(module['operator'], after['operators']['char_a'])

    def test_removed_operator_can_export_its_old_modules_even_when_owner_is_gone(self):
        before = self.sample()
        after = {'version': {'official_version': '78.3.0'}, 'operators': {}, 'modules': {}}
        result = payload(before, after)
        operator = next(e for e in result['entries'] if e['category'] == 'operators')
        self.assertEqual(operator['relatedModules'], list(before['modules'].values()))
        self.assertEqual(operator['record'], before['operators']['char_a'])

    def test_context_does_not_create_false_changes_or_mutate_snapshots(self):
        before = self.sample()
        after = copy.deepcopy(before)
        after['version']['official_version'] = '78.3.0'
        after['modules']['module_b'] = {'id': 'module_b', 'operator_id': 'char_a', 'name': '新模组'}
        expected_before, expected_after = copy.deepcopy(before), copy.deepcopy(after)
        result = payload(before, after)
        self.assertEqual([(e['category'], e['id'], e['status']) for e in result['entries']],
                         [('modules', 'module_b', 'added')])
        self.assertEqual(result['difference']['operators']['changed'], [])
        self.assertEqual((before, after), (expected_before, expected_after))


if __name__ == '__main__':
    unittest.main()
