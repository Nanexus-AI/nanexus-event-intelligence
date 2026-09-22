"""add durable external processor jobs

Revision ID: a7c2d9e41f10
Revises: ff7f74e1aa8b
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c2d9e41f10"
down_revision: str | None = "ff7f74e1aa8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("review_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_revision",
                sa.String(128),
                server_default="unknown",
                nullable=False,
            )
        )

    op.create_table(
        "processor_jobs",
        sa.Column("processor_type", sa.String(255), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("subject_revision", sa.String(255), nullable=False),
        sa.Column("contract_version", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(512), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(128)),
        sa.Column("last_error", sa.Text()),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','retry_wait','succeeded','abstained','failed')",
            name="ck_processor_jobs_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_processor_jobs_attempt_count"),
        sa.UniqueConstraint("idempotency_key", name="uq_processor_jobs_idempotency_key"),
    )
    op.create_index(
        "ix_processor_jobs_status_available", "processor_jobs", ["status", "available_at"]
    )

    with op.batch_alter_table("model_invocations") as batch_op:
        batch_op.add_column(sa.Column("processor_job_id", sa.Uuid()))
        batch_op.add_column(
            sa.Column("status", sa.String(32), server_default="running", nullable=False)
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("error_message", sa.Text()))
        batch_op.add_column(
            sa.Column(
                "external_network_used", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )
        batch_op.create_foreign_key(
            "fk_model_invocations_processor_job_id",
            "processor_jobs",
            ["processor_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_model_invocation_status",
            "status IN ('running','succeeded','abstained','failed')",
        )
        batch_op.create_unique_constraint("uq_model_invocation_processor_job", ["processor_job_id"])

    with op.batch_alter_table("claims") as batch_op:
        batch_op.add_column(sa.Column("review_item_id", sa.Uuid()))
        batch_op.create_foreign_key(
            "fk_claims_review_item_id",
            "review_items",
            ["review_item_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_constraint("fk_claims_review_item_id", type_="foreignkey")
        batch_op.drop_column("review_item_id")

    with op.batch_alter_table("model_invocations") as batch_op:
        batch_op.drop_constraint("uq_model_invocation_processor_job", type_="unique")
        batch_op.drop_constraint("ck_model_invocation_status", type_="check")
        batch_op.drop_constraint("fk_model_invocations_processor_job_id", type_="foreignkey")
        for column in (
            "external_network_used",
            "error_message",
            "completed_at",
            "started_at",
            "status",
            "processor_job_id",
        ):
            batch_op.drop_column(column)

    op.drop_index("ix_processor_jobs_status_available", table_name="processor_jobs")
    op.drop_table("processor_jobs")

    with op.batch_alter_table("review_items") as batch_op:
        batch_op.drop_column("source_revision")
