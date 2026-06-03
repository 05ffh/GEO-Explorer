"""P2-1: Claim Nature Classifier — rule-based fact/opinion/speculation detection.

Classifies each AI-generated claim by its epistemological nature:
- FACT: verifiable objective statement (numbers, dates, verifiable attributes)
- OPINION: subjective judgment/evaluation (superlatives, preferences)
- SPECULATION: forward-looking/unverified claim (hedging, future tense, predictions)

claim_type column stores the ClaimNature value but is named claim_type for DB clarity.
The column represents claim NATURE (cognitive type), not claim subject or predicate domain.
"""

import re
from dataclasses import dataclass, field
from src.analyzer.enums import ClaimNature


# ── Signal word dictionaries (strong / weak / negation) ─────────────────────

_CN_SPECULATION_STRONG = [
    "可能", "或将", "有望", "预计", "预测", "估计", "或许", "也许",
    "大概率", "很有可能", "极有可能",
]

_CN_SPECULATION_WEAK = [
    "将", "将会", "未来", "计划", "探索", "尝试", "拟",
    "即将", "下一步", "下一阶段", "远期", "趋势", "方向",
    "打算", "正在考虑",
]

_CN_OPINION_STRONG = [
    "最好", "最强", "顶级", "一流", "最佳", "最受欢迎", "最大",
    "卓越", "绝对领先", "无可匹敌", "无与伦比",
]

_CN_OPINION_WEAK = [
    "领先", "受欢迎", "优质", "出色", "优秀", "强大",
    "深受好评", "备受赞誉", "公认", "知名", "行业领先",
    "体验好", "服务优质", "用户认可",
]

_CN_FACT_STRONG = [
    "成立于", "创立于", "总部设在", "总部位于",
]

_CN_FACT_WEAK = [
    "拥有", "覆盖", "员工", "营收", "收入", "融资", "上市",
    "已获得", "获得", "提供", "包含", "推出",
]

_CN_NEGATION = [
    "不是", "并非", "没有", "不认为", "无法", "不能",
]

# ── English signals ─────────────────────────────────────────────────────────

_EN_SPECULATION_STRONG = [
    "could", "might", "may", "likely to", "expected to", "predicted to",
    "projected to", "potentially", "possibly",
]

_EN_SPECULATION_WEAK = [
    "will", "would", "plans to", "aims to", "seeks to",
    "exploring", "considering", "in the future", "upcoming",
    "rumored to", "reportedly", "allegedly",
]

_EN_OPINION_STRONG = [
    "best", "top", "excellent", "superior", "outstanding",
    "premier", "unmatched", "unrivaled", "ultimate",
]

_EN_OPINION_WEAK = [
    "leading", "popular", "premium", "highly rated", "renowned",
    "widely regarded", "better than", "more.*than",
]

_EN_FACT_STRONG = [
    "founded in", "headquartered in",
]

_EN_FACT_WEAK = [
    "has", "owns", "operates", "revenue", "launched in",
    "acquired", "reported", "currently", "as of", "since",
    "employees", "stores", "locations",
]

_EN_NEGATION = [
    "not", "isn't", "aren't", "doesn't", "don't", "never",
    "no longer", "cannot", "can't",
]

# Numeric/date patterns for fact detection (language-agnostic)
_FACT_NUMERIC_RE = re.compile(
    r'\d{4}年|'           # Chinese year
    r'\d+[家个项次元]|'    # Chinese counters
    r'\d+[%％]|'          # percentages
    r'\d+[万亿]|'         # large Chinese numbers
    r'\$\d+[BKMT]?|'      # dollar amounts
    r'\d+\s*(stores|employees|locations|users|customers|revenue|million|billion)',
    re.IGNORECASE,
)

# Structural signals for speculation negation context
_NEGATION_CONTEXT_RE = re.compile(
    r'(?:不是|并非|没有|不|not?\s+|never\s+|no\s+)?',
)


# ── High-risk predicate types (escalate severity for speculation) ────────────

HIGH_RISK_PREDICATES = {
    "identity", "financial_performance", "regulatory_status",
    "health_effect", "safety", "legal_compliance", "pricing",
}

LOW_RISK_PREDICATES = {
    "reputation", "scenario", "target_user",
}


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class ClaimNatureResult:
    """Output of ClaimNatureClassifier.classify()."""
    claim_nature: ClaimNature
    confidence: float
    matched_signals: list[str] = field(default_factory=list)
    signal_categories: list[str] = field(default_factory=list)
    reason: str = ""
    speculation_risk_level: str = ""  # low / medium / high (only for speculation)


# ── Classifier ───────────────────────────────────────────────────────────────

