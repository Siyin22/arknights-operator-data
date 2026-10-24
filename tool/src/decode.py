"""Bounded FlatBuffers reader for independently recovered schemas."""
import argparse
import json
import math
import struct
from pathlib import Path

FORMATS={'bool':'?','byte':'b','ubyte':'B','short':'h','ushort':'H','int':'i','uint':'I','long':'q','ulong':'Q','float':'f','double':'d'}


class Reader:
    def __init__(self,data,nodes):
        self.data=data;self.nodes=nodes;self.count=0

    def number(self,fmt,p):
        size=struct.calcsize('<'+fmt)
        if p<0 or p+size>len(self.data): raise ValueError(f'Out of bounds {p}/{len(self.data)}')
        return struct.unpack_from('<'+fmt,self.data,p)[0]

    def indirect(self,p):
        offset=self.number('I',p)
        if offset==0: raise ValueError('Zero relative pointer')
        return p+offset

    def slot(self,pos,index):
        v=pos-self.number('i',pos);size=self.number('H',v);obj=self.number('H',v+2)
        if size<4 or size%2 or v+size>len(self.data) or obj<4 or pos+obj>len(self.data):
            raise ValueError(f'Invalid vtable at {v}')
        offset=self.number('H',v+4+index*2) if 4+index*2<size else 0
        if offset>=obj: raise ValueError('Field outside table')
        return pos+offset if offset else None

    def check_layout(self,pos,field_count):
        self.slot(pos,0)
        v=pos-self.number('i',pos)
        count=(self.number('H',v)-4)//2
        if any(self.number('H',v+4+i*2) for i in range(field_count,count)):
            raise ValueError('发现未知数据字段，需要适配新格式')

    def field(self,name,p,depth):
        n=self.nodes[name];kind=n['kind']
        if kind in ('scalar','enum') and n['scalar']!='string':
            val=self.number(FORMATS[n['scalar']],p) if p is not None else False if n['scalar']=='bool' else 0
            if isinstance(val,float) and not math.isfinite(val): raise ValueError('Non-finite float')
            return val
        if p is None: return None
        target=self.indirect(p)
        if kind=='scalar':
            length=self.number('I',target);start=target+4
            if start+length>=len(self.data) or self.data[start+length]!=0:raise ValueError('Invalid string length/terminator')
            return self.data[start:start+length].decode('utf-8')
        if kind in ('vector','dict'):return self.vector(name,target,depth+1)
        return self.table(name,target,depth+1)

    def vector(self,name,pos,depth):
        n=self.nodes[name];length=self.number('I',pos)
        if length>len(self.data):raise ValueError('Invalid vector length')
        element=self.nodes[n['element']] if n['kind']=='vector' else None
        width=struct.calcsize(FORMATS[element['scalar']]) if element and element['kind'] in ('scalar','enum') and element['scalar']!='string' else 4
        if pos+4+length*width>len(self.data):raise ValueError('Vector outside buffer')
        out=[];result={}
        for i in range(length):
            address=pos+4+i*width
            if n['kind']=='dict':
                entry=self.indirect(address)
                self.check_layout(entry,2)
                key=self.field(n['key'],self.slot(entry,0),depth+1)
                value=self.field(n['value'],self.slot(entry,1),depth+1)
                key=str(key)
                if key in result:raise ValueError('Duplicate dictionary key '+key)
                result[key]=value
            elif element['kind'] in ('vector','dict'):
                out.append(self.table(n['element'],self.indirect(address),depth+1))
            else:out.append(self.field(n['element'],address,depth+1))
        return result if n['kind']=='dict' else out

    def table(self,name,pos,depth=0):
        self.count+=1
        if depth>100 or self.count>10000000:raise ValueError('Decode resource limit')
        n=self.nodes[name]
        if n['kind'] in ('vector','dict'):
            self.check_layout(pos,1)
            p=self.slot(pos,0)
            return self.vector(name,self.indirect(p),depth+1) if p is not None else None
        out={}
        self.check_layout(pos,len(n['fields']))
        for f in n['fields']:
            try:out[f['name']]=self.field(f['type'],self.slot(pos,f['id']),depth+1)
            except Exception as e: raise ValueError(f'{name}.{f["name"]}: {e}') from e
        if n.get('matrix'):
            if len(out['data'] or [])!=out['rows']*out['cols']: raise ValueError('Matrix shape mismatch')
            return [out['data'][i*out['cols']:(i+1)*out['cols']] for i in range(out['rows'])]
        return out

    def root(self,name):return self.table(name,self.number('I',0))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('schema',type=Path);ap.add_argument('raw',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--operators-only',action='store_true')
    a=ap.parse_args();s=json.loads(a.schema.read_text(encoding='utf-8'));a.output.mkdir(parents=True,exist_ok=True)
    results=[]
    for name,root in s['roots'].items():
        if a.operators_only and name not in {'character_table','char_patch_table','skill_table','uniequip_table','battle_equip_table','building_data'}:continue
        if name=='level':paths=[p for p in a.raw.glob('levels/**/*.bytes') if p.name.startswith('level_')]
        else:paths=list(a.raw.rglob(name+'*.bytes'))
        if not paths:raise ValueError('No raw data for '+name)
        if name!='level' and len(paths)!=1:raise ValueError('Ambiguous data files for '+name)
        for index,p in enumerate(sorted(paths)):
            data=p.read_bytes()
            try:out=Reader(data[128:],s['nodes']).root(root)
            except Exception as e:raise ValueError(f'{p}: {e}') from e
            target=a.output/(p.relative_to(a.raw).with_suffix('.json') if name=='level' else Path(name+'.json'))
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            results.append({'root':name,'source':str(p),'output':str(target),'count':len(out) if isinstance(out,(list,dict)) else None})
            if name=='level' and (index+1)%100==0:print(f'关卡解析 {index+1}/{len(paths)}',flush=True)
        print(name,len(paths),'files',flush=True)
    (a.output/'decode-report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
