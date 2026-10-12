"""甲方自己页面全文抓取（P2 GT 正文分层）：抓正文 → 过滤 → 分层存 raw_content + content_text。

核心逻辑在 src.collector.client_pages（run_gt_diagnosis 链路复用同一函数）。本脚本用于
对已有 run 单独补采/重跑（换过滤规则时用 raw_content 重跑，不用重抓）。

用法：
  python scripts/fetch_client_pages.py <品牌> <collection_run_id> [--city 福州] [--city-en fuzhou] [--apply]
"""
import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.client_pages import fetch_and_store_client_pages
from src.config import settings
from src.models.brand import Brand


async def main():
    p = argparse.ArgumentParser(description="甲方自己页面全文抓取 → raw_content + content_text")
    p.add_argument("brand")
    p.add_argument("run_id")
    p.add_argument("--city", default="福州")
    p.add_argument("--city-en", default="fuzhou")
    p.add_argument("--brand-en", default="", help="品牌英文名（认领英文域名页面，如 shangri-la；表内品牌可填）")
    p.add_argument("--apply", action="store_true", help="写回（默认只预览）")
    p.add_argument("--refilter", action="store_true", help="用当前规则重跑 raw_content→content_text（不重抓）")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        brand = (await db.execute(select(Brand).where(Brand.name == args.brand))).scalar_one_or_none()
        if brand is None:
            print(f"错误: 品牌 {args.brand} 不存在")
            sys.exit(1)
        if args.refilter:
            from src.collector.client_pages import refilter_client_pages
            n = await refilter_client_pages(db, brand.id)
            await db.commit()
            print(f"重跑过滤：{n} 行 raw_content → content_text（未重抓）")
        elif not args.apply:
            from sqlalchemy import text
            from src.collector.client_pages import is_client_page_url
            rows = (await db.execute(text("""
                SELECT DISTINCT url FROM search_results
                WHERE brand_id=:b AND url IS NOT NULL AND query LIKE :bq AND query LIKE :cq
            """), {"b": brand.id, "bq": f"%{args.brand}%", "cq": f"%{args.city}%"})).fetchall()
            urls = [u for (u,) in rows if is_client_page_url(u, args.brand, args.city, args.city_en, args.brand_en)]
            print(f"甲方自己的页面 URL（去重）: {len(urls)} 个（预览模式，未抓取；加 --apply 抓取+过滤+存储）")
            for u in urls[:10]:
                print("  " + u[:80])
        else:
            stat = await fetch_and_store_client_pages(db, brand.id, args.brand, args.city, args.city_en, args.brand_en)
            await db.commit()
            print(f"抓取 {stat['urls']} URL → 成功 {stat['fetched']}，写 raw_content+content_text {stat['rows']} 行")
            if stat.get("reason"):
                print(f"  ⚠️ 未抓取到甲方页面：{stat['reason']}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
