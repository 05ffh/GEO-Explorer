"""P2 诊断入口（确定性段）：建单元 → 采集 → 负面率初筛 → 档位 → 输出介入点清单。

主 agent 调度契约：脚本只跑「确定性」部分，跑完 dump 中间产物到
/tmp/gt_collect_result.json，并打印「主 agent 介入点清单」。
主 agent 对照清单做「语义判断」（字段提取 / 可信度评定 / 负面终判 / 档位兜底 / 竞品识别），
再调 src.collector.gt_entry 的 write_* 写库。
"""
import asyncio
import copy
import json
import sys
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_collector_v2 import collect_raw, collect_sentiment, group_by_field
from src.collector.gt_entry import (
    carry_forward_p2, create_collection_run, get_or_create_brand, write_positioning,
    write_search_result, write_sentiment,
)
from src.collector.sentiment import compute_negative_rate
from src.collector.tier import derive_tier
from src.industry_knowledge.loader import get_knowledge_loader


def find_brand_en(brand_zh: str) -> str | None:
    """从 brand_domains 查英文名（甲方页面 URL 认领用）。表外返回 None。"""
    for item in get_knowledge_loader().load_category("brand_domains"):
        if item.get("zh") == brand_zh:
            return (item.get("en") or "").lower() or None
    return None
from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.organization import Organization
from src.search.search_all import search_all_backends


def _dump(materials, with_tier: bool) -> list[dict]:
    out = []
    for m in materials:
        d = {"url": m.url, "title": m.title, "snippet": m.snippet,
             "query": m.query, "provider": m.provider}
        if with_tier:
            d["tier"] = m.tier
        out.append(d)
    return out


