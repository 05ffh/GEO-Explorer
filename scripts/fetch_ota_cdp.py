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
import os
import re
import time
import urllib.request

import websocket
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.collector.content_filter import filter_client_facts
from src.config import settings
from src.gt.source_tier import classify_source_tier

# 与 bin/start-chrome-geo.sh 的 GEO_CHROME_PORT 对齐（换端口时两侧自动一致，复现者零改代码）
CDP_PORT = int(os.environ.get("GEO_CHROME_PORT", "9223"))

# ---- 平台规格（白名单 + 边界切分）----
# boundaries 有序：只在列出的边界名处切分；类型 fact=提取 / opinion=边界不提取 / ignore=不提取。
# keep_until：区块内遇到该独立行就截断（裁长尾噪音，如携程「地点」只取「交通」子区）。
SPECS: dict[str, dict] = {
    "ctrip": {
        "domain": "ctrip.com",
        "url_tpl": "https://hotels.ctrip.com/hotels/{hotel_id}.html",
        "hotel_id_re": r"/hotels?/(\d+)\.html",
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
    "tongcheng": {
        "domain": "ly.com",
        "url_tpl": "https://www.ly.com/hotel/hoteldetail?hotelId={hotel_id}",
        "hotel_id_re": r"hotelId=(\d+)",
        "default_type": "fact",
        "wait_for": "附近的酒店",  # 末区块标记（同携程：出现才算渲染完）
        # extract_js / room_cards_js 在下方 JS 常量定义后挂载（同程专属，与携程分开）
        # 同程部分事实写在 H3 标题里（「入住时间：14:00后 退房时间：12:00前」本身即标题，
        # 标题之后为空）→ 非边界标题文字并入该段。
        "emit_heading": True,
        "boundaries": [
            ("用户点评", "opinion", {}),   # 边界名带计数「用户点评 (11244)」，segment 容错尾部 (N)
            ("酒店介绍", "fact", {}),      # 基础信息：开业/装修/客房数/类型/电话 + 酒店描述
            ("订房必读", "fact", {}),      # 可接待人群/入离时间/城市通知（事实在 H3 标题里）
            ("入住政策", "fact", {}),      # 年龄/儿童加床/宠物/前台/早餐/押金/证件
            ("服务与设施", "fact", {}),    # 设施 + 收费标记
            ("最近浏览", "ignore", {}),
            ("附近的酒店", "ignore", {}),
        ],
        # 行级噪声（同程特有：房型筛选标签 / rate-plan 码 / 划线价格免责声明）。
        # 隔离在平台内，不动携程既有 _OTA_UI/_RATE_PLAN。
        "drop_lines": [
            r"^在地图上显示$",
            r"^(双床|大床|单人早餐|双人早餐|含三早及以上|含套餐|含早餐|不含早)$",
            r"^(同程艺龙直销|健康守护优惠|可用红包|可用券|普卡特权|门店新客|优选推荐|有返现)$",
            r"^无餐食",                                   # 无餐食今天18:00前可免费取消 / 无餐食不可取消
            r"^\d+份早餐",                                # 2份早餐今天18:00前可免费取消 / 3份早餐不可取消
            r"^套餐",                                     # 套餐 2份早餐今天18:00前可免费取消
            r"^含[双三单]早",                             # 含双早-内宾 / 含三早-内宾
            r"^可入住\d+人$",
            r"^预付-",                                    # 预付-常规
            r"^[a-z0-9]{6,}[¥￥][\d,]+$",                 # rate-plan 码 lm577f19¥525
            r"^(平台补贴|限时抢购|特惠|红包|会员)等\d+项$",
            r"^优惠[¥￥][\d,]+$",
            r"^(查看其他\d+个报价|查看更多房型)$",
            r"^(特大床|双床|\d+成人\d+儿童)$",
            r"^(查看供应商信息|酒店接受以下付款方式:|价格说明)$",
            r"^划线价格指",                                # 单行长免责声明
        ],
    },
    "fliggy": {
        "domain": "alitrip.com",  # 实际域名 hotel.alitrip.com（页面后端 JS 里引用 hotel.fliggy.com）
        "url_tpl": "https://hotel.alitrip.com/hotel_detail2.htm?shid={hotel_id}",
        "hotel_id_re": r"shid=(\d+)",
        "default_type": "fact",  # 顶部大区（导航/房型列表/预订 UI）——房型走 DOM，预订 UI 由 drop_lines 清
        "wait_for": "{city}酒店信息",  # 末段标记（城市 SEO 块「{城市}酒店信息」，渲染完才出现）——{city} 运行时格式化
        # 飞猪区块（白名单）：房型在顶部大区（默认 fact），事实段=酒店介绍；设施段为空、交通段纯噪声。
        # ⚠️ 区块名须**城市无关**（否则换城市失效）：尾部「{城市}酒店信息」城市 SEO 块**不列入边界**
        # → 其文本自动并入前一「住客评价」opinion 段丢弃（其后预订 UI/推荐同理）。
        "boundaries": [
            ("酒店介绍", "fact", {}),      # 开业/装修/房量/电话 + 描述（宴会厅/多功能厅/餐厅）
            ("设施与服务", "fact", {}),    # 飞猪该段为空（仅 JS，无设施数据）——保留边界以在 dry-run 显式展示
            ("交通及周边", "ignore", {}),  # 地图 + 驾车路线，无可用事实（真实位置事实在「酒店介绍」散文里）
            ("住客评价", "opinion", {}),   # 评分 + 点评正文（观点层）；其后城市 SEO/预订 UI/推荐自动并入本段
        ],
        # 行级噪声（飞猪特有：顶部导航 / 预订 UI / rate-plan / 房型规格行）。
        # 隔离在平台内，不动携程/同程既有过滤。
        "drop_lines": [
            r"^(收藏|搜索|入住|离店|明天|后天|今天|共\d+晚)$",
            r"^(酒店预订|酒店信息|交通及周边|住客评价\(\d+\))$",  # 顶部 nav
            r"^超值团购|^报价列表|^[¥￥][\d,]+(起|/晚)?$",
            r"^查看房型图片\(\d+\)$",
            r"^床型：|^面积：|^楼层：|^窗型：",
            r"^(卖家|处理时长|预订成功率|预订详情|价格|举报|预订)$",
            r"^\d+分钟$|^100%$|^\d+%$",
            r"^(限时取消|有条件取消|不可取消)$",
            r"^已优惠$|^已优惠\s*[¥￥]|^已减\s*[¥￥]",
            r"^该卖家同房型的另外\d+个报价$",
            r"^(全人群运营活动|限时活动|会员专享)$",
            r"(专营店|旗舰店|专卖店)$",   # 卖方店铺名（深圳奇迹云游酒店专营店…）
            r"^\d+\.\s*沿",              # 驾车路线步骤（交通段整段 ignore 的兜底）
            r"^(公交|驾车|交通路线|餐饮|娱乐|购物)$",
            r"^©|^GS\(|^\d+\s*米$",
        ],
        # 地址行重写：飞猪「街道号，地标, 城市」→「城市市+街道号」（对齐携程/同程口径）。
        # 注：飞猪页无省/区，此处只做格式；「区」由中间处理层跨平台对齐补全（见 _CDP_MIDLAYER_SPEC）。
        "replace_lines": [
            (r"^(\S+?号)\s*[，,]\s*\S+?\s*[，,]\s*(\S+?)(?:市)?\s*$", r"\2市\1"),
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

# ===== 同程专属 DOM（与携程分开，避免冲突）=====
# 同程 4 处结构差异：① nav 用空文字 h（segment 丢空标题）② 事实写在 H3 标题里（emit_heading）
# ③ 表格/设施详情是 div 组件非 <table>（本 JS 内联）④ 房型卡 DOM 不同（_TC_ROOM_CARDS_JS）。
# 区块抽取变体：同携程 Range 取相邻标题间文本，但额外内联两类 div 组件——
#   .table-info（早餐/儿童加床等"表格"）→ 逐行 "cell | cell | cell"（保留首列标签，修丢主语）；
#   .view-detail[tip]（设施"详细展示"）→ 读 tip 属性（营业时间/收费信息），**无需点击**。
_TC_EXTRACT_JS = r"""(function(){
  function inSticky(h){var n=h;for(var i=0;i<6&&n;i++){var p='';try{p=getComputedStyle(n).position;}catch(e){}if(p==='fixed'||p==='sticky')return true;n=n.parentElement;}return false;}
  var hs=[].slice.call(document.querySelectorAll('h1,h2,h3,h4')).filter(function(h){return h.offsetParent!==null && !inSticky(h);});
  function rng(a,b){
    var r=document.createRange();r.setStartAfter(a);
    if(b){r.setEndBefore(b);}else{r.setEnd(document.body,document.body.childNodes.length);}
    var frag=r.cloneContents(), lines=[];
    function walk(node){
      for(var i=0;i<node.childNodes.length;i++){
        var c=node.childNodes[i];
        if(c.nodeType===3){var t=(c.nodeValue||'').trim();if(t)lines.push(t);}
        else if(c.nodeType===1){
          if(c.tagName==='SCRIPT'||c.tagName==='STYLE')continue;
          var cls=''+(c.className||'');
          if(/(^|\s)table-info(\s|$)/.test(cls)){  // 表格组件 → 逐行 "cell | cell | cell"
            [].slice.call(c.querySelectorAll('.table-info-header, .table-info-content-item')).forEach(function(rw){
              var cells=[].slice.call(rw.querySelectorAll('.t-content'));
              var line=cells.length?cells.map(function(x){return (x.innerText||'').trim();}).filter(Boolean).join(' | ')
                                  :(rw.innerText||'').trim().replace(/\s+/g,' ');
              if(line)lines.push(line);
            });
            continue;
          }
          // 设施条目：整块处理（名 + 「详细展示」tip），避免 tip 与相邻条目错位
          var vd=null;try{vd=c.querySelector(':scope > .view-detail');}catch(e){}
          if(vd&&vd.getAttribute('tip')){
            var nm=c.querySelector('.amenities-info-name');
            var nmt=nm?(nm.innerText||'').trim().replace(/\s+/g,' '):'';
            var tl=vd.getAttribute('tip').replace(/<\/div>/g,'\n').replace(/<[^>]+>/g,'')
              .split('\n').map(function(x){return x.trim();}).filter(Boolean);
            // 名 + 详情并成一行：相邻条目 tip 完全相同（如接机/送机同价）时，filter 去重会拆散名与详情 → 错位
            lines.push((nmt?nmt+' ':'')+tl.join(' '));
            continue;
          }
          if(/(^|\s)view-detail(\s|$)/.test(cls)&&c.getAttribute('tip')){  // 兜底：裸 view-detail
            c.getAttribute('tip').replace(/<\/div>/g,'\n').replace(/<[^>]+>/g,'')
              .split('\n').map(function(x){return x.trim();}).filter(Boolean).forEach(function(x){lines.push(x);});
            continue;
          }
          walk(c);
        }
      }
    }
    walk(frag);
    return lines.join('\n').slice(0,20000);
  }
  var out=[];
  for(var i=0;i<hs.length;i++){out.push({name:hs[i].innerText.trim(),text:rng(hs[i],hs[i+1]||null)});}
  return JSON.stringify(out);
})()"""

# 同程房型卡：房型名（H1）+ 规格行「床型 | 面积 | 人数」+ 起价（最低 ¥）。
# 携程用「含 ¥ 的祖先」找卡；同程规格行含 "| 面积"，故用「含 ¥ 且含 | 且含 ㎡ 的最近祖先」。
_TC_ROOM_CARDS_JS = r"""(function(){
  function findCard(e){var n=e;for(var i=0;i<14&&n;i++){var t=n.innerText||'';
    // 体积上限：真房型卡 < 2000 字；下拉列表项无 ¥，向上会撞到整页大容器（>万字符）→ 排除
    if(t.length<2000&&/[¥￥]\s*[\d,]+/.test(t)&&t.indexOf('|')>=0&&/㎡|平方米/.test(t))return n;n=n.parentElement;}return null;}
  // 房型名有时是 H1/H2、有时是 DIV（满房房型）→ 一并选；findCard 兜住（无 ¥ 祖先则跳过）
  var cands=[].slice.call(document.querySelectorAll('h1,h2,h3,h4,div,span')).filter(function(e){
    var t=(e.innerText||'').trim();
    return /(房|套房|公寓)/.test(t)&&t.length>=4&&t.length<=40&&e.children.length<=1
      &&t.indexOf('¥')<0&&t.indexOf('￥')<0&&t.indexOf('\n')<0
      &&!/入住|退房|加床|政策|：|展示|查看|酒店|全部房型/.test(t);});  // 排除含"房"字非房型（勿含"儿童"，会误排"…含儿童高低床"房型）
  var out=[], seen={};
  for(var k=0;k<cands.length;k++){
    var t=cands[k].innerText.trim(); if(seen[t])continue;
    var card=findCard(cands[k]); if(!card) continue;  // 先确认有卡再去重（下拉列表同名无卡→不占位）
    seen[t]=1;
    var ct=(card.innerText||'').replace(/\s+/g,' ');
    var m=ct.match(/\s([^\s|]{1,12})\s*\|\s*(\d+(?:-\d+)?\s*(?:㎡|平方米))\s*\|/);  // 床型 | 面积 |
    // 价格：排除「优惠/补贴/立减/券后」前缀的促销额（否则 min 取到"优惠¥10"）
    var nums=[], re=/(优惠|补贴|立减|券后|收取)\s*[¥￥]\s*[\d,]+|[¥￥]\s*([\d,]+)/g, mm;
    while((mm=re.exec(ct))){ if(mm[2]!==undefined){var v=parseInt(mm[2].replace(/[^\d]/g,''),10); if(v>0)nums.push(v);} }
    if(!nums.length) continue;
    out.push({name:t, price:'¥'+Math.min.apply(null,nums), bed:(m?m[1]:''), area:(m?m[2].replace(/\s+/g,''):'')});
  }
  return JSON.stringify(out);
})()"""

# ===== 飞猪专属 DOM（与携程/同程分开）=====
# 飞猪房型卡是语义 class（非 hash）：.room-item-wrapper 卡 > .item-title（房名）
# + .info（「床型：… 面积：… 楼层：… 窗型：…」）+「报价列表 ¥N起」（per-room 起价，稳定）。
# 起价优先取「报价列表 ¥N起」；兜底 min ¥ 排除「已优惠/优惠/补贴」额（同程同款坑）。
# spec 单字段承载「床型｜面积｜楼层｜窗型」（_render_room_cards 支持 spec 覆盖）。
_FLIGGY_ROOM_CARDS_JS = r"""(function(){
  var out=[];
  [].slice.call(document.querySelectorAll('.room-item-wrapper')).forEach(function(w){
    var nm=w.querySelector('.item-title');
    var name=nm?(nm.innerText||'').trim():'';
    if(!name)return;
    var inf=w.querySelector('.info');
    var info=inf?(inf.innerText||'').replace(/\s+/g,' ').trim():'';
    function g(re){var m=info.match(re);return m?m[1]:'';}
    var bed=g(/床型：\s*(\S+)/), area=g(/面积：\s*(\S+)/), floor=g(/楼层：\s*(\S+)/), win=g(/窗型：\s*(\S+)/);
    var parts=[bed,area,floor?floor+'层':'',win].filter(Boolean);
    var t=(w.innerText||'').replace(/\s+/g,' ');
    var price='';
    var pm=t.match(/报价列表\s*[¥￥]\s*([\d,]+)\s*起/);
    if(pm){price='¥'+pm[1].replace(/[^\d]/g,'');}
    else{
      var nums=[], re=/(已优惠|优惠|补贴|已减|立减|券后)\s*[¥￥]?\s*[\d,]+|[¥￥]\s*([\d,]+)/g, m;
      while((m=re.exec(t))){if(m[2]!==undefined){var v=parseInt(m[2].replace(/[^\d]/g,''),10);if(v>0)nums.push(v);}}
      if(nums.length)price='¥'+Math.min.apply(null,nums);
    }
    if(!price)return;
    out.push({name:name, price:price, spec:parts.join('｜')});
  });
  return JSON.stringify(out);
})()"""

# 飞猪区块抽取 = 默认 Range 抽取 + 注入「酒店星级」行。
# 星级在标题旁 span.row-subtitle[title="国家旅游局评定为五星级"]，不在文本流里 → 需 DOM 取。
_FLIGGY_EXTRACT_JS = (
    "(function(){var out=JSON.parse(" + _EXTRACT_JS + ");"
    "var st=document.querySelector('.row-subtitle');var star=st&&st.getAttribute('title');"
    "if(star&&out.length){out[0].text='酒店星级：'+star+'\\n'+out[0].text;}"
    "return JSON.stringify(out);})()"
)

# 同程/飞猪挂载专属 DOM JS（SPECS 定义在 JS 常量之前，故此处回填）。
SPECS["tongcheng"]["extract_js"] = _TC_EXTRACT_JS
SPECS["tongcheng"]["room_cards_js"] = _TC_ROOM_CARDS_JS
SPECS["fliggy"]["extract_js"] = _FLIGGY_EXTRACT_JS
SPECS["fliggy"]["room_cards_js"] = _FLIGGY_ROOM_CARDS_JS

# 展开链接（定位用）：点击"展示其余N个房型"渲染全部房型（未展开时 DOM 只有首屏房型）。
# 不标记已点——展开验证靠"链接是否消失"（见 _click_expand），故需可重复定位。
_FIND_EXPAND_JS = r"""(function(){
  var re=/^(展示其余\d+个房型|查看更多房型|查看其他房型)$/;
  var els=[].slice.call(document.querySelectorAll('a,span,div,button,p'));
  for(var i=0;i<els.length;i++){
    var e=els[i];
    if(re.test((e.innerText||'').trim()) && e.children.length<=1){
      e.scrollIntoView({block:'center'});
      var r=e.getBoundingClientRect();
      return JSON.stringify({x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2),t:e.innerText.trim()});
    }
  }
  return 'none';
})()"""

# 展开链接的 JS 点击（兜底）：原生 mousePressed/Released 对 **Vue 组件**（同程 `p.more-room-btn`）
# 无间隔时**不触发**（2026-10-14 实测）→ 用 JS `.click()` 兜底（按文本定位，平台无关）。
_CLICK_EXPAND_JS = r"""(function(){
  var re=/^(展示其余\d+个房型|查看更多房型|查看其他房型)$/;
  var els=[].slice.call(document.querySelectorAll('a,span,div,button,p'));
  for(var i=0;i<els.length;i++){var e=els[i];
    if(re.test((e.innerText||'').trim())&&e.children.length<=1){e.click();return true;}}
  return false;
})()"""


# ---- CDP ----
def _tabs() -> list[dict]:
    # timeout：Chrome 未起/端口不通时快速失败（chrome_ready 靠它给提示，不能挂）
    return json.load(urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json", timeout=3))


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
    return json.load(urllib.request.urlopen(req, timeout=3))


def chrome_ready() -> bool:
    """CDP 端口可达？（GEO Chrome 起了没）——未起时调用方给提示（同 Docker 前提）。"""
    try:
        _tabs()
        return True
    except Exception:
        return False


def _find_verified_tab(domain: str, brand: str, city: str,
                       tabs: list[dict] | None = None) -> dict | None:
    """找该平台已打开、且**标题验证为指定品牌（+城市）**的标签页（用户手动打开的酒店页）。

    为什么靠标题：OTA 详情页 URL **不含品牌名**（`hotels.ctrip.com/hotels/429558.html`），
    无法像"甲方页面"那样靠 URL 认领品牌 → 唯一可靠判别 = **页面标题含品牌名（+城市）**。
    找不到/标题不符 → 返回 None（调用方跳过该平台，绝不抓错酒店）。
    `tabs` 参数供测试注入（缺省取实时标签页）。
    """
    if tabs is None:
        try:
            tabs = _tabs()
        except Exception:
            return None
    for t in tabs:
        if t.get("type") != "page" or domain not in t.get("url", ""):
            continue
        title = t.get("title", "") or ""
        if brand and brand in title and (not city or city in title):
            return t
    return None


def _click_expand(ws) -> list[str]:
    """点展开链接并**验证「内容变长」**（展开真的渲染了），可重试。返回点击的链接文本。

    两个坑（实测）：
    ① 后台标签页被 Chrome 节流 → 点击不触发重渲染（配套修复 = `Page.bringToFront` 激活）；
    ② 展开按钮常是 **Vue 组件**（同程 `p.more-room-btn`）→ 原生 mousePressed/Released **无间隔不触发**
       （加 ~100ms 间隔即生效）→ 故加间隔 + JS `.click()` 兜底。
    验证「内容变长」比「链接消失」可靠——链接可能因瞬时重渲染消失而内容未渲染。
    """
    def body_len() -> int:
        r = _cmd(ws, 57, "Runtime.evaluate",
                 {"expression": "document.body?document.body.innerText.length:0", "returnByValue": True})
        return r["result"]["result"].get("value", 0)

    def grew(before: int, rounds: int) -> bool:
        for _ in range(rounds):
            time.sleep(1)
            if body_len() > before:
                return True
        return False

    clicked = []
    for k in range(6):
        try:
            r = _cmd(ws, 40 + k, "Runtime.evaluate", {"expression": _FIND_EXPAND_JS, "returnByValue": True})
            v = r["result"]["result"].get("value", "none")
            if v == "none":
                break  # 无展开链接 = 已展开（或本平台无房型展开，如飞猪）
            pos = json.loads(v)
            before = body_len()
            # ① 原生点击（pressed/released 间隔 100ms——无间隔对 Vue 组件不触发）
            for typ in ("mouseMoved", "mousePressed"):
                _cmd(ws, 50 + k, "Input.dispatchMouseEvent",
                     {"type": typ, "x": pos["x"], "y": pos["y"], "button": "left", "clickCount": 1})
            time.sleep(0.1)
            _cmd(ws, 50 + k, "Input.dispatchMouseEvent",
                 {"type": "mouseReleased", "x": pos["x"], "y": pos["y"], "button": "left", "clickCount": 1})
            clicked.append(pos["t"])
            if grew(before, 8):
                continue
            # ② 原生点击无效 → JS `.click()` 兜底（按文本定位，平台无关）
            _cmd(ws, 58, "Runtime.evaluate", {"expression": _CLICK_EXPAND_JS, "returnByValue": True})
            grew(before, 6)
        except Exception:  # 点击后页面若重排/WS 抖动 → 停止展开，用已渲染内容
            break
    return clicked


def _wait_render_complete(ws, id_base: int = 60, need: int = 2, max_rounds: int = 25) -> int:
    """抽取前闸门：等页面渲染完成（innerText 长度连续 need 次不变，每轮 1s）。返回稳定长度。

    OTA 页面异步/分阶段渲染（房型展开后尤其慢），长度未稳定就抽取会漏内容——
    2026-10-13 实测：点「查看更多房型」后未等渲染 → 只抓到首屏 2 个房型。
    携程/同程共用此闸门（"等渲染完成再抓取"）。
    """
    last, stable = -1, 0
    for k in range(max_rounds):
        time.sleep(1)
        r = _cmd(ws, id_base + k, "Runtime.evaluate",
                 {"expression": "document.body?document.body.innerText.length:0", "returnByValue": True})
        n = r["result"]["result"].get("value", 0)
        stable = stable + 1 if n == last else 0
        if stable >= need and n > 200:
            return n
        last = n
    return last


def fetch(url: str, domain: str, wait_for: str = "",
          extract_js: str = _EXTRACT_JS, room_cards_js: str = _ROOM_CARDS_JS,
          ) -> tuple[list[dict], str, list[dict]]:
    """导航 + 等渲染 + 抽取区块。返回 (regions, title)。

    等待判据：innerText 长度稳定 **且** wait_for 标记已出现（OTA 分阶段渲染，仅看长度
    会在部分渲染时就稳定 → 漏区块；2026-10-10 实测偶发）。
    """
    tab = _open_tab(domain)
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=120, suppress_origin=True)
    try:
        _cmd(ws, 1, "Runtime.enable")
        _cmd(ws, 2, "Page.enable")
        # 激活标签页：后台页被 Chrome 节流（document.hidden）→ 渲染/点击不触发重渲染 →
        # 展开不生效（2026-10-13 实测：后台页点「查看更多房型」房型恒 2）。必须先置前再导航。
        _cmd(ws, 4, "Page.bringToFront")
        for _ in range(10):  # 等标签页**真正激活**（bringToFront 后可能仍 hidden）——否则渲染/点击不生效
            time.sleep(0.5)
            r = _cmd(ws, 5, "Runtime.evaluate", {"expression": "document.hidden", "returnByValue": True})
            if not r["result"]["result"].get("value", True):
                break
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
        # 抓取前闸门：等页面渲染完成（含展开后的异步渲染）再抽取——携程/同程共用。
        _wait_render_complete(ws)
        r = _cmd(ws, 11, "Runtime.evaluate", {"expression": extract_js, "returnByValue": True})
        regions = json.loads(r["result"]["result"].get("value", "[]"))
        r = _cmd(ws, 13, "Runtime.evaluate", {"expression": room_cards_js, "returnByValue": True})
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
        if re.match(r'^[A-Za-z_$][\w$]*\s*:\s*["\']', s):  # JS 对象属性残留（shname : "…"）
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


_BOUNDARY_COUNT = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def _norm_name(name: str) -> str:
    """边界名归一化：去尾部计数（同程「用户点评 (11244)」→「用户点评」）。"""
    return _BOUNDARY_COUNT.sub("", name or "")


def segment(regions: list[dict], spec: dict) -> list[tuple[str, str]]:
    """区块序列 → [(type, text)]（按规格边界切分）。

    `__TOP__`（首个可见标题之前 = 头部导航/SSR 噪声）恒丢弃。
    空标题区块（同程 nav 用无文字的 h 标签，Range 会吞进站点导航）恒丢弃。
    边界名匹配容忍尾部计数（同程「用户点评 (11244)」→「用户点评」）。
    `emit_heading`（同程）：非边界标题的文字并入该段——同程部分事实写在 H3 标题里
    （「入住时间：14:00后 退房时间：12:00前」本身就是标题，标题之后为空）。
    opinion 段可带 `fact_head_until`：头部（评分等结构化数值）并入 fact，其余（点评正文）丢弃。
    """
    bmap = {b[0]: b for b in spec["boundaries"]}
    emit_heading = spec.get("emit_heading", False)
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
        name = reg["name"]
        if name == "__TOP__" or not name.strip():
            continue
        b = bmap.get(name) or bmap.get(_norm_name(name))
        if b is not None:
            if cur or segs:
                emit(cur_type, cur_opts, "\n".join(cur))
            cur_type, cur_opts, cur = b[1], b[2], [_strip_noise(reg["text"])]
        else:
            txt = f"{name}\n{reg['text']}" if emit_heading else reg["text"]
            cur.append(_strip_noise(txt))
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
    """房型卡 → "房型名 ¥价（规格）" 行（精确配对）。

    规格：携程/同程用 bed｜area 两字段；飞猪用 spec 单字段（床型｜面积｜楼层｜窗型）。
    """
    def spec(c: dict) -> str:
        if c.get("spec"):
            return f"（{c['spec']}）"
        parts = [x for x in (c.get("bed"), c.get("area")) if x]
        return f"（{'｜'.join(parts)}）" if parts else ""
    return "\n".join(f"{c['name']} {c['price']}{spec(c)}" for c in cards)


# 房型区规格残渣：床型行（"2张1.2米单人床"）、面积楼层行（"40平方米 | 6-20层"）——无主语，已并入卡片
_SPEC_FRAG = re.compile(r"^[1-9]张[^ ]*床|^\d[\d–\-]*平方米")

# 房型 rate-plan 文案（会员价/含餐价/Wi-Fi 价/人数价）——随酒店而异，卡片子树外的独立 rate-box
# 也会出现（世茂洲际实测）→ 关键词兜底（这些词永不构成甲方事实）。
_RATE_PLAN = re.compile(r"会员价|早餐及晚餐|份早餐|Wi-?Fi免费[¥￥]|儿童早餐|有窗|无窗|封闭窗|^\d+[¥￥][\d,]+$")


def _drop_room_lines(txt: str, names: set[str]) -> str:
    """丢文本流里的房型区噪声：房型名行（去空格/前缀匹配）+ 多价乱价行 + 无主语规格残渣。

    去空格归一 + 前缀匹配：飞猪卖方报价区会出现裸房名「豪华大床房」（卡片名「豪华大床房-…」的前缀）
    与双空格变体（「豪华双床房  城市景观」vs 卡片名单空格）——房型已由卡片精确出，这些是残渣。
    """
    nn = {re.sub(r"\s+", "", n) for n in names if n}
    out = []
    for line in txt.split("\n"):
        s = line.strip()
        ns = re.sub(r"\s+", "", s)
        if (ns in nn) or (len(ns) >= 4 and any(n.startswith(ns) for n in nn)) \
           or _SPEC_FRAG.match(s) or _RATE_PLAN.search(s):
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
    found = {b[0] for b in spec["boundaries"]} & {_norm_name(r["name"]) for r in regions}
    fact = "\n".join(t for typ, t in segs if typ == "fact")
    body = filter_client_facts(_merge_values(fact))
    if spec.get("drop_lines"):
        pats = [re.compile(p) for p in spec["drop_lines"]]
        body = "\n".join(ln for ln in body.split("\n") if not any(p.search(ln) for p in pats))
    if spec.get("replace_lines"):  # 行级重写（如飞猪地址行「街道号，地标, 城市」→「城市市+街道号」对齐口径）
        for pat, repl in spec["replace_lines"]:
            body = re.sub(pat, repl, body, flags=re.M)
    if cards:
        body = _drop_room_lines(body, {c["name"] for c in cards})
        body = _render_room_cards(cards) + "\n" + body
    return body, sorted(found)


# ---- 落库 ----
async def detect_hotel_id(db, run_id, spec) -> str | None:
    """认领 hotelId（携程 /hotels/429558.html、同程 ?hotelId=…、飞猪 ?shid=…）。

    优先**本 run 已有 CDP 行**（重跑稳定，指向正确酒店）→ 回退本 run 语料 URL（启发式）。
    ⚠️ 启发式对**多酒店品牌**可能取错（语料含同品牌多城市 URL）→ 换酒店请显式 `--hotel-id`。
    """
    pat = re.compile(spec["hotel_id_re"])
    for extra in ("AND search_backend='cdp'", ""):  # 先 CDP 行（稳定）→ 再全语料（启发式）
        rows = (await db.execute(text(
            f"SELECT url FROM search_results WHERE collection_run_id=:r {extra} "
            "AND url LIKE :p LIMIT 50"),
            {"r": run_id, "p": f"%{spec['domain']}%"})).fetchall()
        for (u,) in rows:
            m = pat.search(u or "")
            if m:
                return m.group(1)
    return None


async def scrape_platform(db, run_id, platform, *, hotel_id: str | None = None,
                          dry_run: bool = False) -> dict:
    """抓一个平台并（非 dry_run 时）落库，返回结果 dict（**不 commit**——调用方负责）。

    **hotelId 解析顺序**：显式 hotel_id → **已验证的已开标签页**（用户手动打开，标题含品牌+城市）
    → `detect_hotel_id`（本 run 语料，兜底）。
    **页面验证闸门**：抓完页面后标题须含**品牌名（+城市）**，否则不落库（防抓错酒店）。
    """
    spec = SPECS[platform]
    row = (await db.execute(text(
        "SELECT brand_id, organization_id, city FROM collection_runs WHERE id=:r"),
        {"r": run_id})).fetchone()
    if not row:
        return {"platform": platform, "ok": False, "error": f"run {run_id} 不存在"}
    brand_id, org_id, city = row
    brand_name = (await db.execute(text("SELECT name FROM brands WHERE id=:b"),
                                   {"b": brand_id})).scalar() or ""

    # hotelId：显式 → 已验证标签页（用户手动打开的页面）→ 语料兜底
    src = "显式 --hotel-id"
    if not hotel_id:
        tab = _find_verified_tab(spec["domain"], brand_name, city)
        if tab:
            m = re.search(spec["hotel_id_re"], tab.get("url", ""))
            hotel_id = m.group(1) if m else None
            src = f"已开页面「{(tab.get('title') or '')[:24]}」"
    if not hotel_id:
        hotel_id = await detect_hotel_id(db, run_id, spec)
        src = "语料兜底"
    if not hotel_id:
        return {"platform": platform, "ok": False,
                "error": f"未找到 hotelId（{platform} 页面未打开？或用 --hotel-id 指定）"}

    url = spec["url_tpl"].format(hotel_id=hotel_id)
    wait_for = spec.get("wait_for", "").format(city=city, brand=brand_name)
    regions, title, cards = fetch(url, spec["domain"], wait_for,
                                  spec.get("extract_js", _EXTRACT_JS),
                                  spec.get("room_cards_js", _ROOM_CARDS_JS))

    # 页面验证闸门：标题须含品牌名（+城市）——防抓错酒店（OTA 详情页 URL 不含品牌名，只能靠标题）
    if brand_name and brand_name not in title:
        return {"platform": platform, "ok": False, "hotel_id": hotel_id, "hotel_id_src": src,
                "title": title, "error": f"页面验证失败：标题不含品牌「{brand_name}」"}
    if city and city not in title:
        return {"platform": platform, "ok": False, "hotel_id": hotel_id, "hotel_id_src": src,
                "title": title, "error": f"页面验证失败：标题不含城市「{city}」"}

    content_text, found = build_content_text(regions, spec, cards)
    expected = [b[0] for b in spec["boundaries"] if b[1] != "ignore"]
    missing = [n for n in expected if n not in found]
    out = {"platform": platform, "ok": True, "hotel_id": hotel_id, "hotel_id_src": src, "url": url,
           "title": title, "content_text": content_text, "content_text_len": len(content_text),
           "cards": cards, "found": found, "missing": missing, "regions": regions}
    if not content_text:
        out.update(ok=False, error="事实为空（页面结构可能变了）")
        return out
    if dry_run:
        return out

    # 落库（search_results 无唯一约束）：同 run 同 url 的 cdp 行先删
    await db.execute(text(
        "DELETE FROM search_results WHERE collection_run_id=:r AND url=:u AND search_backend='cdp'"),
        {"r": run_id, "u": url})
    tier = classify_source_tier(url, brand_name)
    raw = "\n".join(x["text"] for x in regions)
    rec = (await db.execute(text("""
        INSERT INTO search_results
          (id, organization_id, brand_id, collection_run_id, search_backend, query, title, url,
           snippet, source_tier, raw_content, content_text, content_layer, rank, collected_at)
        VALUES (gen_random_uuid(), :o, :b, :r, 'cdp', :q, :t, :u, '', :tier, :raw, :ct, 'fact', 0, NOW())
        RETURNING id
    """), {"o": org_id, "b": brand_id, "r": run_id, "q": f"{city}{brand_name}",
           "t": title, "u": url, "tier": tier, "raw": raw, "ct": content_text})).fetchone()
    out["id"] = str(rec[0])
    out["source_tier"] = tier
    return out


CDP_PLATFORMS = ("ctrip", "tongcheng", "fliggy")


async def cdp_scrape_all(db, run_id, brand_name, city,
                         platforms=CDP_PLATFORMS) -> dict[str, dict]:
    """抓多平台并落库（`run_gt_diagnosis` 调用）。返回 {平台: 结果 dict}。

    **前提检查**：GEO Chrome 未起（CDP 端口不可达）→ 各平台返回跳过原因（同 Docker 前提）。
    逐平台 try/except：一个平台失败不拖垮其他平台。
    """
    if not chrome_ready():
        msg = (f"GEO Chrome 未起（端口 {CDP_PORT}）→ 先运行：bash bin/start-chrome-geo.sh"
               "（并登录携程/同程/飞猪、打开酒店页）")
        return {p: {"platform": p, "ok": False, "error": msg} for p in platforms}
    out: dict[str, dict] = {}
    for p in platforms:
        try:
            out[p] = await scrape_platform(db, run_id, p)
        except Exception as e:  # 一个平台异常不拖垮其他平台
            out[p] = {"platform": p, "ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--platform", default="ctrip", choices=list(SPECS))
    ap.add_argument("--hotel-id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_async_engine(settings.database_url, connect_args={"timeout": 5})
    async with engine.begin() as db:  # 非 dry-run 时退出自动 commit；dry-run 无写操作
        r = await scrape_platform(db, args.run_id, args.platform,
                                  hotel_id=args.hotel_id, dry_run=args.dry_run)
    await engine.dispose()

    if not r.get("ok"):
        print(f"[{args.platform}] ✗ {r.get('error')}")
        if r.get("title"):
            print(f"  title: {r['title'][:60]}")
        return 1
    print(f"[{args.platform}] hotelId={r['hotel_id']}（{r['hotel_id_src']}）")
    print(f"  URL: {r['url']}")
    print(f"  title: {r['title'][:60]}")
    print(f"  区块: {[x['name'] for x in r['regions']]}")
    print(f"  命中边界: {r['found']}  缺: {r['missing'] or '无'}")
    print(f"  content_text: {r['content_text_len']} 字")
    if r["missing"]:
        print(f"  ⚠ 期望边界缺失 {r['missing']}（页面可能改版，人工确认）")
    if args.dry_run:
        print(f"\n--- 房型卡（{len(r['cards'])}）---")
        for c in r["cards"]:
            print(f"    {c['name']}  {c['price']}  {c.get('bed', '')}")
        print("\n--- 分段 ---")
        for typ, t in segment(r["regions"], SPECS[args.platform]):
            print(f"    [{typ:7s}] {len(t):6d} 字 | {t.strip()[:70]!r}")
        print("\n--- content_text 全文 ---")
        print(r["content_text"])
    else:
        print(f"  ✓ 落库 id={r['id'][:8]} tier={r['source_tier']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
