"""Cross-check generated FBS with the official flatc on actual game buffers."""
import argparse
import json
import math
import subprocess
import os
from pathlib import Path
from decode import Reader


def normalize(nodes,name,value,wrapped=False):
    n=nodes[name];k=n['kind']
    if wrapped and k in ('vector','dict'):value=value.get('values')
    if value is None:return None
    if k=='enum':
        if isinstance(value,str):
            if value=='_ZERO':return 0
            if value in n['values']:return n['values'][value]
            return sum(n['values'][v] for v in value.split())
        return value
    if k=='vector':return [normalize(nodes,n['element'],v,True) for v in value]
    if k=='dict':return {str(normalize(nodes,n['key'],e.get('key'))):normalize(nodes,n['value'],e.get('value')) for e in value}
    if k=='table':
        out={f['name']:normalize(nodes,f['type'],value.get(f['name'])) for f in n['fields']}
        if n.get('matrix'):
            return [out['data'][i*out['cols']:(i+1)*out['cols']] for i in range(out['rows'])]
        return out
    return value


def equal(a,b,path=''):
    if isinstance(a,float) or isinstance(b,float):
        if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-7):raise ValueError(f'Float mismatch {path}: {a}, {b}')
    elif isinstance(a,dict):
        if not isinstance(b,dict) or a.keys()!=b.keys():raise ValueError('Key mismatch '+path)
        for k in a:equal(a[k],b[k],path+'/'+k)
    elif isinstance(a,list):
        if not isinstance(b,list) or len(a)!=len(b):raise ValueError('Length mismatch '+path)
        for i,(x,y) in enumerate(zip(a,b)):equal(x,y,path+'/'+str(i))
    elif a!=b:raise ValueError(f'Mismatch {path}: {a}, {b}')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('flatc',type=Path)
    ap.add_argument('--operators-only',action='store_true')
    a=ap.parse_args();exe=str(a.flatc.resolve());schema=json.loads((a.run/'schemas/schema.json').read_text(encoding='utf-8'))
    out=a.run/'verification';out.mkdir(exist_ok=True);report=[]
    for label,root in schema['roots'].items():
        if a.operators_only and label not in {'character_table','char_patch_table','skill_table','uniequip_table','battle_equip_table','building_data'}:continue
        fbs=a.run/'schemas'/(label+'.fbs')
        subprocess.run([exe,'--binary','--schema','--no-warnings','-o',str(out),str(fbs)],check=True,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if label=='level':
            allpaths=sorted((a.run/'raw/levels').rglob('level_*.bytes'))
            paths=list(dict.fromkeys([allpaths[0],allpaths[-1],*sorted(allpaths,key=lambda p:p.stat().st_size,reverse=True)[:5],*[p for p in allpaths if '/a001/' in p.as_posix()][:3]]))
        else:paths=sorted((a.run/'raw').rglob(label+'*.bytes'))
        if not paths:raise ValueError('Missing verification source: '+label)
        for i,p in enumerate(paths):
            data=p.read_bytes()[128:];raw=out/f'{label}_{i}.bin';raw.write_bytes(data)
            proc=subprocess.run([exe,'--json','--raw-binary','--strict-json','--defaults-json','--natural-utf8','--no-warnings','-o',str(out),str(fbs),'--',str(raw)],capture_output=True,text=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if proc.returncode:raise ValueError(proc.stderr)
            standard=json.loads(raw.with_suffix('.json').read_text(encoding='utf-8'))
            standard=normalize(schema['nodes'],root,standard,True)
            own=Reader(data,schema['nodes']).root(root)
            equal(own,standard)
            report.append({'root':label,'source':str(p),'flatc_and_python_agree':True})
        print(label, len(paths),'flatc checks passed',flush=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
