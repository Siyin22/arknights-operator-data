// Run with node tests/test_report_batch.cjs; exercises the shipped export selection logic.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src/report_assets/report.js'),'utf8');
const logic=source.slice(source.indexOf('const recordKey ='),source.indexOf('const durationText ='));
const version={official_version:'78.2.0'};
function operator(id,status='added'){
  return {category:'operators',id,status,record:{id},version};
}
function moduleEntry(id,owner,status='added'){
  return {category:'modules',id,status,record:{id,operator_id:owner,type:id},version};
}
function setup(entries,extras=[]){
  const context=vm.createContext({report:{entries},current:{modules:Object.fromEntries(
    [...entries,...extras].filter(e=>e.category==='modules').map(e=>[e.id,e.record]))},
    state:{modules:new Map()}});
  vm.runInContext(logic,context);
  return code=>JSON.parse(JSON.stringify(vm.runInContext(code,context)));
}
const activity=[operator('clemnt'),operator('toledo'),operator('hbound'),
  moduleEntry('shu','shu'),moduleEntry('ulpia','ulpia'),
  moduleEntry('toledo-module','toledo'),moduleEntry('hbound-module','hbound')];
let run=setup(activity);
let result=run('updateExportEntries()');
assert.equal(result.length,5);
assert.deepEqual(result.find(e=>e.id==='toledo').moduleIds,['toledo-module']);
assert.deepEqual(result.find(e=>e.id==='hbound').moduleIds,['hbound-module']);
assert.ok(result.some(e=>e.id==='shu')&&result.some(e=>e.id==='ulpia'));
run("state.modules.set(recordKey(report.entries[1]),[]); null");
result=run('updateExportEntries()');
assert.equal(result.length,6);
assert.ok(result.some(e=>e.id==='toledo-module'));
assert.deepEqual(result.find(e=>e.id==='toledo').moduleIds,[]);
run("state.modules.set(recordKey(report.entries[2]),[]); null");
assert.equal(run('updateExportEntries()').length,7);

run=setup([operator('new'),moduleEntry('m1','new'),moduleEntry('m2','new')]);
assert.equal(run('updateExportEntries()').length,1);
assert.deepEqual(run('updateExportEntries()[0].moduleIds'),['m1','m2']);

run=setup([operator('old','changed'),moduleEntry('new-module','old')]);
assert.equal(run('updateExportEntries()').length,2,'changed operators keep standalone updates');
assert.deepEqual(run('updateExportEntries()[0].moduleIds'),[]);

run=setup([operator('new'),moduleEntry('module-form','other-form')],
  [moduleEntry('existing-module','new','current')]);
assert.equal(run('updateExportEntries()').length,2,'match owner IDs, not similar names');
assert.deepEqual(run('updateExportEntries()[0].moduleIds'),[],'do not attach unrelated existing modules');

const historical={...moduleEntry('module-old','new'),version:{official_version:'78.1.0'}};
run=setup([operator('new'),historical]);
assert.equal(run('updateExportEntries()').length,2,'do not merge across data versions');

run=setup(activity);
assert.deepEqual(run('exportEntry(report.entries[1],true).moduleIds'),[],'base-only export stays available');
assert.equal(run('report.entries.length'),7,'export grouping must not alter change statistics');
console.log('Batch export checks passed: activity 7 -> 5, unchecked fallback, multiple modules, ownership and versions.');
