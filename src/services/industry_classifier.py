"""GEO Explorer — Industry Classifier.

Multi-signal weighted scoring to identify which industry template fits a brand.
Uses 8 signal types: brand name, official site, products, scenarios, competitors, GT fields, risk terms, business model.
"""

# Signal keywords per industry — used for keyword-based classification
INDUSTRY_SIGNALS = {
    "finance": {
        "product_keywords": ["银行","保险","证券","基金","贷款","理财","信用卡","支付","存款","信托","财富管理","投资","股票","债券","外汇","期货","消费金融","供应链金融","融券","融资","保理"],
        "scenario_keywords": ["开户","转账","理财规划","融资","投资","贷款申请","风险评估","资产配置","保险理赔","信用评估"],
        "brand_name_keywords": ["银行","保险","证券","基金","金融","支付","财富","信托","资本"],
        "competitor_keywords": ["招商银行","工商银行","平安","蚂蚁","微众","众安","陆金所"],
        "risk_keywords": ["保证收益","保本保息","无风险","内幕消息","监管背书","稳赚不赔"],
        "gt_field_indicators": ["license_type","regulator","risk_disclosure","fee_structure","financial_products"],
        "business_model_indicators": ["licensed_institution","regulated","risk_managed"],
    },
    "fnb": {
        "product_keywords": ["咖啡","茶饮","奶茶","餐饮","餐厅","火锅","快餐","烘焙","甜品","小吃","饮品","酒","啤酒","白酒","饮料","矿泉水","果汁","奶制品","预制菜","调味品","零食","坚果","巧克力"],
        "scenario_keywords": ["早餐","午餐","晚餐","下午茶","聚会","约会","外卖","堂食","排队","订位","包厢","生日","团建","应酬"],
        "brand_name_keywords": ["咖啡","茶","奶茶","火锅","餐厅","厨房","小厨","面馆","烧烤","料理","酒馆","烘焙","甜品","炸鸡"],
        "competitor_keywords": ["星巴克","瑞幸","海底捞","麦当劳","肯德基","必胜客","喜茶","蜜雪冰城","奈雪"],
        "risk_keywords": ["包治百病","药用功效","绝对健康","虚假产地","食品安全事故","全国门店最多"],
        "gt_field_indicators": ["store_coverage","menu_categories","delivery_channels","signature_products","food_safety_policy"],
        "business_model_indicators": ["offline_chain","food_safety","consumer_brand"],
    },
    "saas_b2b": {
        "product_keywords": ["CRM","ERP","SaaS","软件","系统","平台","工具","API","云服务","数据","自动化","协同","办公","客服","营销","人力","财务","项目管理","低代码","无代码","BPM","BI","企业服务"],
        "scenario_keywords": ["企业管理","销售管理","客户管理","数据分析","流程自动化","团队协作","远程办公","项目管理","报表分析","审批流程"],
        "brand_name_keywords": ["软件","云","科技","数据","智能","信息","网络","数字"],
        "competitor_keywords": ["Salesforce","HubSpot","Zoho","钉钉","飞书","企业微信","用友","金蝶"],
        "risk_keywords": ["永久免费","无数据风险","替代所有人工","百分百准确","无需实施","不限用户"],
        "gt_field_indicators": ["deployment_model","integrations","security_certifications","api_support","pricing_model","target_company_size"],
        "business_model_indicators": ["subscription","cloud","b2b"],
    },
    "ev_mobility": {
        "product_keywords": ["汽车","电动车","新能源汽车","充电","电池","智能驾驶","自动驾驶","换电","电驱","混动","增程","纯电","车载","智能座舱"],
        "scenario_keywords": ["代步","通勤","自驾","跑长途","接送","越野","城市出行","跨城","露营","充电","充换电","保养"],
        "brand_name_keywords": ["汽车","电动","新能源","出行","车","驰","驱","行"],
        "competitor_keywords": ["特斯拉","比亚迪","小鹏","蔚来","理想","问界","极氪","小米汽车","零跑","哪吒"],
        "risk_keywords": ["完全自动驾驶","永不自燃","无需接管","零事故","L4自动驾驶","失控","起火"],
        "gt_field_indicators": ["vehicle_models","battery_technology","charging_network","smart_driving_level","safety_rating"],
        "business_model_indicators": ["hardware","service_network","safety_critical"],
    },
    "consumer_electronics": {
        "product_keywords": ["手机","电脑","笔记本","平板","手表","耳机","音响","电视","相机","无人机","穿戴","家电","扫地","冰箱","洗衣机","空调","机器人","游戏","投影"],
        "scenario_keywords": ["办公","娱乐","摄影","游戏","学习","健身","家居","智能控制","通话","拍摄"],
        "brand_name_keywords": ["电子","科技","智能","数码","手机","通讯","视","声","光"],
        "competitor_keywords": ["华为","小米","OPPO","vivo","荣耀","三星","大疆","索尼"],
        "risk_keywords": ["性能最强","永不卡顿","绝对安全","官方未发布","全球首发","军工品质"],
        "gt_field_indicators": ["product_models","technical_specs","compatibility","battery_life"],
        "business_model_indicators": ["hardware","consumer_brand","retail_channel"],
    },
    "healthcare_pharma": {
        "product_keywords": ["药品","医疗器械","诊疗","体检","手术","疫苗","生物制品","基因","诊断","试剂","耗材","影像","透析","康复","血液","制剂"],
        "scenario_keywords": ["就医","挂号","问诊","检查","体检","手术","住院","配药","复诊","急诊","转诊","治疗","康复"],
        "brand_name_keywords": ["医","药","健康","生物","基因","生命","诊断","疗","康"],
        "competitor_keywords": ["辉瑞","强生","罗氏","默沙东","阿斯利康","恒瑞","迈瑞","联影"],
        "risk_keywords": ["治愈","根治","无副作用","包治百病","替代治疗","100%有效"],
        "gt_field_indicators": ["medical_license","approved_indications","clinical_evidence","contraindications","usage_warnings"],
        "business_model_indicators": ["regulated","safety_critical","licensed"],
    },
    "education": {
        "product_keywords": ["课程","培训","教育","学习","备考","考试","辅导","网课","直播课","录播","题库","练习","测评","留学","游学","考研","考公","雅思","托福","GRE"],
        "scenario_keywords": ["上课","做题","考试","留学申请","面试","考证","提升","转行","入学","毕业","升学","求职"],
        "brand_name_keywords": ["教育","学","培训","课","辅导","留学","考"],
        "competitor_keywords": ["新东方","好未来","学而思","中公","粉笔","高途","作业帮","猿辅导"],
        "risk_keywords": ["包过","保录取","保证就业","快速致富","通过率100%","零基础变专家"],
        "gt_field_indicators": ["course_categories","certification_info","teacher_qualification","learning_outcomes"],
        "business_model_indicators": ["subscription","service","certification"],
    },
    "ecommerce_retail": {
        "product_keywords": ["电商","商城","旗舰店","购物","零售","超市","便利店","卖场","百货","批发","分销","品牌","商品","店铺","下单","快递","包裹"],
        "scenario_keywords": ["购物","下单","收货","退换","会员","积分","秒杀","满减","包邮","到店","配送"],
        "brand_name_keywords": ["商城","超市","便利店","品牌","电商","零售","百货","集市","铺"],
        "competitor_keywords": ["淘宝","京东","拼多多","抖音电商","快手","唯品会","美团","饿了么"],
        "risk_keywords": ["全网最低价","销量第一","官方授权","永久保修","虚构优惠","原装正品"],
        "gt_field_indicators": ["product_categories","sales_channels","official_store_urls","return_policy","membership_program"],
        "business_model_indicators": ["retail","consumer_brand","omni_channel"],
    },
    "travel_hospitality": {
        "product_keywords": ["酒店","民宿","景区","旅游","机票","火车票","门票","度假","跟团","自由行","邮轮","租车","导游","包车","签证","攻略","游记"],
        "scenario_keywords": ["出差","度假","蜜月","亲子游","自驾","背包","跟团","周边","周末","假期"],
        "brand_name_keywords": ["酒店","旅游","旅行","航空","景区","度假","民宿","客栈","乐园"],
        "competitor_keywords": ["携程","美团","飞猪","Booking","Airbnb","万豪","希尔顿","洲际","华住"],
        "risk_keywords": ["永久免费","五星评级","全天开放","零差评","不存在的景点","海景房","绝对安全"],
        "gt_field_indicators": ["location","opening_hours","booking_channels","amenities","seasonality"],
        "business_model_indicators": ["service","offline","seasonal"],
    },
    "real_estate_home": {
        "product_keywords": ["楼盘","住宅","别墅","公寓","写字楼","商铺","厂房","仓库","房源","物业","家装","装修","建材","瓷砖","地板","涂料","门窗","卫浴","厨房","衣柜","沙发","床垫","灯饰"],
        "scenario_keywords": ["看房","买房","租房","交房","装修","搬家","入住","验房","签约","贷款","产权"],
        "brand_name_keywords": ["地产","房产","置业","物业","城","府","湾","里","家居","建材"],
        "competitor_keywords": ["万科","碧桂园","融创","保利","龙湖","红星美凯龙","居然之家","宜家"],
        "risk_keywords": ["保证升值","学区房保证","零甲醛","永久产权","地铁房","拎包入住"],
        "gt_field_indicators": ["project_location","property_type","delivery_time","developer_qualification","environmental_certifications"],
        "business_model_indicators": ["asset_heavy","regulated","offline_service"],
    },
    "industrial_b2b": {
        "product_keywords": ["制造","设备","机械","零件","模具","铸造","焊接","冲压","注塑","表面处理","检测","测试","精密","数控","机床","自动化","机器人","产线","工厂","OEM","ODM"],
        "scenario_keywords": ["打样","试产","量产","质检","出货","验厂","认证","投标","询价","下单"],
        "brand_name_keywords": ["制造","工业","重工","机械","精密","模具","电子","半导体","光电"],
        "competitor_keywords": ["富士康","立讯精密","台积电","宁德时代","博世","西门子"],
        "risk_keywords": ["全球第一","军工认证","独家供应","产能虚构","零缺陷","Tier1"],
        "gt_field_indicators": ["product_specs","certifications","production_capacity","application_industries","quality_standards"],
        "business_model_indicators": ["b2b","heavy_asset","technical"],
    },
    "logistics_crossborder": {
        "product_keywords": ["快递","物流","货运","仓储","配送","最后一公里","冷链","整车","零担","集装箱","海运","空运","铁路","卡车","包裹","中转","报关","清关","退税","海外仓","FBA"],
        "scenario_keywords": ["发货","收货","退货","转运","报关","代收","签收","查询","预约","调度"],
        "brand_name_keywords": ["物流","快递","供应链","货运","速运","通达","达","邦","通"],
        "competitor_keywords": ["顺丰","中通","圆通","韵达","京东物流","菜鸟","DHL","FedEx","UPS"],
        "risk_keywords": ["100%清关","绝对准时","免税保证","最低价保证","全球覆盖","当天达"],
        "gt_field_indicators": ["service_regions","shipping_lanes","delivery_time_range","customs_clearance_capability","warehouse_network"],
        "business_model_indicators": ["service_network","crossborder","time_sensitive"],
    },
    "ai_cloud_devtools": {
        "product_keywords": ["AI","人工智能","机器学习","深度学习","模型","API","SDK","云","Serverless","容器","K8s","数据库","缓存","消息队列","CDN","DevOps","CI/CD","Git","开源","代码","编程","框架","库","IDE","调试","监控","日志","追踪"],
        "scenario_keywords": ["开发","调试","部署","上线","扩容","迁移","监控","排查","优化","压测","发布"],
        "brand_name_keywords": ["AI","云","数据","智能","平台","科技","开源"],
        "competitor_keywords": ["AWS","Azure","Google Cloud","阿里云","腾讯云","Hugging Face","GitHub","GitLab"],
        "risk_keywords": ["百分百准确","完全替代工程师","永久免费","无数据风险","无限调用","零宕机"],
        "gt_field_indicators": ["core_capabilities","api_docs","deployment_options","security_certifications","sla","open_source_license"],
        "business_model_indicators": ["subscription","api_first","developer_ecosystem"],
    },
    "beauty_fashion": {
        "product_keywords": ["化妆品","护肤品","面膜","精华","乳液","防晒","口红","香水","沐浴","洗发","染发","身体乳","手霜","服饰","衣服","裤子","裙子","外套","包","鞋","眼镜","首饰","手表","奢侈品","设计师","联名"],
        "scenario_keywords": ["护肤","化妆","穿搭","搭配","送礼","约会","聚会","上班","日常","旅行","婚礼"],
        "brand_name_keywords": ["美妆","护肤","化妆品","时装","服饰","奢侈品","生活","品牌"],
        "competitor_keywords": ["欧莱雅","雅诗兰黛","资生堂","ZARA","H&M","优衣库","LVMH","开云"],
        "risk_keywords": ["立刻美白","永久抗衰","医学认证","无任何副作用","纯天然","七日见效","人人适用"],
        "gt_field_indicators": ["ingredients","target_skin_or_user_type","safety_testing","product_categories","usage_scenarios"],
        "business_model_indicators": ["consumer_brand","lifestyle","trend_sensitive"],
    },
    "public_sector_city": {
        "product_keywords": ["政务服务","公共服务","行政审批","市场监管","税务","工商","社保","公积金","住建","规划","环保","城市管理","招商","投资","园区","开发","自贸","新区","口岸","保税"],
        "scenario_keywords": ["办事","审批","查询","申报","备案","年检","换证","缴纳","咨询","投诉","建议"],
        "brand_name_keywords": ["政府","城市","省","市","区","园区","新区","开发区"],
        "competitor_keywords": [],
        "risk_keywords": ["保证审批通过","官方补贴必得","虚构政策","虚构政府背书","税收优惠","落户政策"],
        "gt_field_indicators": ["official_government_site","policy_documents","application_process","eligibility_criteria","investment_policy"],
        "business_model_indicators": ["public_sector","official","policy_driven"],
    },
}