async def _carry_p2_on_rebuild(db, brand_id, city: str, new_run: CollectionRun) -> dict:
    """重建 P2（run_gt_diagnosis）：从同品牌+城市**最近一个 run** 承接甲方级 P2（gt/cdp/positioning），
    `sentiment` 重采、`tier` 重算。返回承接的 positioning（供调用方合并新 tier）；无前序 run → 空 dict。

    **第一性原理**：甲方事实（gt/cdp）绑定**诊断单元**（品牌+城市）而非问法 → 重建 P2 时事实不变、应承接；
    换品牌/城市 = 新诊断单元 → 无前序 run → 不承接。**修 2026-10-14**：原 `run_gt_diagnosis` 只产定位/舆情/
    页面/CDP，**不产 gt** → 不承接则新 run 第一依据为空（体系B 换舆情词必走此重建路径）。
    """
    prev = (await db.execute(
        select(CollectionRun)
        .where(CollectionRun.brand_id == brand_id, CollectionRun.city == city,
               CollectionRun.id != new_run.id)
        .order_by(CollectionRun.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if prev is None:
        return {}
    if not new_run.region and prev.region:
        new_run.region = prev.region
    await carry_forward_p2(db, prev, new_run, skip=("sentiment_json",))
    return copy.deepcopy(new_run.positioning_json or {})


async def main(brand_name: str, city: str, region: str | None):
    # ① 建诊断单元
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            org = Organization(name="默认机构")
            db.add(org)
            await db.flush()
        brand = await get_or_create_brand(db, brand_name, org.id)
        run = await create_collection_run(db, org.id, brand.id, city, region)
        # 重建 P2：承接甲方级 P2（gt/cdp/positioning），sentiment 重采、tier 重算
        carried_pos = await _carry_p2_on_rebuild(db, brand.id, city, run)
        await db.commit()
        org_id, brand_id, run_id = str(org.id), str(brand.id), str(run.id)

    # ② 采集（事实 + 舆情）
    fact = await collect_raw(brand_name, city, search_all_backends)
    senti = await collect_sentiment(brand_name, city, search_all_backends)
    fact_grouped = group_by_field(fact)
    senti_grouped = group_by_field(senti)

    # ③ 负面率初筛（关键词粗筛，终判由主 agent）
    store = compute_negative_rate(senti_grouped.get("store_level", []))
    brand_neg = compute_negative_rate(senti_grouped.get("brand_level", []))

    # ④ 档位（查表；表外品牌返回 None → 主 agent 兜底；city 过滤本地品牌地区归属）
    tier = derive_tier(brand_name, city=city)

    # ④½ 写定位 + 负面率（粗筛 preliminary，待主 agent 终判 confirmed）+ 事实/舆情材料落库（带 URL，spec 4.5）
    seen_urls: set[str] = set()
    async with session_factory() as db:
        # 承接的 positioning（competitors/personas）保留，tier 用本次重算；positioned_at 重新锚定
        carried_pos.pop("positioned_at", None)
        await write_positioning(db, run_id, {**carried_pos, "tier": tier,
                                             "competitors": carried_pos.get("competitors", [])})
        senti_json = {"store_level": {**store, "status": "preliminary"}}
        if senti_grouped.get("brand_level"):     # 单档（体系B，无品牌级词）→ 不写 brand_level
            senti_json["brand_level"] = {**brand_neg, "status": "preliminary"}
        await write_sentiment(db, run.id, senti_json)
        # 事实 + 舆情材料都落库（事实页是"甲方自己页面全文抓取"的 URL 来源）
        for m in fact + senti:
            if m.url:
                if m.url in seen_urls:
                    continue
                seen_urls.add(m.url)
            await write_search_result(db, org.id, brand.id, run.id, m.provider, m.query,
                                      m.url, m.title, m.snippet, m.tier, m.published_at)
        await db.commit()

        # ④¾ 甲方自己页面全文抓取 → 过滤 → 分层存 raw_content + content_text（P2 GT 正文，2026-09-14）
        from src.collector.client_pages import fetch_and_store_client_pages, city_pinyin
        brand_en = find_brand_en(brand_name) or ""
        stat = await fetch_and_store_client_pages(db, brand.id, brand_name, city,
                                                  city_pinyin(city), brand_en)
        await db.commit()
        print(f"甲方页面全文抓取: {stat['urls']} URL → {stat['fetched']} 成功，写正文 {stat['rows']} 行")
        if stat.get("reason"):
            print(f"  ⚠️ 甲方页面接地语料为空（归因将退回只用 AI 引用内容）：{stat['reason']}")

        # ④⅞ CDP 抓取（3 平台）：用户已在浏览器打开酒店页 → 系统**验证标题（品牌+城市）** → 抓取落库。
        # 谨慎边界：Chrome 未起 / 页面未开 / 标题不符 → 跳过 + 告警，**不阻塞 P2 主流程**。
        from scripts.fetch_ota_cdp import cdp_scrape_all
        cdp = await cdp_scrape_all(db, run_id, brand_name, city)
        await db.commit()
        print(f"CDP 抓取（3 平台）:")
        for _p, _r in cdp.items():
            if _r.get("ok"):
                print(f"  ✓ [{_p}] 落库 {str(_r.get('id', ''))[:8]}  {_r['content_text_len']} 字"
                      f"（hotelId={_r['hotel_id']}，{_r['hotel_id_src']}）")
            else:
                print(f"  ⚠️ [{_p}] 跳过：{_r.get('error')}")

    # ⑤ 异常检测（主 agent 补救信号）
    thin_fields = {f: len(ms) for f, ms in fact_grouped.items() if len(ms) < 3}
    providers = Counter(m.provider for m in fact + senti if m.provider)
    missing_backends = [b for b in ("tavily", "doubao_search") if providers.get(b, 0) == 0]

    result = {
        "org_id": org_id, "brand_id": brand_id, "collection_run_id": run_id,
        "brand": brand_name, "city": city, "region": region,
        "tier": tier,
        "tier_unresolved": tier is None,
        "competitor_skipped": "competitors" not in fact_grouped,
        "fact_fields": {f: _dump(ms, True) for f, ms in fact_grouped.items()},
        "sentiment": {f: _dump(ms, False) for f, ms in senti_grouped.items()},
        "negative_rate_preliminary": {"store_level": store, "brand_level": brand_neg},
        "thin_fields": thin_fields,
        "missing_backends": missing_backends,
    }
    with open("/tmp/gt_collect_result.json", "w") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(json.dumps({
        "brand_id": brand_id, "collection_run_id": run_id, "tier": tier,
        "tier_unresolved": tier is None,
        "competitor_skipped": "competitors" not in fact_grouped,
        "fact_fields_count": {f: len(ms) for f, ms in fact_grouped.items()},
        "sentiment_count": {f: len(ms) for f, ms in senti_grouped.items()},
        "negative_rate_preliminary": {"store_level": store["rate"], "brand_level": brand_neg["rate"]},
    }, ensure_ascii=False, indent=2))

    print("\n=== 主 agent 介入点清单 ===")
    tier_msg = f"已定 {tier}" if tier is not None else "未定，主 agent 判档位"
    print(f"1. 档位: {tier_msg}")
    print("   → 品牌表内已按品牌行政档位定档；若需 ADR/星级精修（豪华品牌实际价位可能降档，表外品牌靠价位），")
    print("     从 star_rating/adr 字段材料提取 ADR/星级，执行:")
    print(f"     python scripts/finalize_tier.py {run_id} --adr 850 --star 五星   # derive_tier 综合算档位")
    print(f"     或 python scripts/finalize_tier.py {run_id} --tier 高端           # 主 agent 直接指定")
    print(f"2. 竞品识别（P3 归因题前置）: {'档位未定→竞品查询词已跳过，先定档再识别同地区同档竞品' if 'competitors' not in fact_grouped else '竞品材料已采（±1档多档位词），主 agent 从中识别候选竞品名 + 判定档位/圈层/业态（语义）'}")
    print(f"   → 竞对判定 = 同城 ∩ ADR带(甲方±50%) ∩ 档位(±1) ∩ 业态可替代；系统判档位/ADR带，主 agent 复核 ring/format/去重")
    print(f"   → 结构化写库: python scripts/write_competitor.py {run_id} '福州世茂洲际酒店:核心:高端:700:标准'（名:圈层:档位:ADR:业态）；否则 P3 归因层 5 题静默缺失")
    print(f"3. 字段提取: {sorted(fact_grouped.keys())}")
    print("4. 可信度评定: 每字段提取归一化值后，构建 Evidence 调 assess_credibility（verified/consensus 才写正文）")
    print("5. 负面终判（spec 4.5，负面率现为 preliminary 粗筛下界，细筛交主 agent）:")
    print(f"   python scripts/finalize_sentiment.py {run_id} --generate   # 生成负面候选清单（URL/内容/主题）")
    print("   主 agent 逐条标 verdict: negative（真负面）/ exclude（误判：主语不符/地名歧义/跨国/评分摘要），加 reason")
    print(f"   python scripts/finalize_sentiment.py {run_id} --apply /tmp/verdict_xxx.json  # 重算负面率写回 status=confirmed")
    print(f"6. 采集不足: {thin_fields or '无'}")
    print(f"7. 后端失败: {missing_backends or '无'}")
    print("8. 人群推断: 读官网定位描述/房型/设施/地理位置四信号，判各人群信号数，执行:")
    print(f"   python scripts/finalize_personas.py {run_id} 商务差旅 3 亲子家庭 1   # 写回 positioning.personas")
    await engine.dispose()


if __name__ == "__main__":
    brand = sys.argv[1] if len(sys.argv) > 1 else "香格里拉"
    city = sys.argv[2] if len(sys.argv) > 2 else "福州"
    region = sys.argv[3] if len(sys.argv) > 3 else None
    asyncio.run(main(brand, city, region))
