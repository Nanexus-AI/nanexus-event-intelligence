"""CLI for canonical event export and deterministic dry-run replay."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from uuid6 import uuid7

from nanexus_event_intelligence.alerts.replay import ShadowDecisionDryRunSink
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.persistence.database import create_engine, create_session_factory
from nanexus_event_intelligence.replay.bundle import ReplayBundleError, load_replay_bundle
from nanexus_event_intelligence.replay.engine import DryRunDigestSink, ReplayEngine
from nanexus_event_intelligence.replay.exporter import ObservationExporter, ReplayExportError
from nanexus_event_intelligence.replay.models import ReplayEvent


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Export and replay canonical Nanexus events")
    commands = root.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="export canonical observations")
    export.add_argument("--source-id", required=True, type=UUID)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--from", dest="occurred_from", type=parse_datetime)
    export.add_argument("--to", dest="occurred_to", type=parse_datetime)
    export.add_argument("--limit", type=int, default=100_000)
    export.add_argument("--exported-at", type=parse_datetime)

    replay = commands.add_parser("run", help="validate and dry-run a replay bundle")
    replay.add_argument("bundle", type=Path)
    replay.add_argument("--speed", type=float, default=0)
    replay.add_argument("--step", action="store_true")
    replay.add_argument("--fixed-clock", type=parse_datetime)
    replay.add_argument("--run-id", type=UUID)
    replay.add_argument("--evaluate-alerts", action="store_true")
    return root


async def export_command(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            manifest = await ObservationExporter(session).export(
                source_instance_id=args.source_id,
                output_dir=args.output,
                exported_at=args.exported_at or datetime.now(UTC),
                occurred_from=args.occurred_from,
                occurred_to=args.occurred_to,
                limit=args.limit,
            )
        print(
            json.dumps(
                {
                    "status": "exported",
                    "bundle_id": str(manifest.bundle_id),
                    "event_count": manifest.event_count,
                    "events_sha256": manifest.events_sha256,
                    "truncated": manifest.truncated,
                },
                separators=(",", ":"),
            )
        )
    finally:
        await engine.dispose()


async def replay_command(args: argparse.Namespace) -> None:
    if args.step and args.speed != 0:
        raise ValueError("--step and --speed cannot be used together")
    bundle = load_replay_bundle(args.bundle)
    sink = ShadowDecisionDryRunSink() if args.evaluate_alerts else DryRunDigestSink()

    async def stepper(sequence: int, event: ReplayEvent) -> None:
        del event
        await asyncio.to_thread(
            input, f"Replay event {sequence + 1}/{len(bundle.records)} [Enter] "
        )

    result = await ReplayEngine(
        bundle,
        sink,
        run_id=args.run_id or uuid7(),
        speed=args.speed,
        fixed_clock=args.fixed_clock,
        stepper=stepper if args.step else None,
    ).run()
    alert_output = (
        {
            "shadow_decision_sha256": sink.output_sha256,
            "shadow_outcomes": [item.outcome for item in sink.evaluations],
        }
        if isinstance(sink, ShadowDecisionDryRunSink)
        else {}
    )
    print(
        json.dumps(
            {
                "status": "dry-run-complete",
                "run_id": str(result.run_id),
                "bundle_id": str(result.bundle_id),
                "event_count": result.emitted,
                "output_sha256": result.output_sha256,
                "production_side_effects": False,
                **alert_output,
            },
            separators=(",", ":"),
        )
    )


async def async_main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "export":
        await export_command(args)
    else:
        await replay_command(args)


def main() -> None:
    try:
        asyncio.run(async_main())
    except (ReplayBundleError, ReplayExportError, SQLAlchemyError, ValueError) as error:
        raise SystemExit(f"Replay command failed: {type(error).__name__}") from None
    except KeyboardInterrupt:
        print("Replay stopped by user")


if __name__ == "__main__":
    main()