SIGNAL_WEIGHTS = {
    "brand_name": 0.10,
    "product": 0.25,
    "scenario": 0.15,
    "competitor": 0.10,
    "gt_field": 0.10,
    "risk": 0.03,
    "business_model": 0.02,
    "official_site": 0.25,
}


def classify_industry(brand_name: str = "", products: str = "", scenarios: str = "",
                      competitors: str = "", gt_fields: list = None,
                      official_site_text: str = "") -> dict:
    """Multi-signal industry classification. Returns scored results for all 15 industries."""
    scores = {}
    evidence = []

    for slug, signals in INDUSTRY_SIGNALS.items():
        score = 0.0
        matched = {}

        # Brand name signal
        if brand_name:
            hits = sum(1 for kw in signals.get("brand_name_keywords", []) if kw in brand_name)
            if hits:
                s = min(hits * SIGNAL_WEIGHTS["brand_name"], SIGNAL_WEIGHTS["brand_name"])
                score += s
                matched["brand_name"] = round(s, 3)

        # Product keywords (from GT fields, official site, user input)
        product_text = " ".join([products, official_site_text, " ".join(gt_fields or [])])
        if product_text:
            hits = sum(1 for kw in signals.get("product_keywords", []) if kw in product_text)
            if hits:
                s = min(hits * 0.05, SIGNAL_WEIGHTS["product"])
                score += s
                matched["product"] = round(s, 3)

        # Scenario keywords
        if scenarios:
            hits = sum(1 for kw in signals.get("scenario_keywords", []) if kw in scenarios)
            if hits:
                s = min(hits * 0.04, SIGNAL_WEIGHTS["scenario"])
                score += s
                matched["scenario"] = round(s, 3)

        # Competitor signal
        if competitors:
            hits = sum(1 for kw in signals.get("competitor_keywords", []) if kw in competitors)
            if hits:
                s = min(hits * 0.05, SIGNAL_WEIGHTS["competitor"])
                score += s
                matched["competitor"] = round(s, 3)

        # GT field indicators
        if gt_fields:
            hits = sum(1 for f in gt_fields if f in signals.get("gt_field_indicators", []))
            if hits:
                s = min(hits * 0.03, SIGNAL_WEIGHTS["gt_field"])
                score += s
                matched["gt_field"] = round(s, 3)

        # Business model
        tags_text = product_text
        if tags_text:
            hits = sum(1 for kw in signals.get("business_model_indicators", []) if kw in tags_text)
            if hits:
                s = min(hits * 0.01, SIGNAL_WEIGHTS["business_model"])
                score += s
                matched["business_model"] = round(s, 3)

        scores[slug] = {"score": round(score, 4), "matched_signals": matched, "conflicts": []}

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
    top_score = ranked[0][1]["score"] if ranked else 0
    second_score = ranked[1][1]["score"] if len(ranked) > 1 else 0
    gap = top_score - second_score

    # Determine confidence
    if top_score >= 0.3 and gap >= 0.15:
        confidence = "high"
    elif top_score >= 0.15 and gap >= 0.05:
        confidence = "medium"
    elif top_score >= 0.05:
        confidence = "low"
    else:
        return {
            "primary_slug": "unknown", "primary_name": "未知行业",
            "confidence": "low", "confidence_score": round(top_score, 4),
            "secondary": [], "alternative_templates": [],
            "evidence": evidence, "conflicts": [],
            "needs_user_confirmation": True,
            "business_model_tags": [],
            "reason": "所有行业得分均过低，无法确定品牌所属行业。建议补充官网、产品或目标用户信息。",
        }

    needs_confirmation = confidence != "high"

    # Build alternatives
    alternatives = []
    for i, (slug, data) in enumerate(ranked[1:4]):
        if data["score"] > 0.03:
            alternatives.append({"template": slug, "score": data["score"],
                                 "reason": "存在部分匹配信号"})

    return {
        "primary_slug": ranked[0][0],
        "primary_name": _slug_to_name(ranked[0][0]),
        "confidence": confidence,
        "confidence_score": top_score,
        "secondary": [alt["template"] for alt in alternatives[:2] if alt["score"] > 0.05],
        "alternative_templates": alternatives,
        "evidence": [{"signal": sig, "value": val} for sig, val in ranked[0][1]["matched_signals"].items()],
        "conflicts": [],
        "needs_user_confirmation": needs_confirmation,
        "business_model_tags": _infer_business_tags(ranked[0][0], products, official_site_text),
        "reason": _generate_reason(ranked[0][0], top_score, ranked[0][1]["matched_signals"]),
    }


