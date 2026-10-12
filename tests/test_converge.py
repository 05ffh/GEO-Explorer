"""复测收敛测试：converge 纯逻辑（L1 CI / L2 稳定与平台分布 / 停止判据 / 翻转）+ remeasure 分层合并。"""

import scripts.converge as conv
from scripts.remeasure import merge_round_measurements


def _hit(qid, reco):
    return {"question_id": qid, "layer": "hit", "has_hotel_recommendations": True,
            "recommendation": reco, "reason": "agent_finalized"}


def _attr(qid, dim, typ, ev="x"):
    return {"question_id": qid, "layer": "attribution",
            "attribution_result": {"client_disadvantage_dims": [{"dim": dim, "type": typ, "evidence": ev}]}}


def _round(plat_judgments):
    return {"platforms": {pl: {"judgments": js} for pl, js in plat_judgments.items()}}


def test_l1_hit_rate_ci():
    qids = [f"q{i}" for i in range(25)]
    rounds = [_round({"doubao": [_hit(q, "recommend") for q in qids]}) for _ in range(3)]
    c = conv.compute_convergence(rounds)
    h = c["platforms_hit_rate"]["doubao"]
    assert h["hit_rate"] == 1.0 and h["rounds"] == 3 and h["ci_half"] == 0.0
    assert c["stop"]["ci_met"] is True


def test_l1_mixed_rates_per_platform():
    rounds = []
    for _ in range(3):
        dj = [_hit(f"q{i}", "recommend") for i in range(10)] + [_hit(f"q{i}", "mention") for i in range(10, 25)]
        kj = [_hit(f"q{i}", "recommend") for i in range(20)] + [_hit(f"q{i}", "absent") for i in range(20, 25)]
        rounds.append(_round({"doubao": dj, "deepseek": kj}))
    c = conv.compute_convergence(rounds)
    assert c["platforms_hit_rate"]["doubao"]["hit_rate"] == round(10 / 25, 4)
    assert c["platforms_hit_rate"]["deepseek"]["hit_rate"] == round(20 / 25, 4)
    assert c["platforms_hit_rate"]["deepseek"]["rounds"] == 3


def test_l2_stability_and_platform_distribution():
    un = "client_has_unreferenced"
    tr = "true_disadvantage"
    rounds = [
        _round({"doubao": [_attr("attr_business", "设施", un)], "deepseek": [_attr("attr_business", "设施", un)]}),
        _round({"doubao": [_attr("attr_business", "设施", un)], "deepseek": [_attr("attr_business", "设施", un)]}),
        _round({"doubao": [_attr("attr_business", "设施", tr)], "deepseek": [_attr("attr_business", "设施", un)]}),
    ]
    c = conv.compute_convergence(rounds)
    ds = c["decision_sets"]["client_has_unreferenced"]
    items = ds["设施"]
    assert any(d["question_id"] == "attr_business" and d["status"] == "stable" for d in items)
    d = next(d for d in items if d["question_id"] == "attr_business")
    assert d["types"] == {un: 5, tr: 1}
    assert d["best_type"] == un and d["best_ratio"] == round(5 / 6, 3)
    assert set(d["platforms"][un]) == {"doubao", "deepseek"}   # 平台分布标注


def test_verdict_converged_at_fixed_point():
    qids = [f"q{i}" for i in range(25)]
    rounds = [_round({"doubao": [_hit(q, "recommend") for q in qids]}) for _ in range(3)]
    c = conv.compute_convergence(rounds)
    assert c["stop"]["fixed_point"] is True
    assert c["stop"]["verdict"] == "converged"


def test_verdict_unstable_when_flips():
    rounds = []
    for r in range(3):
        js = []
        for i in range(3):
            if r in (i, (i + 1) % 3):
                typ = "true_disadvantage" if r == i else "client_has_unreferenced"
                js.append(_attr(f"a{i}", "设施", typ))
        rounds.append(_round({"doubao": js}))
    c = conv.compute_convergence(rounds)
    assert c["stop"]["verdict"] == "unstable"
    assert c["flip_rate"] > 0.2


def test_hit_flip_unstable():
    # 命中层推荐状态跨轮翻转多 → hit_flip_rate > gate → unstable（回答结论翻转过多）
    qids = [f"q{i}" for i in range(25)]
    r1 = _round({"doubao": [_hit(q, "recommend" if i % 2 == 0 else "absent") for i, q in enumerate(qids)]})
    r2 = _round({"doubao": [_hit(q, "absent" if i % 2 == 0 else "recommend") for i, q in enumerate(qids)]})
    r3 = _round({"doubao": [_hit(q, "recommend" if i % 2 == 0 else "absent") for i, q in enumerate(qids)]})
    c = conv.compute_convergence([r1, r2, r3])
    assert c["hit_flip_rate"] == 1.0
    assert c["stop"]["verdict"] == "unstable"


