import json
import struct
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common import DEFAULT_GAME,read_json,write_json
from decode import Reader
from export_excel import Excel,defined
from pipeline import Pipeline,Cancelled,check_client
from openpyxl import load_workbook


class IntegrityTests(unittest.TestCase):
    def test_unknown_binary_fields_are_rejected(self):
        # Root at 12, vtable at 4. Two present scalar slots; schema knows one.
        data=struct.pack('<IHHHHiII',12,8,12,4,8,8,42,99)
        nodes={'root':{'kind':'table','fields':[{'name':'x','type':'int','id':0}]},'int':{'kind':'scalar','scalar':'int'}}
        with self.assertRaisesRegex(ValueError,'未知'):Reader(data,nodes).root('root')

    def test_truncated_pointer_is_rejected(self):
        nodes={'root':{'kind':'table','fields':[]}}
        with self.assertRaises(ValueError):Reader(b'\xff'*4,nodes).root('root')

    def test_changed_client_is_rejected(self):
        if not DEFAULT_GAME.exists():self.skipTest('Local integration fixture not installed')
        with patch('pipeline.sha256',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'尚未适配'):check_client(DEFAULT_GAME)

    def test_failure_keeps_previous_success_and_creates_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d);write_json(output/'latest.json',{'folder':'previous'})
            p=Pipeline(DEFAULT_GAME,emit=lambda s:None,output=output)
            with patch.object(p,'work',side_effect=ValueError('incompatible layout')):
                with self.assertRaises(ValueError):p.run()
            self.assertEqual(read_json(output/'latest.json'),{'folder':'previous'})
            with zipfile.ZipFile(p.run_dir/'诊断包.zip') as z:
                report=json.loads(z.read('failure.json'))
                self.assertEqual(report['error'],'incompatible layout')

    def test_cancel_stops_child_and_keeps_previous_success(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d);write_json(output/'latest.json',{'folder':'previous'})
            p=Pipeline(DEFAULT_GAME,emit=lambda s:None,output=output)
            def work():
                p.step('cancel test')
                timer=threading.Timer(.4,p.cancel.set);timer.start()
                try:p.command([sys.executable,'-c','import time; time.sleep(30)'],timeout=10)
                finally:timer.cancel()
            with patch.object(p,'work',side_effect=work):
                with self.assertRaises(Cancelled):p.run()
            self.assertEqual(read_json(output/'latest.json'),{'folder':'previous'})

    def test_excel_preserves_literal_text_and_chinese(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.xlsx';e=Excel(p);s=e.sheet('数据',['名称','值'])
            e.row(s,['阿米娅','=1+1']);e.save()
            wb=load_workbook(p);self.assertEqual(wb.active['A2'].value,'阿米娅')
            self.assertEqual(wb.active['B2'].value,'=1+1');self.assertEqual(wb.active['B2'].data_type,'s');wb.close()

    def test_undefined_enemy_values_are_not_zero(self):
        self.assertIsNone(defined({'m_defined':False,'m_value':0}))
        self.assertEqual(defined({'m_defined':True,'m_value':0}),0)


if __name__=='__main__':unittest.main()
