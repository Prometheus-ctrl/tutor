/* 0B 语音闭环：录音 WAV → Qwen3-ASR → 可编辑文字 → Qwen-Plus → Qwen3-TTS */
const $ = s => document.querySelector(s);
const state = { papers: [], paper: null, problems: [], history: [], health: null, segments: [], due: [], reviewMode: false, examMode: false, sessionId: null, subjectId: 'math2', problemType: 'single', speechToken: 0, spokenUrls: [], autoSpeak: false, lastSpeech: '', paperToken: 0, doubtAsked: false, batches: [], batchCount: 0, turnsSincePref: 0, prefCount: 0, prefPair: null, prefLoading: false, inputDirty: false, selectMode: false, selected: new Set(), companionConfig: { preference: { every_turns: 4, max_per_batch: 3 } } };
let rec = null;
let micDeviceId = '';
let speakerMode = false;
try {
  micDeviceId = localStorage.getItem('tutorMicId') || '';
  speakerMode = localStorage.getItem('tutorSpeakerMode') === '1';
} catch (e) { micDeviceId = ''; speakerMode = false; }

// 到期复习“绕路”状态：被到期题拉去别的卷时记住原卷，做完回来继续
function setDetour(d) {
  state.detour = d || null;
  try {
    sessionStorage.setItem('tutorDetour', state.detour ? JSON.stringify(state.detour) : '');
  } catch (e) { /* ignore */ }
}

async function refreshMicDevices() {
  const sel = $('#micSelect');
  if (!sel || !navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
  let list = [];
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    list = devices.filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications');
    // 默认输出是不是耳机：是的话录音时关掉回声消除（否则浏览器里播放的白噪音会被当回声，连人声一起压）
    const outs = devices.filter(d => d.kind === 'audiooutput');
    const defOut = outs.find(d => d.deviceId === 'default') || outs[0];
    const outLabel = defOut ? String(defOut.label || '') : '';
    state.headphoneOut = outLabel ? /耳机|耳麦|headphone|headset|earbud|earphone/i.test(outLabel) : null;
  } catch (e) { list = []; }
  const cur = micDeviceId;
  sel.innerHTML = '';
  const def = document.createElement('option');
  def.value = '';
  def.textContent = '系统默认';
  sel.appendChild(def);
  list.forEach((d, i) => {
    const o = document.createElement('option');
    o.value = d.deviceId;
    o.textContent = d.label || ('麦克风 ' + (i + 1) + '（首次录音后显示名称）');
    sel.appendChild(o);
  });
  if (cur && !list.some(d => d.deviceId === cur)) {
    const o = document.createElement('option');
    o.value = cur;
    o.textContent = '已选设备（当前不可用）';
    sel.appendChild(o);
  }
  sel.value = cur;
}

function setFinishLabel(review) {
  const text = review ? '结束复述' : '结束本题';
  ['#dockFinish'].forEach(sel => {
    const el = $(sel);
    if (el) el.textContent = text;
  });
}

function setComposer(open) {
  $('#composer').classList.toggle('collapsed', !open);
  $('#voiceFab').classList.toggle('expanded', open);
  const toggle = $('#toggleComposer');
  if (toggle) toggle.textContent = open ? '收起' : '编辑';
  if (open) {
    $('#voiceBubble').hidden = true;
  } else {
    updateBubble();
  }
  setTimeout(clampFab, 0);
}

