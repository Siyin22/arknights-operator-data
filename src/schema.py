"""Build schemas from local IL2CPP types, never from OpenArknightsFBS."""
import argparse
import hashlib
import json
import re
from pathlib import Path

PRIMITIVES = dict(zip(
    ('Boolean','SByte','Byte','Int16','UInt16','Int32','UInt32','Int64','UInt64','Single','Double','String'),
    ('bool','byte','ubyte','short','ushort','int','uint','long','ulong','float','double','string')))
ROOTS = {
    'character_table':'System.Collections.Generic.Dictionary`2<System.String,Torappu.CharacterData>',
    'token_table':'System.Collections.Generic.Dictionary`2<System.String,Torappu.CharacterData>',
    'skill_table':'System.Collections.Generic.Dictionary`2<System.String,Torappu.SkillDataBundle>',
    'uniequip_table':'Torappu.UniEquipTable',
    'battle_equip_table':'System.Collections.Generic.Dictionary`2<System.String,Torappu.BattleEquipPack>',
    'char_patch_table':'Torappu.CharPatchData',
    'building_data':'Torappu.BuildingData',
    'char_meta_table':'Torappu.CharMetaTable',
    'char_master_table':'System.Collections.Generic.Dictionary`2<System.String,Torappu.CharacterData/MasterDataBundle>',
    'enemy_handbook_table':'Torappu.EnemyHandBookDataGroup',
    'enemy_database':'Torappu.EnemyDatabase',
    'stage_table':'Torappu.StageTable',
    'level':'Torappu.LevelData',
}


def generic(name):
    if '<' not in name:
        return name, []
    base, rest = name.split('<',1)
    args, start, depth = [], 0, 0
    rest = rest[:-1]
    for i, c in enumerate(rest):
        if c == '<': depth += 1
        if c == '>': depth -= 1
        if c == ',' and depth == 0:
            args.append(rest[start:i]); start = i+1
    args.append(rest[start:])
    return base, args


def substitute(name, bindings):
    if name in bindings: return bindings[name]
    if name.endswith('[]'): return substitute(name[:-2],bindings)+'[]'
    base, args = generic(name)
    return base+'<'+','.join(substitute(a,bindings) for a in args)+'>' if args else name


def attr(item, suffix):
    return next((a for a in item['attrs'] if a['name'].endswith('.'+suffix)),None)


