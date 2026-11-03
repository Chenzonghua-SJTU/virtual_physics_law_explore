'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    token: '', configured: false, defaults: {}, runs: [], active: null, run: null,
    selected: null, busy: false, connected: false, timer: null, generation: 0,
    renderedEvents: new Set(), liveIds: new Set(), lastChartSignature: '', toastTimer: null,
    listAt: 0, manuallySelectedLaw: false, lawNames: new Map(),
    deletedRuns: [], historyBusy: null, historyRevision: 0, worlds: [], bodyTime: null,
  };
  const tools = {
    observe_body: '观测公开天体', insert_probe: '投放探针', summarize_data: '分析实验数据',
    fit_law_and_rollout: '拟合候选规律', validate_law: '验证独立轨迹',
    call_back: '查阅实验档案', analyze_residual: '分析预测残差', submit: '提交候选规律',
  };
  const statuses = {
    running: '正在探索', starting: '正在启动', stopping: '正在停止', stopped: '已停止', evaluating: '独立评测中', interrupted: '探索已中断',
    submitted: '已本地受理', accepted: '已本地受理', failed: '探索失败',
    error: '探索失败', incomplete: '探索未完成', completed: '已结束', finished: '已结束',
  };
  const errors = {
    missing_api_key: '请填写 API 密钥，或在启动实验台时配置 DEEPSEEK_API_KEY。',
    invalid_api_key: 'API 密钥格式不正确，请重新填写。',
    invalid_run_configuration: '实验配置无效，请检查模型、随机种子和预算。',
    run_already_active: '已有探索正在进行，请等待结束或先停止当前探索。',
    run_is_active: '正在运行的会话不能删除，请先等待结束或停止探索。',
    run_already_exists: '历史会话中已存在相同编号，暂时无法恢复，请刷新列表。',
    invalid_session_token: '实验台连接已更新，请点击“重新连接”后再试。',
    run_not_found: '找不到这次探索记录，请刷新历史会话。',
    server_error: '实验台暂时无法完成请求，请稍后重试。',
    invalid_model: '模型名称无效，请检查后重试。',
    invalid_world_id: '实验世界无效，请重新选择世界后再试。',
    invalid_seed: '随机种子超出允许范围，请检查后重试。',
    invalid_max_total_tokens: 'Token 预算超出允许范围，请检查后重试。',
    invalid_output_budget: '单次输出上限应在 64–393,216 之间。',
    invalid_budget: 'Token 预算应在 1,000–10,000,000 之间。',
  };
  const colors = ['#377e8a', '#6c8c6a', '#9b7760', '#65819d', '#9b8b4d', '#8c7a9a', '#588f87', '#b27e64'];
  const modes = {autonomous_discovery: '自主探索', manual_engineering_smoke: '手工工程检查', standalone_analyst_diagnostic: '历史分析诊断', historical_unverified: '早期记录'};
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const number = (v) => finite(v) ? new Intl.NumberFormat('en-US').format(v) : '—';
  const compact = (v) => !finite(v) ? '—' : v >= 1000000 ? `${(v / 1000000).toFixed(v % 1000000 ? 2 : 0)}M` : v >= 10000 ? `${(v / 1000).toFixed(v % 1000 ? 1 : 0)}k` : number(v);
  const scientific = (v) => !finite(v) ? '—' : v === 0 ? '0' : Math.abs(v) < .001 || Math.abs(v) >= 10000 ? v.toExponential(3) : Number(v.toPrecision(5)).toString();
  const asArray = (v) => Array.isArray(v) ? v : [];
  const isRunning = (r) => Boolean(r && (r.running || ['running', 'starting', 'stopping'].includes(r.status)));
  const statusLabel = (s) => statuses[s] || '已结束';
  const scoreNumber = (value) => finite(value) ? value.toFixed(2) : '—';
  function hasScore(run) {
    return run?.evaluation_state === 'scored' && run.evaluation_score?.status === 'scored'
      && finite(run.evaluation_score.total);
  }
  function runLabel(run, compactScore = false) {
    if (hasScore(run)) return compactScore ? `${scoreNumber(run.evaluation_score.total)} 分`
      : `得分 ${scoreNumber(run.evaluation_score.total)} / ${number(run.evaluation_score.maximum)}`;
    const labels = {pending: '已提交 · 待测评', running: '独立测评中', error: '测评异常',
      unavailable: '评分数据不足', scored: '评分数据不足'};
    return labels[run?.evaluation_state] || statusLabel(run?.status);
  }
  function runTone(run) {
    if (hasScore(run)) return 'scored';
    if (run?.evaluation_state === 'error') return 'bad';
    if (run?.evaluation_state === 'running' || run?.evaluation_state === 'pending' || isRunning(run)) return 'live';
    return ['failed', 'error'].includes(run?.status) ? 'bad' : '';
  }
  function scoreExplanation(run) {
    if (hasScore(run)) return run.evaluation_score.reason === 'candidate_prediction_invalid'
      ? '候选预测无效或超时，预测分按题目计为 0；声明仍单独计分。使用本地隐藏测试集，非官方成绩。'
      : '按题目公式与本地隐藏测试集计分；不是官方成绩，也不评价物理解释的质量。';
    return {pending: '提交已受理，等待独立测评计算得分。', running: '正在对最终提交进行独立测评，完成后显示得分。',
      error: '独立测评发生异常，暂不展示得分。', unavailable: '当前记录缺少计算题目得分所需的数据，未将缺失项记为零。',
      scored: '当前评分记录不完整，暂不展示得分。'}[run?.evaluation_state]
      || '提交已受理；独立测评得分以评测记录为准。';
  }
  const worldLabel = (run) => state.worlds.find((world) => world.id === (run?.world_id || 'world_1'))?.name || run?.world_name || '世界 01';
  const node = (tag, className, content) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content != null) el.textContent = content;
    return el;
  };
  function printable(value) {
    return JSON.stringify(value, (key, item) => ['reasoning_content', 'api_key', 'authorization', 'token'].includes(key.toLowerCase()) ? undefined : item, 2);
  }
  function updateLawNames(run) {
    const fitted = asArray(run.events).filter((event) => event.kind === 'tool_result' && event.tool === 'fit_law_and_rollout' && event.ok !== false).map((event) => event.data?.law_id);
    const ids = [...new Set([...fitted, ...asArray(run.records?.laws).map((law) => law.law_id)])].filter((id) => typeof id === 'string' && /^law_[A-Za-z0-9_]+$/.test(id));
    // New sessions already have readable canonical IDs. Reserve them before aliasing old records.
    for (const id of ids) if (/^law_\d+$/.test(id)) state.lawNames.set(id, id);
    const used = new Set(state.lawNames.values());
    let next = 1;
    for (const id of ids) {
      if (state.lawNames.has(id)) continue;
      while (used.has(`law_${next}`)) next += 1;
      const name = `law_${next}`;
      state.lawNames.set(id, name); used.add(name);
    }
  }
  function lawName(id) { return state.lawNames.get(id) || id; }
  function displayLawText(value) {
    // Only replace whole known identifiers in prose, never identifier substrings or formula/code spans.
    return value.split(/(```[\s\S]*?```|`[^`]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g).map((part, index) => {
      if (index % 2) {
        const reference = /^`(law_[A-Za-z0-9_]+)`$/.exec(part);
        return reference ? `\`${lawName(reference[1])}\`` : part;
      }
      return part.replace(/(^|[^A-Za-z0-9_])law_[A-Za-z0-9_]+(?=$|[^A-Za-z0-9_])/g, (match, prefix) => prefix + lawName(match.slice(prefix.length)));
    }).join('');
  }
  function displayLawRecord(value, key = '') {
    if (['law_spec', 'ax', 'ay', 'formula', 'expression', 'code', 'source', 'fitted_parameters', 'parameter_spec'].includes(key)) return value;
    if (typeof value === 'string') return displayLawText(value);
    if (Array.isArray(value)) return value.map((item) => displayLawRecord(item, key));
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, item]) => [lawName(name), displayLawRecord(item, name)]));
    return value;
  }
  function displayPrintable(value) { return printable(displayLawRecord(value)); }
  function errorMessage(error) {
    if (error.name === 'AbortError') return '实验台响应超时，请检查本地服务是否仍在运行。';
    return errors[error.code] || error.message || '请求失败，请重试。';
  }
  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(path, {...options, signal: controller.signal, cache: 'no-store', headers: {
        ...(options.method ? {'Content-Type': 'application/json', 'X-Session-Token': state.token} : {}),
        ...options.headers,
      }});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error('实验台返回了无法读取的数据，请重新连接。'); }
      if (!response.ok) {
        const err = new Error(errors[data.error] || `请求未完成（HTTP ${response.status}）。`);
        err.code = data.error;
        throw err;
      }
      return data;
    } catch (error) {
      if (error instanceof TypeError) throw new Error('无法连接本地实验台，请确认启动命令仍在运行。');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function toast(message) {
    $('toast').textContent = message;
    $('toast').hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6000);
  }
  function connectionError(message) {
    $('connection-message').textContent = message;
    $('connection-banner').hidden = false;
  }
  function setFormState() {
    const active = Boolean(state.active);
    $('start-button').disabled = !state.connected || active || state.busy || Boolean(state.historyBusy);
    $('start-button').querySelector('span').textContent = state.busy ? '正在启动…' : active ? '探索正在进行' : '开始探索';
    $('stop-button').hidden = !active;
    $('stop-button').lastChild.textContent = state.active && state.selected !== state.active ? '停止正在运行的探索' : '停止本次探索';
    $('stop-button').disabled = state.busy || (state.run?.id === state.active && state.run?.status === 'stopping');
    for (const id of ['model', 'api-key', 'world-select', 'noise', 'thinking', 'seed', 'max-tokens', 'output-tokens']) $(id).disabled = active || state.busy;
  }
  function formatDate(value) {
    if (!value) return '时间未记录';
    const date = new Date(typeof value === 'number' ? value * (value < 1e12 ? 1000 : 1) : value);
    if (Number.isNaN(date.getTime())) return '时间未记录';
    return new Intl.DateTimeFormat('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false}).format(date);
  }
  function renderHistory() {
    const list = $('history-list');
    const scrollTop = list.scrollTop, scrollLeft = list.scrollLeft;
    list.replaceChildren();
    if (!state.runs.length) list.append(node('p', 'muted small', state.deletedRuns.length ? '暂无历史会话，可从回收站恢复。' : '尚无探索记录，开始你的第一次实验。'));
    for (const run of state.runs) {
      const row = node('div', 'history-row');
      const button = node('button', `history-item${run.id === state.selected ? ' selected' : ''}`);
      button.type = 'button';
      button.disabled = Boolean(state.historyBusy);
      button.setAttribute('aria-pressed', String(run.id === state.selected));
      button.title = run.id;
      const top = node('span', 'history-item-top');
      const label = runLabel(run, true);
      top.append(node('span', 'history-item-date', formatDate(run.created_at)));
      top.append(node('span', `history-state ${runTone(run)}`, label));
      const bottom = node('span', 'history-item-bottom');
      bottom.append(node('span', 'history-id', `${worldLabel(run)} · ${modes[run.mode] || '探索记录'}`));
      bottom.append(node('span', '', finite(run.energy_remaining) ? `${number(run.energy_remaining)} 能量` : '查看记录'));
      button.append(top, bottom);
      button.addEventListener('click', () => selectRun(run.id));
      const remove = node('button', 'history-delete');
      remove.type = 'button';
      const active = run.id === state.active || isRunning(run) || run.status === 'evaluating';
      remove.disabled = active || Boolean(state.historyBusy) || !state.connected || state.busy;
      remove.title = active ? '运行中的会话不能删除' : '删除会话，可从回收站恢复';
      remove.setAttribute('aria-label', `删除会话 ${run.id}（可恢复）`);
      if (state.historyBusy?.id === run.id && state.historyBusy.action === 'delete') remove.textContent = '…';
      else {
        const icon = svgNode('svg', {viewBox: '0 0 16 16', 'aria-hidden': 'true'});
        icon.append(svgNode('path', {d: 'M3 4.5h10M6 4.5V2.5h4v2M4.5 5.5l.6 8h5.8l.6-8M6.5 7v4M9.5 7v4'}));
        remove.append(icon);
      }
      remove.addEventListener('click', () => changeHistory('delete', run.id));
      row.append(button, remove); list.append(row);
    }
    list.scrollTop = scrollTop; list.scrollLeft = scrollLeft;
    renderDeleted();
    $('refresh-history').disabled = Boolean(state.historyBusy);
  }
  function renderDeleted() {
    const list = $('deleted-list');
    const scrollTop = list.scrollTop;
    list.replaceChildren();
    $('deleted-count').textContent = String(state.deletedRuns.length);
    if (!state.deletedRuns.length) list.append(node('p', 'muted small', '回收站为空。'));
    for (const run of state.deletedRuns) {
      const row = node('div', 'deleted-item');
      const info = node('div', 'deleted-info');
      info.title = run.id;
      info.append(node('span', 'history-item-date', formatDate(run.created_at)));
      info.append(node('span', 'deleted-meta', `${worldLabel(run)} · ${modes[run.mode] || '探索记录'} · ${runLabel(run, true)}`));
      info.append(node('span', 'deleted-at', `删除于 ${formatDate(run.deleted_at)}`));
      const restore = node('button', 'history-restore', state.historyBusy?.id === run.id && state.historyBusy.action === 'restore' ? '恢复中…' : '恢复');
      restore.type = 'button';
      restore.disabled = Boolean(state.historyBusy) || !state.connected || state.busy;
      restore.setAttribute('aria-label', `恢复会话 ${run.id}`);
      restore.addEventListener('click', () => changeHistory('restore', run.id));
      row.append(info, restore); list.append(row);
    }
    list.scrollTop = scrollTop;
  }
  async function refreshHistory(showFailure = false, duringMutation = false) {
    if (state.historyBusy && !duringMutation) return false;
    const revision = state.historyRevision;
    try {
      const data = await api('/api/runs');
      if (revision !== state.historyRevision) return false;
      state.runs = asArray(data.runs);
      state.deletedRuns = asArray(data.deleted_runs);
      state.active = data.active_run_id || null;
      state.listAt = Date.now();
      renderHistory(); setFormState();
      if (state.selected && !state.runs.some((run) => run.id === state.selected)) await selectRemainingRun();
      return true;
    } catch (error) { if (showFailure) toast(errorMessage(error)); return false; }
  }
  async function selectRemainingRun() {
    const next = state.runs.find((run) => run.id === state.active)
      || state.runs.find((run) => run.mode === 'autonomous_discovery' && ['submitted', 'accepted'].includes(run.status))
      || state.runs[0];
    if (next) await selectRun(next.id);
    else clearSelectedRun();
  }
  function clearSelectedRun() {
    clearTimeout(state.timer); state.generation += 1;
    state.selected = null; state.run = null;
    resetView();
    $('mode-badge').textContent = '准备就绪'; $('mode-badge').className = 'badge badge-neutral';
    $('run-status').textContent = '配置完成后即可开始';
    $('run-status').className = 'status-text';
    $('session-caption').textContent = '选择历史会话，或配置实验开始新的探索。';
    $('wall-clock').textContent = '剩余时间 —';
    $('live-dot').className = 'live-dot'; $('timeline-caption').textContent = '等待探索开始';
    $('export-link').hidden = true; $('export-link').href = '#';
    for (const id of ['energy-value', 'calls-value', 'tokens-value', 'probes-value']) $(id).textContent = '—';
    $('energy-progress').value = 0; $('validations-value').textContent = '0';
    $('calls-limit').textContent = '无次数上限';
    $('calls-note').textContent = '主 Agent 模型请求';
    $('tokens-note').textContent = '累计输入与输出';
    $('tokens-limit').textContent = `/ ${compact(state.defaults.max_total_tokens ?? 2000000)}`;
    renderChart(); renderTimeline([]); renderDiscovery(); renderHistory(); setFormState();
  }
  async function changeHistory(action, id) {
    if (!['delete', 'restore'].includes(action) || state.historyBusy || state.busy || !state.connected) return;
    const run = (action === 'delete' ? state.runs : state.deletedRuns).find((item) => item.id === id);
    if (!run) return;
    if (action === 'delete' && (state.active === id || isRunning(run) || run.status === 'evaluating')) { toast(errors.run_is_active); return; }
    state.historyBusy = {action, id}; state.historyRevision += 1;
    if (action === 'delete' && state.selected === id) { clearTimeout(state.timer); state.generation += 1; }
    renderHistory(); setFormState();
    try {
      await api(`/api/runs/${encodeURIComponent(id)}/${action}`, {method: 'POST', body: '{}'});
      state.historyRevision += 1;
      if (action === 'delete') {
        state.runs = state.runs.filter((item) => item.id !== id);
        state.deletedRuns = [{...run, deleted_at: new Date().toISOString()}, ...state.deletedRuns.filter((item) => item.id !== id)];
        state.liveIds.delete(id);
        if (state.selected === id) await selectRemainingRun();
        toast('会话已移入回收站，随时可以恢复。');
      } else {
        state.deletedRuns = state.deletedRuns.filter((item) => item.id !== id);
        state.runs = [{...run}, ...state.runs.filter((item) => item.id !== id)];
        if (!state.selected) await selectRun(id);
        toast('会话已恢复，可在历史会话中查看。');
      }
      await refreshHistory(true, true);
    } catch (error) {
      await refreshHistory(false, true);
      if (state.selected === id && state.runs.some((item) => item.id === id)) await selectRun(id);
      toast(errorMessage(error));
      if (error.code === 'invalid_session_token') connectionError(errorMessage(error));
    } finally {
      state.historyBusy = null;
      renderHistory(); setFormState();
      const focusTarget = action === 'restore' ? $('deleted-list').querySelector('button') : $('history-list').querySelector('.history-item');
      (focusTarget || $('recycle-bin').querySelector('summary')).focus({preventScroll: true});
    }
  }
  function resetView() {
    state.renderedEvents.clear(); state.lastChartSignature = ''; state.manuallySelectedLaw = false;
    state.bodyTime = null;
    $('body-time-control').hidden = true;
    state.lawNames.clear();
    $('timeline').replaceChildren();
    $('probe-select').replaceChildren(new Option('全部轨迹', 'all'));
    $('law-select').replaceChildren(new Option('尚无拟合规律', ''));
    delete $('probe-select').dataset.keys; delete $('law-select').dataset.keys;
  }
  async function selectRun(id) {
    clearTimeout(state.timer);
    state.generation += 1;
    state.selected = id; state.run = null;
    resetView(); renderHistory();
    $('run-status').textContent = '正在读取探索记录';
    $('run-status').className = 'status-text';
    $('timeline-caption').textContent = '读取中…';
    $('mode-badge').textContent = id === state.active ? '实时探索' : '历史记录';
    $('mode-badge').className = `badge ${id === state.active ? 'badge-live' : 'badge-history'}`;
    $('timeline').append(node('p', 'muted small', '正在读取探索过程…'));
    await pollRun(state.generation);
  }
  async function pollRun(generation) {
    const id = state.selected;
    if (!id || generation !== state.generation) return;
    let shouldContinue = false;
    try {
      const run = await api(`/api/runs/${encodeURIComponent(id)}`);
      if (generation !== state.generation) return;
      state.run = run;
      if (isRunning(run)) { state.active = id; state.liveIds.add(id); }
      else if (state.active === id) state.active = null;
      $('connection-banner').hidden = true;
      renderRun(run);
      shouldContinue = isRunning(run);
      if (Date.now() - state.listAt > 5000 || !shouldContinue) await refreshHistory();
    } catch (error) {
      if (generation !== state.generation) return;
      connectionError(errorMessage(error));
      $('run-status').textContent = '连接中断，正在重试';
      $('run-status').className = 'status-text';
      shouldContinue = error.code !== 'run_not_found';
    }
    if (generation === state.generation && (shouldContinue || state.active)) {
      state.timer = setTimeout(() => pollRun(generation), shouldContinue ? 1000 : 3000);
    }
  }
  function renderRun(run) {
    updateLawNames(run);
    const history = !isRunning(run) && !state.liveIds.has(run.id);
    $('mode-badge').textContent = history ? '历史记录' : isRunning(run) ? '实时探索' : '本次探索';
    $('mode-badge').className = `badge ${history ? 'badge-history' : isRunning(run) ? 'badge-live' : ['failed', 'error'].includes(run.status) ? 'badge-error' : 'badge-neutral'}`;
    $('run-status').textContent = runLabel(run);
    $('run-status').className = `status-text ${runTone(run)}`;
    $('session-caption').textContent = `${history ? '历史会话' : '当前会话'} · ${worldLabel(run)} · ${modes[run.mode] || '探索记录'} · ${formatDate(run.created_at)} · ${run.id}`;
    $('live-dot').className = `live-dot${isRunning(run) ? ' running' : ''}`;
    $('timeline-caption').textContent = history ? '历史记录 · 非实时运行' : run.status === 'stopping' ? '正在停止，请稍候' : isRunning(run) ? '实时更新 · 每秒同步' : '本次探索已结束';
    $('export-link').href = `/api/runs/${encodeURIComponent(run.id)}/export`;
    $('export-link').hidden = false;
    const budget = run.budget || run.result?.budget || {};
    const usage = run.model_usage || run.result?.model_usage || {};
    const config = run.limits || run.config?.model || run.config || {};
    const records = run.records || {};
    $('energy-value').textContent = number(budget.energy_remaining);
    const seconds = budget.wall_seconds_remaining;
    $('wall-clock').textContent = finite(seconds) ? `剩余时间 ${String(Math.floor(Math.max(0, seconds) / 60)).padStart(2, '0')}:${String(Math.floor(Math.max(0, seconds)) % 60).padStart(2, '0')}` : '剩余时间 —';
    $('energy-progress').value = finite(budget.energy_remaining) ? Math.max(0, Math.min(100, budget.energy_remaining)) : 0;
    $('calls-value').textContent = number(usage.calls);
    const legacyAnalystCalls = usage.roles?.analyst?.calls;
    $('calls-note').textContent = finite(legacyAnalystCalls) && legacyAnalystCalls > 0
      ? `含旧版分析子 Agent ${number(legacyAnalystCalls)} 次请求` : '主 Agent 模型请求';
    $('tokens-value').textContent = compact(usage.total_tokens);
    const requestBudget = usage.request_budget;
    $('tokens-note').textContent = requestBudget?.status === 'blocked' && finite(requestBudget.estimated_prompt_tokens)
      ? `剩余 ${compact(requestBudget.available_tokens)} · 下次输入预估 ${compact(requestBudget.estimated_prompt_tokens)}`
      : finite(requestBudget?.reported_prompt_tokens)
        ? `最近输入：预估 ${compact(requestBudget.estimated_prompt_tokens)} / 实际 ${compact(requestBudget.reported_prompt_tokens)}`
        : '累计输入与输出';
    const callLimit = Object.prototype.hasOwnProperty.call(config, 'max_calls') ? config.max_calls : run.max_calls;
    $('calls-limit').textContent = finite(callLimit) && callLimit > 0 ? `/ ${number(callLimit)}` : '无次数上限';
    $('tokens-limit').textContent = `/ ${compact(config.max_total_tokens ?? run.max_total_tokens ?? state.defaults.max_total_tokens ?? 2000000)}`;
    $('probes-value').textContent = number(asArray(records.probes).length);
    $('validations-value').textContent = number(asArray(records.validations).length);
    updateSelectors(records);
    const signature = printable({selectedLaw: $('law-select').value, probes: records.probes, laws: records.laws, validations: records.validations, bodies: run.bodies, body_estimate: run.body_position_estimate, body_source: run.body_position_source, body_observations: records.body_observations});
    if (signature !== state.lastChartSignature) { renderChart(); state.lastChartSignature = signature; }
    renderDiscovery(); renderTimeline(asArray(run.events)); setFormState();
  }
  function updateSelectors(records) {
    const probeSelect = $('probe-select');
    const probeValue = probeSelect.value;
    const probes = asArray(records.probes);
    const probeKeys = probes.map((p) => p.probe_id).join('|');
    if (probeSelect.dataset.keys !== probeKeys) {
      probeSelect.replaceChildren(new Option(`全部轨迹${probes.length ? ` · ${probes.length} 条` : ''}`, 'all'));
      for (const p of probes) probeSelect.append(new Option(p.probe_id, p.probe_id));
      if (probes.some((p) => p.probe_id === probeValue)) probeSelect.value = probeValue;
      probeSelect.dataset.keys = probeKeys;
    }
    const lawSelect = $('law-select');
    const lawValue = lawSelect.value;
    const laws = [...asArray(records.laws)].sort((a, b) => Number(lawName(a.law_id).slice(4)) - Number(lawName(b.law_id).slice(4)));
    const lawKeys = laws.map((l) => l.law_id).join('|');
    if (lawSelect.dataset.keys !== lawKeys) {
      lawSelect.replaceChildren();
      if (!laws.length) lawSelect.append(new Option('尚无拟合规律', ''));
      laws.forEach((law) => lawSelect.append(new Option(lawName(law.law_id), law.law_id)));
      lawSelect.value = state.manuallySelectedLaw && laws.some((l) => l.law_id === lawValue) ? lawValue : laws.at(-1)?.law_id || '';
      lawSelect.dataset.keys = lawKeys;
    }
    if (!state.manuallySelectedLaw && laws.length) {
      const fittedId = asArray(state.run?.events).filter((e) => e.kind === 'tool_result' && e.tool === 'fit_law_and_rollout' && e.ok !== false).at(-1)?.data?.law_id;
      const preferredId = state.run?.result?.submission?.law_id || fittedId;
      if (laws.some((l) => l.law_id === preferredId)) lawSelect.value = preferredId;
    }
  }
  function eventDescription(event) {
    if (event.kind === 'status' && typeof event.content === 'string') {
      const statusMessages = {autonomous_session_started: '实验已启动，Agent 开始读取任务与公开观测。', submission_accepted_locally: '候选规律已被本地受理，会话结束。', accepted_before_stop: '停止前已有提交被本地受理。', stopped_by_user: '已按要求停止探索，实验记录已保留。', model_call_budget_exhausted: '已达到模型调用上限，会话结束。', model_token_budget_exhausted: '剩余 Token 预算不足以继续请求，会话结束。', model_finish_length: '本次回复达到单次输出上限，未执行截断的工具调用。可在高级设置中提高「单次输出上限」后重新探索；仅提高总预算不能解决单次截断。', model_finish_content_filter: '模型回复被内容过滤，未执行该回复中的工具调用。已有记录已保留。', content_filter: '模型回复被内容过滤，未执行该回复中的工具调用。已有记录已保留。'};
      if (statusMessages[event.content]) return statusMessages[event.content];
    }
    if (event.content) return typeof event.content === 'string' ? displayLawText(event.content) : displayPrintable(event.content);
    if (event.error === 'analyst_invalid_json' || event.error?.code === 'analyst_invalid_json') return '旧版分析子 Agent 返回的内容不符合要求的数据格式，本次分析未完成。';
    if (event.error) return displayLawText(typeof event.error === 'string' ? event.error : event.error.message || event.error.code || '该步骤未完成');
    const data = event.data || {};
    if (event.kind === 'tool_start') {
      const args = event.arguments || {};
      if (event.tool === 'insert_probe') return `投放 ${asArray(args.probes).length} 条轨迹 · 每条 ${args.n_samples ?? '—'} 个采样点`;
      if (event.tool === 'fit_law_and_rollout') return `使用 ${asArray(args.train_probe_ids).length} 条训练轨迹拟合候选公式`;
      if (event.tool === 'validate_law') return `使用 ${asArray(args.test_probe_ids).length} 条未参与拟合的轨迹检验预测`;
      return '';
    }
    if (event.kind === 'tool_result') {
      if (event.ok === false) return '执行未成功；Agent 将依据返回结果继续判断。';
      if (data.law_id) return `${lawName(data.law_id)}${data.errors?.overall ? ` · 位置 RMSE ${scientific(data.errors.overall.position_rmse)}` : ''}`;
      if (data.submission_id) return data.status === 'accepted' ? '本地提交已受理；受理仅表示格式与执行检查完成。' : '已收到本地提交检查结果。';
      if (data.probe_ids) return `已取得 ${asArray(data.probe_ids).length} 条轨迹`;
      if (data.observation_id) return `观测记录 ${data.observation_id}`;
      return '已取得执行结果';
    }
    return event.status ? statusLabel(event.status) : '';
  }
  function renderTimeline(events) {
    const timeline = $('timeline');
    const stickBottom = timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 70;
    const firstLoad = state.renderedEvents.size === 0;
    if (firstLoad) timeline.replaceChildren();
    if (!events.length && firstLoad) {
      const empty = node('div', 'timeline-empty');
      empty.append(node('h3', '', !state.selected ? '每一步，都有迹可循。' : isRunning(state.run) ? 'Agent 正在读取任务…' : '暂无过程事件'));
      empty.append(node('p', '', !state.selected ? '开始探索后，观测、拟合与验证过程将在这里记录。' : isRunning(state.run) ? '第一次响应可能需要一些时间。' : '可在轨迹与候选规律中查看已有实验记录。'));
      timeline.append(empty);
    }
    events.forEach((event, index) => {
      const key = event.seq ?? index;
      if (state.renderedEvents.has(key)) return;
      state.renderedEvents.add(key);
      const row = node('article', `timeline-event ${['progress', 'tool_start', 'tool_result', 'status'].includes(event.kind) ? event.kind : 'progress'}${event.ok === false ? ' failed' : ''}`);
      row.append(node('span', 'event-dot'));
      const heading = node('div', 'event-heading');
      let title = event.kind === 'progress' ? 'Agent 进展' : event.kind === 'status' ? '会话状态' : tools[event.tool] || '执行工具';
      if (event.kind === 'tool_start') title += ' · 开始';
      if (event.kind === 'tool_result') title += event.ok === false ? ' · 未完成' : ' · 返回';
      heading.append(node('span', 'event-title', title), node('span', 'event-seq', String(index + 1).padStart(2, '0')));
      row.append(heading);
      const description = eventDescription(event);
      if (description) row.append(node('p', 'event-text', description));
      if (event.tool || event.arguments || event.data) {
        const details = node('details', 'event-detail');
        details.append(node('summary', '', event.tool || '查看记录'));
        details.append(node('pre', '', displayPrintable({arguments: event.arguments, ok: event.ok, data: event.data, error: event.error})));
        row.append(details);
      }
      timeline.append(row);
    });
    $('event-count').textContent = `${events.length} 条`;
    if (stickBottom || firstLoad) timeline.scrollTop = timeline.scrollHeight;
  }
  function currentLaw() { return asArray(state.run?.records?.laws).find((l) => l.law_id === $('law-select').value); }
  function renderDiscovery() {
    const run = state.run;
    const law = currentLaw();
    const submissions = asArray(run?.records?.submissions);
    const accepted = run?.result?.submission?.status === 'accepted' ? run.result.submission
      : submissions.filter((item) => item.status === 'accepted').at(-1);
    $('discovery-empty').hidden = Boolean(law);
    $('discovery-content').hidden = !law;
    if (law) {
      $('law-label').textContent = lawName(law.law_id);
      $('fit-status').textContent = law.converged ? '拟合收敛' : law.fit_status === 'converged' ? '拟合收敛' : '候选结果';
      $('formula-x').textContent = law.law_spec?.ax || '—';
      $('formula-y').textContent = law.law_spec?.ay || '—';
      $('law-parameters').replaceChildren();
      for (const [name, value] of Object.entries(law.fitted_parameters || {})) $('law-parameters').append(node('span', 'parameter-chip', `${name} = ${scientific(value)}`));
      const formulaSource = run?.mode === 'manual_engineering_smoke' ? '开发者给定候选结构 · 手工工程检查'
        : run?.mode === 'autonomous_discovery' ? '公式为 Agent 提出的候选解释' : '公式来源以会话记录为准';
      $('law-train-note').textContent = `基于 ${asArray(law.train_probe_ids).length} 条训练轨迹拟合 · ${formulaSource}`;
      const frozenEstimate = law.body_context || law.body_position_estimate;
      const timeContext = frozenEstimate?.kind === 'observed_body_trajectories'
        || law.body_input_protocol === 'instantaneous_visible_state';
      $('law-body-note').textContent = timeContext
        ? `力律与训练时天体观测快照已冻结（${frozenEstimate?.version || '已保存'}）；验证使用各自记录的当次天体状态。`
        : frozenEstimate
        ? `天体位置固定于 ${frozenEstimate.version} · 来自 ${asArray(frozenEstimate.observation_ids).join('、')}；追加观测不会改变此候选。`
        : '历史候选使用当时保存的天体位置，未记录观测估计版本。';
      $('training-rmse').textContent = scientific(law.errors?.overall?.position_rmse);
      const validation = asArray(run.records?.validations).filter((v) => v.law_id === law.law_id).at(-1);
      $('validation-rmse').textContent = scientific(validation?.errors?.overall?.position_rmse);
      const validationContext = validation?.body_context;
      const contextNote = validationContext?.kind === 'observed_body_trajectories'
        ? ` · 天体状态 ${validationContext.version}，覆盖 t=${asArray(validationContext.time_range).map(scientific).join('–')}` : '';
      $('validation-note').textContent = validation ? `${asArray(validation.test_probe_ids).length} 条未参与该版本拟合的轨迹 · 误差相对观测计算${contextNote}` : '等待独立轨迹验证';
      const submission = accepted || run.result?.submission || submissions.at(-1);
      $('submission-outcome').hidden = !submission || submission.law_id !== law.law_id;
      if (submission) {
        $('submission-outcome').textContent = submission.status === 'accepted'
          ? `${runLabel(run)} · ${scoreExplanation(run)}`
          : '提交尚未被本地受理，请查看过程记录中的检查结果。';
        $('submission-outcome').className = `submission-outcome ${runTone(run)}`;
      }
    }
    // This is the final submitted explanation, even while inspecting a different candidate.
    $('physical-explanation-block').hidden = !accepted;
    const explanation = typeof accepted?.physical_explanation === 'string' ? accepted.physical_explanation : '';
    $('physical-explanation').textContent = accepted
      ? (explanation.trim() ? explanation : '该历史会话未提交物理解释。') : '';
    $('physical-explanation-law').textContent = accepted
      ? `对应最终提交 ${lawName(accepted.law_id)}${law && law.law_id !== accepted.law_id ? ' · 与当前查看的候选规律不同' : ''}` : '';
    const evaluation = run?.evaluation;
    const evaluationVisible = Boolean(evaluation || (run?.evaluation_state && run.evaluation_state !== 'not_applicable'));
    $('evaluation-block').hidden = !evaluationVisible;
    if (evaluationVisible) {
      const score = run?.evaluation_score && typeof run.evaluation_score === 'object' ? run.evaluation_score : null;
      $('evaluation-block').className = `evaluation-block ${runTone(run)}`;
      $('evaluation-summary').textContent = runLabel(run);
      $('evaluation-score').textContent = scoreNumber(hasScore(run) ? score?.total : null);
      $('evaluation-maximum').textContent = number(score?.maximum ?? 100);
      $('evaluation-prediction').textContent = scoreNumber(score?.prediction);
      $('evaluation-law').textContent = scoreNumber(score?.law);
      $('evaluation-conservation').textContent = scoreNumber(score?.conservation);
      $('evaluation-rmse').textContent = scientific(evaluation?.overall?.position_rmse);
      const subject = evaluation?.law_id && law && evaluation.law_id !== law.law_id ? '评测对象为最终提交版本，与当前所选候选不同。' : '评测对象为最终提交版本。';
      const counts = evaluation ? `${evaluation.n_successful ?? '—'} / ${evaluation.n_trajectories ?? '—'} 条未见初态取得有效预测。` : '';
      $('evaluation-note').textContent = `${subject}${counts}${scoreExplanation(run)}`;
      $('evaluation-inputs').textContent = score
        ? `位置 MSE = ${scientific(score.position_mse)} · 参考方差 V = ${scientific(score.reference_variance)} · 归一化误差 e = ${scientific(score.normalized_error)} · 已用能量 E = ${number(score.energy_used)}`
        : '评分输入尚不完整。';
      $('evaluation-claims').replaceChildren();
      const claimNames = {dynamics_order: '动力学阶数', hidden_matter: '隐藏物质', time_dependence: '显式时间依赖'};
      for (const claim of asArray(score?.claim_checks).filter((item) => item && typeof item === 'object')) {
        const value = (item) => typeof item === 'boolean' ? (item ? '是' : '否') : item == null ? '未提供' : String(item);
        $('evaluation-claims').append(node('li', '', `${claimNames[claim.field] || claim.field}：提交 ${value(claim.submitted)}，参考 ${value(claim.expected)} · ${scoreNumber(claim.points)} / 5`));
      }
    }
    const result = run?.result;
    const done = run && !isRunning(run);
    $('run-outcome').hidden = !done;
    if (done) {
      const reason = result?.reason;
      const reasonMap = {
        submission_accepted_locally: '本地受理只确认提交可执行；预测能力应结合独立验证与评测判断。',
        model_call_budget_exhausted: '此历史会话达到当时的模型调用上限；新会话已取消次数限制。',
        token_budget_exhausted: '剩余 Token 预算不足以继续请求。可以调整预算，开启新的探索。',
        model_token_budget_exhausted: '剩余 Token 预算不足以继续请求。可以调整预算，开启新的探索。',
        model_finish_length: '本次回复达到单次输出上限，未执行截断的工具调用。可在高级设置中提高「单次输出上限」后重新探索；仅提高总预算不能解决单次截断。',
        model_finish_content_filter: '模型回复被内容过滤，未执行该回复中的工具调用。已有记录已保留。',
        content_filter: '模型回复被内容过滤，未执行该回复中的工具调用。已有记录已保留。',
        stopped_by_user: '已按要求停止，取得的实验记录已保留。',
        accepted_before_stop: '停止前已有提交被本地受理；可在探索进程中查看对应检查结果。',
        user_requested_stop: '已按要求停止，取得的实验记录已保留。',
        user_stopped: '已按要求停止，取得的实验记录已保留。',
      };
      let message = reasonMap[reason] || (['stopped', 'stopping'].includes(run.status) ? '已停止探索，取得的实验记录已保留。' : ['failed', 'error'].includes(run.status) ? '本次探索未能完成。请查看探索进程中的错误信息，再开启新实验。' : '已有记录已保留，可导出或继续查看各个候选规律。');
      const requestBudget = (run.model_usage || result?.model_usage || {}).request_budget;
      if (reason === 'model_token_budget_exhausted' && requestBudget?.status === 'blocked'
          && finite(requestBudget.available_tokens) && finite(requestBudget.estimated_prompt_tokens)) {
        message = `下一次请求未发送：剩余 ${number(requestBudget.available_tokens)} token，预计输入 ${number(requestBudget.estimated_prompt_tokens)} token，还需至少 ${number(requestBudget.minimum_output_tokens)} token 输出额度。已有记录已保留。`;
      }
      if (reason && !reasonMap[reason] && !['failed', 'error', 'stopped'].includes(run.status)) message += ` 结束原因：${reason}`;
      if (run.evaluation_state && run.evaluation_state !== 'not_applicable') message = scoreExplanation(run);
      $('run-outcome').textContent = `${runLabel(run)} · ${message}`;
      $('run-outcome').className = `run-outcome ${runTone(run)}`;
    }
  }
  function svgNode(tag, attrs, content) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, String(value)));
    if (content != null) el.textContent = content;
    return el;
  }
  const validPoint = (p) => Array.isArray(p) && p.length >= 2 && finite(p[0]) && finite(p[1]);
  function bodySeries(estimate) {
    if (estimate?.kind !== 'observed_body_trajectories') return null;
    const times = asArray(estimate.times), ids = asArray(estimate.body_ids), positions = asArray(estimate.positions);
    if (!times.length || !ids.length || positions.length !== times.length
        || times.some((t, i) => !finite(t) || (i > 0 && t <= times[i - 1]))
        || positions.some((row) => !Array.isArray(row) || row.length !== ids.length || !row.every(validPoint))) return null;
    return {times, ids, positions};
  }
  function bodiesAt(estimate, time) {
    const series = bodySeries(estimate);
    if (!series || !finite(time) || time < series.times[0] || time > series.times.at(-1)) return [];
    const {times, ids, positions} = series;
    const upper = times.findIndex((t) => t >= time);
    const lower = Math.max(0, upper - 1);
    const exact = Math.abs(times[upper] - time) < 1e-9;
    const weight = exact ? 1 : (time - times[lower]) / (times[upper] - times[lower]);
    return ids.map((body_id, index) => ({
      body_id, position_time: time,
      position: exact ? [...positions[upper][index]] : positions[lower][index].map((value, axis) =>
        value + weight * (positions[upper][index][axis] - value)),
      position_standard_error: exact ? estimate.position_standard_errors?.[upper]?.[index] : null,
    }));
  }
  function renderBodyTime(estimate) {
    const series = bodySeries(estimate);
    $('body-time-control').hidden = !series;
    if (!series) return null;
    const start = series.times[0], end = series.times.at(-1);
    const time = finite(state.bodyTime) ? Math.max(start, Math.min(end, state.bodyTime)) : end;
    if (finite(state.bodyTime)) state.bodyTime = time;
    const slider = $('body-time');
    slider.min = start; slider.max = end; slider.value = time;
    slider.disabled = start === end;
    $('body-time-readout').textContent = `t = ${scientific(time)}`;
    const exact = series.times.some((t) => Math.abs(t - time) < 1e-9);
    const origin = exact && time === 0 && Object.keys(estimate.known_initial_positions || {}).length
      ? '已知初始位置' : exact ? '观测时刻' : '观测间线性插值';
    $('body-time-coverage').textContent = `${origin} · 已知位置覆盖 t=${scientific(start)}–${scientific(end)} · 仅在覆盖范围内显示`;
    $('body-time-latest').disabled = state.bodyTime === null;
    return time;
  }
  function renderChart() {
    const svg = $('trajectory-chart');
    svg.replaceChildren();
    const records = state.run?.records || {};
    const law = currentLaw();
    const allProbes = asArray(records.probes);
    const selected = $('probe-select').value;
    const probes = allProbes.filter((p) => selected === 'all' || p.probe_id === selected);
    const validationRollouts = asArray(records.validations).filter((v) => v.law_id === law?.law_id).flatMap((v) => asArray(v.rollouts));
    const predictions = [...asArray(law?.rollouts), ...validationRollouts].filter((r) => probes.some((p) => p.probe_id === r.probe_id));
    const estimate = state.run?.body_position_estimate;
    const series = bodySeries(estimate);
    const bodyTime = renderBodyTime(estimate);
    const bodies = series ? bodiesAt(estimate, bodyTime) : asArray(estimate?.bodies || state.run?.bodies);
    const legacyBodies = state.run?.body_position_source === 'legacy_public_coordinates'
      || (!state.run?.body_position_source && !estimate && bodies.length);
    const frozenEstimate = law?.body_context || law?.body_position_estimate;
    const frozenBodies = series ? bodiesAt(frozenEstimate, bodyTime)
      : asArray(frozenEstimate?.bodies || law?.known_bodies);
    const differentFrozenBodies = frozenBodies.filter((body) => validPoint(body.position) && !bodies.some((current) =>
      current.body_id === body.body_id && validPoint(current.position) && current.position.every((v, i) => Math.abs(v - body.position[i]) < 1e-12)));
    const trails = series ? series.ids.map((body_id, i) => ({body_id, positions: series.positions.map((row) => row[i])})) : [];
    const points = [...probes.flatMap((p) => asArray(p.r_obs)), ...predictions.flatMap((p) => asArray(p.r_pred)),
      ...trails.flatMap((trail) => trail.positions), ...bodies.map((b) => b.position), ...differentFrozenBodies.map((b) => b.position)].filter(validPoint);
    let xMin = -4, xMax = 4, yMin = -2.5, yMax = 2.5;
    if (points.length) {
      xMin = Infinity; xMax = -Infinity; yMin = Infinity; yMax = -Infinity;
      for (const [x, y] of points) { xMin = Math.min(xMin, x); xMax = Math.max(xMax, x); yMin = Math.min(yMin, y); yMax = Math.max(yMax, y); }
      const padX = Math.max((xMax - xMin) * .13, .4), padY = Math.max((yMax - yMin) * .13, .4);
      xMin -= padX; xMax += padX; yMin -= padY; yMax += padY;
    }
    const left = 54, top = 18, width = 640, height = 333;
    // Keep equal scale on both axes so trajectories retain their geometry.
    const xSpan = xMax - xMin, ySpan = yMax - yMin;
    if (xSpan / width > ySpan / height) { const delta = (xSpan / width * height - ySpan) / 2; yMin -= delta; yMax += delta; }
    else { const delta = (ySpan / height * width - xSpan) / 2; xMin -= delta; xMax += delta; }
    const x = (n) => left + (n - xMin) / (xMax - xMin) * width;
    const y = (n) => top + height - (n - yMin) / (yMax - yMin) * height;
    const niceStep = (range, count) => { const raw = range / count; const magnitude = 10 ** Math.floor(Math.log10(raw)); const ratio = raw / magnitude; return (ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 5 ? 5 : 10) * magnitude; };
    const xStep = niceStep(xMax - xMin, 7), yStep = niceStep(yMax - yMin, 5);
    const tickText = (v, step) => { if (Math.abs(v) < step / 100) return '0'; return Math.abs(v) >= 1e5 || Math.abs(v) < .001 ? v.toExponential(1) : Number(v.toFixed(Math.max(0, -Math.floor(Math.log10(step))))).toString(); };
    for (let v = Math.ceil(xMin / xStep) * xStep, i = 0; v <= xMax && i < 30; v += xStep, i++) {
      svg.append(svgNode('line', {x1: x(v), x2: x(v), y1: top, y2: top + height, class: Math.abs(v) < xStep / 100 ? 'chart-axis' : 'chart-grid'}));
      svg.append(svgNode('text', {x: x(v), y: top + height + 21, 'text-anchor': 'middle', class: 'chart-tick'}, tickText(v, xStep)));
    }
    for (let v = Math.ceil(yMin / yStep) * yStep, i = 0; v <= yMax && i < 30; v += yStep, i++) {
      svg.append(svgNode('line', {x1: left, x2: left + width, y1: y(v), y2: y(v), class: Math.abs(v) < yStep / 100 ? 'chart-axis' : 'chart-grid'}));
      svg.append(svgNode('text', {x: left - 13, y: y(v) + 4, 'text-anchor': 'end', class: 'chart-tick'}, tickText(v, yStep)));
    }
    svg.append(svgNode('text', {x: left + width, y: top + height + 41, 'text-anchor': 'end', class: 'chart-axis-label'}, 'x / 环境单位'));
    svg.append(svgNode('text', {x: left, y: top - 8, class: 'chart-axis-label'}, 'y / 环境单位'));
    for (const trail of trails) {
      const path = svgNode('polyline', {points: trail.positions.map((p) => `${x(p[0])},${y(p[1])}`).join(' '),
        fill: 'none', stroke: '#59766d', 'stroke-width': 1.5, 'stroke-dasharray': '3 4', opacity: .65});
      path.append(svgNode('title', {}, `${trail.body_id} · 已取得的天体位置，观测时刻之间以直线连接`));
      svg.append(path);
      for (const [i, point] of trail.positions.entries()) {
        const dot = svgNode('circle', {cx: x(point[0]), cy: y(point[1]), r: 1.7, fill: '#59766d', opacity: .5});
        dot.append(svgNode('title', {}, `${trail.body_id} · t=${scientific(series.times[i])} · 已知位置 (${point.map(scientific).join(', ')})`));
        svg.append(dot);
      }
    }
    for (const probe of probes) {
      const obs = asArray(probe.r_obs).filter(validPoint);
      const color = colors[Math.max(0, allProbes.indexOf(probe)) % colors.length];
      if (obs.length > 1) svg.append(svgNode('polyline', {points: obs.map((p) => `${x(p[0])},${y(p[1])}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 1.4, opacity: .35}));
      for (const [i, point] of obs.entries()) {
        const circle = svgNode('circle', {cx: x(point[0]), cy: y(point[1]), r: i === 0 ? 3.5 : 2.6, fill: color, stroke: '#fff', 'stroke-width': .7});
        circle.append(svgNode('title', {}, `${probe.probe_id} · t=${probe.times?.[i] ?? i}\nx=${scientific(point[0])}, y=${scientific(point[1])}${i === 0 ? ' · 初态' : ''}`));
        svg.append(circle);
      }
    }
    for (const rollout of predictions) {
      const pred = asArray(rollout.r_pred).filter(validPoint);
      if (pred.length > 1) {
        const line = svgNode('polyline', {points: pred.map((p) => `${x(p[0])},${y(p[1])}`).join(' '), fill: 'none', stroke: '#d6a15c', 'stroke-width': 2, 'stroke-dasharray': '6 5', opacity: .9});
        line.append(svgNode('title', {}, `${rollout.probe_id} · 候选规律预测`));
        svg.append(line);
      }
    }
    for (const body of bodies) {
      if (!validPoint(body.position)) continue;
      const bx = x(body.position[0]), by = y(body.position[1]);
      svg.append(svgNode('circle', {cx: bx, cy: by, r: 13, fill: '#edf2ed', opacity: .8}));
      const diamond = svgNode('path', {d: `M ${bx} ${by - 5} L ${bx + 5} ${by} L ${bx} ${by + 5} L ${bx - 5} ${by} Z`, fill: '#31535a'});
      const uncertainty = asArray(body.position_standard_error).length === 2
        ? `\n各坐标标准误：${body.position_standard_error.map(scientific).join(', ')}` : '';
      diamond.append(svgNode('title', {}, `${body.body_id} · ${legacyBodies ? '历史公开坐标' : series ? `t=${scientific(bodyTime)} 的位置` : '观测位置估计'} (${body.position.map(scientific).join(', ')})${body.sample_count ? `\n累计 ${body.sample_count} 个位置样本` : ''}${uncertainty}`));
      svg.append(diamond, svgNode('text', {x: bx + 12, y: by - 10, class: 'body-label'}, body.body_id));
    }
    for (const body of differentFrozenBodies) {
      const bx = x(body.position[0]), by = y(body.position[1]);
      const marker = svgNode('circle', {cx: bx, cy: by, r: 7, fill: 'none', stroke: '#bd8c4d', 'stroke-width': 1.5});
      marker.append(svgNode('title', {}, `${body.body_id} · ${lawName(law.law_id)} ${series ? `训练快照在 t=${scientific(bodyTime)} 的位置` : '冻结的位置'} (${body.position.map(scientific).join(', ')})\n${frozenEstimate?.version || '历史记录未提供观测版本'}`));
      svg.append(marker);
    }
    $('body-legend-label').textContent = legacyBodies ? '历史公开坐标' : series ? `天体 · t=${scientific(bodyTime)}` : '天体位置估计';
    $('body-trail-legend').hidden = !series;
    $('frozen-body-legend').hidden = !differentFrozenBodies.length;
    $('frozen-body-label').textContent = series ? '训练快照同一时刻的位置' : '候选冻结的位置';
    const observationNote = $('body-observation-note');
    const note = series
      ? `天体路径来自已知初态与 ${asArray(estimate.observation_ids).length} 次已取得观测（${estimate.version}）；同一时刻重复观测取均值，时刻之间仅做线性插值，不推断覆盖范围外的位置。`
      : estimate ? `天体位置来自 ${asArray(estimate.observation_ids).length} 次已取得观测的均值（${estimate.version}），位置精度受观测噪声影响。`
      : legacyBodies ? '此历史会话仅保留了旧版公开坐标，无法追溯位置观测估计。'
      : state.run?.body_position_source === 'invalid_observations' ? '天体观测记录不完整，暂无法计算当前位置估计。' : '';
    const frozenNote = series && law ? (frozenBodies.length
      ? ' 候选力律与训练快照保持冻结；验证使用各次验证记录中的天体状态。'
      : ' 当前显示时刻不在候选训练快照覆盖范围内，不显示训练位置标记；验证使用各次验证记录中的天体状态。') : '';
    observationNote.textContent = note + frozenNote + (differentFrozenBodies.length
      ? series ? ` 空心圆为 ${lawName(law.law_id)} 训练快照在同一时刻的位置。`
        : ` 空心圆为 ${lawName(law.law_id)} 冻结的位置，该候选的位置配置保持不变。` : '');
    observationNote.hidden = !observationNote.textContent;
    $('chart-empty').hidden = points.length > 0;
    $('plot-note').textContent = probes.length ? `${probes.reduce((n, p) => n + asArray(p.r_obs).length, 0)} 个观测点 · 等比例坐标` : '自动缩放 · 坐标为环境单位';
    svg.setAttribute('aria-label', `二维轨迹图，${probes.length} 条观测轨迹，${predictions.length} 条候选预测，${bodies.length} 个天体${legacyBodies ? '的历史公开坐标' : series ? `在绝对时间 ${scientific(bodyTime)} 的位置及观测路径` : '的位置估计'}，${differentFrozenBodies.length} 个候选训练位置标记。坐标为环境单位。`);
  }
  async function startRun(event) {
    event.preventDefault();
    if (state.busy || state.active || state.historyBusy || !state.connected) return;
    if (!$('run-form').reportValidity()) return;
    $('form-error').hidden = true;
    if (!$('api-key').value.trim() && !state.configured) {
      $('form-error').textContent = errors.missing_api_key; $('form-error').hidden = false; $('api-key').focus(); return;
    }
    const body = {
      model: $('model').value.trim(), world_id: $('world-select').value, noise: $('noise').checked, seed: Number($('seed').value),
      max_total_tokens: Number($('max-tokens').value), max_tokens_per_call: Number($('output-tokens').value), thinking: $('thinking').checked,
    };
    if ($('api-key').value.trim()) body.api_key = $('api-key').value.trim();
    $('api-key').value = '';
    state.busy = true; setFormState();
    try {
      const data = await api('/api/runs', {method: 'POST', body: JSON.stringify(body)});
      state.active = data.run_id; state.liveIds.add(data.run_id);
      state.busy = false;
      toast('探索已启动，Agent 正在读取任务与初始观测。');
      await selectRun(data.run_id);
      await refreshHistory();
    } catch (error) {
      $('form-error').textContent = errorMessage(error); $('form-error').hidden = false;
      if (error.code === 'invalid_session_token') connectionError(errorMessage(error));
      if (error.code === 'run_already_active') await refreshHistory();
    } finally { delete body.api_key; state.busy = false; setFormState(); }
  }
  async function stopRun() {
    if (!state.active) return;
    $('stop-button').disabled = true;
    try {
      const id = state.active;
      await api(`/api/runs/${encodeURIComponent(id)}/stop`, {method: 'POST', body: '{}'});
      toast('已请求停止探索，已取得的实验记录会保留。');
      await selectRun(id);
    } catch (error) { toast(errorMessage(error)); }
    finally { setFormState(); }
  }
  async function bootstrap() {
    $('reconnect-button').disabled = true;
    try {
      const data = await api('/api/bootstrap');
      state.token = data.token; state.configured = data.api_key_configured; state.defaults = data.defaults || {};
      state.worlds = asArray(data.worlds);
      if (!state.worlds.length) state.worlds = [{id: 'world_1', name: '世界 01'}];
      const selectedWorld = $('world-select').value;
      $('world-select').replaceChildren(...state.worlds.map((world) => new Option(world.name, world.id)));
      $('world-select').value = state.selected && state.worlds.some((world) => world.id === selectedWorld) ? selectedWorld : state.defaults.world_id || 'world_1';
      state.runs = asArray(data.runs); state.deletedRuns = asArray(data.deleted_runs); state.active = data.active_run_id || null; state.connected = true; state.listAt = Date.now();
      $('connection-banner').hidden = true;
      $('key-state').textContent = state.configured ? '服务已配置' : '仅本次使用';
      $('api-key').placeholder = state.configured ? '已配置，可直接开始探索' : '输入 DeepSeek API Key';
      $('key-note').textContent = state.configured ? '可直接使用已配置的密钥，或填入本次使用的密钥。' : '密钥仅用于启动本次探索，不保存在浏览器中。';
      if (!state.selected) {
        $('model').value = state.defaults.model || 'deepseek-flash';
        $('noise').checked = Boolean(state.defaults.noise);
        $('thinking').checked = state.defaults.thinking ?? true;
        $('seed').value = state.defaults.seed ?? 42;
        $('max-tokens').value = state.defaults.max_total_tokens ?? 2000000;
        $('output-tokens').value = state.defaults.max_tokens_per_call ?? 65536;
      }
      renderHistory(); setFormState();
      const requestedId = new URLSearchParams(window.location.search).get('run');
      const linkedId = !state.selected && state.runs.some((r) => r.id === requestedId) ? requestedId : null;
      const preferred = linkedId || state.active || state.selected || state.runs.find((r) => ['submitted', 'accepted'].includes(r.status) && r.mode === 'autonomous_discovery')?.id;
      if (preferred) await selectRun(preferred);
      else { $('run-status').textContent = '配置完成后即可开始'; renderChart(); }
    } catch (error) {
      state.connected = false; setFormState(); connectionError(errorMessage(error));
      $('run-status').textContent = '未连接实验台';
    } finally { $('reconnect-button').disabled = false; }
  }
  $('run-form').addEventListener('submit', (event) => event.preventDefault());
  $('start-button').addEventListener('click', startRun);
  $('stop-button').addEventListener('click', stopRun);
  $('refresh-history').addEventListener('click', () => refreshHistory(true));
  $('reconnect-button').addEventListener('click', bootstrap);
  $('probe-select').addEventListener('change', renderChart);
  $('body-time').addEventListener('input', () => { state.bodyTime = Number($('body-time').value); renderChart(); });
  $('body-time-latest').addEventListener('click', () => { state.bodyTime = null; renderChart(); });
  $('law-select').addEventListener('change', () => { state.manuallySelectedLaw = true; renderChart(); renderDiscovery(); });
  $('scroll-latest').addEventListener('click', () => { $('timeline').scrollTop = $('timeline').scrollHeight; });
  renderChart(); bootstrap();
})();
