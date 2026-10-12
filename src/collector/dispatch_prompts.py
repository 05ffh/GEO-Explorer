"""子 agent 判定调度外壳（2026-09-18 固化，防主 agent 手写 prompt 漂移）。

分层：**判定规范**（_HIT_SPEC/_ATTRIBUTION_SPEC）已固化在代码并随待判文件 `spec` 字段
自动下发；**调度外壳**（你是谁/读哪个文件/输出格式）此前由主 agent 每次手写，容易漂移
（不同轮次/不同人派发措辞不一致）——本模块把它固化成模板，主 agent 派发时 `format()`
填充平台名+文件路径即可，判定依据恒为待判文件里的固化 spec。

子 agent 约束（历史拍板）：无写文件权限 → 回复吐完整 JSON，主 agent 落盘。
"""

HIT_DISPATCH = (
    "你是命中判定员，负责判定【{platform} 平台】的命中层问题。\n"
    "## 输入\n"
    "读取文件 `{path}`。它是 JSON：`platforms` 下每个平台是待判题 {{qid: {{question, answer, prefill}}}}"
    "（你只判 `platforms.{platform}` 下的题）；`spec` 是命中判定规范（**必须严格按它执行**，"
    "含甲方身份声明、推荐名单完整性、scene 复合局限、reject_if_absent 判据）。\n"
    "## 判定要求\n"
    "对每题读 AI 原始回答（answer），严格按 spec 输出：recommendation（recommend/mention/exclude/absent）、"
    "scene（dim+val，复合场景只记主维度）、referred_content（AI 引用的甲方内容）、"
    "has_hotel_recommendations（bool，必填）、hotels_recommended（推荐名单，**必须完整列出**）、"
    "hotels_mentioned（提及名单）。\n"
    "## 输出格式（严格遵守）\n"
    "最终回复**只输出** {platform} 平台的 patch JSON，形如：\n"
    "```json\n{{\"{platform}\": {{\"<qid>\": {{\"recommendation\": \"...\", \"scene\": {{\"dim\": \"...\", \"val\": \"...\"}}, "
    "\"referred_content\": [], \"has_hotel_recommendations\": true, "
    "\"hotels_recommended\": [], \"hotels_mentioned\": []}}}}\n```\n"
    "- 覆盖全部命中题，qid 与文件一致；无其他文字/解释\n"
    "- 你没有写文件权限，JSON 直接吐在回复里"
)

ATTRIBUTION_DISPATCH = (
    "你是归因劣势提取判定员，负责判定【{platform} 平台】的归因题。\n"
    "## 输入\n"
    "读取文件 `{path}`。它是 JSON：`platforms` 下每个平台是待判题 {{qid: {{question, answer, scenario}}}}"
    "（你只判 `platforms.{platform}` 下的题）；`client_context` 是甲方两级接地"
    "（【甲方事实清单】= 判决第一依据 +【甲方页面内容】= 原文佐证 +【AI 引用过的甲方内容】+ 档位）；"
    "`spec` 是归因判定规范（**必须严格按它执行**，含三态裁决顺序、evidence 逐字约束、"
    "优势维度主题全覆盖、劣势判定铁律）。\n"
    "## 判定要求\n"
    "对每题读 AI 原始回答（answer），严格按 spec 执行：\n"
    "1. pick：AI 最终推荐谁（competitor/client/tie/no_choice）\n"
    "2. client_disadvantage_dims：AI 认为甲方不如竞品的维度。每条 dim（枚举内）+ evidence"
    "（**AI 原话逐字，禁加前缀/注释/改写**）+ corpus_fact（资产类维度必填：先查【甲方事实清单】"
    "无则回【甲方页面内容】，none/refutes/confirms 三选一）。type 不输出（系统派生）。\n"
    "3. client_advantage_dims：AI 认为甲方占优的维度（平衡题必填），dim + evidence（主题全覆盖，同维度合并）。\n"
    "## 输出格式（严格遵守）\n"
    "最终回复**只输出** {platform} 平台的 patch JSON，形如：\n"
    "```json\n{{\"{platform}\": {{\"<qid>\": {{\"pick\": \"...\", "
    "\"client_disadvantage_dims\": [{{\"dim\": \"...\", \"corpus_fact\": \"...\", \"evidence\": \"...\"}}], "
    "\"client_advantage_dims\": [{{\"dim\": \"...\", \"evidence\": \"...\"}}]}}}}\n```\n"
    "- 覆盖全部题，qid 与文件一致；无其他文字/解释\n"
    "- 你没有写文件权限，JSON 直接吐在回复里"
)
