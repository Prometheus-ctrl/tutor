const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');

async function api(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}

function talkUrl(paper, index) {
  return '/talk.html?paper=' + encodeURIComponent(paper) + '&index=' + encodeURIComponent(index || 0);
}

function paperRow(p) {
  const due = p.due ? '<span class="sub-due">到期 ' + p.due + '</span>' : '';
  return '<div class="q-item">' +
    '<div><a href="' + talkUrl(p.id, 0) + '">' + esc(p.title) + '</a>' +
    '<div class="muted">已讲 ' + p.finished + '/' + p.problems + ' · 未讲 ' + p.untouched + '</div></div>' +
    '<div class="row">' + due + '<a href="' + talkUrl(p.id, 0) + '">打开</a></div>' +
    '</div>';
}

function renderTree(goals, expandAll) {
  const open = expandAll ? ' open' : '';
  const box = $('#tree');
  if (!goals.length) {
    box.innerHTML = '<div class="notice">还没有目标/任务/计划。先用「切题校正」上传整卷，或导入旧工作台数据；整卷会先出现在下面的「未归档」。</div>';
    return;
  }
  box.innerHTML = goals.map(g => {
    const tasks = (g.tasks || []).map(t => {
      const plans = (t.plans || []).map(p => {
        const papers = (p.papers || []).map(paperRow).join('') || '<div class="muted">还没有整卷</div>';
        const next = p.next
          ? '<div class="row" style="margin-bottom:8px;"><a class="chip" href="/talk.html?paper=' +
            encodeURIComponent(p.next.paper) + '&index=' + encodeURIComponent(p.next.index) +
            '">下一题：' + esc(p.next.paper_title || '') + ' 第' + esc(p.next.no || '') + '题</a></div>'
          : '';
        const actions = '<div class="row plan-actions">' +
          '<button class="chip plan-detail" data-plan="' + esc(p.id) + '">查看单元</button>' +
          (p.phase === 'archived'
            ? '<span class="chip">已归档</span><button class="chip plan-action" data-plan="' + esc(p.id) + '" data-action="active">取消归档</button>'
            : (p.active
              ? '<span class="chip">当前计划</span>'
              : '<button class="chip plan-action" data-plan="' + esc(p.id) + '" data-action="active">设为当前计划</button>')) +
          (p.phase === 'first_done'
            ? '<button class="chip plan-action" data-plan="' + esc(p.id) + '" data-action="archived">归档</button>'
            : '') +
          '</div>';
        return '<details' + open + '>' +
          '<summary><span>' + (p.active ? '▶ ' : '') + esc(p.name) + '</span>' +
          '<span class="plan-meta">' + (p.phase_label ? esc(p.phase_label) + ' · ' : '') +
          (p.units ? ('余 ' + p.units_left + '/' + p.units) : '空') +
          (p.writing ? ' · 写作 ' + p.writing : '') +
          (p.due ? ' · 到期 ' + p.due : '') + '</span>' +
          '<button class="chip plan-detail" data-plan="' + esc(p.id) + '">单元</button>' +
          '</summary>' +
          '<div class="leaf">' + actions + next + papers + '</div></details>';
      }).join('') || '<div class="muted">还没有计划</div>';
      const activePlan = (t.plans || []).find(x => x.active);
      return '<details' + open + '>' +
        '<summary><span>' + esc(t.title) + '</span>' +
        '<span class="plan-meta">' + (t.plans || []).length + ' 个计划' + (t.due ? ' · 到期 ' + t.due : '') + '</span>' +
        (activePlan ? '<button class="chip plan-detail" data-plan="' + esc(activePlan.id) + '">单元</button>' : '') +
        '</summary>' +
        '<div class="leaf">' + plans + '</div></details>';
    }).join('') || '<div class="muted">还没有任务</div>';
    return '<details open>' +
      '<summary><span>目标 · ' + esc(g.title) + '</span>' +
      '<span class="plan-meta">' + (g.due ? '到期 ' + g.due : '') + '</span></summary>' +
      '<div class="leaf">' + tasks + '</div></details>';
  }).join('');
  box.querySelectorAll('.plan-action').forEach(btn => {
    btn.addEventListener('click', async () => {
      const planId = btn.dataset.plan;
      const action = btn.dataset.action;
      btn.disabled = true;
      try {
        if (action === 'active') {
          await api('/api/app/plan/active', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ planId })
          });
        } else {
          await api('/api/app/plan/status', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ planId, status: action })
          });
        }
        await main();
      } catch (e) {
        btn.disabled = false;
        alert('操作失败：' + e.message);
      }
    });
  });
  box.querySelectorAll('.plan-detail').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      openPlanDetail(btn.dataset.plan);
    });
  });
}