class ClaimNatureClassifier:
    """Rule-based classifier for claim epistemological nature.

    Priority: speculation > opinion > fact.
    A claim containing both "may" and a number is SPECULATION — hedging dominates.
    """

    def classify(self, claim_text: str, predicate_type: str = "other") -> ClaimNatureResult:
        """Classify a claim's cognitive nature from its text.

        Args:
            claim_text: The claim text fragment (Chinese and/or English).
            predicate_type: The predicate domain (identity, product, etc.)
                           Used for risk level assessment on speculation.

        Returns:
            ClaimNatureResult with nature, confidence, signals, and reason.
        """
        text = claim_text.strip()

        # Too short to classify
        if len(text) < 5:
            return ClaimNatureResult(
                claim_nature=ClaimNature.UNKNOWN,
                confidence=0.0,
                reason="文本过短(<5字符)，无法判定声明性质",
            )

        text_lower = text.lower()

        # Check negation context
        has_negation = any(n in text_lower for n in _CN_NEGATION) or \
                       any(n in text_lower for n in _EN_NEGATION)

        # ── Detect signals ───────────────────────────────────────────────

        cn_spec_strong = [s for s in _CN_SPECULATION_STRONG if s in text]
        cn_spec_weak = [s for s in _CN_SPECULATION_WEAK if s in text]
        en_spec_strong = [s for s in _EN_SPECULATION_STRONG if s in text_lower]
        en_spec_weak = [s for s in _EN_SPECULATION_WEAK if s in text_lower]

        cn_opin_strong = [s for s in _CN_OPINION_STRONG if s in text]
        cn_opin_weak = [s for s in _CN_OPINION_WEAK if s in text]
        en_opin_strong = [s for s in _EN_OPINION_STRONG if s in text_lower]
        en_opin_weak = [s for s in _EN_OPINION_WEAK if s in text_lower]

        cn_fact_strong = [s for s in _CN_FACT_STRONG if s in text]
        cn_fact_weak = [s for s in _CN_FACT_WEAK if s in text]
        en_fact_strong = [s for s in _EN_FACT_STRONG if s in text_lower]
        en_fact_weak = [s for s in _EN_FACT_WEAK if s in text_lower]

        has_numeric = bool(_FACT_NUMERIC_RE.search(text))

        # ── Priority: SPECULATION > OPINION > FACT ───────────────────────

        spec_signals = cn_spec_strong + cn_spec_weak + en_spec_strong + en_spec_weak
        opin_signals = cn_opin_strong + cn_opin_weak + en_opin_strong + en_opin_weak
        fact_signals = cn_fact_strong + cn_fact_weak + en_fact_strong + en_fact_weak

        has_spec_strong = bool(cn_spec_strong) or bool(en_spec_strong)
        has_opin_strong = bool(cn_opin_strong) or bool(en_opin_strong)
        has_fact_strong = bool(cn_fact_strong) or bool(en_fact_strong)

        # ── SPECULATION ──────────────────────────────────────────────────
        if spec_signals:
            confidence = 0.85 if has_spec_strong else 0.65
            categories = ["speculation"]
            if has_spec_strong:
                categories.append("speculation_strong")
            if cn_spec_weak or en_spec_weak:
                categories.append("speculation_weak")

            # Assess risk level
            risk_level = self._assess_speculation_risk(
                predicate_type, has_spec_strong, has_negation)

            reason_parts = []
            if has_negation:
                reason_parts.append("否定语境中的推测信号")
            if risk_level == "high":
                reason_parts.append(f"高风险predicate({predicate_type})推测")
            elif risk_level == "medium":
                reason_parts.append("中等风险推测")

            return ClaimNatureResult(
                claim_nature=ClaimNature.SPECULATION,
                confidence=confidence,
                matched_signals=spec_signals,
                signal_categories=categories,
                reason="; ".join(reason_parts) if reason_parts else f"命中推测信号: {spec_signals[:3]}",
                speculation_risk_level=risk_level,
            )

        # ── OPINION ──────────────────────────────────────────────────────
        if opin_signals:
            confidence = 0.85 if has_opin_strong else 0.65
            categories = ["opinion"]
            if has_opin_strong:
                categories.append("opinion_strong")
            if cn_opin_weak or en_opin_weak:
                categories.append("opinion_weak")
            if has_negation:
                categories.append("negated_opinion")

            reason = f"命中观点信号: {opin_signals[:3]}"
            if has_negation:
                reason = f"否定语境中的观点表达: {opin_signals[:3]}"

            return ClaimNatureResult(
                claim_nature=ClaimNature.OPINION,
                confidence=confidence,
                matched_signals=opin_signals,
                signal_categories=categories,
                reason=reason,
            )

        # ── FACT ─────────────────────────────────────────────────────────
        if has_numeric or fact_signals:
            confidence = 0.85 if (has_fact_strong or has_numeric) else 0.55
            categories = ["fact"]
            if has_fact_strong:
                categories.append("fact_strong")
            if has_numeric:
                categories.append("fact_numeric")

            return ClaimNatureResult(
                claim_nature=ClaimNature.FACT,
                confidence=confidence,
                matched_signals=fact_signals + (
                    ["<numeric_pattern>"] if has_numeric else []),
                signal_categories=categories,
                reason=f"命中事实信号" + (f": {fact_signals[:3]}" if fact_signals else " (数字/日期模式)"),
            )

        # ── UNKNOWN ──────────────────────────────────────────────────────
        return ClaimNatureResult(
            claim_nature=ClaimNature.UNKNOWN,
            confidence=0.0,
            reason="未命中事实/观点/推测信号，无法判定声明性质",
        )

    @staticmethod
    def _assess_speculation_risk(
        predicate_type: str,
        has_strong_signal: bool,
        has_negation: bool,
    ) -> str:
        """Assess speculation risk level based on predicate and signal strength."""
        if predicate_type in HIGH_RISK_PREDICATES:
            return "high"
        if predicate_type in LOW_RISK_PREDICATES:
            return "low"
        if has_strong_signal:
            return "medium"
        return "low"


# Module-level instance for convenience
classifier = ClaimNatureClassifier()


def classify_claim_nature(claim_text: str, predicate_type: str = "other") -> ClaimNatureResult:
    """Convenience function for claim nature classification."""
    return classifier.classify(claim_text, predicate_type)
