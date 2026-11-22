from fractions import Fraction
from pathlib import Path

import pytest

from youtube_video_editing.ask_studio_parser import load_ask_studio_text, parse_ask_studio_text
from youtube_video_editing.timeline_parser import PlanError


ROOT = Path(__file__).resolve().parents[1]
LATEST_PLAN = ROOT / "plans" / "ask_studio_daily_vlog.md"

EXPECTED_IDS = [
    "1A", "1B", "1C", "2A", "3A", "3B", "3C", "3D", "4A", "5A",
    "6A", "6B", "6C", "7A", "8A", "8B", "8C", "9A", "10A", "10B",
]

EXPECTED_SOURCE_RANGES = [
    (165, 171),
    (4255, 4263),
    (5480, 5487),
    (3543, 3610),
    (165, 202),
    (326, 360),
    (930, 958),
    (3479, 3496),
    (3801, 3880),
    (4204, 4296),
    (4395, 4441),
    (4480, 4500),
    (5204, 5225),
    (5470, 5505),
    (5928, 5975),
    (6341, 6355),
    (6369, 6380),
    (6555, 6611),
    (6812, 6850),
    (3788, 3800),
]

EXPECTED_TARGET_WINDOWS = [
    (0, 20),
    (20, 85),
    (85, 270),
    (270, 360),
    (360, 435),
    (435, 570),
    (570, 645),
    (645, 765),
    (765, 825),
    (825, 900),
]


def test_latest_attached_plan_contains_exactly_all_defined_clips_and_ranges():
    plan = load_ask_studio_text(LATEST_PLAN)
    clips = [clip for section in plan.sections for clip in section.clips]

    assert len(plan.sections) == 10
    assert [len(section.clips) for section in plan.sections] == [3, 1, 4, 1, 1, 3, 1, 3, 1, 2]
    assert [clip.clip_id for clip in clips] == EXPECTED_IDS
    assert [
        (clip.source_in_requested, clip.source_out_requested) for clip in clips
    ] == [(Fraction(start), Fraction(end)) for start, end in EXPECTED_SOURCE_RANGES]
    assert [
        (section.target_start, section.target_end) for section in plan.sections
    ] == [
        (Fraction(start), Fraction(end)) for start, end in EXPECTED_TARGET_WINDOWS
    ]


def test_nested_word_level_transcript_cues_do_not_become_extra_clips():
    plan = load_ask_studio_text(LATEST_PLAN)

    # Sequence 2 has many nested transcript cue timestamps but one defined
    # source clip. The parser must not split it into phrase-level cuts.
    assert len(plan.sections[1].clips) == 1
    assert plan.sections[1].clips[0].clip_id == "2A"
    assert (plan.sections[1].clips[0].source_in_requested,
            plan.sections[1].clips[0].source_out_requested) == (3543, 3610)

    # The complete new plan has 20 top-level source ranges, not all nested cues.
    assert sum(len(section.clips) for section in plan.sections) == 20


def test_parser_rejects_bullet_without_its_own_top_level_source_range():
    malformed = """### Sequence 1: Test (फाइनल वीडियो: 00:00 – 00:10)
*   **Cut 1A:** no top-level source range
    *   **00:00:01 - 00:00:02:** transcript cue only
"""
    with pytest.raises(PlanError, match="top-level source In/Out range"):
        parse_ask_studio_text(malformed)
