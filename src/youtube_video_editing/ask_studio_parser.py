"""Parse the current transcript-aligned YouTube edit plan.

Only timestamp ranges on top-level clip bullets define edit boundaries. Nested
word/phrase transcript cue ranges remain reference text and never become clips.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import EditPlan
from .timeline_parser import PlanError, parse_plan_document

_SECTION_RE = re.compile(
    r"^### Sequence (?P<number>\d+): (?P<name>.+?) \((?:Target|फाइनल वीडियो): "
    r"(?P<start>\d{2}:\d{2})\s*[–-]\s*(?P<end>\d{2}:\d{2})\)",
    re.MULTILINE | re.IGNORECASE,
)

# Match first-level Markdown bullets only. [ \t] is deliberate: using \s here
# would consume the newline after a label-only heading and capture the first
# nested transcript cue as if it were the top-level clip range.
_BULLET_RE = re.compile(
    r"^[*-][ \t]+\*\*(?P<label>.+?):\*\*[ \t]*(?P<text>[^\r\n]*)$",
    re.MULTILINE,
)

_RANGE_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*[–—-]\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"


def parse_ask_studio_text(text: str) -> EditPlan:
    """Parse fixed source ranges, retaining only the ranges explicitly listed."""
    if not isinstance(text, str) or not text.strip():
        raise PlanError("Ask Studio text is empty")

    headings = list(_SECTION_RE.finditer(text))
    if not headings:
        raise PlanError(
            "No sequence headings found; expected "
            "'### Sequence N: Name (फाइनल वीडियो: MM:SS – MM:SS)'"
        )

    section_numbers = [int(item.group("number")) for item in headings]
    if section_numbers != list(range(1, len(headings) + 1)):
        raise PlanError(
            f"Sequence numbers must be consecutive from 1; found {section_numbers}"
        )

    sections: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, heading in enumerate(headings):
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end():body_end]
        bullets = list(_BULLET_RE.finditer(body))
        section_number = int(heading.group("number"))
        section_name = heading.group("name").strip()
        section_id = _slug(section_name)
        clips: list[dict[str, str]] = []

        for bullet in bullets:
            label = bullet.group("label").strip()
            direct_text = bullet.group("text").strip()
            if label == "बोले गए शब्द व टाइमलाइन" and not direct_text:
                continue

            # Timestamp values are sometimes surrounded by Markdown backticks.
            range_text = direct_text.replace(chr(96), "")
            # Do not search the bullet's nested block: transcript cue timestamps
            # are alignment references, not additional cuts.
            ranges = list(_RANGE_RE.finditer(range_text))
            if not ranges:
                raise PlanError(
                    f"Sequence {section_number}, bullet {label!r} has no "
                    "top-level source In/Out range"
                )
            if len(ranges) != 1:
                raise PlanError(
                    f"Sequence {section_number}, bullet {label!r} must define "
                    f"exactly one top-level source range; found {len(ranges)}"
                )

            id_match = re.search(r"(?:Clip|Cut)\s+(\d+[A-Z]?)", label, re.IGNORECASE)
            if id_match:
                clip_id = id_match.group(1)
            elif label in {"रॉ टाइमस्टैम्प", "Raw Timestamps"}:
                clip_id = f"{section_number}A"
            else:
                clip_id = f"{section_number}{chr(65 + len(clips))}"

            if clip_id in seen_ids:
                raise PlanError(
                    f"Duplicate clip identifier extracted from Ask Studio text: {clip_id}"
                )
            seen_ids.add(clip_id)

            source_range = ranges[0]
            source_in = source_range.group("start")
            source_out = source_range.group("end")
            clips.append({
                "id": clip_id,
                "source_in": source_in,
                "source_out": source_out,
                "description": f"{label}: {source_in} – {source_out}",
            })

        if not clips:
            raise PlanError(
                f"Sequence {section_number} '{section_name}' contains no source clips"
            )

        sections.append({
            "id": section_id,
            "name": section_name,
            "target_start": heading.group("start"),
            "target_end": heading.group("end"),
            "purpose": "Transcript-aligned sequence from the latest supplied timeline.",
            "clips": clips,
        })

    document = {
        "project_name": "YouTube Ask Studio Edit",
        "sequence_name": "YouTube Ask Studio Edit",
        "default_outro_variant": "fixed",
        "sections": sections,
    }
    return parse_plan_document(document, outro_variant="fixed")


def load_ask_studio_text(path: str | Path) -> EditPlan:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise PlanError(f"Ask Studio text file does not exist: {source}")
    try:
        return parse_ask_studio_text(source.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise PlanError(f"Could not read Ask Studio text file {source}: {exc}") from exc
