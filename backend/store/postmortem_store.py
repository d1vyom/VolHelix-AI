import os
import aiosqlite
from typing import List, Optional
from backend.models.debate import PostMortem

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "postmortems.db")

class PostmortemStore:
    """SQLite persistence for PostMortem records."""

    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS postmortems (
                    trade_id TEXT PRIMARY KEY,
                    data JSON
                )
                """
            )
            await db.commit()

    async def save(self, postmortem: PostMortem):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO postmortems (trade_id, data)
                VALUES (?, ?)
                """,
                (postmortem.trade_id, postmortem.model_dump_json())
            )
            await db.commit()

    async def get_all(self) -> List[PostMortem]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM postmortems ORDER BY rowid DESC") as cursor:
                rows = await cursor.fetchall()
                return [PostMortem.model_validate_json(row[0]) for row in rows]

    async def get_by_trade(self, trade_id: str) -> Optional[PostMortem]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT data FROM postmortems WHERE trade_id = ?", (trade_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return PostMortem.model_validate_json(row[0])
                return None

postmortem_store = PostmortemStore()