function status(text, kind) {
  const el = $('#status');
  el.textContent = text || '';
  el.className = 'voice-status ' + (kind || '');
  const dock = $('#dockStatus');
  if (dock) {
    dock.textContent = text || '';
    dock.className = 'dock-status ' + (kind || '');
  }
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function decodeEntities(s) {
  return String(s == null ? '' : s)
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}

function mdLite(html) {
  return html
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function mathHtml(text) {
  const s = decodeEntities(text);
  const re = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$)/g;
  const parts = [];
  let last = 0, m;
  while ((m = re.exec(s))) {
    if (m.index > last) parts.push(mdLite(esc(s.slice(last, m.index))));
    const raw = m[0];
    let expr = null, display = false;
    if (raw.startsWith('$$')) { expr = raw.slice(2, -2); display = true; }
    else if (raw.startsWith('\\[')) { expr = raw.slice(2, -2); display = true; }
    else if (raw.startsWith('\\(')) { expr = raw.slice(2, -2); }
    else { expr = raw.slice(1, -1); }
    if (expr != null && window.katex) {
      try { parts.push(katex.renderToString(expr, { displayMode: display, throwOnError: false, strict: false })); }
      catch (e) { parts.push(esc(raw)); }
    } else parts.push(esc(raw));
    last = re.lastIndex;
  }
  if (last < s.length) parts.push(mdLite(esc(s.slice(last))));
  return parts.join('');
}

function clozeHtml(text) {
  const parts = String(text || '').split('【完型选项】');
  if (parts.length < 2) return '';
  const article = parts[0].trim();
  const lines = parts[1].split('\n').map(s => s.trim()).filter(Boolean);
  const rows = [];
  const re = /^(\d{1,2})\s*[.．]\s*(?:\[)?A(?:\])?\s*[.．]?\s*(.*?)\s+(?:\[)?B(?:\])?\s*[.．]?\s*(.*?)\s+(?:\[)?C(?:\])?\s*[.．]?\s*(.*?)\s+(?:\[)?D(?:\])?\s*[.．]?\s*(.*)$/;
  for (const line of lines) {
    const m = line.match(re);
    if (m) rows.push({no: m[1], a: m[2], b: m[3], c: m[4], d: m[5]});
  }
  if (rows.length < 15) return '';
  const opts = rows.map(r =>
    '<div class="cloze-q"><div class="cloze-no">' + esc(r.no) + '.</div><div class="cloze-grid">' +
    '<div class="cloze-opt"><b>A</b> ' + esc(r.a) + '</div>' +
    '<div class="cloze-opt"><b>B</b> ' + esc(r.b) + '</div>' +
    '<div class="cloze-opt"><b>C</b> ' + esc(r.c) + '</div>' +
    '<div class="cloze-opt"><b>D</b> ' + esc(r.d) + '</div>' +
    '</div></div>'
  ).join('');
  return '<div class="cloze-article">' + mathHtml(article) + '</div>' +
    '<div class="cloze-options"><div class="cloze-title">完型选项</div>' + opts + '</div>';
}

let imageZoom = 1;
let imageMode = '';

function applyImageZoom() {
  const label = $('#imageZoomLabel');
  if (label) label.textContent = Math.round(imageZoom * 100) + '%';
  if (imageMode === 'image') {
    const orig = $('#imageOriginalImg');
    if (orig) orig.style.width = (imageZoom * 100) + '%';
  } else if (imageMode === 'page') {
    const frame = $('#imageFrame');
    try { frame.contentDocument.body.style.zoom = String(imageZoom); } catch (e) { /* 跨域 */ }
  }
}

function resetImageModalView() {
  const img = $('#imageFull');
  const link = $('#imageOriginal');
  const view = $('#imageOriginalView');
  const frame = $('#imageFrame');
  const orig = $('#imageOriginalImg');
  imageZoom = 1;
  imageMode = '';
  state.originalPage = null;
  const pages = document.querySelector('.image-pages');
  if (pages) pages.hidden = true;
  if (img) {
    img.hidden = false;
    img.classList.remove('page-mode');
  }
  if (link) link.hidden = false;
  if (view) view.hidden = true;
  if (frame) {
    frame.hidden = false;
    frame.src = 'about:blank';
  }
  if (orig) {
    orig.hidden = true;
    orig.removeAttribute('src');
    orig.style.width = '';
  }
  const label = $('#imageZoomLabel');
  if (label) label.textContent = '100%';
}

function setOriginalPage(url) {
  const m = String(url || '').match(/\/media\/([^/]+)\/pages\/page-(\d+)\.jpg(\?[^#]*)?$/);
  const wrap = document.querySelector('.image-pages');
  if (!m) {
    state.originalPage = null;
    if (wrap) wrap.hidden = true;
    return;
  }
  const page = parseInt(m[2], 10);
  const total = Math.max(state.paperPages || 1, page);
  state.originalPage = { paper: m[1], page: page, total: total, query: m[3] || '' };
  if (wrap) wrap.hidden = false;
  const label = $('#pageLabel');
  if (label) label.textContent = '第 ' + page + ' / ' + total + ' 页';
  const prev = $('#pagePrev');
  const next = $('#pageNext');
  if (prev) prev.disabled = page <= 1;
  if (next) next.disabled = page >= total;
}

function gotoOriginalPage(page) {
  const info = state.originalPage;
  if (!info) return;
  const target = Math.min(Math.max(1, page), info.total);
  if (target === info.page) return;
  const url = '/media/' + info.paper + '/pages/page-' + String(target).padStart(2, '0') + '.jpg' + (info.query || '');
  showOriginalPage(url);
}

function showOriginalPage(url) {
  document.querySelector('#imageFull').hidden = true;
  document.querySelector('#imageOriginal').hidden = true;
  document.querySelector('#imageOriginalView').hidden = false;
  const frame = document.querySelector('#imageFrame');
  const orig = document.querySelector('#imageOriginalImg');
  const isImage = /\.(png|jpe?g|webp|gif|bmp|svg)([?#]|$)/i.test(url);
  imageZoom = 1;
  setOriginalPage(isImage ? url : null);
  if (isImage) {
    imageMode = 'image';
    orig.hidden = false;
    orig.src = url;
    orig.style.width = '100%';
    frame.hidden = true;
    frame.src = 'about:blank';
  } else {
    imageMode = 'page';
    orig.hidden = true;
    frame.hidden = false;
    frame.onload = () => {
      try {
        const style = frame.contentDocument.createElement('style');
        style.textContent =
          'html,body{margin:0!important;background:#fff!important}' +
          'img{display:block!important;width:100%!important;max-width:none!important;height:auto!important}';
        frame.contentDocument.head.appendChild(style);
      } catch (e) { /* 跨域原页不注入 */ }
      applyImageZoom();
    };
    frame.src = url;
  }
  applyImageZoom();
}

let figureData = null;

function closeFigureModal() {
  const modal = $('#figureModal');
  if (modal) modal.hidden = true;
}

function setFigurePreview(src) {
  const img = $('#figurePreview');
  if (!img) return;
  if (src) {
    img.src = src;
    img.hidden = false;
  } else {
    img.hidden = true;
    img.removeAttribute('src');
  }
}

function setFigureThumb(src) {
  const wrap = $('#figureThumbWrap');
  const img = $('#figureThumb');
  if (!wrap || !img) return;
  if (src) {
    img.src = src;
    wrap.hidden = false;
  } else {
    img.removeAttribute('src');
    wrap.hidden = true;
  }
}

function setFigureHint(text, kind) {
  const el = $('#figureHint');
  if (!el) return;
  el.textContent = text || '';
  el.className = 'figure-hint' + (kind ? ' ' + kind : '');
}

function readFigureFile(file) {
  if (!file || !/^image\//.test(file.type || '')) return;
  const reader = new FileReader();
  reader.onload = () => {
    figureData = String(reader.result || '');
    setFigurePreview(figureData);
    const btn = $('#figureSave');
    if (btn) btn.disabled = false;
    setFigureHint('图片已添加，点「保存并识别」。', 'ok');
  };
  reader.readAsDataURL(file);
}

async function loadFigureInfo() {
  if (!state.paper) return;
  const paper = state.paper;
  const index = Number($('#problem').value || 0);
  try {
    const data = await api('/api/app/figure?paper=' + encodeURIComponent(paper) +
      '&index=' + encodeURIComponent(index));
    if (state.paper !== paper || Number($('#problem').value || 0) !== index) return;
    const btn = $('#figureBtn');
    if (btn) {
      btn.textContent = data.description ? '题图✓' : '题图';
      btn.title = data.description ? '已有题图描述，点击查看或修改' : '添加题图并生成描述';
    }
    const desc = $('#figureDesc');
    if (desc && data.description) desc.value = data.description;
    setFigureThumb(data.image_url || '');
    if (data.image_url) setFigurePreview(data.image_url);
  } catch (e) { /* 没图也不影响讲题 */ }
}

async function openFigureModal() {
  const modal = $('#figureModal');
  if (!modal) return;
  const paper = state.paper;
  const index = Number($('#problem').value || 0);
  figureData = null;
  $('#figureDesc').value = '';
  setFigureHint('');
  const descBox = $('#figureDescBox');
  if (descBox) descBox.hidden = true;
  const descToggle = $('#figureDescToggle');
  if (descToggle) descToggle.textContent = '查看识别描述';
  setFigurePreview('');
  const btn = $('#figureSave');
  if (btn) {
    btn.disabled = false;
    btn.textContent = '保存并识别';
  }
  const saveDesc = $('#figureSaveDesc');
  if (saveDesc) saveDesc.disabled = true;
  const p = state.problems[Number($('#problem').value || 0)];
  const pageBtn = $('#figureOpenPage');
  if (pageBtn) pageBtn.disabled = !(p && (p.page_url || p.image_url));
  modal.hidden = false;
  try {
    const data = await api('/api/app/figure?paper=' + encodeURIComponent(paper) +
      '&index=' + encodeURIComponent(index));
    if (state.paper !== paper || Number($('#problem').value || 0) !== index) return;
    if (data.image_url) setFigurePreview(data.image_url);
    if (data.description) $('#figureDesc').value = data.description;
    if (saveDesc) saveDesc.disabled = false;
  } catch (e) { /* ignore */ }
}

async function saveFigure() {
  if (!figureData) {
    setFigureHint('还没有新图片：先点「添加图片」，或直接在面板里 Ctrl+V 粘贴。', 'err');
    status('先添加一张题图。', 'err');
    return;
  }
  const btn = $('#figureSave');
  btn.disabled = true;
  btn.textContent = '识别中…';
  setFigureHint('正在识别题图，请稍等…');
  status('正在识别题图…');
  try {
    const data = await api('/api/app/figure', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper: state.paper,
        index: Number($('#problem').value || 0),
        image: figureData,
      })
    });
    if (data.image_url) {
      setFigurePreview(data.image_url);
      setFigureThumb(data.image_url);
    }
    if (data.description) $('#figureDesc').value = data.description;
    figureData = null;
    const b = $('#figureBtn');
    if (b) b.textContent = '题图✓';
    const sd = $('#figureSaveDesc');
    if (sd) sd.disabled = false;
    setFigureHint('已保存。识别描述在「查看识别描述」里，可修改。', 'ok');
    status('题图已保存，之后复述直接读描述。', 'ok');
  } catch (e) {
    setFigureHint('识别失败：' + e.message, 'err');
    status('题图识别失败：' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '保存并识别';
  }
}

async function saveFigureDesc() {
  const desc = $('#figureDesc').value.trim();
  const btn = $('#figureSaveDesc');
  if (btn) btn.disabled = true;
  try {
    await api('/api/app/figure', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'description',
        paper: state.paper,
        index: Number($('#problem').value || 0),
        description: desc,
      })
    });
    const b = $('#figureBtn');
    if (b) b.textContent = desc ? '题图✓' : '题图';
    setFigureHint('描述已保存。', 'ok');
    status('题图描述已保存。', 'ok');
  } catch (e) {
    setFigureHint('保存描述失败：' + e.message, 'err');
    status('保存描述失败：' + e.message, 'err');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function removeFigure() {
  if (!confirm('删除这道题的手动题图和描述？')) return;
  try {
    await api('/api/app/figure', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', paper: state.paper, index: Number($('#problem').value || 0) })
    });
    setFigurePreview('');
    setFigureThumb('');
    $('#figureDesc').value = '';
    figureData = null;
    const b = $('#figureBtn');
    if (b) b.textContent = '题图';
    const sd = $('#figureSaveDesc');
    if (sd) sd.disabled = true;
    setFigureHint('题图已删除。', 'ok');
    status('题图已删除。', 'ok');
  } catch (e) {
    setFigureHint('删除失败：' + e.message, 'err');
    status('删除失败：' + e.message, 'err');
  }
}

function openImage(src, original, pageMode) {
  const modal = $('#imageModal');
  const img = $('#imageFull');
  const link = $('#imageOriginal');
  if (!modal || !img || !src) return;
  resetImageModalView();
  img.src = src;
  img.classList.toggle('page-mode', !!pageMode);
  if (link) link.dataset.href = original || src;
  modal.hidden = false;
  const close = $('#imageClose');
  if (close) close.focus();
}

function fmtDueTime(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  const now = new Date();
  const y = d.getFullYear() === now.getFullYear() ? '' : (d.getFullYear() + '年');
  return y + (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function relDueTime(iso) {
  const ms = new Date(iso).getTime() - Date.now();
  if (!isFinite(ms)) return '';
  const abs = Math.abs(ms);
  const suffix = ms < 0 ? '前' : '后';
  const mins = Math.round(abs / 60000);
  if (mins < 60) return '约 ' + Math.max(1, mins) + ' 分钟' + suffix;
  const hours = Math.round(abs / 3600000);
  if (hours < 48) return '约 ' + hours + ' 小时' + suffix;
  return '约 ' + Math.round(abs / 86400000) + ' 天' + suffix;
}

function renderProblem() {
  const p = state.problems[Number($('#problem').value || 0)];
  if (!p) { $('#problemText').textContent = '这张卷子没有题。'; return; }
  state.problemType = p.type || 'single';
  const opts = p.options || [];
  const imageOpts = opts.filter(o => o && o.image_url);
  let html = (p.type === 'cloze' && clozeHtml(p.text)) || '<div>' + mathHtml(p.text || '') + '</div>';
  if (p.crop && !imageOpts.length && (state.subjectId === 'cs408' || /[图表]/.test(p.text || ''))) {
    const src = p.retake ? p.image_url : (p.crop_url || p.page_url);
    const link = p.page_url || src;
    html += '<a href="' + esc(link) + '" target="_blank" rel="noopener"><img class="problem-img" src="' + esc(src) + '" alt="原题图" title="点开看大图"></a>';
  }
  if (imageOpts.length) {
    html += '<div class="opt-image-grid">' + imageOpts.map(o =>
      '<div class="opt opt-image"><b>' + esc(o.label || '') + '</b>' +
      '<a href="' + esc(o.image_url) + '" target="_blank" rel="noopener">' +
      '<img class="opt-img" src="' + esc(o.image_url) + '" alt="选项 ' + esc(o.label || '') + '"></a></div>'
    ).join('') + '</div>';
  }
  opts.filter(o => !o.image_url).forEach(o => {
    html += '<div class="opt"><b>' + esc(o.label || '') + '</b><span>' + mathHtml(o.text || '') + '</span></div>';
  });
  if (p.last_session_at) {
    const d = new Date(p.last_session_at * 1000);
    const pad = n => String(n).padStart(2, '0');
    const when = (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    const rounds = p.last_session_turns ? ' · ' + p.last_session_turns + ' 轮对话' : '';
    const note = p.last_session_open
      ? '上次没结束；直接发第一句会接上次的对话。'
      : '上次已结束；这次是新会话。';
    html = '<div class="last-hint">这题上次练过：' + when + rounds + '。' + note + '</div>' + html;
  }
  if (p.review_due) {
    const dueMs = new Date(p.review_due).getTime();
    if (isFinite(dueMs) && dueMs <= Date.now()) {
      html = '<div class="review-hint due">⏰ 到期复习：原定 ' + esc(fmtDueTime(p.review_due)) + ' 到期（' + esc(relDueTime(p.review_due)) + '）</div>' + html;
    } else if (isFinite(dueMs)) {
      html = '<div class="review-hint">✅ 已复习过 · 下次到期 ' + esc(fmtDueTime(p.review_due)) + '（' + esc(relDueTime(p.review_due)) + '）</div>' + html;
    }
  }
  $('#problemText').innerHTML = html;
  loadFigureInfo();
}

function tutorMode() {
  if (state.reviewMode) return 'review';
  return state.examMode ? 'exam' : 'tutor';
}

async function restoreHistory() {
  if (!state.paper) return;
  const paper = state.paper;
  const index = Number($('#problem').value || 0);
  try {
    const data = await api('/api/session/history?paper=' + encodeURIComponent(paper) + '&index=' + encodeURIComponent(index));
    if (state.paper !== paper || Number($('#problem').value || 0) !== index) return;
    state.sessionId = data.sessionId || null;
    const batches = data.batches || [];
    state.batches = [];
    state.history = [];
    batches.forEach((b, bi) => {
      const turns = (b.turns || []).filter(t => t.role === 'user' || t.role === 'assistant' || t.role === 'summary');
      if (!turns.length) return;
      const when = b.rated_at || b.ended_at || b.created_at;
      const label = batchLabel(bi + 1, when, !b.ended_at, b.rating);
      state.batches.push({ id: b.id, label: label });
      turns.forEach((t, ti) => {
        const isUser = t.role === 'user';
        state.history.push({
          role: t.role,
          content: t.content || '',
          display: isUser ? (t.speech || '') : '',
          raw: isUser ? (t.content || '') : '',
          created_at: t.created_at,
          session_id: b.id,
          batchStart: ti === 0,
          batchLabel: ti === 0 ? label : '',
        });
      });
    });
    state.batchCount = state.batches.length;
    renderHistory();
  } catch (e) { /* 历史接口失败不影响讲题 */ }
}

async function openSession(mode, opts) {
  opts = opts || {};
  const p = state.problems[Number($('#problem').value || 0)];
  if (!state.paper || !p) { state.sessionId = null; return; }
  try {
    const data = await api('/api/session', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper: state.paper, index: Number($('#problem').value || 0), mode: mode || 'tutor', model: $('#modelSelect').value })
    });
    state.sessionId = data.id;
    state.reviewMode = data.mode === 'review';
    const turns = (data.turns || [])
      .filter(t => t.role === 'user' || t.role === 'assistant' || t.role === 'summary')
      .map(t => ({
        role: t.role,
        content: t.content || '',
        display: t.role === 'user' ? (t.speech || '') : '',
        raw: t.role === 'user' ? (t.content || '') : '',
        created_at: t.created_at,
      }));
    if (!(opts.keepHistory && state.history.length && !turns.length)) {
      state.history = turns;
    }
    if (!opts.keepDraft) state.segments = [];
    renderHistory();
    renderSegments();
    updateBubble();
    $('#reviewBanner').hidden = !state.reviewMode;
    setFinishLabel(state.reviewMode);
    setComposer(false);
  } catch (e) {
    state.sessionId = null;
  }
}

async function loadPaper(id, opts) {
  opts = opts || {};
  const token = ++state.paperToken;
  state.paper = id;
  const paperMeta = state.papers.find(x => x.id === id);
  state.subjectId = (paperMeta && paperMeta.subject_id) || 'math2';
  state.problemType = 'single';
  const paperSel = $('#paper');
  const problemSel = $('#problem');
  paperSel.disabled = true;
  problemSel.disabled = true;
  try {
    const data = await api('/api/paper/' + encodeURIComponent(id));
    if (token !== state.paperToken) return;
    paperSel.value = id;
    state.problems = data.problems || [];
    state.paperPages = data.pages || 1;
    problemSel.innerHTML = '';
    state.problems.forEach((p, i) => {
      const o = document.createElement('option');
      o.value = i;
      o.textContent = '第 ' + (p.no || i + 1) + ' 题';
      problemSel.appendChild(o);
    });
    renderProblem();
  } finally {
    if (token === state.paperToken) {
      paperSel.disabled = false;
      problemSel.disabled = false;
    }
  }
}

async function loadConfig() {
  try {
    const h = await api('/api/health');
    state.health = h;
    const sel = $('#modelSelect');
    const models = (h.models || []).filter(m => m.available);
    sel.innerHTML = '';
    models.forEach(m => {
      const o = document.createElement('option');
      o.value = m.id;
      o.textContent = m.label;
      sel.appendChild(o);
    });
    if (!models.length) {
      const o = document.createElement('option');
      o.textContent = '无可用模型';
      o.disabled = true;
      sel.appendChild(o);
    } else {
      const saved = localStorage.getItem('tutorModel');
      const pick = models.find(m => m.id === saved) || models.find(m => m.id === h.chatModel) || models[0];
      sel.value = pick.id;
    }
    sel.title = '讲题：' + (sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : h.chatModel || '') +
      ' · ASR ' + (h.asrModel || '') + ' · TTS ' + (h.ttsModel || '');
  } catch (e) { /* 健康接口失败不影响讲题 */ }
}

async function loadCompanionConfig() {
  try {
    const data = await api('/api/companion/config');
    if (data && data.preference) state.companionConfig = data;
  } catch (e) { /* 配置接口失败用默认值 */ }
}

function syncPosition() {
  if (!state.paper) return;
  const index = String($('#problem').value || 0);
  const u = new URL(location.href);
  u.searchParams.set('paper', state.paper);
  u.searchParams.set('index', index);
  history.replaceState(null, '', u);
  try {
    sessionStorage.setItem('tutorLastPosition', JSON.stringify({ paper: state.paper, index: Number(index) }));
  } catch (e) { /* ignore */ }
  // 让计划页的「下一题」知道我现在在哪一卷/哪一题
  try {
    fetch('/api/app/position', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper: state.paper, index: Number(index) }),
    }).catch(() => {});
  } catch (e) { /* ignore */ }
}

