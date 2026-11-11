const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
let tasks = [];
let templates = [];
let current = null;

function statusLabel(status) {
  return ({draft: '草稿', revised: '已改', feedback: '待重写', ready: '可定稿', final: '定稿'})[status] || status || '草稿';
}

function optionLabel(t) {
  return t.year + ' · Part ' + t.part + ' · ' + statusLabel(t.status);
}

function refreshOption(t) {
  const opt = $('#taskSelect').querySelector('option[value="' + CSS.escape(t.id) + '"]');
  if (opt) opt.textContent = optionLabel(t);
}

function setStatus(text, cls) {
  const el = $('#status');
  el.textContent = text || '';
  el.className = 'status' + (cls ? ' ' + cls : '');
}
function updateCount() {
  const text = $('#draft').value || '';
  const words = (text.match(/[A-Za-z]+(?:['’-][A-Za-z]+)?/g) || []).length;
  const target = current && current.part === 'A' ? 100 : 150;
  $('#count').textContent = words + ' 词 / 目标约 ' + target + ' 词';
}

function tokenize(s) {
  return String(s || '').match(/[A-Za-z]+(?:['’-][A-Za-z]+)?|\d+(?:\.\d+)?|[^\s]/g) || [];
}

function diffTokens(a, b) {
  const n = a.length, m = b.length;
  const dp = Array.from({length: n + 1}, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { ops.push(['=', a[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push(['-', a[i]]); i++; }
    else { ops.push(['+', b[j]]); j++; }
  }
  while (i < n) ops.push(['-', a[i++]]);
  while (j < m) ops.push(['+', b[j++]]);
  return ops;
}

function renderCompare(t) {
  const box = $('#compareBox');
  const first = String(t.first_draft || '');
  const current = String(t.draft || '');
  if (!first || !current || first === current) { box.hidden = true; box.innerHTML = ''; return; }
  const ops = diffTokens(tokenize(first), tokenize(current));
  let left = '', right = '';
  for (const [op, word] of ops) {
    const w = esc(word);
    if (op === '=') { left += w + ' '; right += w + ' '; }
    else if (op === '-') left += '<del>' + w + '</del> ';
    else right += '<ins>' + w + '</ins> ';
  }
  box.innerHTML = '<h3>初稿 / 重写对比</h3><div class="diff-cols">' +
    '<div class="diff-col"><b>初稿</b>' + left + '</div>' +
    '<div class="diff-col"><b>当前稿</b>' + right + '</div></div>';
  box.hidden = false;
}

function inlineMd(s) {
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function templateHtml(md) {
  const lines = String(md || '').split('\n');
  const out = [];
  let table = null;
  let code = null;
  const flushTable = () => {
    if (!table) return;
    out.push('<table class="tpl-table">' + table.join('') + '</table>');
    table = null;
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith('```')) {
      if (code === null) { flushTable(); code = []; }
      else { out.push('<pre class="tpl-code">' + esc(code.join('\n')) + '</pre>'); code = null; }
      continue;
    }
    if (code !== null) { code.push(raw); continue; }
    if (/^\|/.test(line)) {
      if (/^\|\s*[-: ]+\|/.test(line)) continue;
      const cells = line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(x => x.trim());
      const tag = table ? 'td' : 'th';
      if (!table) table = [];
      table.push('<tr>' + cells.map(x => '<' + tag + '>' + inlineMd(x) + '</' + tag + '>').join('') + '</tr>');
      continue;
    }
    flushTable();
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      const n = h[1].length + 1;
      out.push('<h' + n + ' class="tpl-h">' + inlineMd(h[2]) + '</h' + n + '>');
    } else if (/^-\s+/.test(line)) {
      out.push('<div class="tpl-li">• ' + inlineMd(line.replace(/^-\s+/, '')) + '</div>');
    } else if (/^>\s?/.test(line)) {
      out.push('<blockquote class="tpl-note">' + inlineMd(line.replace(/^>\s?/, '')) + '</blockquote>');
    } else if (!line.trim()) {
      out.push('<div class="tpl-gap"></div>');
    } else {
      out.push('<p>' + inlineMd(line) + '</p>');
    }
  }
  flushTable();
  if (code !== null) out.push('<pre class="tpl-code">' + esc(code.join('\n')) + '</pre>');
  return out.join('');
}

function showTemplate(id) {
  const t = templates.find(x => x.id === id);
  if (!t) return;
  $('#templateTitle').textContent = t.title;
  $('#templateBody').innerHTML = templateHtml(t.body);
}

function renderTemplates(part) {
  const box = $('#templateBox');
  const list = templates.filter(t => !part || !t.part || t.part === part);
  if (!list.length) { box.hidden = true; return; }
  const sel = $('#templateSelect');
  sel.innerHTML = list.map(t => '<option value="' + esc(t.id) + '">' + esc(t.title) + '</option>').join('');
  sel.value = list[0].id;
  showTemplate(list[0].id);
  box.hidden = false;
}


function actionHtml(text) {
  const s = String(text || '');
  const idx = s.indexOf('可加：');
  if (idx < 0) return esc(s);
  const head = s.slice(0, idx + 3);
  const items = s.slice(idx + 3).split('；').map(x => x.trim()).filter(Boolean);
  return esc(head) + '<div class="action-list">' +
    items.map(x => '<div>• ' + esc(x) + '</div>').join('') + '</div>';
}

function renderFeedback(f) {
  const box = $('#feedbackBox');
  const must = f ? (f.must_fix || f.issues || []) : [];
  const optional = f ? (f.optional || []) : [];
  if (!f || (!must.length && !optional.length && !f.scores)) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  const showScores = $('#scoreToggle').checked;
  const s = f.scores || {};
  const score = '内容/任务 ' + (s.task ?? '-') + ' · 结构 ' + (s.structure ?? '-') +
    ' · 语言 ' + (s.language ?? '-');
  const scale = '三项独立评分，每项 0-' + (f.total || '-') + '，不相加；没有合成总分。只作参考。';
  const nextText = String(f.next_action || '');
  const nextBody = nextText.replace(/^这次只改[:：]\s*/, '');
  const issues = must.map(x => {
    const fix = String(x.fix || x.action || '');
    const showFix = fix.trim() && fix.trim() !== nextBody.trim();
    return '<li><span class="quote">“' + esc(x.quote) + '”</span><br>' +
      esc(x.problem) + (showFix ? '<br><b>改法：</b>' + actionHtml(fix) : '') + '</li>';
  }).join('');
  const opts = optional.map(x => '<li>' + esc(x) + '</li>').join('');
  let html = '<h3>AI 批改</h3>';
  if (must.length) {
    html += '<div class="scale">必须改（这些会阻断定稿）</div><ul>' + issues + '</ul>';
    if (nextText) {
      html += '<div class="next">' +
        (/^这次只改/.test(nextText) ? '' : '这次只改：') + actionHtml(nextText) + '</div>';
    }
  } else {
    html += '<div class="clean">没有必须修改的硬伤，可以定稿。</div>';
  }
  if (showScores && f.scores) {
    html += '<div class="score">' + esc(score) + '</div><div class="scale">' + esc(scale) + '</div>';
  }
  if (opts) {
    html += '<details><summary>可选润色（不影响定稿）</summary><ul>' + opts + '</ul></details>';
  }
  box.innerHTML = html;
  box.hidden = false;
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}

async function loadTask(id) {
  const t = await api('/api/app/writing/' + encodeURIComponent(id));
  const m = /:(\d{4}):([AB])$/.exec(t.id || '');
  t.year = m ? m[1] : (t.year || '');
  t.part = m ? m[2] : (t.part || '');
  current = t;
  refreshOption(t);
  renderTemplates(t.part);
  localStorage.setItem('writingTask', t.id);
  const u = new URL(location.href);
  u.searchParams.set('task', t.id);
  history.replaceState(null, '', u);
  $('#taskTitle').textContent = t.year + ' 英语二 · Part ' + t.part;
  $('#prompt').textContent = t.prompt || '';
  const wrap = $('#promptImageWrap');
  if (t.image_url) {
    $('#promptImage').src = t.image_url;
    $('#promptImageLink').href = t.image_url;
    wrap.hidden = false;
  } else {
    $('#promptImage').removeAttribute('src');
    wrap.hidden = true;
  }
  $('#draft').value = t.draft || '';
  const dueLine = t.status === 'ready'
    ? '<br>没有必须修改的硬伤，可直接定稿。'
    : (t.rewrite_due ? '<br>重写到期：' + esc(t.rewrite_due) : '');
  $('#taskMeta').innerHTML = '状态：' + esc(statusLabel(t.status)) + dueLine;
  updateCount();
  renderFeedback(t.feedback_data);
  renderCompare(t);
  setStatus(t.status === 'final' ? '已定稿' : '已加载');
}

async function save() {
  if (!current) return;
  $('#save').disabled = true;
  try {
    const t = await api('/api/app/writing/' + encodeURIComponent(current.id), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft: $('#draft').value })
    });
    current = t;
  refreshOption(t);
    setStatus('已保存', 'ok');
    $('#taskMeta').innerHTML = '状态：' + esc(statusLabel(t.status)) + '<br>刚刚保存。';
  } catch (e) {
    setStatus('保存失败：' + e.message, 'err');
  } finally {
    $('#save').disabled = false;
  }
}

async function feedback() {
  if (!current) return;
  if (!($('#draft').value || '').trim()) { setStatus('先写草稿，再批改。', 'err'); return; }
  const btn = $('#feedbackBtn');
  btn.disabled = true; setStatus('AI 正在按评分点看草稿…');
  try {
    const t = await api('/api/app/writing/' + encodeURIComponent(current.id) + '/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft: $('#draft').value })
    });
    current = t;
  refreshOption(t);
    renderFeedback(t.feedback_data);
  renderCompare(t);
    $('#taskMeta').innerHTML = '状态：' + esc(statusLabel(t.status)) +
      (t.rewrite_due ? '<br>重写到期：' + esc(t.rewrite_due) : '<br>无需重写，可直接定稿。');
    const must = (t.feedback_data && (t.feedback_data.must_fix || t.feedback_data.issues)) || [];
    setStatus(must.length ? '批改好了。只改必改项，改完点「我改好了」。' : '没有必须修改的硬伤，可以直接定稿。', 'ok');
  } catch (e) {
    setStatus('批改失败：' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

async function showReport() {
  if (!current) return;
  const btn = $('#reportBtn');
  btn.disabled = true;
  try {
    const d = await api('/api/app/writing/' + encodeURIComponent(current.id) + '/report');
    $('#reportText').textContent = d.report || '';
    $('#reportBox').hidden = false;
  } catch (e) {
    setStatus('报告生成失败：' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

async function finalize() {
  if (!current) return;
  if (!($('#draft').value || '').trim()) { setStatus('重写内容为空。', 'err'); return; }
  if (!confirm('定稿后不再自动安排重写。\n\n确认前请再看一眼：AI 批改里还有「必须改」吗？有就点取消，改完再批一次。\n\n确定定稿吗？')) return;
  const btn = $('#finalBtn');
  btn.disabled = true; setStatus('保存重写…');
  try {
    const t = await api('/api/app/writing/' + encodeURIComponent(current.id) + '/final', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft: $('#draft').value })
    });
    current = t;
  refreshOption(t);
    renderFeedback(t.feedback_data);
  renderCompare(t);
    $('#taskMeta').innerHTML = '状态：' + esc(statusLabel(t.status)) + '<br>已定稿。';
    setStatus('已定稿。', 'ok');
  } catch (e) {
    setStatus('提交失败：' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

(async function init() {
  try {
    const d = await api('/api/app/writing');
    tasks = d.tasks || [];
    try {
      const td = await api('/api/app/writing/templates');
      templates = td.templates || [];
    } catch (e) { templates = []; }
    const sel = $('#taskSelect');
    sel.innerHTML = tasks.map(t =>
      '<option value="' + esc(t.id) + '">' + t.year + ' · Part ' + esc(t.part) + ' · ' + statusLabel(t.status) + '</option>'
    ).join('');
    if (!tasks.length) { setStatus('还没有写作题，先导入。', 'err'); return; }
    sel.addEventListener('change', () => loadTask(sel.value).catch(e => setStatus(e.message, 'err')));
    $('#draft').addEventListener('input', updateCount);
    $('#save').addEventListener('click', save);
    $('#feedbackBtn').addEventListener('click', feedback);
    $('#finalBtn').addEventListener('click', finalize);
    $('#reportBtn').addEventListener('click', showReport);
    $('#reportClose').addEventListener('click', () => { $('#reportBox').hidden = true; });
    $('#templateSelect').addEventListener('change', e => showTemplate(e.target.value));
    const scoreToggle = $('#scoreToggle');
    scoreToggle.checked = localStorage.getItem('writingScores') === '1';
    scoreToggle.addEventListener('change', () => {
      localStorage.setItem('writingScores', scoreToggle.checked ? '1' : '0');
      if (current) renderFeedback(current.feedback_data);
    });
    const lightbox = $('#lightbox');
    const closeLightbox = () => { lightbox.hidden = true; $('#lightboxImg').removeAttribute('src'); };
    $('#promptImageLink').addEventListener('click', e => {
      e.preventDefault();
      const src = $('#promptImage').getAttribute('src');
      if (!src) return;
      $('#lightboxImg').src = src;
      lightbox.hidden = false;
    });
    $('#lightboxClose').addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', e => { if (e.target === lightbox) closeLightbox(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });;
    const wanted = new URLSearchParams(location.search).get('task') || localStorage.getItem('writingTask');
    const task = tasks.find(x => x.id === wanted) || tasks[0];
    sel.value = task.id;
    await loadTask(task.id);
  } catch (e) {
    setStatus('加载失败：' + e.message, 'err');
  }
})();
