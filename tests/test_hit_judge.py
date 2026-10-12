"""命中判定器测试：列表式确定性 + 动态 N + 自然段式主 agent 标记。"""
from src.collector.hit_judge import judge, prefill


def test_list_hit_first_rank():
    r = judge("1. 香格里拉\n2. 希尔顿\n3. 万豪", "香格里拉")
    assert r == {"needs_agent": False, "hit": True, "rank": 1, "brand_count": 3}


def test_list_hit_third_rank():
    r = judge("1. 希尔顿\n2. 万豪\n3. 香格里拉", "香格里拉")
    assert r["hit"] is True
    assert r["rank"] == 3


def test_list_not_mentioned():
    r = judge("1. 希尔顿\n2. 万豪\n3. 凯宾斯基", "香格里拉")
    assert r == {"needs_agent": False, "hit": False, "rank": None, "brand_count": 3}


def test_dynamic_n_small_list():
    # 只有 3 项，N=3（不是 8），甲方第 3 仍命中
    r = judge("1. 希尔顿\n2. 万豪\n3. 香格里拉", "香格里拉")
    assert r["brand_count"] == 3
    assert r["hit"] is True


def test_rank_beyond_n_8():
    # 9 项，N=8，甲方第 9 → 提到但靠后，不算命中
    answer = "1. 品牌1\n2. 品牌2\n3. 品牌3\n4. 品牌4\n5. 品牌5\n6. 品牌6\n7. 品牌7\n8. 品牌8\n9. 香格里拉"
    r = judge(answer, "香格里拉")
    assert r["hit"] is False
    assert r["rank"] == 9
    assert r["brand_count"] == 9


def test_natural_paragraph_needs_agent():
    r = judge("推荐希尔顿、万豪，还有香格里拉也不错", "香格里拉")
    assert r["needs_agent"] is True
    assert r["hit"] is None


def test_english_brand_match():
    r = judge("1. Shangri-La\n2. Hilton", "香格里拉", "Shangri-La")
    assert r["hit"] is True
    assert r["rank"] == 1


def test_circle_number_markers():
    r = judge("①香格里拉 ②希尔顿 ③万豪", "香格里拉")
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 1


def test_single_item_list_hit():
    # AI 只列一家「1. 香格里拉」= 强烈推荐 = 命中 rank 1
    r = judge("1. 香格里拉", "香格里拉")
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 1
    assert r["brand_count"] == 1


def test_markdown_heading_number_list():
    # 真实 AI 回答「### 2. 香格里拉」Markdown 标题序号 → 列表式，rank 2
    r = judge("### 1. 悦华酒店\n### 2. 福州香格里拉大酒店\n### 3. 希尔顿", "香格里拉")
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 2
    assert r["brand_count"] == 3


def test_dash_bullet_list():
    # 项目符号列表 → 列表式，rank 2
    r = judge("- 悦华酒店\n- 福州香格里拉大酒店\n- 希尔顿", "香格里拉")
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 2


def test_single_dash_is_natural_paragraph():
    # 只有 1 个项目符号（可能破折号）→ 自然段式
    r = judge("- 福州出差推荐市中心酒店，交通方便", "香格里拉")
    assert r["needs_agent"] is True


def test_bullet_dot_list():
    # • 项目符号列表
    r = judge("• 悦华酒店\n• 香格里拉\n• 希尔顿", "香格里拉")
    assert r["needs_agent"] is False
    assert r["rank"] == 2


def test_markdown_table_needs_agent():
    # Markdown 表格 → needs_agent（排名语义需主 agent 判，不武断 miss）
    r = judge("| 酒店 | 位置 | 价格 |\n|:---|:---|:---|\n| 悦华酒店 | 五四路 | ¥470 |\n| 香格里拉 | 五一广场 | ¥900 |", "香格里拉")
    assert r["needs_agent"] is True
    assert r["reason"] == "table"