async function loadPapers() {
  const data = await api('/api/papers');
  state.papers = data.papers || [];
  const sel = $('#paper');
  sel.innerHTML = '';
  state.papers.forEach(p => {
    const o = document.createElement('option');
    o.value = p.id;
    o.textContent = (p.title || p.id) + '（' + p.problems + ' 题）';
    sel.appendChild(o);
  });
  if (state.papers.length) await loadPaper(state.papers[0].id);
  else $('#problemText').textContent = '还没有卷子，先去切题校正页上传。';
}

function resetSession() {
  state.history = [];
  state.segments = [];
  state.sessionId = null;
  state.batches = [];
  state.batchCount = 0;
  state.turnsSincePref = 0;
  state.prefCount = 0;
  state.prefPair = null;
  hidePrefCard();
  state.inputDirty = false;
  if (state.selectMode) {
    state.selectMode = false;
    state.selected = new Set();
    const bar = $('#selectBar');
    if (bar) bar.hidden = true;
    const btn = $('#selectBtn');
    if (btn) btn.textContent = '多选';
  }
  state.doubtAsked = false;
  renderHistory();
  renderSegments();
  updateBubble();
  const a = $('#audio');
  try { a.pause(); } catch (e) {}
  a.removeAttribute('src');
  $('#audioRow').hidden = true;
  state.reviewMode = false;
  $('#reviewBanner').hidden = true;
  setFinishLabel(false);
  setComposer(false);
}

function renderDue() {
  const box = $('#dueList');
  box.innerHTML = '';
  state.due.forEach(item => {
    const b = document.createElement('button');
    b.className = 'due-item';
    const due = item.due ? new Date(item.due).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
    const snippet = (item.summary && item.summary.outline) || '';
    b.innerHTML = '<div class="due-title">第 ' + esc(item.no || '?') + ' 题</div>' +
      '<div class="due-meta">' + esc(item.paper || '') + ' · 到期 ' + esc(due) + '</div>' +
      '<div class="due-snippet">' + esc(snippet) + '</div>';
    b.onclick = () => loadReview(item);
    box.appendChild(b);
  });
}

async function loadDue() {
  try {
    const data = await api('/api/reviews/due');
    state.due = data.reviews || [];
    const c = $('#dueCount');
    if (c) c.textContent = state.due.length;
    if ($('#dueModal') && !$('#dueModal').hidden) renderDue();
  } catch (e) { /* 到期接口失败不影响讲题 */ }
}

async function loadReview(item) {
  $('#dueModal').hidden = true;
  try {
    await loadPaper(item.paper, { skipSession: true });
    $('#problem').value = String(item.index);
    renderProblem();
    resetSession();
    await openSession('review');
    $('#reviewBanner').hidden = false;
    setFinishLabel(true);
    status('整题复述：把这道题完整讲一遍，我不会主动提示。', 'ok');
  } catch (e) {
    status('打开到期题失败：' + e.message, 'err');
  }
}

function mergeChunks(chunks) {
  let n = 0;
  chunks.forEach(c => { n += c.length; });
  const out = new Float32Array(n);
  let off = 0;
  chunks.forEach(c => { out.set(c, off); off += c.length; });
  return out;
}

// 裁掉首尾静音（保守：短录音不裁、保留足够余量），让“有声%”反映说话部分
function trimSilence(data, sampleRate) {
  if (data.length < sampleRate * 1.5) return data;
  const win = Math.max(1, Math.round(sampleRate * 0.1));
  const n = Math.floor(data.length / win);
  if (n < 3) return data;
  const threshold = 0.004;
  let first = -1, last = -1;
  for (let k = 0; k < n; k++) {
    let s2 = 0;
    const start = k * win;
    for (let j = start; j < start + win; j++) s2 += data[j] * data[j];
    if (Math.sqrt(s2 / win) > threshold) {
      if (first < 0) first = k;
      last = k;
    }
  }
  if (first < 0) return data;
  const margin = Math.round(0.3 * sampleRate);
  const start = Math.max(0, first * win - margin);
  const end = Math.min(data.length, (last + 1) * win + margin);
  if (end - start < sampleRate * 0.3) return data;
  if (data.length - (end - start) < sampleRate * 0.25) return data;
  return data.subarray(start, end);
}

function downsample(data, inRate, outRate) {
  if (outRate === inRate) return data;
  const ratio = inRate / outRate;
  const len = Math.max(1, Math.round(data.length / ratio));
  const out = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    const start = Math.round(i * ratio);
    const end = Math.min(data.length, Math.round((i + 1) * ratio));
    let sum = 0, n = 0;
    for (let j = start; j < end; j++) { sum += data[j]; n++; }
    out[i] = n ? sum / n : 0;
  }
  return out;
}

function encodeWav(samples, sampleRate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const w = (off, s) => { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE');
  w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, 'data'); v.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    off += 2;
  }
  return buf;
}

function audioConstraints() {
  // 耳机输出时关掉回声消除：浏览器会把“正在播放的声音”当回声，白噪音持续播放时容易连人声一起压掉
  const headphone = state.headphoneOut === true && !speakerMode;
  return {
    channelCount: 1,
    echoCancellation: !speakerMode && !headphone,
    noiseSuppression: !speakerMode,
    autoGainControl: { ideal: true },
    sampleRate: { ideal: 16000 },
  };
}

function b64(buf) {
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

async function startRecording(target) {
  target = target || 'main';
  let carryEdited = false;
  if (target === 'main') {
    const typed = $('#chatInput').value.trim();
    const old = $('#transcript').value.trim();
    if (typed !== old) {
      $('#transcript').value = typed;
      state.segments = [];
      renderSegments();
      state.inputDirty = !!typed;
      carryEdited = !!typed;
    }
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    status('这个浏览器不支持录音，换 Chrome/Edge。', 'err');
    return;
  }
  let stream;
  let fellBack = false;
  const audio = audioConstraints();
  if (micDeviceId) audio.deviceId = { exact: micDeviceId };
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio });
  } catch (e) {
    if (micDeviceId) {
      try {
        delete audio.deviceId;
        stream = await navigator.mediaDevices.getUserMedia({ audio });
        fellBack = true;
        status('选中的麦克风不可用，这次退回系统默认。', 'err');
      } catch (e2) {
        status('麦克风打不开：' + e2.message, 'err');
        return;
      }
    } else {
      status('麦克风打不开：' + e.message, 'err');
      return;
    }
  }
  refreshMicDevices();
  const micSel = $('#micSelect');
  let micLabel = micSel && micSel.selectedOptions[0] ? micSel.selectedOptions[0].textContent : '系统默认';
  if (!micDeviceId) micLabel = '系统默认';
  if (fellBack) micLabel += '（回落默认）';
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  await ctx.resume();
  const source = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const gain = ctx.createGain();
  gain.gain.value = 0;
  const chunks = [];
  proc.onaudioprocess = e => { chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
  source.connect(proc);
  proc.connect(gain);
  gain.connect(ctx.destination);
  const button = target === 'finish' ? $('#finishMic') : $('#mic');
  rec = { stream, ctx, source, proc, gain, chunks, sampleRate: ctx.sampleRate, started: Date.now(), target, button, carryEdited, micLabel };
  rec.timer = setTimeout(() => { if (rec) stopRecording(true); }, 60000);
  $('#voiceBubble').hidden = true;
  button.textContent = target === 'finish' ? '⏹ 停止' : '⏹';
  button.classList.add('rec');
  button.disabled = false;
  const hpNote = (!speakerMode && state.headphoneOut === true) ? ' · 耳机输出，已关回声消除' : '';
  status('录音中…（' + micLabel + hpNote + '）再按一下停止。');
}

