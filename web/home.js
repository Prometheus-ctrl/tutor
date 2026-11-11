const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');

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
  if (!ref) return '/talk.html';
  const i = ref.lastIndexOf(':');
  if (i < 0) return '/talk.html?paper=' + encodeURIComponent(ref);
  return '/talk.html?paper=' + encodeURIComponent(ref.slice(0, i)) + '&index=' + encodeURIComponent(ref.slice(i + 1));
}

function daysUntil(iso) {
  if (!iso) return null;
  const target = new Date(iso + 'T00:00:00');
  const now = new Date(today() + 'T00:00:00');
  return Math.ceil((target - now) / 86400000);
}

function renderStats(over, time) {
  const due = (over.due || []).length;
  const weekly = (over.weekly || []).reduce((n, w) => n + (w.planned_min || 0), 0);
  const planned = time && time.plan ? (time.blocks || []).reduce((n, b) => n + (b.minutes || 0), 0) : 0;
  const days = daysUntil(over.exam && over.exam.exam_date);
  $('#stats').innerHTML = [
    ['距考试', days == null ? '—' : days + ' 天'],
    ['当前到期', due],
    ['本周目标', Math.round(weekly / 60) + 'h'],
    ['今天已排', planned ? Math.round(planned) + ' 分' : '未排']
  ].map(x => '<div class="stat"><b>' + esc(x[1]) + '</b><span>' + esc(x[0]) + '</span></div>').join('');
  if (days != null) $('#heroTitle').textContent = '距 ' + over.exam.exam_date + ' 还有 ' + days + ' 天';
}

function renderSubjects(over) {
  const box = $('#subjects');
  const subjects = over.subjects || [];
  if (!subjects.length) { box.innerHTML = '<div class="empty">还没有科目。</div>'; return; }
  box.innerHTML = subjects.map(s => {
    const pct = s.problems ? Math.round(s.finished / s.problems * 100) : 0;
    return '<a class="sub" href="/plan.html?subject=' + encodeURIComponent(s.id) + '">' +
      '<div class="sub-top"><span class="sub-name">' + esc(s.name) + '</span>' +
      (s.due ? '<span class="sub-due">到期 ' + s.due + '</span>' : '') + '</div>' +
      '<div class="sub-meta">' + s.papers + ' 份整卷 · ' + s.problems + ' 题 · 已讲 ' + s.finished + '</div>' +
      '<div class="progress"><i style="width:' + pct + '%"></i></div></a>';
  }).join('');
}

function renderToday(time) {
  const box = $('#today');
  if (!time || !time.plan) {
    $('#todayBadge').textContent = '未排';
    box.innerHTML = '<div class="empty">还没有排今天。</div>';
    return;
  }
  $('#todayBadge').textContent = time.plan.status === 'confirmed' ? '已确认' : '草稿';
  const blocks = time.blocks || [];
  if (!blocks.length) { box.innerHTML = '<div class="empty">今天没有可排的块。</div>'; return; }
  box.innerHTML = blocks.map(b => '<div class="block"><div class="block-head"><b>' + esc(b.subject) +
    '</b><span>' + b.minutes + ' 分钟</span></div>' +
    (b.items || []).map(it => '<div class="q-item"><span>' + esc(it.title || '') + '</span>' +
      '<span class="muted">' + (it.estimate_min || 0) + ' 分</span></div>').join('') +
    '</div>').join('');
}

function renderDue(over) {
  const list = over.due || [];
  $('#dueBadge').textContent = list.length;
  const box = $('#dueList');
  if (!list.length) { box.innerHTML = '<div class="empty">今天没有到期题。</div>'; return; }
  box.innerHTML = list.map(d => {
    const where = [d.goal_title, d.task_title, d.plan_name, d.paper_title].filter(Boolean).join(' · ');
    return '<a class="item" href="' + talkUrl(d.problem_id) + '">' +
      '<div class="item-title">' + esc(d.paper_title || d.problem_id) + ' · 第 ' + esc(d.no || '?') + ' 题</div>' +
      '<div class="item-meta">' + esc(where) + ' · 去复述</div></a>';
  }).join('');
}

async function main() {
  try {
    const [over, time] = await Promise.all([
      api('/api/app/overview'),
      api('/api/app/time?date=' + today()).catch(() => ({ plan: null, blocks: [] }))
    ]);
    renderStats(over, time);
    renderSubjects(over);
    renderToday(time);
    renderDue(over);
  } catch (e) {
    $('#subjects').innerHTML = '<div class="notice">加载失败：' + esc(e.message) + '</div>';
    $('#today').innerHTML = '';
    $('#dueList').innerHTML = '';
  }
}
main();
