# F10 blind review guide

Guide version: `f10-blind-review-v1`

## Blindness and attribution

Review only the two media files named in `review_manifest.json`, this guide, and the blank CSV. Do not open the model reports, contact sheet, captions, candidate labels, or score files until the CSV is submitted. The clips are excerpts from *Tears of Steel*, attributed to the Blender Foundation under CC BY 3.0.

Use your own reviewer ID. Set `verification_status` to:

- `human_verified` when you reviewed the full clip and the labels and timing below match what you independently saw or heard.
- `partial` when you reviewed it but one or more labels or boundaries remain unclear.
- `unverified` when the row has not been independently reviewed.

Use the guide version above verbatim. Leave fields blank when the clip does not support a claim; do not infer hidden actions or instruments.

## VIDEO-only row (`video_01`)

Clip time 0–10 s maps to original-film source PTS 120000–130000 ms. The available one-frame-per-second evidence points are listed as `review_frame_pts_ms` in the manifest. Cite at least two distinct points from that list in `evidence_frame_source_ms`, separated by semicolons. Each cited frame should show evidence for the action, not only the subject.

Describe visible entities in `observed_entities_ru`. Use `subject_ru`, `action_ru`, and `object_ru` for the clearest entity–action–object event. This example needs a visible object tied to the action; if none is clear, mark the row `partial` and explain why in `notes`. Put a natural Russian sentence describing the action sequence in `action_sequence_ru`. Enter the action's start and end in original-film milliseconds. Use the first visible evidence of the action for the start and the last visible evidence for the end; the end is exclusive. Keep the interval inside 120000–130000 ms.

## AUDIO-only row (`audio_01`)

Clip time 0–20 s maps to original-film source PTS 185000–205000 ms. The four 5-second review windows are listed in the manifest. Describe the audible scene in `audio_scene_ru`, including speech and ambience when clear.

For `music_layer_type`, use `vocal`, `percussion`, `bass`, `instrument_family`, `music_presence`, or `unknown`. For `music_layer_state`, use `none`, `present`, `onset`, `offset`, `changed`, or `unknown`. Use `unknown` only with `partial` or `unverified`; a `human_verified` row must state what happened to music. Describe an audible change in `music_layer_change_ru`; do not call a scene handoff a musical change unless the music itself changes. For a transition, enter its source-time start/end, identify its layer type, and cite at least one `evidence_audio_source_ms` point before it and one after it. Separate multiple evidence points with semicolons. Leave transition times blank if no music transition is audible.

If the clip has no audible music transition, record that accurately. The CSV validator will accept a complete human review, but the B0 example builder will refuse to label it as a positive transition; we will need another excerpt for that success example.

## CSV format

Keep the two `clip_id` values unchanged and include exactly one row per clip. Separate multiple timestamps with semicolons. Use integer milliseconds in original-source time, without units or thousands separators. Preserve the header and UTF-8 encoding. The validator is `scripts/validate_f10_review_labels.py`; an empty template is expected to fail as incomplete.

After both rows are `human_verified`, run `python scripts/build_f10_reviewed_graphs.py --narrate-qwen`. It checks the labels again, writes separate VIDEO-only and AUDIO-only EventGraph bundles with accepted, provenance-tagged B0 claims, runs the pinned local CPU Qwen narrator, and saves the actual L3 captions with claim coverage and fallback status. It refuses to build the audio success example unless the review confirms an onset, offset, or change in a music layer. Use `--threads`, `--max-tokens`, and `--timeout-seconds` to reproduce a different documented CPU configuration.
