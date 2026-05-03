import asyncio
import os

import httpx

from . import db

CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "600"))
FAIL_THRESHOLD = int(os.getenv("HEALTH_FAIL_THRESHOLD", "3"))


async def probe_url(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> bool:
    try:
        async with sem:
            r = await client.get(url, timeout=4.0)
        return r.status_code == 200 and bool(r.content)
    except (httpx.HTTPError, asyncio.TimeoutError):
        return False


async def check_all(client: httpx.AsyncClient, sem: asyncio.Semaphore) -> dict:
    """
    Проверяет ВСЕ камеры (включая active=0) — чтобы выключенные могли
    автоматически вернуться в строй, как только заработают.
    """
    cams = await db.list_cameras(only_active=False)
    if not cams:
        return {"checked": 0, "ok": 0, "fail": 0}

    results = await asyncio.gather(
        *(probe_url(client, c["url"], sem) for c in cams),
        return_exceptions=False,
    )
    ok = 0
    for cam, is_ok in zip(cams, results):
        await db.mark_check_result(cam["id"], is_ok, fail_threshold=FAIL_THRESHOLD)
        if is_ok:
            ok += 1
    return {"checked": len(cams), "ok": ok, "fail": len(cams) - ok}


class HealthLoop:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.client: httpx.AsyncClient | None = None
        self.sem: asyncio.Semaphore | None = None

    def start(self, client: httpx.AsyncClient, sem: asyncio.Semaphore):
        self.client = client
        self.sem = sem
        self._stop.clear()
        self.task = asyncio.create_task(self._run())

    async def _run(self):
        # пауза перед первым прогоном — не дёргаем апстрим на старте
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=30.0)
            return
        except asyncio.TimeoutError:
            pass
        while not self._stop.is_set():
            try:
                await check_all(self.client, self.sem)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=CHECK_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def stop(self):
        self._stop.set()
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=5.0)
            except asyncio.TimeoutError:
                self.task.cancel()
