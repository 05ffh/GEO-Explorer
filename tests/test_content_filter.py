"""正文过滤测试（GT 正文分层）：去噪 + 抽属性 + 高召回。"""

from src.collector.content_filter import filter_client_facts


def test_keeps_attribute_facts():
    raw = "\n".join([
        "福州香格里拉设有414间宽敞明亮的豪华客房和套房，面积约从39平方米到237平方米不等。",
        "设施齐全健体中心，包含室内恒温泳池。",
        "江南灶·融府，福建省米其林一星餐厅。",
        "距福州长乐国际机场仅45分钟路程。",
    ])
    out = filter_client_facts(raw)
    assert "414间" in out
    assert "室内恒温泳池" in out
    assert "米其林一星" in out
    assert "机场" in out


def test_drops_noise():
    raw = "\n".join([
        "[信息&价格](https://x.com/a#1)",           # 纯链接行
        "* 2位成人 · 0名儿童 · 1间客房",              # 下单 UI
        "Kanak-kanak berumur 7–11 tahun CNY 70",   # 非中文
        "选择入住人数",                              # 短 nav（无属性词）
        "福州香格里拉大酒店位于福州市中心。",          # 保留
    ])
    out = filter_client_facts(raw)
    assert "信息&价格" not in out
    assert "位成人" not in out
    assert "Kanak-kanak" not in out
    assert "选择入住人数" not in out
    assert "位于福州市中心" in out


def test_dedup():
    raw = "室内恒温泳池\n室内恒温泳池\n室内恒温泳池"
    assert filter_client_facts(raw).count("室内恒温泳池") == 1


def test_high_recall_long_line_without_keyword():
    # 高召回：不含属性关键词但较长的实质行也保留
    raw = "这家酒店经过全面翻新后呈现出现代雅致的整体风格与服务体验"
    assert filter_client_facts(raw) != ""


def test_keeps_short_facility_names_and_english_with_unit():
    # 2026-09-14 修：OTA 设施列表是短行、英文距离带中文单位——都是真事实，须保留（旧版误丢 395 行）
    raw = "\n".join([
        "室内泳池",
        "健身房",
        "桑拿",
        "行政樓層",
        "接站服務",
        "Fuzhou Changle International Airport 45 公里",
        "入住 14:00 | 退房 12:00",
        "Kanak-kanak berumur 7–11 tahun CNY 70",   # 纯外文重复——丢
    ])
    out = filter_client_facts(raw)
    assert "室内泳池" in out          # 短设施名保留
    assert "健身房" in out
    assert "行政楼层" in out          # 繁体已转简体（2026-09-18 繁→简链路改造）
    assert "行政樓層" not in out      # 繁体不再保留
    assert "接站服务" in out          # 繁体→简体
    assert "45 公里" in out           # 英文带中文单位保留
    assert "Kanak-kanak" not in out   # 纯外文重复丢弃


def test_to_simplified_converts_traditional():
    # 2026-09-18 繁→简链路改造：境外 OTA（agoda/trip hk-tw/booking）繁体界面统一转简体
    from src.collector.content_filter import to_simplified
    src = "位於福州市鼓樓區新權南路9號，毗鄰五一廣場，步行至地鐵南門兜站約5分鐘。行政樓層"
    out = to_simplified(src)
    assert out == "位于福州市鼓楼区新权南路9号，毗邻五一广场，步行至地铁南门兜站约5分钟。行政楼层"
    assert to_simplified("简体输入幂等") == "简体输入幂等"


def test_drops_link_clusters():
    # 链接簇行（≥2 个 markdown 链接 = 导航/footer，每页重复白吃语料预算）丢弃
    raw = "\n".join([
        "[我们的目的地](https://x/a)[查找预订](https://x/b)[会议与宴会](https://x/c)",
        "福州香格里拉设有414间豪华客房。",
    ])
    out = filter_client_facts(raw)
    assert "我们的目的地" not in out
    assert "414间" in out


def test_booking_ui_tokens_do_not_kill_real_facts():
    # 2026-09-15 修：间客房/位成人/名儿童 裸子串曾把真事实当预订框误删（库中真实行回归）
    raw = "\n".join([
        "414间客房与套房，均可俯瞰乌山和于山的醉人美景",        # 客房数+景观事实
        "最多入住4位成人，最多入住2位儿童，最多入住总人数6人",   # 容量政策
        "每2晚由**USD 209**起",                              # 价格（带粗体标记）
        "414间客房",                                          # 单段客房数不应触发选择器
    ])
    out = filter_client_facts(raw)
    assert "414间客房与套房" in out
    assert "最多入住" in out
    assert "USD 209" in out
    assert "414间客房" in out


def test_keeps_cny_symbol_price_short_line():
    # 2026-10-10：¥价格行汉字少也留（CDP OTA 政策价 "¥70/人"）；纯外文行（CNY 在马来句里）仍丢
    out = filter_client_facts("7-11岁儿童\n¥70/人\nKanak-kanak berumur 7–11 tahun CNY 70")
    assert "¥70/人" in out
    assert "Kanak-kanak" not in out


def test_booking_widget_still_dropped():
    # 真正的整行选择器（≥2 段）仍丢
    raw = "\n".join([
        "2位成人 · 0名儿童 · 1间客房",
        "1間房, 2位成人, 0位小童",
        "选择入住人数",
    ])
    out = filter_client_facts(raw)
    assert "位成人" not in out
    assert "間房" not in out
    assert "选择入住" not in out
