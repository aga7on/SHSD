from __future__ import annotations

from shsd.detectors.types import SignalObservation
from shsd.semantic.relations import CrossModalRelationValidator


def _observation(
    start_ms: int,
    end_ms: int,
    subtype: str,
    value: float | bool,
    method: str,
) -> SignalObservation:
    return SignalObservation(
        start_ms=start_ms,
        end_ms=end_ms,
        subtype=subtype,
        quality=0.9,
        method_version=method,
        value=value,
        unit="boolean" if isinstance(value, bool) else "normalized_flux",
    )


def test_scene_cut_and_audio_onset_pair_with_both_evidence_and_no_causality() -> None:
    validator = CrossModalRelationValidator(tolerance_ms=250)
    validator.add_audio(_observation(900, 920, "onset", 0.8, "audio-v1"))
    validator.add_video(_observation(800, 1_000, "scene_cut", True, "video-v1"))

    result = validator.assess(available_modalities={"audio", "video"})

    assert result.status == "assessed"
    assert len(result.matches) == 1
    relation = result.matches[0].to_dict()
    assert relation["delta_ms"] == 90
    assert len(relation["evidence_refs"]) == 2  # type: ignore[arg-type]
    assert relation["causality_claimed"] is False


def test_intentionally_shifted_audio_onset_is_not_called_synchronous() -> None:
    validator = CrossModalRelationValidator(tolerance_ms=250)
    validator.add_audio(_observation(0, 20, "onset", 0.9, "audio-v1"))
    validator.add_video(_observation(800, 1_000, "scene_cut", True, "video-v1"))

    result = validator.assess(available_modalities={"audio", "video"})

    assert result.status == "assessed"
    assert result.matches == ()
    assert result.unmatched_scene_cut_count == 1
    assert result.unmatched_audio_onset_count == 1


def test_missing_modality_is_unavailable_and_signal_memory_is_bounded() -> None:
    unavailable = CrossModalRelationValidator()
    result = unavailable.assess(available_modalities={"video"})
    assert result.status == "unavailable"
    assert result.unavailable_modalities == ("audio",)

    bounded = CrossModalRelationValidator(max_observations=2, bucket_ms=100)
    for timestamp in (0, 100, 200):
        bounded.add_audio(
            _observation(timestamp, timestamp + 10, "onset", 0.8, "audio-v1")
        )
    assessment = bounded.assess(available_modalities={"audio", "video"})
    assert assessment.status == "truncated"
    assert assessment.audio_onset_count == 2
    assert assessment.dropped_audio_count == 1
