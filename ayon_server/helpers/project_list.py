from datetime import datetime
from typing import Any

from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel
from ayon_server.utils import get_nickname, json_dumps, json_loads


class ProjectListItem(OPModel):
    name: str
    code: str
    created_at: datetime
    nickname: str


async def build_project_list() -> list[dict[str, Any]]:
    q = """SELECT name, code, created_at FROM projects ORDER BY name ASC"""
    result: list[dict[str, Any]] = []
    async for row in Postgres.iterate(q):
        result.append(
            {
                "name": row["name"],
                "code": row["code"],
                "created_at": row["created_at"],
                "nickname": get_nickname(str(row["created_at"]) + row["name"], 2),
            }
        )
    await Redis.set("global", "project-list", json_dumps(result))
    return result


async def get_project_list() -> list[ProjectListItem]:
    project_list = await Redis.get("global", "project-list")
    if project_list is None:
        project_list = await build_project_list()
    else:
        project_list = json_loads(project_list)
    return [ProjectListItem(**item) for item in project_list]