function flattenPlans(goals) {
  const out = [];
  (goals || []).forEach(g => (g.tasks || []).forEach(t => (t.plans || []).forEach(p => {
    out.push({ id: p.id, subject_id: p.subject_id, label: g.title + ' / ' + t.title + ' / ' + p.name });
  })));
  return out;
}

function renderUnassigned(papers, plans) {
  const box = $('#unassigned');
  if (!papers.length) {
    box.innerHTML = '<div class="empty">没有未归档整卷。</div>';
    return;
  }
  if (!plans.length) {
    box.innerHTML = '<div class="notice">还没有可归属的计划。先在计划树里新建任务/计划。</div>';
    return;
  }
  box.innerHTML = papers.map(p => {
    const opts = plans.filter(x => !x.subject_id || x.subject_id === p.subject_id)
      .map(x => '<option value="' + esc(x.id) + '">' + esc(x.label) + '</option>').join('');
    return '<div class="item">' +
      '<div class="row" style="justify-content:space-between;">' +
      '<div><div class="item-title"><a href="' + talkUrl(p.id, 0) + '">' + esc(p.title) + '</a></div>' +
      '<div class="item-meta">' + p.problems + ' 题 · 已讲 ' + p.finished + ' · 未讲 ' + p.untouched +
      (p.due ? ' · 到期 ' + p.due : '') + '</div></div>' +
      '<div class="row"><select class="assign-select" data-paper="' + esc(p.id) + '" style="max-width:260px;padding:7px;border:1px solid var(--line);border-radius:8px;">' +
      opts + '</select><button class="chip assign-btn" data-paper="' + esc(p.id) + '">归到计划</button></div>' +
      '</div></div>';
  }).join('');
  box.querySelectorAll('.assign-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const paperId = btn.dataset.paper;
      const sel = box.querySelector('.assign-select[data-paper="' + CSS.escape(paperId) + '"]');
      if (!sel || !sel.value) return;
      btn.disabled = true;
      btn.textContent = '归入中…';
      try {
        await api('/api/app/paper/assign', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ paperId, planId: sel.value })
        });
        await main();
      } catch (e) {
        alert('归入失败：' + e.message);
        btn.disabled = false;
        btn.textContent = '归到计划';
      }
    });
  });
}

function renderHeadline(data, subjectId) {
  let subjects = data.subjects || [];
  if (subjectId) subjects = subjects.filter(s => s.id === subjectId);
  const due = subjects.reduce((n, s) => n + (s.due || 0), 0);
  const papers = subjects.reduce((n, s) => n + (s.papers || 0), 0);
  const problems = subjects.reduce((n, s) => n + (s.problems || 0), 0);
  const finished = subjects.reduce((n, s) => n + (s.finished || 0), 0);
  const stats = subjectId
    ? [['整卷', papers], ['题目', problems], ['已讲', finished], ['当前到期', due]]
    : [['科目', subjects.length], ['整卷', papers], ['题目', problems], ['当前到期', due]];
  $('#headline').innerHTML = stats.map(x => '<div class="stat"><b>' + x[1] + '</b><span>' + x[0] + '</span></div>').join('');
}

let currentPlanId = null;

