const grid = document.getElementById('grid');
const tabsNav = document.getElementById('tabs');
const cameras = JSON.parse(grid.dataset.cameras);
const ACTIVE_TAB_ID = parseInt(grid.dataset.activeTab, 10);
const FPS = parseFloat(grid.dataset.fps) || 5;
const TILE = parseInt(grid.dataset.tileSize, 10) || 320;
const pauseBtn = document.getElementById('pause');
const editBtn = document.getElementById('edit-mode');
const addTabBtn = document.getElementById('add-tab');

const intervalMs = 1000 / FPS;
let paused = false;
let editMode = false;
let authHeader = sessionStorage.getItem('admin_auth') || null;

document.documentElement.style.setProperty('--tile', TILE + 'px');

const tiles = new Map();

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function buildTile(cam) {
  const tile = document.createElement('div');
  tile.className = 'tile';
  tile.dataset.id = cam.id;
  tile.innerHTML = `
    <img alt="">
    <span class="status"></span>
    <span class="label">${escapeHtml(cam.name)}</span>
    <a class="live-link" href="/stream/${cam.id}" target="_blank" rel="noopener">поток</a>
  `;
  const img = tile.querySelector('img');
  grid.appendChild(tile);
  tiles.set(cam.id, { tile, img, visible: false, lastLoad: 0, inflight: false, cam });
}

cameras.forEach(buildTile);

// IntersectionObserver: грузим только видимые ±200px
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const id = parseInt(e.target.dataset.id, 10);
    const t = tiles.get(id);
    if (!t) continue;
    t.visible = e.isIntersecting;
  }
}, { rootMargin: '200px' });

tiles.forEach(({ tile }) => io.observe(tile));

// =================== refresh loop ===================
function tick() {
  if (paused) return;
  const now = performance.now();
  for (const t of tiles.values()) {
    if (!t.visible || t.inflight) continue;
    if (now - t.lastLoad < intervalMs) continue;
    requestSnap(t, now);
  }
}

function requestSnap(t, now) {
  t.inflight = true;
  t.lastLoad = now;
  const url = `/snap/${t.cam.id}?t=${Date.now()}`;
  const next = new Image();
  next.onload = () => {
    t.img.src = next.src;
    t.tile.classList.remove('err');
    t.tile.classList.add('ok');
    t.inflight = false;
  };
  next.onerror = () => {
    t.tile.classList.remove('ok');
    t.tile.classList.add('err');
    t.inflight = false;
  };
  next.src = url;
}

setInterval(tick, 50);

pauseBtn.addEventListener('click', () => {
  paused = !paused;
  pauseBtn.textContent = paused ? 'возобновить' : 'пауза';
  pauseBtn.classList.toggle('active', paused);
});

grid.addEventListener('dblclick', (e) => {
  if (e.target.closest('.live-link')) return;
  if (editMode) return;
  const tile = e.target.closest('.tile');
  if (!tile) return;
  if (document.fullscreenElement) document.exitFullscreen();
  else tile.requestFullscreen();
});

// =================== auth ===================
async function checkAuth(header) {
  const r = await fetch('/admin/whoami', {
    headers: header ? { 'Authorization': header } : {},
  });
  return r.ok;
}

async function ensureAuth() {
  if (authHeader && await checkAuth(authHeader)) return true;
  const login = prompt('Логин админа:', 'admin');
  if (!login) return false;
  const password = prompt('Пароль:');
  if (password == null) return false;
  const header = 'Basic ' + btoa(`${login}:${password}`);
  if (!(await checkAuth(header))) {
    alert('Неверный логин или пароль');
    return false;
  }
  authHeader = header;
  sessionStorage.setItem('admin_auth', header);
  return true;
}

function authedFetch(url, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (authHeader) headers['Authorization'] = authHeader;
  return fetch(url, Object.assign({}, opts, { headers }));
}

// =================== edit mode ===================
editBtn.addEventListener('click', async () => {
  if (editMode) { setEditMode(false); return; }
  if (!(await ensureAuth())) return;
  setEditMode(true);
});

