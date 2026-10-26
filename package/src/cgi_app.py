#!/usr/bin/python3
import datetime as dt
import grp
import hashlib
import hmac
import json
import os
import pwd
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

os.umask(0o077)

PKG_VAR = Path("/var/packages/DBBackup/var")
DB_PATH = PKG_VAR / "state.sqlite3"
AUTH_CGI = "/usr/syno/synoman/webman/modules/authenticate.cgi"
SYSTEM_DATABASES = {"information_schema", "performance_schema", "mysql", "sys"}
MAX_BODY = 65536
APP_VERSION = "0.2.0-0002"


# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据库自动备份</title><style nonce="__NONCE__">
:root{color-scheme:light;--ink:#17212b;--muted:#657383;--line:#dbe2e8;--blue:#1769aa;--bg:#f3f6f8;--card:#fff;--good:#177245;--bad:#b42318}*{box-sizing:border-box}body{margin:0;background:var(--bg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink)}header{background:#123c5a;color:#fff;padding:20px max(24px,calc((100% - 1100px)/2));display:flex;align-items:center;justify-content:space-between}header h1{font-size:21px;margin:0}header span{font-size:13px;color:#cde3f2}.wrap{max-width:1100px;margin:24px auto;padding:0 18px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:0 0 18px;box-shadow:0 2px 8px #17324d0b}.card h2{font-size:18px;margin:0 0 14px}.row{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.field{display:flex;flex-direction:column;gap:5px;min-width:150px;flex:1}label{font-weight:600;font-size:13px}.hint,.muted{color:var(--muted);font-size:13px}.hint{margin:5px 0 12px}input,select{font:inherit;border:1px solid #b9c6d0;border-radius:7px;padding:9px 10px;background:white;color:var(--ink)}input[readonly]{background:#eef2f5}input[type=checkbox]{width:16px;height:16px;vertical-align:middle}button{border:0;border-radius:7px;background:var(--blue);color:#fff;font:600 14px inherit;padding:10px 14px;cursor:pointer}button.secondary{background:#e8eef3;color:#253746}button.danger{background:#fff0ef;color:#a21c14}button:disabled{opacity:.55;cursor:wait}.db-list{margin-top:14px;border-top:1px solid var(--line)}.db-item{padding:11px 4px;border-bottom:1px solid var(--line)}.db-head{display:flex;gap:10px;align-items:center}.db-head strong{flex:1}.tables{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:6px;margin:10px 0 0 28px}.table-item{font-size:13px;overflow-wrap:anywhere}.task{border-top:1px solid var(--line);padding:13px 0;display:grid;grid-template-columns:1fr auto;gap:8px}.task h3{font-size:15px;margin:0}.task .meta{font-size:13px;color:var(--muted)}.actions{display:flex;gap:7px;align-items:start}.status{padding:9px 12px;border-radius:7px;margin-bottom:14px;background:#e9f3f9;color:#1a4a69}.status.error{background:#fff0ef;color:var(--bad)}.status.good{background:#e9f6ef;color:var(--good)}.modal{position:fixed;inset:0;background:#0e1c2a88;display:none;align-items:center;justify-content:center;padding:18px}.modal.open{display:flex}.dialog{background:#fff;border-radius:12px;width:min(720px,100%);max-height:85vh;display:flex;flex-direction:column;padding:18px}.dialog-head{display:flex;justify-content:space-between;align-items:center}.dialog-body{overflow:auto;margin:10px 0}.fs-entry{padding:9px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}.fs-entry button{padding:6px 9px}.fs-path{font-family:monospace;font-size:12px;overflow-wrap:anywhere}.footer{padding:0 4px 24px;color:var(--muted);font-size:12px}@media(max-width:650px){header{padding:16px}.card{padding:15px}.task{grid-template-columns:1fr}.actions{justify-content:flex-start}}
[hidden]{display:none!important}</style></head><body>
<header><h1>数据库自动备份</h1><span>已通过 DSM 登录验证</span></header><main class="wrap">
<div id="notice" class="status" hidden></div>
<section class="card"><h2>数据库数据源</h2><p class="hint">服务器地址留空表示备份本机 NAS 上的 MariaDB 10；填写 IP 或域名并设置端口，即可备份内网其他服务器上的 MySQL / MariaDB，备份文件统一保存到本 NAS 的共享文件夹。账号密码按 DSM 用户分别加密保存；连接成功后会自动检测并显示数据库和数据表，无需手动填写名称。</p><div class="row"><div class="field"><label for="sourceSelect">选择数据源</label><select id="sourceSelect"></select></div><button class="secondary" id="newSource">新增数据源</button><button class="danger" id="deleteSource">删除此数据源</button></div><div class="row" style="margin-top:12px"><div class="field"><label for="sourceName">数据源名称</label><input id="sourceName" maxlength="60" placeholder="例如：本机 MariaDB / 网站服务器"></div><div class="field"><label for="sourceHost">服务器地址（留空=本机）</label><input id="sourceHost" placeholder="192.168.1.10 或 db.example.com"></div><div class="field" style="max-width:130px"><label for="sourcePort">端口</label><input id="sourcePort" type="number" min="1" max="65535" value="3306"></div></div><div class="row" style="margin-top:12px"><div class="field"><label for="dbuser">数据库用户名</label><input id="dbuser" autocomplete="username" placeholder="建议使用只读账号"></div><div class="field"><label for="dbpass">数据库密码</label><input id="dbpass" type="password" autocomplete="new-password" placeholder="首次设置必填；留空则保留已保存的密码"></div><button id="saveProfile">保存并连接</button><button class="secondary" id="discover">重新检测数据库</button></div><div class="hint">远程备份要求：目标服务器防火墙放行本 NAS 的 IP 与所选端口；账号需具备 SELECT、SHOW VIEW、TRIGGER、EVENT、LOCK TABLES 权限，备份 routine 时还需 SELECT 权限读取 mysql.proc。若远程是 MySQL 8 且账号使用 caching_sha2_password 认证，请改成 mysql_native_password，否则 NAS 上的 MariaDB 客户端可能无法登录。</div><div id="profileState" class="hint"></div><div id="dbList" class="db-list"></div></section>
<section class="card" id="planForm"><h2 id="planFormTitle">备份计划</h2><p class="hint">自动检测并显示数据库和数据表，勾选一个或多个数据库；展开的数据表可单独勾选。勾选数据库但不勾选数据表时，将备份该数据库的全部数据表。</p><div class="row"><div class="field"><label for="taskName">计划名称</label><input id="taskName" maxlength="80" placeholder="例如：网站数据库"></div><div class="field"><label for="planSource">数据源</label><input id="planSource" readonly placeholder="请在上方选择数据源"></div><div class="field"><label for="target">备份目录</label><input id="target" readonly placeholder="请使用右侧按钮选择"></div><button class="secondary" id="chooseFolder">选择目录</button></div><div class="row" style="margin-top:12px"><div class="field" id="convertToScheduleWrap" hidden><label><input id="convertToSchedule" type="checkbox"> 保存后改为定时计划</label></div><div class="field"><label for="frequency">备份方式</label><select id="frequency"><option value="daily">每天（自定义时间）</option><option value="weekly">每周（自定义星期和时间）</option><option value="interval">按间隔执行</option><option value="startup">开机后备份（每次开机执行一次）</option></select></div><div class="field" id="weekdayWrap" hidden><label for="weekday">星期</label><select id="weekday"><option value="0">星期一</option><option value="1">星期二</option><option value="2">星期三</option><option value="3">星期四</option><option value="4">星期五</option><option value="5">星期六</option><option value="6">星期日</option></select></div><div class="field" id="timeWrap"><label for="runTime">执行时间</label><input id="runTime" type="time" value="02:00"></div><div class="field" id="intervalWrap" hidden><label for="intervalValue">间隔数值</label><input id="intervalValue" type="number" min="1" max="168" value="1"></div><div class="field" id="intervalUnitWrap" hidden><label for="intervalUnit">间隔单位</label><select id="intervalUnit"><option value="hours">小时</option><option value="minutes">分钟</option></select></div><div class="field" id="bootDelayWrap" hidden><label for="bootDelay">开机后延迟（分钟）</label><input id="bootDelay" type="number" min="0" max="1440" value="5"></div><div class="field"><label for="retentionCount">计划保留份数（达到后清理最旧备份；0 表示不限）</label><input id="retentionCount" type="number" min="0" max="1000" value="0"></div><button id="createTask">新增计划</button><button class="secondary" id="cancelEdit" hidden>取消编辑</button><button class="secondary" id="backupNowSelected">立即备份所选内容</button></div><div class="hint" id="scheduleHint">选择“开机后备份”可设置 NAS 每次开机后延迟几分钟执行一次；日常计划按设置频率运行。达到保留份数上限后，新备份成功时会清理同一计划、同一数据库的最旧备份。立即备份会单独保存，不自动清理。</div></section>
<section class="card"><h2>我的备份计划</h2><div id="tasks"><span class="muted">正在加载…</span></div></section>
<div class="footer">备份文件为未压缩 SQL，文件名格式为“数据库名-备份时间.sql”。数据源可以是本机 MariaDB，也可以是内网其他服务器上的 MySQL / MariaDB（通过网络直连，需要目标端放行端口并授予只读权限）。<br>© 2026 AWA · www.akkdiy.cn。免责声明：本套件按“现状”提供；用户须自行确认备份完整性、保存期限和还原可用性。作者不对数据丢失、服务中断或其他损失承担责任。</div></main>
<div class="modal" id="folderModal"><div class="dialog"><div class="dialog-head"><strong>选择 NAS 目录</strong><button class="secondary" id="closeFolder">关闭</button></div><div class="fs-path" id="fsBreadcrumb"></div><div class="dialog-body" id="folderEntries"></div><div class="hint">列表使用当前 DSM 登录账号的 File Station 会话。选择前会检查创建文件权限。</div></div></div>
<script nonce="__NONCE__">
const CSRF='__CSRF__',DSM_TOKEN=__SYNO_TOKEN__;
const $=id=>document.getElementById(id);
let dbs=[],sources=[],currentSourceId='',selectedFolder=null,editingTaskId=null,editingManualOnly=false;
function notice(msg,bad=false){const n=$('notice');n.textContent=msg;n.className='status'+(bad?' error':' good');n.hidden=false;clearTimeout(n._timer);n._timer=setTimeout(()=>n.hidden=true,6500);if(bad)n.scrollIntoView({behavior:'smooth',block:'center'})}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function api(action,data=null){const o={method:data?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:{'Accept':'application/json'}};if(DSM_TOKEN)o.headers['X-SYNO-TOKEN']=DSM_TOKEN;let url='api.cgi?action='+encodeURIComponent(action);if(data){o.headers['Content-Type']='application/json';o.headers['X-CSRF-Token']=CSRF;o.body=JSON.stringify({...data,action})}const r=await fetch(url,o);const j=await r.json().catch(()=>({ok:false,error:'服务器响应格式错误'}));if(r.status===401){location.reload();throw Error('DSM 登录已失效')}if(!r.ok||!j.ok)throw Error(j.error||'操作失败');return j}
const tableCache=Object.create(null);
function showTables(item,names){const grid=document.createElement('div');grid.className='tables';if(!names.length){grid.textContent='此数据库没有可见的数据表。'}else for(const t of names){const lab=document.createElement('label');lab.className='table-item';lab.innerHTML='<input type="checkbox" class="table-check" value="'+esc(t)+'"> '+esc(t);lab.querySelector('.table-check').onchange=function(){if(this.checked)item.querySelector('.db-check').checked=true};grid.append(lab)}const old=item.querySelector('.tables');if(old)old.replaceWith(grid);else item.append(grid)}
async function loadTables(item,name){const key=currentSourceId+'\u0000'+name;if(Object.prototype.hasOwnProperty.call(tableCache,key)){showTables(item,tableCache[key]);return}const box=item.querySelector('.tables');box.textContent='正在自动检测数据表…';try{const x=await api('tables',{source_id:currentSourceId,database:name});tableCache[key]=x.tables||[];showTables(item,tableCache[key])}catch(e){box.textContent='数据表检测失败：'+e.message}}
function renderDbs(){const box=$('dbList');box.replaceChildren();if(!dbs.length){box.innerHTML='<p class="muted">尚未连接数据源，或该账号没有可备份的数据库。</p>';return Promise.resolve()}const loads=[];for(const db of dbs){const item=document.createElement('div');item.className='db-item';item.dataset.db=db.name;item.innerHTML='<div class="db-head"><input type="checkbox" class="db-check"><strong>'+esc(db.name)+'</strong><span class="muted">勾选数据库可备份全部表；也可勾选下方单表</span></div><div class="tables muted">正在自动检测数据表…</div>';box.append(item);loads.push(loadTables(item,db.name))}return Promise.all(loads)}
function sourceLabel(s){return s?(s.name+(s.host?'（'+s.host+':'+s.port+'）':'（本机）')):'未选择数据源'}
function currentSource(){return sources.find(s=>s.id===currentSourceId)||null}
function renderSources(){const sel=$('sourceSelect');sel.replaceChildren();const known=sources.some(s=>s.id===currentSourceId);if(!known){const o=document.createElement('option');o.value='';o.textContent=sources.length?'（新增数据源…）':'（尚未添加数据源）';sel.append(o)}for(const s of sources){const o=document.createElement('option');o.value=s.id;o.textContent=sourceLabel(s);sel.append(o)}sel.value=known?currentSourceId:''}
function fillSourceFields(){const s=currentSource();$('sourceName').value=s?s.name:'';$('sourceHost').value=s?s.host:'';$('sourcePort').value=s?String(s.port):'3306';$('dbuser').value=s?s.db_user:'';$('dbpass').value='';$('deleteSource').disabled=!s;$('planSource').value=sourceLabel(s)}
function setSource(id,reload){currentSourceId=id;renderSources();fillSourceFields();return reload===false?Promise.resolve(true):loadDatabases()}
async function loadDatabases(){const box=$('dbList');if(!currentSourceId){dbs=[];box.replaceChildren();$('profileState').textContent='请填写并保存一个数据源后即可自动检测数据库。';renderDbs();return false}box.innerHTML='<p class="muted">正在连接并自动检测数据库…</p>';try{const x=await api('databases',{source_id:currentSourceId});dbs=x.databases||[];$('profileState').textContent='已连接 '+sourceLabel(currentSource())+'，检测到 '+dbs.length+' 个数据库。';await renderDbs();return true}catch(e){dbs=[];$('profileState').textContent='连接失败：'+e.message;renderDbs();return false}}
function taskPayload(){const databases=[];document.querySelectorAll('.db-item').forEach(el=>{if(!el.querySelector('.db-check').checked)return;const tables=[...el.querySelectorAll('.table-check:checked')].map(x=>x.value);databases.push({name:el.dataset.db,tables})});return {name:$('taskName').value.trim(),target:selectedFolder||$('target').dataset.real||'',source_id:currentSourceId,databases,frequency:$('frequency').value,weekday:Number($('weekday').value),time:$('runTime').value,interval_value:Number($('intervalValue').value),interval_unit:$('intervalUnit').value,startup_delay:Number($('bootDelay').value),retention_count:Number($('retentionCount').value),convert_to_schedule:editingManualOnly&&$('convertToSchedule').checked}}
async function refresh(){try{const x=await api('status');sources=x.sources||[];if(!sources.some(s=>s.id===currentSourceId))currentSourceId=sources.length?sources[0].id:'';renderSources();fillSourceFields();renderTasks(x.tasks||[]);await loadDatabases()}catch(e){notice(e.message,true)}}
function nextExecution(t){if(t.manual_only)return t.queued?'立即备份队列中':'等待手动触发';if(!t.enabled)return '已停用';if(t.next_run){const d=new Date(t.next_run);return isNaN(d.getTime())?t.next_run:d.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})}if(t.frequency==='startup')return '下次开机后 '+t.startup_delay+' 分钟';return '等待调度器计算'}
function renderTasks(tasks){const box=$('tasks');box.replaceChildren();if(!tasks.length){box.innerHTML='<span class="muted">尚未创建计划。</span>';return}for(const t of tasks){const el=document.createElement('div');el.className='task';let schedule=t.manual_only?'立即备份队列':t.frequency==='startup'?'开机后 '+t.startup_delay+' 分钟执行一次':t.frequency==='weekly'?'每周'+['一','二','三','四','五','六','日'][t.weekday]+' '+t.run_time:t.frequency==='interval'?'每 '+t.interval_value+(t.interval_unit==='minutes'?' 分钟':' 小时'):'每天 '+t.run_time;const dbtext=t.databases.map(d=>d.name+(d.tables&&d.tables.length?'（'+d.tables.length+' 张表）':'（全部数据表）')).join('、');el.innerHTML='<div><h3>'+esc(t.name||'未命名计划')+(t.enabled?'':'（已停用）')+'</h3><div class="meta">'+esc(schedule)+'<br>数据源：'+esc(t.source_name||'（数据源已删除）')+'<br>备份目录：'+esc(t.target)+'<br>数据库：'+esc(dbtext)+'<br>保留份数：'+(Number(t.retention_count)>0?esc(t.retention_count)+' 份':'不限')+'<br>下次执行：'+esc(nextExecution(t))+'<br>上次执行：'+esc(t.last_run||'尚未执行')+' · '+esc(t.last_message||'等待调度')+'</div></div><div class="actions"><button class="secondary edit">编辑</button><button class="secondary run">立即备份</button><button class="secondary toggle">'+(t.enabled?'停用':'启用')+'</button><button class="danger delete">删除</button></div>';el.querySelector('.edit').onclick=()=>editTask(t);el.querySelector('.run').onclick=async()=>{try{await api('run_task',{id:t.id});notice('已加入立即备份队列。');await refresh()}catch(e){notice(e.message,true)}};el.querySelector('.toggle').onclick=async()=>{try{await api('toggle_task',{id:t.id,enabled:!t.enabled});await refresh()}catch(e){notice(e.message,true)}};el.querySelector('.delete').onclick=async()=>{if(!confirm('确定删除这个备份计划？'))return;try{await api('delete_task',{id:t.id});await refresh()}catch(e){notice(e.message,true)}};box.append(el)}}
function setScheduleDisabled(disabled){['frequency','weekday','runTime','intervalValue','intervalUnit','bootDelay','retentionCount'].forEach(id=>$(id).disabled=disabled)}
function resetEditor(){editingTaskId=null;editingManualOnly=false;$('convertToScheduleWrap').hidden=true;$('convertToSchedule').checked=false;$('planFormTitle').textContent='备份计划';$('createTask').textContent='新增计划';$('cancelEdit').hidden=true;$('taskName').value='';$('target').value='';$('target').dataset.real='';selectedFolder=null;$('frequency').value='daily';$('weekday').value='0';$('runTime').value='02:00';$('intervalValue').value='1';$('intervalUnit').value='hours';$('bootDelay').value='5';$('retentionCount').value='0';setScheduleDisabled(false);document.querySelectorAll('.db-check,.table-check').forEach(x=>x.checked=false);updateScheduleFields()}
async function editTask(t){try{if(t.source_id&&!sources.some(s=>s.id===t.source_id))throw Error('该计划关联的数据源已被删除，请先新增数据源再编辑此计划。');if(t.source_id&&t.source_id!==currentSourceId){const ok=await setSource(t.source_id);if(!ok)throw Error('无法连接该计划的数据源，请检查服务器地址、端口与账号后重试。')}const saved=new Map(t.databases.map(x=>[x.name,x]));if([...saved.keys()].some(name=>!dbs.some(x=>x.name===name)))throw Error('计划中的数据库当前未检测到，请先重新检测数据库后再编辑。');await renderDbs();for(const [name,selection] of saved){const item=[...document.querySelectorAll('.db-item')].find(x=>x.dataset.db===name);if(!item)throw Error('数据库 '+name+' 当前不可用，无法安全编辑。');const checks=[...item.querySelectorAll('.table-check')];const wanted=selection.tables||[];if(wanted.some(table=>!checks.some(x=>x.value===table)))throw Error('数据库 '+name+' 的数据表未能完整检测，请重新检测后再编辑。');item.querySelector('.db-check').checked=true;checks.forEach(x=>x.checked=wanted.includes(x.value))}editingTaskId=t.id;editingManualOnly=Boolean(t.manual_only);$('convertToScheduleWrap').hidden=!editingManualOnly;$('convertToSchedule').checked=false;$('planFormTitle').textContent=t.manual_only?'编辑立即备份':'编辑备份计划';$('createTask').textContent='保存修改';$('cancelEdit').hidden=false;$('taskName').value=t.name||'';$('target').value=t.target||'';$('target').dataset.real=t.target||'';selectedFolder=t.target||null;$('frequency').value=t.frequency||'daily';$('weekday').value=String(t.weekday||0);$('runTime').value=t.run_time||'02:00';$('intervalValue').value=String(t.interval_value||1);$('intervalUnit').value=t.interval_unit||'hours';$('bootDelay').value=String(t.startup_delay||0);$('retentionCount').value=String(t.retention_count||0);setScheduleDisabled(editingManualOnly);updateScheduleFields();if(t.manual_only)$('scheduleHint').textContent='这是一次性立即备份任务。修改数据库、目录等后，保存再点“立即备份”重试；勾选“保存后改为定时计划”可编辑并启用下方计划设置。';$('planForm').scrollIntoView({behavior:'smooth',block:'start'});notice('已载入计划，请修改后保存。')}catch(e){notice(e.message,true)}}
$('sourceSelect').onchange=()=>{setSource($('sourceSelect').value)};
$('newSource').onclick=()=>{currentSourceId='';renderSources();fillSourceFields();dbs=[];$('dbList').replaceChildren();$('profileState').textContent='填写数据源名称、服务器地址（留空表示本机 NAS）、端口、账号和密码，然后点“保存并连接”。';$('sourceName').focus()};
$('saveProfile').onclick=async()=>{const button=$('saveProfile');if(button.disabled)return;const oldText=button.textContent;button.disabled=true;button.textContent='正在连接…';try{const x=await api('save_source',{id:currentSourceId||null,name:$('sourceName').value.trim(),host:$('sourceHost').value.trim(),port:Number($('sourcePort').value||3306),db_user:$('dbuser').value.trim(),db_password:$('dbpass').value});$('dbpass').value='';currentSourceId=x.id;Object.keys(tableCache).forEach(k=>delete tableCache[k]);notice('数据源已保存，正在自动检测数据库和数据表。');await refresh()}catch(e){notice(e.message,true)}finally{button.disabled=false;button.textContent=oldText}};
$('deleteSource').onclick=async()=>{if(!currentSourceId)return;if(!confirm('确定删除数据源“'+sourceLabel(currentSource())+'”？使用它的备份计划需要先删除或改到其他数据源。'))return;try{await api('delete_source',{id:currentSourceId});currentSourceId='';notice('数据源已删除。');await refresh()}catch(e){notice(e.message,true)}};
$('discover').onclick=async()=>{Object.keys(tableCache).forEach(k=>delete tableCache[k]);const ok=await loadDatabases();if(ok)notice('已重新检测数据库和数据表。')};
function updateScheduleFields(){const f=$('frequency').value;$('weekdayWrap').hidden=f!=='weekly';$('timeWrap').hidden=f==='interval'||f==='startup';$('intervalWrap').hidden=f!=='interval';$('intervalUnitWrap').hidden=f!=='interval';$('bootDelayWrap').hidden=f!=='startup';$('scheduleHint').textContent=f==='startup'?'每次 NAS 开机后按此延迟执行一次。若 NAS 已开机，新计划从下次开机开始生效。每个计划、每个数据库分别保留设置的份数；达到上限后，先成功生成新备份，再清理最旧备份。立即备份单独保存，不自动清理。':'日常计划按设置频率运行，不会因 NAS 重启额外执行。达到保留份数上限后，新备份成功时会清理同一计划、同一数据库的最旧备份。立即备份会单独保存，不自动清理。'}
$('frequency').onchange=updateScheduleFields;updateScheduleFields();
$('intervalUnit').onchange=()=>{$('intervalValue').max=$('intervalUnit').value==='minutes'?'10080':'168';if(Number($('intervalValue').value)>Number($('intervalValue').max))$('intervalValue').value=$('intervalValue').max};
$('chooseFolder').onclick=async()=>{selectedFolder=null;$('folderModal').classList.add('open');await browseShares()};$('closeFolder').onclick=()=>$('folderModal').classList.remove('open');
async function fsCall(apiName,params){const q=new URLSearchParams({api:apiName,...params});if(DSM_TOKEN)q.set('SynoToken',DSM_TOKEN);const r=await fetch('/webapi/entry.cgi?'+q,{credentials:'same-origin',cache:'no-store'});const j=await r.json();if(!j.success)throw Error('File Station 无法读取此目录，请检查登录账号权限');return j.data||{}}
function pathFor(virtual,real){$('fsBreadcrumb').textContent=virtual||'共享文件夹';$('folderEntries').dataset.virtual=virtual||'';$('folderEntries').dataset.real=real||''}
async function browseShares(){try{pathFor('','');const d=await fsCall('SYNO.FileStation.List',{version:'2',method:'list_share',onlywritable:'true',additional:JSON.stringify(['real_path','perm'])});renderFolders((d.shares||[]).filter(x=>x.isdir),true)}catch(e){notice(e.message,true);$('folderEntries').textContent=e.message}}
async function browseFolder(path,real){try{pathFor(path,real);const d=await fsCall('SYNO.FileStation.List',{version:'2',method:'list',folder_path:path,additional:JSON.stringify(['real_path','perm'])});const files=(d.files||[]).filter(x=>x.isdir);renderFolders(files,false)}catch(e){notice(e.message,true)}}
function renderFolders(items,shares){const box=$('folderEntries');box.replaceChildren();if(!shares){const up=document.createElement('div');up.className='fs-entry';up.innerHTML='<span>返回上层</span><button class="secondary">返回</button>';up.querySelector('button').onclick=()=>{const parts=box.dataset.virtual.split('/').filter(Boolean);parts.pop();if(!parts.length){browseShares();return}const realParts=(box.dataset.real||'').split('/').filter(Boolean);realParts.pop();browseFolder('/'+parts.join('/'),'/'+realParts.join('/'))};box.append(up)}for(const x of items){const entry=document.createElement('div');entry.className='fs-entry';entry.innerHTML='<span>'+esc(x.name)+'</span><span class="actions"><button class="secondary open">打开</button><button class="choose">选择</button></span>';entry.querySelector('.open').onclick=()=>browseFolder(x.path,x.additional?.real_path||'');entry.querySelector('.choose').onclick=async()=>{try{await fsCall('SYNO.FileStation.CheckPermission',{version:'3',method:'write',path:x.path,filename:'.dbbackup-check-'+Math.random().toString(36).slice(2),create_only:'true'});const real=x.additional?.real_path||'';if(!real)throw Error('DSM 未返回实际目录，请刷新或更新 DSM');await api('check_target',{target:real});selectedFolder=real;$('target').value=real;$('target').dataset.real=real;$('folderModal').classList.remove('open');notice('已选择套件服务账号可写入的目录。')}catch(e){notice(e.message,true)}};box.append(entry)}if(!items.length)box.innerHTML='<span class="muted">此目录没有子文件夹。</span>'}
$('createTask').onclick=async()=>{const button=$('createTask');if(button.disabled)return;const oldText=button.textContent;button.disabled=true;button.textContent='正在保存…';try{const editing=editingTaskId;const p=taskPayload();if(editing)p.id=editing;if(!p.source_id)throw Error('请先选择或新增一个数据源');if(!p.target)throw Error('请先选择备份目录');if(!p.databases.length)throw Error('请至少选择一个数据库');await api('save_task',p);notice(editing?'备份计划已更新。':'备份计划已保存。');resetEditor();await refresh()}catch(e){notice(e.message,true)}finally{button.disabled=false;if(button.textContent==='正在保存…')button.textContent=oldText}};
$('cancelEdit').onclick=resetEditor;
$('convertToSchedule').onchange=()=>{if(editingManualOnly){setScheduleDisabled(!$('convertToSchedule').checked);if($('convertToSchedule').checked)$('scheduleHint').textContent='保存后该任务会变为定时备份计划，并按下方设置执行。'}};
$('backupNowSelected').onclick=async()=>{try{const p=taskPayload();if(!p.source_id)throw Error('请先选择或新增一个数据源');if(!p.target)throw Error('请先选择备份目录');if(!p.databases.length)throw Error('请至少选择一个数据库');await api('backup_now',p);notice('已将所选数据库/数据表加入立即备份队列。');await refresh()}catch(e){notice(e.message,true)}};
refresh();
</script></body></html>'''


def ensure_private_dir():
    PKG_VAR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(PKG_VAR, 0o700)
    except OSError:
        pass


def connect_db():
    ensure_private_dir()
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    os.chmod(DB_PATH, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS profiles (
        owner TEXT PRIMARY KEY, db_user TEXT NOT NULL, db_password TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
        host TEXT NOT NULL DEFAULT '', port INTEGER NOT NULL DEFAULT 3306,
        db_user TEXT NOT NULL, db_password TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS sources_owner_idx ON sources(owner);
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
        target TEXT NOT NULL, databases_json TEXT NOT NULL,
        frequency TEXT NOT NULL, weekday INTEGER NOT NULL, run_time TEXT NOT NULL,
        interval_value INTEGER NOT NULL DEFAULT 1, interval_unit TEXT NOT NULL DEFAULT 'hours',
        startup_delay INTEGER NOT NULL, retention_count INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 1,
        manual_only INTEGER NOT NULL DEFAULT 0, next_run TEXT, run_requested INTEGER NOT NULL DEFAULT 0,
        last_run TEXT, last_message TEXT
      );
      CREATE INDEX IF NOT EXISTS tasks_owner_idx ON tasks(owner);
      CREATE TABLE IF NOT EXISTS backup_files (
        path TEXT PRIMARY KEY, task_id TEXT NOT NULL, database_key TEXT NOT NULL,
        created_at REAL NOT NULL
      );
      CREATE INDEX IF NOT EXISTS backup_files_scope_idx ON backup_files(task_id,database_key,created_at);
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    existing = {row[1] for row in db.execute("PRAGMA table_info(tasks)").fetchall()}
    if "interval_value" not in existing:
        db.execute("ALTER TABLE tasks ADD COLUMN interval_value INTEGER NOT NULL DEFAULT 1")
    if "interval_unit" not in existing:
        db.execute("ALTER TABLE tasks ADD COLUMN interval_unit TEXT NOT NULL DEFAULT 'hours'")
    if "manual_only" not in existing:
        db.execute("ALTER TABLE tasks ADD COLUMN manual_only INTEGER NOT NULL DEFAULT 0")
    if "retention_count" not in existing:
        db.execute("ALTER TABLE tasks ADD COLUMN retention_count INTEGER NOT NULL DEFAULT 0")
    if "source_id" not in existing:
        db.execute("ALTER TABLE tasks ADD COLUMN source_id TEXT NOT NULL DEFAULT ''")
    migrate_legacy_profile(db)
    return db


def legacy_source_id(owner):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "dbbackup:local:" + owner))


def migrate_legacy_profile(db):
    """Turn the single per-user local MariaDB connection into a data source."""
    try:
        rows = db.execute("SELECT owner,db_user,db_password,updated_at FROM profiles").fetchall()
    except sqlite3.Error:
        return
    for row in rows:
        source_id = legacy_source_id(row["owner"])
        exists = db.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO sources(id,owner,name,host,port,db_user,db_password,updated_at) VALUES(?,?,?,'',3306,?,?,?)",
                (source_id, row["owner"], "本机 MariaDB", row["db_user"], row["db_password"], row["updated_at"]))
        db.execute("UPDATE tasks SET source_id=? WHERE owner=? AND source_id=''", (source_id, row["owner"]))
    db.commit()


AUTH_DIAGNOSTIC = "DSM 会话验证未完成。"

def authenticate():
    global AUTH_DIAGNOSTIC
    cookie_present = bool(os.environ.get("HTTP_COOKIE", "").strip())
    from urllib.parse import parse_qs
    query_token = parse_qs(os.environ.get("QUERY_STRING", ""), keep_blank_values=False).get("SynoToken", [""])[0]
    header_token = os.environ.get("HTTP_X_SYNO_TOKEN", "").strip()
    syno_token = header_token or query_token.strip()
    token_present = bool(syno_token and len(syno_token) <= 512 and re.fullmatch(r"[A-Za-z0-9._-]+", syno_token))
    user = os.environ.get("REMOTE_USER", "").strip()
    if user and len(user) <= 128 and not any(ord(c) < 32 for c in user):
        AUTH_DIAGNOSTIC = ""
        return user

    # The launcher is setuid to the package account for private state access.
    # Run DSM's auth helper with the original CGI identity so its own execute
    # permissions are honored, while the parent retains package privileges.
    real_uid = os.getuid()
    drop_euid = None
    if hasattr(os, "geteuid") and os.geteuid() != real_uid:
        def drop_to_cgi_user():
            os.seteuid(real_uid)
        drop_euid = drop_to_cgi_user
    p = None
    try:
        auth_env = os.environ.copy()
        if token_present:
            auth_env["HTTP_X_SYNO_TOKEN"] = syno_token
            if not query_token:
                current_query = auth_env.get("QUERY_STRING", "")
                auth_env["QUERY_STRING"] = current_query + ("&" if current_query else "") + "SynoToken=" + syno_token
        p = subprocess.run([AUTH_CGI], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=5, check=False, close_fds=True,
                           preexec_fn=drop_euid, env=auth_env)
        lines = p.stdout.decode("utf-8", "replace").replace("\x00", "").splitlines() if p.stdout else []
        user = next((line.strip() for line in lines
                     if line.strip() and not line.lstrip().lower().startswith(("content-type:", "status:"))), "")
    except PermissionError:
        user = ""
        AUTH_DIAGNOSTIC = "DSM Cookie 已到达：" + ("有" if cookie_present else "无") + "；DSM 认证程序拒绝以 CGI 身份执行（权限不足）。"
    except subprocess.TimeoutExpired:
        user = ""
        AUTH_DIAGNOSTIC = "DSM 认证程序响应超时。"
    except OSError as exc:
        user = ""
        AUTH_DIAGNOSTIC = "DSM 认证程序无法启动（系统错误 " + str(exc.errno or 0) + "）。"
    except Exception as exc:
        user = ""
        AUTH_DIAGNOSTIC = "DSM 认证检查失败（" + type(exc).__name__ + "）。"

    if not user or len(user) > 128 or any(ord(c) < 32 for c in user):
        if not AUTH_DIAGNOSTIC or AUTH_DIAGNOSTIC == "DSM 会话验证未完成。":
            if not cookie_present:
                AUTH_DIAGNOSTIC = "请求没有收到 DSM 会话 Cookie。"
            elif p is not None and p.returncode != 0:
                AUTH_DIAGNOSTIC = "已收到 DSM Cookie；SynoToken" + ("已" if token_present else "未") + "传入认证程序，但 DSM 认证程序返回错误代码 " + str(p.returncode) + "。"
            else:
                AUTH_DIAGNOSTIC = "已收到 DSM Cookie，但 DSM 认证程序未返回用户名。"
        return None
    AUTH_DIAGNOSTIC = ""
    return user


def application_authorized(user):
    """The DSM app is configured for administrators only; enforce that on CGI too."""
    try:
        admin_gid = grp.getgrnam("administrators").gr_gid
        account = pwd.getpwnam(user)
        return admin_gid in os.getgrouplist(user, account.pw_gid)
    except (KeyError, OSError, AttributeError):
        return False


def csrf_key():
    ensure_private_dir()
    path = PKG_VAR / "csrf.key"
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    except FileExistsError:
        pass
    except OSError:
        pass
    try:
        os.chmod(path, 0o600)
        data = path.read_bytes()
        if len(data) == 32:
            return data
    except OSError:
        pass
    raise RuntimeError("无法建立套件私有 CSRF 金鑰")


def new_csrf(owner):
    payload = str(int(time.time())) + "." + secrets.token_urlsafe(16)
    sig = hmac.new(csrf_key(), (owner + "\n" + payload).encode(), hashlib.sha256).hexdigest()
    return payload + "." + sig


def valid_csrf(owner, token):
    try:
        ts, nonce, sig = token.split(".", 2)
        if abs(int(time.time()) - int(ts)) > 3600 or len(nonce) < 16:
            return False
        payload = ts + "." + nonce
        expected = hmac.new(csrf_key(), (owner + "\n" + payload).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def same_origin():
    origin = os.environ.get("HTTP_ORIGIN", "")
    host = os.environ.get("HTTP_HOST", "")
    if not origin or not host or len(host) > 255 or any(c in host for c in "\r\n/\\"):
        return False
    scheme = "https" if os.environ.get("HTTPS", "").lower() in ("on", "1", "https") else "http"
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        return parsed.scheme == scheme and parsed.netloc.lower() == host.lower() and parsed.path in ("", "/") and not parsed.query and not parsed.fragment
    except Exception:
        return False


def json_out(data, status="200 OK"):
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(("Status: " + status + "\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: SAMEORIGIN\r\n\r\n").encode())
    sys.stdout.buffer.write(body)


def text_out(text, status="200 OK", ctype="text/html; charset=utf-8", nonce=""):
    csp = "default-src 'self'; connect-src 'self'; style-src 'nonce-" + nonce + "'; script-src 'nonce-" + nonce + "'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
    sys.stdout.write("Status: " + status + "\r\nContent-Type: " + ctype + "\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nX-Frame-Options: SAMEORIGIN\r\nContent-Security-Policy: " + csp + "\r\nReferrer-Policy: same-origin\r\n\r\n")
    sys.stdout.write(text)


def source_by_id(db, source_id):
    """Return a decrypted data source, or None when it no longer exists."""
    if not isinstance(source_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", source_id):
        return None
    row = db.execute("SELECT id,owner,name,host,port,db_user,db_password FROM sources WHERE id=?", (source_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"], "owner": row["owner"], "name": row["name"],
        "host": row["host"] or "", "port": int(row["port"] or 3306),
        "db_user": row["db_user"], "db_password": decrypt_secret(row["db_password"]),
    }


def owned_source(db, owner, source_id):
    source = source_by_id(db, source_id)
    if not source or source["owner"] != owner:
        raise ValueError("数据源不存在或已被删除，请重新选择")
    return source


def source_list(db, owner):
    rows = db.execute("SELECT id,name,host,port,db_user FROM sources WHERE owner=? ORDER BY name,id", (owner,)).fetchall()
    return [{"id": r["id"], "name": r["name"], "host": r["host"] or "", "port": int(r["port"] or 3306), "db_user": r["db_user"]} for r in rows]


def encryption_key():
    ensure_private_dir()
    key_path = PKG_VAR / "encryption.key"
    try:
        fd = os.open(str(key_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_hex(32).encode("ascii") + b"\n" + secrets.token_hex(32).encode("ascii") + b"\n")
    except FileExistsError:
        pass
    os.chmod(key_path, 0o600)
    lines = key_path.read_text("ascii").splitlines()
    if len(lines) != 2 or any(not re.fullmatch(r"[0-9a-f]{64}", x) for x in lines):
        raise RuntimeError("本机加密金鑰格式错误")
    return key_path, bytes.fromhex(lines[0]), bytes.fromhex(lines[1])


def openssl_path():
    for candidate in ("/usr/bin/openssl", "/bin/openssl", "/usr/local/bin/openssl"):
        if os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("找不到 OpenSSL；无法安全保存数据库密码")


def encrypt_secret(value):
    key_path, _aes_key, mac_key = encryption_key()
    p = subprocess.run([openssl_path(), "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "200000", "-pass", "file:" + str(key_path)], input=value.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if p.returncode:
        raise RuntimeError("数据库密码加密失败")
    tag = hmac.new(mac_key, p.stdout, hashlib.sha256).hexdigest()
    import base64
    return "v1:" + base64.b64encode(p.stdout).decode("ascii") + ":" + tag


def decrypt_secret(value):
    if not value.startswith("v1:"):
        raise RuntimeError("已保存的数据库密码格式不安全，请重新保存数据库连接")
    try:
        import base64
        _version, encoded, tag = value.split(":", 2)
        ciphertext = base64.b64decode(encoded, validate=True)
        key_path, _aes_key, mac_key = encryption_key()
        expected = hmac.new(mac_key, ciphertext, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(tag, expected):
            raise RuntimeError("数据库密码完整性检查失败")
        p = subprocess.run([openssl_path(), "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", "file:" + str(key_path)], input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=False)
        if p.returncode:
            raise RuntimeError("数据库密码解密失败")
        return p.stdout.decode("utf-8")
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("数据库密码解密失败")


def client_candidates(dump=False):
    names = ("mariadb-dump", "mysqldump") if dump else ("mariadb", "mysql")
    roots = [
        "/var/packages/MariaDB10/target/usr/local/mariadb10/bin",
        "/var/packages/MariaDB10/target/usr/local/bin",
        "/var/packages/MariaDB11/target/usr/local/mariadb11/bin",
        "/var/packages/MariaDB11/target/usr/local/bin",
        "/usr/local/mariadb10/bin",
        "/usr/local/mariadb11/bin",
        "/usr/bin",
        "/bin",
    ]
    return [str(Path(root) / name) for root in roots for name in names if os.access(str(Path(root) / name), os.X_OK)]


def quote_option(value):
    if any(ord(ch) < 32 and ch not in "\t" for ch in value) or "\x00" in value:
        raise ValueError("数据库账号或密码包含不支持的控制字元")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t") + '"'


def make_option_file(profile):
    ensure_private_dir()
    fd, path = __import__("tempfile").mkstemp(prefix="mysql-", suffix=".cnf", dir=str(PKG_VAR))
    os.fchmod(fd, 0o600)
    try:
        text = "[client]\nuser=" + quote_option(profile["db_user"]) + "\npassword=" + quote_option(profile["db_password"]) + "\ndefault-character-set=utf8mb4\n"
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    except Exception:
        try: os.close(fd)
        except OSError: pass
        try: os.unlink(path)
        except OSError: pass
        raise


def run_client(cmd, args, timeout=15):
    """Run a MariaDB/MySQL client, dropping --connect-timeout if it is unknown.

    --connect-timeout is a mysql/mariadb *client* option. mariadb-dump rejects it
    with "unknown variable 'connect-timeout'", so it must never reach a dump
    command line. Older clients are handled by retrying without the option.
    """
    result = None
    for extra in (args, [a for a in args if not a.startswith("--connect-timeout")]):
        result = subprocess.run(cmd + extra, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
        if result.returncode == 0 or b"connect-timeout" not in (result.stderr or b""):
            return result
    return result


def connection(profile):
    """Build a working client command line for a local or a remote database.

    The returned command is shared with mariadb-dump, so it may only contain
    options that both the client and the dump tool understand.
    """
    clients = client_candidates(False)
    if not clients:
        raise RuntimeError("找不到 mariadb/mysql 客户端；请在套件中心安装 MariaDB 10 或 11（备份远程数据库也需要它提供客户端工具）")
    option_file = make_option_file(profile)
    host = (profile.get("host") or "").strip()
    port = int(profile.get("port") or 3306)
    candidates = []
    if host:
        for client in clients:
            candidates.append([client, "--defaults-extra-file=" + option_file, "--protocol=tcp",
                               "--host=" + host, "--port=" + str(port)])
        last = "无法连接到远程数据库 " + host + ":" + str(port) + "。请检查地址、端口、防火墙与账号权限。"
    else:
        sockets = ["/run/mysqld/mysqld10.sock", "/run/mysqld/mysqld.sock", "/var/run/mysqld/mysqld10.sock"]
        for client in clients:
            for port_candidate in (3307, 3306):
                for loop in ("127.0.0.1", "localhost"):
                    candidates.append([client, "--defaults-extra-file=" + option_file, "--protocol=tcp", "--host=" + loop, "--port=" + str(port_candidate)])
            for sock in sockets:
                if os.path.exists(sock):
                    candidates.append([client, "--defaults-extra-file=" + option_file, "--protocol=socket", "--socket=" + sock])
        last = "无法连接到本机 MariaDB。"
    for cmd in candidates:
        try:
            r = run_client(cmd, ["--connect-timeout=10", "--batch", "--skip-column-names", "--execute", "SELECT 1"], timeout=15)
            if r.returncode == 0:
                return cmd, option_file
            err = r.stderr.decode("utf-8", "replace").strip()
            if err:
                last = err.replace(profile["db_password"], "[已隐藏]")[:350]
        except subprocess.TimeoutExpired:
            last = "连接超时。"
    try: os.unlink(option_file)
    except OSError: pass
    raise RuntimeError(last)


def run_sql(profile, sql):
    cmd, option_file = connection(profile)
    try:
        p = run_client(cmd, ["--connect-timeout=10", "--batch", "--skip-column-names", "--execute", sql], timeout=60)
        if p.returncode:
            err = p.stderr.decode("utf-8", "replace").strip().replace(profile["db_password"], "[已隐藏]")
            raise RuntimeError(err[:500] or "MariaDB 查询失败")
        return p.stdout.decode("utf-8", "replace").splitlines()
    finally:
        try: os.unlink(option_file)
        except OSError: pass


def sql_ident(name):
    return "`" + name.replace("`", "``") + "`"


def list_databases(profile):
    return [x for x in run_sql(profile, "SHOW DATABASES") if x and x not in SYSTEM_DATABASES]


def list_tables(profile, database):
    if database not in list_databases(profile):
        raise ValueError("数据库不存在或当前账号没有权限")
    rows = run_sql(profile, "SHOW FULL TABLES FROM " + sql_ident(database))
    return [x.split("\t", 1)[0] for x in rows if x]


def task_rows(db, owner):
    rows = db.execute("SELECT t.*, s.name AS source_name FROM tasks t LEFT JOIN sources s ON s.id=t.source_id WHERE t.owner=? ORDER BY t.name,t.id", (owner,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["databases"] = json.loads(item.pop("databases_json"))
        item["enabled"] = bool(item["enabled"])
        item["manual_only"] = bool(item.get("manual_only", 0))
        item["interval_value"] = int(item.get("interval_value", 1))
        item["interval_unit"] = item.get("interval_unit", "hours")
        item["source_id"] = item.get("source_id") or ""
        item["source_name"] = item.get("source_name") or ""
        item["queued"] = bool(item.get("run_requested", 0))
        item.pop("run_requested", None)
        out.append(item)
    return out


def api_status(owner):
    db = connect_db()
    try:
        return {"ok": True, "sources": source_list(db, owner), "tasks": task_rows(db, owner)}
    finally:
        db.close()


def read_json():
    try:
        length = int(os.environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
            raise ValueError("请求格式错误")
    if length < 1 or length > MAX_BODY:
        raise ValueError("请求大小不正确")
    raw = sys.stdin.buffer.read(length)
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("请求格式不正确")
    return obj


def safe_target(value):
    if not isinstance(value, str) or len(value) > 2048 or "\x00" in value or "\\" in value:
        raise ValueError("备份目录路径不正确")
    if not value.startswith("/") or ".." in value.split("/") or os.path.normpath(value) != value.rstrip("/"):
        raise ValueError("备份目录不能包含上层路径")
    lexical = Path(value)
    current = Path("/")
    for part in lexical.parts[1:]:
        current = current / part
        if os.path.islink(current):
            raise ValueError("备份目录不能经过符号链接")
    real = os.path.realpath(value)
    if not re.fullmatch(r"/volume[0-9]+/.+", real):
        raise ValueError("请选择 volume 内的共享文件夹")
    if real != value:
        raise ValueError("备份目录必须使用实际路径，不能使用别名或符号链接")
    if not os.path.isdir(real) or not os.access(real, os.W_OK | os.X_OK, effective_ids=True):
        raise ValueError("套件服务账号 dbbackup 无法写入所选目录；请给该账号授予共享文件夹读写权限后重试")
    return real


def normalize_host(value):
    """Empty host means the local NAS MariaDB; otherwise an IP or DNS name."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("服务器地址格式不正确")
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if len(value) > 255 or value.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
        raise ValueError("服务器地址只能填写 IP 或域名，例如 192.168.1.10 或 db.example.com")
    return value


def validate_selection(profile, payload):
    raw = payload.get("databases")
    if not isinstance(raw, list) or not raw or len(raw) > 200:
        raise ValueError("请选择至少一个数据库")
    available = set(list_databases(profile))
    seen = set()
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("数据库选择格式不正确")
        name = item.get("name")
        if not isinstance(name, str) or name not in available or name in seen:
            raise ValueError("所选数据库不存在或重复")
        seen.add(name)
        tables = item.get("tables", [])
        if not isinstance(tables, list) or len(tables) > 10000:
            raise ValueError("数据表选择格式不正确")
        all_tables = set(list_tables(profile, name))
        if any(not isinstance(t, str) or t not in all_tables for t in tables) or len(set(tables)) != len(tables):
            raise ValueError("所选数据表不存在或重复")
        if tables and (name.startswith("-") or any(t.startswith("-") for t in tables)):
            raise ValueError("MariaDB 备份工具不支持以连字符开头的数据库或数据表名称")
        result.append({"name": name, "tables": tables})
    return result


def handle_post(owner, req):
    action = req.get("action")
    db = connect_db()
    try:
        if action == "tables":
            source = owned_source(db, owner, req.get("source_id"))
            name = req.get("database", "")
            if not isinstance(name, str) or len(name) > 128:
                raise ValueError("数据库名稱不正确")
            return {"ok": True, "tables": list_tables(source, name)}
        if action == "databases":
            source = owned_source(db, owner, req.get("source_id"))
            return {"ok": True, "databases": [{"name": x} for x in list_databases(source)]}
        if action == "save_source":
            name = req.get("name") or ""
            if not isinstance(name, str) or len(name) > 60 or any(ord(c) < 32 for c in name):
                raise ValueError("数据源名称格式不正确")
            host = normalize_host(req.get("host"))
            port = req.get("port", 3306)
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
                raise ValueError("端口必须在 1 到 65535 之间")
            user = req.get("db_user", "")
            password = req.get("db_password", "")
            if not isinstance(user, str) or not user or len(user) > 128 or any(ord(c) < 32 for c in user):
                raise ValueError("请输入有效的数据库账号")
            if not isinstance(password, str) or len(password) > 1024 or "\x00" in password:
                raise ValueError("数据库密码格式不正确")
            source_id = req.get("id") or ""
            if source_id:
                if not isinstance(source_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", source_id):
                    raise ValueError("数据源编号不正确")
                row = db.execute("SELECT owner,db_password FROM sources WHERE id=?", (source_id,)).fetchone()
                if not row or row["owner"] != owner:
                    raise ValueError("找不到此数据源")
                if not password:
                    password = decrypt_secret(row["db_password"])
            else:
                source_id = str(uuid.uuid4())
            if not password:
                raise ValueError("首次设置时请输入数据库密码")
            profile = {"host": host, "port": port, "db_user": user, "db_password": password}
            # Only persist after the credentials are proven to work.
            found = list_databases(profile)
            if not name:
                name = "本机 MariaDB" if not host else host
            db.execute("INSERT INTO sources(id,owner,name,host,port,db_user,db_password,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,host=excluded.host,port=excluded.port,db_user=excluded.db_user,db_password=excluded.db_password,updated_at=excluded.updated_at",
                       (source_id, owner, name, host, port, user, encrypt_secret(password), dt.datetime.now(dt.timezone.utc).isoformat()))
            db.commit()
            return {"ok": True, "id": source_id, "databases": [{"name": x} for x in found]}
        if action == "delete_source":
            source_id = req.get("id")
            if not isinstance(source_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", source_id):
                raise ValueError("数据源编号不正确")
            if not db.execute("SELECT 1 FROM sources WHERE id=? AND owner=?", (source_id, owner)).fetchone():
                raise ValueError("找不到此数据源")
            used = db.execute("SELECT COUNT(*) FROM tasks WHERE owner=? AND source_id=?", (owner, source_id)).fetchone()[0]
            if used:
                raise ValueError("还有 " + str(used) + " 个备份计划在使用此数据源，请先删除或改到其他数据源")
            db.execute("DELETE FROM sources WHERE id=? AND owner=?", (source_id, owner))
            db.commit()
            return {"ok": True}
        if action == "check_target":
            target = safe_target(req.get("target"))
            return {"ok": True, "target": target}
        if action == "backup_now":
            source = owned_source(db, owner, req.get("source_id"))
            target = safe_target(req.get("target"))
            databases = validate_selection(source, req)
            task_id = str(uuid.uuid4())
            name = req.get("name", "立即备份")
            if not isinstance(name, str) or len(name) > 80 or any(ord(c) < 32 for c in name):
                name = "立即备份"
            db.execute("INSERT INTO tasks(id,owner,name,target,source_id,databases_json,frequency,weekday,run_time,interval_value,interval_unit,startup_delay,retention_count,enabled,manual_only,next_run,run_requested,last_message) VALUES(?,?,?,?,?,?,'interval',0,'00:00',1,'hours',0,0,0,1,NULL,1,'等待立即执行')", (task_id, owner, name or "立即备份", target, source["id"], json.dumps(databases, ensure_ascii=False, separators=(",", ":"))))
            db.commit()
            return {"ok": True, "id": task_id}
        if action == "save_task":
            source = owned_source(db, owner, req.get("source_id"))
            target = safe_target(req.get("target"))
            databases = validate_selection(source, req)
            freq = req.get("frequency")
            if freq not in ("daily", "weekly", "interval", "startup"):
                raise ValueError("备份方式不正确")
            weekday = req.get("weekday", 0)
            delay = req.get("startup_delay", 5)
            retention_count = req.get("retention_count", 0)
            if not isinstance(weekday, int) or not 0 <= weekday <= 6:
                raise ValueError("星期设置不正确")
            if not isinstance(delay, int) or not 0 <= delay <= 1440:
                raise ValueError("开机延迟必须在 0 到 1440 分钟之间")
            if not isinstance(retention_count, int) or not 0 <= retention_count <= 1000:
                raise ValueError("保留份数必须在 0 到 1000 之间")
            interval_value = req.get("interval_value", 1)
            interval_unit = req.get("interval_unit", "hours")
            if not isinstance(interval_value, int) or interval_unit not in ("minutes", "hours"):
                raise ValueError("间隔设置不正确")
            if interval_value < 1 or interval_value > (10080 if interval_unit == "minutes" else 168):
                raise ValueError("间隔需在 1 分钟到 168 小时之间")
            run_time = req.get("time")
            if freq in ("daily", "weekly") and (not isinstance(run_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", run_time)):
                raise ValueError("请输入有效的执行时间")
            name = req.get("name", "")
            if not isinstance(name, str) or len(name) > 80 or any(ord(c) < 32 for c in name):
                raise ValueError("计划名称格式不正确")
            task_id = req.get("id")
            packed = json.dumps(databases, ensure_ascii=False, separators=(",", ":"))
            if task_id:
                if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", task_id):
                    raise ValueError("计划编号不正确")
                row = db.execute("SELECT id,manual_only FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
                if not row:
                    raise ValueError("找不到此计划")
                # Recalculate the selected recurrence from now. startup_delay is
                # applied only by initialize_boot_schedule() after a NAS reboot.
                values = (name or "数据库备份", target, source["id"], packed, freq, weekday, run_time or "00:00", interval_value, interval_unit, delay, retention_count, task_id, owner)
                if row["manual_only"] and req.get("convert_to_schedule") is True:
                    db.execute("UPDATE tasks SET name=?,target=?,source_id=?,databases_json=?,frequency=?,weekday=?,run_time=?,interval_value=?,interval_unit=?,startup_delay=?,retention_count=?,manual_only=0,enabled=1,run_requested=0,last_message='等待调度',next_run=NULL WHERE id=? AND owner=?", values)
                else:
                    db.execute("UPDATE tasks SET name=?,target=?,source_id=?,databases_json=?,frequency=?,weekday=?,run_time=?,interval_value=?,interval_unit=?,startup_delay=?,retention_count=?,next_run=NULL WHERE id=? AND owner=?", values)
            else:
                task_id = str(uuid.uuid4())
                db.execute("INSERT INTO tasks(id,owner,name,target,source_id,databases_json,frequency,weekday,run_time,interval_value,interval_unit,startup_delay,retention_count,enabled,manual_only,next_run,run_requested,last_message) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,NULL,0,'等待调度')", (task_id, owner, name or "数据库备份", target, source["id"], packed, freq, weekday, run_time or "00:00", interval_value, interval_unit, delay, retention_count))
            db.commit()
            return {"ok": True, "id": task_id}
        task_id = req.get("id")
        if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", task_id):
            raise ValueError("计划编号不正确")
        row = db.execute("SELECT id FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
        if not row:
            raise ValueError("找不到此计划")
        if action == "delete_task":
            db.execute("DELETE FROM tasks WHERE id=? AND owner=?", (task_id, owner))
        elif action == "run_task":
            db.execute("UPDATE tasks SET run_requested=1,last_message='等待立即执行' WHERE id=? AND owner=?", (task_id, owner))
        elif action == "toggle_task":
            enabled = req.get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError("启用状态不正确")
            db.execute("UPDATE tasks SET enabled=?,next_run=NULL WHERE id=? AND owner=?", (1 if enabled else 0, task_id, owner))
        else:
            raise ValueError("不支持的操作")
        db.commit()
        return {"ok": True}
    finally:
        db.close()


def main():
    owner = authenticate()
    if not owner:
        message = "无法验证 DSM 当前的登录会话。套件不需要单獨登录。"
        if len(sys.argv) > 1 and sys.argv[1] == "index":
            body = "<!doctype html><meta charset=utf-8><title>DSM 会话验证</title><h3>" + message + "</h3><p>诊断：" + AUTH_DIAGNOSTIC + "</p><small>DBBackup " + APP_VERSION + "</small>"
            text_out(body, "401 Unauthorized")
        else:
            json_out({"ok": False, "error": message, "diagnostic": AUTH_DIAGNOSTIC, "version": APP_VERSION}, "401 Unauthorized")
        return
    if not application_authorized(owner):
        if len(sys.argv) > 1 and sys.argv[1] == "index":
            text_out("<!doctype html><meta charset=utf-8><title>没有权限</title><p>此套件只允许 DSM administrators 群组使用。</p>", "403 Forbidden")
        else:
            json_out({"ok": False, "error": "此套件只允许 DSM administrators 群组使用"}, "403 Forbidden")
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    if mode == "index":
        nonce = secrets.token_urlsafe(18)
        from urllib.parse import parse_qs
        token = parse_qs(os.environ.get("QUERY_STRING", "")).get("SynoToken", [""])[0]
        if not token or len(token) > 512 or not re.fullmatch(r"[A-Za-z0-9._-]+", token):
            token = ""
        page = HTML.replace("__CSRF__", new_csrf(owner)).replace("__NONCE__", nonce)
        page = page.replace("__SYNO_TOKEN__", json.dumps(token))
        text_out(page, nonce=nonce)
        return
    if mode != "api":
        json_out({"ok": False, "error": "不支持的入口"}, "404 Not Found")
        return
    method = os.environ.get("REQUEST_METHOD", "GET").upper()
    if method == "GET":
        from urllib.parse import parse_qs
        query = parse_qs(os.environ.get("QUERY_STRING", ""))
        action = query.get("action", [""])[0]
        try:
            if action == "status":
                result = api_status(owner)
            elif action == "databases":
                db = connect_db()
                try:
                    result = {"ok": True, "databases": [{"name": x} for x in list_databases(owned_source(db, owner, query.get("source", [""])[0]))]}
                finally:
                    db.close()
            elif action == "tables":
                db = connect_db()
                try:
                    result = {"ok": True, "tables": list_tables(owned_source(db, owner, query.get("source", [""])[0]), query.get("database", [""])[0])}
                finally:
                    db.close()
            else:
                raise ValueError("不支持的操作")
            json_out(result)
        except Exception as e:
            json_out({"ok": False, "error": str(e)[:500]})
        return
    if method != "POST" or not same_origin() or not valid_csrf(owner, os.environ.get("HTTP_X_CSRF_TOKEN", "")):
        json_out({"ok": False, "error": "请求未通过来源或 CSRF 检查"}, "403 Forbidden")
        return
    if os.environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
        json_out({"ok": False, "error": "只接受 JSON 请求"}, "415 Unsupported Media Type")
        return
    try:
        req = read_json()
        action = req.get("action")
        if action == "test_connection":
            db = connect_db()
            try:
                result = {"ok": True, "databases": [{"name": x} for x in list_databases(owned_source(db, owner, req.get("source_id")))]}
            finally:
                db.close()
        else:
            result = handle_post(owner, req)
        json_out(result)
    except Exception as e:
        json_out({"ok": False, "error": str(e)[:500]})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        json_out({"ok": False, "error": "服务器內部错误"}, "500 Internal Server Error")
