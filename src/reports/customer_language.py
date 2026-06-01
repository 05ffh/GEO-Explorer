"""Customer-language translation layer — KPI mappings, term replacements, industry language."""
import re

# ── 10 KPI customer-language mappings ────────────────────────────────────────

KPI_CUSTOMER_LANGUAGE = {
    "sov": {
        "label": "品牌被 AI 看见的程度",
        "question": "当用户向 AI 提问时，品牌有没有被提到？",
        "good": "品牌在 AI 对话中被频繁提及，说明品牌内容覆盖较好，用户在相关场景中容易看到你的品牌。",
        "bad": "品牌在 AI 讨论中出现频率偏低，用户可能在相关场景中注意不到你的品牌。",
        "action": "建议增加更多面向真实用户场景的内容（如场景FAQ、使用指南），提升品牌在 AI 回答中的出现机会。",
        "verdict_threshold_good": 0.50,
        "verdict_threshold_bad": 0.30,
    },
    "first_rec_rate": {
        "label": "AI 优先推荐品牌的比例",
        "question": "AI 在回答中是否优先推荐你的品牌？",
        "good": "AI 倾向于在多个场景中将品牌列为首选或重点推荐，有利于获取用户的第一注意力。",
        "bad": "品牌在 AI 的推荐排序中位置靠后，用户更可能先看到竞品。",
        "action": "加强品牌核心差异化内容的铺设，让 AI 有更多理由优先推荐你的品牌。",
        "verdict_threshold_good": 0.30,
        "verdict_threshold_bad": 0.10,
    },
    "accuracy_rate": {
        "label": "AI 描述品牌的准确程度",
        "question": "AI 对品牌的描述准确吗？有没有说错？",
        "good": "AI 对品牌信息的描述与品牌事实高度一致，用户获得的品牌认知基本正确。",
        "bad": "AI 存在多处与品牌事实不符的描述，可能导致潜在客户形成错误认知。",
        "action": "在官网发布准确、完整的品牌介绍，确保 AI 有正确的信息可以引用。",
        "verdict_threshold_good": 0.70,
        "verdict_threshold_bad": 0.50,
    },
    "completeness_rate": {
        "label": "AI 对品牌描述的完整程度",
        "question": "AI 有没有把品牌的关键信息说全？",
        "good": "AI 能够在回答中覆盖品牌的主要信息维度，让用户获得较为全面的品牌认知。",
        "bad": "AI 对品牌的描述较为片面，缺少关键信息（如核心产品、目标用户、差异化优势等）。",
        "action": "补充缺失维度的官网内容，确保每个关键品牌信息都有对应的官方页面。",
        "verdict_threshold_good": 0.60,
        "verdict_threshold_bad": 0.40,
    },
    "citation_rate": {
        "label": "AI 引用官方来源的频率",
        "question": "AI 在说品牌的时候，会不会引用你的官方网站？",
        "good": "AI 在描述品牌时频繁引用官方来源，有利于用户直接访问品牌官网获取准确信息。",
        "bad": "AI 很少引用品牌的官方来源，用户难以从 AI 回答中获取官方信息入口。",
        "action": "提升官网内容的权威性和结构化程度，让 AI 更愿意引用官方信息。",
        "verdict_threshold_good": 0.40,
        "verdict_threshold_bad": 0.15,
    },
    "scenario_recall": {
        "label": "AI 在真实场景中想到品牌的能力",
        "question": "当用户描述一个真实需求场景时，AI 会不会想到你的品牌？",
        "good": "品牌在多个非品牌指定场景中被 AI 主动提及，说明场景联想覆盖良好。",
        "bad": "当用户描述真实需求时，AI 很少提到品牌，说明品牌在用户真实场景中的认知联想不足。",
        "action": "针对目标用户的使用场景，创建场景化内容（如使用指南、解决方案、案例），提升场景联想覆盖。",
        "verdict_threshold_good": 0.30,
        "verdict_threshold_bad": 0.15,
    },
    "semantic_stability": {
        "label": "AI 对品牌描述的一致性",
        "question": "不同 AI 平台对品牌的描述一致吗？",
        "good": "各 AI 平台对品牌的核心描述基本一致，品牌在 AI 世界中的认知形象较为统一。",
        "bad": "不同 AI 平台对品牌的描述差异较大，品牌在 AI 世界中的认知形象碎片化。",
        "action": "在各渠道统一品牌核心信息表达，让 AI 从不同来源都能获得一致的品牌描述。",
        "verdict_threshold_good": 0.60,
        "verdict_threshold_bad": 0.40,
    },
    "differentiation": {
        "label": "AI 是否区分品牌与竞品的差异",
        "question": "AI 能不能说出你的品牌和别人不一样的地方？",
        "good": "AI 能够清晰识别并表达品牌与竞品的差异化特征，帮助用户在比较中做出选择。",
        "bad": "AI 难以区分品牌与竞品的差异，品牌在 AI 的认知中可能被同质化。",
        "action": "在官网明确表达品牌差异化定位，提供具体的差异化信息让 AI 能够学习和传达。",
        "verdict_threshold_good": 0.40,
        "verdict_threshold_bad": 0.20,
    },
    "cross_platform_consistency": {
        "label": "不同 AI 平台对品牌说法的一致程度",
        "question": "各个 AI 平台对品牌的描述统一吗？",
        "good": "跨平台的品牌描述较为统一，说明品牌的核心信息在 AI 世界中传播一致。",
        "bad": "不同 AI 平台对品牌的描述存在明显差异，可能因为各平台获取的品牌信息不一致。",
        "action": "确保品牌核心信息在官网、百科、行业媒体等多个渠道保持一致，减少 AI 获取的信息差异。",
        "verdict_threshold_good": 0.60,
        "verdict_threshold_bad": 0.40,
    },
    "recommendation_quality": {
        "label": "AI 推荐品牌时的理由质量",
        "question": "AI 推荐你的品牌时，理由有说服力吗？",
        "good": "AI 推荐品牌时提供的理由具体且有说服力，有助于用户做出选择。",
        "bad": "AI 推荐品牌时的理由较弱或模棱两可，难以有效说服用户选择你的品牌。",
        "action": "在官网提供具体的产品优势、客户案例和权威认证等信息，让 AI 有更充分的推荐理由。",
        "verdict_threshold_good": 0.50,
        "verdict_threshold_bad": 0.30,
    },
}


