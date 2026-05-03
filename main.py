import asyncio
import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import (
    Depends, FastAPI, Form, HTTPException, Request, status,
)
from fastapi.responses import (
    FileResponse, JSONResponse, RedirectResponse, StreamingResponse,
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .recorder import RecorderManager, REC_ROOT, list_recordings
from .health import HealthLoop, check_all

BASE = Path(__file__).parent
SNAPSHOT_TIMEOUT = float(os.getenv("SNAPSHOT_TIMEOUT", "4.0"))
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "32"))
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "strongpassword123")
STREAM_FPS = float(os.getenv("STREAM_FPS", "5.0"))
DEFAULT_IP_TEMPLATE = os.getenv("IP_URL_TEMPLATE", "http://{ip}/snapshot.cgi")

http_client: httpx.AsyncClient | None = None
sem: asyncio.Semaphore | None = None
recorder = RecorderManager()
health = HealthLoop()
security = HTTPBasic()


def auth(creds: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(creds.username, ADMIN_LOGIN)
    ok_pass = secrets.compare_digest(creds.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, sem
    await db.init_db()
    REC_ROOT.mkdir(parents=True, exist_ok=True)

    if await db.get_setting("ip_url_template") is None:
        await db.set_setting("ip_url_template", DEFAULT_IP_TEMPLATE)

    limits = httpx.Limits(max_keepalive_connections=64, max_connections=128)
    http_client = httpx.AsyncClient(
        timeout=SNAPSHOT_TIMEOUT,
        limits=limits,
        follow_redirects=True,
        verify=False,
    )
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    recorder.attach_client(http_client)
    await recorder.sync()
    health.start(http_client, sem)
    try:
        yield
    finally:
        await health.stop()
        await recorder.stop_all()
        await http_client.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


# ---------------- helpers ----------------

_IP_RE = re.compile(
    r"^((?:\d{1,3}\.){3}\d{1,3}|\[?[0-9a-fA-F:]+\]?)(?::(\d{1,5}))?$"
)


def expand_ip(line: str, template: str) -> str:
    """
    Принимает 'IP' или 'IP:port' и подставляет в шаблон.
    Шаблон должен содержать {ip} (опционально {port}).
    Если в строке не IP — возвращает её без изменений.
    """
    line = line.strip()
    m = _IP_RE.match(line)
    if not m:
        return line
    ip = m.group(1)
    port = m.group(2)
    if "{ip}" in template:
        if "{port}" in template:
            out = template.replace("{ip}", ip).replace("{port}", port or "")
        else:
            target = ip + (f":{port}" if port else "")
            out = template.replace("{ip}", target)
        return out
    target = ip + (f":{port}" if port else "")
    return f"{template.rstrip('/')}/{target}"


async def _probe(url: str) -> bool:
    try:
        async with sem:
            r = await http_client.get(url)
        return r.status_code == 200 and bool(r.content)
    except httpx.HTTPError:
        return False


# ---------------- public ----------------

@app.get("/")
async def index(request: Request):
    cams = await db.list_cameras(only_active=True)
    return templates.TemplateResponse(
        "index.html", {"request": request, "cameras": cams}
    )


@app.get("/api/cameras")
async def api_cameras():
    return await db.list_cameras(only_active=True)


@app.get("/snap/{cam_id}")
async def snap(cam_id: int):
    cam = await db.get_camera(cam_id)
    if not cam:
        raise HTTPException(404, "camera not found")
    async with sem:
        try:
            r = await http_client.get(cam["url"])
        except httpx.HTTPError as e:
            return JSONResponse({"error": str(e)}, status_code=502)
    if r.status_code != 200:
        return JSONResponse({"error": f"upstream {r.status_code}"}, status_code=502)
    media = r.headers.get("content-type", "image/jpeg")
    return StreamingResponse(
        iter([r.content]),
        media_type=media,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/stream/{cam_id}")
async def stream(cam_id: int):
    cam = await db.get_camera(cam_id)
    if not cam:
        raise HTTPException(404, "camera not found")

    boundary = "frame"
    interval = 1.0 / STREAM_FPS

    async def gen():
        while True:
            t0 = asyncio.get_event_loop().time()
            try:
                async with sem:
                    r = await http_client.get(cam["url"])
                if r.status_code == 200 and r.content:
                    chunk = (
                        f"--{boundary}\r\n"
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(r.content)}\r\n\r\n"
                    ).encode() + r.content + b"\r\n"
                    yield chunk
            except httpx.HTTPError:
                pass
            except asyncio.CancelledError:
                break
            dt = asyncio.get_event_loop().time() - t0
            await asyncio.sleep(max(0.0, interval - dt))

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store"},
    )


# ---------------- admin ----------------

@app.get("/admin")
async def admin(request: Request, _: str = Depends(auth)):
    cams = await db.list_cameras()
    template = await db.get_setting("ip_url_template", DEFAULT_IP_TEMPLATE)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "cameras": cams, "ip_template": template},
    )


@app.get("/admin/whoami")
async def admin_whoami(user: str = Depends(auth)):
    """Лёгкий пинг auth — для Edit Mode на главной."""
    return JSONResponse({"user": user, "ok": True})


