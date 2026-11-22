"""Load and validate an external JSON editing plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ClipPlan, EditPlan, SectionPlan
from .timecode_utils import parse_frame_rate, parse_timestamp


class PlanError(ValueError):
    pass


def _clip_from_dict(data: dict[str, Any], where: str) -> ClipPlan:
    try:
        clip_id = str(data["id"]).strip()
        if not clip_id:
            raise ValueError("id cannot be empty")
        source_in = parse_timestamp(data["source_in"], field=f"{where}.source_in")
        source_out = parse_timestamp(data["source_out"], field=f"{where}.source_out")
        description = str(data.get("description", clip_id)).strip()
        if source_out <= source_in:
            raise ValueError("source_out must be greater than source_in")
        return ClipPlan(clip_id, source_in, source_out, description)
    except (KeyError, ValueError, TypeError) as exc:
        raise PlanError(f"Invalid clip at {where}: {exc}") from exc


def parse_plan_document(
    document: dict[str, Any], *, outro_variant: str | None = None
) -> EditPlan:
    if not isinstance(document, dict):
        raise PlanError("The plan root must be a JSON object")
    project_name = str(document.get("project_name", "Untitled Edit")).strip()
    sequence_name = str(document.get("sequence_name", project_name)).strip()
    if not project_name or not sequence_name:
        raise PlanError("project_name and sequence_name cannot be empty")
    try:
        raw_fps = document.get("timeline_fps")
        fps = None if raw_fps in (None, "") else parse_frame_rate(raw_fps, field="timeline_fps")
    except ValueError as exc:
        raise PlanError(str(exc)) from exc

    raw_sections = document.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise PlanError("Plan must contain a non-empty sections array")

    variant_map = document.get("outro_variants", {})
    if not isinstance(variant_map, dict):
        raise PlanError("outro_variants must be a JSON object")
    selected_variant = outro_variant or str(document.get("default_outro_variant", "late"))
    if variant_map and selected_variant not in variant_map:
        available = ", ".join(sorted(variant_map))
        raise PlanError(
            f"Unknown outro variant {selected_variant!r}; available variants: {available}"
        )

    section_ids: set[str] = set()
    clip_ids: set[str] = set()
    sections: list[SectionPlan] = []
    variant = variant_map.get(selected_variant) if variant_map else None
    variant_section_id = None
    variant_clip = None
    if variant is not None:
        if not isinstance(variant, dict):
            raise PlanError(f"outro_variants.{selected_variant} must be an object")
        variant_section_id = str(variant.get("section_id", ""))
        raw_variant_clip = variant.get("clip")
        if not isinstance(raw_variant_clip, dict):
            raise PlanError(f"outro_variants.{selected_variant}.clip must be an object")
        variant_clip = _clip_from_dict(
            raw_variant_clip, f"outro_variants.{selected_variant}.clip"
        )

    for section_index, raw_section in enumerate(raw_sections):
        where = f"sections[{section_index}]"
        if not isinstance(raw_section, dict):
            raise PlanError(f"{where} must be an object")
        section_id = str(raw_section.get("id", "")).strip()
        name = str(raw_section.get("name", "")).strip()
        if not section_id or not name:
            raise PlanError(f"{where} requires non-empty id and name")
        if section_id in section_ids:
            raise PlanError(f"Duplicate section id: {section_id}")
        section_ids.add(section_id)

        try:
            target_start = (
                None if raw_section.get("target_start") in (None, "")
                else parse_timestamp(raw_section["target_start"], field=f"{where}.target_start")
            )
            target_end = (
                None if raw_section.get("target_end") in (None, "")
                else parse_timestamp(raw_section["target_end"], field=f"{where}.target_end")
            )
        except ValueError as exc:
            raise PlanError(str(exc)) from exc
        if target_start is not None and target_end is not None and target_end <= target_start:
            raise PlanError(f"{where} target_end must be greater than target_start")

        raw_clips = raw_section.get("clips")
        if not isinstance(raw_clips, list):
            raise PlanError(f"{where}.clips must be an array")
        clips = [
            _clip_from_dict(item, f"{where}.clips[{clip_index}]")
            for clip_index, item in enumerate(raw_clips)
        ]
        if section_id == variant_section_id and variant_clip is not None:
            clips.append(variant_clip)
        if not clips:
            raise PlanError(f"{where} must contain at least one clip")
        for clip in clips:
            if clip.clip_id in clip_ids:
                raise PlanError(f"Duplicate clip id: {clip.clip_id}")
            clip_ids.add(clip.clip_id)
        sections.append(
            SectionPlan(
                section_id=section_id,
                name=name,
                target_start=target_start,
                target_end=target_end,
                purpose=str(raw_section.get("purpose", "")).strip(),
                clips=tuple(clips),
            )
        )

    if variant_clip is not None and variant_section_id not in section_ids:
        raise PlanError(
            f"Outro variant {selected_variant!r} references unknown section "
            f"{variant_section_id!r}"
        )
    return EditPlan(
        project_name=project_name,
        sequence_name=sequence_name,
        timeline_fps=fps,
        sections=tuple(sections),
        selected_outro_variant=selected_variant,
        source_document=document,
    )


def load_edit_plan(path: str | Path, *, outro_variant: str | None = None) -> EditPlan:
    plan_path = Path(path).expanduser().resolve()
    if not plan_path.is_file():
        raise PlanError(f"Editing plan does not exist: {plan_path}")
    try:
        document = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError(
            f"Invalid JSON in {plan_path}, line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise PlanError(f"Could not read editing plan {plan_path}: {exc}") from exc
    return parse_plan_document(document, outro_variant=outro_variant)