def test_converged_on_fixed_point_without_ci():
    # 判据重构（2026-09-16）：不动点成立但 CI 未达标（p≈0.5 波动平台，±10pp 物理不可达）
    # → 仍 converged——CI 是辅助精度标注，不阻塞收敛；收敛=结论不翻转
    qids = [f"q{i}" for i in range(25)]
    rounds = []
    for _ in range(3):
        js = [_hit(q, "recommend" if i % 2 == 0 else "absent") for i, q in enumerate(qids)]
        rounds.append(_round({"doubao": js}))
    c = conv.compute_convergence(rounds)
    assert c["stop"]["fixed_point"] is True
    assert c["stop"]["ci_met"] is False      # CI 半宽 0.113 > 0.10 未达标
    assert c["hit_flip_rate"] == 0.0          # 但每题跨轮推荐状态完全一致
    assert c["stop"]["verdict"] == "converged"


def test_single_appearance_not_stable():
    # 只出现 1 次的维度不得判稳定（分母=总判定次数，对抗审查 2026-09-15 修）
    un = "client_has_unreferenced"
    rounds = [
        _round({"doubao": [_attr("attr_business", "设施", un)]}),
        _round({"doubao": [_attr("attr_business", "餐饮", un)]}),
        _round({"doubao": [_attr("attr_business", "餐饮", un)]}),
    ]
    c = conv.compute_convergence(rounds)
    ds = c["decision_sets"]
    assert not ds["client_has_unreferenced"].get("设施")            # 设施 1/3 → 未成信号
    assert ds["client_has_unreferenced"].get("餐饮")                 # 餐饮 2/3 → 稳定
    assert any(d["dim"] == "设施" and d["status"] == "absent" for d in ds["absent"])


def test_drift_flag_when_last_differs():
    qids = [f"q{i}" for i in range(25)]
    r1 = _round({"doubao": [_hit(q, "recommend") for q in qids]})
    r2 = _round({"doubao": [_hit(q, "absent") for q in qids]})
    c = conv.compute_convergence([r1, r2])
    assert c["drift"]["doubao"]["flag"] is True  # 1.0 vs 0.0 差 > 2×CI


def test_l1_stable_platform_hit_single_round():
    # 对抗审查 2026-09-16：稳定平台（DS/Kimi）轮2/3 命中层沿用轮1（merge 复制），
    # converge L1 只统计真正重采过命中层的轮次——复制样本不得被当独立样本拉虚 CI。
    hit_qids = [f"h{i}" for i in range(25)]
    attr_qids = [f"a{i}" for i in range(10)]

    def hit(qid, reco):
        return {"question_id": qid, "layer": "hit", "has_hotel_recommendations": True,
                "recommendation": reco, "reason": "agent_finalized"}

    def attr(qid):
        return {"question_id": qid, "layer": "attribution",
                "attribution_result": {"client_disadvantage_dims": [{"dim": "设施", "type": "true_disadvantage", "evidence": "e"}]}}

    r1 = {"platforms": {"deepseek": {"judgments":
          [hit(q, "recommend" if i % 2 == 0 else "absent") for i, q in enumerate(hit_qids)]
          + [attr(q) for q in attr_qids]}}}
    rounds = [r1]
    for rn in (2, 3):   # 轮2/3 只采归因层，命中层沿用轮1
        m = merge_round_measurements(r1, {"deepseek": {"judgments": [attr(q) for q in attr_qids], "agent_notes": ""}},
                                     {"deepseek": ("attribution",)}, rn, ["fp"], "2026-01-01")
        rounds.append(m)
    c = conv.compute_convergence(rounds)
    ds = c["platforms_hit_rate"]["deepseek"]
    assert ds["rounds"] == 1, ds                 # 命中层只采 1 轮（轮1），轮2/3 复制不计
    assert ds["samples"] == 25, ds
    assert ds["round_rates"] == [0.52], ds       # 单条真实轮次，无 0.52/0.52/0.52 复制
    assert c["stop"]["ci_met"] is True           # 无波动平台重测 → 达标恒真（不受稳定平台污染）


def test_merge_keeps_uncollected_layer():
    existing = {"platforms": {"deepseek": {"judgments": [
        _hit("h1", "recommend"),
        _attr("a1", "设施", "true_disadvantage", "old"),
    ]}}}
    results = {"deepseek": {"judgments": [_attr("a1", "设施", "client_has_unreferenced", "new")], "agent_notes": ""}}
    m = merge_round_measurements(existing, results, {"deepseek": ("attribution",)}, 2, ["fp"], "2026-01-01T00:00:00")
    js = m["platforms"]["deepseek"]["judgments"]
    qids = [j["question_id"] for j in js]
    assert "h1" in qids                                        # 命中层保留（稳定平台沿用第 1 轮）
    assert js[qids.index("a1")]["attribution_result"]["client_disadvantage_dims"][0]["type"] == "client_has_unreferenced"
    assert m["round_no"] == 2 and m["question_fingerprint"] == ["fp"]
