'use strict';
const states = {queued:'排队等待',running:'正在探索',evaluating:'交卷后评测',submitted:'已提交',error:'错误',stopped:'已停止',incomplete:'未完成',completed:'已结束',interrupted:'已中断'};
function element(tag, text, cls) {
  const el=document.createElement(tag);
  if(text!==undefined) el.textContent=text;
  if(cls) el.className=cls;
  return el;
}
const number=(value,digits=2)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(digits):'—';
const duration=(seconds)=>typeof seconds==='number'&&Number.isFinite(seconds)?`${Math.floor(Math.round(seconds)/60)}分${Math.round(seconds)%60}秒`:'—';
const studyGroup=batch=>batch.id.match(/^e[4-8](?=-)/i)?.[0]?.toUpperCase()||batch.experiment_group;
const scored=row=>row.evaluation_score?.status==='scored'&&Number.isFinite(row.evaluation_score.total);
let latestBatches=[], lastRefreshed=null;
const query=new URLSearchParams(location.search), requestedBatch=query.get('batch');
const groupSelector=document.getElementById('experiment-group');
if(requestedBatch&&/^[A-Za-z0-9_-]{1,80}$/.test(requestedBatch)){
  const option=element('option',`单批：${requestedBatch}`);
  option.value='batch:'+requestedBatch;groupSelector.append(option);groupSelector.value=option.value;
}else if(['all','E8','E7','E6','E5_AB','E5','E4','E3'].includes(query.get('group'))){
  groupSelector.value=query.get('group');
}
function render(batch) {
  const section=element('section');
  const study=studyGroup(batch);
  const repeat=(batch.id.match(/-s\d+/i)?.[0].slice(1)||batch.id.match(/r\d+$/i)?.[0]||'R01').toUpperCase();
  section.append(element('h2',`${study} · ${batch.model} · ${repeat} · ${states[batch.status]||batch.status}`));
  section.append(element('div',batch.id,'batch-id'));
  section.append(element('p',`${batch.energy_budget} 能量 · ${batch.wall_seconds} 秒探索 · 噪声${batch.noise?'开启':'关闭'} · 思考${batch.thinking?'开启':'关闭'} · 单次输出上限 ${batch.output_limit??'未记录'} token`,'batch-id'));
  if(['E6','E7','E8'].includes(study)) {
    section.append(element('p',`提示词：${batch.guidance_profile??'baseline'} · PySR：${batch.symbolic_regression_enabled?'开启':'关闭'} · 模型 seed：${batch.model_sampling_seed??'未固定'} · 时间预算包含科学工具`,'batch-id'));
    section.append(element('p',`累计 Token 上限：${batch.max_total_tokens===null?'不设上限':batch.max_total_tokens??'未记录'} · 重复调用恢复：${batch.loop_recovery?'开启':'关闭'}`,'batch-id'));
  }else if(batch.experiment_group==='E5') {
    section.append(element('p',`通用数值诊断：${batch.diagnostics_enabled?'开启':'关闭'} · 温度：${batch.model_temperature??'模型默认'} · seed：${batch.model_sampling_seed??'未固定'}`,'batch-id'));
    if(batch.diagnostics_harmonic||batch.diagnostics_on_fit) section.append(element('p',`时间项诊断：${batch.diagnostics_harmonic?'开启':'关闭'} · 拟合残差较大时自动诊断训练数据：${batch.diagnostics_on_fit?'开启':'关闭'}`,'batch-id'));
  }
  const evaluated=batch.worlds.filter(row=>row.evaluation_complete);
  const highScores=evaluated.filter(row=>typeof row.evaluation_score?.total==='number'&&row.evaluation_score.total>=90).length;
  section.append(element('p',`本批达到 90 分：${highScores} / ${batch.worlds.length} 个世界 · 全部测试轨迹预测有效：${evaluated.length} / ${batch.worlds.length}。预测失败时按原记录显示声明分；90 分按原始分数判断。`,'batch-id'));
  const wrap=element('div',undefined,'table-wrap'), table=element('table');
  const head=element('tr');
  for(const title of ['世界','状态','本地总分','位置 RMSE','探索耗时','交卷后评测','总耗时','平均输出 / 轮','单次最大输出','调用数','PySR 调用 / 耗时','测试轨迹','消耗能量']) head.append(element('th',title));
  const thead=element('thead');thead.append(head);table.append(thead);
  const body=element('tbody');
  for(const row of batch.worlds){
    const tr=element('tr'), name=element('td'), link=element('a',row.world_id.replace('world_','世界 0'));
    link.href='/?run='+encodeURIComponent(row.run_id);name.append(link);tr.append(name);
    const predictionFailed=scored(row)&&row.evaluation_score.reason==='candidate_prediction_invalid';
    const status=element('td',predictionFailed?'预测失败 · 按规则计分':states[row.status]||row.status,predictionFailed?'failed':row.status==='submitted'?'submitted':(['running','queued','evaluating'].includes(row.status)?'running':'failed'));
    if(row.reason&&row.status!=='submitted') status.append(element('span',row.reason,'reason'));
    tr.append(status);
    const rmse=row.evaluation_complete?row.independent_rmse?.position_rmse:null;
    const score=scored(row)?row.evaluation_score.total:null;
    const error=typeof rmse==='number'&&Number.isFinite(rmse)?(rmse<0.001?rmse.toExponential(3):rmse.toFixed(4)):'—';
    const terminal=!['queued','running','starting','evaluating'].includes(row.status);
    const average=row.average_output_tokens_per_call??(terminal&&row.calls>0&&row.conservative_reserved_tokens===0?row.completion_tokens/row.calls:null);
    const maxOutput=row.max_call_output_tokens;
    const maximum=typeof maxOutput==='number'?`${maxOutput}${row.output_cap_compliant===false?' ⚠ 超限':batch.experiment_group==='E3'&&maxOutput>4096?'（高于 E4 上限）':''}`:'未记录';
    const sr=row.symbolic_search_calls?`${row.symbolic_search_calls}次 / ${duration(row.symbolic_search_seconds)}`:'—';
    for(const val of [number(score),error,duration(row.exploration_seconds),duration(row.evaluation_seconds),duration(row.wall_seconds_including_evaluation),number(average,1),maximum,row.calls??0,sr,row.n_test_trajectories??'—',number(row.energy_used,0)]) tr.append(element('td',String(val)));
    body.append(tr);
  }
  table.append(body);wrap.append(table);section.append(wrap);return section;
}
function renderAll(){
  const selected=document.getElementById('experiment-group').value;
  const sorted=latestBatches.filter(b=>selected==='all'||studyGroup(b)===selected||selected==='batch:'+b.id||(selected==='E5_AB'&&b.id.startsWith('e5-qwen38-tools-'))).sort((a,b)=>studyGroup(b).localeCompare(studyGroup(a))||a.id.localeCompare(b.id));
  document.getElementById('batches').replaceChildren(...sorted.map(render));
  const rows=sorted.flatMap(b=>b.worlds), completed=rows.filter(r=>r.evaluation_complete).length;
  document.getElementById('connection').textContent=`当前筛选全部测试轨迹预测有效 ${completed} / ${rows.length} · 更新于 ${lastRefreshed??'—'} · 每 5 秒刷新`;
}
document.getElementById('experiment-group').addEventListener('change',renderAll);
async function refresh(){
  try{
    const response=await fetch('/api/baselines');if(!response.ok)throw Error('HTTP '+response.status);
    const data=await response.json();
    latestBatches=data.batches;lastRefreshed=new Date().toLocaleTimeString();renderAll();
  }catch(e){document.getElementById('connection').textContent='连接暂时中断，保留上次结果，正在重试…';}
  setTimeout(refresh,5000);
}
refresh();