async function stopRecording(auto) {
  const r = rec;
  if (!r) return;
  rec = null;
  clearTimeout(r.timer);
  try { r.proc.disconnect(); r.source.disconnect(); r.gain.disconnect(); } catch (e) {}
  r.stream.getTracks().forEach(t => t.stop());
  const seconds = (Date.now() - r.started) / 1000;
  await r.ctx.close();
  r.button.textContent = r.target === 'finish' ? '🎤 语音' : '🎤';
  r.button.classList.remove('rec');
  if (seconds < 0.35) { status('太短了，再说一次。', 'err'); return; }
  const mergedAll = mergeChunks(r.chunks);
  const merged = trimSilence(mergedAll, r.sampleRate);
  const trimmedSec = Math.max(0, (mergedAll.length - merged.length) / r.sampleRate);
  let peak = 0, sq = 0;
  for (let i = 0; i < merged.length; i++) {
    const v = Math.abs(merged[i]);
    if (v > peak) peak = v;
    sq += merged[i] * merged[i];
  }
  const rms = merged.length ? Math.sqrt(sq / merged.length) : 0;
  let active = 0, frames = 0;
  const win = Math.max(1, Math.round(r.sampleRate * 0.1));
  for (let i = 0; i + win <= merged.length; i += win) {
    let s2 = 0;
    for (let j = i; j < i + win; j++) s2 += merged[j] * merged[j];
    if (Math.sqrt(s2 / win) > 0.01) active++;
    frames++;
  }
  const activePct = frames ? Math.round(active * 100 / frames) : 0;
  let gain = 1;
  if (peak > 0.0005 && peak < 0.25) gain = Math.min(0.9 / peak, 6);
  if (gain > 1.01) {
    for (let i = 0; i < merged.length; i++) merged[i] = Math.max(-1, Math.min(1, merged[i] * gain));
  }
  const levelNote = '（峰值 ' + peak.toFixed(3) + '，平均 ' + rms.toFixed(3) + '，有声 ' + activePct + '%'
    + (gain > 1.01 ? '，放大 ' + gain.toFixed(1) + 'x' : '') + '）';
  const recLevel = $('#recLevel');
  if (recLevel) {
    recLevel.hidden = false;
    const eff = trimmedSec > 0.3 ? ' · 有效 ' + (merged.length / r.sampleRate).toFixed(1) + 's' : '';
    recLevel.textContent = '上次录音（' + (r.micLabel || '系统默认') + '）：' + levelNote + eff;
  }
  if (peak < 0.002) {
    r.button.disabled = false;
    status('没听到声音' + levelNote + '：检查顶部「麦克风」选的设备、系统输入音量；用 Broadcast 时先确认降噪开关已开、电平条会跳。', 'err');
    return;
  }
  // 只录到一下杂音/极短音节时不送识别，避免模型拿题目上下文“脑补”出整句话
  const speechSec = merged.length / r.sampleRate;
  const activeFrames = frames ? Math.round(activePct * frames / 100) : 0;
  if (speechSec < 0.45 && activeFrames < 3) {
    r.button.disabled = false;
    status('没听完整' + levelNote + '：可能只录到一下声音，靠近麦克风完整说一句再停。', 'err');
    return;
  }
  const wav = encodeWav(downsample(merged, r.sampleRate, 16000), 16000);
  status(auto ? '到 60 秒了，正在识别…' : '正在识别…');
  r.button.disabled = true;
  try {
    const data = await api('/api/asr', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio: 'data:audio/wav;base64,' + b64(wav), context: asrContext() })
    });
    if (data.silent) {
      r.button.disabled = false;
      status('没听到声音' + levelNote + '（服务端判定静音）：检查麦克风设备/输入音量。', 'err');
      return;
    }
    if (data.echo) {
      r.button.disabled = false;
      status('这段听起来像题目原文（多半是声音太小或没录清），没听清，再说一次。', 'err');
      return;
    }
    const heard = String(data.text || '').trim();
    if (r.target === 'finish') {
      const old = $('#finishSummary').value.trim();
      $('#finishSummary').value = old ? (old + '\n' + heard).trim() : heard;
      if (!heard) status('录音收到了，但没识别出文字' + levelNote + '。检查麦克风/输入音量，或靠近再说一次。', 'err');
      else status('识别完成，可改字后提交。' + levelNote, 'ok');
      return;
    }
    const old = $('#transcript').value.trim();
    const mergedText = old ? (old + '\n' + heard).trim() : heard;
    $('#transcript').value = mergedText;
    $('#chatInput').value = mergedText;
    state.inputDirty = !!r.carryEdited;
    autoGrowInput();
    if (!heard) {
      if (activePct < 25) {
        status('录音里大部分没声音（有声 ' + activePct + '%）' + levelNote + '：可能是降噪/门限把话掐断了，或麦克风没对准；换「麦克风阵列」再试一次。', 'err');
      } else {
        status('录音收到了，但没识别出文字' + levelNote + '。检查麦克风选择/输入音量，或靠近再说一次。', 'err');
      }
    } else if (peak < 0.004) {
      status('识别完成，但录音很小声' + levelNote + '，建议靠麦克风近一点。', 'err');
    } else {
      status('识别完成。可直接发送，也可以改字。' + levelNote, 'ok');
    }
    normalizeNew(heard);
  } catch (e) {
    status('识别失败：' + e.message, 'err');
  } finally {
    r.button.disabled = false;
  }
}

const ASR_TERMS = {
  cs408: '无向图 有向图 连通图 强连通 顶点 度 入度 出度 边数 邻接矩阵 邻接表 生成树 拓扑排序 关键路径 最短路径 二叉树 遍历 哈希 栈 队列 排序 时间复杂度 渐进 页表 虚拟内存 中断 DMA 流水线 CPI 指令 缓存 拥塞控制 路由 子网 文件系统',
  math2: '极限 连续 可导 导数 微分 积分 中值定理 偏导 全微分 矩阵 行列式 特征值 特征向量 二次型 概率 期望 方差 分布 收敛 级数 切线 法线 极值 驻点 拐点 泰勒 等价无穷小',
  english2: '完形 阅读 翻译 写作 作文 段落 主旨 细节 词汇',
};

function asrContext() {
  const p = state.problems[Number($('#problem').value || 0)];
  if (!p) return '';
  const opts = (p.options || []).map(o => (o.label || '') + '. ' + (o.text || '')).join('\n');
  const terms = ASR_TERMS[state.subjectId] || ASR_TERMS.math2;
  const said = ($('#transcript').value || '').trim();
  const parts = [
    '科目：' + (state.subjectId || ''),
    '题目：' + (p.text || ''),
    opts ? '选项：\n' + opts : '',
    '本卷常见术语（听写时按这些写法）：' + terms,
    said ? '刚才已经说过（保持术语一致）：' + said.slice(-200) : '',
  ].filter(Boolean);
  return parts.join('\n').slice(0, 2500);
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(Number(ts) * 1000);
  if (isNaN(d.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  const now = new Date();
  const hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
  if (d.toDateString() === now.toDateString()) return hm;
  return (d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + hm;
}

function batchLabel(index, ts, open, rating) {
  const d = ts ? new Date(Number(ts) * 1000) : new Date();
  const pad = n => String(n).padStart(2, '0');
  const when = d.getMonth() + 1 + '月' + d.getDate() + '日 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  return '第 ' + index + ' 次复述 · ' + when + (rating ? ' · ' + rating : '') + (open ? ' · 进行中' : '');
}

function renderHistory() {
  const box = $('#reply');
  box.innerHTML = '';
  state.history.forEach((m, idx) => {
    if (m.batchStart) {
      const sep = document.createElement('div');
      sep.className = 'batch-sep';
      sep.textContent = m.batchLabel || '新一次复述';
      box.appendChild(sep);
    }
    if (m.role === 'summary') {
      const srow = document.createElement('div');
      srow.className = 'msg-row summary-row';
      srow.dataset.index = String(idx);
      const card = document.createElement('div');
      card.className = 'finish-card';
      card.innerHTML = '<div class="card-title">学伴总结</div>' +
        '<div class="card-body">' + mathHtml(m.content || '') + '</div>';
      srow.appendChild(card);
      box.appendChild(srow);
      return;
    }
    const row = document.createElement('div');
    row.className = 'msg-row ' + (m.role === 'assistant' ? 'agent' : 'user');
    row.dataset.index = String(idx);
    if (state.selectMode) {
      row.classList.add('selectable');
      if (state.selected.has(idx)) row.classList.add('selected');
      const check = document.createElement('span');
      check.className = 'msg-check';
      check.textContent = state.selected.has(idx) ? '✓' : '';
      row.prepend(check);
    }
    const d = document.createElement('div');
    d.className = 'msg ' + (m.role === 'assistant' ? 'agent' : 'user');
    if (m.raw) d.title = '原文：' + m.raw;
    d.innerHTML = mathHtml(m.display || m.content);
    row.appendChild(d);
    const time = formatTime(m.created_at);
    if (time) {
      const t = document.createElement('span');
      t.className = 'msg-time';
      t.textContent = time;
      row.appendChild(t);
    }
    box.appendChild(row);
  });
  const last = box.lastElementChild;
  if (last) last.scrollIntoView({ block: 'nearest' });
  requestAnimationFrame(renderBatchMarks);
}

function selectedMessage() {
  if (state.selected.size !== 1) return null;
  const idx = [...state.selected][0];
  const m = state.history[idx];
  return m ? { idx, message: m } : null;
}

function turnIndexInSession(idx) {
  const m = state.history[idx];
  if (!m || !m.session_id) return -1;
  let n = 0;
  for (let i = 0; i < idx; i++) {
    if (state.history[i].session_id === m.session_id) n++;
  }
  return n;
}

function selectionIsCurrentSession() {
  const s = selectedMessage();
  return !!(s && state.sessionId && s.message.session_id === state.sessionId);
}

function updateSelectBar() {
  const count = state.selected.size;
  const c = $('#selectCount');
  if (c) c.textContent = String(count);
  const copy = $('#selectCopy');
  const exp = $('#selectExport');
  const rollback = $('#selectRollback');
  const regen = $('#selectRegen');
  const s = selectedMessage();
  if (copy) copy.disabled = !count;
  if (exp) exp.disabled = !count;
  if (rollback) rollback.disabled = !selectionIsCurrentSession();
  if (regen) {
    if (!s || !selectionIsCurrentSession() || s.message.role !== 'assistant') {
      regen.disabled = true;
    } else {
      let found = false;
      for (let i = s.idx - 1; i >= 0; i--) {
        const m = state.history[i];
        if (m.session_id !== s.message.session_id) break;
        if (m.role === 'user') { found = true; break; }
      }
      regen.disabled = !found;
    }
  }
}

function toggleSelectMode(on) {
  state.selectMode = !!on;
  state.selected = new Set();
  const bar = $('#selectBar');
  if (bar) bar.hidden = !state.selectMode;
  const btn = $('#selectBtn');
  if (btn) btn.textContent = state.selectMode ? '退出多选' : '多选';
  renderHistory();
  updateSelectBar();
}

function toggleMessageSelection(row) {
  const idx = Number(row.dataset.index);
  if (!Number.isInteger(idx)) return;
  if (state.selected.has(idx)) state.selected.delete(idx);
  else state.selected.add(idx);
  row.classList.toggle('selected', state.selected.has(idx));
  const check = row.querySelector('.msg-check');
  if (check) check.textContent = state.selected.has(idx) ? '✓' : '';
  updateSelectBar();
}

function buildExportText() {
  const p = state.problems[Number($('#problem').value || 0)];
  const paper = $('#paper').selectedOptions[0] ? $('#paper').selectedOptions[0].textContent : (state.paper || '');
  const lines = [];
  lines.push('# 对话分析包');
  lines.push('');
  lines.push('## 背景');
  lines.push('- 试卷：' + paper);
  lines.push('- 题号：' + (p ? ('第' + (p.no || '') + '题') : '未知'));
  lines.push('- 科目：' + (state.subjectId || ''));
  if (p && p.text) lines.push('- 题目：' + String(p.text).replace(/\s+/g, ' ').trim());
  lines.push('');
  const picked = [...state.selected].sort((a, b) => a - b);
  lines.push('## 对话');
  picked.forEach(i => {
    const m = state.history[i];
    if (!m) return;
    if (m.batchStart && m.batchLabel) {
      lines.push('');
      lines.push('### ' + m.batchLabel);
    }
    const who = m.role === 'summary' ? '学伴总结' : (m.role === 'assistant' ? '讲伴' : '我');
    const t = formatTime(m.created_at);
    lines.push('[' + (t || '') + '] ' + who + '：' + (m.content || ''));
  });
  lines.push('');
  lines.push('## 请分析');
  lines.push('哪一轮让你不舒服、它当时做了什么、差在哪一层，只提一个最小改动。');
  return lines.join('\n');
}

function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  ta.remove();
  return Promise.resolve();
}

async function exportSelected(copyOnly) {
  if (!state.selected.size) return;
  const text = buildExportText();
  try {
    await copyText(text);
    if (copyOnly) {
      const msg = '已复制分析包，可粘贴到分析对话中。';
      status(msg, 'ok');
      setTimeout(() => {
        if ($('#status').textContent === msg) status('');
      }, 3000);
      return;
    }
    const p = state.problems[Number($('#problem').value || 0)];
    const r = await api('/api/chat/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: (p ? ('第' + (p.no || '') + '题') : 'chat'),
        text,
      })
    });
    status('已导出：' + r.path, 'ok');
  } catch (e) {
    status('导出失败：' + e.message, 'err');
  }
}

