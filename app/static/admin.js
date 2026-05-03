const ACTIVE_TAB_ID = parseInt(
  document.getElementById('tabs').dataset.active, 10
);

// =================== thumbnails ===================
document.querySelectorAll('img.thumb').forEach(img => {
  img.addEventListener('error', () => img.classList.add('thumb-broken'));
});

// =================== tabs management ===================
const addTabBtn = document.getElementById('add-tab');
addTabBtn.addEventListener('click', async () => {
  const name = prompt('Название новой вкладки:');
  if (!name || !name.trim()) return;
  const fd = new FormData();
  fd.append('name', name.trim());
  try {
    const r = await fetch('/admin/tabs/add', { method: 'POST', body: fd });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    location.reload();
  } catch (e) {
    alert('Ошибка: ' + e.message);
  }
});

document.querySelectorAll('.tab-rename').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const id = btn.dataset.tabId;
    const wrap = btn.closest('.tab-wrap');
    const current = wrap.querySelector('.tab').textContent.trim().replace(/\s*\(\d+\)$/, '');
    const name = prompt('Новое имя вкладки:', current);
    if (!name || !name.trim() || name === current) return;
    const fd = new FormData();
    fd.append('name', name.trim());
    try {
      const r = await fetch(`/admin/tabs/rename/${id}`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      location.reload();
    } catch (err) {
      alert('Ошибка: ' + err.message);
    }
  });
});

let tabDeleteConfirmId = null;
document.querySelectorAll('.tab-delete').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const id = btn.dataset.tabId;
    if (tabDeleteConfirmId !== id) {
      tabDeleteConfirmId = id;
      btn.classList.add('confirm');
      btn.textContent = '✓';
      btn.title = 'нажми ещё раз для удаления';
      setTimeout(() => {
        if (tabDeleteConfirmId === id) {
          tabDeleteConfirmId = null;
          btn.classList.remove('confirm');
          btn.textContent = '×';
          btn.title = 'удалить вкладку';
        }
      }, 4000);
      return;
    }
    tabDeleteConfirmId = null;
    try {
      const r = await fetch(`/admin/tabs/delete/${id}`, { method: 'POST' });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || ('HTTP ' + r.status));
      }
      location.href = '/admin';
    } catch (err) {
      alert('Ошибка: ' + err.message);
      btn.classList.remove('confirm');
      btn.textContent = '×';
    }
  });
});

// =================== bulk add ===================
const bulkBtn = document.getElementById('bulk-add');
const bulkArea = document.getElementById('bulk-urls');
const bulkStatus = document.getElementById('bulk-status');
const bulkResults = document.getElementById('bulk-results');
const asIpCb = document.getElementById('bulk-as-ip');
const ipTplRow = document.getElementById('ip-template-row');
const ipTplInput = document.getElementById('ip-template');

asIpCb.addEventListener('change', () => {
  ipTplRow.style.display = asIpCb.checked ? '' : 'none';
});

bulkBtn.addEventListener('click', async () => {
  const text = bulkArea.value.trim();
  if (!text) return;
  bulkBtn.disabled = true;
  bulkStatus.textContent = 'проверяю и добавляю...';
  bulkResults.innerHTML = '';

  try {
    const fd = new FormData();
    fd.append('urls', text);
    fd.append('as_ip', asIpCb.checked ? '1' : '0');
    fd.append('template', ipTplInput.value || '');
    fd.append('tab_id', String(ACTIVE_TAB_ID));
    const r = await fetch('/admin/bulk_add', { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || err.detail || ('HTTP ' + r.status));
    }
    const data = await r.json();
    let msg = `добавлено: ${data.added}`;
    if (data.skipped) msg += ` · пропущено (дубликаты): ${data.skipped}`;
    bulkStatus.textContent = msg;
    for (const item of data.results) {
      const div = document.createElement('div');
      div.className = 'res ' + (item.ok ? 'ok' : 'err');
      div.textContent = `${item.ok ? '✓' : '✗'} [${item.id}] ${item.name} — ${item.url}`;
      bulkResults.appendChild(div);
    }
    setTimeout(() => location.reload(), 1500);
  } catch (e) {
    bulkStatus.textContent = 'ошибка: ' + e.message;
  } finally {
    bulkBtn.disabled = false;
  }
});