def get_kpi_verdict(key: str, value: float) -> str:
    """Return 'good', 'warning', or 'bad' for a KPI value."""
    cfg = KPI_CUSTOMER_LANGUAGE.get(key, {})
    good = cfg.get("verdict_threshold_good", 0.5)
    bad = cfg.get("verdict_threshold_bad", 0.3)
    if value >= good:
        return "good"
    if value >= bad:
        return "warning"
    return "bad"


# ── Term replacements ───────────────────────────────────────────────────────

TECH_TERM_REPLACEMENTS = {
    "SOV": "品牌被 AI 看见的程度",
    "Share of Voice": "AI 提到品牌的比例",
    "hallucination": "AI 错误信息",
    "semantic anchor": "AI 记住的品牌关键说法",
    "semantic stability": "AI 对品牌描述的一致性",
    "citation rate": "AI 引用官方来源的频率",
    "scenario recall": "AI 在真实场景中想到品牌的能力",
    "first recommendation rate": "AI 优先推荐品牌的比例",
    "accuracy rate": "AI 描述品牌的准确程度",
    "completeness rate": "AI 对品牌描述的完整程度",
    "cross-platform consistency": "不同 AI 平台对品牌说法的统一程度",
    "differentiation": "AI 是否区分品牌与竞品的差异",
    "recommendation quality": "AI 推荐品牌时的理由质量",
    "GT": "品牌事实库",
    "Ground Truth": "品牌事实库",
    "KPI": "观察指标",
    "LLM": "AI 平台",
}

FORBIDDEN_ABSOLUTE_TERMS = [
    "一定", "必然", "肯定", "保证", "所有用户都会",
    "永远", "绝对", "毫无疑问", "100%",
]

# Patterns to skip during term replacement
_SKIP_PATTERNS = [
    re.compile(r'https?://\S+'),       # URLs
    re.compile(r'```[\s\S]*?```'),      # code blocks
    re.compile(r'`[^`]+`'),             # inline code
    re.compile(r'"[^"]*?"'),           # JSON string values (keys are handled separately)
    re.compile(r'/[^\s]*?\.[a-z]{1,6}'), # file paths
]


