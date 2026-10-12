"""命中语义判定工具（A-2，spec 11.9）：generate 待判清单 → 子 agent 判六字段 → apply 回填。

替代 complete_measure.py（旧回填只写 hit/rank 旧字段，与新六字段结构不匹配）。

用法：
  1. generate：python scripts/finalize_hit.py --generate <collection_run_id> [--out 待判清单.json] [--all]
     → 输出待判清单（题目+回答+系统预判），主 agent 调度子 agent 逐题判；--all=rejudge 全量（含已判题 + 当前值）
  2. 子 agent 判定 JSON（按平台+题组织）：
     {"deepseek": {"hit_business_generic": {
         "recommendation": "recommend|mention|exclude|absent",
         "scene": {"dim": "region", "val": "鼓楼区", "rank_in_scene": 1, "in_scene_count": 3},
         "referred_content": ["江南灶·融府"],
         "has_hotel_recommendations": true,
         "hotels_recommended": ["福州世茂洲际酒店", "福州香格里拉大酒店"],
         "hotels_mentioned": ["福州泰禾凯宾斯基酒店"]
     }}}
  3. apply：python scripts/finalize_hit.py --apply <collection_run_id> 判定.json
     → 写回六字段 + needs_agent=False + 系统派生档位（answer_tier_distribution/same_tier_pushed）
     + 派生 hit + finalize 重算 + 落库（backfill）

子 agent 判定规范（六字段边界，2026-09-04 对齐 + 校准集修正）：
- recommendation：
  - recommend = AI 明确推荐甲方（"首选/推荐"语境），**含"被列入推荐列表"即使靠后**——
    甲方在 AI 的推荐列表里（第 2-5 位）就是被推荐（排名靠后不降级为 mention，2026-09-04 裁决）
  - mention = 甲方名字出现但**不在推荐列表**（结尾顺嘴一句、或"也不错，但更推荐 X"后没列入名单）
  - exclude = AI **明确不推荐**甲方/指出甲方不合适；**"推荐甲方但指出缺点"（如早餐另付费）≠ exclude**，
    仍算 recommend（2026-09-04 修正 Kimi Q4 误判）
  - absent = 完全没提甲方
  - 描述式指代：AI 用门店特征描述甲方（"五一广场那家"）时按实际语境判
  - **命中独立于竞争关系与区域档位**（2026-09-05 分界补强）：甲方被列入推荐列表 = recommend，
    即使该列表其他酒店档位低于甲方（AI 把甲方归入低档区域 ≠ 降级推荐）；竞对出现在**其他区域**
    不影响甲方命中——竞对信息只进 same_tier_pushed/answer_tier_distribution；**真劣势只在甲方
    absent（未出现）且同档竞对被推时成立**。
  - **备选区域唯一列出 = 推荐**：AI 用"最推荐/备选/如果住 X"分层时，**每层级的推荐列表都算推荐**；
    甲方在任一推荐列表（含备选区域）作为推荐对象列出 = recommend（如"其他备选区域：五一广场/
    南门兜 → 福州香格里拉"，该区域唯一酒店 = 强推荐，2026-09-05 Kimi hit_friends_generic 误判修正）
- scene：**必须用 AI 回答里甲方所在分块的原始标题**；AI 给每家酒店标注了区域/商圈时，
  **必须用甲方所在的具体区域（dim=region）**，禁止用"题目的筛选条件"当 scene
  （如题目问"亲子房+儿童乐园"是筛选项，不是甲方所在分块——DeepSeek Q7 反例：AI 标了
  "（鼓楼区）"，scene 应判 dim=region val=鼓楼区 rank 1）
  {dim: region/tier/topic/category/budget, val, rank_in_scene, in_scene_count}；absent 时 null。
  **rank_in_scene = 甲方在子场景内第几个被推荐（子场景内唯一 = 1）**，不是"子场景在回答里的
  序号"——DeepSeek Q7 校准教训：鼓楼区是回答里第 5 个被列出的区域、甲方是其内唯一推荐，
  rank_in_scene 应为 1（不是 5）。in_scene_count = 子场景内被推荐的酒店数（唯一 = 1）。
  **自洽硬约束（2026-09-05）**：判了 rank_in_scene≥1 = 甲方被推荐 → recommendation **必须**
  recommend；recommendation 为 mention/exclude/absent 时 scene 必须为 null（不设 rank）。
  **酒店名后的括号位置说明（如"福州香格里拉（五一广场商圈）"）≠ 场景**——场景必须用
  甲方所在**上级分块标题**（DeepSeek Q8 校准教训：原回答分块是"推荐的亲子酒店："，
  括号里的"五一广场商圈"是位置标注，应判 dim=topic val=推荐的亲子酒店，不是 dim=region）。
- referred_content：甲方被引用的差异化内容片段（设施/餐厅/评分/位置优势），通用标签不收。
- has_hotel_recommendations：本题 AI 是否给出酒店推荐——**AI 是否把具体酒店作为推荐对象列出**
  （"推荐 XX 酒店"），含民宿/青旅/公寓（给了可住的住宿推荐即 true）。
  **"提到酒店名作背景/范围说明"不算推荐 → false**（DeepSeek Q16/17 + 文心 Q16 校准教训：AI 推荐
  区域/商圈时说"从如家到世茂洲际都有""高端酒店（聚春园、香格里拉等）""住宿选择多样，例如榕宿青旅
  和邂候青年旅舍""摆渡青年公寓"——**"例如/包括/从…到…"列举住宿选择是背景描述，不是把酒店作为
  推荐对象**；只答区域/商圈/泛建议 + 仅背景列举酒店名 → false）。
- hotels_recommended（推荐名单，2026-09-10 拆分）：AI 作为候选/推荐对象列出的酒店——**必须完整列出
  所有酒店（不只甲方、不只高档）**，它是竞对聚合与真劣势/同档判定的唯一输入；系统查 brand_domains
  派生档位。**背景列举（"例如/包括/从…到…"）不算推荐对象，进 hotels_mentioned**。
- hotels_mentioned（提及名单，新增）：AI 顺嘴提到的酒店（背景/范围说明，如"福州高端酒店有世茂洲际、
  香格里拉等"）——**不进推荐判定、不触发真劣势**，只作竞对发现参考；纯背景列举不影响
  has_hotel_recommendations=true（有明确推荐对象才算 true）。
- **首推/备选分层（2026-09-05 方案 A 裁决）**：AI 明确分"首推/备选"两个推荐列表时——
  scene 按甲方所在层记（dim=topic val=首推/备选），rank_in_scene=该层内排名；
  **首推率只统计甲方在"首推"层的 rank 1**；甲方在"备选"层 = recommend（命中）+ 记录
  rank_in_scene，但**不计入首推率**（避免把次选层首位当核心首选，高估强可见度）。
"""
import asyncio
import json
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import write_measurement
from src.collector.hit_rate import close_measurement
from src.collector.judgment import _HIT_SPEC
from src.collector.judgment_apply import apply_patch, generate_pending
from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode, run_id = sys.argv[1], sys.argv[2]

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        run = await db.get(CollectionRun, run_id)
        if run is None:
            print(f"错误: collection_run {run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        m = dict(run.measurement_json or {})

        if mode == "--generate":
            out = generate_pending(m, include_all="--all" in sys.argv)
            out["city"] = run.city
            out["client_tier"] = (run.positioning_json or {}).get("tier")
            # 嵌入命中判定规范（2026-09-18 固化 _HIT_SPEC，同归因 _ATTRIBUTION_SPEC 自动下发，
            # 主 agent 不再手写 prompt，防 spec 文档-代码漂移再咬人）
            out["spec"] = _HIT_SPEC
            total = sum(len(v) for v in out["platforms"].values())
            # 解析 --out <path>（flags 与位置参数混用，不用 argparse）
            out_path = None
            if "--out" in sys.argv:
                i = sys.argv.index("--out")
                if i + 1 < len(sys.argv):
                    out_path = sys.argv[i + 1]
            if out_path:
                with open(out_path, "w", encoding="utf-8") as fh:
                    json.dump(out, fh, ensure_ascii=False, indent=2)
                print(f"待判清单 {total} 题 → {out_path}")
            else:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            await engine.dispose()
            return

        if mode == "--apply":
            patch_file = sys.argv[3]
            with open(patch_file, encoding="utf-8") as fh:
                patch = json.load(fh)
            if not isinstance(patch, dict):
                print("错误: 判定 JSON 顶层必须是 {平台: {题: 判定}}")
                await engine.dispose()
                sys.exit(1)
            force = "--force" in sys.argv
            client_tier = (run.positioning_json or {}).get("tier")
            applied = apply_patch(m, patch, city=run.city, client_tier=client_tier, force=force)
            # 盖章（spec ⑫ 唯一收口）：close_measurement 一次算齐全部派生字段
            # （命中率/有效可见度/竞对相对可见度/画像），并钉住竞对+负面率输入
            remaining = close_measurement(
                m,
                competitors=(run.positioning_json or {}).get("competitors") or [],
                sentiment=run.sentiment_json or {},
                city=run.city,
                client_tier=(run.positioning_json or {}).get("tier"),
            )
            if remaining > 0:
                print(f"警告: 还有 {remaining} 题未判（recommendation=None），status 保持 partial")
            # 判定=新版本（judge/rejudge），绝不原地覆盖——重判留痕（spec ⑫ 决策②）
            has_snap = (await db.execute(
                select(func.count()).select_from(MeasurementSnapshot)
                .where(MeasurementSnapshot.collection_run_id == run_id)
            )).scalar() > 0
            snap_type = "rejudge" if has_snap else "judge"
            await write_measurement(db, run_id, m, snapshot_type=snap_type)
            await db.commit()
            print(
                f"已判定 {applied} 题并盖章为 {snap_type} 版本，status={m['status']}，"
                f"overall_hit_rate={m['overall']['overall_hit_rate']}，"
                f"miss_structure={m['miss_structure']}"
            )
            await engine.dispose()
            return

        print(f"未知模式 {mode!r}（支持 --generate / --apply）")
        await engine.dispose()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
