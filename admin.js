// ---------- bulk add ----------
const bulkBtn = document.getElementById('bulk-add');
const bulkArea = document.getElementById('bulk-urls');
const bulkStatus = document.getElementById('bulk-status');
const bulkResults = document.getElementById('bulk-results');

bulkBtn.addEventListener('click', async () => {
  const text = bulkArea.value.trim();
  if (!text) return;
  bulkBtn.disabled = true;
  bulkStatus.textContent = 'Проверяю и добавляю...';
  bulkResults.innerHTML = '';

  try {
    const fd = new FormData();
    fd.append('urls', text);
    const r = await fetch('/admin/bulk_add', { method: 'POST', body: fd });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    bulkStatus.textContent = `Добавлено: ${data.added}`;
    for (const item of data.results) {
      const div = document.createElement('div');
      div.className = 'res ' + (item.ok ? 'ok' : 'err');
      div.textContent = `${item.ok ? '✓' : '✗'} [${item.id}] ${item.name} — ${item.url}`;
      bulkResults.appendChild(div);
    }
    setTimeout(() => location.reload(), 1500);
  } catch (e) {
    bulkStatus.textContent = 'Ошибка: ' + e.message;
  } finally {
    bulkBtn.disabled = false;
  }
});

// ---------- recording toggle ----------
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

// ---------- active toggle ----------
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
      btn.textContent = next ? '✓' : '✗';
      btn.closest('tr').classList.toggle('inactive', !next);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  });
});

// ---------- probe ----------
document.querySelectorAll('.probe').forEach(btn => {
  btn.addEventListener('click', async () => {
    const id = btn.dataset.id;
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = '...';
    try {
      const r = await fetch(`/admin/probe/${id}`, { method: 'POST' });
      const data = await r.json();
      btn.textContent = data.ok ? '✓ OK' : '✗ FAIL';
      const tr = btn.closest('tr');
      tr.classList.toggle('inactive', !data.ok);
      const at = tr.querySelector('.toggle-active');
      if (at) {
        at.dataset.active = data.ok ? '1' : '0';
        at.textContent = data.ok ? '✓' : '✗';
      }
      setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1500);
    } catch (e) {
      btn.textContent = 'ERR';
      btn.disabled = false;
    }
  });
});

// ---------- drag & drop sort ----------
const tbody = document.getElementById('cams-tbody');
let dragRow = null;

tbody.querySelectorAll('tr').forEach(tr => {
  tr.setAttribute('draggable', 'true');

  tr.addEventListener('dragstart', (e) => {
    dragRow = tr;
    tr.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  });

  tr.addEventListener('dragend', () => {
    tr.classList.remove('dragging');
    tbody.querySelectorAll('tr').forEach(r => r.classList.remove('drop-target'));
    dragRow = null;
    saveOrder();
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
    await fetch('/admin/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order }),
    });
  } catch (e) {
    console.error('reorder failed', e);
  }
}
