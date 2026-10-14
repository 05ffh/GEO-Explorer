"""fetch_ota_cdp 纯函数单测：区块切分（同程新增的空标题丢弃 / 边界计数归一 / emit_heading / drop_lines）。"""
import json

from scripts.fetch_ota_cdp import (
    segment, build_content_text, _norm_name, SPECS,
    _drop_room_lines, _render_room_cards,
)


def test_norm_name_strips_count():
    assert _norm_name("用户点评 (11244)") == "用户点评"
    assert _norm_name("用户点评 ( 8 )") == "用户点评"
    assert _norm_name("酒店介绍") == "酒店介绍"
    assert _norm_name("") == ""


def test_segment_drops_empty_nav_regions():
    # 同程 nav 用无文字的 h 标签，Range 会吞进站点导航 → 空标题区块必须丢弃。
    regions = [
        {"name": "", "text": "国内景点\n周边跟团游\n定制旅行"},
        {"name": "鼓楼区新权南路9号", "text": "在地图上显示"},
        {"name": "用户点评 (11244)", "text": "4.6 很好\n全部房型"},
        {"name": "点评正文", "text": "设施老旧"},
    ]
    spec = {"default_type": "fact", "emit_heading": True,
            "boundaries": [("用户点评", "opinion", {})]}
    segs = segment(regions, spec)
    assert [t for t, _ in segs] == ["fact", "opinion"]
    fact, opinion = segs[0][1], segs[1][1]
    assert "国内景点" not in fact            # 空标题导航被丢
    assert "鼓楼区新权南路9号" in fact        # 非边界标题文字保留（emit_heading）
    assert "设施老旧" in opinion             # 点评正文归 opinion 段


def test_segment_emit_heading_only_for_non_boundary():
    # 同程部分事实写在 H3 标题里（标题之后为空）→ 非边界标题文字入段；边界标题（区块名）不入。
    regions = [
        {"name": "入住政策", "text": ""},
        {"name": "入住时间：14:00后 退房时间：12:00前", "text": ""},
    ]
    spec = {"default_type": "fact", "emit_heading": True,
            "boundaries": [("入住政策", "fact", {})]}
    segs = segment(regions, spec)
    assert [(t, txt.strip()) for t, txt in segs] == [("fact", "入住时间：14:00后 退房时间：12:00前")]


def test_segment_emit_heading_off_by_default():
    # 携程不设 emit_heading → 非边界标题文字不入段（保持既有行为）。
    regions = [{"name": "子标题", "text": "事实行"}]
    spec = {"default_type": "fact", "boundaries": []}
    assert segment(regions, spec) == [("fact", "事实行")]


def test_build_content_text_drop_lines():
    # drop_lines 只在平台内生效：同一输入，设与不设 drop_lines 的差异即证。
    regions = [{"name": "服务与设施",
                "text": "室内泳池\n免费\n划线价格指由商品提供方提供的参考价门市价建议公示价"}]
    base = {"default_type": "fact", "boundaries": [("服务与设施", "fact", {})]}
    ct_without, _ = build_content_text(regions, {**base, "drop_lines": []}, None)
    ct_with, _ = build_content_text(regions, {**base, "drop_lines": [r"^划线价格指"]}, None)
    assert "划线价格" in ct_without
    assert "划线价格" not in ct_with
    assert "室内泳池免费" in ct_with          # 正常事实不被误删


def test_tongcheng_spec_shape():
    spec = SPECS["tongcheng"]
    assert spec["domain"] == "ly.com"
    assert spec["emit_heading"] is True
    assert "extract_js" in spec and "room_cards_js" in spec  # 同程专属 DOM JS（与携程分开）
    assert spec["hotel_id_re"] == r"hotelId=(\d+)"
    names = [b[0] for b in spec["boundaries"]]
    assert names == ["用户点评", "酒店介绍", "订房必读", "入住政策", "服务与设施", "最近浏览", "附近的酒店"]
    assert SPECS["ctrip"]["hotel_id_re"] == r"/hotels?/(\d+)\.html"


def test_fliggy_spec_shape():
    spec = SPECS["fliggy"]
    assert spec["domain"] == "alitrip.com"          # 实际域名（非 hotel.fliggy.com）
    assert spec["hotel_id_re"] == r"shid=(\d+)"
    assert "room_cards_js" in spec and "extract_js" in spec  # 飞猪专属房型卡 JS + 星级注入抽取器
    assert "replace_lines" in spec                          # 地址行「城市市+街道号」重写
    assert "{city}" in spec["wait_for"]                      # wait_for 城市无关（运行时格式化）
    names = [b[0] for b in spec["boundaries"]]
    assert names == ["酒店介绍", "设施与服务", "交通及周边", "住客评价"]  # 无城市硬编码


