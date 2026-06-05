"""P2-1: Claim Nature Classifier — rule-based fact/opinion/speculation detection.

Classifies each AI-generated claim by its epistemological nature:
- FACT: verifiable objective statement (numbers, dates, verifiable attributes)
- OPINION: subjective judgment/evaluation (superlatives, preferences)
- SPECULATION: forward-looking/unverified claim (hedging, future tense, predictions)

v2: Weighted-scoring classifier with negation window, n-gram fallback, and
industry-specific high-risk term detection. Replaces the simple priority chain.

claim_type column stores the ClaimNature value but is named claim_type for DB clarity.
The column represents claim NATURE (cognitive type), not claim subject or predicate domain.
"""

import re
from dataclasses import dataclass, field
from src.analyzer.enums import ClaimNature


# ═══════════════════════════════════════════════════════════════════════════════
# Signal word dictionaries (strong / weak / negation)
# ═══════════════════════════════════════════════════════════════════════════════

_CN_SPECULATION_STRONG = [
    # Core hedging
    "可能", "或将", "有望", "预计", "预测", "估计", "或许", "也许",
    "大概率", "很有可能", "极有可能", "很可能",
    # Uncertainty markers
    "似乎", "好像", "疑似", "据传", "传闻", "据说", "据报道", "据称",
    "据透露", "据悉", "有消息称", "有传言称", "尚不确定", "尚无定论",
    "难以确定", "难以预测", "不排除", "仍存变数",
    # Speculative hedge
    "或", "有可能", "概率",
]

_CN_SPECULATION_WEAK = [
    # Future-oriented
    "将", "将会", "未来", "计划", "探索", "尝试", "拟",
    "即将", "下一步", "下一阶段", "远期", "趋势", "方向",
    "打算", "正在考虑",
    # Planning/roadmap
    "预期", "展望", "布局", "规划", "准备", "酝酿",
    "研发中", "开发中", "筹建", "筹办", "推进中", "筹备",
    "下阶段", "目标", "愿景", "瞄准", "进军", "发力",
    "将推出", "将发布", "将上线", "将启动",
    # Aspirational
    "希望", "期望", "致力于", "力求", "争取", "谋求",
    # Emerging
    "新兴", "崛起", "崭露头角", "初露锋芒", "渐成趋势",
]

_CN_OPINION_STRONG = [
    # Superlative
    "最好", "最强", "顶级", "一流", "最佳", "最受欢迎", "最大",
    "卓越", "绝对领先", "无可匹敌", "无与伦比",
    "最权威", "最具", "最专业", "最先进", "最值得",
    "无可争议", "遥遥领先", "首屈一指", "独一无二",
    "举世闻名", "享誉全球", "当之无愧", "独占鳌头",
    "无出其右", "傲视", "冠绝", "称雄",
    # Absolute claims (financially/legally risky when combined with industry risk)
    "唯一", "第一", "100%", "绝对", "完全", "彻底",
]

_CN_OPINION_WEAK = [
    # Quality evaluation
    "领先", "受欢迎", "优质", "出色", "优秀", "强大",
    "深受好评", "备受赞誉", "公认", "知名", "行业领先",
    "体验好", "服务优质", "用户认可",
    # Subjective endorsement
    "极具", "颇受", "广受", "备受", "备受瞩目", "引人注目",
    "脱颖而出", "名列前茅", "口碑", "好评如潮", "推荐",
    "赞誉", "盛赞", "推崇",
    # Descriptive adjectives
    "专业", "权威", "精英", "高端", "创新", "突破",
    "先进", "前沿", "标杆", "典范", "领军", "龙头",
    "标杆企业", "代表性", "标志性", "典型",
    # Positive reception
    "认可", "信赖", "青睐", "追捧", "热捧", "首选",
    "首选品牌", "必选", "值得信赖", "值得推荐",
]

_CN_FACT_STRONG = [
    # Establishment/location
    "成立于", "创立于", "总部设在", "总部位于",
    "注册于", "注册地址", "注册地", "发源于",
    "全称", "原名", "前身", "隶属于",
    # Legal entity
    "注册资本", "法人代表", "法定代表人", "统一社会信用代码",
    # Precise location
    "位于", "地址", "坐落于",
]

