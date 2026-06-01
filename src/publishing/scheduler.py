"""Publishing + SaaS governance Celery Beat schedule (P2-4/P2-5)."""
from celery.schedules import crontab
from src.celery_app import app as celery_app

# Register periodic tasks
celery_app.conf.beat_schedule = {
    # ── P2-4 Publishing reconciliation ──
    "reconcile-publish-requests-every-15min": {
        "task": "src.publishing.reconciliation.reconcile_publish_requests_task",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "geo_default"},
    },
    "reconcile-publish-batches-every-15min": {
        "task": "src.publishing.reconciliation.reconcile_publish_batches_task",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "geo_default"},
    },
    "reconcile-publish-targets-every-15min": {
        "task": "src.publishing.reconciliation.reconcile_publish_targets_task",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "geo_default"},
    },

    # ── P2-5 SaaS governance ──
    "reconcile-org-usage-counts-hourly": {
        "task": "src.saas.governance.reconcole_org_usage_counts_task",
        "schedule": crontab(minute="7"),  # offset from :00/:30
        "options": {"queue": "geo_default"},
    },
    "aggregate-usage-snapshots-hourly": {
        "task": "src.saas.governance.aggregate_usage_snapshots_task",
        "schedule": crontab(minute="17"),
        "options": {"queue": "geo_default"},
    },
    "enforce-data-retention-daily": {
        "task": "src.saas.governance.enforce_data_retention_task",
        "schedule": crontab(hour="3", minute="27"),
        "options": {"queue": "geo_default"},
    },
    "cleanup-expired-exports-hourly": {
        "task": "src.saas.governance.cleanup_expired_exports_task",
        "schedule": crontab(minute="37"),
        "options": {"queue": "geo_default"},
    },
    "expire-invites-hourly": {
        "task": "src.saas.governance.expire_invites_task",
        "schedule": crontab(minute="47"),
        "options": {"queue": "geo_default"},
    },
    "apply-scheduled-plan-changes-hourly": {
        "task": "src.saas.governance.apply_scheduled_plan_changes_task",
        "schedule": crontab(minute="57"),
        "options": {"queue": "geo_default"},
    },
    "verify-audit-log-chain-daily": {
        "task": "src.saas.governance.verify_audit_log_chain_task",
        "schedule": crontab(hour="4", minute="7"),
        "options": {"queue": "geo_default"},
    },
    "expire-platform-access-sessions-every-10min": {
        "task": "src.saas.governance.expire_platform_access_sessions_task",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "geo_default"},
    },
    "expire-feature-flag-overrides-hourly": {
        "task": "src.saas.governance.expire_feature_flag_overrides_task",
        "schedule": crontab(minute="27"),
        "options": {"queue": "geo_default"},
    },
    "expire-emergency-pauses-every-10min": {
        "task": "src.saas.governance.expire_emergency_pauses_task",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "geo_default"},
    },

    # ── Data Deletion ──
    "data-deletion-scan-every-17min": {
        "task": "src.saas.deletion_task.data_deletion_scan_task",
        "schedule": crontab(minute="17, 47"),
        "options": {"queue": "geo_default"},
    },
    "data-deletion-retry-scan-every-30min": {
        "task": "src.saas.deletion_task.data_deletion_retry_scan_task",
        "schedule": crontab(minute="47"),
        "options": {"queue": "geo_default"},
    },
}

celery_app.conf.timezone = "Asia/Shanghai"
