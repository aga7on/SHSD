"""Run one local Qwen narration against a fixed accepted-claim fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shsd.captions import (
    NarrationClaim,
    NarrationEventRef,
    NarrationRequest,
    QwenNarrator,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks" / "reports" / "narrator_smoke.json",
    )
    args = parser.parse_args()
    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = lock["models"]["qwen3_0_6b"]
    request = NarrationRequest(
        stream_id="narrator-smoke",
        epoch=0,
        event_refs=(NarrationEventRef("evt-1", 1),),
        claims=(
            NarrationClaim(
                claim_id="claim-1",
                event_id="evt-1",
                revision=1,
                start_ms=1200,
                end_ms=4200,
                text_ru="Слышна музыка.",
                evidence_refs=("audio:1200-4200", "embedding:audio:test"),
            ),
        ),
        state={"active_music": "music_present"},
        delta={"changed_fields": []},
    )
    narrator = QwenNarrator(
        model,
        ROOT / "models",
        ROOT,
        threads=args.threads,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout_seconds,
    )
    result = narrator.narrate(request)
    report = {
        "schema_version": 1,
        "runtime_target": "cpu",
        "threads": args.threads,
        "max_tokens": args.max_tokens,
        "timeout_seconds": args.timeout_seconds,
        "input": request.facts_payload(),
        "narration": result.to_dict(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
