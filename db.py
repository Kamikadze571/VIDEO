import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "cameras.db"


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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # миграции: добавляем поля если их нет
        cur = await db.execute("PRAGMA table_info(cameras)")
        cols = {row[1] for row in await cur.fetchall()}
        if "active" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN active INTEGER DEFAULT 1")
        if "recording" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN recording INTEGER DEFAULT 0")
        if "position" not in cols:
            await db.execute("ALTER TABLE cameras ADD COLUMN position INTEGER DEFAULT 0")
        await db.commit()


async def list_cameras(only_active: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT id, name, url, position, active, recording FROM cameras"
        if only_active:
            sql += " WHERE active=1"
        sql += " ORDER BY position, id"
        async with db.execute(sql) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_camera(cam_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, url, position, active, recording FROM cameras WHERE id=?",
            (cam_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_camera(name: str, url: str, active: int = 1) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM cameras"
        )
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


async def update_camera(cam_id: int, name: str, url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cameras SET name=?, url=? WHERE id=?", (name, url, cam_id)
        )
        await db.commit()


async def set_active(cam_id: int, active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE cameras SET active=? WHERE id=?", (active, cam_id))
        await db.commit()


async def set_recording(cam_id: int, recording: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE cameras SET recording=? WHERE id=?", (recording, cam_id)
        )
        await db.commit()


async def reorder(order: list[int]):
    """order — список cam_id в нужном порядке."""
    async with aiosqlite.connect(DB_PATH) as db:
        for pos, cam_id in enumerate(order):
            await db.execute(
                "UPDATE cameras SET position=? WHERE id=?", (pos, cam_id)
            )
        await db.commit()


async def cameras_with_recording() -> list[dict]:
    return [c for c in await list_cameras() if c["recording"]]