async function openPlanDetail(planId) {
  currentPlanId = planId;
  const modal = $('#planModal');
  const title = $('#planModalTitle');
  const body = $('#planModalBody');
  if (!modal || !title || !body) return;
  const openPapers = new Set([...body.querySelectorAll('.plan-paper[open]')].map(x => x.dataset.paper));
  body.innerHTML = '<div class="muted">加载中…</div>';
  modal.hidden = false;
  try {
    const data = await api('/api/app/plan/' + encodeURIComponent(planId));
    const plan = data.plan || {};
    title.textContent = (plan.name || '计划') + ' · 单元';
    const papers = data.papers || [];
    const problems = data.problems || [];
    const byPaper = new Map();
    problems.forEach(p => {
      if (!byPaper.has(p.paper_id)) byPaper.set(p.paper_id, []);
      byPaper.get(p.paper_id).push(p);
    });
    let html = '<div class="plan-summary">' +
      '<span>' + esc(plan.phase_label || '') + '</span>' +
      '<span>余 ' + esc(plan.units_left || 0) + '/' + esc(plan.units || 0) + '</span>' +
      '<span>题目 ' + esc(problems.length) + '</span>' +
      '</div>';
    if (plan.next) {
      html += '<div class="row" style="margin-bottom:10px;"><a class="chip" href="/talk.html?paper=' +
        encodeURIComponent(plan.next.paper) + '&index=' + encodeURIComponent(plan.next.index) +
        '">下一题：' + esc(plan.next.paper_title || '') + ' 第' + esc(plan.next.no || '') + '题</a></div>';
    }
    html += papers.map(paper => {
      const rows = byPaper.get(paper.id) || [];
      const done = rows.filter(x => x.unit_status === 'finished').length;
      return '<details class="plan-paper" data-paper="' + esc(paper.id) + '"' +
        (openPapers.has(paper.id) ? ' open' : '') + '><summary>' + esc(paper.title || paper.id) +
        '<span>' + done + '/' + rows.length + ' 单元</span></summary>' +
        rows.map(x => {
          const state = x.state === 'due' ? '到期' : (x.unit_status === 'finished' ? '已讲' : '未讲');
          const toggle = x.unit_id
            ? '<button class="unit-toggle" data-unit="' + esc(x.unit_id) +
              '" data-status="' + (x.unit_status === 'finished' ? 'pending' : 'finished') + '">' +
              (x.unit_status === 'finished' ? '恢复未讲' : '标完成') + '</button>'
            : '';
          return '<div class="plan-unit"><span>第' + esc(x.no || '') + '题 · ' + esc(state) + '</span>' +
            '<span class="row">' + toggle +
            '<a href="/talk.html?paper=' + encodeURIComponent(x.paper_id) + '&index=' +
            encodeURIComponent(rows.indexOf(x)) + '">打开</a></span></div>';
        }).join('') +
        '</details>';
    }).join('') || '<div class="muted">这个计划还没有单元。</div>';
    body.innerHTML = html;
  } catch (e) {
    body.innerHTML = '<div class="muted">加载失败：' + esc(e.message) + '</div>';
  }
}

function closePlanDetail() {
  const modal = $('#planModal');
  if (modal) modal.hidden = true;
}

async function main() {
  try {
    const subjectId = new URLSearchParams(location.search).get('subject') || '';
    const [tree, over] = await Promise.all([
      api('/api/app/plans'),
      api('/api/app/overview')
    ]);
    let goals = tree.goals || [];
    let unassigned = tree.unassigned || [];
    if (subjectId) {
      goals = goals.filter(g => g.subject_id === subjectId);
      unassigned = unassigned.filter(p => p.subject_id === subjectId);
      const subject = (over.subjects || []).find(s => s.id === subjectId);
      $('#planTitle').textContent = (subject ? subject.name : '本科目') + ' · 计划';
      $('#planSub').textContent = '只看这一科；点任务/计划展开整卷。';
      $('#allPlansLink').hidden = false;
    } else {
      $('#planTitle').textContent = '材料推进到哪了？';
      $('#planSub').textContent = '目标 → 任务 → 计划 → 整卷。这里只记事实，不判断掌握。';
      $('#allPlansLink').hidden = true;
    }
    renderHeadline(over, subjectId);
    renderTree(goals, !!subjectId);
    renderUnassigned(unassigned, flattenPlans(goals));
  } catch (e) {
    $('#tree').innerHTML = '<div class="notice">加载失败：' + esc(e.message) + '</div>';
    $('#unassigned').innerHTML = '';
  }
}
$('#allPlansLink').addEventListener('click', e => {
  e.preventDefault();
  location.assign('/plan.html');
});
$('#planModalClose').addEventListener('click', closePlanDetail);
$('#planModalBody').addEventListener('click', async e => {
  const btn = e.target.closest('.unit-toggle');
  if (!btn) return;
  btn.disabled = true;
  try {
    await api('/api/app/plan/unit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ unitId: btn.dataset.unit, status: btn.dataset.status })
    });
    if (currentPlanId) await openPlanDetail(currentPlanId);
  } catch (err) {
    btn.disabled = false;
    alert('操作失败：' + err.message);
  }
});
$('#planModal').addEventListener('click', e => {
  if (e.target === $('#planModal')) closePlanDetail();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('#planModal').hidden) closePlanDetail();
});
main();
