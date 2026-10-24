import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from version_compare import potential_details


class PotentialReportTests(unittest.TestCase):
    def test_each_talent_enhancement_uses_its_previous_potential(self):
        first = {'name': '第一天赋', 'description': '攻击力135%'}
        first_up = {'name': '第一天赋', 'description': '攻击力150%（+15%）'}
        second = {'name': '第二天赋', 'description': '减伤30%'}
        second_up = {'name': '第二天赋', 'description': '减伤35%（+5%）'}
        p = {'potential': ['第一天赋效果增强', '攻击速度+8', '第二天赋效果增强'],
             'variants': [{'talents': t} for t in (
                 [first, second], [first_up, second],
                 [first_up, second], [first_up, second_up])]}
        self.assertEqual(potential_details(p), [
            '第一天赋（提升后）：攻击力150%（+15%）', '攻击速度+8',
            '第二天赋（提升后）：减伤35%（+5%）'])

    def test_renamed_and_new_talents_are_preserved(self):
        p = {'potential': ['天赋效果加强'], 'variants': [
            {'talents': [{'name': '救援喷雾·I', 'description': '恢复200点生命'}]},
            {'talents': [{'name': '救援喷雾·II', 'description': '恢复260点生命'},
                         {'name': '额外效果', 'description': '新效果'}]}]}
        self.assertEqual(potential_details(p), [
            '救援喷雾·II（提升后）：恢复260点生命；额外效果（提升后）：新效果'])

    def test_unavailable_or_unchanged_data_keeps_original_label(self):
        self.assertEqual(potential_details({'potential': ['天赋效果增强']}), ['天赋效果增强'])
        self.assertEqual(potential_details({'potential': ['天赋效果增强'],
                                            'variants': [{'talents': []}] * 2}), ['天赋效果增强'])
        self.assertEqual(potential_details({'potential': []}), [])


if __name__ == '__main__':
    unittest.main()
