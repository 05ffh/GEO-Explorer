"""报告渲染：数据 + 业务叙述 → 商务蓝 HTML（Jinja2）。"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TDIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TDIR)),
                       autoescape=select_autoescape(["html"]))


def render_report(data: dict, narrative: dict, *, brand: str, city: str, date: str) -> str:
    tpl = _env().get_template("geo_report.html.j2")
    ctx = dict(data)
    ctx.update({"narrative": narrative, "brand": brand, "city": city, "date": date})
    return tpl.render(**ctx)
