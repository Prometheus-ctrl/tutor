(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const state = { paper: null, problems: [], images: new Map(), dirty: false };
  const statusEl = $('#status');
  const listEl = $('#list');
  const selectEl = $('#paperSelect');

  function status(text, kind) {
    statusEl.textContent = text || '';
    statusEl.className = 'status ' + (kind || '');
  }

  async function api(url, opts) {
    const r = await fetch(url, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
    return data;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": "'" }[c]));
  }

  function decodeEntities(s) {
    return String(s || '')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
      .replace(/&amp;/g, '&');
  }

  function mathHtml(text) {
    const raw = decodeEntities(text);
    const parts = raw.split(/(\$\$[\s\S]*?\$\$|\$[^$\n]*?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))/g);
    return parts.map(seg => {
      if (!seg) return '';
      let expr = null, display = false;
      if (seg.startsWith('$$') && seg.endsWith('$$') && seg.length > 4) { expr = seg.slice(2, -2); display = true; }
      else if (seg.startsWith('\\[') && seg.endsWith('\\]')) { expr = seg.slice(2, -2); display = true; }
      else if (seg.startsWith('$') && seg.endsWith('$') && seg.length > 2) { expr = seg.slice(1, -1); }
      else if (seg.startsWith('\\(') && seg.endsWith('\\)')) { expr = seg.slice(2, -2); }
      if (expr != null && window.katex) {
        try { return katex.renderToString(expr, { displayMode: display, throwOnError: false, strict: false }); }
        catch (e) { return escapeHtml(seg); }
      }
      return escapeHtml(seg).replace(/\n/g, '<br>');
    }).join('');
  }

  function img(src) {
    if (state.images.has(src)) return state.images.get(src);
    const p = new Promise((resolve, reject) => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = reject;
      im.src = src;
    });
    state.images.set(src, p);
    return p;
  }

  function draw(card) {
    const p = card.p;
    const canvas = $('canvas', card.el);
    if (!p.bbox) return;
    const composite = p.cross_page && p.crop_url;
    img(composite ? p.crop_url : (p.image_url || p.page_url)).then(im => {
      const b = composite ? [0, 0, 1, 1] : p.bbox;
      const sx = b[0] * im.naturalWidth;
      const sy = b[1] * im.naturalHeight;
      const sw = Math.max(1, (b[2] - b[0]) * im.naturalWidth);
      const sh = Math.max(1, (b[3] - b[1]) * im.naturalHeight);
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const cssW = Math.min(700, canvas.parentElement.clientWidth - 2);
      const cssH = Math.max(72, Math.min(380, cssW * sh / sw));
      canvas.style.width = cssW + 'px';
      canvas.style.height = cssH + 'px';
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, cssW, cssH);
      ctx.drawImage(im, sx, sy, sw, sh, 0, 0, cssW, cssH);
    }).catch(() => {});
  }

  function nudge(p, which, delta) {
    const b = p.bbox.slice();
    if (which === 'top') b[1] = Math.max(0, Math.min(b[3] - 0.01, b[1] + delta));
    else b[3] = Math.min(1, Math.max(b[1] + 0.01, b[3] + delta));
    p.bbox = b.map(v => Math.round(v * 10000) / 10000);
    state.dirty = true;
    render();
  }

  function toggleTrust(p) {
    p.text_trusted = p.text_trusted === false;
    state.dirty = true;
    render();
  }

  async function reread(index) {
    status('重读第 ' + state.problems[index].no + ' 题…');
    try {
      await api('/api/paper/' + encodeURIComponent(state.paper) + '/reread', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index })
      });
      await loadPaper(state.paper);
      status('重读完成，检查右边渲染结果', 'ok');
    } catch (e) {
      status('重读失败：' + e.message, 'err');
    }
  }

  function compress(file) {
    return new Promise((resolve, reject) => {
      const im = new Image();
      im.onload = () => {
        const max = 1800;
        const scale = Math.min(1, max / Math.max(im.width, im.height));
        const c = document.createElement('canvas');
        c.width = Math.round(im.width * scale);
        c.height = Math.round(im.height * scale);
        c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
        resolve(c.toDataURL('image/jpeg', 0.86));
      };
      im.onerror = reject;
      im.src = URL.createObjectURL(file);
    });
  }

  async function retake(index, file) {
    if (!file) return;
    status('上传重拍照…');
    try {
      const dataUrl = await compress(file);
      await api('/api/paper/' + encodeURIComponent(state.paper) + '/retake', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index, image: dataUrl })
      });
      await loadPaper(state.paper);
      status('重拍完成，已自动重读', 'ok');
    } catch (e) {
      status('重拍失败：' + e.message, 'err');
    }
  }

  function optionsHtml(p) {
    if (!(p.options || []).length) return '';
    return '<div class="opts-render">' + p.options.map(o =>
      '<div class="opt"><b>' + escapeHtml(o.label) + '.</b><span>' + mathHtml(o.text || '') + '</span></div>'
    ).join('') + '</div>';
  }

  function cardFor(p, index) {
    const card = document.createElement('section');
    card.className = 'card' + (p.text_trusted === false ? ' untrusted' : '');
    const head = document.createElement('div');
    head.className = 'head';
    head.innerHTML = `<b>第 ${p.no} 题</b><span>第 ${p.page} 页 · 框选 ${p.bbox ? p.bbox.map(v => v.toFixed(3)).join(', ') : '无'}</span>`
      + (p.text_trusted === false ? '<em class="badge">待重读</em>' : '');
    card.appendChild(head);

    const view = document.createElement('div');
    view.className = 'view';
    view.appendChild(document.createElement('canvas'));
    card.appendChild(view);

    const preview = document.createElement('div');
    preview.className = 'preview';
    preview.innerHTML = '<div class="qtext">' + mathHtml(p.text) + '</div>' + optionsHtml(p);
    card.appendChild(preview);

    const tools = document.createElement('div');
    tools.className = 'tools';
    const mk = (label, fn, cls) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.className = cls || '';
      b.onclick = fn;
      tools.appendChild(b);
    };
    mk('上边界 ↑', () => nudge(p, 'top', -0.004));
    mk('上边界 ↓', () => nudge(p, 'top', 0.004));
    mk('下边界 ↑', () => nudge(p, 'bottom', -0.004));
    mk('下边界 ↓', () => nudge(p, 'bottom', 0.004));
    mk('重读此题', () => reread(index), 'primary');
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.setAttribute('capture', 'environment');
    fileInput.hidden = true;
    fileInput.onchange = () => { retake(index, fileInput.files[0]); fileInput.value = ''; };
    card.appendChild(fileInput);
    mk('重拍此题', () => fileInput.click(), 'ghost');
    mk(p.text_trusted === false ? '文字正常' : '标记待重读', () => toggleTrust(p), 'ghost');
    mk('编辑文字', () => {
      const adv = $('.advanced', card);
      adv.hidden = !adv.hidden;
    }, 'ghost');
    mk('合并到上一题', () => mergeToPrev(index), 'ghost');
    mk('删除本题', () => removeProblem(index), 'danger');
    card.appendChild(tools);

    const advanced = document.createElement('div');
    advanced.className = 'advanced';
    advanced.hidden = true;
    const ta = document.createElement('textarea');
    ta.value = p.text || '';
    ta.rows = Math.max(2, Math.min(8, Math.ceil((p.text || '').length / 70)));
    ta.oninput = () => { p.text = ta.value; state.dirty = true; $('.qtext', card).innerHTML = mathHtml(ta.value); };
    advanced.appendChild(ta);
    (p.options || []).forEach(o => {
      const row = document.createElement('label');
      row.className = 'opt-edit';
      const tag = document.createElement('b');
      tag.textContent = o.label + '.';
      const input = document.createElement('input');
      input.value = o.text || '';
      input.oninput = () => { o.text = input.value; state.dirty = true; $('.opts-render', card).innerHTML = p.options.map(x => '<div class="opt"><b>' + escapeHtml(x.label) + '.</b><span>' + mathHtml(x.text || '') + '</span></div>').join(''); };
      row.append(tag, input);
      advanced.appendChild(row);
    });
    card.appendChild(advanced);

    const open = document.createElement('a');
    open.className = 'page-link';
    open.href = p.image_url || p.page_url;
    open.target = '_blank';
    open.textContent = p.retake ? '看重拍照 ↗' : '看整页 ↗';
    card.appendChild(open);

    card.el = card;
    card.p = p;
    setTimeout(() => draw(card), 0);
    return card;
  }

  function render() {
    listEl.innerHTML = '';
    state.problems.forEach((p, i) => listEl.appendChild(cardFor(p, i)));
    status(state.dirty ? '有未保存修改' : (state.paper ? '已加载 ' + state.problems.length + ' 题' : ''), state.dirty ? 'warn' : '');
  }

  function removeProblem(index) {
    if (!confirm('删除第 ' + state.problems[index].no + ' 题？')) return;
    state.problems.splice(index, 1);
    state.dirty = true;
    render();
  }

  function mergeToPrev(index) {
    if (index <= 0) return;
    const cur = state.problems[index];
    const prev = state.problems[index - 1];
    if (!confirm('把第 ' + cur.no + ' 题并到第 ' + prev.no + ' 题？')) return;
    prev.text = (prev.text || '') + '\n' + (cur.text || '');
    const labels = new Set((prev.options || []).map(o => (o.label || '').toUpperCase()));
    (cur.options || []).forEach(o => {
      if (!labels.has((o.label || '').toUpperCase())) prev.options = (prev.options || []).concat([o]);
    });
    if (prev.bbox && cur.bbox) {
      prev.bbox = [Math.min(prev.bbox[0], cur.bbox[0]), Math.min(prev.bbox[1], cur.bbox[1]),
        Math.max(prev.bbox[2], cur.bbox[2]), Math.max(prev.bbox[3], cur.bbox[3])];
    }
    prev.merged_from_next = true;
    state.problems.splice(index, 1);
    state.dirty = true;
    render();
  }

  async function loadPaper(id) {
    status('加载中…');
    const data = await api('/api/paper/' + encodeURIComponent(id));
    state.paper = id;
    state.problems = data.problems || [];
    state.images.clear();
    state.dirty = false;
    render();
  }

  async function loadList() {
    const data = await api('/api/papers');
    selectEl.innerHTML = '';
    (data.papers || []).forEach(p => {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.id + '（' + p.problems + ' 题）';
      selectEl.appendChild(o);
    });
    if (data.papers && data.papers.length) await loadPaper(data.papers[0].id);
    else status('samples 里还没有 ingest-* 结果，先跑 ingest.py', 'warn');
  }

  async function save() {
    if (!state.paper) return;
    status('保存中…');
    const payload = {
      problems: state.problems.map(p => ({
        no: p.no, text: p.text, options: p.options || [], latex: p.latex || '',
        bbox: p.bbox, page: p.page, continues_next: p.continues_next,
        merged_from_next: p.merged_from_next, page_fragments: p.page_fragments || [],
        text_trusted: p.text_trusted !== false, cross_page: !!p.cross_page, crop: p.crop || null
      }))
    };
    try {
      const r = await api('/api/paper/' + encodeURIComponent(state.paper) + '/save', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      });
      state.dirty = false;
      await loadPaper(state.paper);
      status('已保存 ' + r.problems + ' 题', 'ok');
    } catch (e) {
      status('保存失败：' + e.message, 'err');
    }
  }

  selectEl.onchange = () => loadPaper(selectEl.value);
  $('#saveBtn').onclick = save;
  window.addEventListener('beforeunload', e => { if (state.dirty) { e.preventDefault(); e.returnValue = ''; } });
  loadList().catch(e => status('加载失败：' + e.message, 'err'));
})();
