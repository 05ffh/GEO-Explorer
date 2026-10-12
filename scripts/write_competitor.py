"""主 agent 介入工具：竞品识别后写回 positioning_json（P3 归因题前置）。

用法：python scripts/write_competitor.py <collection_run_id> <竞品> [竞品2 ...] [--client-adr 850]

竞品格式（结构化，spec 3.1 竞对圈层·系统化承载）：
  "福州世茂洲际酒店:核心:高端:700:标准"    # name:ring:tier:adr:format
  或纯名 "福州希尔顿"                      # 自动转 {"name": 名}，ring/tier 待补
band 自动分类（spec 3.1 甲方视角，2026-09-07）：系统查 brand_domains 判国际五星（main，
主竞争带）/本地高端（secondary，次竞争带）；表外 → band=None 待主 agent 复核。

复核门：传 --client-adr（甲方 ADR）时，系统用 filter_competitors 对候选做 ADR 带（甲方±50%）
+ 档位（±1）判定，带外项打印 ⚠️ 提示（不阻断写库），主 agent 据此复核。

主 agent 读 run_gt_diagnosis.py 介入点清单第 2 条，识别竞品（含档位/圈层语义）后，
执行本脚本把结构化竞品写回 collection_run.positioning_json["competitors"]。
P3 提问时从 positioning_json["competitors"] 读主竞对（核心圈同档 ADR 最接近者）。
"""
import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.competitor import COMPETITOR_BAND_MAIN, COMPETITOR_BAND_SECONDARY, classify_band, filter_competitors
from src.collector.gt_entry import append_competitors
from src.collector.tier import get_brand
from src.config import settings
from src.models.collection_run import CollectionRun


def _parse_competitor(s: str) -> dict:
    """解析 "名:ring:tier:adr:format:ai_cooccurrence:guest_mix"（可省略后段）或纯名。

    guest_mix 用 / 分隔多个客群（如 商务差旅/亲子家庭）。ai_cooccurrence = AI 同场景共现次数。
    """
    parts = s.split(":")
    name = parts[0].strip()
    if len(parts) == 1:
        return {"name": name}
    try:
        adr = float(parts[3]) if len(parts) > 3 and parts[3].strip() else None
    except ValueError:
        adr = None
        print(f"  ⚠️ {name} adr 非数字 {parts[3]!r}，按缺省处理")
    return {
        "name": name,
        "ring": parts[1].strip() or None,
        "tier": parts[2].strip() if len(parts) > 2 and parts[2].strip() else None,
        "adr": adr,
        "format": parts[4].strip() if len(parts) > 4 and parts[4].strip() else None,
        "ai_cooccurrence": int(parts[5]) if len(parts) > 5 and parts[5].strip().isdigit() else None,
        "guest_mix": [g.strip() for g in parts[6].split("/")] if len(parts) > 6 and parts[6].strip() else None,
    }


def _parse_args(argv):
    p = argparse.ArgumentParser(description="写竞品到 positioning_json（结构化，含 ADR 带/档位复核）")
    p.add_argument("run_id", help="collection_run id")
    p.add_argument("competitors", nargs="+", help="竞品，格式 名:ring:tier:adr:format 或纯名")
    p.add_argument("--client-adr", type=float, default=None,
                   help="甲方 ADR，传入则系统做 ADR 带/档位复核，带外项打印 ⚠️ 提示")
    return p.parse_args(argv)


async def main():
    args = _parse_args(sys.argv[1:])
    run_id, competitors = args.run_id, [_parse_competitor(x) for x in args.competitors]
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        run = await db.get(CollectionRun, run_id)
        if run is None:
            print(f"错误: collection_run {run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        client_tier = (run.positioning_json or {}).get("tier")
        # 自动 band 分类（spec 3.1 甲方视角：国际五星=主竞对/本地高端=次竞对）：
        # 系统查 brand_domains 判定，主 agent 复核表外项（band=None 时）
        for c in competitors:
            if c.get("band") is None:
                band = classify_band(get_brand(c["name"], city=run.city))
                if band is not None:
                    c["band"] = band
                else:
                    print(f"  ⚠️ {c['name']} 表外/非甲方同档，band 未定，主 agent 复核")
            elif c["band"] not in (COMPETITOR_BAND_MAIN, COMPETITOR_BAND_SECONDARY):
                print(f"  ⚠️ {c['name']} band 非法 {c.get('band')!r}，忽略 band")
                c["band"] = None
        if args.client_adr:
            # 复核门：系统对主 agent 输入候选做 ADR 带/档位判定，带外项提示（不阻断写库）
            for c in filter_competitors(competitors, client_tier, args.client_adr):
                flags = [f for f, ok in (("ADR带外", c.get("adr_in_band")), ("档位带外", c.get("tier_in_span"))) if not ok]
                mark = "⚠️" if flags else "✓"
                print(f"  {mark} {c['name']}: {' '.join(flags) if flags else '带内+同档'}")
        await append_competitors(db, run_id, competitors)
        await db.commit()
        print(f"已写竞品 {len(competitors)} 个 → collection_run {run_id}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
