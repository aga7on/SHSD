# Live-проверка Qwen v2 на CPU

## Метод

- 90-секундный A/V-фрагмент *Tears of Steel* подавался по loopback RTSP в течение 60 секунд со скоростью 1x (`ffmpeg -re`). SHSD: CPU, 4 threads, 5-second windows, standard A/V profiles, L0/L1/L2/L3, Qwen requested. ASR off.
- За live-результат здесь считается только вывод, который API увидел до остановки publisher; время drain после stop считается отдельно.

## Прогресс до stop

| Метрика | Значение |
|---|---:|
| Публикация | 60.000 s |
| Последний pre-stop снепшот | 59.656 s |
| Capture C | 41.828 s / 60 s (около 69.7%) |
| Embedding E | 35.120 s |
| Reducer R[L1] / R[L2] / R[L3] | 35.120 / 25.120 / 29.745 s |
| L1 / L2 revisions seen live | 28 / 12 |
| L1 output lag p50 / p95 | 22.27 / 31.89 s |
| L2 output lag p50 / p95 | 17.73 / 17.75 s |
| Live L3 captions / first-observed lag | 1 / 20.839 s |
| Qwen generation / fallback | 1 / 0 |
| Qwen generation latency | 2300.9 ms |
| Peak process-tree RSS | 3.16 GiB |
| Shared prefetch drops / ingest drops | 503 / 0 |

## Что было выведено

- 26.543 s после старта потока API впервые показало L3 caption для 00:04.704–00:05.704: **Обнаружено заметное изменение изображения.**
- Это реальный русский выход, но общая фраза: она не описывает музыку или диалог.
- После stop система дошла до terminal status за 3.254 s; post-stop captions: 0.
- Всего зафиксировано media-ingest packet drops: 0; shared-prefetch drops: 503. Embedding cache hits: audio 0, image 0, so this run is not a warm-cache result.

## Вывод

Qwen v2 реально стримит выход во время подачи, но SHSD не дошла до realtime: за 60 секунд подачи захват дошёл только до 41.8 секунды, L1/L2 отставали на 17.7–22.3 секунды по p50, а shared-prefetch зафиксировал 503 drops. L3 выдал одну общую caption с ~20.8-секундной задержкой. Post-stop drain 3.25 секунды короче и чистое медиаформулирование отделено от live latency. По одному cold-cache прогону нельзя приписать изменения целиком на narrator-дедупликацию; прошлый paired benchmark в `live_qwen_online_60s_20261026.md` остаёт контролем.

## Артефакты

- Raw summary: [`report.json`](report.json).
- Events first observed before stop and final export: [`events_live.json`](events_live.json).
- L3 captions: [`captions_live.json`](captions_live.json).
- Live benchmark runner: [`benchmark_live_qwen.py`](../../../scripts/benchmark_live_qwen.py).
- Full offline real-source events and scores: [`report.md`](../qwen_l3_dedup_20261026/report.md).
