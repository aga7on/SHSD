"""Profile real L1 cosine/margin decisions and text-hypothesis separation."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from shsd.embeddings.provider import EmbeddingProvider
from shsd.semantic.hypotheses import HypothesisProfile, encode_profile_candidates, load_profiles

ROOT = Path(__file__).resolve().parents[1]


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p25": None, "median": None, "mean": None, "p75": None, "max": None}
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 6),
        "p25": round(float(np.quantile(ordered, 0.25)), 6),
        "median": round(float(statistics.median(ordered)), 6),
        "mean": round(float(statistics.mean(ordered)), 6),
        "p75": round(float(np.quantile(ordered, 0.75)), 6),
        "max": round(ordered[-1], 6),
    }


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0


def _profile_diagnostics(
    profiles: tuple[HypothesisProfile, ...], provider: EmbeddingProvider
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    axis_reports: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    for profile in profiles:
        encoded = encode_profile_candidates(profile, provider)
        axes_by_id = {axis.axis_id: axis for axis in profile.axes}
        for axis_id, candidate_records in encoded.items():
            axis = axes_by_id[axis_id]
            candidates = {item.candidate_id: item for item in axis.candidates}
            vectors = {
                candidate_id: np.asarray(record.embedding, dtype=np.float32)
                for candidate_id, record in candidate_records.items()
            }
            pairs: list[dict[str, Any]] = []
            items = list(axis.candidates)
            for left_index, left in enumerate(items):
                for right in items[left_index + 1 :]:
                    similarity = _cosine(vectors[left.candidate_id], vectors[right.candidate_id])
                    pairs.append(
                        {
                            "left_candidate": left.candidate_id,
                            "right_candidate": right.candidate_id,
                            "cosine": round(similarity, 6),
                            "left_text_en": left.text_en,
                            "right_text_en": right.text_en,
                        }
                    )
            axis_reports.append(
                {
                    "profile_id": profile.profile_id,
                    "profile_version": profile.profile_version,
                    "embedding_language": profile.embedding_language,
                    "axis_id": axis_id,
                    "modality": axis.modality,
                    "mutually_exclusive": axis.mutually_exclusive,
                    "candidate_count": len(items),
                    "candidates": [
                        {
                            "candidate_id": candidate_id,
                            "text_en": candidates[candidate_id].text_en,
                            "text_ru": candidates[candidate_id].text_ru,
                        }
                        for candidate_id in candidate_records
                    ],
                    "pairwise_text_cosine": sorted(
                        pairs, key=lambda item: item["cosine"], reverse=True
                    ),
                    "pairwise_cosine_distribution": _quantiles([item["cosine"] for item in pairs]),
                }
            )
            for candidate_id, record in candidate_records.items():
                candidate = candidates[candidate_id]
                all_candidates.append(
                    {
                        "profile_id": profile.profile_id,
                        "axis_id": axis_id,
                        "modality": axis.modality,
                        "candidate_id": candidate_id,
                        "text_en": candidate.text_en,
                        "text_ru": candidate.text_ru,
                        "embedding": np.asarray(record.embedding, dtype=np.float32),
                    }
                )
    cross_axis_pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(all_candidates):
        for right in all_candidates[left_index + 1 :]:
            if left["profile_id"] == right["profile_id"] and left["axis_id"] == right["axis_id"]:
                continue
            cross_axis_pairs.append(
                {
                    "left": f"{left['profile_id']}.{left['axis_id']}.{left['candidate_id']}",
                    "right": f"{right['profile_id']}.{right['axis_id']}.{right['candidate_id']}",
                    "modality": left["modality"],
                    "cosine": round(_cosine(left["embedding"], right["embedding"]), 6),
                    "left_text_en": left["text_en"],
                    "right_text_en": right["text_en"],
                }
            )
    cross_axis_pairs.sort(key=lambda item: item["cosine"], reverse=True)
    for item in all_candidates:
        item.pop("embedding")
    return axis_reports, cross_axis_pairs[:40]


def _window_diagnostics(
    input_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    rows = [
        json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line
    ]
    analysis = next(row for row in rows if row.get("record_type") == "analysis")
    window_matches = [row for row in rows if row.get("record_type") == "window_match"]
    policy = analysis["decision_policy"]
    per_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in window_matches:
        per_axis[row["axis_id"]].append(row)
    reports = []
    for axis_id, items in sorted(per_axis.items()):
        uncertain = [row for row in items if row.get("decision") == "uncertain"]
        top_candidates = [row.get("top_candidates", []) for row in items]
        runner_up_scores = [
            float(candidates[1]["raw_cosine"])
            for candidates in top_candidates
            if len(candidates) > 1 and candidates[1].get("raw_cosine") is not None
        ]
        top_gaps = [
            float(candidates[0]["raw_cosine"]) - float(candidates[1]["raw_cosine"])
            for candidates in top_candidates
            if len(candidates) > 1
            and candidates[0].get("raw_cosine") is not None
            and candidates[1].get("raw_cosine") is not None
        ]
        below_similarity = [
            row for row in uncertain if row.get("raw_cosine", -1.0) < policy["minimum_similarity"]
        ]
        margin_abstentions = [
            row for row in uncertain if row.get("raw_cosine", -1.0) >= policy["minimum_similarity"]
        ]
        reports.append(
            {
                "axis_id": axis_id,
                "count": len(items),
                "decisions": dict(Counter(row.get("decision") for row in items)),
                "candidate_counts": dict(Counter(row.get("candidate_id") for row in items)),
                "cosine": _quantiles([float(row["raw_cosine"]) for row in items]),
                "margin": _quantiles([float(row["margin"]) for row in items]),
                "runner_up_cosine": _quantiles(runner_up_scores),
                "top_two_gap": _quantiles(top_gaps),
                "thresholds_seen": sorted(
                    {json.dumps(row.get("thresholds", {}), sort_keys=True) for row in items}
                ),
                "uncertain_below_similarity_floor": len(below_similarity),
                "uncertain_above_similarity_floor": len(margin_abstentions),
                "accepted_examples": [
                    {
                        "start_ms": row["start_ms"],
                        "candidate_id": row["candidate_id"],
                        "cosine": row["raw_cosine"],
                        "margin": row["margin"],
                    }
                    for row in items
                    if row.get("decision") == "accepted"
                ],
            }
        )
    return analysis, policy, reports


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    policy = report["decision_policy"]
    lines = [
        "# Semantic Matcher diagnostic",
        "",
        f"- Input JSONL SHA-256: `{report['input_sha256']}`.",
        f"- EmbeddingGemma revision: `{report['model_revision']}`; "
        f"CPU threads: {report['threads']}.",
        f"- Run policy: min cosine {policy['minimum_similarity']}, "
        f"min margin {policy['minimum_margin']}; thresholds unchanged.",
        f"- L1 rows: {report['window_match_count']}; decisions: `{report['overall_decisions']}`.",
        "- No labels were joined. The existing 40-clip speech pack is described as "
        f"`{report['manual_label_context']['existing_40_clip_speech_pack']}`; "
        "it is not gold for music-prompt tuning.",
        "",
        "## Real-window score and abstention distributions",
        "",
        "| Axis | Rows | Decisions | Best cosine min / median / max | Runner-up median | "
        "Margin min / median / mean / max | Uncertain below / above cosine floor |",
        "|---|---:|---|---|---:|---|---:|",
    ]
    for axis in report["window_axes"]:
        cosine = axis["cosine"]
        runner_up = axis["runner_up_cosine"]["median"]
        margin = axis["margin"]
        lines.append(
            f"| `{axis['axis_id']}` | {axis['count']} | `{axis['decisions']}` | "
            f"{cosine['min']:.3f} / {cosine['median']:.3f} / {cosine['max']:.3f} | "
            f"{runner_up:.3f} | "
            f"{margin['min']:.3f} / {margin['median']:.3f} / "
            f"{margin['mean']:.3f} / {margin['max']:.3f} | "
            f"{axis['uncertain_below_similarity_floor']} / "
            f"{axis['uncertain_above_similarity_floor']} |"
        )
    lines.extend(
        [
            "",
            "## Within-axis text-hypothesis similarity",
            "",
            "| Profile | Axis | Candidates | Mean cosine | Closest pair |",
            "|---|---|---:|---:|---|",
        ]
    )
    for axis in report["hypothesis_axes"]:
        pairs = axis["pairwise_text_cosine"]
        closest = pairs[0] if pairs else None
        pair_text = (
            f"`{closest['left_candidate']}` / `{closest['right_candidate']}`: "
            f"{closest['cosine']:.3f}"
            if closest
            else "-"
        )
        distribution = axis["pairwise_cosine_distribution"]
        mean = distribution["mean"]
        mean_text = "-" if mean is None else f"{mean:.3f}"
        lines.append(
            f"| `{axis['profile_id']}` | `{axis['axis_id']}` | "
            f"{axis['candidate_count']} | {mean_text} | {pair_text} |"
        )
    lines.extend(
        [
            "",
            "## Closest text hypotheses across axes (all modalities)",
            "",
            "| Cosine | Left | Right |",
            "|---:|---|---|",
        ]
    )
    for item in report["closest_cross_axis_pairs"][:20]:
        lines.append(f"| {item['cosine']:.3f} | `{item['left']}` | `{item['right']}` |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Similarity and margin answer different questions. Current acceptance requires "
            "best media-to-text cosine ≥ 0.60 and a top-candidate lead ≥ 0.05.",
            "- Uncertainty can be a margin issue even when best cosine clears the floor. "
            "Visual axes also include low-cosine cases. Cosine is not probability.",
            "- Pairwise text cosine diagnoses prompt-bank overlap, not quality. Cross-axis "
            "pairs include audio/music/visual concepts because hypotheses share one encoder.",
            "- This report does not tune thresholds. Use blind labels to compare per-axis "
            "precision, recall, accepted coverage, and false-positive rates.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT
        / "benchmarks"
        / "reports"
        / "music_quality_v2"
        / "f701_real_tos_l3_final.jsonl",
    )
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT
        / "benchmarks"
        / "reports"
        / "semantic_matcher_diagnostic_20261026"
        / "semantic_matcher_diagnostic.json",
    )
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    lock = json.loads((ROOT / "models.lock.json").read_text(encoding="utf-8"))
    model = lock["models"]["embeddinggemma2"]
    provider = EmbeddingProvider(
        model,
        ROOT / "models",
        threads=args.threads,
        enabled_modalities=set(),
    )
    profiles = load_profiles(
        ROOT / "configs" / "hypotheses",
        expected_model_revision=model["revision"],
    )
    analysis, policy, window_axes = _window_diagnostics(args.input)
    hypothesis_axes, cross_axis_pairs = _profile_diagnostics(profiles, provider)
    input_sha256 = hashlib.sha256(args.input.read_bytes()).hexdigest()
    all_rows = [
        json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line
    ]
    window_rows = [row for row in all_rows if row.get("record_type") == "window_match"]
    review_readme = (
        ROOT / "benchmarks" / "reports" / "iterative_speech_presence_natural" / "README.md"
    )
    review_text = review_readme.read_text(encoding="utf-8") if review_readme.is_file() else ""
    review_pack_status = (
        "source-description-derived; not independently reviewed by listening"
        if "not been independently reviewed by listening" in review_text
        else "not joined to this report; label provenance not assessed"
    )
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "input_jsonl": str(args.input.resolve()),
        "input_sha256": input_sha256,
        "model_revision": model["revision"],
        "threads": args.threads,
        "decision_policy": policy,
        "window_match_count": len(window_rows),
        "overall_decisions": dict(Counter(row.get("decision") for row in window_rows)),
        "window_axes": window_axes,
        "hypothesis_axes": hypothesis_axes,
        "closest_cross_axis_pairs": cross_axis_pairs,
        "manual_label_context": {
            "labels_joined_to_input": False,
            "existing_40_clip_speech_pack": review_pack_status,
            "valid_for_music_prompt_tuning": False,
        },
        "scope": "Label-free diagnostic; no thresholds or model weights changed.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_markdown(report, args.report.with_suffix(".md"))
    print(
        f"window matches: {report['window_match_count']}; decisions: {report['overall_decisions']}"
    )
    print(f"json: {args.report}")
    print(f"markdown: {args.report.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
