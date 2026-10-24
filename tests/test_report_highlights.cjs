// Run with: node tests/test_report_highlights.cjs (no npm dependencies).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../src/report_assets/report.js'),'utf8');
const context = vm.createContext({});
const helpers = source.split('\n').filter(line=>/^const (escapeHTML|e |text )/.test(line)).join('\n');
vm.runInContext(helpers+'\n'+source.slice(source.indexOf('const effectTokens='),source.indexOf('function moduleBody(')),context);
const evaluate = code => vm.runInContext(code,context);
const highlighted = html => [...html.matchAll(/<span class="effect-change">(.*?)<\/span>(?:<\/span>)?/gs)]
  .map(match=>match[1].replace(/<[^>]+>/g,'')).join('');
const plain = html => html.replace(/<[^>]+>/g,'');

for (const [before,after,expected] of [
  ['攻击力20%','攻击力25%','25%'],
  ['攻击力20%','攻击力20%，新增效果','新增效果'],
  ['攻击力20%','攻击力20%，新增效果。','新增效果'],
  ['原有效果','原有效果，',''],
  ['恢复10点','恢复10点，生命+20%，防御+5','生命+20%，防御+5'],
  ['攻击力10%','攻击力-10%','-'],
  ['伤害100（+10）','伤害100（+20）','20'],
  ['攻击力25%','攻击力25%',''],
  ['额外攻击20%','攻击20%','']
]) {
  const html=evaluate(`changedText(${JSON.stringify(before)},${JSON.stringify(after)})`);
  assert.equal(plain(html),after,'must preserve complete original text');
  assert.equal(highlighted(html),expected,after);
}
const oldEffect={name:'领袖',condition:'',description:'攻击力20%'};
const nextEffect={...oldEffect,description:'攻击力25%'};
const render=(effects,previous)=>evaluate(`moduleEffectsHTML(${JSON.stringify(effects)},${JSON.stringify(previous)})`);
assert.equal(highlighted(render([nextEffect],[oldEffect])),'25%');
assert.equal(highlighted(render([nextEffect,nextEffect],[oldEffect])),'' ,'ambiguous effect names cannot be matched');
assert.equal(highlighted(render([nextEffect],[{...oldEffect,condition:'集成战略'}])),'' ,'different conditions cannot be matched');
assert.equal(highlighted(render([nextEffect],[])),'' ,'a newly unlocked effect has no prior baseline');
assert.match(render([oldEffect],[oldEffect]),/同上一级/);
assert.ok(!evaluate(`changedText('原文','原文，<script>')`).includes('<script>'),'escape inserted text');
console.log('Highlight regression checks passed: numbers, separators, signs, matching conditions and escaping.');
