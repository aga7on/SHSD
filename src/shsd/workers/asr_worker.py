"""Bounded, optional GigaAM CPU transcription worker."""

from __future__ import annotations

import importlib.util
import json
import queue
import tempfile
import threading
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import numpy as np

from shsd.workers.scheduler import RuntimeLoadController, WorkPriority

SAMPLE_RATE = 16_000
ASR_WINDOW_MS = 20_000


@dataclass(frozen=True, slots=True)
class SpeechTask:
    """One timestamped mono audio segment queued for independent ASR."""

    start_ms: int
    end_ms: int
    samples: np.ndarray


@dataclass(frozen=True, slots=True)
class SpeechResult:
    """A completed or failed ASR segment, retaining its source interval."""

    start_ms: int
    end_ms: int
    text: str | None
    status: Literal["complete", "failed", "dropped"] = "complete"
    error: str | None = None


class Transcriber(Protocol):
    def __call__(self, samples: np.ndarray) -> str: ...


class GigaAMTranscriber:
    """Lazy local-only adapter for the pinned GigaAM-v3-e2e-CTC checkpoint."""

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self._model: object | None = None
        self._load_error: Exception | None = None

    def _load(self) -> object:
        if self._model is not None:
            return self._model
        if self._load_error is not None:
            raise RuntimeError(f"GigaAM model could not be loaded: {self._load_error}")
        try:
            from shsd.models.artifacts import verify_local_artifacts

            repo_root = Path(__file__).resolve().parents[3]
            lock_path = repo_root / "models.lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            model_lock = lock["models"]["gigaam_v3_e2e_ctc"]
            verify_local_artifacts(
                "gigaam_v3_e2e_ctc", model_lock, self.model_dir.resolve().parent
            )
            # The embedding worker may be running concurrently in this process.
            # Do not change PyTorch's process-wide thread count from the ASR lane.
            modeling_path = self.model_dir / "modeling_gigaam.py"
            config_path = self.model_dir / "config.json"
            if not modeling_path.is_file() or not config_path.is_file():
                raise FileNotFoundError("pinned GigaAM model code or config is missing")
            spec = importlib.util.spec_from_file_location(
                "shsd_gigaam_local_modeling", modeling_path
            )
            if spec is None or spec.loader is None:
                raise ImportError("could not load the local GigaAM model module")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            model_config = module.GigaAMConfig.from_pretrained(
                str(self.model_dir), local_files_only=True
            )
            import transformers

            load_kwargs: dict[str, object] = {}
            if int(transformers.__version__.split(".", maxsplit=1)[0]) >= 5:
                # Transformers 5 constructs custom PreTrainedModels on the meta
                # device. GigaAM's torchaudio MelSpectrogram builds CPU tensors
                # during __init__, so create its module tree explicitly on CPU.
                # GigaAM has no tied parameters; Transformers 5 now expects the
                # corresponding key map to exist during load finalization.
                original_init = module.GigaAMModel.__init__

                def initialize_on_cpu(instance: object, config: object) -> None:
                    with module.torch.device("cpu"):
                        original_init(instance, config)

                module.GigaAMModel.__init__ = initialize_on_cpu
                module.GigaAMModel.all_tied_weights_keys = {}
                load_kwargs["low_cpu_mem_usage"] = False
            model = module.GigaAMModel.from_pretrained(
                str(self.model_dir),
                config=model_config,
                local_files_only=True,
                **load_kwargs,
            )
            model.to("cpu")
            model.eval()
            self._model = model
        except Exception as error:
            self._load_error = error
            raise RuntimeError(f"GigaAM model could not be loaded: {error}") from error
        return self._model

    def __call__(self, samples: np.ndarray) -> str:
        """Transcribe a <=20s float32 window through the upstream short-form API."""
        if samples.ndim != 1 or samples.size == 0:
            raise ValueError("GigaAM expects a non-empty mono waveform")
        if samples.size > ASR_WINDOW_MS * SAMPLE_RATE // 1000:
            raise ValueError("GigaAM input exceeds the configured 20-second window")
        pcm = np.clip(samples, -1.0, 1.0)
        pcm16 = np.rint(pcm * 32767.0).astype("<i2", copy=False)
        model = self._load()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            path = Path(audio_file.name)
        try:
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(pcm16.tobytes())
            transcript = cast(Any, model).transcribe(str(path))
            if not isinstance(transcript, str):
                raise TypeError("GigaAM transcribe() returned a non-text result")
            return transcript.strip()
        finally:
            path.unlink(missing_ok=True)