async function rollbackSelected() {
  const s = selectedMessage();
  if (!s) return;
  if (!selectionIsCurrentSession()) {
    status('只能回退当前这次复述。', 'err');
    return;
  }
  const turnIndex = turnIndexInSession(s.idx);
  if (turnIndex < 0) return;
  if (!confirm('回退到这条消息之前？这条及之后的消息会从当前复述中移除。')) return;
  try {
    await api('/api/session/' + encodeURIComponent(state.sessionId) + '/rollback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: turnIndex })
    });
    state.history = state.history.slice(0, s.idx);
    toggleSelectMode(false);
    await restoreHistory();
    status('已回退到此前。', 'ok');
  } catch (e) {
    status('回退失败：' + e.message, 'err');
  }
}

async function regenerateSelected() {
  const s = selectedMessage();
  if (!s || s.message.role !== 'assistant') return;
  if (!selectionIsCurrentSession()) {
    status('只能重新生成当前这次复述。', 'err');
    return;
  }
  let userIdx = -1;
  for (let i = s.idx - 1; i >= 0; i--) {
    const m = state.history[i];
    if (m.session_id !== s.message.session_id) break;
    if (m.role === 'user') { userIdx = i; break; }
  }
  if (userIdx < 0) {
    status('这条回复前面没有对应的学生发言。', 'err');
    return;
  }
  const turnIndex = turnIndexInSession(userIdx);
  const userText = state.history[userIdx].content || '';
  try {
    status('正在重新生成…');
    await api('/api/session/' + encodeURIComponent(state.sessionId) + '/rollback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: turnIndex })
    });
    state.history = state.history.slice(0, userIdx);
    toggleSelectMode(false);
    state.segments = [];
    renderSegments();
    state.inputDirty = true;
    $('#chatInput').value = userText;
    autoGrowInput();
    await send();
  } catch (e) {
    status('重新生成失败：' + e.message, 'err');
  }
}

function renderBatchMarks() {
  const chat = document.querySelector('.chat');
  const rail = $('#batchMarks');
  if (!chat || !rail) return;
  const pane = rail.parentElement;
  const chatRect = chat.getBoundingClientRect();
  const paneRect = pane.getBoundingClientRect();
  rail.style.top = (chatRect.top - paneRect.top) + 'px';
  rail.style.height = chatRect.height + 'px';
  rail.innerHTML = '';
  const seps = [...chat.querySelectorAll('.batch-sep')];
  if (!seps.length) return;
  const total = chat.scrollHeight || 1;
  seps.forEach(sep => {
    const offset = sep.getBoundingClientRect().top - chatRect.top + chat.scrollTop;
    const mark = document.createElement('button');
    mark.type = 'button';
    mark.className = 'batch-mark';
    mark.style.top = Math.max(0, Math.min(100, offset / total * 100)) + '%';
    mark.title = sep.textContent;
    mark.addEventListener('click', () => {
      chat.scrollTo({ top: Math.max(0, offset - 10), behavior: 'smooth' });
    });
    rail.appendChild(mark);
  });
}

function formulaContext(index) {
  const p = state.problems[Number($('#problem').value || 0)];
  const parts = [];
  if (p) {
    parts.push('题目：' + (p.text || '') + '\n' + (p.options || []).map(o => (o.label || '') + '. ' + (o.text || '')).join('\n'));
  }
  const prior = state.segments.slice(0, index).map(s => s.normalized || s.raw).filter(Boolean);
  if (prior.length) parts.push('前文：\n' + prior.join('\n'));
  return parts.join('\n');
}

function renderSegments() {
  const box = $('#normalized');
  const dock = $('#formulaDock');
  if (dock) {
    dock.hidden = !state.segments.length;
    dock.classList.remove('is-sending');
  }
  box.innerHTML = '';
  $('#segCount').textContent = state.segments.length ? '（' + state.segments.length + ' 句）' : '';
  if (!state.segments.length) {
    box.textContent = '识别后自动整理成 LaTeX，方便你检查哪里听错了。';
    return;
  }
  state.segments.forEach((s, i) => {
    const card = document.createElement('div');
    card.className = 'seg';
    const body = document.createElement('div');
    body.className = 'seg-body';
    body.innerHTML = s.normalized ? mathHtml(s.normalized) : '<span class="muted">整理中…</span>';
    card.appendChild(body);
    if (s.normalized && s.raw && s.raw !== s.normalized) {
      const raw = document.createElement('div');
      raw.className = 'seg-raw';
      raw.textContent = '原话：' + s.raw;
      card.appendChild(raw);
    }
    const tools = document.createElement('div');
    tools.className = 'seg-tools';
    const re = document.createElement('button');
    re.textContent = '重整本句';
    re.onclick = () => normalizeSegment(i);
    tools.appendChild(re);
    card.appendChild(tools);
    box.appendChild(card);
  });
}

function updateBubble() {
  const bubble = $('#voiceBubble');
  if (!bubble) return;
  if ($('#voiceFab').classList.contains('expanded')) { bubble.hidden = true; return; }
  const last = state.segments[state.segments.length - 1];
  if (!last) { bubble.hidden = true; return; }
  bubble.hidden = false;
  $('#bubbleRaw').textContent = last.raw || '';
  $('#bubbleFormula').innerHTML = last.normalized ? mathHtml(last.normalized) : '<span class="muted">整理中…</span>';
  setTimeout(clampFab, 0);
}

function clampFab() {
  const fab = $('#voiceFab');
  if (!fab.style.left) return;
  const r = fab.getBoundingClientRect();
  const left = Math.max(8, Math.min(window.innerWidth - r.width - 8, parseFloat(fab.style.left) || 0));
  const top = Math.max(8, Math.min(window.innerHeight - r.height - 8, parseFloat(fab.style.top) || 0));
  fab.style.left = left + 'px';
  fab.style.top = top + 'px';
}

async function normalizeSegment(i) {
  const s = state.segments[i];
  if (!s) return;
  s.normalized = '';
  s.confirmed = false;
  s.req = (s.req || 0) + 1;
  const req = s.req;
  renderSegments();
  updateBubble();
  status('整理本句…');
  try {
    const data = await api('/api/normalize', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: s.raw, context: formulaContext(i) })
    });
    if (state.segments[i] !== s || s.req !== req) return;
    s.normalized = data.text || '';
    renderSegments();
    updateBubble();
    status('本句已整理，可继续下一句。', 'ok');
  } catch (e) {
    if (state.segments[i] !== s || s.req !== req) return;
    s.normalized = s.raw;
    renderSegments();
    updateBubble();
    status('本句整理失败，原文仍可发送：' + e.message, 'err');
  }
}

async function normalizeNew(text) {
  if (!String(text || '').trim()) return;
  state.segments.push({ raw: text, normalized: '', confirmed: false });
  updateBubble();
  await normalizeSegment(state.segments.length - 1);
  const box = $('#normalized');
  box.scrollTop = box.scrollHeight;
  updateBubble();
}

async function normalizeAll() {
  const text = ($('#chatInput').value || $('#transcript').value).trim();
  if (!text) {
    state.segments = [];
    renderSegments();
    return;
  }
  state.segments = [];
  state.inputDirty = false;
  await normalizeNew(text);
  const f = $('#normalized').closest('.formula');
  if (f) f.classList.remove('stale');
  status('已按当前输入重新整理。', 'ok');
}

function renderRatings(data) {
  $('#finishPrompt').textContent = '你的总结已记录。选一个评级。';
  $('#finishSummary').disabled = true;
  $('#finishTools').hidden = true;
  $('#finishQuestion').hidden = true;
  $('#ratingBox').hidden = false;
  $('#finishSuggest').textContent = data.reason ? '建议理由：' + data.reason : '';
  const labels = { again: ['重来', '没掌握'], hard: ['困难', '勉强'], good: ['良好', '独立'], easy: ['简单', '很熟'] };
  const row = $('#ratingRow');
  row.innerHTML = '';
  ['again', 'hard', 'good', 'easy'].forEach(key => {
    const b = document.createElement('button');
    b.className = 'rating-btn' + (data.suggested === key ? ' suggested' : '');
    b.dataset.rating = key;
    b.innerHTML = labels[key][0] + '<small>' + labels[key][1] + '</small>';
    b.onclick = () => rateReview(key);
    row.appendChild(b);
  });
  $('#finishDue').textContent = '';
}

function renderAutoRatings(data) {
  $('#finishPrompt').textContent = '学伴总结好了。扫一眼，选评级后自动进入下一题。';
  $('#finishSummary').disabled = false;
  $('#finishTools').hidden = true;
  $('#finishQuestion').hidden = true;
  $('#ratingBox').hidden = false;
  $('#finishSuggest').textContent = data.reason ? '建议理由：' + data.reason : '';
  const labels = { again: ['重来', '没掌握'], hard: ['困难', '勉强'], good: ['良好', '独立'], easy: ['简单', '很熟'] };
  const row = $('#ratingRow');
  row.innerHTML = '';
  ['again', 'hard', 'good', 'easy'].forEach(key => {
    const b = document.createElement('button');
    b.className = 'rating-btn' + (data.suggested === key ? ' suggested' : '');
    b.dataset.rating = key;
    b.innerHTML = labels[key][0] + '<small>' + labels[key][1] + '</small>';
    b.onclick = () => rateReview(key);
    row.appendChild(b);
  });
  $('#finishDue').textContent = '';
}

async function submitFinishSummary() {
  if (!state.finishId) return;
  const text = $('#finishSummary').value.trim();
  if (!text) { status('先写/说一句自己的总结。', 'err'); return; }
  const btn = $('#finishSubmit');
  btn.disabled = true;
  status('对照你的总结…');
  try {
    const r = await api('/api/finish/summary', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: state.finishId, summary: text })
    });
    if (!r.done) {
      $('#finishQuestion').hidden = false;
      $('#finishQuestion').textContent = r.question || '再补充一下最关键的依据。';
      $('#finishPrompt').textContent = '再补充一下你的总结。';
      $('#finishSubmit').textContent = '继续提交';
      status('还有一处没说到。', 'ok');
      return;
    }
    const data = await api('/api/finish/complete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: state.finishId, summary: text })
    });
    state.finish = data;
    state.finishId = null;
    renderRatings(data);
    status('收尾完成，选一个评级。', 'ok');
  } catch (e) {
    status('收尾失败：' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

async function rateReview(rating) {
  document.querySelectorAll('.rating-btn').forEach(b => { b.disabled = true; });
  status('保存评级…');
  try {
    if (!state.finish) {
      if (!state.finishId) throw new Error('收尾会话已过期');
      const summary = $('#finishSummary').value.trim() || '学伴自动总结';
      const complete = await api('/api/finish/complete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: state.finishId, summary })
      });
      state.finish = complete;
      state.finishId = null;
    }
    const data = await api('/api/review', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: state.finish.id, rating, sessionId: state.sessionId })
    });
    const due = new Date(data.due);
    $('#finishDue').textContent = '下次整题复述：' + due.toLocaleString('zh-CN', {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    state.reviewMode = false;
    $('#reviewBanner').hidden = true;
    setFinishLabel(false);
    if (state.sessionId) {
      const sid = state.sessionId;
      state.sessionId = null;
      try {
        await api('/api/session/' + encodeURIComponent(sid) + '/end', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        });
      } catch (e) { /* 会话已结束也不影响评级 */ }
    }
    $('#finishModal').hidden = true;
    $('#endAskModal').hidden = true;
    await nextProblem();
    loadDue();
  } catch (e) {
    document.querySelectorAll('.rating-btn').forEach(b => { b.disabled = false; });
    status('保存失败：' + e.message, 'err');
  }
}