_CN_FACT_WEAK = [
    # Business scale
    "拥有", "覆盖", "员工", "营收", "收入", "融资", "上市",
    "门店", "店铺", "家门店", "直营", "加盟",
    "超过", "达到", "实现", "累计",
    # Product/service
    "已获得", "获得", "提供", "包含", "推出",
    "业务", "产品", "服务", "旗下", "包括", "主要有",
    # Operations
    "合作", "签约", "入驻", "开设", "进驻", "布局",
    "设有", "设立", "建立", "建成",
    # Quantifiable
    "年营收", "年收入", "市值", "估值", "同比增长",
    "环比增长", "市场份额", "占有率",
]

_CN_NEGATION = [
    "不是", "并非", "没有", "不认为", "无法", "不能",
    "并非如此", "并不", "并未", "决不", "绝非",
    "否认", "澄清", "驳斥", "辟谣",
    "不", "未", "无", "尚未", "难以", "不一定",
    "并不意味着", "不代表", "未必",
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

# ── Signal config: (strong_list, weak_list, weight_strong, weight_weak) ──────

_SIGNAL_CONFIG = {
    "speculation": (_CN_SPECULATION_STRONG, _CN_SPECULATION_WEAK,
                     _EN_SPECULATION_STRONG, _EN_SPECULATION_WEAK),
    "opinion": (_CN_OPINION_STRONG, _CN_OPINION_WEAK,
                _EN_OPINION_STRONG, _EN_OPINION_WEAK),
    "fact": (_CN_FACT_STRONG, _CN_FACT_WEAK,
             _EN_FACT_STRONG, _EN_FACT_WEAK),
}

# ── Numeric/date patterns for fact detection ─────────────────────────────────

_FACT_NUMERIC_RE = re.compile(
    r'\d{4}\s*年|'
    r'\d{1,2}\s*月|'
    r'\d{1,2}\s*日|'
    r'第\s*\d+|'
    r'\d+[家个项次名位只台座间处所]|'
    r'\d+[%％]|'
    r'百分之\s*\d+|'
    r'\d+\s*[万亿]|'
    r'\d+\s*[元块]|'
    r'\d+\s*万\s*[元吨个家]|'
    r'\d+\s*亿\s*[美元元]|'
    r'\d+[倍成]|'
    r'\$\d+[BKMT]?|'
    r'\d+\s*(stores|employees|locations|users|customers|revenue|million|billion|trillion)',
    re.IGNORECASE,
)

_FACT_STRUCTURAL_PATTERNS = [
    re.compile(r'截至\s*\d{4}'),
    re.compile(r'累计\s*\d+'),
    re.compile(r'已有\s*\d+'),
    re.compile(r'超过\s*\d+'),
    re.compile(r'达到\s*\d+'),
    re.compile(r'共\s*\d+'),
    re.compile(r'\d+\s*[～~至到-]\s*\d+'),
]

# Chinese sentence-final particles indicating speculative/questioning tone
_CN_SPEC_PARTICLES = ("吧", "吗", "呢")

# ── Industry high-risk term dictionaries ─────────────────────────────────────

_INDUSTRY_HIGH_RISK_TERMS: dict[str, list[str]] = {
    "financial_services": [
        "保本", "高收益", "无风险", "稳赚", "兜底", "暴雷", "刚兑",
        "年化收益", "资金安全", "保底收益", "绝对收益", "零风险",
        "稳赚不赔", "刚性兑付", "承诺收益", "固定收益", "保本保息",
        "预期收益", "收益保证",
    ],
    "healthcare": [
        "治愈", "疗效", "无副作用", "临床证明", "药监局批准", "治疗效果",
        "根治", "特效", "包治", "有效率", "治愈率", "无创", "微创",
        "100%有效", "彻底治愈", "药到病除", "副作用为零",
    ],
    "education_training": [
        "保过", "包就业", "稳上岸", "录取保证", "提分", "名师押题",
        "100%通过", "保证录取", "包过", "包教包会", "签约保分",
        "考试必过", "保证提分", "不通过退款",
    ],
}

# Industry code → risk key mapping
_INDUSTRY_CODE_TO_RISK_KEY: dict[str, list[str]] = {
    "banking": ["financial_services"],
    "insurance": ["financial_services"],
    "securities": ["financial_services"],
    "fintech": ["financial_services"],
    "healthcare": ["healthcare"],
    "pharmaceutical": ["healthcare"],
    "medical_device": ["healthcare"],
    "education": ["education_training"],
    "edtech": ["education_training"],
    "training": ["education_training"],
}

# ── High-risk predicate types ────────────────────────────────────────────────

HIGH_RISK_PREDICATES = {
    "identity", "financial_performance", "regulatory_status",
    "health_effect", "safety", "legal_compliance", "pricing",
}

LOW_RISK_PREDICATES = {
    "reputation", "scenario", "target_user",
}

# Absolute opinion keywords that escalate risk in regulated industries
_ABSOLUTE_OPINION_KEYWORDS = {"唯一", "第一", "100%", "绝对", "完全", "彻底", "最好"}


# ═══════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClaimNatureResult:
    """Output of ClaimNatureClassifier.classify()."""
    claim_nature: ClaimNature
    confidence: float
    matched_signals: list[str] = field(default_factory=list)
    signal_strength: str = "none"          # "strong" | "weak" | "mixed" | "none"
    negation_detected: bool = False
    signal_categories: list[str] = field(default_factory=list)
    reason: str = ""
    speculation_risk_level: str = ""       # low | medium | high (speculation only)
    industry_risk: bool = False
    needs_human_review: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Classifier
# ═══════════════════════════════════════════════════════════════════════════════

class ClaimNatureClassifier:
    """Rule-based classifier for claim epistemological nature.

    v2: Weighted-scoring classification with negation window, n-gram fallback,
    and industry-specific high-risk term detection.
    """

    # Scoring weights
    _STRONG_WEIGHT = 2
    _WEAK_WEIGHT = 1
    _NUMERIC_BONUS = 1
    _STRUCTURAL_BONUS = 1
    _CONFLICT_THRESHOLD = 1.3       # top/second < 1.3 → UNKNOWN
    _SPECULATION_OVERRIDE_RATIO = 0.5  # speculation >= fact * ratio → speculation

    def classify(self, claim_text: str, predicate_type: str = "other",
                 industry_code: str = "") -> ClaimNatureResult:
        text = claim_text.strip()

        if len(text) < 5:
            return ClaimNatureResult(
                claim_nature=ClaimNature.UNKNOWN,
                confidence=0.0,
                reason="文本过短(<5字符)，无法判定声明性质",
            )

        text_lower = text.lower()

        # ── 1. Detect all signal words with positions ──────────────────────

        signals = self._detect_signals(text, text_lower)

        # ── 2. Run negation window detection on matched signals ────────────

        negated_any = False
        for cat in ("speculation", "opinion", "fact"):
            for entry in signals[f"{cat}_strong"]:
                if self._detect_negation_window(text, entry["word"], entry["pos"]):
                    entry["negated"] = True
                    negated_any = True
            for entry in signals[f"{cat}_weak"]:
                if self._detect_negation_window(text, entry["word"], entry["pos"]):
                    entry["negated"] = True
                    negated_any = True

        # ── 3. Compute weighted scores ─────────────────────────────────────

        scores = self._compute_scores(signals, text)
        has_any_signal = any(v > 0 for v in scores.values())

        # ── 4. Chinese sentence-final particle check ───────────────────────

        has_spec_particle = any(
            text.rstrip("?？!！。.）)").endswith(p) for p in _CN_SPEC_PARTICLES)
        if has_spec_particle and len(text) > 5:
            scores["speculation"] += self._WEAK_WEIGHT
            signals["speculation_weak"].append({
                "word": "句末语气词:" + text[-1], "pos": len(text) - 1, "negated": False})

        # ── 5. Resolve nature from scores ──────────────────────────────────

        if not has_any_signal and scores["speculation"] == 0:
            return ClaimNatureResult(
                claim_nature=ClaimNature.UNKNOWN,
                confidence=0.0,
                reason="未命中事实/观点/推测信号，无法判定声明性质",
            )

        claim_nature, confidence, resolution_reason = self._resolve_nature(scores)

        if claim_nature == ClaimNature.UNKNOWN:
            return ClaimNatureResult(
                claim_nature=ClaimNature.UNKNOWN,
                confidence=0.0,
                reason=resolution_reason,
            )

        # ── 6. Build matched_signals and signal_categories ─────────────────

        all_matched, categories = self._collect_matched_signals(signals, claim_nature)

        # ── 7. Compute signal_strength ─────────────────────────────────────

        n_strong = len(signals.get(f"{claim_nature.value}_strong", []))
        n_weak = len(signals.get(f"{claim_nature.value}_weak", []))
        # Also count strong/weak from other categories that were present
        for cat in ("speculation", "opinion", "fact"):
            if cat != claim_nature.value:
                n_strong += len(signals.get(f"{cat}_strong", []))
                n_weak += len(signals.get(f"{cat}_weak", []))

        if n_strong > 0 and n_weak > 0:
            signal_strength = "mixed"
        elif n_strong > 0:
            signal_strength = "strong"
        elif n_weak > 0:
            signal_strength = "weak"
        else:
            signal_strength = "none"

        # ── 8. Compute speculation risk level ──────────────────────────────

        risk_level = ""
        if claim_nature == ClaimNature.SPECULATION:
            has_spec_strong = len(signals.get("speculation_strong", [])) > 0
            risk_level = self._assess_speculation_risk(
                predicate_type, has_spec_strong, negated_any)

        # ── 9. Industry high-risk term detection ───────────────────────────

        industry_risk, matched_risk_terms, needs_hr = self._detect_industry_risk(
            text, industry_code, claim_nature, signals)
        if industry_risk:
            all_matched.extend([f"[risk]{t}" for t in matched_risk_terms])
            categories.append("industry_risk")

        # ── 10. needs_human_review determination ───────────────────────────

        needs_hr = needs_hr or self._should_flag_human_review(
            claim_nature, confidence, risk_level, industry_risk, predicate_type)

        # ── 11. Build reason ───────────────────────────────────────────────

        reason_parts = [resolution_reason]
        if negated_any:
            reason_parts.append("含否定语境")
        if risk_level == "high":
            reason_parts.append(f"高风险predicate({predicate_type})推测")
        elif risk_level == "medium":
            reason_parts.append("中等风险推测")
        if industry_risk:
            reason_parts.append(f"行业高风险词: {matched_risk_terms[:3]}")
        if needs_hr:
            reason_parts.append("需人审")

        return ClaimNatureResult(
            claim_nature=claim_nature,
            confidence=confidence,
            matched_signals=all_matched,
            signal_strength=signal_strength,
            negation_detected=negated_any,
            signal_categories=categories,
            reason="; ".join(reason_parts),
            speculation_risk_level=risk_level,
            industry_risk=industry_risk,
            needs_human_review=needs_hr,
        )

    # ── Signal detection ───────────────────────────────────────────────────

    def _detect_signals(self, text: str, text_lower: str) -> dict:
        """Detect all signal words with positions.

        Returns dict with keys: speculation_strong, speculation_weak,
        opinion_strong, opinion_weak, fact_strong, fact_weak.
        Each value is a list of dicts: {word, pos, negated}.
        Sub-signal dedup: if a longer word in strong list matches, its
        substring in weak list is removed (e.g., "最受欢迎" prevents "受欢迎").
        """
        result: dict[str, list[dict]] = {}
        for cat in ("speculation", "opinion", "fact"):
            cn_strong, cn_weak, en_strong, en_weak = _SIGNAL_CONFIG[cat]
            strong_matches = self._match_signals(
                text, text_lower, cn_strong, en_strong)
            weak_matches = self._match_signals(
                text, text_lower, cn_weak, en_weak)

            # Cross-list dedup: remove weak matches that are substrings of strong
            all_strong_words = {m["word"] for m in strong_matches}
            deduped_weak = []
            for wm in weak_matches:
                is_sub = any(
                    wm["word"] != sw and wm["word"] in sw
                    for sw in all_strong_words)
                if not is_sub:
                    deduped_weak.append(wm)

            result[f"{cat}_strong"] = strong_matches
            result[f"{cat}_weak"] = deduped_weak
        return result

    def _match_signals(self, text: str, text_lower: str,
                       cn_list: list[str], en_list: list[str]) -> list[dict]:
        """Match signal words with direct substring or n-gram fallback.

        Returns list of {word, pos, negated} dicts.
        Longer matches take priority: if word A is a substring of word B
        and both match, only the longer word B is kept.
        """
        matches: list[dict] = []
        seen_words: set[str] = set()

        for word in cn_list:
            if word in seen_words:
                continue
            pos = text.find(word)
            matched = pos >= 0
            if not matched:
                matched, pos = self._ngram_match(text, word)
            if matched:
                seen_words.add(word)
                matches.append({"word": word, "pos": max(pos, 0), "negated": False})

        for word in en_list:
            if word in seen_words:
                continue
            pos = text_lower.find(word)
            matched = pos >= 0
            if not matched and " " not in word:
                matched, pos = self._ngram_match(text_lower, word)
            if matched:
                seen_words.add(word)
                matches.append({"word": word, "pos": max(pos, 0), "negated": False})

        # Deduplicate within this list: remove shorter words that are substrings
        sorted_matches = sorted(matches, key=lambda m: len(m["word"]), reverse=True)
        deduped: list[dict] = []
        for m in sorted_matches:
            is_sub = any(
                m["word"] != other["word"] and m["word"] in other["word"]
                for other in sorted_matches)
            if not is_sub:
                deduped.append(m)

        return deduped

    # ── Negation window detection ──────────────────────────────────────────

    @staticmethod
    def _detect_negation_window(text: str, signal_word: str,
                                 signal_pos: int, window: int = 5) -> bool:
        """Check if negation word appears within `window` chars of signal."""
        if signal_pos < 0:
            return False
        win_start = max(0, signal_pos - window)
        win_end = min(len(text), signal_pos + len(signal_word) + window)
        window_text = text[win_start:win_end]
        for neg in _CN_NEGATION:
            if neg in window_text:
                return True
        for neg in _EN_NEGATION:
            if neg in window_text.lower():
                return True
        return False

    # ── n-gram fallback matching ───────────────────────────────────────────

    @staticmethod
    def _ngram_match(text: str, signal_word: str, threshold: float = 0.6
                     ) -> tuple[bool, int]:
        """Character-level bigram+trigram fallback for Chinese fuzzy matching.

        Returns (matched, position) where position is the start of the best
        matching n-gram region, or -1 if no match.
        """
        if len(signal_word) < 3:
            return (False, -1)
        bigrams = [signal_word[i:i + 2] for i in range(len(signal_word) - 1)]
        trigrams = [signal_word[i:i + 3] for i in range(len(signal_word) - 2)]
        ngrams = bigrams + trigrams
        if not ngrams:
            return (False, -1)
        matches = sum(1 for ng in ngrams if ng in text)
        ratio = matches / len(ngrams)
        if ratio >= threshold:
            # Return position of first matching n-gram
            for ng in ngrams:
                pos = text.find(ng)
                if pos >= 0:
                    return (True, pos)
        return (False, -1)

    # ── Weighted scoring ───────────────────────────────────────────────────

    @staticmethod
    def _compute_scores(signals: dict, text: str) -> dict[str, float]:
        """Compute weighted scores for each category.

        score = strong_count * STRONG_WEIGHT + weak_count * WEAK_WEIGHT
                + numeric_bonus + structural_bonus
        Negated signals contribute 0 (deducted from their category).
        """
        scores: dict[str, float] = {"fact": 0, "opinion": 0, "speculation": 0}

        for cat in ("speculation", "opinion", "fact"):
            strong_entries = signals.get(f"{cat}_strong", [])
            weak_entries = signals.get(f"{cat}_weak", [])
            for e in strong_entries:
                if not e.get("negated", False):
                    scores[cat] += ClaimNatureClassifier._STRONG_WEIGHT
            for e in weak_entries:
                if not e.get("negated", False):
                    scores[cat] += ClaimNatureClassifier._WEAK_WEIGHT

        # Fact bonuses
        has_numeric = bool(_FACT_NUMERIC_RE.search(text))
        has_structural = any(p.search(text) for p in _FACT_STRUCTURAL_PATTERNS)
        if has_numeric:
            scores["fact"] += ClaimNatureClassifier._NUMERIC_BONUS
        if has_structural:
            scores["fact"] += ClaimNatureClassifier._STRUCTURAL_BONUS

        return scores

    # ── Nature resolution ──────────────────────────────────────────────────

    @classmethod
    def _resolve_nature(cls, scores: dict[str, float]
                        ) -> tuple[ClaimNature, float, str]:
        """Resolve claim nature from weighted scores with conflict detection."""
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_cat, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0

        if top_score == 0:
            return (ClaimNature.UNKNOWN, 0.0,
                    "未命中事实/观点/推测信号，无法判定声明性质")

        spec_score = scores.get("speculation", 0)
        fact_score = scores.get("fact", 0)

        # Speculation tiebreaker: speculation dominates opinion in ties
        # "可能成为最好的品牌" — spec and opinion tied, hedging wins
        if (spec_score > 0 and spec_score == scores.get("opinion", 0)
                and spec_score >= fact_score):
            top_cat = "speculation"
            top_score = spec_score
            other_scores = {k: v for k, v in scores.items() if k != "speculation"}
            second_score = max(other_scores.values()) if other_scores else 0
        # Override: strong speculation dominates weak-only fact signals
        # "预计营收增长50%" should be speculation, not UNKNOWN
        elif spec_score > 0 and fact_score > 0 and spec_score >= fact_score:
            top_cat = "speculation"
            top_score = spec_score
            other_scores = {k: v for k, v in scores.items() if k != "speculation"}
            second_score = max(other_scores.values()) if other_scores else 0
        elif (top_cat == "fact" and spec_score > 0
              and spec_score >= fact_score * cls._SPECULATION_OVERRIDE_RATIO):
            top_cat = "speculation"
            top_score = spec_score
            other_scores = {k: v for k, v in scores.items() if k != "speculation"}
            second_score = max(other_scores.values()) if other_scores else 0

        # Signal conflict: skip after speculation override (override is intentional)
        # Only check conflict when top cat is the original (non-overridden) winner
        is_overridden = (top_cat == "speculation"
                         and ranked[0][0] != "speculation"
                         and top_score > 0)
        if not is_overridden and second_score > 0 and (top_score / second_score) < cls._CONFLICT_THRESHOLD:
            return (ClaimNature.UNKNOWN, 0.0,
                    f"信号冲突(FACT={scores['fact']:.0f} "
                    f"OPINION={scores['opinion']:.0f} "
                    f"SPECULATION={scores['speculation']:.0f})，无法裁定")

        # Confidence: top / (top + second) * 0.9, clamped
        if second_score == 0:
            confidence = 0.85 if top_score >= 3 else 0.65
        else:
            raw_conf = (top_score / (top_score + second_score)) * 0.9
            confidence = max(0.55, min(0.95, raw_conf))

        nature_map = {
            "fact": ClaimNature.FACT,
            "opinion": ClaimNature.OPINION,
            "speculation": ClaimNature.SPECULATION,
        }
        cn = nature_map.get(top_cat, ClaimNature.UNKNOWN)

        reason = f"命中{top_cat}信号(score={top_score:.0f})"
        return (cn, round(confidence, 2), reason)

    # ── Collect matched signals ────────────────────────────────────────────

    @staticmethod
    def _collect_matched_signals(signals: dict, claim_nature: ClaimNature
                                 ) -> tuple[list[str], list[str]]:
        """Gather all matched signal words and categories."""
        all_matched: list[str] = []
        categories: list[str] = [claim_nature.value]

        for cat in ("speculation", "opinion", "fact"):
            strong_entries = signals.get(f"{cat}_strong", [])
            weak_entries = signals.get(f"{cat}_weak", [])
            for e in strong_entries:
                tag = e["word"]
                if e.get("negated"):
                    tag = f"[neg]{tag}"
                all_matched.append(tag)
            for e in weak_entries:
                tag = e["word"]
                if e.get("negated"):
                    tag = f"[neg]{tag}"
                all_matched.append(tag)
            if strong_entries:
                categories.append(f"{cat}_strong")
            if weak_entries:
                categories.append(f"{cat}_weak")

        if any(e.get("negated") for e in
               (signals.get("speculation_strong", []) +
                signals.get("speculation_weak", []) +
                signals.get("opinion_strong", []) +
                signals.get("opinion_weak", []))):
            categories.append("negated")

        return (all_matched, categories)

    # ── Speculation risk assessment ────────────────────────────────────────

    @staticmethod
    def _assess_speculation_risk(predicate_type: str, has_strong_signal: bool,
                                  has_negation: bool) -> str:
        if predicate_type in HIGH_RISK_PREDICATES:
            return "high"
        if predicate_type in LOW_RISK_PREDICATES:
            return "low"
        if has_strong_signal:
            return "medium"
        return "low"

    # ── Industry risk detection ────────────────────────────────────────────

    @classmethod
    def _detect_industry_risk(cls, text: str, industry_code: str,
                               claim_nature: ClaimNature,
                               signals: dict) -> tuple[bool, list[str], bool]:
        """Check industry-specific high-risk terms.

        Returns: (has_risk, matched_terms, needs_human_review).
        """
        if not industry_code or claim_nature == ClaimNature.FACT:
            return (False, [], False)

        risk_keys = _INDUSTRY_CODE_TO_RISK_KEY.get(industry_code, [])
        if not risk_keys:
            return (False, [], False)

        all_terms: list[str] = []
        for rk in risk_keys:
            all_terms.extend(_INDUSTRY_HIGH_RISK_TERMS.get(rk, []))

        if not all_terms:
            return (False, [], False)

        matched = [t for t in all_terms if t in text]
        if not matched:
            return (False, [], False)

        needs_hr = False
        if claim_nature == ClaimNature.SPECULATION:
            needs_hr = True  # Speculation + industry risk term → human review
        elif claim_nature == ClaimNature.OPINION:
            # Opinion + absolute keyword + industry risk → human review
            has_absolute = any(
                s["word"] in _ABSOLUTE_OPINION_KEYWORDS
                for s in signals.get("opinion_strong", []))
            if has_absolute:
                needs_hr = True

        return (True, matched, needs_hr)

    # ── Human review flag ──────────────────────────────────────────────────

    @staticmethod
    def _should_flag_human_review(claim_nature: ClaimNature, confidence: float,
                                   speculation_risk: str, industry_risk: bool,
                                   predicate_type: str) -> bool:
        if claim_nature == ClaimNature.UNKNOWN:
            return True
        if confidence < 0.6:
            return True
        if speculation_risk == "high":
            return True
        if industry_risk and speculation_risk == "medium":
            return True
        if claim_nature == ClaimNature.SPECULATION and predicate_type in HIGH_RISK_PREDICATES:
            return True
        return False


# Module-level instance for convenience
classifier = ClaimNatureClassifier()


def classify_claim_nature(claim_text: str, predicate_type: str = "other",
                          industry_code: str = "") -> ClaimNatureResult:
    """Convenience function for claim nature classification.

    Args:
        claim_text: The claim text fragment (Chinese and/or English).
        predicate_type: The predicate domain (identity, product, etc.)
        industry_code: The brand's industry code for risk term detection.

    Returns:
        ClaimNatureResult with nature, confidence, signals, and reason.
    """
    return classifier.classify(claim_text, predicate_type, industry_code)