class Builder:
    def __init__(self, types):
        self.types = {t['name']:t for t in types}
        self.nodes = {}

    def collection(self, name, seen=None):
        if name.endswith('[]'): return 'vector',[name[:-2]]
        base, args = generic(name)
        if base in ('System.Collections.Generic.List`1','System.Collections.Generic.HashSet`1'):
            return 'vector',args
        if base in ('System.Collections.Generic.Dictionary`2','Torappu.ListDict`2'):
            return 'dict',args
        if base in self.types:
            t=self.types[base]
            if t['parent'] and t['parent'] not in ('System.Object','System.ValueType','System.Enum'):
                seen=set() if seen is None else seen
                if name in seen: raise ValueError('Cyclic collection inheritance')
                seen.add(name)
                return self.collection(substitute(t['parent'],dict(zip(t['generic'],args))),seen)
        return None

    def fields(self, name):
        base,args=generic(name);t=self.types[base];bindings=dict(zip(t['generic'],args))
        fields=[]
        for f in t['fields']:
            if f['isStatic'] or attr(f,'JsonIgnoreAttribute'): continue
            prop=attr(f,'JsonPropertyAttribute')
            if not f['isPublic'] and not prop: continue
            if attr(f,'NonSerializedAttribute') and not prop: continue
            rename=(prop['args'][0] if prop and prop['args'] else None) or (prop['properties'].get('PropertyName') if prop else None)
            fields.append(dict(f,name=rename or f['name'],source_name=f['name'],type=substitute(f['type'],bindings)))
        if t['parent'] not in (None,'System.Object','System.ValueType','System.Enum'):
            shadowed={f['source_name'] for f in fields}
            fields += [f for f in self.fields(substitute(t['parent'],bindings)) if f['source_name'] not in shadowed]
        return fields

    def build(self,name):
        if name in self.nodes: return name
        self.nodes[name]={'kind':'pending'}
        if name=='System.Int16[,]':
            n={'kind':'table','matrix':True,'fields':[{'name':nm,'type':self.build(tp),'id':i,'offset':None,'attrs':[],'source_name':nm} for i,(nm,tp) in enumerate([('rows','System.Int32'),('cols','System.Int32'),('data','System.Int16[]')])]}
        elif name.startswith('System.') and name[7:] in PRIMITIVES:
            n={'kind':'scalar','scalar':PRIMITIVES[name[7:]]}
        elif name.startswith('CodeStage.AntiCheat.ObscuredTypes.Obscured'):
            suffix=name.split('Obscured')[-1]
            scalar={'Int':'int','Float':'float','Bool':'bool','Long':'long','Double':'double','String':'string'}.get(suffix)
            if not scalar: raise ValueError('Unsupported obscured primitive '+name)
            n={'kind':'scalar','scalar':scalar}
        elif (c:=self.collection(name)):
            kind,args=c
            if kind=='vector': n={'kind':'vector','element':self.build(args[0])}
            else: n={'kind':'dict','key':self.build(args[0]),'value':self.build(args[1])}
        else:
            base,args=generic(name);t=self.types[base]
            if t['kind']=='enum':
                n={'kind':'enum','scalar':PRIMITIVES[next(f['type'][7:] for f in t['fields'] if f['name']=='value__')],
                   'values':{f['name']:f['constant'] for f in t['fields'] if f['constant'] is not None}}
            else:
                fields=self.fields(name)
                # KeyValuePair's private fields are exposed by its properties.
                if base=='System.Collections.Generic.KeyValuePair`2':
                    fields=[{'name':'key','type':args[0],'source_name':'key','offset':None,'attrs':[]},
                            {'name':'value','type':args[1],'source_name':'value','offset':None,'attrs':[]}]
                n={'kind':'table','fields':[{'name':f['name'],'source_name':f['source_name'],
                    'type':self.build(f['type']),'id':i,'offset':f['offset'],'attrs':f['attrs']} for i,f in enumerate(fields)]}
        self.nodes[name]=n
        return name

    def fbs(self,root):
        definitions={}
        def ident(n):
            return re.sub(r'[^A-Za-z0-9_]','_',n)[:120]+'_'+hashlib.sha256(n.encode()).hexdigest()[:8]
        def typ(n, nested=False):
            node=self.nodes[n];kind=node['kind'];key=ident(n)
            if kind=='scalar': return node['scalar']
            if kind=='enum':
                if key not in definitions:
                    vals={}
                    for name,value in node['values'].items(): vals.setdefault(value,name)
                    if 0 not in vals: vals[0]='_ZERO'
                    definitions[key]='enum '+key+' : '+node['scalar']+' {\n'+''.join(f'  {v} = {k},\n' for k,v in sorted(vals.items()))+'}\n'
                return key
            if kind in ('vector','dict'):
                if kind=='vector': v='['+typ(node['element'],True)+']'
                else:
                    entry=key+'_Entry'
                    if entry not in definitions:
                        definitions[entry]=''
                        definitions[entry]=f'table {entry} {{\n  key:{typ(node["key"])} (id:0);\n  value:{typ(node["value"])} (id:1);\n}}\n'
                    v='['+entry+']'
                if not nested: return v
                if key not in definitions: definitions[key]=f'table {key} {{\n  values:{v} (id:0);\n}}\n'
                return key
            if key not in definitions:
                definitions[key]=''
                body=''.join(f'  {f["name"]}:{typ(f["type"])} (id:{f["id"]});\n' for f in node['fields'])
                definitions[key]=f'table {key} {{\n{body}}}\n'
            return key
        rt=typ(root,True)
        ordered=sorted(definitions.values(),key=lambda d:0 if d.startswith('enum ') else 1)
        return '// Generated from local client metadata. See schema.json and native-audit.json.\n\n'+'\n'.join(ordered)+f'\nroot_type {rt};\n'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('types',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--binary',type=Path);ap.add_argument('--dump',type=Path)
    a=ap.parse_args();b=Builder(json.loads(a.types.read_text(encoding='utf-8')))
    a.output.mkdir(parents=True,exist_ok=True)
    for root in ROOTS.values():b.build(root)
    if a.binary:
        from audit import run
        audit=run(a.binary,list(b.types.values()),b.nodes,a.dump)
        for name,result in audit.items():
            if result['status']!='mapped':continue
            mapping={m['field']:m['id'] for m in result['mappings']}
            reads={r['id'] for r in result['reads']}
            if set(mapping.values())!=reads or sorted(reads)!=list(range(len(reads))):
                # Open generic parent fields can have placeholder offset 0 in IL2CPP metadata.
                # Keep their declared slots only when every slot is read and all known stores agree.
                fields=b.nodes[name]['fields']
                if (reads==set(range(len(fields))) and all(
                        mapping.get(f['source_name'])==f['id'] if f['source_name'] in mapping
                        else f['offset'] is not None and int(f['offset'],16)==0 for f in fields)):
                    b.nodes[name]['native_partial']=True
                    continue
                raise ValueError('Incomplete native slot recovery: '+name)
            node=b.nodes[name]
            fields=[]
            for f in node['fields']:
                if f['source_name'] in mapping:
                    fields.append(dict(f,id=mapping[f['source_name']]))
            node['fields']=sorted(fields,key=lambda f:f['id'])
            node['native_verified']=True
        (a.output/'native-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    for label,root in ROOTS.items():
        (a.output/(label+'.fbs')).write_text(b.fbs(root),encoding='utf-8')
        print(label,len(b.nodes))
    (a.output/'schema.json').write_text(json.dumps({'roots':ROOTS,'nodes':b.nodes},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
