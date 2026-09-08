"""Explicit opt-in discovery entrypoints; existing Explore paths stay unchanged."""

from pathlib import Path

from ..capabilities.explore.discovery_runtime import (
    evaluate_discovery,
    load_json,
    read_discovery,
    run_discovery,
)

DISCOVERY_COMMANDS = {"discover", "discovery-readback", "discovery-evaluate"}


def register_explore_discovery_commands(sub, add_format) -> None:
    discover = sub.add_parser(
        "discover",
        help="Preview a default-off receipt-bound discovery run; --execute captures and settles evaluation scope.",
    )
    add_format(discover)
    discover.add_argument("--goal-id", required=True)
    discover.add_argument(
        "--binding-file",
        required=True,
        help="Owner-reviewed local provider bindings; enabled must explicitly be true.",
    )
    discover.add_argument(
        "--trigger-id",
        required=True,
        help="Stable idempotency key; Core allocates the session ordinal.",
    )
    discover.add_argument("--cutoff-at", required=True)
    discover.add_argument("--execute", action="store_true")
    for command in ("discovery-readback", "discovery-evaluate"):
        parser = sub.add_parser(
            command,
            help="Verify Core discovery receipts"
            + (
                " and invoke the frozen evaluator."
                if command.endswith("evaluate")
                else "."
            ),
        )
        add_format(parser)
        parser.add_argument("--goal-id", required=True)
        parser.add_argument("--run-id", required=True)
        if command.endswith("evaluate"):
            parser.add_argument("--binding-file", required=True)
            parser.add_argument(
                "--input-file",
                required=True,
                help="Existing evaluator input with the exact frozen universe; proposals do not supply factor judgments.",
            )
            parser.add_argument("--execute", action="store_true")


def handle_explore_discovery_command(
    args, *, registry_path: Path, runtime_root: Path
) -> dict:
    common = {"runtime_root": runtime_root, "goal_id": args.goal_id}
    if args.explore_command == "discover":
        return run_discovery(
            **common,
            registry_path=registry_path,
            binding=load_json(Path(args.binding_file)),
            trigger_id=args.trigger_id,
            cutoff_at=args.cutoff_at,
            execute=args.execute,
        )
    if args.explore_command == "discovery-readback":
        return read_discovery(**common, run_id=args.run_id)
    return evaluate_discovery(
        **common,
        registry_path=registry_path,
        run_id=args.run_id,
        provider_input=load_json(Path(args.input_file)),
        execute=args.execute,
        binding=load_json(Path(args.binding_file)),
    )