// =================== recording toggle ===================
document.querySelectorAll('.rec-toggle').forEach(cb => {
  cb.addEventListener('change', async () => {
    const id = cb.dataset.id;
    const fd = new FormData();
    fd.append('recording', cb.checked ? '1' : '0');
    try {
      const r = await fetch(`/admin/recording/${id}`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('HTTP ' + r.status);
    } catch (e) {
      alert('Ошибка: ' + e.message);
      cb.checked = !cb.checked;
    }
  });
});

// =================== active toggle ===================
document.querySelectorAll('.toggle-active').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const id = btn.dataset.id;
    const cur = btn.dataset.active === '1';
    const next = cur ? 0 : 1;
    const fd = new FormData();
    fd.append('active', String(next));
    try {
      const r = await fetch(`/admin/active/${id}`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      btn.dataset.active = String(next);
      btn.textContent = next ? 'вкл' : 'выкл';
      btn.closest('tr').classList.toggle('inactive', !next);
      const fc = btn.parentElement.querySelector('.fc');
      if (fc) fc.textContent = '0';
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  });
});

// =================== probe single ===================
document.querySelectorAll('.probe').forEach(btn => {
  btn.addEventListener('click', async () => {
    const id = btn.dataset.id;
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = '...';
    try {
      const r = await fetch(`/admin/probe/${id}`, { method: 'POST' });
      const data = await r.json();
      btn.textContent = data.ok ? 'ok' : 'fail';
      const tr = btn.closest('tr');
      tr.classList.toggle('inactive', !data.ok);
      const at = tr.querySelector('.toggle-active');
      if (at) {
        at.dataset.active = data.ok ? '1' : '0';
        at.textContent = data.ok ? 'вкл' : 'выкл';
      }
      const fc = tr.querySelector('.fc');
      if (fc && data.ok) fc.textContent = '0';
      setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1500);
    } catch (e) {
      btn.textContent = 'err';
      btn.disabled = false;
    }
  });
});

// =================== probe all / dedupe / renumber ===================
const actionStatus = document.getElementById('action-status');

async function runAction(btn, url, label) {
  btn.disabled = true;
  actionStatus.textContent = label + '...';
  try {
    const r = await fetch(url, { method: 'POST' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    if (typeof data.deleted === 'number') {
      actionStatus.textContent = `удалено: ${data.deleted}`;
    } else if (typeof data.checked === 'number') {
      actionStatus.textContent = `проверено ${data.checked} · ok ${data.ok} · fail ${data.fail}`;
    } else {
      actionStatus.textContent = 'готово';
    }
    setTimeout(() => location.reload(), 800);
  } catch (e) {
    actionStatus.textContent = 'ошибка: ' + e.message;
    btn.disabled = false;
  }
}

document.getElementById('check-all').addEventListener('click', e => runAction(e.currentTarget, '/admin/probe_all', 'проверяю'));
document.getElementById('dedupe').addEventListener('click', e => runAction(e.currentTarget, '/admin/dedupe', 'удаляю дубли'));
document.getElementById('renumber').addEventListener('click', e => runAction(e.currentTarget, '/admin/renumber', 'перенумеровываю'));

// =================== settings ===================
const settingsForm = document.getElementById('settings-form');
const settingsStatus = document.getElementById('settings-status');
settingsForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(settingsForm);
  settingsStatus.textContent = 'сохраняю...';
  try {
    const r = await fetch('/admin/settings', { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || ('HTTP ' + r.status));
    }
    settingsStatus.textContent = 'сохранено';
    setTimeout(() => settingsStatus.textContent = '', 2000);
  } catch (err) {
    settingsStatus.textContent = 'ошибка: ' + err.message;
  }
});

// =================== bulk select & delete ===================
const tbody = document.getElementById('cams-tbody');
const selAll = document.getElementById('sel-all');
const bulkBar = document.getElementById('bulk-bar');
const selCount = document.getElementById('sel-count');
const bulkDelBtn = document.getElementById('bulk-delete');
const bulkDelConfirm = document.getElementById('bulk-delete-confirm');
const bulkDelCancel = document.getElementById('bulk-delete-cancel');

function getSelectedIds() {
  return [...tbody.querySelectorAll('.sel:checked')]
    .map(cb => parseInt(cb.dataset.id, 10));
}

let confirmTimer = null;
function resetConfirm() {
  bulkDelBtn.style.display = '';
  bulkDelConfirm.style.display = 'none';
  bulkDelCancel.style.display = 'none';
  if (confirmTimer) { clearTimeout(confirmTimer); confirmTimer = null; }
}

