"""Recover native unpack slot -> managed field mappings for x64 classes."""
import collections
import json
import re
from pathlib import Path
from native import Native,capstone


def recover(native,method,node):
    ins=native.disasm(int(method['rva'],16))
    regs={};reads=[]
    for ix,i in enumerate(ins):
        op=i.operands
        if i.mnemonic=='mov' and len(op)==2 and op[0].type==capstone.CS_OP_REG:
            reg=i.reg_name(op[0].reg)
            if op[1].type==capstone.CS_OP_IMM:regs[reg]=op[1].imm
            else:regs.pop(reg,None)
        if i.mnemonic=='xor' and len(op)==2 and op[0].type==capstone.CS_OP_REG and op[0].reg==op[1].reg:
            regs[i.reg_name(op[0].reg)]=0
        if i.mnemonic=='call' and op[0].type==capstone.CS_OP_IMM:
            target=native.methods.get(op[0].imm,{}).get('signature','')
            if ('FlatStoreUtil' in target and 'Unpack' in target) or 'Table::__offset' in target:
                slot=regs.get('r8d') if '::Unpack(System.Type,' in target else regs.get('edx')
                if slot is not None and slot>=4 and slot%2==0 and slot<2000:
                    reads.append({'index':ix,'id':(slot-4)//2,'call':hex(i.address),'helper':target})
            for reg in ('eax','rax','ecx','rcx','edx','rdx','r8','r8d','r9','r9d'):regs.pop(reg,None)
    fields={int(f['offset'],16):f for f in node['fields'] if f['offset'] is not None}
    groups=collections.defaultdict(list)
    for j,r in enumerate(reads):
        end=reads[j+1]['index'] if j+1<len(reads) else len(ins)
        for i in ins[r['index']+1:end]:
            op=i.operands
            mem=None
            if i.mnemonic.startswith('mov') and len(op)>1 and op[0].type==capstone.CS_OP_MEM:
                mem=op[0].mem
            elif i.mnemonic=='lea' and len(op)>1 and op[1].type==capstone.CS_OP_MEM:
                mem=op[1].mem
            if mem and not mem.index:
                base=i.reg_name(mem.base)
                if base not in ('rsp','rbp','rip') and mem.disp in fields:
                    groups[base].append(dict(r,field=fields[mem.disp]['source_name'],offset=mem.disp,store=hex(i.address)))
    if not groups:return {'status':'unresolved','reads':reads}
    base=max(groups,key=lambda x:len({(a['id'],a['field']) for a in groups[x]}))
    found={}
    for r in groups[base]:
        found.setdefault(r['id'],{})[r['field']]=r
    mappings=[];ambiguous=[]
    for slot,choices in sorted(found.items()):
        if len(choices)==1:mappings.append(next(iter(choices.values())))
        else:ambiguous.append({'id':slot,'fields':list(choices)})
    return {'status':'mapped' if not ambiguous else 'ambiguous','receiver':base,'mappings':mappings,'ambiguous':ambiguous,'reads':reads}


def run(binary,types,nodes,dump=None):
    native=Native(binary,types,dump)
    methods={m['name']:m for t in types if t['name']=='Torappu.FlatBuffers.FlatLookupConverter' for m in t['methods']}
    audit={}
    for name,node in nodes.items():
        if node['kind']!='table':continue
        method=methods.get('Unpack_'+re.sub(r'[./]','_',name))
        if method is None:continue
        result=recover(native,method,node);result['method']=method
        audit[name]=result
    return audit


if __name__=='__main__':
    import sys
    types=json.loads(Path(sys.argv[2]).read_text());schema=json.loads(Path(sys.argv[3]).read_text())
    audit=run(sys.argv[1],types,schema['nodes'])
    Path(sys.argv[4]).write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(collections.Counter(a['status'] for a in audit.values()))
    for name,a in audit.items():
        n=schema['nodes'][name]
        mapped={m['field']:m['id'] for m in a.get('mappings',[])}
        mismatch=[(f['source_name'],f['id'],mapped[f['source_name']]) for f in n['fields'] if f['source_name'] in mapped and mapped[f['source_name']]!=f['id']]
        missing=[f['source_name'] for f in n['fields'] if f['source_name'] not in mapped]
        if mismatch or missing:print(name,'mismatch',mismatch,'missing',missing,'ambiguous',a.get('ambiguous'))