def test_specs_are_city_and_hotel_agnostic():
    # 换城市/换酒店可复用的守卫：SPECS 内不得出现硬编码城市/酒店名（wait_for 用 {city} 占位）。
    for p, s in SPECS.items():
        blob = json.dumps(s, ensure_ascii=False)
        for bad in ("福州", "香格里拉", "新权南路", "鼓楼"):
            assert bad not in blob, f"{p} SPECS 含硬编码 {bad!r}"


def test_drop_room_lines_prefix_and_space():
    # 飞猪卖方报价区：裸房名（卡片名前缀）+ 双空格变体 → 都要丢；正常事实保留。
    names = {"豪华大床房-尽览榕城繁华城景", "豪华双床房 城市景观"}
    txt = "豪华大床房\n豪华双床房  城市景观\n室内泳池免费\n豪华大床房-尽览榕城繁华城景"
    out = _drop_room_lines(txt, names).split("\n")
    assert "豪华大床房" not in out            # 裸房名（前缀匹配）
    assert "豪华双床房  城市景观" not in out   # 双空格变体（去空格归一）
    assert "豪华大床房-尽览榕城繁华城景" not in out
    assert "室内泳池免费" in out             # 正常事实不被误删


def test_build_content_text_replace_lines():
    # replace_lines 只在平台内生效：飞猪地址行「街道号，地标, 城市」→「城市市+街道号」（对齐口径）。
    regions = [{"name": "酒店介绍", "text": "新权南路9号 ，五一广场旁 , 福州\n酒店设有414间客房"}]
    base = {"default_type": "fact", "boundaries": [("酒店介绍", "fact", {})]}
    ct, _ = build_content_text(regions, {**base, "replace_lines": [
        (r"^(\S+?号)\s*[，,]\s*\S+?\s*[，,]\s*(\S+?)\s*$", r"\2市\1")]}, None)
    assert "福州市新权南路9号" in ct          # 地址行重写
    assert "五一广场旁" not in ct              # 地标（非正式地址成分）已去
    assert "414间客房" in ct                   # 非地址行不受影响


def test_find_verified_tab():
    from scripts.fetch_ota_cdp import _find_verified_tab
    tabs = [
        {"type": "page", "url": "https://hotels.ctrip.com/hotels/429558.html",
         "title": "福州香格里拉大酒店预订价格,联系电话位置地址【携程酒店】"},
        {"type": "page", "url": "https://www.ly.com/hotel/hoteldetail?hotelId=51402044",
         "title": "福州世茂洲际酒店,地址：台江区广达路108号【同程酒店】"},
        {"type": "page", "url": "https://hotel.alitrip.com/hotel_detail2.htm?shid=10015487",
         "title": "福州香格里拉大酒店预订,福州香格里拉大酒店价格,点评"},
    ]
    # 命中：域名+标题含品牌+城市
    assert _find_verified_tab("ctrip.com", "香格里拉", "福州", tabs)["url"].endswith("429558.html")
    assert "51402044" in _find_verified_tab("ly.com", "世茂洲际", "福州", tabs)["url"]
    # 同域但错酒店（标题是世茂洲际）→ None（不抓错酒店）
    assert _find_verified_tab("ly.com", "香格里拉", "福州", tabs) is None
    # 错城市 / 错品牌 → None
    assert _find_verified_tab("ctrip.com", "香格里拉", "上海", tabs) is None
    assert _find_verified_tab("ctrip.com", "不存在的酒店", "福州", tabs) is None
    # 域名不匹配 → None
    assert _find_verified_tab("meituan.com", "香格里拉", "福州", tabs) is None


def test_render_room_cards_spec_override():
    # 飞猪用 spec 单字段（床型｜面积｜楼层｜窗型）；携程/同程无 spec → 回退 bed｜area。
    out = _render_room_cards([
        {"name": "豪华大床房", "price": "¥524", "spec": "1张特大床(2M)｜40㎡｜6-20层｜有窗"},
        {"name": "高级大床房", "price": "¥593", "bed": "特大床", "area": "40㎡"},
    ]).split("\n")
    assert out[0] == "豪华大床房 ¥524（1张特大床(2M)｜40㎡｜6-20层｜有窗）"
    assert out[1] == "高级大床房 ¥593（特大床｜40㎡）"