def replace_terms_for_customer_language(text: str, edition: str, mode: str = "strict") -> str:
    """Replace technical terms with customer-friendly language.

    Skips URLs, code blocks, file paths, and inline code.
    mode: 'strict' (replace all), 'explain_first' (first occurrence explained), 'lenient' (allow some)
    """
    if not text:
        return text

    # Extract skip regions
    skip_regions = []
    for pat in _SKIP_PATTERNS:
        for m in pat.finditer(text):
            skip_regions.append((m.start(), m.end()))

    def _in_skip(pos: int) -> bool:
        return any(s <= pos < e for s, e in skip_regions)

    result = list(text)
    for term, replacement in TECH_TERM_REPLACEMENTS.items():
        idx = 0
        first = True
        while True:
            idx = text.find(term, idx)
            if idx == -1:
                break
            if not _in_skip(idx):
                if mode == "strict" or edition == "executive":
                    rep = replacement
                elif mode == "explain_first":
                    rep = f"{replacement}（原称 {term}）" if first else replacement
                else:  # lenient
                    rep = replacement
                for i in range(len(term)):
                    result[idx + i] = ""
                result[idx] = rep
                first = False
            idx += len(term)
    return "".join(result)


def contains_forbidden_terms(text: str) -> list[str]:
    """Return list of forbidden absolute terms found in text."""
    found = []
    for term in FORBIDDEN_ABSOLUTE_TERMS:
        if term in text:
            found.append(term)
    return found


# ── Industry report language ────────────────────────────────────────────────

