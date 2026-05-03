const grid = document.getElementById('grid');
const cameras = JSON.parse(grid.dataset.cameras);
const sizeInput = document.getElementById('size');
const fpsInput = document.getElementById('fps');
const fpsLabel = document.getElementById('fpsv');
const pauseBtn = document.getElementById('pause');

let intervalMs = 1000 / parseInt(fpsInput.value, 10);
let paused = false;

const tiles = new Map();

function buildTile(cam) {
  const tile = document.createElement('div');
  tile.className = 'tile';
  tile.dataset.id = cam.id;
  tile.innerHTML = `
    <img alt="">
    <span class="status"></span>
    <span class="label">${escapeHtml(cam.name)}</span>
    <a class="live-link" href="/stream/${cam.id}" target="_blank" rel="noopener">Live</a>
  `;
  const img = tile.querySelector('img');
  grid.appendChild(tile);
  tiles.set(cam.id, { tile, img, visible: false, lastLoad: 0, inflight: false, cam });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

cameras.forEach(buildTile);

const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const id = parseInt(e.target.dataset.id, 10);
    const t = tiles.get(id);
    if (!t) continue;
    t.visible = e.isIntersecting;
  }
}, { rootMargin: '200px' });

tiles.forEach(({ tile }) => io.observe(tile));

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

sizeInput.addEventListener('input', () => {
  document.documentElement.style.setProperty('--tile', sizeInput.value + 'px');
});
fpsInput.addEventListener('input', () => {
  const fps = parseInt(fpsInput.value, 10);
  fpsLabel.textContent = fps;
  intervalMs = 1000 / fps;
});
pauseBtn.addEventListener('click', () => {
  paused = !paused;
  pauseBtn.textContent = paused ? 'Resume' : 'Pause';
});

grid.addEventListener('dblclick', (e) => {
  if (e.target.closest('.live-link')) return;
  const tile = e.target.closest('.tile');
  if (!tile) return;
  if (document.fullscreenElement) document.exitFullscreen();
  else tile.requestFullscreen();
});
