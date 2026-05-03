import re
import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "cameras.db"

_DEFAULT_NAME_RE = re.compile(r"^Camera \d+$")


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                recording INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                last_check TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cur = await db.execute("PRAGMA table_info(cameras)")
        cols = {row[1] for row in await cur.fetchall()}
        if "active" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN active INTEGER DEFAULT 1")
        if "recording" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN recording INTEGER DEFAULT 0")
        if "position" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN position INTEGER DEFAULT 0")
        if "fail_count" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN fail_count INTEGER DEFAULT 0")
        if "last_check" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN last_check TIMESTAMP NULL")
        await db.commit()


async def list_cameras(only_active: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = (
            "SELECT id, name, url, position, active, recording, "
            "fail_count, last_check FROM cameras"
        )
        if only_active:
            sql += " WHERE active=1"
        sql += " ORDER BY position, id"
        async with db.execute(sql) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_camera(cam_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, url, position, active, recording, "
            "fail_count, last_check FROM cameras WHERE id=?",
            (cam_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def find_by_url(url: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, url, position, active, recording, "
            "fail_count, last_check FROM cameras WHERE url=? LIMIT 1",
            (url,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_camera(name: str, url: str, active: int = 1) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM cameras")
        pos = (await cur.fetchone())[0]
        cur = await db.execute(
            "INSERT INTO cameras (name, url, position, active) VALUES (?, ?, ?, ?)",
            (name, url, pos, active),
        )
        await db.commit()
        return cur.lastrowid


async def delete_camera(cam_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cameras WHERE id=?", (cam_id,))
        await db.commit()


async def delete_cameras(ids: list[int]) -> int:
    if not ids:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" * len(ids))
        cur = await db.execute(
            f"DELETE FROM cameras WHERE id IN ({placeholders})", ids
        )
        await db.commit()
        return cur.rowcount or 0


async def update_camera(cam_id: int, name: str, url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cameras SET name=?, url=? WHERE id=?", (name, url, cam_id)
        )
        await db.commit()


async def set_active(cam_id: int, active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cameras SET active=?, fail_count=0 WHERE id=?",
            (active, cam_id),
        )
        await db.commit()


async def set_recording(cam_id: int, recording: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cameras SET recording=? WHERE id=?", (recording, cam_id)
        )
        await db.commit()


async def reorder(order: list[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        for pos, cam_id in enumerate(order):
            await db.execute(
                "UPDATE cameras SET position=? WHERE id=?", (pos, cam_id)
            )
        await db.commit()


async def cameras_with_recording() -> list[dict]:
    return [c for c in await list_cameras() if c["recording"]]


async def mark_check_result(cam_id: int, ok: bool, fail_threshold: int = 3):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT active, fail_count FROM cameras WHERE id=?", (cam_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return
        if ok:
            await db.execute(
                "UPDATE cameras SET fail_count=0, active=1, "
                "last_check=CURRENT_TIMESTAMP WHERE id=?",
                (cam_id,),
            )
        else:
            new_fc = (row["fail_count"] or 0) + 1
            new_active = 0 if new_fc >= fail_threshold else row["active"]
            await db.execute(
                "UPDATE cameras SET fail_count=?, active=?, "
                "last_check=CURRENT_TIMESTAMP WHERE id=?",
                (new_fc, new_active, cam_id),
            )
        await db.commit()


async def dedupe_by_url() -> int:
    """Удаляет дубликаты по URL, оставляя только первую (по position) камеру."""
    cams = await list_cameras()
    seen: set[str] = set()
    to_delete: list[int] = []
    for c in cams:
        if c["url"] in seen:
            to_delete.append(c["id"])
        else:
            seen.add(c["url"])
    if to_delete:
        await delete_cameras(to_delete)
    return len(to_delete)


async def renumber():
    """
    Пересчитывает position подряд (0..N-1) и переименовывает все камеры
    с дефолтным именем 'Camera N' в правильную нумерацию.
    Кастомные имена не трогает.
    """
    cams = await list_cameras()
    async with aiosqlite.connect(DB_PATH) as db:
        for i, cam in enumerate(cams):
            new_name = cam["name"]
            if _DEFAULT_NAME_RE.match(cam["name"] or ""):
                new_name = f"Camera {i + 1}"
            await db.execute(
                "UPDATE cameras SET position=?, name=? WHERE id=?",
                (i, new_name, cam["id"]),
            )
        await db.commit()


# ---------- settings ----------

async def get_setting(key: str, default: str | None = None) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()
