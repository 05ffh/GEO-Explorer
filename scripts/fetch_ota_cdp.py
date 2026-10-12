"""CDP 抓取 OTA 甲方详情页 → 甲方事实语料（spec「CDP 采集能力」+ 三平台区块规格定稿）。

背景（第一性原理）：国内 OTA（携程/美团/飞猪）JS 渲染 + 反爬，httpx 抓不到正文 →
现有语料偏国际 OTA + 官网，而 AI 实际点名的是国内 OTA。CDP 操控真实浏览器拿渲染后页面补这个缺口。

策略（B + 白名单 + 边界切分，spec 定稿）：
  抽取器只在规格列出的边界名处切分（未列出的可见标题被吸收进所在区块，由
  filter_client_facts 清理 → 规避 nav 同名歧义）；首个边界之前 = 事实区。
  区块文本用 DOM Range 取两可见标题之间文本（可见标题自动排除 hidden nav 锚点）。

落库契约（缺一不可，否则下游读不到）：
  query 含城市（build_grounding_corpus 的 `query LIKE '%城市%'` 过滤）
  content_text 非空 / content_layer='fact' / source_tier=T1 / search_backend='cdp'

用法：
  PYTHONPATH=. .venv/bin/python scripts/fetch_ota_cdp.py <run_id> [--platform ctrip] [--hotel-id 429558] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import urllib.request

import websocket
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.collector.content_filter import filter_client_facts
from src.config import settings
from src.gt.source_tier import classify_source_tier

CDP_PORT = 9223

# ---- 平台规格（白名单 + 边界切分）----
# boundaries 有序：只在列出的边界名处切分；类型 fact=提取 / opinion=边界不提取 / ignore=不提取。
# keep_until：区块内遇到该独立行就截断（裁长尾噪音，如携程「地点」只取「交通」子区）。
SPECS: dict[str, dict] = {
    "ctrip": {
        "domain": "ctrip.com",
        "url_tpl": "https://hotels.ctrip.com/hotels/{hotel_id}.html",
        "default_type": "fact",  # 首个边界之前 = 事实区（地址/亮点/评分/房型）
        "wait_for": "附近的酒店",  # 末区块标记：出现才算渲染完（防分阶段渲染漏区块）
        # 评分区展示的「精选点评」样例（观点）→ 区间剔除（显示所有N条点评 … 附近）
        "default_opts": {"drop_spans": [(r"^显示所有\s*[\d,]+\s*条点评$", r"^附近$")]},
        "boundaries": [
            # 点评区头部（评分 4.6 + 分维度 卫生/设施/环境/服务）是量化劣势证据 → 并入 fact；
            # 「热门提及」之后的点评正文/标签为观点 → 丢弃。
            ("点评", "opinion", {"fact_head_until": "热门提及"}),
            ("地点", "fact", {"keep_until": "购物"}),  # 只取交通子区，丢购物/景点/美食 POI 长尾
            ("服务及设施", "fact", {}),
            ("酒店政策", "fact", {}),
            ("酒店简介", "fact", {}),
            ("订房必读", "fact", {}),
            ("附近的酒店", "ignore", {}),
        ],
    },
}

# 可见标题（h1-h4，offsetParent!=null 排除 hidden nav 锚点）+ Range 取相邻标题间文本。
# 末段 open-ended 会吞 footer/隐藏文本 → slice 封顶（末段多为 ignore，不提取）。
_EXTRACT_JS = r"""(function(){
  // 排除吸顶导航容器内的标题（position:fixed/sticky）：滚到下方时导航变可见 → 其"点评/
  // 地点/服务及设施"被误当区块边界，导致点评正文漏进 fact 区。语义信号比硬编码类名稳。
  function inSticky(h){var n=h;for(var i=0;i<6&&n;i++){var p='';try{p=getComputedStyle(n).position;}catch(e){}if(p==='fixed'||p==='sticky')return true;n=n.parentElement;}return false;}
  var hs=[].slice.call(document.querySelectorAll('h1,h2,h3,h4')).filter(function(h){return h.offsetParent!==null && !inSticky(h);});
  // 文本节点遍历（每个文本节点一行）——Range.toString() 会压成一行使行级过滤失效。
  function rng(a,b){var r=document.createRange();r.setStartAfter(a);
    if(b){r.setEndBefore(b);}else{r.setEnd(document.body,document.body.childNodes.length);}
    var it=document.createNodeIterator(r.commonAncestorContainer,NodeFilter.SHOW_TEXT,null),p=[],n;
    while(n=it.nextNode()){try{if(!r.intersectsNode(n))continue;}catch(e){continue;}
      var t=(n.nodeValue||'').trim();if(t)p.push(t);}
    return p.join('\n').slice(0,20000);}
  var out=[];
  for(var i=0;i<hs.length;i++){out.push({name:hs[i].innerText.trim(),text:rng(hs[i],hs[i+1]||null)});}
  return JSON.stringify(out);
})()"""

# 房型卡提取（DOM，绕开文本流）：一个房型 = 一个 <section>，innerText = "¥价 房型名 规格 UI…"
# → {name, price, bed}。文本流里价/名/规格交错无法配对，按卡片取才精确（2026-10-10）。
# 不依赖 class（hash 易变），用"文本以 ¥N 开头"选卡。
_ROOM_CARDS_JS = r"""(function(){
  var out=[], seen={};
  // 亮点标签的悬浮提示框描述（"每日的第一缕晨曦…客房内…"）含"房"被误当房型 → 排除 tooltip 祖先
  function inTooltip(e){var n=e;for(var i=0;i<5&&n;i++){if((''+n.className).indexOf('tooltip')>=0)return true;n=n.parentElement;}return false;}
  // 房型名元素（最深、短、含"房/套房/公寓"）为锚
  var cands=[].slice.call(document.querySelectorAll('div,span,a,h1,h2,h3,h4')).filter(function(e){
    var t=(e.innerText||'').trim();
    return /(房|套房|公寓)/.test(t) && t.length>=6 && t.length<=40 && e.children.length<=1
           && t.indexOf('¥')<0 && t.indexOf('￥')<0 && t.indexOf('\n')<0
           && !/政策|入住|退房|加床|：|展示|查看|店|\(/.test(t) && !inTooltip(e);
  });
  for(var k=0;k<cands.length;k++){
    var t=(cands[k].innerText||'').trim();
    // 该房型卡 = 含该名的最近含¥祖先（SECTION 摘要卡）→ 取最低价（起价，稳定准确）
    var n=cands[k], card=null;
    for(var i=0;i<8&&n;i++){ if(/[¥￥]\s*[\d,]+/.test(n.innerText||'')){ card=n; break; } n=n.parentElement; }
    if(!card) continue;
    var ct=(card.innerText||'').replace(/\s+/g,' ');
    var nums=(ct.match(/[¥￥]\s*[\d,]+/g)||[]).map(function(x){return parseInt(x.replace(/[^\d]/g,''),10)}).filter(function(x){return x>0});
    if(!nums.length) continue;
    var bed=(ct.match(/[1-9]张[^ ]*床/)||[''])[0];
    var area=(ct.match(/\d[\d–\-]*平方米\s*\|\s*\d[\d–\-]*层/)||[''])[0].replace(/\s+/g,'');
    if(seen[t]!==undefined){  // 同名（头部推荐卡 vs 房型列表）→ 补全缺失字段（头部卡无面积/楼层）
      var prev=out[seen[t]];
      if(!prev.area && area) prev.area=area;
      if(!prev.bed && bed) prev.bed=bed;
      continue;
    }
    seen[t]=out.length;
    out.push({name:t, price:'¥'+Math.min.apply(null,nums), bed:bed, area:area});
  }
  return JSON.stringify(out);
})()"""

# 展开链接：点击"展示其余N个房型"渲染全部房型（未展开时 DOM 只有首个房型）。
_EXPAND_JS = r"""(function(){
  var re=/^(展示其余\d+个房型|查看更多房型|查看其他房型)$/;
  var els=[].slice.call(document.querySelectorAll('a,span,div,button,p'));
  for(var i=0;i<els.length;i++){
    var e=els[i];
    if(e.dataset&&e.dataset.cdpClicked) continue;  // 已点过的链接跳过（防重复点同一链接）
    if(re.test((e.innerText||'').trim()) && e.children.length<=1){
      if(e.dataset) e.dataset.cdpClicked='1';
      e.scrollIntoView({block:'center'});
      var r=e.getBoundingClientRect();
      return JSON.stringify({x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2),t:e.innerText.trim()});
    }
  }
  return 'none';
})()"""


# ---- CDP ----
def _tabs() -> list[dict]:
    return json.load(urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json"))


def _cmd(ws, i: int, method: str, params: dict | None = None) -> dict:
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == i:
            return m


def _open_tab(domain: str) -> dict:
    """复用已开的同域 tab（带登录态）；无则新建。"""
    for t in _tabs():
        if t.get("type") == "page" and domain in t.get("url", ""):
            return t
    req = urllib.request.Request(f"http://localhost:{CDP_PORT}/json/new?about:blank", method="PUT")
    return json.load(urllib.request.urlopen(req))


def _click_expand(ws) -> list[str]:
    """点"展示其余N个房型"展开全部房型（真实鼠标事件 Input 域，更接近人为）。返回点击的链接文本。"""
    clicked = []
    for k in range(6):
        try:
            r = _cmd(ws, 40 + k, "Runtime.evaluate", {"expression": _EXPAND_JS, "returnByValue": True})
            v = r["result"]["result"].get("value", "none")
            if v == "none":
                break
            pos = json.loads(v)
            for typ in ("mouseMoved", "mousePressed", "mouseReleased"):
                _cmd(ws, 50 + k, "Input.dispatchMouseEvent",
                     {"type": typ, "x": pos["x"], "y": pos["y"], "button": "left", "clickCount": 1})
            time.sleep(1.5)
            clicked.append(pos["t"])
        except Exception:  # 点击后页面若重排/WS 抖动 → 停止展开，用已渲染内容
            break
    return clicked


def fetch(url: str, domain: str, wait_for: str = "") -> tuple[list[dict], str, list[dict]]:
    """导航 + 等渲染 + 抽取区块。返回 (regions, title)。

    等待判据：innerText 长度稳定 **且** wait_for 标记已出现（OTA 分阶段渲染，仅看长度
    会在部分渲染时就稳定 → 漏区块；2026-10-10 实测偶发）。
    """
    tab = _open_tab(domain)
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=120, suppress_origin=True)
    try:
        _cmd(ws, 1, "Runtime.enable")
        _cmd(ws, 2, "Page.enable")
        _cmd(ws, 3, "Page.navigate", {"url": url})
        has_expr = (f"document.body.innerText.includes({json.dumps(wait_for)})"
                    if wait_for else "true")
        last, stable = -1, 0
        for _ in range(40):
            time.sleep(2)
            r = _cmd(ws, 10, "Runtime.evaluate",
                     {"expression": f"JSON.stringify([document.body?document.body.innerText.length:0,{has_expr}])",
                      "returnByValue": True})
            n, has = json.loads(r["result"]["result"].get("value", "[0,false]"))
            stable = stable + 1 if n == last else 0
            if stable >= 1 and n > 200 and has:
                break
            last = n
        expanded = _click_expand(ws)
        print(f"  [展开点击] {expanded or '无'}")
        if expanded:
            # 展开后滚回顶部：滚动会让吸顶导航（概览/房间/…）变可见 → 被误当区块边界。
            # 展开点击触发的 React 重渲染会把页面再次滚下去，单次 scrollTo 被覆盖 → 轮询到稳定。
            for _ in range(8):
                _cmd(ws, 14, "Runtime.evaluate",
                     {"expression": "window.scrollTo(0,0)", "returnByValue": True})
                time.sleep(0.5)
                r = _cmd(ws, 15, "Runtime.evaluate",
                         {"expression": "Math.round(window.scrollY)", "returnByValue": True})
                if r["result"]["result"].get("value") == 0:
                    break
        r = _cmd(ws, 11, "Runtime.evaluate", {"expression": _EXTRACT_JS, "returnByValue": True})
        regions = json.loads(r["result"]["result"].get("value", "[]"))
        r = _cmd(ws, 13, "Runtime.evaluate", {"expression": _ROOM_CARDS_JS, "returnByValue": True})
        cards = json.loads(r["result"]["result"].get("value", "[]"))
        t = _cmd(ws, 12, "Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
        return regions, t["result"]["result"].get("value", ""), cards
    finally:
        ws.close()


# ---- 切分（白名单 + 边界）----
# OTA 预订 UI / 地图 UI（CDP innerText 特有噪声，非甲方事实）——整行匹配才丢。
_OTA_UI = re.compile(
    r"^(无早餐|不含早|含早餐|不可取消|可免费取消|免费取消|到店付|在线付|立即确认|需担保|"
    r"限时抢购|特惠一口价|黄金贵宾价|今日价格|选择房间|查看更多选项|查看其他房型|房量紧张|"
    r"预订|可住人数|房间详情|房型摘要|所有设施|"
    r"在地图上查看|显示地图|收藏|将鼠标悬浮在日期上查看节假日信息|所有日期均为当地时间|"
    r"酒店套餐|可订|在线付款|到店付款|免费Wi-Fi上网|免费有线宽带|起|1晚|1小时内确认|"
    r"概览|房间|点评|服务及设施|政策|地点|大床房|双床房|亲子主题房|"
    r"展示额外\d+个房型价格（¥[\d,]+起）|展示其余\d+个房型|以下房间可满足您的部分要求：)$"
    r"|^优惠\d+$|^仅剩\d+间$|^\d+份早餐$|^\d+间, \d+成人.*$|"
    r"^入住当天.*可免费取消$|^订单确认后.*免费取消$|^到店付.*需担保$|^\d{1,2}月\d{1,2}日.*$"
)

# 标签/值被拆成独立文本节点（"室内泳池"/"免费"、"7-11岁儿童"/"¥70/人"、"南门兜地铁站"/"310米"）
# → 值行并回上一行，恢复"标签+值"的自然形态。
# 前缀（每天/每人）与括号距离（（4.0公里））也算纯值：DOM 实测"专车接机"+“每天¥770"、
# "儿童乐园"+"每人¥228"、"地标: 上下杭"+"（4.0公里）"皆为相邻节点——不并回则丢主语/被去重丢。
_VALUE_ONLY = re.compile(
    r"^(?:每天|每人|每晚|每次)?(?:免费|收费|[¥￥][\d,]+(?:/人|/间|/晚)?|\d+元)$"
    r"|^（?\d+(?:\.\d+)?\s*(?:米|千米|公里|km)）?$")


def _merge_values(txt: str) -> str:
    out: list[str] = []
    for line in txt.split("\n"):
        s = line.strip()
        if _VALUE_ONLY.match(s) and out:
            out[-1] = out[-1].rstrip() + s
        else:
            out.append(line)
    return "\n".join(out)


def _strip_noise(txt: str) -> str:
    """丢隐藏文本（SSR JSON/script）+ OTA 预订/地图 UI 行 + 房型套餐构成文案。"""
    out = []
    for line in txt.split("\n"):
        s = re.sub(r"^[·•]\s*", "", line.strip())  # 剥前导装饰点（设施图片角标 "·宴会厅"）
        if not s:
            continue
        if '{"' in line or '":"' in line or s.startswith(("{", "[")):
            continue
        if _OTA_UI.match(s):
            continue
        if "份+" in s or "份/天" in s:  # 房型套餐构成文案（营销，非甲方属性事实）
            continue
        out.append(s)
    return "\n".join(out)


def _keep_until(txt: str, marker: str) -> str:
    out = []
    for line in txt.split("\n"):
        if line.strip() == marker:
            break
        out.append(line)
    return "\n".join(out)


def segment(regions: list[dict], spec: dict) -> list[tuple[str, str]]:
    """区块序列 → [(type, text)]（按规格边界切分）。

    `__TOP__`（首个可见标题之前 = 头部导航/SSR 噪声）恒丢弃。
    opinion 段可带 `fact_head_until`：头部（评分等结构化数值）并入 fact，其余（点评正文）丢弃。
    """
    bmap = {b[0]: b for b in spec["boundaries"]}
    segs: list[tuple[str, str]] = []

    def emit(t: str, opts: dict, txt: str) -> None:
        txt = _apply_opts(txt, opts)
        hu = opts.get("fact_head_until")
        if t == "opinion" and hu:
            head = " ".join(s.strip() for s in _keep_until(txt, hu).split("\n") if s.strip())
            if head:
                segs.append(("fact", head))
            return
        segs.append((t, txt))

    cur_type, cur_opts, cur = spec["default_type"], spec.get("default_opts", {}), []
    for reg in regions:
        if reg["name"] == "__TOP__":
            continue
        b = bmap.get(reg["name"])
        if b is not None:
            if cur or segs:
                emit(cur_type, cur_opts, "\n".join(cur))
            cur_type, cur_opts, cur = b[1], b[2], [_strip_noise(reg["text"])]
        else:
            cur.append(_strip_noise(reg["text"]))
    emit(cur_type, cur_opts, "\n".join(cur))
    return segs


def _drop_spans(txt: str, spans: list) -> str:
    """剔除区间 [start行, end行) —— 双 marker 都命中才剔（缺任一则不动，安全）。

    用途：区块内的观点区间（如携程评分区展示的「精选点评」样例）。
    """
    lines = txt.split("\n")
    for start_pat, end_pat in spans:
        si = next((i for i, ln in enumerate(lines) if re.match(start_pat, ln.strip())), None)
        if si is None:
            continue
        ei = next((i for i in range(si + 1, len(lines)) if re.match(end_pat, lines[i].strip())), None)
        if ei is None:
            continue
        del lines[si:ei]
    return "\n".join(lines)


def _apply_opts(txt: str, opts: dict) -> str:
    if opts.get("keep_until"):
        txt = _keep_until(txt, opts["keep_until"])
    if opts.get("drop_spans"):
        txt = _drop_spans(txt, opts["drop_spans"])
    return txt


def _render_room_cards(cards: list[dict]) -> str:
    """房型卡 → "房型名 ¥价（床型｜面积楼层）" 行（精确配对，含规格）。"""
    def spec(c: dict) -> str:
        parts = [x for x in (c.get("bed"), c.get("area")) if x]
        return f"（{'｜'.join(parts)}）" if parts else ""
    return "\n".join(f"{c['name']} {c['price']}{spec(c)}" for c in cards)


# 房型区规格残渣：床型行（"2张1.2米单人床"）、面积楼层行（"40平方米 | 6-20层"）——无主语，已并入卡片
_SPEC_FRAG = re.compile(r"^[1-9]张[^ ]*床|^\d[\d–\-]*平方米")

# 房型 rate-plan 文案（会员价/含餐价/Wi-Fi 价/人数价）——随酒店而异，卡片子树外的独立 rate-box
# 也会出现（世茂洲际实测）→ 关键词兜底（这些词永不构成甲方事实）。
_RATE_PLAN = re.compile(r"会员价|早餐及晚餐|份早餐|Wi-?Fi免费[¥￥]|儿童早餐|有窗|无窗|封闭窗|^\d+[¥￥][\d,]+$")


def _drop_room_lines(txt: str, names: set[str]) -> str:
    """丢文本流里的房型区噪声：房型名行 + 多价乱价行 + 无主语规格残渣（房型已由卡片精确出）。"""
    out = []
    for line in txt.split("\n"):
        s = line.strip()
        if s in names or _SPEC_FRAG.match(s) or _RATE_PLAN.search(s):
            continue
        if len(re.findall(r"[¥￥][\d,]+", s)) >= 2:  # 多价拼一行（房型区乱价）
            continue
        out.append(line)
    return "\n".join(out)


def build_content_text(regions: list[dict], spec: dict,
                       cards: list[dict] | None = None) -> tuple[str, list[str]]:
    """区块 → 过滤后甲方事实（content_text）+ 命中的边界名（校验用）。

    cards（房型卡）非空时：文本流里的房型噪声丢弃，房型改由卡片行精确给出（房型名 + 价）。
    """
    segs = segment(regions, spec)
    found = {b[0] for b in spec["boundaries"]} & {r["name"] for r in regions}
    fact = "\n".join(t for typ, t in segs if typ == "fact")
    body = filter_client_facts(_merge_values(fact))
    if cards:
        body = _drop_room_lines(body, {c["name"] for c in cards})
        body = _render_room_cards(cards) + "\n" + body
    return body, sorted(found)


# ---- 落库 ----
async def detect_hotel_id(db, brand_id, spec) -> str | None:
    """从语料已存 URL 里认领 hotelId（如 hotels.ctrip.com/hotels/429558.html）。"""
    rows = (await db.execute(text(
        "SELECT url FROM search_results WHERE brand_id=:b AND url LIKE :p LIMIT 50"),
        {"b": brand_id, "p": f"%{spec['domain']}%"})).fetchall()
    import re
    pat = re.compile(r"/hotels?/(\d+)\.html")
    for (u,) in rows:
        m = pat.search(u or "")
        if m:
            return m.group(1)
    return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--platform", default="ctrip", choices=list(SPECS))
    ap.add_argument("--hotel-id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    spec = SPECS[args.platform]

    engine = create_async_engine(settings.database_url, connect_args={"timeout": 5})
    async with engine.begin() as db:
        row = (await db.execute(text(
            "SELECT brand_id, organization_id, city FROM collection_runs WHERE id=:r"),
            {"r": args.run_id})).fetchone()
        if not row:
            print(f"错误: run {args.run_id} 不存在")
            return 1
        brand_id, org_id, city = row
        brand_name = (await db.execute(text("SELECT name FROM brands WHERE id=:b"),
                                       {"b": brand_id})).scalar() or ""

        hotel_id = args.hotel_id or await detect_hotel_id(db, brand_id, spec)
        if not hotel_id:
            print(f"错误: 未找到 {args.platform} hotelId（用 --hotel-id 指定）")
            return 1
        url = spec["url_tpl"].format(hotel_id=hotel_id)
        print(f"[{args.platform}] run={args.run_id[:8]} brand={brand_name} city={city} hotelId={hotel_id}")
        print(f"  URL: {url}")

        regions, title, cards = fetch(url, spec["domain"], spec.get("wait_for", ""))
        content_text, found = build_content_text(regions, spec, cards)

        # 健全性检查：边界名命中 + 事实非空
        expected = [b[0] for b in spec["boundaries"] if b[1] != "ignore"]
        missing = [n for n in expected if n not in found]
        print(f"  title: {title[:60]}")
        print(f"  区块: {[r['name'] for r in regions]}")
        print(f"  命中边界: {found}  缺: {missing or '无'}")
        print(f"  content_text: {len(content_text)} 字")
        if not content_text:
            print("  ✗ 事实为空 → 页面结构可能变了，不落库")
            return 1
        if missing:
            print(f"  ⚠ 期望边界缺失 {missing}（页面可能改版，人工确认）")

        if args.dry_run:
            print(f"\n--- 房型卡（{len(cards)}）---")
            for c in cards:
                print(f"    {c['name']}  {c['price']}  {c.get('bed', '')}")
            print("\n--- 分段 ---")
            for typ, t in segment(regions, spec):
                print(f"    [{typ:7s}] {len(t):6d} 字 | {t.strip()[:70]!r}")
            print("\n--- content_text 全文 ---")
            print(content_text)
            return 0

        # 去重（search_results 无唯一约束）：同 run 同 url 的 cdp 行先删
        await db.execute(text(
            "DELETE FROM search_results WHERE collection_run_id=:r AND url=:u AND search_backend='cdp'"),
            {"r": args.run_id, "u": url})
        tier = classify_source_tier(url, brand_name)
        raw = "\n".join(r["text"] for r in regions)
        rec = (await db.execute(text("""
            INSERT INTO search_results
              (id, organization_id, brand_id, collection_run_id, search_backend, query, title, url,
               snippet, source_tier, raw_content, content_text, content_layer, rank, collected_at)
            VALUES (gen_random_uuid(), :o, :b, :r, 'cdp', :q, :t, :u, '', :tier, :raw, :ct, 'fact', 0, NOW())
            RETURNING id
        """), {"o": org_id, "b": brand_id, "r": args.run_id, "q": f"{city}{brand_name}",
               "t": title, "u": url, "tier": tier, "raw": raw, "ct": content_text})).fetchone()
        print(f"  ✓ 落库 id={str(rec[0])[:8]} tier={tier} query={city}{brand_name}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
