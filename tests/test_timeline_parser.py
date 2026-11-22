import json
from pathlib import Path

import pytest

from youtube_video_editing.timeline_parser import PlanError, load_edit_plan, parse_plan_document


ROOT = Path(__file__).resolve().parents[1]


def test_normalized_json_is_the_latest_transcript_aligned_timeline():
    plan = load_edit_plan(ROOT / "plans" / "daily_vlog.json")
    assert len(plan.sections) == 10
    assert plan.sections[0].name == "Teaser / Hook"
    assert plan.sections[-1].name == "Cook Bhaiya & Vlog Sign-Off"

    clips = {clip.clip_id: clip for section in plan.sections for clip in section.clips}
    assert len(clips) == 20
    assert clips["1A"].source_in_requested == clips["3A"].source_in_requested == 165
    assert clips["1B"].source_out_requested < clips["5A"].source_out_requested
    assert clips["3B"].source_in_requested == 326
    assert clips["3D"].source_in_requested == 3479
    assert clips["5A"].source_in_requested == 4204
    assert clips["8A"].source_in_requested == 5928
    assert clips["10B"].source_in_requested == 3788
    assert clips["10B"].source_out_requested == 3800
    assert (plan.sections[-1].target_start, plan.sections[-1].target_end) == (825, 900)


def test_json_plan_format_still_supports_optional_outro_variants():
    document = {
        "project_name": "Variant test",
        "sections": [{
            "id": "story",
            "name": "Story",
            "clips": [{"id": "main", "source_in": "0", "source_out": "1"}],
        }],
        "outro_variants": {
            "late": {
                "section_id": "story",
                "clip": {"id": "closing", "source_in": "10", "source_out": "11"},
            },
            "early": {
                "section_id": "story",
                "clip": {"id": "closing", "source_in": "20", "source_out": "21"},
            },
        },
    }
    late = parse_plan_document(document, outro_variant="late")
    early = parse_plan_document(document, outro_variant="early")
    assert late.sections[-1].clips[-1].source_in_requested == 10
    assert early.sections[-1].clips[-1].source_in_requested == 20


def test_duplicate_identifiers_are_rejected():
    document = {
        "sections": [
            {"id": "s1", "name": "One", "clips": [
                {"id": "x", "source_in": "0", "source_out": "1"}
            ]},
            {"id": "s2", "name": "Two", "clips": [
                {"id": "x", "source_in": "2", "source_out": "3"}
            ]},
        ]
    }
    with pytest.raises(PlanError, match="Duplicate clip id"):
        parse_plan_document(document)


def test_target_end_must_follow_target_start():
    document = {
        "sections": [{
            "id": "s1", "name": "One", "target_start": "00:00:10",
            "target_end": "00:00:09",
            "clips": [{"id": "x", "source_in": "0", "source_out": "1"}],
        }]
    }
    with pytest.raises(PlanError, match="target_end"):
        parse_plan_document(document)


def test_plan_json_is_valid():
    json.loads((ROOT / "plans" / "daily_vlog.json").read_text(encoding="utf-8"))