INDUSTRY_REPORT_LANGUAGE = {
    "finance": {
        "opening_frame": "金融行业的 AI 认知管理需要特别关注合规表述、资质准确性和客户信息保护。",
        "risk_focus": ["资质准确性", "收益相关误导", "监管信息来源", "客户隐私保护", "风险提示完整性"],
        "preferred_action_language": ["补充", "核实", "确保", "按要求披露", "经合规审核后发布"],
        "compliance_note": "本报告不构成投资建议。AI 平台对金融产品的表述不代表监管机构立场。金融相关内容发布前需经合规审核。",
    },
    "fnb": {
        "opening_frame": "餐饮行业的 AI 认知管理需要关注门店覆盖、产品信息准确性、消费场景和食品安全相关表述。",
        "risk_focus": ["门店信息准确性", "产品描述", "食品安全相关表述", "价格信息", "消费场景覆盖"],
        "preferred_action_language": ["更新", "补充", "核实", "标注", "增加"],
        "compliance_note": "食品相关信息需确保符合相关法规要求。价格和促销信息发布前需确认时效性。",
    },
    "saas_b2b": {
        "opening_frame": "B2B SaaS 行业的 AI 认知管理需要聚焦功能差异化、技术能力、客户案例和安全合规。",
        "risk_focus": ["功能描述准确性", "客户案例真实性", "安全认证", "集成能力说明", "价格套餐信息"],
        "preferred_action_language": ["补充", "验证", "更新", "说明", "增强"],
        "compliance_note": "客户案例和性能数据发布前需获得客户授权。安全认证信息需保持最新。",
    },
    "ev_mobility": {
        "opening_frame": "新能源汽车行业的 AI 认知管理需要关注车型定位、技术参数、补能网络和安全相关的品牌表述。",
        "risk_focus": ["车型参数准确性", "交付数据", "补能网络信息", "智能驾驶相关表述", "安全相关声明"],
        "preferred_action_language": ["更新", "核实", "补充", "标注", "说明"],
        "compliance_note": "车辆参数和性能数据需以官方发布为准。安全相关表述需经技术和法务审核。",
    },
    "consumer_electronics": {
        "opening_frame": "消费电子行业的 AI 认知管理需要聚焦产品参数、功能特性、使用场景和竞品差异。",
        "risk_focus": ["产品参数准确性", "功能特性描述", "竞品比较表述", "价格信息", "售后政策"],
        "preferred_action_language": ["更新", "补充", "说明", "对比", "标注"],
        "compliance_note": "产品参数以官方规格表为准。竞品比较需基于公开可验证信息。",
    },
    "healthcare_pharma": {
        "opening_frame": "医疗健康行业的 AI 认知管理需要特别关注产品适应症、禁忌、临床数据和合规表述。",
        "risk_focus": ["适应症准确性", "禁忌说明", "临床数据引用", "资质认证", "不良反应信息"],
        "preferred_action_language": ["核实", "标注", "引用官方说明", "经医学审核后发布"],
        "compliance_note": "本报告不构成医疗建议。药品和医疗器械相关信息需符合监管要求，发布前需经医学和法务审核。",
    },
    "education": {
        "opening_frame": "教育行业的 AI 认知管理需要关注课程信息、师资资质、教学成果和学员反馈的准确性。",
        "risk_focus": ["课程描述准确性", "师资资质", "教学成果数据", "学费信息", "认证资质"],
        "preferred_action_language": ["补充", "更新", "说明", "标注", "核实"],
        "compliance_note": "教学成果和师资信息需以实际数据为准。教育相关承诺需符合广告法要求。",
    },
    "ecommerce_retail": {
        "opening_frame": "电商零售行业的 AI 认知管理需要关注产品信息、价格、库存、配送和售后等关键环节的品牌表述。",
        "risk_focus": ["产品信息准确性", "价格描述", "配送政策", "售后说明", "促销活动表述"],
        "preferred_action_language": ["更新", "补充", "标注", "核实"],
        "compliance_note": "价格和库存信息具有时效性，建议定期更新。促销活动信息需符合广告法规。",
    },
    "travel_hospitality": {
        "opening_frame": "旅游酒店行业的 AI 认知管理需要关注服务设施、地理位置、价格和用户评价相关的表述。",
        "risk_focus": ["设施描述准确性", "地理位置信息", "价格信息", "服务内容", "用户评价引用"],
        "preferred_action_language": ["更新", "补充", "标注", "说明", "核实"],
        "compliance_note": "价格和服务内容具有时效性。用户评价引用需注明来源和时间。",
    },
    "real_estate_home": {
        "opening_frame": "房地产行业的 AI 认知管理需要关注项目信息、户型数据、配套设施和销售相关的表述。",
        "risk_focus": ["项目信息准确性", "户型数据", "配套设施描述", "价格信息", "销售承诺"],
        "preferred_action_language": ["核实", "补充", "更新", "说明", "标注"],
        "compliance_note": "房地产相关信息需以政府部门公示为准。销售承诺需符合房地产广告法规。",
    },
    "industrial_b2b": {
        "opening_frame": "工业 B2B 行业的 AI 认知管理需要关注产品规格、技术参数、行业认证和应用场景的准确性。",
        "risk_focus": ["技术参数准确性", "行业认证", "应用场景描述", "产能数据", "客户案例"],
        "preferred_action_language": ["核实", "更新", "补充", "说明"],
        "compliance_note": "技术参数以官方数据表为准。客户案例发布前需获得授权。",
    },
    "logistics_crossborder": {
        "opening_frame": "物流跨境行业的 AI 认知管理需要关注服务范围、时效承诺、价格和合规能力。",
        "risk_focus": ["服务范围准确性", "时效承诺", "价格信息", "合规资质", "覆盖区域"],
        "preferred_action_language": ["更新", "核实", "标注", "补充"],
        "compliance_note": "时效和价格信息具有波动性。跨境服务信息需符合相关法规。",
    },
    "ai_cloud_devtools": {
        "opening_frame": "AI/云计算/开发者工具行业的认知管理需要聚焦技术能力、API 文档、定价模型和安全合规。",
        "risk_focus": ["技术能力描述", "API 文档完整性", "定价模型准确性", "安全合规认证", "客户案例"],
        "preferred_action_language": ["补充", "更新", "验证", "说明", "增强"],
        "compliance_note": "技术指标以官方文档为准。安全认证信息需定期更新。",
    },
    "beauty_fashion": {
        "opening_frame": "美妆时尚行业的 AI 认知管理需要关注产品成分、功效说明、使用方法和品牌调性的一致性。",
        "risk_focus": ["成分说明准确性", "功效表述", "使用方法", "价格信息", "品牌调性一致性"],
        "preferred_action_language": ["补充", "说明", "更新", "标注"],
        "compliance_note": "化妆品功效表述需符合相关法规。成分信息以产品标签为准。",
    },
    "public_sector_city": {
        "opening_frame": "公共部门与城市品牌的 AI 认知管理需要关注官方信息、政策表述、服务内容和数据准确性。",
        "risk_focus": ["官方信息准确性", "政策表述", "服务内容", "数据引用", "联系方式"],
        "preferred_action_language": ["核实", "更新", "引用官方来源", "标注", "补充"],
        "compliance_note": "公共信息以政府官方发布为准。数据引用需注明来源和时间。",
    },
}


def get_industry_language(industry_key: str | None) -> dict:
    """Return industry-specific report language, or general fallback."""
    if industry_key and industry_key in INDUSTRY_REPORT_LANGUAGE:
        return INDUSTRY_REPORT_LANGUAGE[industry_key]
    return {
        "opening_frame": "",
        "risk_focus": [],
        "preferred_action_language": ["补充", "更新", "优化"],
        "compliance_note": "",
    }
