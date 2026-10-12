"""P1-② 归因劣势提取测试：pending + apply 校验（pick/dim/type/evidence）+ 接地分类聚合。"""

from src.collector.attribution_extract import (
    apply_attribution, aggregate_attribution, build_client_context, generate_attribution_pending,
    render_gt_facts, _derive_type,
    TYPE_TRUE_DISADVANTAGE, TYPE_CLIENT_HAS_UNREFERENCED,
)


def _attr_judgment(qid, question, answer):
    return {"question_id": qid, "layer": "attribution", "question": question, "answer": answer,
            "reason": "agent_finalized", "attribution_result": None}


def test_generate_pending_only_attribution_and_context():
    m = {
        "content_assets": [{"content": "室内泳池", "count": 3}, {"content": "亲子乐园", "count": 2}],
        "platforms": {
            "deepseek": {"judgments": [
                _attr_judgment("attr_business", "香格里拉和世茂洲际出差住哪家好，为什么", "世茂洲际位置更方便"),
                {"question_id": "hit_business_generic", "layer": "hit", "reason": "agent_finalized"},  # 命中层跳过
            ]},
        },
    }
    out = generate_attribution_pending(m)
    assert "室内泳池" in out["client_context"]          # 甲方已知属性进上下文（接地）
    ds = out["platforms"]["deepseek"]
    assert set(ds) == {"attr_business"}
    assert ds["attr_business"]["scenario"] == "business"


def test_generate_pending_embeds_spec():
    """判定规范随文件下发（2026-09-18 对抗审查修）：spec 自包含，主 agent 不再手贴。"""
    m = {"content_assets": [{"content": "x", "count": 1}], "platforms": {}}
    out = generate_attribution_pending(m)
    spec = out["spec"]
    for k in ("两级接地", "事实清单", "原文佐证", "裁决顺序", "不判「甲方没有」", "不算甲方资产"):
        assert k in spec, f"spec 缺 {k}"
    # 防错警告（2026-09-18 重判实证固化）：条件分流句/竞对优势≠劣势、禁同句重复
    for k in ("条件分流句 ≠ 劣势", "竞对优势 ≠ 劣势", "禁同句重复"):
        assert k in spec, f"spec 缺防错警告 {k}"


def test_apply_attribution_writes_and_validates():
    m = {"platforms": {"deepseek": {"judgments": [
        _attr_judgment("attr_business", "q", "世茂洲际在市中心，香格里拉离地铁远"),
        _attr_judgment("attr_family", "q", "香格里拉亲子设施好"),
    ]}}}
    patch = {"deepseek": {
        "attr_business": {
            "pick": "competitor",
            "client_disadvantage_dims": [
                {"dim": "位置", "corpus_fact": "none", "evidence": "世茂洲际在市中心"},
                {"dim": "设施", "corpus_fact": "refutes", "evidence": "香格里拉有泳池但没提"},
                {"dim": "价格", "evidence": "香格里拉价格更高"},
            ],
            "client_advantage_dims": [{"dim": "价格", "evidence": "香格里拉性价比高"}],
        },
        # 非法：资产类维度缺 corpus_fact → 跳过
        "attr_family": {"pick": "client", "client_disadvantage_dims": [{"dim": "设施", "evidence": "x"}],
                        "client_advantage_dims": []},
    }}
    applied = apply_attribution(m, patch)
    assert applied == 1
    r = m["platforms"]["deepseek"]["judgments"][0]["attribution_result"]
    assert r["pick"] == "competitor"
    # type 由 corpus_fact 确定性派生：none→true / refutes→clie / 价格→true
    assert r["client_disadvantage_dims"][0]["type"] == TYPE_TRUE_DISADVANTAGE
    assert r["client_disadvantage_dims"][1]["type"] == TYPE_CLIENT_HAS_UNREFERENCED
    assert r["client_disadvantage_dims"][2]["type"] == TYPE_TRUE_DISADVANTAGE
    assert r["client_disadvantage_dims"][1]["corpus_fact"] == "refutes"
    # attr_family 因缺 corpus_fact 未回填
    assert m["platforms"]["deepseek"]["judgments"][1]["attribution_result"] is None


def test_derive_type_boundary_cases():
    """U/T 边界确定性派生（2026-09-17 修）：质量批评不得凭"语料有该资产"翻 clie。"""
    # 质量批评（语料只有"存在"，证不了质量）→ true（治"服务响应慢"被误判 clie 的 misfire）
    assert _derive_type("服务", "none") == TYPE_TRUE_DISADVANTAGE
    assert _derive_type("餐饮", "none") == TYPE_TRUE_DISADVANTAGE
    # 存在否定被反 / 同属性具体反证（步行3分钟vs8-12分钟 / 语料有芽宝乐园）→ clie
    assert _derive_type("位置", "refutes") == TYPE_CLIENT_HAS_UNREFERENCED
    assert _derive_type("设施", "refutes") == TYPE_CLIENT_HAS_UNREFERENCED
    # 语料证实 AI（2005年开业证实设施旧）→ true
    assert _derive_type("设施", "confirms") == TYPE_TRUE_DISADVANTAGE
    # 价格/品牌恒 true，无需 corpus_fact
    assert _derive_type("价格", None) == TYPE_TRUE_DISADVANTAGE
    assert _derive_type("品牌", "refutes") == TYPE_TRUE_DISADVANTAGE