def test_markdown_bold_number_list():
    # 回归 2026-09-04 真实 Q6：AI 用 markdown 粗体序号「**1. 福州香格里拉大酒店** ⭐ 综合最推荐」——
    # _LIST_MARKER 原不识别 ** 前缀，甲方整段被吞、静默漏判。粗体序号须识别为列表。
    r = judge(
        "**1. 福州香格里拉大酒店** ⭐ 综合最推荐\n五一广场核心商圈，步行可达南门兜地铁站\n"
        "**2. 福州世茂洲际酒店**\n茶亭公园旁\n**3. 福州悦华酒店（西湖公园店）**\n就在西湖公园旁",
        "香格里拉",
    )
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 1
    assert r["brand_count"] == 3


def test_markdown_bold_number_client_middle():
    # 粗体序号列表，甲方在中段（第 2 项）→ rank 2
    r = judge(
        "**1. 福州世茂洲际酒店**\n茶亭公园旁\n**2. 福州香格里拉大酒店** ⭐\n五一广场\n**3. 福州悦华酒店（西湖公园店）**\n西湖公园旁",
        "香格里拉",
    )
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 2
    assert r["brand_count"] == 3


def test_blocked_list_attr_labels():
    # 分块式：有列表标记（**N. **）但 items 开头是属性标签（景点密集/交通便利/吃饭方便）
    # → 非简单列表，扁平 rank 因标题占位不可靠（甲方实为"交通便利"块内首推却数成 rank4）→ needs_agent
    r = judge(
        "**1. 景点密集**：三坊七巷、东街口\n**2. 交通便利**：东街口、南门兜\n**3. 吃饭方便**：商圈成熟\n**4. 福州香格里拉**（五一广场）",
        "香格里拉",
    )
    assert r["needs_agent"] is True
    assert r["reason"] == "blocked"


def test_blocked_list_scene_labels():
    # 分块式：场景首选标签（追求…首选/江景…首选）→ needs_agent
    r = judge(
        "**1. 追求市中心地道福州味首选**：福州香格里拉\n**2. 江景+年轻潮逛商圈首选**：福州世茂洲际酒店\n**3. 热闹综合体+性价比高端首选**：福州泰禾凯宾斯基酒店",
        "香格里拉",
    )
    assert r["needs_agent"] is True
    assert r["reason"] == "blocked"


def test_simple_list_with_hotel_terms_keeps_rank():
    # 简单列表（items 开头是酒店名含特征词）→ 仍确定性判定 rank
    r = judge(
        "**1. 福州香格里拉大酒店**：自助餐\n**2. 福建外贸中心悦华酒店（三坊七巷店）**\n**3. 福州泰禾铂尔曼酒店**",
        "香格里拉",
    )
    assert r["needs_agent"] is False
    assert r["hit"] is True
    assert r["rank"] == 1


def test_prefill_table():
    p = prefill("| 酒店 | 价格 |\n|:---|:---|\n| 香格里拉 | 900 |", "香格里拉")
    assert p["answer_form"] == "table"
    assert p["simple"] is None
    assert p["client_present"] is True
    assert p["client_rank"] is None


def test_prefill_prose():
    p = prefill("推荐希尔顿、万豪，还有香格里拉也不错", "香格里拉")
    assert p["answer_form"] == "prose"
    assert p["simple"] is None
    assert p["client_present"] is True


def test_prefill_blocked():
    # 分块式：answer_form=list 但 simple=False（需子 agent 判 scene）
    p = prefill(
        "**1. 景点密集**：三坊七巷\n**2. 交通便利**：东街口\n**3. 吃饭方便**：商圈成熟\n**4. 福州香格里拉**（五一广场）",
        "香格里拉",
    )
    assert p["answer_form"] == "list"
    assert p["simple"] is False
    assert p["client_present"] is True
    assert p["client_rank"] is None
    assert p["item_count"] == 4


def test_prefill_simple_list_rank():
    p = prefill(
        "**1. 福州世茂洲际酒店**\n**2. 福州香格里拉大酒店**\n**3. 福州悦华酒店**",
        "香格里拉",
    )
    assert p["answer_form"] == "list"
    assert p["simple"] is True
    assert p["client_rank"] == 2
    assert p["item_count"] == 3


def test_prefill_simple_list_no_client():
    p = prefill("1. 福州世茂洲际酒店\n2. 福州悦华酒店", "香格里拉")
    assert p["simple"] is True
    assert p["client_rank"] is None
    assert p["client_present"] is False
