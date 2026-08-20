from nanexus_event_intelligence.adapters.frigate.cli import build_parser


def test_cli_requires_output_and_source_version() -> None:
    args = build_parser().parse_args(
        ["--output", "fixtures/frigate/0.17/capture", "--source-version", "0.17.1"]
    )
    assert args.source_version == "0.17.1"
    assert args.duration == 300