class SpeechWindowAssembler:
    """Combine analysis windows into bounded, timestamped ASR windows."""

    def __init__(self, *, window_ms: int = ASR_WINDOW_MS) -> None:
        if window_ms < 250 or window_ms > ASR_WINDOW_MS:
            raise ValueError("ASR window must be between 250ms and 20s")
        self.target_samples = max(1, round(window_ms * SAMPLE_RATE / 1000))
        self._start_ms: int | None = None
        self._parts: list[np.ndarray] = []
        self._samples = 0
        self._cursor_ms: int | None = None

    def _take(self) -> SpeechTask | None:
        if self._samples == 0 or self._start_ms is None:
            return None
        values = np.concatenate(self._parts).astype(np.float32, copy=False)
        end_ms = max(self._start_ms + 1, self._start_ms + round(values.size * 1000 / SAMPLE_RATE))
        task = SpeechTask(self._start_ms, end_ms, values)
        self._parts = []
        self._samples = 0
        self._start_ms = None
        return task

    def push(self, start_ms: int, samples: np.ndarray) -> list[SpeechTask]:
        if start_ms < 0 or samples.ndim != 1:
            raise ValueError("audio window must have a non-negative start and mono samples")
        emitted: list[SpeechTask] = []
        if self._cursor_ms is not None and abs(start_ms - self._cursor_ms) > 2:
            previous = self._take()
            if previous is not None:
                emitted.append(previous)
            self._cursor_ms = start_ms
        offset = 0
        while offset < samples.size:
            if self._start_ms is None:
                self._start_ms = start_ms + round(offset * 1000 / SAMPLE_RATE)
            take = min(self.target_samples - self._samples, samples.size - offset)
            self._parts.append(samples[offset : offset + take])
            self._samples += take
            offset += take
            self._cursor_ms = start_ms + round(offset * 1000 / SAMPLE_RATE)
            if self._samples == self.target_samples:
                task = self._take()
                if task is not None:
                    emitted.append(task)
        return emitted

    def flush(self) -> SpeechTask | None:
        """Return the trailing short segment, if present."""
        task = self._take()
        self._cursor_ms = None
        return task


class BoundedSpeechWorker:
    """Run ASR on a daemon worker with bounded input and result queues."""

    def __init__(
        self,
        transcriber: Transcriber,
        *,
        queue_capacity: int = 2,
        result_capacity: int = 8,
        load_controller: RuntimeLoadController | None = None,
    ) -> None:
        if queue_capacity < 1 or result_capacity < 1:
            raise ValueError("ASR queue capacities must be positive")
        self._transcriber = transcriber
        self._load_controller = load_controller
        self.queue_capacity = queue_capacity
        self.result_capacity = result_capacity
        self._tasks: queue.Queue[SpeechTask | None] = queue.Queue(maxsize=queue_capacity)
        self._results: queue.Queue[SpeechResult] = queue.Queue(maxsize=result_capacity)
        self._thread = threading.Thread(target=self._run, name="shsd-asr", daemon=True)
        self._closed = False
        self.outstanding = 0
        self.max_outstanding = 0
        self.submitted_count = 0
        self.last_submit_reason: str | None = None
        self._thread.start()

    @property
    def admission_capacity(self) -> int:
        """Bounded tasks, results, and the one active transcriber call."""
        return self.queue_capacity + self.result_capacity + 1

    def submit(self, task: SpeechTask) -> bool:
        """Queue one segment without waiting; false means explicit ASR backpressure."""
        self.last_submit_reason = None
        if self._closed:
            self.last_submit_reason = "asr_worker_closed"
            return False
        if self._load_controller is not None:
            decision = self._load_controller.admit(WorkPriority.L2_ASR)
            if not decision.admitted:
                self.last_submit_reason = decision.reason or "load_pressure"
                return False
        try:
            self._tasks.put_nowait(task)
        except queue.Full:
            self.last_submit_reason = "asr_queue_full"
            return False
        self.outstanding += 1
        self.submitted_count += 1
        self.max_outstanding = max(self.max_outstanding, self.outstanding)
        return True

    def drain(self, callback: Callable[[SpeechResult], None]) -> int:
        count = 0
        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                break
            self.outstanding -= 1
            callback(result)
            count += 1
        return count

    def finish(self, callback: Callable[[SpeechResult], None]) -> None:
        """Wait for queued jobs while draining bounded results on the caller thread."""
        if self._closed:
            return
        self._closed = True
        while True:
            try:
                self._tasks.put_nowait(None)
                break
            except queue.Full:
                self.drain(callback)
                self._thread.join(timeout=0.02)
        while self._thread.is_alive():
            self.drain(callback)
            self._thread.join(timeout=0.02)
        self.drain(callback)

    def snapshot(self) -> dict[str, int | str | None]:
        """Expose bounded ASR pressure to the common runtime scheduler."""
        return {
            "queue_capacity": self.queue_capacity,
            "result_capacity": self.result_capacity,
            "admission_capacity": self.admission_capacity,
            "queue_depth": self._tasks.qsize(),
            "result_depth": self._results.qsize(),
            "outstanding": self.outstanding,
            "max_outstanding": self.max_outstanding,
            "submitted": self.submitted_count,
            "last_submit_reason": self.last_submit_reason,
        }

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is None:
                self._tasks.task_done()
                return
            try:
                text = self._transcriber(task.samples)
                result = SpeechResult(task.start_ms, task.end_ms, text)
            except Exception as error:
                result = SpeechResult(
                    task.start_ms,
                    task.end_ms,
                    None,
                    "failed",
                    f"{type(error).__name__}: {error}"[:500],
                )
            self._results.put(result)
            self._tasks.task_done()