function refreshSelection() {
  const ids = getSelectedIds();
  selCount.textContent = ids.length;
  bulkBar.style.display = ids.length ? 'flex' : 'none';
  if (!ids.length) resetConfirm();
  const all = tbody.querySelectorAll('.sel');
  selAll.checked = all.length > 0 && ids.length === all.length;
  selAll.indeterminate = ids.length > 0 && ids.length < all.length;
}

tbody.addEventListener('change', (e) => {
  if (e.target.classList.contains('sel')) refreshSelection();
});

selAll.addEventListener('change', () => {
  tbody.querySelectorAll('.sel').forEach(cb => { cb.checked = selAll.checked; });
  refreshSelection();
});

bulkDelBtn.addEventListener('click', () => {
  if (!getSelectedIds().length) return;
  bulkDelBtn.style.display = 'none';
  bulkDelConfirm.style.display = '';
  bulkDelCancel.style.display = '';
  bulkDelConfirm.textContent = `Подтвердить удаление (${getSelectedIds().length})`;
  confirmTimer = setTimeout(resetConfirm, 5000);
});

bulkDelCancel.addEventListener('click', resetConfirm);

bulkDelConfirm.addEventListener('click', async () => {
  const ids = getSelectedIds();
  if (!ids.length) { resetConfirm(); return; }
  bulkDelConfirm.disabled = true;
  try {
    const r = await fetch('/admin/bulk_delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    location.reload();
  } catch (e) {
    alert('Ошибка: ' + e.message);
    bulkDelConfirm.disabled = false;
  }
});

// =================== drag & drop sort + camera→tab move ===================
let dragRow = null;

tbody.querySelectorAll('tr').forEach(tr => {
  tr.setAttribute('draggable', 'true');

  tr.addEventListener('mousedown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' ||
        e.target.tagName === 'A' || e.target.tagName === 'IMG') {
      tr.removeAttribute('draggable');
    } else {
      tr.setAttribute('draggable', 'true');
    }
  });

  tr.addEventListener('dragstart', (e) => {
    if (!tr.hasAttribute('draggable')) { e.preventDefault(); return; }
    dragRow = tr;
    tr.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    document.body.classList.add('dragging-row');
  });

  tr.addEventListener('dragend', () => {
    tr.classList.remove('dragging');
    document.body.classList.remove('dragging-row');
    tbody.querySelectorAll('tr').forEach(r => r.classList.remove('drop-target'));
    document.querySelectorAll('#tabs .drop-target').forEach(el => el.classList.remove('drop-target'));
    if (dragRow) saveOrder();
    dragRow = null;
  });

  tr.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (!dragRow || dragRow === tr) return;
    const rect = tr.getBoundingClientRect();
    const after = (e.clientY - rect.top) > rect.height / 2;
    tbody.querySelectorAll('tr').forEach(r => r.classList.remove('drop-target'));
    tr.classList.add('drop-target');
    if (after) tr.after(dragRow);
    else tr.before(dragRow);
  });
});

// camera → tab move
document.querySelectorAll('#tabs .tab-wrap').forEach(wrap => {
  const targetId = parseInt(wrap.dataset.tabId, 10);
  wrap.addEventListener('dragover', (e) => {
    if (!dragRow) return;
    e.preventDefault();
    wrap.classList.add('drop-target');
  });
  wrap.addEventListener('dragleave', () => {
    wrap.classList.remove('drop-target');
  });
  wrap.addEventListener('drop', async (e) => {
    if (!dragRow) return;
    e.preventDefault();
    wrap.classList.remove('drop-target');
    if (targetId === ACTIVE_TAB_ID) { dragRow = null; return; }
    const camId = parseInt(dragRow.dataset.id, 10);
    dragRow = null;
    const fd = new FormData();
    fd.append('tab_id', String(targetId));
    try {
      const r = await fetch(`/admin/cameras/${camId}/move`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      location.reload();
    } catch (err) {
      alert('Ошибка перемещения: ' + err.message);
    }
  });
});

async function saveOrder() {
  const order = [...tbody.querySelectorAll('tr')].map(r => parseInt(r.dataset.id, 10));
  try {
    const r = await fetch('/admin/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tab_id: ACTIVE_TAB_ID, order }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  } catch (e) {
    console.error('reorder failed', e);
  }
}
