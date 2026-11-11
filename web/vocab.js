const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function render(items) {
  const list = $('#vocabList');
  const fresh = items.filter(x => x.status === 'new').length;
  $('#vocabStats').innerHTML =
    '<div class="stat"><b>' + items.length + '</b><span>生词</span></div>' +
    '<div class="stat"><b>' + fresh + '</b><span>未认</span></div>' +
    '<div class="stat"><b>' + (items.length - fresh) + '</b><span>已认</span></div>';
  if (!items.length) {
    list.innerHTML = '<div class="empty">还没有生词。阅读时把词和原句存进来。</div>';
    return;
  }
  list.innerHTML = items.map(x => {
    const known = x.status === 'known';
    return '<div class="vocab-item">' +
      '<div class="row" style="justify-content:space-between;align-items:flex-start;">' +
      '<div><div class="vocab-word">' + esc(x.word) + '</div>' +
      (x.sentence ? '<div class="vocab-sentence">' + esc(x.sentence) + '</div>' : '') +
      '<div class="vocab-meta">' + esc(x.paper_title || '未挂文章') + ' · ' + (known ? '已认' : '未认') + '</div></div>' +
      '<div class="vocab-actions"><button class="chip" data-id="' + esc(x.id) + '" data-status="' +
      (known ? 'new' : 'known') + '">' + (known ? '标回生词' : '认识了') + '</button>' +
      '<button class="chip" data-id="' + esc(x.id) + '" data-delete="1">删除</button></div>' +
      '</div></div>';
  }).join('');
  list.querySelectorAll('[data-status]').forEach(btn => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await api('/api/app/vocab', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'status', id: btn.dataset.id, status: btn.dataset.status })
        });
        await load();
      } catch (e) { btn.disabled = false; alert(e.message); }
    });
  });
  list.querySelectorAll('[data-delete]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('删除这个词？')) return;
      btn.disabled = true;
      try {
        await api('/api/app/vocab', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'delete', id: btn.dataset.id })
        });
        await load();
      } catch (e) { btn.disabled = false; alert(e.message); }
    });
  });
}

async function load() {
  const data = await api('/api/app/vocab');
  render(data.items || []);
}

async function loadPapers() {
  try {
    const data = await api('/api/papers');
    const sel = $('#vocabPaper');
    (data.papers || []).forEach(p => {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.title || p.id;
      sel.appendChild(o);
    });
  } catch (e) { /* 没卷子也能用词本 */ }
}

$('#vocabForm').addEventListener('submit', async e => {
  e.preventDefault();
  const word = $('#vocabWord').value.trim();
  if (!word) return;
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  try {
    await api('/api/app/vocab', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'add',
        word,
        sentence: $('#vocabSentence').value.trim(),
        paperId: $('#vocabPaper').value || ''
      })
    });
    $('#vocabWord').value = '';
    $('#vocabSentence').value = '';
    await load();
  } catch (err) {
    alert('保存失败：' + err.message);
  } finally {
    btn.disabled = false;
  }
});

loadPapers();
load().catch(e => { $('#vocabList').innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>'; });