async function nextProblem() {
  if (!state.paper) return;
  const btn = $('#nextBtn');
  btn.disabled = true;
  try {
    const curIndex = Number($('#problem').value || 0);
    let fromPaper = state.paper;
    let fromIndex = curIndex;
    // 被到期复习题拉走时，记住原来的卷；做完到期题后下一题回原卷继续
    const returning = !!(state.detour && state.paper === state.detour.duePaper);
    if (returning) {
      fromPaper = state.detour.originPaper;
      fromIndex = state.detour.originIndex;
    }
    const data = await api('/api/app/problem/' + encodeURIComponent(fromPaper) +
      '/' + encodeURIComponent(fromIndex) + '/next');
    const n = data.next;
    if (n.paper !== fromPaper) {
      if (!state.detour) {
        setDetour({ originPaper: fromPaper, originIndex: fromIndex, duePaper: n.paper, dueIndex: n.index });
      } else {
        setDetour({ originPaper: state.detour.originPaper, originIndex: state.detour.originIndex, duePaper: n.paper, dueIndex: n.index });
      }
    } else if (state.detour && n.paper === state.detour.originPaper) {
      setDetour(null);
    }
    resetSession();
    await loadPaper(n.paper, { skipSession: true });
    $('#problem').value = String(n.index);
    renderProblem();
    syncPosition();
    await restoreHistory();
    status(state.detour ? '到期复习：先做这道，下一题会回到原卷。'
      : (returning ? '已回到原来的卷。' : '已切到下一题。'), 'ok');
  } catch (e) {
    status(e.message === 'no next problem' ? '这是最后一题了。' : ('下一题失败：' + e.message), 'err');
  } finally {
    btn.disabled = false;
  }
}

async function previousProblem() {
  if (!state.paper) return;
  setDetour(null);
  const btn = $('#prevBtn');
  btn.disabled = true;
  try {
    const data = await api('/api/app/problem/' + encodeURIComponent(state.paper) +
      '/' + encodeURIComponent($('#problem').value || 0) + '/prev');
    const p = data.prev;
    resetSession();
    await loadPaper(p.paper, { skipSession: true });
    $('#problem').value = String(p.index);
    renderProblem();
    syncPosition();
    await restoreHistory();
    status('已切到上一题。', 'ok');
  } catch (e) {
    status(e.message === 'no prev problem' ? '这是第一题了。' : ('上一题失败：' + e.message), 'err');
  } finally {
    btn.disabled = false;
  }
}

function contextText() {
  const p = state.problems[Number($('#problem').value || 0)];
  return p ? [p.text || ''].concat((p.options || []).map(o => (o.label || '') + '. ' + (o.text || ''))).join('\n') : '';
}

function hidePrefCard() {
  const card = $('#prefCard');
  if (card) card.hidden = true;
  state.prefPair = null;
}

function renderPrefCard(pair, quote) {
  const card = $('#prefCard');
  const box = $('#prefOptions');
  if (!card || !box) return;
  const q = $('#prefQuote');
  if (q) q.textContent = quote ? ('你刚才说：' + quote) : '';
  box.innerHTML = '';
  [['A', pair.a.text], ['B', pair.b.text]].forEach(([label, text]) => {
    const d = document.createElement('div');
    d.className = 'pref-option';
    const b = document.createElement('b');
    b.textContent = label;
    d.appendChild(b);
    d.appendChild(document.createTextNode(text || ''));
    box.appendChild(d);
  });
  card.hidden = false;
}

async function maybeAskPreference(force) {
  if (state.prefPair || state.prefLoading) return;
  if (state.finish) return;
  if (!$('#finishModal').hidden || !$('#endAskModal').hidden) return;
  if (!force) {
    const pc = state.companionConfig.preference || {};
    if (state.turnsSincePref < (pc.every_turns || 4) || state.prefCount >= (pc.max_per_batch || 3)) return;
  }
  if (rec) return;
  if ($('#chatInput').value.trim()) return;
  const lastUser = [...state.history].reverse().find(m => m.role === 'user');
  const lastAgent = [...state.history].reverse().find(m => m.role === 'assistant');
  if (!lastUser || !lastAgent) {
    if (force) status('先和学伴聊一轮，再生成对比版本。', 'err');
    return;
  }
  if (state.history.lastIndexOf(lastUser) > state.history.lastIndexOf(lastAgent)) {
    if (force) status('这一轮学伴还没回，先聊完再对比。', 'err');
    return;
  }
  if (force) status('正在生成两个版本…');
  const hist = state.history.slice(0, -1).map(m => ({ role: m.role, content: m.content || '', session_id: m.session_id, batchStart: m.batchStart }));
  state.prefLoading = true;
  try {
    const pair = await api('/api/preference/pair', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: lastUser.content,
        actual: lastAgent.content,
        history: hist,
        context: contextText(),
        paper: state.paper,
        index: Number($('#problem').value || 0),
        mode: tutorMode(),
        subjectId: state.subjectId,
        problemType: state.problemType,
        model: $('#modelSelect').value,
      })
    });
    if (!pair.ok) {
      state.turnsSincePref = 0;
      if (force) status('这一轮两个版本差别不大，先不生成。', 'err');
      return;
    }
    state.prefPair = pair;
    if (!force) {
      state.turnsSincePref = 0;
      state.prefCount += 1;
    }
    renderPrefCard(pair, lastUser.content);
    if (force) status('看看这两个版本，你更喜欢哪个？', 'ok');
  } catch (e) {
    /* 偏好卡片失败不影响讲题 */
    if (force) status('生成对比失败：' + e.message, 'err');
  } finally {
    state.prefLoading = false;
  }
}

async function votePreference(choice) {
  const pair = state.prefPair;
  if (!pair) return;
  hidePrefCard();
  try {
    await api('/api/preference/vote', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper: state.paper,
        index: Number($('#problem').value || 0),
        sessionId: state.sessionId,
        axis: pair.axis,
        optionA: pair.a.text,
        optionB: pair.b.text,
        aSource: pair.a.source,
        bSource: pair.b.source,
        choice,
      })
    });
    status('已记录这次的偏好。', 'ok');
  } catch (e) {
    status('偏好记录失败：' + e.message, 'err');
  }
}

function formatFinishSummary(text) {
  let s = String(text || '').trim();
  if (!s) return '';
  const start = s.indexOf('{');
  if (start < 0) return s;
  const head = s.slice(0, start).trim();
  if (head && !/^(思路|总结)?[:：]?$/.test(head)) return s;
  const body = s.slice(start);
  if (!/"outline"\s*:/.test(body)) return s;
  const parts = obj => {
    const out = [];
    if (obj.outline) out.push('思路：' + obj.outline);
    if (obj.stuck) out.push('卡点：' + obj.stuck);
    if (obj.pitfalls) out.push('易错：' + obj.pitfalls);
    return out.join('\n');
  };
  try {
    const fixed = body.replace(/(?<!\\)\\(?![\\"/bfnrtu])/g, '\\\\');
    const obj = JSON.parse(fixed);
    const out = parts(obj);
    if (out) return out;
  } catch (e) { /* 退回原文 */ }
  return s;
}

function renderFinishCards(summary, data) {
  const box = $('#reply');
  const old = box.querySelectorAll('.finish-card');
  old.forEach(x => x.remove());
  const sum = document.createElement('div');
  sum.className = 'finish-card';
  sum.innerHTML = '<div class="card-title">学伴总结</div>' +
    '<div class="card-body">' + mathHtml(formatFinishSummary(summary) || '（没有生成总结）') + '</div>';
  box.appendChild(sum);
  const rate = document.createElement('div');
  rate.className = 'finish-card rating-card';
  const labels = { again: '重来', hard: '困难', good: '良好', easy: '简单' };
  const suggested = (data && data.suggested) || 'good';
  const reason = (data && data.reason) || '';
  rate.innerHTML = '<div class="card-title">这次掌握得怎么样？</div>' +
    '<div class="suggest">建议：' + esc(labels[suggested] || suggested) +
    (reason ? ' · ' + esc(reason) : '') + '</div>' +
    '<div class="chat-rating-row"></div>';
  const row = rate.querySelector('.chat-rating-row');
  ['again', 'hard', 'good', 'easy'].forEach(key => {
    const b = document.createElement('button');
    b.className = 'rating-btn' + (suggested === key ? ' suggested' : '');
    b.type = 'button';
    b.dataset.rating = key;
    b.innerHTML = labels[key] + '<small>' + ({ again: '没掌握', hard: '勉强', good: '独立', easy: '很熟' }[key]) + '</small>';
    b.onclick = () => rateReview(key);
    row.appendChild(b);
  });
  box.appendChild(rate);
  rate.scrollIntoView({ block: 'end', behavior: 'smooth' });
}

async function finishProblem(confirmed = false) {
  if (!state.history.some(m => m.role === 'assistant')) {
    status('先和讲伴讲一段，再结束本题。', 'err');
    return;
  }
  const p = state.problems[Number($('#problem').value || 0)];
  if (!p) { status('没有选中题目。', 'err'); return; }
  const btn = $('#dockFinish');
  btn.disabled = true;
  status('正在生成总结…');
  try {
    const start = await api('/api/finish/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper: state.paper, index: Number($('#problem').value || 0),
        history: state.history, model: $('#modelSelect').value
      })
    });
    const summary = start.summary || '（没有生成总结，可以直接写一句。）';
    const complete = await api('/api/finish/complete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: start.id, summary })
    });
    state.finish = complete;
    state.finishId = null;
    renderFinishCards(summary, complete || start);
    status('总结好了。选评级后自动下一题。', 'ok');
  } catch (e) {
    status('收尾失败：' + e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

function splitSentences(text) {
  const s = String(text || '').replace(/\s+/g, ' ').trim();
  if (!s) return [];
  return s.split(/(?<=[。！？!?；;])/).map(x => x.trim()).filter(Boolean);
}

async function ttsUrl(text, opts = {}) {
  const t = await api('/api/tts', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, provider: opts.provider, voice: opts.voice })
  });
  return t.url;
}

async function playUrl(url, token, onStart) {
  const a = $('#audio');
  if (token !== state.speechToken) return false;
  a.src = url;
  $('#audioRow').hidden = false;
  if (a.readyState < 2) {
    await new Promise(resolve => {
      const done = () => resolve();
      a.addEventListener('canplay', done, { once: true });
      a.addEventListener('error', done, { once: true });
      setTimeout(done, 3000);
    });
  }
  if (token !== state.speechToken) return false;
  a.currentTime = 0;
  await a.play();
  if (onStart) onStart();
  await new Promise(resolve => {
    const done = () => { a.removeEventListener('ended', done); resolve(); };
    a.addEventListener('ended', done, { once: true });
  });
  return token === state.speechToken;
}

async function speakSentences(text, token) {
  const parts = splitSentences(text);
  if (!parts.length) return;
  let next = ttsUrl(parts[0], { provider: 'cloud', voice: 'Serena' });
  for (let i = 0; i < parts.length; i++) {
    const url = await next;
    if (token !== state.speechToken) return;
    state.spokenUrls.push(url);
    next = i + 1 < parts.length ? ttsUrl(parts[i + 1], { provider: 'cloud', voice: 'Serena' }) : null;
    const ok = await playUrl(url, token);
    if (!ok) return;
    status('正在朗读… (' + (i + 1) + '/' + parts.length + ')', 'ok');
  }
}

