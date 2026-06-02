"""P1-9: Industry classification system — codes, profiles, and default configs."""
from enum import Enum


class IndustryCode(str, Enum):
    DEFAULT = "default"
    RESTAURANT_CHAIN = "restaurant_chain"
    SAAS = "saas"
    TRAVEL_HOTEL = "travel_hotel"
    FINANCIAL_SERVICES = "financial_services"
    EDUCATION_TRAINING = "education_training"
    CONSUMER_BRAND = "consumer_brand"
    RETAIL_ECOMMERCE = "retail_ecommerce"
    HEALTHCARE = "healthcare"
    AUTOMOTIVE = "automotive"
    REAL_ESTATE = "real_estate"


INDUSTRY_PROFILES: dict[IndustryCode, dict] = {
    IndustryCode.DEFAULT: {
        "industry_code": "default",
        "industry_group": "general",
        "display_name": "通用",
        "aliases": [],
    },
    IndustryCode.RESTAURANT_CHAIN: {
        "industry_code": "restaurant_chain",
        "industry_group": "local_consumer_service",
        "display_name": "餐饮连锁",
        "aliases": ["连锁餐饮", "咖啡餐饮", "餐饮零售", "快餐连锁", "茶饮连锁"],
    },
    IndustryCode.SAAS: {
        "industry_code": "saas",
        "industry_group": "technology",
        "display_name": "SaaS",
        "aliases": ["软件服务", "企业服务软件", "B2B软件", "云服务"],
    },
    IndustryCode.TRAVEL_HOTEL: {
        "industry_code": "travel_hotel",
        "industry_group": "hospitality_travel",
        "display_name": "旅游酒店",
        "aliases": ["酒旅", "酒店旅游", "在线旅游", "OTA", "度假村"],
    },
    IndustryCode.FINANCIAL_SERVICES: {
        "industry_code": "financial_services",
        "industry_group": "finance",
        "display_name": "金融",
        "aliases": ["金融服务", "银行金融", "保险", "证券", "支付"],
    },
    IndustryCode.EDUCATION_TRAINING: {
        "industry_code": "education_training",
        "industry_group": "education",
        "display_name": "教育培训",
        "aliases": ["教育", "培训", "在线教育", "K12", "职业教育"],
    },
    IndustryCode.CONSUMER_BRAND: {
        "industry_code": "consumer_brand",
        "industry_group": "consumer_goods",
        "display_name": "消费品牌",
        "aliases": ["消费品", "快消品", "日化", "美妆", "食品饮料"],
    },
    IndustryCode.RETAIL_ECOMMERCE: {
        "industry_code": "retail_ecommerce",
        "industry_group": "retail",
        "display_name": "零售电商",
        "aliases": ["零售", "电商", "线上零售", "百货"],
    },
    IndustryCode.HEALTHCARE: {
        "industry_code": "healthcare",
        "industry_group": "healthcare",
        "display_name": "医疗健康",
        "aliases": ["医疗", "健康", "医院", "诊所", "医药"],
    },
    IndustryCode.AUTOMOTIVE: {
        "industry_code": "automotive",
        "industry_group": "automotive",
        "display_name": "汽车交通",
        "aliases": ["汽车", "新能源车", "出行", "交通"],
    },
    IndustryCode.REAL_ESTATE: {
        "industry_code": "real_estate",
        "industry_group": "real_estate",
        "display_name": "房地产",
        "aliases": ["地产", "住房", "商业地产", "物业"],
    },
}

# Industry detection keywords from GT fields → IndustryCode
INDUSTRY_KEYWORD_MAP: dict[str, list[str]] = {
    IndustryCode.RESTAURANT_CHAIN: ["餐饮", "餐厅", "咖啡", "奶茶", "快餐", "连锁", "门店", "外卖", "堂食", "菜单"],
    IndustryCode.SAAS: ["SaaS", "软件", "平台", "API", "云", "工具", "订阅", "企业服务"],
    IndustryCode.TRAVEL_HOTEL: ["酒店", "旅游", "旅行", "机票", "景点", "度假", "民宿", "OTA", "出行"],
    IndustryCode.FINANCIAL_SERVICES: ["银行", "金融", "保险", "支付", "理财", "证券", "基金", "贷款", "风控"],
    IndustryCode.EDUCATION_TRAINING: ["教育", "培训", "课程", "学习", "学校", "学院", "K12", "职业"],
    IndustryCode.CONSUMER_BRAND: ["美妆", "护肤", "食品", "饮料", "日化", "快消", "消费", "品牌"],
    IndustryCode.RETAIL_ECOMMERCE: ["零售", "电商", "商城", "百货", "购物", "线上线下", "门店"],
    IndustryCode.HEALTHCARE: ["医疗", "健康", "医院", "诊所", "患者", "药品", "医药", "器械"],
    IndustryCode.AUTOMOTIVE: ["汽车", "车", "出行", "驾驶", "新能源", "充电"],
    IndustryCode.REAL_ESTATE: ["地产", "房产", "住房", "物业", "楼盘", "售楼", "租赁"],
}
