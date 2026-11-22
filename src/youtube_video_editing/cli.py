"""Command-line interface for timeline creation and plan validation."""
from __future__ import annotations

import argparse
import sys
from fractions import Fraction
from pathlib import Path

from .ask_studio_parser import load_ask_studio_text
from .report_generator import write_edit_report, write_edl_csv, write_validated_plan
from .resolve_exporter import export_fcpxml, export_otio
from .timecode_utils import parse_frame_rate
from .timeline_builder import TimelineBuildError, build_timeline
from .timeline_parser import PlanError, load_edit_plan
from .timeline_validator import TimelineValidationError, validate_fcpxml, validate_timeline
from .video_metadata import MetadataError, probe_video


def _parse_fps(value: str) -> Fraction:
    try:
        return parse_frame_rate(value, field="--fps")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _load_plan(args: argparse.Namespace):
    if args.ask_studio_text:
        return load_ask_studio_text(args.ask_studio_text)
    return load_edit_plan(args.plan, outro_variant=args.outro_variant)


def _build_command(args: argparse.Namespace) -> int:
    plan = _load_plan(args)
    source = probe_video(args.source)
    timeline = build_timeline(plan, source, timeline_fps=args.fps)
    validate_timeline(timeline)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or "daily_vlog"
    fcpxml_path = export_fcpxml(timeline, output_dir / f"{stem}.fcpxml")
    validate_fcpxml(fcpxml_path, timeline)

    optional_notes: list[str] = []
    try:
        export_otio(timeline, output_dir / f"{stem}.otio")
    except RuntimeError as exc:
        optional_notes.append(f"OTIO export skipped: {exc}")

    write_edl_csv(timeline, output_dir / "edit_decision_list.csv")
    write_validated_plan(timeline, output_dir / "validated_edit_plan.json")
    report_path = write_edit_report(timeline, output_dir / "edit_report.md", optional_export_notes=tuple(optional_notes))

    print(f"FCPXML: {fcpxml_path}")
    if (output_dir / f"{stem}.otio").exists():
        print(f"OTIO: {output_dir / f'{stem}.otio'}")
    print(f"Report: {report_path}")
    print(f"Clips: {len(timeline.clips)} | Sections: {len(timeline.sections)}")
    print(f"Timeline duration: {timeline.duration} seconds")
    print("Structural validation: PASSED")
    if optional_notes:
        print(optional_notes[0], file=sys.stderr)
    return 0


def _validate_plan_command(args: argparse.Namespace) -> int:
    plan = _load_plan(args)
    clip_count = sum(len(section.clips) for section in plan.sections)
    if args.ask_studio_text:
        print(f"Plan valid: {len(plan.sections)} sections, {clip_count} clips, fixed source ranges")
    else:
        print(f"Plan valid: {len(plan.sections)} sections, {clip_count} clips, outro variant={plan.selected_outro_variant}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-video-editing",
        description="Build a deterministic, editable DaVinci Resolve timeline.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="Probe source media, validate a plan, and export timelines")
    build.add_argument("--source", required=True, help="Absolute or relative path to original source video")
    plan_input = build.add_mutually_exclusive_group(required=True)
    plan_input.add_argument("--plan", help="Path to editing-plan JSON")
    plan_input.add_argument("--ask-studio-text", help="Path to Markdown/text response copied from YouTube Ask Studio")
    build.add_argument("--output-dir", required=True, help="Directory for generated timeline and reports")
    build.add_argument("--fps", type=_parse_fps, help="Optional timeline frame rate, e.g. 30 or 30000/1001")
    build.add_argument("--outro-variant", choices=("late", "early"), help="Select a JSON plan's optional ending (not used for fixed Ask Studio timelines)")
    build.add_argument("--name", help="Output filename stem (default: daily_vlog)")
    build.set_defaults(handler=_build_command)

    validate = commands.add_parser("validate-plan", help="Validate a JSON plan or Ask Studio text without source media")
    validate_input = validate.add_mutually_exclusive_group(required=True)
    validate_input.add_argument("--plan", help="Path to editing-plan JSON")
    validate_input.add_argument("--ask-studio-text", help="Path to YouTube Ask Studio text response")
    validate.add_argument("--outro-variant", choices=("late", "early"), help="Select a JSON plan's optional ending (not used for fixed Ask Studio timelines)")
    validate.set_defaults(handler=_validate_plan_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (PlanError, MetadataError, TimelineBuildError, TimelineValidationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
