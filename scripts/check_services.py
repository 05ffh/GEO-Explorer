"""服务可用性自检（新开基线前）：Docker(DB) + 两路搜索后端 + 四大 AI 平台。只读、最小调用。

用法：PYTHONPATH=. .venv/bin/python scripts/check_services.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import settings
from src.search import get_available_backends

_AI = [("DeepSeek", "DeepSeekAdapter"), ("Kimi", "KimiAdapter"),
       ("豆包", "DoubaoAdapter"), ("文心", "WenxinAdapter")]


async def _check_db() -> tuple[bool, str]:
    try:
        e = create_async_engine(settings.database_url, connect_args={"timeout": 5})
        async with e.connect() as c:
            await c.execute(text("SELECT 1"))
        await e.dispose()
        return True, "连接成功"
    except Exception as ex:
        return False, f"{type(ex).__name__}: {ex}"


async def _check_search() -> dict:
    out = {}
    for b in get_available_backends(settings):
        try:
            r = await b.search("福州香格里拉酒店", num=3)
            out[b.__class__.__name__] = (len(r) > 0, f"{len(r)} 条结果")
        except Exception as ex:
            out[b.__class__.__name__] = (False, f"{type(ex).__name__}: {ex}")
    return out


async def _check_ai() -> dict:
    import src.adapters as A
    out = {}
    for name, cls_name in _AI:
        try:
            resp = await getattr(A, cls_name)().query("只回复两个字：可用")
            txt = (resp.answer_text or "").strip()
            out[name] = (bool(txt) and not resp.error, txt[:40] or (resp.error or "(空)"))
        except Exception as ex:
            out[name] = (False, f"{type(ex).__name__}: {ex}")
    return out


async def main() -> None:
    db = await _check_db()
    print(f"[Docker/DB]  {'✅' if db[0] else '❌'} {db[1]}")
    print("\n[两路搜索后端]")
    for n, (ok, msg) in (await _check_search()).items():
        print(f"  {'✅' if ok else '❌'} {n}: {msg}")
    print("\n[四大 AI 平台]")
    for n, (ok, msg) in (await _check_ai()).items():
        print(f"  {'✅' if ok else '❌'} {n}: {msg}")


if __name__ == "__main__":
    asyncio.run(main())
