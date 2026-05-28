"""init all models

Revision ID: 0d3178a9cc1d
Revises:
Create Date: 2026-05-28 18:35:19.207923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0d3178a9cc1d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.models.base import Base
    from src.models import (  # noqa: F401 — ensure all models registered
        Organization, User, Brand, GroundTruthVersion,
        QueryTemplate, PromptVersion, CollectionRun,
        QueryResult, ApiUsage, MetricsSnapshot,
        HallucinationResult, ActionPlan, ContentLibrary, CompetitorSet,
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(50), server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="viewer"),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "brands",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("aliases", sa.dialects.postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("industry", sa.String(255), server_default=""),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ground_truth_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("ground_truth_json", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("source_urls", sa.dialects.postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("reviewer", sa.String(255), server_default=""),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "query_templates",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("system_prompt", sa.Text, server_default=""),
        sa.Column("template_rules", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("prompt_version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=True),
        sa.Column("ground_truth_version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("ground_truth_versions.id"), nullable=True),
        sa.Column("trigger_type", sa.String(50), server_default="manual"),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_queries", sa.Integer, server_default="0"),
        sa.Column("success_count", sa.Integer, server_default="0"),
        sa.Column("failure_count", sa.Integer, server_default="0"),
        sa.Column("error_summary", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "query_results",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("collection_run_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("collection_runs.id"), nullable=False, index=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("template_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("query_templates.id"), nullable=False),
        sa.Column("prompt_version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=True),
        sa.Column("question", sa.Text, server_default=""),
        sa.Column("system_prompt", sa.Text, server_default=""),
        sa.Column("user_prompt", sa.Text, server_default=""),
        sa.Column("request_payload_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("response_raw_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("answer_text", sa.Text, server_default=""),
        sa.Column("citations", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("model_name", sa.String(100), server_default=""),
        sa.Column("model_version", sa.String(100), server_default=""),
        sa.Column("temperature", sa.Float, server_default="0.3"),
        sa.Column("search_enabled", sa.Boolean, server_default="false"),
        sa.Column("status", sa.String(50), server_default="pending", index=True),
        sa.Column("error_code", sa.String(50), server_default=""),
        sa.Column("error_message", sa.Text, server_default=""),
        sa.Column("latency_ms", sa.Integer, server_default="0"),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("collected_at", sa.DateTime(timezone=True), index=True),
    )
    op.create_table(
        "api_usage_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("collection_run_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("collection_runs.id"), nullable=False, index=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("query_result_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("query_results.id"), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, server_default="0"),
        sa.Column("cost", sa.Numeric(10, 6), server_default="0"),
        sa.Column("status", sa.String(50), server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "metrics_snapshots",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("collection_run_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("collection_runs.id"), nullable=True),
        sa.Column("ground_truth_version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("ground_truth_versions.id"), nullable=True),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("dimension", sa.String(100), nullable=True),
        sa.Column("sov", sa.Float, server_default="0.0"),
        sa.Column("first_rec_rate", sa.Float, server_default="0.0"),
        sa.Column("accuracy_rate", sa.Float, server_default="0.0"),
        sa.Column("completeness_rate", sa.Float, server_default="0.0"),
        sa.Column("citation_rate", sa.Float, server_default="0.0"),
        sa.Column("sample_size", sa.Integer, server_default="0"),
        sa.Column("failure_rate", sa.Float, server_default="0.0"),
        sa.Column("details", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "hallucination_results",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("query_result_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("query_results.id"), nullable=False, index=True),
        sa.Column("ground_truth_version_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("ground_truth_versions.id"), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("field_level", sa.String(10), nullable=False),
        sa.Column("severity", sa.String(10), server_default="P1"),
        sa.Column("verdict", sa.String(50), server_default="uncertain"),
        sa.Column("ai_claim", sa.Text, server_default=""),
        sa.Column("ground_truth_value", sa.Text, server_default=""),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("human_reviewed", sa.Boolean, server_default="false"),
        sa.Column("human_verdict", sa.String(50), nullable=True),
        sa.Column("reviewer_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "action_plans",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("trigger_type", sa.String(100), nullable=False),
        sa.Column("action_type", sa.String(100), server_default=""),
        sa.Column("priority", sa.String(10), server_default="P2"),
        sa.Column("evidence_hallucination_ids", sa.dialects.postgresql.JSONB, server_default="[]"),
        sa.Column("ai_wrong_claims", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("correct_ground_truth", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("suggested_content_type", sa.String(100), server_default=""),
        sa.Column("acceptance_criteria", sa.Text, server_default=""),
        sa.Column("target_page", sa.String(500), server_default=""),
        sa.Column("status", sa.String(50), server_default="pending", index=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "content_library",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("action_plan_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("action_plans.id"), nullable=True),
        sa.Column("content_type", sa.String(100), server_default=""),
        sa.Column("title", sa.String(500), server_default=""),
        sa.Column("brief_json", sa.dialects.postgresql.JSONB, server_default="{}"),
        sa.Column("status", sa.String(50), server_default="draft", index=True),
        sa.Column("reviewed_by", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "competitor_sets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("competitor_brand_ids", sa.dialects.postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("source_type", sa.String(50), server_default="manual"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("competitor_sets")
    op.drop_table("content_library")
    op.drop_table("action_plans")
    op.drop_table("hallucination_results")
    op.drop_table("metrics_snapshots")
    op.drop_table("api_usage_logs")
    op.drop_table("query_results")
    op.drop_table("collection_runs")
    op.drop_table("prompt_versions")
    op.drop_table("query_templates")
    op.drop_table("ground_truth_versions")
    op.drop_table("brands")
    op.drop_table("users")
    op.drop_table("organizations")
