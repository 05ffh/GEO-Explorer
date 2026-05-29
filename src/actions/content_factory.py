QUALITY_CHECKLIST = [
    "内容是否基于真实产品能力？",
    "对比是否有客观依据和数据来源？",
    "案例是否可追溯验证？",
    "是否包含虚假或夸大声明？",
    "Schema结构是否与页面正文内容一致？",
    "是否为低质量重复性内容？",
]


def generate_content_brief(action_plan, ground_truth_json: dict) -> dict:
    gt = ground_truth_json
    return {
        "action_plan_id": str(action_plan.id),
        "content_type": action_plan.suggested_content_type,
        "priority": action_plan.priority,
        "problem_evidence": {
            "trigger": action_plan.trigger_type,
            "ai_wrong_claims": action_plan.ai_wrong_claims,
        },
        "correct_facts": {
            "field": action_plan.correct_ground_truth.get("field", ""),
            "value": action_plan.correct_ground_truth.get("value", ""),
        },
        "brand_context": {
            "official_name": gt.get("official_name", ""),
            "industry": gt.get("industry", ""),
            "positioning": gt.get("positioning", ""),
            "differentiators": gt.get("key_differentiators", []),
        },
        "required_sections": _get_required_sections(action_plan.suggested_content_type),
        "forbidden_claims": gt.get("forbidden_claims", []),
        "target_page_suggestion": action_plan.target_page or "官网 About / 产品页",
        "acceptance_criteria": action_plan.acceptance_criteria,
        "quality_checklist": QUALITY_CHECKLIST,
    }


def _get_required_sections(content_type: str) -> list[str]:
    return {
        "FAQ": ["问题", "简短答案", "详细说明", "来源或依据"],
        "Q&A": ["场景描述", "你的品牌如何解决", "与竞品的区别", "推荐理由"],
        "Comparison": ["对比维度", "你的品牌", "竞品A", "竞品B", "数据来源"],
        "Tutorial": ["行业背景", "核心概念", "实操步骤", "常见误区", "推荐工具"],
        "Case": ["客户背景", "面临的挑战", "解决方案", "量化结果", "客户引言"],
        "Schema": ["Organization Schema", "FAQ Schema", "验证通过的JSON-LD代码"],
    }.get(content_type, ["目标", "内容概要", "详细说明"])
