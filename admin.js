// =================== thumbnails: hide broken ===================
document.querySelectorAll('img.thumb').forEach(img => {
  img.addEventListener('error', () => {
    img.classList.add('thumb-broken');
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
  bulkStatus.textContent = 'checking & adding...';
  bulkResults.innerHTML = '';

  try {
    const fd = new FormData();
    fd.append('urls', text);
    fd.append('as_ip', asIpCb.checked ? '1' : '0');
    fd.append('template', ipTplInput.value || '');
    const r = await fetch('/admin/bulk_add', { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || ('HTTP ' + r.status));
    }
    const data = await r.json();
    let msg = `added: ${data.added}`;
    if (data.skipped) msg += ` · skipped (duplicates): ${data.skipped}`;
    bulkStatus.textContent = msg;
    for (const item of data.results) {
      const div = document.createElement('div');
      div.className = 'res ' + (item.ok ? 'ok' : 'err');
      div.textContent = `${item.ok ? '✓' : '✗'} [${item.id}] ${item.name} — ${item.url}`;
      bulkResults.appendChild(div);
    }
    setTimeout(() => location.reload(), 1500);
  } catch (e) {
    bulkStatus.textContent = 'error: ' + e.message;
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
      alert('error: ' + e.message);
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
      btn.textContent = next ? 'on' : 'off';
      btn.closest('tr').classList.toggle('inactive', !next);
      const fc = btn.parentElement.querySelector('.fc');
      if (fc) fc.textContent = '0';
    } catch (e) {
      alert('error: ' + e.message);
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
        at.textContent = data.ok ? 'on' : 'off';
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
      actionStatus.textContent = `removed: ${data.deleted}`;
    } else if (typeof data.checked === 'number') {
      actionStatus.textContent = `checked ${data.checked} · ok ${data.ok} · fail ${data.fail}`;
    } else {
      actionStatus.textContent = 'done';
    }
    setTimeout(() => location.reload(), 800);
  } catch (e) {
    actionStatus.textContent = 'error: ' + e.message;
    btn.disabled = false;
  }
}

document.getElementById('check-all').addEventListener('click', e => runAction(e.currentTarget, '/admin/probe_all', 'checking'));
document.getElementById('dedupe').addEventListener('click', e => runAction(e.currentTarget, '/admin/dedupe', 'deduping'));
document.getElementById('renumber').addEventListener('click', e => runAction(e.currentTarget, '/admin/renumber', 'renumbering'));

// =================== settings form ===================
const settingsForm = document.getElementById('settings-form');
const settingsStatus = document.getElementById('settings-status');
settingsForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(settingsForm);
  settingsStatus.textContent = 'saving...';
  try {
    const r = await fetch('/admin/settings', { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || ('HTTP ' + r.status));
    }
    settingsStatus.textContent = 'saved';
    setTimeout(() => settingsStatus.textContent = '', 2000);
  } catch (err) {
    settingsStatus.textContent = 'error: ' + err.message;
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
  bulkDelConfirm.textContent = `confirm delete (${getSelectedIds().length})`;
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
    alert('error: ' + e.message);
    bulkDelConfirm.disabled = false;
  }
});

// =================== drag & drop sort ===================
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
  });

  tr.addEventListener('dragend', () => {
    tr.classList.remove('dragging');
    tbody.querySelectorAll('tr').forEach(r => r.classList.remove('drop-target'));
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

async function saveOrder() {
  const order = [...tbody.querySelectorAll('tr')].map(r => parseInt(r.dataset.id, 10));
  try {
    const r = await fetch('/admin/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  } catch (e) {
    console.error('reorder failed', e);
  }
}
