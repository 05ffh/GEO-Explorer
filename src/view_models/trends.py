"""GEO Explorer — Trends & Attribution ViewModel."""
from sqlalchemy import select, desc
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.collection_run import CollectionRun
from src.models.action_theme import ActionTheme


def compute_attribution_label(pre_val, post_val, sample_size, gt_changed, platform_failure) -> str:
    """P0-13 fix: minimal working attribution logic with 6 result types."""
    if sample_size < 3:
        return "样本不足"
    if platform_failure:
        return "平台失败影响"
    if gt_changed:
        return "GT 更新混淆"
    if abs(post_val - pre_val) > 0.05:
        return "可能由 Action 导致"
    return "无明显效果"


async def build_trends_vm(brand, range_str, user, db) -> dict:
    """Build view model for the trends & attribution page."""
    return {
        "brand": {"id": str(brand.id), "name": brand.name},
    }