function setEditMode(on) {
  editMode = on;
  document.body.classList.toggle('edit-mode', on);
  editBtn.textContent = on ? 'готово' : 'правка';
  editBtn.classList.toggle('active', on);

  for (const { tile } of tiles.values()) {
    if (on) {
      tile.setAttribute('draggable', 'true');
      attachTileDrag(tile);
    } else {
      tile.removeAttribute('draggable');
    }
  }
}

// =================== drag & drop tiles ===================
let dragTile = null;

function attachTileDrag(tile) {
  if (tile.__dragAttached) return;
  tile.__dragAttached = true;

  tile.addEventListener('dragstart', (e) => {
    if (!editMode) { e.preventDefault(); return; }
    dragTile = tile;
    tile.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', tile.dataset.id); } catch {}
  });

  tile.addEventListener('dragend', async () => {
    tile.classList.remove('dragging');
    grid.querySelectorAll('.drop-target').forEach(t => t.classList.remove('drop-target'));
    tabsNav.querySelectorAll('.drop-target').forEach(t => t.classList.remove('drop-target'));
    if (dragTile) await saveOrder();
    dragTile = null;
  });

  tile.addEventListener('dragover', (e) => {
    if (!editMode || !dragTile || dragTile === tile) return;
    e.preventDefault();
    const rect = tile.getBoundingClientRect();
    const after =
      (e.clientY - rect.top) > rect.height / 2 ||
      ((e.clientY - rect.top) > rect.height * 0.25 &&
       (e.clientX - rect.left) > rect.width / 2);
    grid.querySelectorAll('.drop-target').forEach(t => t.classList.remove('drop-target'));
    tile.classList.add('drop-target');
    if (after) tile.after(dragTile);
    else tile.before(dragTile);
  });

  tile.addEventListener('drop', (e) => e.preventDefault());
}

async function saveOrder() {
  const order = [...grid.querySelectorAll('.tile')].map(t => parseInt(t.dataset.id, 10));
  try {
    const r = await authedFetch('/admin/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tab_id: ACTIVE_TAB_ID, order }),
    });
    if (r.status === 401) {
      sessionStorage.removeItem('admin_auth');
      authHeader = null;
      alert('Сессия истекла, нажми «правка» ещё раз');
      setEditMode(false);
      return;
    }
    if (!r.ok) throw new Error('HTTP ' + r.status);
  } catch (e) {
    console.error('reorder failed', e);
  }
}

// =================== tabs as drop targets ===================
tabsNav.querySelectorAll('.tab[data-tab-id]').forEach(tab => {
  tab.addEventListener('dragover', (e) => {
    if (!editMode || !dragTile) return;
    e.preventDefault();
    tab.classList.add('drop-target');
  });
  tab.addEventListener('dragleave', () => {
    tab.classList.remove('drop-target');
  });
  tab.addEventListener('drop', async (e) => {
    if (!editMode || !dragTile) return;
    e.preventDefault();
    tab.classList.remove('drop-target');
    const targetTab = parseInt(tab.dataset.tabId, 10);
    if (targetTab === ACTIVE_TAB_ID) { dragTile = null; return; }
    const camId = parseInt(dragTile.dataset.id, 10);
    dragTile = null;
    await moveCameraToTab(camId, targetTab);
  });
});

async function moveCameraToTab(camId, tabId) {
  const fd = new FormData();
  fd.append('tab_id', String(tabId));
  try {
    const r = await authedFetch(`/admin/cameras/${camId}/move`, {
      method: 'POST', body: fd,
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    location.reload();
  } catch (e) {
    alert('Ошибка перемещения: ' + e.message);
  }
}

// =================== add tab ===================
addTabBtn.addEventListener('click', async () => {
  if (!(await ensureAuth())) return;
  const name = prompt('Название новой вкладки:');
  if (!name || !name.trim()) return;
  const fd = new FormData();
  fd.append('name', name.trim());
  try {
    const r = await authedFetch('/admin/tabs/add', { method: 'POST', body: fd });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    location.reload();
  } catch (e) {
    alert('Ошибка создания вкладки: ' + e.message);
  }
});
