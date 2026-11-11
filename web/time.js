const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
let selected = 120;
let plan = null;
let confirmed = false;

async function api(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}

function today() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function talkUrl(ref) {
  if (!ref) return '/plan.html';
  const i = ref.lastIndexOf(':');
  if (i < 0) return '/plan.html';
  return '/talk.html?paper=' + encodeURIComponent(ref.slice(0, i)) + '&index=' + encodeURIComponent(ref.slice(i + 1));
}

async function queueOpen(id, ev) {
  ev.preventDefault();
  const href = ev.currentTarget.href;
  try {
    await fetch('/api/app/queue/' + encodeURIComponent(id) + '/open', { method: 'POST' });
  } catch (e) {}
  location.href = href;
  return false;
}

async function queueStart(id, ev) {
  ev.preventDefault();
  try {
    await fetch('/api/app/queue/' + encodeURIComponent(id) + '/open', { method: 'POST' });
    await loadPlan();
  } catch (e) {}
  return false;
}

async function queueDone(id, ev) {
  ev.preventDefault();
  try {
    await fetch('/api/app/queue/' + encodeURIComponent(id) + '/done', { method: 'POST' });
    await loadPlan();
  } catch (e) {}
  return false;
}

function itemHtml(it) {
  const tag = it.type === 'review' ? '<span class="tag review">复述</span>'
    : it.type === 'writing' ? '<span class="tag">写作</span>'
    : it.type === 'offline' ? '<span class="tag">自主</span>'
    : it.type === 'buffer' ? '<span class="tag buffer">缓冲</span>'
    : '<span class="tag">新题</span>';
  const title = esc(it.title || (it.type === 'review' ? '到期题' : it.type === 'writing' ? '写作重写' : it.type === 'offline' ? '政治自主复习' : it.type === 'buffer' ? '缓冲/回看' : '下一道新题'));
  const link = it.type === 'review' ? '<a href="' + talkUrl(it.ref_id) + '">去复述</a>'
    : it.type === 'writing' ? '<a href="/writing.html?task=' + encodeURIComponent(it.ref_id || '') + '" data-qid="' + esc(it.id || '') + '" onclick="return queueOpen(this.dataset.qid,event)">去重写</a>'
    : it.type === 'new' ? '<a href="/plan.html">去计划</a>' : '';
  const status = it.status || 'todo';
  const qid = esc(it.id || '');
  const actions = status === 'done'
    ? '<span class="muted">已完成</span>'
    : (status === 'todo' ? '<button class="chip" data-qid="' + qid + '" onclick="return queueStart(this.dataset.qid,event)">开始</button>' : '') +
      '<button class="chip" data-qid="' + qid + '" onclick="return queueDone(this.dataset.qid,event)">完成</button>';
  return '<div class="q-item"><div>' + tag + ' ' + title + '</div><div class="row">' +
    (it.estimate_min || 0) + ' 分钟 ' + link + ' ' + actions + '</div></div>';
}

function render(data) {
  plan = data.plan;
  const carried = data.carried_writing || 0;
  const carryNote = carried ? '<div class="notice">有 ' + carried + ' 篇写作已顺延，今天会按到期重新排。</div>' : '';
  const box = $('#timeResult');
  if (!plan) {
    box.innerHTML = carryNote + '<div class="empty">还没有排今天。选个时长，点「排今天」。</div>';
    $('#confirmBtn').hidden = true;
    $('#planBtn').disabled = false;
    return;
  }
  confirmed = plan.status === 'confirmed';
  $('#planBtn').disabled = confirmed;
  $('#confirmBtn').hidden = confirmed;
  const blocks = data.blocks || [];
  const total = blocks.reduce((n, b) => n + b.minutes, 0);
  const header = '<div class="card" style="margin-bottom:10px;">' +
    '<div class="card-head"><h2>今天队列</h2><span class="count">' +
    (confirmed ? '已确认' : '草稿') + '</span></div>' +
    '<div class="muted">可用 ' + plan.available_min + ' 分钟 · 已排 ' + total + ' 分钟 · 80% 上限</div></div>';
  const body = blocks.map(b => {
    const items = (b.items || []).map(itemHtml).join('');
    return '<div class="block"><div class="block-head"><b>' + esc(b.subject) + '</b>' +
      '<span>' + b.minutes + ' 分钟</span></div>' + items + '</div>';
  }).join('') || '<div class="empty">没有可排的科目块。</div>';
  box.innerHTML = carryNote + header + body;
}

async function loadPlan() {
  try {
    const d = await api('/api/app/time?date=' + today());
    render(d);
  } catch (e) {
    $('#status').textContent = '加载失败：' + e.message;
  }
}

async function generate() {
  const custom = parseInt($('#customMin').value, 10);
  const minutes = Number.isFinite(custom) && custom >= 30 ? custom : selected;
  $('#status').textContent = '排程中…';
  $('#planBtn').disabled = true;
  try {
    const d = await api('/api/app/time', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: today(), available_min: minutes })
    });
    render(d);
    $('#status').textContent = '已出草稿，确认后才写入今天。';
  } catch (e) {
    $('#status').textContent = '排程失败：' + e.message;
  } finally {
    if (!confirmed) $('#planBtn').disabled = false;
  }
}

async function confirmPlan() {
  $('#confirmBtn').disabled = true;
  try {
    const d = await api('/api/app/time/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: today() })
    });
    render(d);
    $('#status').textContent = '已确认今天队列。';
  } catch (e) {
    $('#status').textContent = '确认失败：' + e.message;
  } finally {
    $('#confirmBtn').disabled = false;
  }
}

document.querySelectorAll('#minuteChips .chip').forEach(b => {
  b.addEventListener('click', () => {
    selected = Number(b.dataset.min);
    document.querySelectorAll('#minuteChips .chip').forEach(x => x.classList.toggle('on', x === b));
    $('#customMin').value = '';
  });
});
$('#customMin').addEventListener('input', () => {
  const v = parseInt($('#customMin').value, 10);
  if (v >= 30) document.querySelectorAll('#minuteChips .chip').forEach(x => x.classList.remove('on'));
});
$('#planBtn').addEventListener('click', generate);
$('#confirmBtn').addEventListener('click', confirmPlan);
$('#dateLabel').textContent = '今天 · ' + today();
loadPlan();
