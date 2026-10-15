"""从子agent 任务输出（JSONL 转录）里提取最终结果 JSON —— 程序化，替代主 agent 手抄。

用法：
  python scripts/extract_subagent_result.py <子agent输出.output> <out.json>

第一性原理：「子agent 输出 → 系统摄入」边界天生有损——子agent 是生成模型、不保证合法 JSON；
主 agent 手抄必然出错。故摄入侧固化本工具：
  1. 取最后一条 `result` 记录（或最后一条 assistant 文本），剥 ```json 围栏；
  2. **宽容解析**：LLM 常把 AI 原话里的半角引号直接塞进 JSON 字符串（未转义）→ 先严格解析；
     失败则把「内容引号」（既不在开引号位、也不在闭引号位的 `"`）**转义为 \\" 再解析**
     —— 解析后字符串值原文一字不改（引号保留）；
  3. 仍失败 → 打印出错位置附近片段并**退出 1**（绝不静默产出错误数据）。
主 agent 终审（G1/G2 结构化复核）仍在 apply 前进行——本工具只替换「手抄」这一环。
"""
import json
import re
import sys

_OPEN_PREV = set(' \t\n:[{,')      # 开引号合法前驱
_CLOSE_NEXT = set(' \t\n:,}]')     # 闭引号合法后继


def _escape_content_quotes(s: str) -> str:
    """把「内容引号」（既非开引号位也非闭引号位）转义 → 使 JSON 合法，且解析后原值不变。"""
    out = []
    n = len(s)
    for i, ch in enumerate(s):
        if ch == '"':
            prev = s[i - 1] if i > 0 else ''
            nxt = s[i + 1] if i + 1 < n else ''
            is_open = prev == '' or prev in _OPEN_PREV
            is_close = nxt == '' or nxt in _CLOSE_NEXT
            if not is_open and not is_close:
                out.append('\\"')
                continue
        out.append(ch)
    return ''.join(out)


def extract(path: str) -> dict:
    res = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("type") == "result" and isinstance(r.get("result"), str):
            res = r["result"]
        elif r.get("type") == "assistant":
            for c in (r.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "text" and (c.get("text") or "").strip():
                    res = c["text"]
    if not res:
        raise SystemExit(f"未找到子agent 结果文本：{path}")
    t = re.sub(r"^```(?:json)?\s*", "", res.strip())
    t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        try:
            d = json.loads(_escape_content_quotes(t))
            print("  [宽容解析] 已转义未转义的内容引号（原文保留）", file=sys.stderr)
            return d
        except json.JSONDecodeError as e2:
            i = e2.pos
            raise SystemExit(f"JSON 非法且自动修复失败：{e2.msg} @ char {i}\n"
                             f"  附近片段：...{t[max(0, i - 80):i + 80]}...")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    d = extract(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False)
    print("OK ->", sys.argv[2], {p: len(v) for p, v in d.items()})


if __name__ == "__main__":
    main()
