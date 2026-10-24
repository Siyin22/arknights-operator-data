"""Static x64 IL2CPP method inspection; never executes game code."""
import bisect
import json
import sys
import struct
import re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/python'))
import capstone
import pefile


class Native:
    def __init__(self, binary, types, dump=None):
        self.data=Path(binary).read_bytes()
        self.pe=pefile.PE(data=self.data,fast_load=True)
        directory=self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
        pdata=self.pe.get_offset_from_rva(directory.VirtualAddress)
        self.ranges={a:b for a,b,_ in struct.iter_unpack('<III',self.data[pdata:pdata+directory.Size])}
        self.starts=sorted(self.ranges)
        dump=Path(dump) if dump else Path(__file__).resolve().parents[1]/'work/提取临时/analysis/dump.cs'
        dump_text=dump.read_text(encoding='utf-8-sig')
        self.managed_starts=sorted({int(x,16) for x in re.findall(r'RVA: (0x[0-9A-F]+)',dump_text)})
        self.md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
        self.md.detail=True
        self.methods={int(m['rva'],16):m for t in types for m in t['methods'] if m['rva']}
        for a,name in re.findall(r'\|-RVA: (0x[0-9A-F]+)[^\n]*\n\s*\|-([^\n]+)',dump_text):
            self.methods.setdefault(int(a,16),{'name':name,'signature':name})

    def disasm(self,rva):
        ix=bisect.bisect_right(self.managed_starts,rva)
        end=self.managed_starts[ix] if ix<len(self.managed_starts) else rva+10000
        offset=self.pe.get_offset_from_rva(rva)
        return list(self.md.disasm(self.data[offset:offset+end-rva],rva))


if __name__=='__main__':
    n=Native(sys.argv[1],json.loads(Path(sys.argv[2]).read_text()))
    for arg in sys.argv[3:]:
        for i in n.disasm(int(arg,16)):
            hint=''
            if i.mnemonic in ('call','jmp') and i.operands[0].type==capstone.CS_OP_IMM:
                hint=n.methods.get(i.operands[0].imm,{}).get('signature','')
            print(hex(i.address),i.mnemonic,i.op_str,hint)