def _slug_to_name(slug: str) -> str:
    mapping = {
        "finance": "金融服务", "fnb": "餐饮与食品饮料", "saas_b2b": "SaaS与企业服务",
        "ev_mobility": "新能源汽车与智能出行", "consumer_electronics": "消费电子与智能硬件",
        "healthcare_pharma": "医疗健康与医药", "education": "教育培训与知识服务",
        "ecommerce_retail": "电商零售与消费品牌", "travel_hospitality": "文旅酒店与本地生活",
        "real_estate_home": "房地产与家居建材", "industrial_b2b": "工业制造与B2B供应链",
        "logistics_crossborder": "物流供应链与跨境贸易", "ai_cloud_devtools": "AI/云计算/开发者工具",
        "beauty_fashion": "美妆个护与时尚生活", "public_sector_city": "政府公共服务与城市品牌",
    }
    return mapping.get(slug, slug)


def _infer_business_tags(slug: str, products: str, site_text: str) -> list:
    text = (products + " " + site_text).lower()
    tags = []
    all_tags = ["subscription","offline_chain","online_platform","marketplace","hardware","software",
                "developer_tool","service_network","retail","franchise","direct_to_consumer",
                "regulated_service","licensed_institution","b2b","consumer_brand"]
    for tag in all_tags:
        if tag in text:
            tags.append(tag)
    return tags[:8]


def _generate_reason(slug: str, score: float, signals: dict) -> str:
    name = _slug_to_name(slug)
    signal_names = list(signals.keys())
    if not signal_names:
        return f"品牌信号较弱，推测属于{name}。建议补充官网和产品信息。"
    sig_labels = {"brand_name": "品牌名称", "product": "产品关键词", "scenario": "场景关键词",
                  "competitor": "竞品信号", "gt_field": "GT字段", "business_model": "业务模式"}
    matched = [sig_labels.get(s, s) for s in signal_names]
    return f"品牌{','.join(matched[:3])}等信号匹配{name}行业。置信度得分 {score:.2f}。"
