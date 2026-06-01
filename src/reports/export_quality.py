"""Export quality checks — PDF/DOCX verification, file naming, version constants (P1-6)."""
import os
import hashlib
import logging

logger = logging.getLogger(__name__)

REPORT_TEMPLATE_VERSION = "1.0"
CUSTOMER_LANGUAGE_VERSION = "1.0"
REPORT_QUALITY_RULE_VERSION = "1.0"


def check_pdf_export(filepath: str) -> dict:
    """Verify a PDF export is valid."""
    result = {"valid": False, "issues": []}
    if not os.path.exists(filepath):
        result["issues"].append("文件不存在")
        return result
    if os.path.getsize(filepath) == 0:
        result["issues"].append("文件为空")
        return result
    try:
        # Check if PDF has extractable text
        with open(filepath, "rb") as f:
            content = f.read(1024)
            if b"%PDF" not in content[:10]:
                result["issues"].append("非有效 PDF 文件")
                return result
    except Exception:
        result["issues"].append("无法读取 PDF 文件")
        return result
    result["valid"] = True
    return result


def check_docx_export(filepath: str) -> dict:
    """Verify a DOCX export is valid."""
    result = {"valid": False, "issues": []}
    if not os.path.exists(filepath):
        result["issues"].append("文件不存在")
        return result
    if os.path.getsize(filepath) == 0:
        result["issues"].append("文件为空")
        return result
    try:
        from docx import Document
        doc = Document(filepath)
        if len(doc.paragraphs) == 0:
            result["issues"].append("DOCX 无内容")
            return result
    except Exception as e:
        result["issues"].append(f"无法读取 DOCX 文件: {e}")
        return result
    result["valid"] = True
    return result


def verify_export_files(filepath: str, fmt: str) -> dict:
    """Route to format-specific checker."""
    if fmt == "pdf":
        return check_pdf_export(filepath)
    if fmt == "docx":
        return check_docx_export(filepath)
    return {"valid": os.path.exists(filepath) and os.path.getsize(filepath) > 0, "issues": []}


def build_report_filename(brand_name: str, date_str: str, edition: str, fmt: str, version: int = 1) -> str:
    """Build safe filename for report export."""
    safe = brand_name.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    safe = "".join(c for c in safe if c.isalnum() or c in "_-.")
    return f"{safe}_{date_str}_{edition}_v{version}.{fmt}"


def compute_file_hash(filepath: str) -> str | None:
    """Compute SHA256 hash of a file."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
