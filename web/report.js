const $ = s => document.querySelector(s);

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
}

function today() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
}

function md(text) {
  const lines = String(text || '').split('\n');
  let html = '';
  let inList = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  lines.forEach(raw => {
    const line = raw.trim();
    if (!line) { closeList(); return; }
    if (line.startsWith('## ')) { closeList(); html += '<h2>' + esc(line.slice(3)) + '</h2>'; return; }
    if (line.startsWith('# ')) { closeList(); html += '<h1>' + esc(line.slice(2)) + '</h1>'; return; }
    if (line.startsWith('- ')) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + esc(line.slice(2)).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>') + '</li>';
      return;
    }
    closeList();
    html += '<p>' + esc(line).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>') + '</p>';
  });
  closeList();
  return html;
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}

function renderDays(dates, active) {
  const box = $('#reportDays');
  box.innerHTML = '';
  dates.forEach(date => {
    const b = document.createElement('button');
    b.textContent = date.slice(5);
    b.className = date === active ? 'on' : '';
    b.onclick = () => loadReport(date).catch(e => status(e.message));
    box.appendChild(b);
  });
}

function status(text) {
  $('#reportStatus').textContent = text || '';
}

async function loadReport(date) {
  status('加载中…');
  const d = await api('/api/app/report?date=' + encodeURIComponent(date));
  $('#reportBody').innerHTML = md(d.report || '');
  const raw = $('#reportRaw');
  if (d.raw) {
    raw.hidden = false;
    raw.innerHTML = '<details><summary>原始事实</summary><pre>' + esc(d.raw) + '</pre></details>';
  } else {
    raw.hidden = true;
    raw.innerHTML = '';
  }
  renderDays(state.dates, date);
  status('已加载 ' + date);
}

const state = { dates: [], active: '' };

async function loadList() {
  const d = await api('/api/app/reports?archive=1');
  state.dates = d.reports || [];
  if (!state.dates.length) {
    renderDays([], '');
    $('#reportBody').innerHTML = '<div class="empty">还没有学习报告。点上面生成今天报告。</div>';
    return;
  }
  const pick = state.dates.includes(today()) ? today() : state.dates[0];
  await loadReport(pick);
}

async function generateToday() {
  const btn = $('#genToday');
  btn.disabled = true;
  status('秘书正在整理今天记录…');
  try {
    await api('/api/app/report/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: today(), polish: true })
    });
    await loadList();
    status('今天报告已生成。');
  } catch (e) {
    status('生成失败：' + e.message);
  } finally {
    btn.disabled = false;
  }
}

$('#genToday').addEventListener('click', generateToday);
$('#loadLatest').addEventListener('click', () => loadList().catch(e => status(e.message)));
loadList().catch(e => status('加载失败：' + e.message));
