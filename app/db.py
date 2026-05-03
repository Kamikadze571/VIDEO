import re
import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "cameras.db"

# поддерживаем старые "Camera N" и новые "Камера N"
_DEFAULT_NAME_RE = re.compile(r"^(?:Camera|Камера) \d+$")
DEFAULT_NAME_PREFIX = "Камера"
DEFAULT_TAB_NAME = "Все камеры"


async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tabs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                tab_id INTEGER NOT NULL DEFAULT 1,
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
        # миграции cameras
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
        if "tab_id" not in cols:
            await db.execute(
                "ALTER TABLE cameras ADD COLUMN tab_id INTEGER NOT NULL DEFAULT 1"
            )
        await db.commit()

        # обеспечить наличие хотя бы одной вкладки
        cur = await db.execute("SELECT COUNT(*) FROM tabs")
        if (await cur.fetchone())[0] == 0:
            await db.execute(
                "INSERT INTO tabs (name, position) VALUES (?, 0)",
                (DEFAULT_TAB_NAME,),
            )
            await db.commit()

        # сиротские камеры → в первую вкладку
        cur = await db.execute("SELECT id FROM tabs ORDER BY position, id LIMIT 1")
        first_tab = (await cur.fetchone())[0]
        await db.execute(
            "UPDATE cameras SET tab_id=? "
            "WHERE tab_id NOT IN (SELECT id FROM tabs)",
            (first_tab,),
        )
        await db.commit()


# ---------- tabs ----------

async def list_tabs():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, position FROM tabs ORDER BY position, id"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_tab(tab_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, position FROM tabs WHERE id=?", (tab_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_tab(name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM tabs")
        pos = (await cur.fetchone())[0]
        cur = await db.execute(
            "INSERT INTO tabs (name, position) VALUES (?, ?)",
            (name.strip(), pos),
        )
        await db.commit()
        return cur.lastrowid


async def rename_tab(tab_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tabs SET name=? WHERE id=?", (name.strip(), tab_id)
        )
        await db.commit()


async def delete_tab(tab_id: int) -> int | None:
    """Удалить вкладку, перенести её камеры в первую оставшуюся.
    Возвращает id целевой вкладки или None если эта была последней."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM tabs WHERE id != ? ORDER BY position, id LIMIT 1",
            (tab_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        target = row[0]
        # max position в целевой
        cur = await db.execute(
            "SELECT COALESCE(MAX(position), -1) FROM cameras WHERE tab_id=?",
            (target,),
        )
        base = (await cur.fetchone())[0] + 1
        # переносимые камеры — в порядке их position
        cur = await db.execute(
            "SELECT id FROM cameras WHERE tab_id=? ORDER BY position, id",
            (tab_id,),
        )
        ids = [r[0] for r in await cur.fetchall()]
        for i, cam_id in enumerate(ids):
            await db.execute(
                "UPDATE cameras SET tab_id=?, position=? WHERE id=?",
                (target, base + i, cam_id),
            )
        await db.execute("DELETE FROM tabs WHERE id=?", (tab_id,))
        await db.commit()
        return target


async def reorder_tabs(order: list[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        for pos, tab_id in enumerate(order):
            await db.execute(
                "UPDATE tabs SET position=? WHERE id=?", (pos, tab_id)
            )
        await db.commit()


# ---------- cameras ----------

async def list_cameras(only_active: bool = False, tab_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = (
            "SELECT id, name, url, tab_id, position, active, recording, "
            "fail_count, last_check FROM cameras WHERE 1=1"
        )
        params: list = []
        if only_active:
            sql += " AND active=1"
        if tab_id is not None:
            sql += " AND tab_id=?"
            params.append(tab_id)
        sql += " ORDER BY tab_id, position, id"
        async with db.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_camera(cam_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, url, tab_id, position, active, recording, "
            "fail_count, last_check FROM cameras WHERE id=?",
            (cam_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def find_by_url(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, url, tab_id, position, active "
            "FROM cameras WHERE url=? LIMIT 1",
            (url,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_camera(name: str, url: str, tab_id: int, active: int = 1) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 "
            "FROM cameras WHERE tab_id=?",
            (tab_id,),
        )
        pos = (await cur.fetchone())[0]
        cur = await db.execute(
            "INSERT INTO cameras (name, url, tab_id, position, active) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, url, tab_id, pos, active),
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
        ph = ",".join("?" * len(ids))
        cur = await db.execute(f"DELETE FROM cameras WHERE id IN ({ph})", ids)
        await db.commit()
        return cur.rowcount or 0


async def update_camera(cam_id: int, name: str, url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cameras SET name=?, url=? WHERE id=?",
            (name, url, cam_id),
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
            "UPDATE cameras SET recording=? WHERE id=?",
            (recording, cam_id),
        )
        await db.commit()


async def reorder(tab_id: int, order: list[int]):
    """Переписывает position для камер указанной вкладки."""
    async with aiosqlite.connect(DB_PATH) as db:
        for pos, cam_id in enumerate(order):
            await db.execute(
                "UPDATE cameras SET position=? WHERE id=? AND tab_id=?",
                (pos, cam_id, tab_id),
            )
        await db.commit()


async def move_camera(cam_id: int, tab_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM tabs WHERE id=?", (tab_id,))
        if not await cur.fetchone():
            return False
        cur = await db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 "
            "FROM cameras WHERE tab_id=?",
            (tab_id,),
        )
        pos = (await cur.fetchone())[0]
        await db.execute(
            "UPDATE cameras SET tab_id=?, position=? WHERE id=?",
            (tab_id, pos, cam_id),
        )
        await db.commit()
        return True


async def cameras_with_recording():
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
    Пересчитывает position внутри каждой вкладки (0..N-1) и переименовывает
    камеры с дефолтным именем 'Camera N' / 'Камера N' в сквозную нумерацию
    в порядке вкладок.
    """
    tabs = await list_tabs()
    cams_all = await list_cameras()
    by_tab: dict[int, list[dict]] = {}
    for c in cams_all:
        by_tab.setdefault(c["tab_id"], []).append(c)
    counter = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for tab in tabs:
            cams = by_tab.get(tab["id"], [])
            for i, cam in enumerate(cams):
                counter += 1
                new_name = cam["name"]
                if _DEFAULT_NAME_RE.match(cam["name"] or ""):
                    new_name = f"{DEFAULT_NAME_PREFIX} {counter}"
                await db.execute(
                    "UPDATE cameras SET position=?, name=? WHERE id=?",
                    (i, new_name, cam["id"]),
                )
        await db.commit()


# ---------- settings ----------

async def get_setting(key: str, default: str | None = None):
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
