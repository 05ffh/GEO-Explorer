"""P1-2 — Industry Classifier Tests."""
from src.services.industry_classifier import classify_industry, INDUSTRY_SIGNALS


class TestIndustrySignals:
    def test_all_15_industries_have_signals(self):
        assert len(INDUSTRY_SIGNALS) == 15

    def test_each_industry_has_product_keywords(self):
        for slug, signals in INDUSTRY_SIGNALS.items():
            assert len(signals.get("product_keywords", [])) >= 5, f"{slug} needs >=5 product keywords"

    def test_each_industry_has_scenario_keywords(self):
        for slug, signals in INDUSTRY_SIGNALS.items():
            assert len(signals.get("scenario_keywords", [])) >= 3, f"{slug} needs >=3 scenario keywords"

    def test_each_industry_has_risk_keywords(self):
        for slug, signals in INDUSTRY_SIGNALS.items():
            assert len(signals.get("risk_keywords", [])) >= 4, f"{slug} needs >=4 risk keywords"

    def test_each_industry_has_gt_field_indicators(self):
        for slug, signals in INDUSTRY_SIGNALS.items():
            assert len(signals.get("gt_field_indicators", [])) >= 3, f"{slug} needs >=3 GT field indicators"


class TestClassification:
    def test_starbucks_classified_as_fnb(self):
        result = classify_industry(
            brand_name="星巴克", products="咖啡 饮品 甜品 门店",
            scenarios="早餐 下午茶 聚会 外卖",
            competitors="瑞幸 Costa Tims",
            gt_fields=["store_coverage", "signature_products", "menu_categories"],
        )
        assert result["primary_slug"] == "fnb"
        assert result["confidence"] == "high"

    def test_bank_classified_as_finance(self):
        result = classify_industry(
            brand_name="招商银行", products="银行 贷款 理财 信用卡 基金",
            scenarios="开户 转账 投资 贷款申请",
            competitors="工商银行 平安",
            gt_fields=["license_type", "regulator", "risk_disclosure"],
        )
        assert result["primary_slug"] == "finance"

    def test_saas_classified_as_saas_b2b(self):
        result = classify_industry(
            brand_name="云科技", products="CRM SaaS 软件 API 数据分析",
            scenarios="企业管理 销售管理 数据分析",
            competitors="Salesforce HubSpot",
            gt_fields=["deployment_model", "integrations", "api_support"],
        )
        assert result["primary_slug"] == "saas_b2b"

    def test_ev_classified_as_ev_mobility(self):
        result = classify_industry(
            brand_name="特斯拉", products="汽车 电动车 电池 智能驾驶 充电",
            scenarios="代步 通勤 自驾 充电",
            competitors="比亚迪 小鹏 蔚来",
            gt_fields=["vehicle_models", "battery_technology", "smart_driving_level"],
        )
        assert result["primary_slug"] == "ev_mobility"

    def test_hospital_classified_as_healthcare(self):
        result = classify_industry(
            brand_name="协和医院", products="药品 医疗器械 诊疗 体检 手术",
            scenarios="就医 挂号 问诊 治疗",
            competitors="",
            gt_fields=["medical_license", "approved_indications", "clinical_evidence"],
        )
        assert result["primary_slug"] == "healthcare_pharma"

    def test_no_signals_returns_unknown(self):
        result = classify_industry(brand_name="", products="", scenarios="")
        assert result["primary_slug"] == "unknown"
        assert result["confidence"] == "low"

    def test_result_has_required_keys(self):
        result = classify_industry(brand_name="星巴克", products="咖啡")
        for key in ("primary_slug", "confidence", "confidence_score", "reason", "needs_user_confirmation"):
            assert key in result

    def test_high_confidence_no_confirmation_needed(self):
        result = classify_industry(
            brand_name="星巴克", products="咖啡 饮品 门店 甜品 外卖 会员",
            scenarios="早餐 下午茶 聚会", competitors="瑞幸 Costa",
            gt_fields=["store_coverage", "signature_products", "menu_categories", "delivery_channels"],
        )
        assert result["confidence"] == "high"