def test_apply_attribution_rejects_bad_pick():
    m = {"platforms": {"deepseek": {"judgments": [_attr_judgment("attr_business", "q", "a")]}}}
    patch = {"deepseek": {"attr_business": {"pick": "瞎选", "client_disadvantage_dims": [],
                                            "client_advantage_dims": []}}}
    assert apply_attribution(m, patch) == 0
    assert m["platforms"]["deepseek"]["judgments"][0]["attribution_result"] is None


def test_aggregate_attribution_counts_and_splits_by_type():
    m = {"platforms": {"deepseek": {"judgments": [
        _attr_judgment("attr_business", "q", "x"),
        _attr_judgment("attr_family", "q", "y"),
    ]}}}
    m["platforms"]["deepseek"]["judgments"][0]["attribution_result"] = {
        "pick": "competitor",
        "client_disadvantage_dims": [
            {"dim": "位置", "type": TYPE_TRUE_DISADVANTAGE, "evidence": "市中心"},
            {"dim": "设施", "type": TYPE_CLIENT_HAS_UNREFERENCED, "evidence": "有泳池没提"},
        ],
        "client_advantage_dims": [{"dim": "价格", "evidence": "性价比高"}],
    }
    m["platforms"]["deepseek"]["judgments"][1]["attribution_result"] = {
        "pick": "client",
        "client_disadvantage_dims": [
            {"dim": "位置", "type": TYPE_TRUE_DISADVANTAGE, "evidence": "离地铁远"},
        ],
        "client_advantage_dims": [],
    }
    agg = aggregate_attribution(m)
    assert agg["位置"]["disadvantage"] == 2
    assert agg["位置"]["true_disadvantage"] == 2
    assert agg["设施"]["client_has_unreferenced"] == 1   # 接地分类单独计数
    assert agg["价格"]["advantage"] == 1
    assert "服务" not in agg                          # 无计数维度不输出


def test_generate_pending_includes_grounding_corpus():
    # 接地语料（2026-09-14 方案A）：甲方页面全文进 client_context；content_assets 仍作补充
    m = {"content_assets": [{"content": "老牌五星", "count": 1}], "platforms": {}}
    corpus = "[T0 官网/官方] 设施齐全健体中心，包含室内恒温泳池。\n[T1 OTA平台] 福州香格里拉距长乐机场45分钟。"
    out = generate_attribution_pending(m, grounding_corpus=corpus)
    joined = "\n".join(out["client_context"])
    assert "室内恒温泳池" in joined           # 甲方页面全文入接地
    assert "甲方页面内容" in joined            # 接地语料段存在
    assert "信源" in joined                    # 标注可信度（tier 图例）
    assert "老牌五星" in out["client_context"]  # content_assets 仍作补充


def test_render_gt_facts_formats_tier_source_kind():
    """事实清单渲染（2026-09-18 架构）：来源 URL / 未单页溯源 / 时间戳 都标出。"""
    facts = {"facts": {"餐饮": [
        {"fact": "江南灶·融府（米其林一星）", "source_tier": "T0",
         "source_url": "https://www.shangri-la.com/cn/fuzhou/shangrila/",
         "captured_at": "2026-09-18", "source_kind": "corpus"},
        {"fact": "韩香馆（已停业）", "source_tier": "T1",
         "captured_at": "2026-09-18", "source_kind": "verified"},
    ]}}
    out = render_gt_facts(facts)
    assert out[0].startswith("【甲方事实清单")
    assert any("[T0]" in l and "江南灶·融府（米其林一星）" in l and "来源:https" in l for l in out)
    assert any("[T1]" in l and "韩香馆（已停业）" in l and "未单页溯源" in l for l in out)
    assert any("核验:2026-09-18" in l for l in out)


def test_render_gt_facts_empty_inputs():
    assert render_gt_facts(None) == []
    assert render_gt_facts({}) == []
    assert render_gt_facts({"facts": {}}) == []
    assert render_gt_facts({"facts": {"餐饮": [{"source_tier": "T0"}]}}) == []  # 无 fact 文本


def test_build_client_context_two_tier_grounding_order():
    """两级接地（2026-09-18 架构）：事实清单（判决第一依据）在前，原文佐证第二。"""
    facts = {"facts": {"餐饮": [{"fact": "江南灶·融府", "source_tier": "T0", "source_kind": "corpus"}]}}
    m = {"content_assets": [], "tier": "高端"}
    ctx = build_client_context(m, grounding_corpus="[T0] 官网正文", gt_facts=facts)
    assert ctx[0].startswith("【甲方事实清单")       # 判决依据第一
    assert "江南灶·融府" in ctx[1]                  # 清单条目
    joined = "\n".join(ctx)
    assert "甲方页面内容" in joined                  # 原文佐证仍保留
    assert "原文佐证" in joined
    assert "未提到≠没有" in joined                   # 三态裁决语义
    assert "不判「甲方没有」" in joined
    assert "AI 声称但此处无" not in joined           # 旧"不算甲方资产"表述已替换为未证实语义
