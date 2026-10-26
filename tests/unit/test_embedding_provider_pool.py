from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

from shsd.embeddings import provider as provider_module
from shsd.embeddings.provider import EmbeddingProviderPool


def test_provider_pool_reuses_matching_profile_after_concurrent_first_access(
    monkeypatch: Any, tmp_path: Any
) -> None:
    constructions: list[object] = []

    class FakeProvider:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            constructions.append(self)

    monkeypatch.setattr(provider_module, "EmbeddingProvider", FakeProvider)
    pool = EmbeddingProviderPool()
    barrier = Barrier(5)
    model = {"revision": "test-revision", "artifact": "frozen"}

    def acquire() -> object:
        barrier.wait(timeout=2)
        return pool.get_or_create(
            model,
            tmp_path,
            cache_dir=tmp_path / "cache",
            threads=1,
            enabled_modalities={"audio", "video"},
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        providers = list(executor.map(lambda _index: acquire(), range(5)))

    assert all(provider is providers[0] for provider in providers)
    assert len(constructions) == 1

    other_profile = pool.get_or_create(
        model,
        tmp_path,
        cache_dir=tmp_path / "cache",
        threads=2,
        enabled_modalities={"audio", "video"},
    )
    assert other_profile is not providers[0]
    assert len(constructions) == 2

    other_concurrency = pool.get_or_create(
        model,
        tmp_path,
        cache_dir=tmp_path / "cache",
        threads=1,
        inference_concurrency=2,
        enabled_modalities={"audio", "video"},
    )
    assert other_concurrency is not providers[0]
    assert len(constructions) == 3
