# youtube-video-editing

A deterministic, frame-accurate editing timeline generator for DaVinci Resolve. It turns either a JSON edit plan or a plain-text YouTube Ask Studio chronological edit plan and an original video into an editable FCPXML timeline (plus OTIO and human-readable reports); it never modifies the source media.

## Requirements

- Python 3.11 or newer
- FFmpeg / FFprobe available on `PATH`
- Optional: OpenTimelineIO (`pip install opentimelineio`) for the `.otio` export

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,otio]'
```

## Build a timeline

```bash
python -m youtube_video_editing build \
  --source "/absolute/path/to/source video.mp4" \
  --plan "plans/daily_vlog.json" \
  --output-dir "output/daily_vlog"
```

The source path is passed as a normal CLI argument and supports spaces. `--fps` can override the timeline frame rate; otherwise the source frame rate is used. The output directory contains an FCPXML, an OTIO file when the optional package is installed, a Markdown report, an EDL CSV, and the validated normalized plan. `--outro-variant` is only for JSON plans that explicitly define optional endings; the latest supplied transcript plan has fixed ranges and no alternate ending.

## Build directly from YouTube Ask Studio text

1. Copy the complete Ask Studio response into a UTF-8 text or Markdown file, for example `plans/ask_studio_daily_vlog.md`.
2. Build the Resolve timeline directly from that response:

```bash
python -m youtube_video_editing build \
  --source "/absolute/path/to/daily-vlog.mp4" \
  --ask-studio-text "plans/ask_studio_daily_vlog.md" \
  --output-dir "output/daily_vlog"
```

The attached transcript-aligned plan has fixed source ranges and one defined sign-off; no alternate-ending selection is used for this plan. You can validate the text before probing or building the source media:

```bash
python -m youtube_video_editing validate-plan --ask-studio-text "plans/ask_studio_daily_vlog.md"
```

The current parser reads all 10 sequence headings and the single source In/Out range on each top-level clip bullet in the latest supplied Hindi transcript document. It creates exactly 20 source clips. Nested word-level transcript timestamps remain in the Markdown source as reference material; they do not silently create extra cuts. No old source ranges or alternate outro ranges are carried forward. The JSON workflow remains available, and `plans/daily_vlog.json` is regenerated from this same latest timeline.

## Editing-plan format

Plans are standalone JSON documents. Each section contains an ordered list of clips with `source_in` and `source_out` elapsed timestamps (`HH:MM:SS[.fraction]`). Source In is inclusive and Source Out is exclusive. Clips within a section are placed consecutively at normal speed and retain the source audio when available. Reusing a source range is supported and intentional. A section's `target_start` controls its timeline position: if earlier footage ends before it, the builder emits an explicit black/silent gap; if earlier footage runs past it, the section is delayed and a warning is recorded. Source ranges are never silently trimmed to force a section into its target window. Target end times are used to report section overruns/unused time and to extend the final sequence when necessary.

The current authoritative transcript and clip list is `plans/ask_studio_daily_vlog.md`. The equivalent normalized JSON is `plans/daily_vlog.json`; see `plans/README.md` for the schema and timing rules.

## DaVinci Resolve

1. Run the build command and inspect `edit_report.md` for warnings and section timing differences.
2. In Resolve, choose **File → Import Timeline → Import AAF, XML…** (menu wording can vary by Resolve release).
3. Select the generated `.fcpxml` file. The XML references the original source video through an absolute, URI-escaped file URL; keep that source file at the same path.
4. Review the imported timeline and confirm media is online and audio/video are linked as expected.

The exporter emits the conservative FCPXML 1.10 interchange format for compatibility with DaVinci Resolve 21.1 and later. Each timeline asset-clip explicitly declares the sequence format. The local environment used for development does not provide an automated Resolve import test, so application-level compatibility still needs to be confirmed by importing the generated file in Resolve. No Resolve Studio scripting API is used.

## Validation and tests

```bash
pytest
python -m youtube_video_editing validate-plan --plan plans/daily_vlog.json
```

Unit tests exercise rational frame conversion, parsing, sequential timeline math, FCPXML structure, XML media references and duplicate preservation. The test suite creates synthetic media and does not need your recording. The actual build command will refuse to export if FFprobe cannot inspect the source, if a requested range is outside its duration, or if frame alignment is invalid.

## Important behavior

- The source recording is read-only; no render or transcode is performed.
- Source timestamps are quantized to the source media's probed frame grid using rational arithmetic; the report records exact frame-derived source and timeline positions.
- The final duration includes all selected source clips plus explicit target-alignment gaps and final padding to the last target end. With the current supplied ranges, the final timeline is exactly 15:00. If a future source range overruns a target window, the following sequence is delayed rather than silently trimming transcript audio.
- The FCPXML contains a primary storyline with every selected source clip and explicit gap elements for target alignment, plus synchronized source audio where an audio stream exists. If the source has no audio stream, only video is emitted. The optional OTIO export mirrors the same gaps on the video and audio tracks.
- The optional OTIO writer uses the same normalized timeline model. If OTIO is not installed, the FCPXML/report deliverables are still generated and the report records the skipped optional export.