async function playReply() {
  if (!state.spokenUrls.length && state.lastSpeech) {
    const token = ++state.speechToken;
    status('正在合成朗读…');
    try {
      await speakSentences(state.lastSpeech, token);
      if (token === state.speechToken) status('可以继续说话。', 'ok');
    } catch (e) {
      if (token === state.speechToken) status('朗读失败：' + e.message, 'err');
    }
    return;
  }
  if (state.spokenUrls.length) {
    const token = ++state.speechToken;
    for (const url of state.spokenUrls) {
      const ok = await playUrl(url, token);
      if (!ok) return;
    }
    status('可以继续说话。', 'ok');
    return;
  }
  const a = $('#audio');
  if (!a.getAttribute('src')) { status('还没有可播放的回复。', 'err'); return; }
  try {
    if (a.readyState < 2) {
      await new Promise(resolve => {
        const done = () => resolve();
        a.addEventListener('canplay', done, { once: true });
        a.addEventListener('error', done, { once: true });
        setTimeout(done, 3000);
      });
    }
    a.currentTime = 0;
    await a.play();
    await new Promise(r => setTimeout(r, 150));
    if (a.paused) throw new Error('播放没有真正开始');
    status('正在朗读…', 'ok');
  } catch (e) {
    status('自动播放被拦截：点「🔊 重听」，或检查标签页是否静音。', 'err');
  }
}

const MODE_LABELS = { listening: '听讲', gap_check: '查漏', gap_fill: '补缺', guide: '引导', summary: '总结', companion: '学伴' };

function setMode(mode, router) {
  const el = $('#modeBadge');
  if (!el) return;
  el.textContent = '模式：' + (MODE_LABELS[mode] || mode || '听讲');
  el.title = router && router.reason ? ('调度：' + router.reason) : '';
}

function autoGrowInput() {
  const el = $('#chatInput');
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(104, Math.max(44, el.scrollHeight)) + 'px';
}

function segmentDisplay(rawText) {
  // 输入框原话 → 这一步整理出的 LaTeX；对不上（被改过/还没整理）就不强行替换
  const segs = state.segments || [];
  if (!segs.length) return '';
  const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
  const joinedRaw = norm(segs.map(s => s.raw || '').filter(Boolean).join(' '));
  if (!joinedRaw || joinedRaw !== norm(rawText)) return '';
  const out = segs.map(s => String(s.normalized || s.raw || '').trim()).filter(Boolean).join('\n').trim();
  if (!out || norm(out) === norm(rawText)) return '';
  return out;
}

async function send() {
  const inputText = ($('#chatInput').value || '').trim();
  const text = inputText;
  const display = segmentDisplay(text);
  if (!text) { status('先说话或输入一句。', 'err'); return; }
  if (state.selectMode) toggleSelectMode(false);
  hidePrefCard();
  state.turnsSincePref += 1;
  if ($('#transcript').value.trim() !== inputText) $('#transcript').value = inputText;
  const hadSession = !!state.sessionId;
  if (!state.sessionId) await openSession(tutorMode(), { keepDraft: true, keepHistory: true });
  if (!state.sessionId) {
    status('会话创建失败，先别发送；检查网络后重试。', 'err');
    return;
  }
  let batchStart = false;
  let batchText = '';
  if (!hadSession) {
    state.batchCount = (state.batchCount || 0) + 1;
    batchStart = true;
    batchText = batchLabel(state.batchCount, Math.floor(Date.now() / 1000), true);
    state.batches.push({ id: 'live-' + state.batchCount, label: batchText });
  }
  const prior = state.history.slice();
  const p = state.problems[Number($('#problem').value || 0)];
  const context = p ? [p.text || ''].concat((p.options || []).map(o => (o.label || '') + '. ' + (o.text || ''))).join('\n') : '';
  const shown = text;
  state.history.push({ role: 'user', content: shown, raw: text, display: display || '', created_at: Math.floor(Date.now() / 1000),
    session_id: state.sessionId, batchStart, batchLabel: batchText });
  renderHistory();
  $('#send').disabled = true;
  status('agent 思考中…');
  try {
    const model = $('#modelSelect').value;
    const data = await api('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: shown, display, history: prior, context, model, mode: tutorMode(), sessionId: state.sessionId, subjectId: state.subjectId, problemType: state.problemType, paper: state.paper, index: Number($('#problem').value || 0) })
    });
    const reply = data.text || '';
    const speech = data.speech || reply;
    setMode(data.mode || 'listening', data.router);
    if (data.silent || !reply) {
      status('我在听，你继续。', 'ok');
      $('#transcript').value = '';
      $('#chatInput').value = '';
    state.inputDirty = false;
      autoGrowInput();
      state.segments = [];
      renderSegments();
      setComposer(false);
      return;
    }
    state.history.push({ role: 'assistant', content: reply, created_at: Math.floor(Date.now() / 1000),
      session_id: state.sessionId });
    renderHistory();
    state.speechToken++;
    state.spokenUrls = [];
    state.lastSpeech = speech;
    const token = state.speechToken;
    if (state.autoSpeak) {
      status('朗读中…');
      speakSentences(speech, token).catch(e => {
        if (token === state.speechToken) status('文字回复好了，但朗读失败：' + e.message, 'err');
      });
    } else {
      status('回复好了（自动朗读已关，需要时点「重听」）。', 'ok');
    }
    $('#transcript').value = '';
    $('#chatInput').value = '';
    state.inputDirty = false;
    autoGrowInput();
    state.segments = [];
    renderSegments();
    $('#normalized').closest('.formula').classList.remove('stale');
    setComposer(false);
    const stamp = state.history.length;
    setTimeout(() => {
      if (state.history.length === stamp) maybeAskPreference();
    }, 1800);
  } catch (e) {
    const dock = $('#formulaDock');
    if (dock) {
      dock.classList.remove('is-sending');
      dock.hidden = !state.segments.length;
    }
    const last = state.history[state.history.length - 1];
    if (last && last.role === 'user' && last.content === shown) {
      state.history.pop();
      renderHistory();
    }
    status('对话失败：' + e.message, 'err');
  } finally {
    $('#send').disabled = false;
  }
}

$('#mic').addEventListener('click', () => { rec ? stopRecording(false) : startRecording('main'); });
$('#finishMic').addEventListener('click', () => { rec ? stopRecording(false) : startRecording('finish'); });
$('#finishSubmit').addEventListener('click', submitFinishSummary);
$('#prevBtn').addEventListener('click', previousProblem);
$('#nextBtn').addEventListener('click', nextProblem);
$('#dockFinish').addEventListener('click', () => finishProblem(false));
$('#endAskNo').addEventListener('click', () => {
  $('#endAskModal').hidden = true;
  finishProblem(true);
});
$('#endAskYes').addEventListener('click', () => {
  $('#endAskModal').hidden = true;
  state.doubtAsked = true;
  const input = $('#chatInput');
  if (input) input.focus();
  status('继续问；问完再点「结束本题」，疑问会写进总结。', 'ok');
});
$('#endAskClose').addEventListener('click', () => { $('#endAskModal').hidden = true; });
$('#endAskModal').addEventListener('click', e => { if (e.target === $('#endAskModal')) $('#endAskModal').hidden = true; });
$('#dueClose').addEventListener('click', () => { $('#dueModal').hidden = true; });
$('#dueModal').addEventListener('click', e => { if (e.target === $('#dueModal')) $('#dueModal').hidden = true; });
$('#usageClose').addEventListener('click', () => { $('#usageModal').hidden = true; });
$('#usageModal').addEventListener('click', e => { if (e.target === $('#usageModal')) $('#usageModal').hidden = true; });
$('#usageBtn').addEventListener('click', () => { $('#usageModal').hidden = false; loadUsage(); });
$('#finishClose').addEventListener('click', () => { $('#finishModal').hidden = true; });
$('#finishModal').addEventListener('click', e => { if (e.target === $('#finishModal')) $('#finishModal').hidden = true; });
$('#bubbleSend').addEventListener('click', send);
$('#bubbleEdit').addEventListener('click', () => setComposer(true));
$('#selectBtn').addEventListener('click', () => toggleSelectMode(!state.selectMode));
$('#selectCancel').addEventListener('click', () => toggleSelectMode(false));
$('#selectAll').addEventListener('click', () => {
  state.selected = new Set(state.history.map((m, i) => i));
  renderHistory();
  updateSelectBar();
});
$('#selectClear').addEventListener('click', () => {
  state.selected = new Set();
  renderHistory();
  updateSelectBar();
});
$('#selectCopy').addEventListener('click', () => exportSelected(true));
$('#selectExport').addEventListener('click', () => exportSelected(false));
$('#selectRollback').addEventListener('click', rollbackSelected);
$('#selectRegen').addEventListener('click', regenerateSelected);
$('#reply').addEventListener('click', e => {
  if (!state.selectMode) return;
  const row = e.target.closest('.msg-row');
  if (!row) return;
  e.preventDefault();
  e.stopPropagation();
  toggleMessageSelection(row);
});
$('#send').addEventListener('click', send);
$('#chatInput').addEventListener('input', () => {
  state.inputDirty = true;
  autoGrowInput();
  if (state.segments.length) {
    const f = $('#normalized').closest('.formula');
    if (f) f.classList.add('stale');
  }
  if ($('#chatInput').value.trim()) hidePrefCard();
});
document.querySelectorAll('#prefCard .pref-actions button').forEach(btn => {
  btn.addEventListener('click', () => votePreference(btn.dataset.choice));
});
$('#tuneBtn').addEventListener('click', () => {
  const panel = $('#tunePanel');
  if (!panel) return;
  panel.hidden = !panel.hidden;
});
$('#tuneClose').addEventListener('click', () => { $('#tunePanel').hidden = true; });
document.querySelectorAll('#tunePanel [data-tag]').forEach(btn => {
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      await api('/api/companion/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paper: state.paper,
          index: Number($('#problem').value || 0),
          sessionId: state.sessionId,
          tags: [btn.dataset.tag],
        })
      });
      btn.classList.add('done');
      status('已记录「' + btn.dataset.tag + '」。', 'ok');
    } catch (e) {
      status('反馈失败：' + e.message, 'err');
    } finally {
      btn.disabled = false;
    }
  });
});
$('#tuneVersions').addEventListener('click', () => {
  $('#tunePanel').hidden = true;
  maybeAskPreference(true);
});
$('#chatInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
$('#problemText').addEventListener('click', e => {
  const img = e.target.closest('img.problem-img, img.opt-img');
  if (!img) return;
  const a = img.closest('a');
  e.preventDefault();
  openImage(img.currentSrc || img.src, a ? a.href : img.src);
});
$('#imageClose').addEventListener('click', () => {
  $('#imageModal').hidden = true;
  resetImageModalView();
});
$('#imageOriginal').addEventListener('click', () => {
  const url = $('#imageOriginal').dataset.href;
  if (!url) return;
  showOriginalPage(url);
});
$('#imageBack').addEventListener('click', resetImageModalView);
$('#imageZoomIn').addEventListener('click', () => {
  imageZoom = Math.min(2.5, imageZoom + 0.25);
  applyImageZoom();
});
$('#imageZoomOut').addEventListener('click', () => {
  imageZoom = Math.max(0.5, imageZoom - 0.25);
  applyImageZoom();
});
$('#imageFit').addEventListener('click', () => {
  imageZoom = 1;
  applyImageZoom();
});
$('#pagePrev').addEventListener('click', () => gotoOriginalPage(((state.originalPage || {}).page || 1) - 1));
$('#pageNext').addEventListener('click', () => gotoOriginalPage(((state.originalPage || {}).page || 1) + 1));
$('#imageModal').addEventListener('click', e => {
  if (e.target === $('#imageModal')) {
    $('#imageModal').hidden = true;
    resetImageModalView();
  }
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (!$('#figureModal').hidden) {
    closeFigureModal();
    return;
  }
  if ($('#imageModal').hidden) return;
  if (!$('#imageOriginalView').hidden) resetImageModalView();
  else {
    $('#imageModal').hidden = true;
    resetImageModalView();
  }
});
$('#figureBtn').addEventListener('click', openFigureModal);
$('#figureClose').addEventListener('click', closeFigureModal);
$('#figureModal').addEventListener('click', e => {
  if (e.target === $('#figureModal')) closeFigureModal();
});
$('#figurePick').addEventListener('click', () => $('#figureFile').click());
$('#figureFile').addEventListener('change', e => {
  const f = e.target.files && e.target.files[0];
  if (f) readFigureFile(f);
});
$('#figureSave').addEventListener('click', saveFigure);
$('#figureOpenPage').addEventListener('click', () => {
  const p = state.problems[Number($('#problem').value || 0)];
  const url = p && (p.page_url || p.image_url);
  if (!url) {
    status('这道题没有保存原页图。', 'err');
    return;
  }
  closeFigureModal();
  openImage(url, url, true);
});
$('#figureDescToggle').addEventListener('click', () => {
  const box = $('#figureDescBox');
  if (!box) return;
  box.hidden = !box.hidden;
  $('#figureDescToggle').textContent = box.hidden ? '查看识别描述' : '收起识别描述';
});
$('#figureSaveDesc').addEventListener('click', saveFigureDesc);
$('#figureRemove').addEventListener('click', removeFigure);
$('#figureThumbWrap').addEventListener('click', openFigureModal);
document.addEventListener('paste', e => {
  if ($('#figureModal').hidden) return;
  const items = (e.clipboardData && e.clipboardData.items) || [];
  for (const item of items) {
    if (item.type && item.type.indexOf('image/') === 0) {
      e.preventDefault();
      readFigureFile(item.getAsFile());
      break;
    }
  }
});
$('#replay').addEventListener('click', playReply);
state.autoSpeak = localStorage.getItem('tutorAutoSpeak') === '1';
$('#speakToggle').checked = state.autoSpeak;
$('#speakToggle').addEventListener('change', e => {
  state.autoSpeak = !!e.target.checked;
  localStorage.setItem('tutorAutoSpeak', state.autoSpeak ? '1' : '0');
  if (!state.autoSpeak) {
    state.speechToken++;
    const a = $('#audio');
    if (a) { a.pause(); a.removeAttribute('src'); }
    $('#audioRow').hidden = true;
    status('已关闭自动朗读，回复只显示文字。', 'ok');
  } else {
    status('已开启自动朗读。', 'ok');
  }
});
$('#audio').addEventListener('ended', () => status('可以继续说话。', 'ok'));
window.addEventListener('resize', () => requestAnimationFrame(renderBatchMarks));
if (window.ResizeObserver && document.querySelector('.chat')) {
  new ResizeObserver(() => requestAnimationFrame(renderBatchMarks)).observe(document.querySelector('.chat'));
}
$('#modelSelect').addEventListener('change', e => {
  localStorage.setItem('tutorModel', e.target.value);
  e.target.title = '讲题：' + e.target.selectedOptions[0].textContent +
    ' · ASR ' + ((state.health && state.health.asrModel) || '') +
    ' · TTS ' + ((state.health && state.health.ttsModel) || '');
  status('下一个问题用 ' + e.target.selectedOptions[0].textContent + '。');
});
$('#clear').addEventListener('click', () => {
  $('#transcript').value = '';
  $('#chatInput').value = '';
  autoGrowInput();
  state.segments = [];
  renderSegments();
  updateBubble();
  $('#normalized').closest('.formula').classList.remove('stale');
  status('已清空，可以重新说。');
});
$('#normalize').addEventListener('click', normalizeAll);
$('#transcript').addEventListener('input', () => {
  state.segments = [];
  renderSegments();
  updateBubble();
  $('#normalized').closest('.formula').classList.add('stale');
});
state.examMode = localStorage.getItem('tutorExamMode') === '1';
$('#examToggle').checked = state.examMode;
$('#examToggle').addEventListener('change', e => {
  state.examMode = !!e.target.checked;
  localStorage.setItem('tutorExamMode', state.examMode ? '1' : '0');
  resetSession();
  status(state.examMode ? '考试模式：只给最小提示。' : '已回到普通讲题。', 'ok');
});
$('#paper').addEventListener('change', async e => {
  setDetour(null);
  try { resetSession(); await loadPaper(e.target.value); syncPosition(); await restoreHistory(); }
  catch (err) { status(err.message, 'err'); }
});
$('#problem').addEventListener('change', async () => {
  setDetour(null);
  resetSession();
  renderProblem();
  syncPosition();
  await restoreHistory();
});
$('#transcript').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(); });

