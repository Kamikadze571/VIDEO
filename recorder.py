import asyncio
import os
from datetime import datetime, date
from pathlib import Path

import aiofiles
import httpx

from . import db

REC_ROOT = Path(__file__).parent.parent / "recordings"
SEGMENT_BYTES = int(os.getenv("REC_SEGMENT_BYTES", str(100 * 1024 * 1024)))  # 100 MB
SEGMENT_SECONDS = int(os.getenv("REC_SEGMENT_SECONDS", str(3600)))  # 1 час
REC_FPS = float(os.getenv("REC_FPS", "5.0"))
BOUNDARY = b"--frame"


class CameraRecorder:
    def __init__(self, cam: dict, client: httpx.AsyncClient):
        self.cam = cam
        self.client = client
        self.task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _open_segment(self):
        d = date.today().isoformat()
        folder = REC_ROOT / f"{self.cam['id']}_{d}"
        folder.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        path = folder / f"{ts}.mjpeg"
        return await aiofiles.open(path, "wb"), path

    async def _run(self):
        interval = 1.0 / REC_FPS
        f, path = await self._open_segment()
        seg_started = asyncio.get_event_loop().time()
        seg_bytes = 0
        try:
            while not self._stop.is_set():
                t0 = asyncio.get_event_loop().time()
                try:
                    r = await self.client.get(self.cam["url"], timeout=4.0)
                    if r.status_code == 200 and r.content:
                        frame = (
                            BOUNDARY
                            + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + str(len(r.content)).encode()
                            + b"\r\n\r\n"
                            + r.content
                            + b"\r\n"
                        )
                        await f.write(frame)
                        seg_bytes += len(frame)
                except (httpx.HTTPError, OSError):
                    pass

                # ротация
                now = asyncio.get_event_loop().time()
                if (
                    seg_bytes >= SEGMENT_BYTES
                    or (now - seg_started) >= SEGMENT_SECONDS
                ):
                    await f.close()
                    f, path = await self._open_segment()
                    seg_started = now
                    seg_bytes = 0

                # держим ритм
                dt = asyncio.get_event_loop().time() - t0
                sleep_for = max(0.0, interval - dt)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=sleep_for)
                except asyncio.TimeoutError:
                    pass
        finally:
            try:
                await f.close()
            except Exception:
                pass

    def start(self):
        if self.task and not self.task.done():
            return
        self._stop.clear()
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=5.0)
            except asyncio.TimeoutError:
                self.task.cancel()


class RecorderManager:
    def __init__(self):
        self.workers: dict[int, CameraRecorder] = {}
        self.client: httpx.AsyncClient | None = None

    def attach_client(self, client: httpx.AsyncClient):
        self.client = client

    async def sync(self):
        """Синхронизирует воркеры с состоянием БД."""
        if self.client is None:
            return
        cams = {c["id"]: c for c in await db.cameras_with_recording()}
        # стопаем убранные
        for cam_id in list(self.workers.keys()):
            if cam_id not in cams:
                await self.workers[cam_id].stop()
                del self.workers[cam_id]
        # стартуем новые
        for cam_id, cam in cams.items():
            if cam_id not in self.workers:
                w = CameraRecorder(cam, self.client)
                w.start()
                self.workers[cam_id] = w

    async def stop_all(self):
        for w in self.workers.values():
            await w.stop()
        self.workers.clear()


def list_recordings(cam_id: int) -> list[dict]:
    base = REC_ROOT
    if not base.exists():
        return []
    out = []
    for folder in sorted(base.glob(f"{cam_id}_*")):
        for f in sorted(folder.glob("*.mjpeg")):
            st = f.stat()
            out.append(
                {
                    "name": f"{folder.name}/{f.name}",
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
            )
    return out
