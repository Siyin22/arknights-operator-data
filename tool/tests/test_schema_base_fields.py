import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import schema


class GenericParentSlotTests(unittest.TestCase):
    def generate(self, *, offset='0x0', reads=(0, 1), mapped_id=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'types.json').write_text('[]')
            class FakeBuilder:
                types = {}
                nodes = {'Room': {'kind': 'table', 'fields': [
                    {'source_name': 'speed', 'id': 0, 'offset': '0x18'},
                    {'source_name': 'phases', 'id': 1, 'offset': offset}]}}
                def __init__(self, types): pass
                def build(self, name): pass
                def fbs(self, name): return ''
            result = {'Room': {'status': 'mapped', 'mappings': [{'field': 'speed', 'id': mapped_id}],
                               'reads': [{'id': i} for i in reads]}}
            with patch.object(schema, 'Builder', FakeBuilder), patch.object(schema, 'ROOTS', {'room': 'Room'}), \
                    patch('audit.run', return_value=result), patch.object(sys, 'argv', [
                        'schema.py', str(root / 'types.json'), str(root / 'out'), '--binary', 'unused.dll']):
                schema.main()
            return json.loads((root / 'out/schema.json').read_text())['nodes']['Room']

    def test_generic_placeholder_offsets_are_only_partially_verified(self):
        node = self.generate()
        self.assertTrue(node['native_partial'])
        self.assertNotIn('native_verified', node)
        self.assertEqual([f['id'] for f in node['fields']], [0, 1])

    def test_non_placeholder_missing_and_conflicting_slots_still_fail(self):
        for args in ({'offset': '0x10'}, {'reads': (0, 2)}, {'mapped_id': 1}, {'offset': None}):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'Incomplete native slot recovery'):
                self.generate(**args)


if __name__ == '__main__':
    unittest.main()
