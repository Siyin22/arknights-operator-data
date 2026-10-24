'use strict';
const report = JSON.parse(document.getElementById('report-data').textContent);
const current = report.current;
const state = {potential:1, skills:'max', selected:null, queue:new Map(), busy:false};
const $ = id => document.getElementById(id);
const disclaimer = $('report-notice').textContent;
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHTML;
const text = value => String(value ?? '').split(/(\d+(?:\.\d+)?%?)/g).map((part,i)=>i%2?`<span class="number">${e(part)}</span>`:e(part)).join('');
const versionText = v => `客户端 ${v.client_version || '未记录'} · 数据 ${v.official_version}`;
const potentialText = count => `潜能 ${Math.min(state.potential,count)}`;
const attrs = [['maxHp','生命上限'],['atk','攻击'],['def','防御'],['magicResistance','法术抗性'],['cost','部署费用'],['blockCnt','阻挡数'],['baseAttackTime','基础攻击间隔 / 秒'],['respawnTime','再部署时间 / 秒']];
const statusNames = {added:'新增',changed:'修改',removed:'移除',current:'当前版本资料'};
function statsHTML(stats){return '<div class="attribute-table">'+attrs.map(([key,label])=>`<div class="attribute-cell"><small>${label}</small><strong>${e(stats[key] ?? '—')}</strong></div>`).join('')+'</div>';}
const durationText = value => value === '即时 / 见描述' ? '即时' : /^\d+(?:\.\d+)?\s*秒$/.test(value) ? `持续时间 ${value}` : value;
function levelHTML(level){return `<div class="skill-level"><div class="skill-metadata"><span class="level-tag">${e(level.label)}</span><span>初始 ${e(level.initial)} / 消耗 ${e(level.cost)} 技力</span><span>${e(durationText(level.duration))}</span>${level.charges>1?`<span>可充能 ${e(level.charges)} 次</span>`:''}</div><p class="effect-text">${text(level.description)}</p></div>`;}
function potentialHTML(p){
  if(!p.potential?.length)return '<p class="card-note">该干员无潜能提升。</p>';
  return '<table class="info-table potential-table"><tbody>'+p.potential.map((label,i)=>{
    const before=p.variants[i]?.talents,after=p.variants[i+1]?.talents;
    // Talent slots keep their order, including robots whose talent names change at each potential.
    const enhanced=label.includes('天赋')&&before&&after?after.filter((t,j)=>t.name!==before[j]?.name||t.description!==before[j]?.description):[];
    const effect=enhanced.length?enhanced.map(t=>`<div class="potential-effect"><strong class="talent-name">${e(t.name)} · 提升后</strong><p class="effect-text">${text(t.description)}</p></div>`).join(''):`<p class="effect-text">${text(label)}</p>`;
    return `<tr><th scope="row">潜能 ${i+2}</th><td>${effect}</td></tr>`;
  }).join('')+'</tbody></table>';
}
function skillHTML(skill,index){
  const levels = state.skills==='all'?skill.levels:[skill.levels.at(-1)];
  return `<section class="skill-box" data-skill="${index}"><div class="skill-heading"><h4><span class="skill-index">SKILL ${e(skill.index)}</span>${e(skill.name)}</h4><span class="skill-type">${e(skill.levels.at(-1).recovery)} · ${e(skill.levels.at(-1).trigger)}</span></div>${state.skills==='max'&&skill.levels.length>1?`<div class="level-tabs no-export" role="group" aria-label="${e(skill.name)}技能等级">${skill.levels.map((lev,i)=>`<button type="button" data-level="${i}" class="${i===skill.levels.length-1?'active':''}" aria-pressed="${i===skill.levels.length-1}">${e(lev.label)}</button>`).join('')}</div>`:''}<div class="skill-content">${levels.map(levelHTML).join('')}</div></section>`;
}
function baseSkillsHTML(p){
  if(!Array.isArray(p.baseSkills))return '<p class="card-note">该历史版本未记录后勤技能。</p>';
  if(!p.baseSkills.length)return '<p class="card-note">该干员无已解锁的后勤技能。</p>';
  return '<table class="info-table base-skills-table"><tbody>'+p.baseSkills.map(group=>{
    const skill=group.levels.at(-1),previous=group.levels.slice(0,-1);
    return `<tr><th scope="row">${e(skill.name)}<small class="base-skill-room">${e(skill.room)}</small></th><td><div class="base-skill-meta">${e(skill.unlock.replace(/ · 1级$/, ''))}${previous.length?` · 替换「${e(previous.at(-1).name)}」`:''}</div><p class="effect-text">${text(skill.description)}</p></td></tr>`;
  }).join('')+'</tbody></table>';
}
function operatorBody(p){
  const v=p.variants[Math.min(state.potential,p.variants.length)-1];
  let body=`<div class="card-caption"><span>精英 ${e(p.phase)} · 满级 ${e(p.level)} · 满信赖 · ${e(p.position||'')}</span><span class="potential-chip">${potentialText(p.variants.length)}</span></div>`;
  body+='<h3 class="card-section-title">基础属性</h3>'+statsHTML(v.stats)+'<p class="card-note">已计入满信赖与所选潜能；不叠加模组、天赋或技能的战斗增益。</p>';
  body+='<h3 class="card-section-title">特性与天赋</h3><table class="info-table"><tbody><tr><th>特性</th><td><p class="effect-text">'+text(v.trait)+'</p></td></tr>';
  body+=v.talents.map((t,i)=>`<tr><th><span class="talent-name">天赋 ${i+1}</span>${e(t.name)}</th><td><p class="effect-text">${text(t.description)}</p></td></tr>`).join('')+'</tbody></table>';
  body+='<h3 class="card-section-title">潜能</h3>'+potentialHTML(p);
  body+='<h3 class="card-section-title">技能</h3>'+(p.skills.map(skillHTML).join('')||'<p class="card-note">该干员没有技能。</p>');
  body+='<h3 class="card-section-title">后勤技能</h3>'+baseSkillsHTML(p);
  if(p.tokens?.length)body+='<details class="supplement"><summary>关联召唤物 · 最高等级基础属性</summary>'+p.tokens.map(t=>`<section class="token-block"><h4>${e(t.name)}</h4>${statsHTML(t.stats)}<p class="effect-text">${text(t.trait)}</p>${t.skills.map((s,i)=>skillHTML(s,'token-'+i)).join('')}</section>`).join('')+'</details>';
  return body;
}
function bonusesHTML(bonuses){return bonuses.map(b=>`<span>${e(b.label)} <strong>${b.value>=0?'+':''}${e(b.value)}</strong></span>`).join('')||'<span>无额外属性加成</span>';}
function moduleBody(m){
  let body=`<div class="card-caption"><span>${e(m.profession)} / ${e(m.branch)} · 解锁：${e(m.unlock)}</span><span class="potential-chip">${potentialText(m.levels[0]?.effects.length||6)}</span></div>`;
  if(m.special)body+=`<p class="card-note">${e(m.special)}</p>`;
  body+='<h3 class="card-section-title">模组升级效果</h3><p class="card-note" style="margin-bottom:16px">各级显示该等级完整加成，不与其他等级累加。</p>';
  for(const level of m.levels){
    const effects=level.effects[Math.min(state.potential,level.effects.length)-1]||[];
    body+=`<section class="module-level"><div class="module-level-label"><strong>${e(level.level)}</strong><small>LEVEL</small></div><div class="module-level-body"><div class="bonus">${bonusesHTML(level.bonuses)}</div>`;
    for(const token of level.tokenBonuses)body+=`<div class="bonus"><span>${e(token.name)}</span>${bonusesHTML(token.bonuses)}</div>`;
    body+=effects.map(f=>`<div class="module-effect"><h5>${e(f.name)}${f.condition?`<span class="condition">${e(f.condition)}</span>`:''}</h5><p class="effect-text">${text(f.description)}</p></div>`).join('')||'<p class="card-note">无额外文字效果。</p>';
    body+='</div></section>';
  }
  if(!m.levels.length)body+='<p class="card-note">本版本尚未提供该模组的战斗效果数据。</p>';
  return body;
}
function changeHTML(rows){return rows.length?`<details class="change-details"><summary>查看 ${rows.length} 处修改前后对照</summary><table class="change-table"><thead><tr><th>项目</th><th>之前</th><th>现在</th></tr></thead><tbody>${rows.map(([path,a,b])=>`<tr><td>${e(path)}</td><td>${e(typeof a==='object'?JSON.stringify(a):a??'无')}</td><td>${e(typeof b==='object'?JSON.stringify(b):b??'无')}</td></tr>`).join('')}</tbody></table></details>`:'';}
function cardHTML(entry){
  const p=entry.record, operator=entry.category==='operators';
  const title=operator?p.name:p.operator_name+' · '+p.name;
  const subtitle=operator?`${p.english||''}　${p.profession} / ${p.branch}　${(p.tags||[]).join(' · ')}`:'MODULE / 模组资料';
  return `<article class="data-card" data-record="${e(entry.id)}"><div class="card-meta"><div class="card-meta-row"><strong class="card-version">${e(versionText(entry.version))}</strong><span class="creator-credit">By 司音</span></div><p class="card-disclaimer">${e(disclaimer)}</p></div><div class="card-title ${operator?'':'module-title'}"><div><h3 class="card-name">${e(title)}</h3><div class="card-subtitle">${e(subtitle)}</div></div>${operator?`<div class="rarity" aria-label="${p.rarity}星">${'★'.repeat(p.rarity)}</div>`:`<div class="module-code">${e(p.type)}</div>`}</div><div class="card-body">${operator?operatorBody(p):moduleBody(p)}</div>${changeHTML(entry.changes||[])}</article>`;
}
function entryHTML(entry,index){return `<div class="entry" data-entry="${index}"><div class="entry-bar"><div class="entry-kind"><span class="badge ${entry.status}">${e(statusNames[entry.status])}</span>${entry.category==='operators'?'干员':'模组'}${entry.status==='current'?' · 不代表本次新增':''}</div><div class="entry-actions"><button data-action="queue">加入清单</button><button data-action="png">导出 PNG</button></div></div>${cardHTML(entry)}</div>`;}
function renderEntries(){
  $('entry-list').innerHTML=report.entries.length?report.entries.map(entryHTML).join(''):`<div class="empty-state"><h3>${report.previous?'这两个版本没有干员或模组变化':'当前版本已建立基准'}</h3><p>${report.previous?'仍可在下方选择当前版本资料，分别导出图片。':'尚无更早的已保存版本，无法判定新增内容。下方资料导出可直接使用；以后更新时，这里会列出真正的版本差异。'}</p></div>`;
  $('export-batch').disabled=!report.entries.length||state.busy;
}
function selectEntry(){const kind=$('record-kind').value;const id=$('record-select').value;state.selected=id?{category:kind,id,record:current[kind][id],status:'current',version:current.version,changes:[]}:null;renderPreview();}
function renderPreview(){$('preview').innerHTML=state.selected?entryHTML(state.selected,'preview'):'<p class="card-note">没有找到匹配的资料。</p>';$('add-image').disabled=!state.selected||state.busy;}
function filterRecords(){
  const kind=$('record-kind').value, query=$('record-search').value.trim().toLocaleLowerCase();
  const previous=$('record-select').value;
  const records=Object.entries(current[kind]).filter(([,r])=>[r.name,r.english,r.operator_name,r.type,r.profession,r.branch].join(' ').toLocaleLowerCase().includes(query));
  records.sort((a,b)=>(a[1].operator_name||a[1].name).localeCompare(b[1].operator_name||b[1].name,'zh-CN'));
  $('record-select').innerHTML=records.map(([id,r])=>`<option value="${e(id)}">${e(kind==='operators'?`${r.name} · ${r.profession} / ${r.branch}`:`${r.operator_name} · ${r.type} · ${r.name}`)}</option>`).join('');
  if(records.some(([id])=>id===previous))$('record-select').value=previous;
  else if(kind==='operators'&&!query&&current.operators.char_4231_clemnt)$('record-select').value='char_4231_clemnt';
  selectEntry();
}
function queueEntry(entry){if(!entry)return;state.queue.set(entry.category+':'+entry.id,entry);updateQueue();}
function updateQueue(){$('queue-label').textContent=state.queue.size?`已选择 ${state.queue.size} 项：${[...state.queue.values()].map(x=>x.category==='operators'?x.record.name:x.record.operator_name+'·'+x.record.type).join('、')}`:'导出清单为空';$('export-queue').disabled=!state.queue.size||state.busy;$('clear-queue').disabled=!state.queue.size||state.busy;}
function filename(entry){const r=entry.record;return `${entry.category==='operators'?'干员_'+r.name+'_'+r.profession:'模组_'+r.operator_name+'_'+r.type+'_'+r.name}_数据${entry.version.official_version}_潜能${Math.min(state.potential,entry.category==='operators'?r.variants.length:r.levels[0]?.effects.length||6)}${entry.category==='operators'?(state.skills==='all'?'_全部技能':'_所选技能'):''}.png`.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_');}
function download(blob,name){const link=document.createElement('a');const url=URL.createObjectURL(blob);link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
function status(message,error=false){$('export-status').textContent=message;$('export-status').classList.toggle('error',error);}
function busy(value){state.busy=value;document.querySelectorAll('button,input,select').forEach(el=>{el.disabled=value;});if(!value){$('export-batch').disabled=!report.entries.length;$('add-image').disabled=!state.selected;updateQueue();}}
async function capture(entry,sourceCard){
  const stage=document.createElement('div');stage.className='export-stage';
  if(sourceCard)stage.append(sourceCard.cloneNode(true));else stage.innerHTML=cardHTML(entry);
  const card=stage.querySelector('.data-card');card.classList.add('export-card');
  card.querySelectorAll('details').forEach(detail=>{detail.open=true;});
  document.body.append(stage);
  try{
    await document.fonts.ready;await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const height=Math.ceil(card.getBoundingClientRect().height),width=1000;
    const scale=Math.min(2,16000/height,Math.sqrt(32000000/(width*height)));
    if(scale<0.75)throw Error('资料过长，请将技能选项切换为最高等级后再导出。');
    const canvas=await html2canvas(card,{backgroundColor:'#ffffff',scale,logging:false,windowWidth:1280,windowHeight:1000,scrollX:0,scrollY:0,imageTimeout:10000});
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw Error('浏览器无法生成图片，请使用最新版 Chrome 或 Edge。');
    canvas.width=0;canvas.height=0;
    return blob;
  }finally{stage.remove();}
}
// ZIP store mode: PNG already compresses its pixels. UTF-8 names, CRC32, no network dependency.
const crcTable=Array.from({length:256},(_,i)=>{for(let j=0;j<8;j++)i=(i&1)?0xedb88320^(i>>>1):i>>>1;return i>>>0;});
function crc32(bytes){let crc=0xffffffff;for(const b of bytes)crc=crcTable[(crc^b)&255]^(crc>>>8);return (crc^0xffffffff)>>>0;}
function zipStore(files){
  const local=[],central=[];let offset=0,centralSize=0;
  for(const file of files){const name=new TextEncoder().encode(file.name),data=file.bytes,crc=crc32(data);
    const header=new Uint8Array(30),h=new DataView(header.buffer);h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x800,true);h.setUint16(12,33,true);h.setUint32(14,crc,true);h.setUint32(18,data.length,true);h.setUint32(22,data.length,true);h.setUint16(26,name.length,true);local.push(header,name,data);
    const record=new Uint8Array(46),c=new DataView(record.buffer);c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x800,true);c.setUint16(14,33,true);c.setUint32(16,crc,true);c.setUint32(20,data.length,true);c.setUint32(24,data.length,true);c.setUint16(28,name.length,true);c.setUint32(42,offset,true);central.push(record,name);centralSize+=record.length+name.length;offset+=header.length+name.length+data.length;
  }
  const end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,files.length,true);v.setUint16(10,files.length,true);v.setUint32(12,centralSize,true);v.setUint32(16,offset,true);
  return new Blob([...local,...central,end],{type:'application/zip'});
}
async function exportOne(entry,card){if(state.busy)return;busy(true);status('正在生成 '+entry.record.name+' 的图片…');try{const blob=await capture(entry,card);download(blob,filename(entry));status('已生成 PNG：'+filename(entry)+'。请在浏览器下载列表中查看。');}catch(error){status('导出失败：'+error.message,true);}finally{busy(false);}}
async function exportMany(entries){if(state.busy||!entries.length)return;busy(true);const files=[],used=new Set();try{for(let i=0;i<entries.length;i++){const entry=entries[i];status(`正在生成 ${i+1} / ${entries.length}：${entry.record.name}`);const displayed=[...document.querySelectorAll('#entry-list .entry')].find(el=>report.entries[Number(el.dataset.entry)]===entry);const blob=await capture(entry,displayed?.querySelector('.data-card'));let name=filename(entry);if(used.has(name))name=name.replace('.png','_'+entry.id+'.png');used.add(name);files.push({name,bytes:new Uint8Array(await blob.arrayBuffer())});}download(zipStore(files),`明日方舟_数据${current.version.official_version}_${files.length}张资料.zip`);status(`已生成 ${files.length} 张独立 PNG，已打包为 ZIP。解压后可分别使用。`);}catch(error){status('导出失败：'+error.message,true);}finally{busy(false);}}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button||state.busy)return;
  const container=button.closest('.entry');if(!container)return;
  const entry=container.dataset.entry==='preview'?state.selected:report.entries[Number(container.dataset.entry)];
  if(button.dataset.action==='png')exportOne(entry,container.querySelector('.data-card'));
  if(button.dataset.action==='queue')queueEntry(entry);
  if(button.dataset.level!==undefined){
    const box=button.closest('.skill-box'),index=box.dataset.skill;
    // Token skills are kept in the all-level view when exporting; locate by title for interactive selection.
    const source=index.startsWith('token-')?entry.record.tokens.flatMap(t=>t.skills).find(s=>box.querySelector('h4').textContent.includes(s.name)):entry.record.skills[Number(index)];
    if(!source)return;box.querySelector('.skill-content').innerHTML=levelHTML(source.levels[Number(button.dataset.level)]);
    box.querySelectorAll('[data-level]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button?'true':'false');});
  }
});
$('potential').addEventListener('change',()=>{state.potential=Number($('potential').value);renderEntries();renderPreview();});
$('skill-mode').addEventListener('change',()=>{state.skills=$('skill-mode').value;renderEntries();renderPreview();});
$('record-kind').addEventListener('change',()=>{$('record-search').value='';filterRecords();});
$('record-search').addEventListener('input',filterRecords);$('record-select').addEventListener('change',selectEntry);
$('add-image').addEventListener('click',()=>queueEntry(state.selected));$('clear-queue').addEventListener('click',()=>{state.queue.clear();updateQueue();});
$('export-queue').addEventListener('click',()=>exportMany([...state.queue.values()]));$('export-batch').addEventListener('click',()=>exportMany(report.entries));
const version=current.version;
$('version-info').innerHTML=`<div class="version-box"><div class="version-item"><small>客户端版本</small><strong>${e(version.client_version||'未记录')}</strong><p>游戏程序与数据结构的版本</p></div><div class="version-item data"><small>数据版本</small><strong>${e(version.official_version)}</strong><p>干员、技能、模组配置的版本 · Git 标签</p></div></div>`;
$('comparison-caption').innerHTML=`<div class="comparison-caption">${report.previous?e(versionText(report.previous))+' → '+e(versionText(version)):'首个已保存版本 · 建立对比基准'}</div>`;
const difference=report.difference;
$('summary').innerHTML=[['added','新增','new'],['changed','修改','changed'],['removed','移除','removed']].map(([key,title,cls])=>`<div class="${cls}"><b>${difference.operators[key].length+difference.modules[key].length}</b><span>${title}条目</span><small>干员 ${difference.operators[key].length} · 模组 ${difference.modules[key].length}</small></div>`).join('');
renderEntries();filterRecords();
