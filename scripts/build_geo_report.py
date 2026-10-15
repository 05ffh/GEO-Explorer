"""生成 AI 可见度诊断报告（HTML / PDF）+ 交付桌面 + 写溯源。

流程（固化）：数据 → 终判闸门 → 叙述 lint → HTML →（预览确认）→ PDF → 视觉审查 → 交付桌面 → 溯源落库。

用法：
  PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py <run_id>            # 出 HTML
  PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py <run_id> --check     # 只跑 lint（对齐内容时用）
  PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py <run_id> --pdf       # 出 HTML + PDF
  PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py <run_id> --pdf --deliver  # 并交付桌面

边界：lint 是**下限防线**（表征层），不替代主 agent 对叙述语义的自审。
"""
import argparse
import asyncio
import hashlib
import importlib
import os
import shutil
import subprocess
import sys
from datetime import datetime

from sqlalchemy import select, cast, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import append_report_artifact
from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot
from src.report.geo_report import render_report
from src.report.narrative import _NARRATIVE_SPEC, answer_corpus, lint_narrative
from src.report.report_data import build_report_data, sentiment_status

_DESKTOP = os.environ.get("GEO_REPORT_DESKTOP", "/mnt/c/Users/25468/Desktop")


async def _resolve_run(db, run_id: str) -> CollectionRun | None:
    """按前缀解析 run（短 id 友好，如 535b8108）；0 或多匹配 → 报错返回 None。"""
    rows = (await db.execute(
        select(CollectionRun).where(cast(CollectionRun.id, String).like(f"{run_id}%"))
    )).scalars().all()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        print(f"错误: run {run_id} 不存在")
    else:
        print(f"错误: run 前缀 {run_id} 不唯一，匹配 {[str(r.id)[:8] for r in rows]}，请给更长的 id")
    return None


async def latest_sealed_snapshot(db, run_id):
    """最新 sealed 快照（既是报告数据源，也是溯源出生快照）。"""
    return (await db.execute(
        select(MeasurementSnapshot)
        .where(MeasurementSnapshot.collection_run_id == run_id)
        .order_by(MeasurementSnapshot.snapshot_no.desc())
        .limit(1)
    )).scalar_one_or_none()


def _sha256(path: str) -> str | None:
    if not (path and os.path.exists(path)):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_pdf(html_path: str, pdf_path: str) -> tuple[bool, str]:
    """Chrome headless 转 PDF。字体由模板 CSS 栈保证（须含 'Noto Sans CJK SC'，否则乱码）；
    --no-pdf-header-footer 去页眉页脚。失败自检：Chrome 未必返非零，故查产物存在+非空。"""
    cmd = ["google-chrome", "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path}", f"file://{os.path.abspath(html_path)}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        return True, f"{os.path.getsize(pdf_path)} bytes"
    return False, (r.stderr or r.stdout or f"rc={r.returncode}")[-400:]


def _deliver(paths: list[str]) -> list[str]:
    os.makedirs(_DESKTOP, exist_ok=True)
    done = []
    for p in paths:
        dst = os.path.join(_DESKTOP, os.path.basename(p))
        shutil.copy2(p, dst)
        print(f"已交付 {dst}")
        done.append(os.path.basename(dst))
    return done


async def main():
    p = argparse.ArgumentParser(description="生成 AI 可见度诊断报告（HTML/PDF）+ 交付桌面 + 写溯源")
    p.add_argument("run_id", help="run 全 UUID 或唯一前缀（如 535b8108）")
    p.add_argument("--out", default="output")
    p.add_argument("--check", action="store_true", help="只跑叙述 lint，不渲染（对齐内容时用）")
    p.add_argument("--pdf", action="store_true", help="另出 PDF")
    p.add_argument("--deliver", action="store_true", help="交付到桌面")
    a = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await _resolve_run(db, a.run_id)
        if run is None:
            await engine.dispose()
            sys.exit(1)
        run_id = str(run.id)
        # 终判闸门：舆情未终判（仍含粗筛误判）→ 拒绝出报告，把"漏执行"变成"跑不出来"
        st = sentiment_status(run)
        if st != "confirmed":
            print(f"错误: 舆情尚未终判（当前 status={st}）——报告不得出。")
            print(f"  请先终判：python scripts/finalize_sentiment.py {a.run_id} --generate"
                  f" → 主 agent 标 verdict → --apply <verdict.json>")
            await engine.dispose()
            sys.exit(1)
        snap = await latest_sealed_snapshot(db, run.id)
        if snap is None:
            print(f"错误: run {run_id[:8]} 无 sealed 快照——报告必须基于已盖章版本，不得用草稿数据。")
            print(f"  请先盖章：python scripts/finalize_v4.py seal {a.run_id} <归因patch.json>")
            await engine.dispose()
            sys.exit(1)
        measurement = snap.measurement_json
        data = build_report_data(run, measurement=measurement)
    await engine.dispose()

    mod = importlib.import_module(f"src.report.narratives.{data['city']}{data['brand']}")
    narrative = mod.NARRATIVE

    # 叙述 lint（下限防线）：error 阻断、warn 提示
    problems = lint_narrative(data, narrative, answer_corpus(measurement or {}))
    warns = [x for x in problems if x["level"] == "warn"]
    for w in warns:
        print(f"  [warn/{w['code']}] {w['msg']}")
    errors = [x for x in problems if x["level"] == "error"]
    if errors:
        for e in errors:
            print(f"  [error/{e['code']}] {e['msg']}")
        print("\n叙述 lint 未过 → 报告不得出。规范：\n" + _NARRATIVE_SPEC)
        sys.exit(1)
    print("叙述 lint 通过")
    if a.check:
        return

    os.makedirs(a.out, exist_ok=True)
    stem = f"{data['city']}{data['brand']}_AI可见度诊断报告"
    html = render_report(data, narrative, brand=data["brand"], city=data["city"],
                         date=(data.get("collected_at") or "")[:10])
    html_path = os.path.join(a.out, f"{stem}.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"已生成 {html_path}")

    artifact_paths = [html_path]
    pdf_path = None
    if a.pdf:
        pdf_path = os.path.join(a.out, f"{stem}.pdf")
        ok, info = _to_pdf(html_path, pdf_path)
        if not ok:
            print(f"错误: PDF 转换失败 — {info}")
            sys.exit(1)
        print(f"已生成 {pdf_path}（{info}）")
        artifact_paths.append(pdf_path)

    delivered = _deliver(artifact_paths) if a.deliver else []

    # 写侧接入：报告产物溯源落库（出生快照号 + 产物 sha256 + lint + 交付）
    record = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "engine": "geo_report/1",
        "snapshot_no": snap.snapshot_no if snap is not None else None,
        "snapshot_collected_at": (measurement or {}).get("collected_at"),
        "html_sha256": _sha256(html_path),
        "pdf_sha256": _sha256(pdf_path) if pdf_path else None,
        "lint": {"errors": 0, "warns": len(warns)},
        "delivered": delivered,
    }
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        await append_report_artifact(db, run_id, record)
        await db.commit()
    await engine.dispose()
    print("已写报告溯源 report_json（出生快照 no="
          f"{record['snapshot_no']}，html sha={str(record['html_sha256'])[:12]}…）")


if __name__ == "__main__":
    asyncio.run(main())