(function initVoiceFab() {
  const fab = $('#voiceFab');
  try {
    const p = JSON.parse(localStorage.getItem('tutorVoicePos') || 'null');
    if (p && p.left) {
      fab.style.left = p.left;
      fab.style.top = p.top;
      fab.style.right = 'auto';
      fab.style.bottom = 'auto';
      clampFab();
    }
  } catch (e) {}
  let drag = null;
  function start(e) {
    if (e.target.closest('button,input,textarea,a,select,label')) return;
    const r = fab.getBoundingClientRect();
    fab.style.left = r.left + 'px';
    fab.style.top = r.top + 'px';
    fab.style.right = 'auto';
    fab.style.bottom = 'auto';
    drag = { dx: e.clientX - r.left, dy: e.clientY - r.top, id: e.pointerId };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) {}
    e.preventDefault();
  }
  function move(e) {
    if (!drag || e.pointerId !== drag.id) return;
    fab.style.left = (e.clientX - drag.dx) + 'px';
    fab.style.top = (e.clientY - drag.dy) + 'px';
    clampFab();
  }
  function end(e) {
    if (!drag || e.pointerId !== drag.id) return;
    drag = null;
    localStorage.setItem('tutorVoicePos', JSON.stringify({ left: fab.style.left, top: fab.style.top }));
  }
  for (const el of [$('#voiceDrag'), $('#voiceBar')]) {
    el.addEventListener('pointerdown', start);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
  }
  window.addEventListener('resize', clampFab);
  document.addEventListener('pointerdown', e => {
    if (fab.classList.contains('expanded') && !fab.contains(e.target)) setComposer(false);
  }, true);
})();

async function openFromQuery() {
  const q = new URLSearchParams(location.search);
  if (q.get('review')) {
    await loadDue();
    const item = state.due.find(x => x.id === q.get('review'));
    if (item) await loadReview(item);
    return;
  }
  let paper = q.get('paper');
  let index = Number(q.get('index') || 0);
  try {
    const nav = performance.getEntriesByType('navigation')[0];
    if (nav && nav.type === 'reload') {
      const saved = JSON.parse(sessionStorage.getItem('tutorLastPosition') || 'null');
      if (saved && saved.paper) {
        paper = saved.paper;
        index = Number(saved.index || 0);
      }
    }
  } catch (e) { /* ignore */ }
  if (paper) {
    await loadPaper(paper, { skipSession: true });
    $('#problem').value = String(index);
    renderProblem();
    resetSession();
    syncPosition();
    await restoreHistory();
  } else {
    await restoreHistory();
  }
}

try {
  const savedDetour = sessionStorage.getItem('tutorDetour');
  if (savedDetour) state.detour = JSON.parse(savedDetour);
} catch (e) { /* ignore */ }

loadConfig();
loadDue();
loadCompanionConfig();
loadPapers().then(openFromQuery).catch(e => status('加载失败：' + e.message, 'err'));

if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
  navigator.mediaDevices.addEventListener('devicechange', refreshMicDevices);
  refreshMicDevices();
}
const micSel = $('#micSelect');
if (micSel) {
  micSel.addEventListener('change', e => {
    micDeviceId = e.target.value || '';
    try { localStorage.setItem('tutorMicId', micDeviceId); } catch (err) { /* ignore */ }
    const label = e.target.selectedOptions[0] ? e.target.selectedOptions[0].textContent : '';
    status(micDeviceId ? ('录音设备已切到：' + label) : '录音设备：系统默认', 'ok');
  });
}
const speakerToggle = $('#speakerToggle');
if (speakerToggle) {
  speakerToggle.checked = speakerMode;
  speakerToggle.addEventListener('change', e => {
    speakerMode = !!e.target.checked;
    try { localStorage.setItem('tutorSpeakerMode', speakerMode ? '1' : '0'); } catch (err) { /* ignore */ }
    status(speakerMode
      ? '外放模式：已关闭回声消除/降噪。录音时请先别播放声音（包括朗读），否则会把外放声也录进去。'
      : '已恢复耳麦模式（回声消除/降噪开启）。', 'ok');
  });
}

function fmtYuan(v) {
  const n = Number(v) || 0;
  return '¥' + (n >= 1 ? n.toFixed(2) : n.toFixed(3));
}

const USAGE_KIND_NAMES = { asr: '语音识别', llm: '对话/整理', vision: '图像识别', tts: '云端朗读', 'tts-local': '本地朗读' };

function renderUsage(d) {
  const body = $('#usageBody');
  if (!body) return;
  const rows = (d.today && d.today.items) || [];
  let h = '<div class="usage-total">今天（' + ((d.today && d.today.date) || '') + '）≈ ' + fmtYuan(d.today && d.today.cost) + '</div>';
  if (!rows.length) {
    h += '<div class="usage-note">今天还没有调用记录。</div>';
  } else {
    h += '<table><thead><tr><th>类型</th><th>模型</th><th class="num">次数</th><th class="num">用量</th><th class="num">花费</th></tr></thead><tbody>';
    rows.forEach(r => {
      let amount;
      if (r.kind === 'asr') amount = Math.round(r.seconds || 0) + ' 秒';
      else if (r.kind === 'tts' || r.kind === 'tts-local') amount = (r.chars || 0) + ' 字';
      else amount = (r.tokensIn || 0) + ' 入 / ' + (r.tokensOut || 0) + ' 出';
      h += '<tr><td>' + (USAGE_KIND_NAMES[r.kind] || r.kind || '') + '</td><td>' + (r.model || '') + '</td>'
        + '<td class="num">' + (r.calls || 0) + '</td><td class="num">' + amount + '</td>'
        + '<td class="num">' + fmtYuan(r.cost) + '</td></tr>';
    });
    h += '</tbody></table>';
  }
  const range = d.range || {};
  const daily = range.daily || [];
  if (daily.length) {
    h += '<div class="usage-total" style="margin-top:14px">近 ' + (d.days || 7) + ' 天 ≈ ' + fmtYuan(range.cost)
      + '（' + (range.calls || 0) + ' 次调用）</div><div class="usage-days">';
    daily.slice(-7).forEach(x => { h += '<span>' + x.date + '：' + fmtYuan(x.cost) + '</span>'; });
    h += '</div>';
  }
  h += '<div class="usage-note">' + (d.note || '') + '</div>';
  body.innerHTML = h;
}

async function loadUsage() {
  try {
    const d = await api('/api/usage/summary?days=7');
    const btn = $('#usageBtn');
    if (btn) btn.textContent = '≈' + fmtYuan(d.today ? d.today.cost : 0);
    renderUsage(d);
  } catch (e) {
    const body = $('#usageBody');
    if (body) body.textContent = '读取失败：' + e.message;
  }
}

loadUsage();