@app.post("/admin/add")
async def admin_add(
    name: str = Form(...),
    url: str = Form(...),
    _: str = Depends(auth),
):
    name, url = name.strip(), url.strip()
    if not name or not url:
        raise HTTPException(400, "name/url required")
    active = 1 if await _probe(url) else 0
    await db.add_camera(name, url, active=active)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/bulk_add")
async def admin_bulk_add(
    urls: str = Form(...),
    as_ip: int = Form(0),
    template: str = Form(""),
    _: str = Depends(auth),
):
    lines = [u.strip() for u in urls.splitlines() if u.strip()]
    if not lines:
        return JSONResponse({"added": 0, "results": []})

    if as_ip:
        tpl = (template or "").strip() or await db.get_setting(
            "ip_url_template", DEFAULT_IP_TEMPLATE
        )
        if "{ip}" not in tpl:
            return JSONResponse(
                {"error": "template must contain {ip}"}, status_code=400
            )
        await db.set_setting("ip_url_template", tpl)
        lines = [expand_ip(line, tpl) for line in lines]

    probes = await asyncio.gather(*[_probe(u) for u in lines])

    existing = await db.list_cameras()
    next_n = len(existing) + 1

    results = []
    for url, ok in zip(lines, probes):
        name = f"Camera {next_n}"
        cam_id = await db.add_camera(name, url, active=1 if ok else 0)
        results.append({"id": cam_id, "url": url, "name": name, "ok": ok})
        next_n += 1

    return JSONResponse({"added": len(results), "results": results})


@app.post("/admin/delete/{cam_id}")
async def admin_delete(cam_id: int, _: str = Depends(auth)):
    await db.set_recording(cam_id, 0)
    await recorder.sync()
    await db.delete_camera(cam_id)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/bulk_delete")
async def admin_bulk_delete(request: Request, _: str = Depends(auth)):
    body = await request.json()
    ids = body.get("ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise HTTPException(400, "bad ids")
    for cid in ids:
        await db.set_recording(cid, 0)
    await recorder.sync()
    deleted = await db.delete_cameras(ids)
    return JSONResponse({"ok": True, "deleted": deleted})


@app.post("/admin/update/{cam_id}")
async def admin_update(
    cam_id: int,
    name: str = Form(...),
    url: str = Form(...),
    _: str = Depends(auth),
):
    await db.update_camera(cam_id, name.strip(), url.strip())
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/active/{cam_id}")
async def admin_active(
    cam_id: int, active: int = Form(...), _: str = Depends(auth)
):
    await db.set_active(cam_id, 1 if active else 0)
    return JSONResponse({"ok": True, "active": bool(active)})


@app.post("/admin/recording/{cam_id}")
async def admin_recording(
    cam_id: int, recording: int = Form(...), _: str = Depends(auth)
):
    await db.set_recording(cam_id, 1 if recording else 0)
    await recorder.sync()
    return JSONResponse({"ok": True, "recording": bool(recording)})


@app.post("/admin/reorder")
async def admin_reorder(request: Request, _: str = Depends(auth)):
    body = await request.json()
    order = body.get("order", [])
    if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
        raise HTTPException(400, "bad order")
    await db.reorder(order)
    return JSONResponse({"ok": True})


@app.post("/admin/probe/{cam_id}")
async def admin_probe(cam_id: int, _: str = Depends(auth)):
    cam = await db.get_camera(cam_id)
    if not cam:
        raise HTTPException(404, "camera not found")
    ok = await _probe(cam["url"])
    await db.mark_check_result(cam_id, ok)
    return JSONResponse({"ok": ok})


@app.post("/admin/probe_all")
async def admin_probe_all(_: str = Depends(auth)):
    summary = await check_all(http_client, sem)
    return JSONResponse(summary)


@app.post("/admin/settings")
async def admin_settings(
    ip_url_template: str = Form(...), _: str = Depends(auth)
):
    tpl = ip_url_template.strip()
    if "{ip}" not in tpl:
        raise HTTPException(400, "template must contain {ip}")
    await db.set_setting("ip_url_template", tpl)
    return JSONResponse({"ok": True, "ip_url_template": tpl})


# ---------------- recordings ----------------

@app.get("/admin/recordings/{cam_id}")
async def recordings_index(
    request: Request, cam_id: int, _: str = Depends(auth)
):
    cam = await db.get_camera(cam_id)
    if not cam:
        raise HTTPException(404, "camera not found")
    files = list_recordings(cam_id)
    return templates.TemplateResponse(
        "recordings.html",
        {"request": request, "camera": cam, "files": files},
    )


@app.get("/admin/recordings/{cam_id}/file")
async def recordings_download(
    cam_id: int, name: str, _: str = Depends(auth)
):
    safe = Path(name)
    if safe.is_absolute() or ".." in safe.parts:
        raise HTTPException(400, "bad path")
    parts = safe.parts
    if len(parts) != 2 or not parts[0].startswith(f"{cam_id}_"):
        raise HTTPException(400, "bad path")
    full = REC_ROOT / safe
    if not full.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(
        full,
        media_type="application/octet-stream",
        filename=f"{parts[0]}_{parts[1]}",
    )
