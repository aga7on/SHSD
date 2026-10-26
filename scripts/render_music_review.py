"""Render a readable L1/L2/L3 review from an SHSD JSONL analysis run."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _timecode(value: int) -> str:
    seconds = value / 1000
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes):02d}:{remainder:05.2f}"


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def _latest_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if record.get("record_type") != "event" or record.get("level") not in {"L1", "L2"}:
            continue
        key = (str(record.get("event_id", "")), str(record["level"]))
        prior = events.get(key)
        if prior is None or int(record.get("revision", 0)) >= int(prior.get("revision", 0)):
            events[key] = record
    return sorted(
        events.values(),
        key=lambda item: (
            int(item.get("start_ms", 0)),
            int(item.get("end_ms", 0)),
            str(item.get("level", "")),
            str(item.get("event_id", "")),
        ),
    )


def _claim_summary(claim: dict[str, Any]) -> str:
    label = str(claim.get("label", "unknown"))
    description = claim.get("text_ru") or label
    score = claim.get("raw_cosine")
    score_text = f"; cosine={float(score):.3f}" if isinstance(score, int | float) else ""
    return (
        f"{description} [{claim.get('decision', 'unknown')}{score_text}; "
        f"{label}]"
    )


def _render_event(event: dict[str, Any]) -> str:
    claims = event.get("claims", [])
    descriptions = "<br>".join(_markdown_cell(_claim_summary(item)) for item in claims)
    if not descriptions:
        descriptions = "—"
    return "| {} | {} | {} | {} | {} | {} |".format(
        _timecode(int(event.get("start_ms", 0))),
        _timecode(int(event.get("end_ms", 0))),
        _markdown_cell(event.get("kind", "unknown")),
        _markdown_cell(event.get("state", "unknown")),
        _markdown_cell(event.get("event_id", "")[:8]),
        descriptions,
    )


def render(source: Path, destination: Path) -> None:
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    analysis = next(
        (item for item in records if item.get("record_type") == "analysis"), {}
    )
    metrics = next(
        (item for item in records if item.get("record_type") == "metrics"), {}
    )
    events = _latest_events(records)
    l2_reports = [
        item for item in records if item.get("record_type") == "l2_refinement"
    ]
    captions = [item for item in records if item.get("record_type") == "caption"]
    l2_statuses = Counter(str(item.get("status", "unknown")) for item in l2_reports)
    new_details = [detail for item in l2_reports for detail in item.get("new_details", [])]
    scheduler_pressure_attempts = int(
        metrics.get("semantic_scheduler", {}).get("pressure_rejected_count", 0)
    )
    degradation = next(
        (item for item in records if item.get("record_type") == "scheduler_degradation"),
        {},
    )
    pressure_event_ids = {
        str(item.get("event_id", ""))
        for item in degradation.get("backpressure", [])
        if item.get("event_id")
    }
    refined_event_ids = {
        str(item.get("event_id", ""))
        for item in records
        if item.get("record_type") == "event" and item.get("level") == "L2"
    }
    recovered_pressure_attempts = len(pressure_event_ids & refined_event_ids)
    unrecovered_pressure_events = len(pressure_event_ids - refined_event_ids)
    multiclass_path = source.parent / "music_multiclass_probe.json"
    detail_probe_path = source.parent / "detail_scores" / "music_dynamics_probe.json"
    multiclass_probe = (
        json.loads(multiclass_path.read_text(encoding="utf-8"))
        if multiclass_path.exists()
        else {}
    )
    detail_probe = (
        json.loads(detail_probe_path.read_text(encoding="utf-8"))
        if detail_probe_path.exists()
        else {}
    )
    multiclass_candidates = multiclass_probe.get("top_candidate_counts", {})
    detail_summary = detail_probe.get("summary", {})
    multiclass_accepted = detail_summary.get("music_presence", {}).get(
        "accepted_candidate_counts", {}
    )
    acoustic_change_count = sum(
        len(item.get("acoustic_changes", [])) for item in l2_reports
    )
    candidate_change_count = sum(
        len(item.get("candidate_changes", [])) for item in l2_reports
    )

    lines = [
        "# Реальный видео прогон: L1/L2/L3",
        "",
        f"Источник: `{analysis.get('source', source)}`.",
        f"Длительность исходного фрагмента: "
        f"{int(analysis.get('source_duration_ms', 0)) / 1000:.0f} с; "
        f"CPU, потоков: {analysis.get('threads', '—')}; окно: {analysis.get('window_ms', '—')} мс.",
        f"L3 backend: `{analysis.get('narrator_mode', 'не запрошен')}`.",
        "",
        "## Результат прогона",
        "",
        f"- Событий L1: {sum(item['level'] == 'L1' for item in events)}; "
        f"событий L2: {sum(item['level'] == 'L2' for item in events)}; "
        f"русских L3 описаний: {len(captions)}.",
        f"- L2 статусы: "
        f"{', '.join(f'{key} — {value}' for key, value in sorted(l2_statuses.items()))}.",
        f"- Новых деталей L2, принятых текущей policy: {len(new_details)}.",
        f"- L2 попыток, отложенных по нагрузке: {scheduler_pressure_attempts}; "
        f"событий с итоговой L2-ревизией после backpressure: {recovered_pressure_attempts}; "
        f"без L2-ревизии: {unrecovered_pressure_events}.",
        f"- Время анализа файла: {float(metrics.get('end_to_end_elapsed', 0)):.2f} с "
        "(это офлайн полный прогон, не realtime-измерение).",
        f"- Неподдержанные новые утверждения Qwen: "
        f"{int(metrics.get('narration_unsupported_claim_count', 0))}; "
        f"fallbacks: {int(metrics.get('narration_fallback_count', 0))}.",
        f"- L2 отдельно записал {acoustic_change_count} акустических изменений и "
        f"{candidate_change_count} принятых semantic candidate transitions.",
        "",
        "## P0: положительная многоклассовая диагностика",
        "",
    ]
    if multiclass_probe:
        accepted_total = int(multiclass_probe.get("accepted_count", 0))
        window_count = int(multiclass_probe.get("window_count", 0))
        baseline_count = int(multiclass_probe.get("baseline_binary_accepted_count", 0))
        accepted_text = ", ".join(
            f"{key}: {value}"
            for key, value in sorted(multiclass_accepted.items())
            if value
        ) or "нет принятых кандидатов"
        top_text = ", ".join(
            f"{key}: {value}" for key, value in sorted(multiclass_candidates.items())
        ) or "нет"
        lines.extend(
            [
                f"- Положительный 4-классовый probe: {accepted_total}/{window_count} "
                f"принятых решений против {baseline_count}/{window_count} у старой бинарной пары.",
                f"- Все принятые классы: {accepted_text}.",
                f"- Top-класс по окнам: {top_text}.",
            ]
        )
        scene_scores = detail_summary.get("music_presence", {})
        best_min, best_mean, best_max = scene_scores.get(
            "best_cosine_min_mean_max", [0.0, 0.0, 0.0]
        )
        margin_min, margin_mean, margin_max = scene_scores.get(
            "top_two_margin_min_mean_max", [0.0, 0.0, 0.0]
        )
        decision_policy = analysis.get("decision_policy", {})
        minimum_similarity = float(decision_policy.get("minimum_similarity", 0.6))
        minimum_margin = float(decision_policy.get("minimum_margin", 0.05))
        lines.append(
            f"- У сцены средний лучший cosine={float(best_mean):.3f} "
            f"(min/max {float(best_min):.3f}/{float(best_max):.3f}), а средний отрыв "
            f"первого кандидата от второго={float(margin_mean):.3f} "
            f"(min/max {float(margin_min):.3f}/{float(margin_max):.3f}) при policy "
            f"similarity={minimum_similarity:.2f}, margin={minimum_margin:.2f}. "
            "Высокое сходство само по себе не снимает abstain, если кандидаты близки."
        )
        transitions = [
            item
            for item in detail_probe.get("ranked_candidate_transitions", [])
            if item.get("axis_id") == "music_presence"
        ]
        if transitions:
            transition_text = "; ".join(
                f"{_timecode(int(item['time_ms']))} "
                f"{item['from_candidate']} → {item['to_candidate']}"
                for item in transitions
            )
            lines.append(
                f"- Неутверждённые top-rank переходы между окнами: {transition_text}."
            )
    else:
        lines.append("- Отчёт multiclass probe рядом с JSONL не найден.")
    if detail_summary:
        lines.extend(
            [
                "- Диагностические принятые кандидаты по независимым осям, "
                "до L2 временной проверки:",
                "",
                "| Ось | Средний лучший cosine | Margin min/mean/max | Принято / окон | "
                "Принятые кандидаты |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for axis_id, result in sorted(detail_summary.items()):
            _best_min, best_mean, _best_max = result.get(
                "best_cosine_min_mean_max", [0.0, 0.0, 0.0]
            )
            margin_min, margin_mean, margin_max = result.get(
                "top_two_margin_min_mean_max", [0.0, 0.0, 0.0]
            )
            accepted_candidates = result.get("accepted_candidate_counts", {})
            accepted_text = ", ".join(
                f"{key}: {value}"
                for key, value in sorted(accepted_candidates.items())
                if value
            ) or "нет"
            accepted_windows = int(result.get("decision_counts", {}).get("accepted", 0))
            total_windows = int(result.get("window_count", 0))
            lines.append(
                f"| `{axis_id}` | {float(best_mean):.3f} | "
                f"{float(margin_min):.3f}/{float(margin_mean):.3f}/{float(margin_max):.3f} | "
                f"{accepted_windows}/{total_windows} | {_markdown_cell(accepted_text)} |"
            )
    lines.extend(
        [
            "- Это label-free сравнение эмбеддингов, не ручная оценка точности; "
            "cosine нельзя читать как вероятность.",
            "",
            "Новая деталь L2, принятая текущей policy (без ручной проверки):",
            "",
        ]
    )
    if new_details:
        for detail in new_details:
            event_id = str(detail.get("claim_id", "")).rsplit("-", 1)[-1][:8]
            text_ru = detail.get("text_ru") or detail.get("label", "unknown")
            refs = ", ".join(detail.get("evidence_refs", []))
            lines.append(
                f"- {text_ru} (cosine={float(detail.get('raw_cosine', 0)):.3f}; "
                f"{refs}; event `{event_id}`)."
            )
    else:
        lines.append("- Нет.")

    lines.extend(
        [
            "",
            "## L1 события",
            "",
            "| Начало | Конец | Тип | Статус | ID | Русские claims (решение; cosine; label) |",
            "|---:|---:|---|---|---|---|",
        ]
    )
    lines.extend(_render_event(item) for item in events if item.get("level") == "L1")
    lines.extend(
        [
            "",
            "## L2 события",
            "",
            "| Начало | Конец | Тип | Статус | ID | Русские claims (решение; cosine; label) |",
            "|---:|---:|---|---|---|---|",
        ]
    )
    lines.extend(_render_event(item) for item in events if item.get("level") == "L2")
    lines.extend(
        [
            "",
            "## L3 описания Qwen",
            "",
            "| Интервал | Русское описание | Время генерации | Источники |",
            "|---|---|---:|---|",
        ]
    )
    for caption in captions:
        interval = caption.get("time_range", {})
        start = _timecode(int(interval.get("start_ms", 0)))
        end = _timecode(int(interval.get("end_ms", 0)))
        refs = ", ".join(
            str(item.get("event_id", ""))[:8]
            for item in caption.get("event_revisions", [])
        )
        lines.append(
            f"| {start}–{end} | {_markdown_cell(caption.get('caption_ru', ''))} | "
            f"{float(caption.get('latency_ms', 0)):.0f} мс | {refs} |"
        )

    lines.extend(
        [
            "",
            "## Ограничения оценки",
            "",
            "- В этом репозитории нет независимых ручных музыкальных меток для этих интервалов. "
            "Поэтому повышение cosine/числа подтверждений не доказывает точность и отсутствие FP.",
            "- Cosine similarity — оценка сходства текста и эмбеддинга, а не вероятность.",
            "- Qwen и L2 здесь запускались после чтения локального файла; задержки не описывают "
            "непрерывную live обработку.",
            "- Веса моделей не изменялись.",
            "",
            "## Тайминги стадий офлайн прогона",
            "",
            "Эти значения суммарные; стадии частично перекрываются и их нельзя складывать "
            "в задержку одного события.",
            "",
        ]
    )
    for name, elapsed_ms in sorted(metrics.get("stage_timings_ms", {}).items()):
        lines.append(f"- `{name}`: {float(elapsed_ms):.1f} мс.")
    lines.append("")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    render(args.source, args.destination)


if __name__ == "__main__":
    main()
