"""酒旅信源 tier 判定测试。"""

from src.gt.source_tier import classify_source_tier


class TestClassifySourceTier:

    def test_government_is_t0(self):
        assert classify_source_tier("http://www.mct.gov.cn/xxx") == "T0"
        assert classify_source_tier("https://fgw.lasa.gov.cn/xxx") == "T0"

    def test_ota_is_t1(self):
        assert classify_source_tier("https://hotels.ctrip.com/hotels/429562.html") == "T1"
        assert classify_source_tier("https://tw.trip.com/hotels/guangzhou-429562/") == "T1"
        assert classify_source_tier("https://www.agoda.cn/shangri-la-hotel-guangzhou/") == "T1"
        assert classify_source_tier("https://www.elong.com/hotel/hoteldetail") == "T1"
        assert classify_source_tier("https://www.wingontravel.com/hotel/detail") == "T1"

    def test_review_is_t2(self):
        assert classify_source_tier("https://www.dianping.com/shop/xxx") == "T2"
        assert classify_source_tier("https://www.mafengwo.cn/poi/xxx") == "T2"

    def test_ugc_is_t3(self):
        assert classify_source_tier("https://www.xiaohongshu.com/note/xxx") == "T3"
        assert classify_source_tier("https://baike.baidu.com/item/xxx") == "T3"
        assert classify_source_tier("https://www.zhihu.com/question/xxx") == "T3"

    def test_empty_or_unknown_is_t3(self):
        assert classify_source_tier("") == "T3"
        # 不传品牌名，无法判定品牌官网 → T3
        assert classify_source_tier("https://www.shangri-la.com/guangzhou/") == "T3"

    def test_brand_domain_is_t0(self):
        """传品牌名时，域名含品牌英文名 → T0（官网）。"""
        assert classify_source_tier("https://www.shangri-la.com/guangzhou/", "香格里拉") == "T0"
        assert classify_source_tier("https://www.hilton.com/zh-cn/", "希尔顿") == "T0"
        assert classify_source_tier("https://www.atour.com/", "亚朵") == "T0"
