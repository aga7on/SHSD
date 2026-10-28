# Аудит репозитория SHSD — 28.10.2026

> **Объект аудита:** `aga7on/SHSD` @ `30a6209bbed59bdad5abfa12f467946d9803578e` (`main`), сверено с GitHub API: `main` совпадает с указанным коммитом.
> **Статус:** аудит завершён; блокер P0 воспроизведён, исправлен и покрыт регрессионным тестом.
> **Область:** сборка/импорт пакета, тесты, линтеры и типы, упаковка и зависимости, API/UI, безопасность локального сервиса, воспроизводимость benchmark-evidence, документация, гигиена репозитория.
> **Вне области (не проверялось):** реальный вывод моделей (EmbeddingGemma 2 / Qwen3-0.6B / GigaAM), GPU-путь, живой RTSP, воспроизведение фикстур через `ffmpeg`, поведение на Windows, torch-зависимые тесты, прогон CI на GitHub.

## 1. Окружение и методика

| Параметр | Значение |
| --- | --- |
| ОС / CPU / RAM | Linux x86_64, 2 vCPU, 3 GiB |
| Python | 3.11.2 (максимум, что есть в песочнице) |
| Установлено | `pip install -e . --no-deps` + `av==18.1.0`, numpy, PyYAML, pytest, ruff, mypy, fastapi, httpx, psutil, requests |
| Не установлено (optional extras) | `torch`, `transformers`, `sentence-transformers`, `PIL`, `uvicorn`, `ffmpeg` |
| Модели | отсутствуют (`models/` не скачивался) — намеренно: аудит статический + unit-уровень |

Команды проверки и их результаты (все выполнены локально):

```text
python -m pytest -q                 -> 277 passed, 1 skipped   (после исправления; до него — 15 ошибок сбора)
ruff check .                        -> All checks passed!      (после исправления; до него — 2 ошибки I001)
mypy                                -> 27 errors in 10 files   (было 43)
shsd --version                      -> shsd 0.1.0
shsd replay tests/fixtures/media/av_sync_20s.mp4 --fast
                                    -> 1139 пакетов, C=20000 ms, 0 дропов
shsd analyze ... --cpu-only --offline
                                    -> exit 2 + «model unavailable: ... download_models.py --model embeddinggemma2»
python -c "import shsd.embeddings"  -> ModuleNotFoundError: shsd.models  (до исправления)
```

## 2. Сводка находок

| ID | Серьёзность | Проблема | Состояние |
| --- | --- | --- | --- |
| A-01 | **P0 (блокер)** | Пакет `src/shsd/models/` отсутствует в Git → пакет не импортируется, 15 тестовых модулей не собираются | **исправлено** |
| A-02 | **P0** | Метаданные пакета несовместимы: `av>=19.0.1` требует Python ≥3.12 при `requires-python = ">=3.11"` | открыто (нужно решение владельца) |
| A-03 | P1 | Qwen-нарратор жёстко привязан к Windows (`llama-cli.exe`), а `models.lock.json` содержит только win-cpu-x64 рантайм — при заявленной поддержке Linux | открыто |
| A-04 | P1 | `mypy --strict` красный (27 ошибок), CI отсутствовал | частично исправлено (43→27), CI добавлен |
| A-05 | P1 | 209 битых ссылок на «сырые» артефакты: `benchmarks/reports/**/*.jsonl|*.wav|*.npy` игнорируются, но на них ссылаются отчёты → evidence не воспроизводим | открыто |
| A-06 | P1 | Локальный API без аутентификации: чтение любых локальных файлов + SSRF по произвольному URL; при `--host 0.0.0.0` это сетевой риск | открыто |
| A-07 | P1 | `POST /v1/streams/{id}/refine` возвращает `Location` на несуществующий GET-эндпоинт | открыто |
| A-08 | P2 | Утечка подписки WebSocket: цикл висит на `queue.get()`, отключение клиента не детектируется | открыто |
| A-09 | P2 | В корне нет `LICENSE` | открыто |
| A-10 | P2 | Гигиена Git: `src/shsd.egg-info/` был закоммичен; 48 МБ бинарников, из них 32 МБ недокументированная фикстура; 6 `.jsonl` закоммичены вопреки собственному `.gitignore` | частично исправлено (egg-info снят) |
| A-11 | P2 | Долг структуры: `analyze.py` 3348 строк, `analyze_media` — 2202 строки, 38 функций ≥120 строк | открыто |
| A-12 | P3 | 38 `except Exception`, часть с молчаливым `pass`/`continue`; нет `py.typed` при strict-конфиге; скрипты (10 165 строк) почти не покрыты тестами (4 модуля из 41) | открыто |

## 3. Блокер A-01: пакет `shsd.models` отсутствует в репозитории

### Симптом

```text
$ python -c "import shsd.embeddings"
ModuleNotFoundError: No module named 'shsd.models'

$ python -m pytest
ERROR tests/unit/test_analyze.py
ERROR tests/unit/test_api.py
... 15 модулей не собираются
```

`src/shsd/embeddings/provider.py:21`, `captions/narrator.py:17`, `captions/hypothesis_proposer.py:14`,
`workers/asr_worker.py:62`, `cli.py:214`, три скрипта и `tests/unit/test_model_artifacts.py:8`
импортируют `shsd.models.artifacts`, которого в дереве нет. Через `embeddings/__init__` это ломает
импорт `shsd.sampling`, `shsd.analyze`, `shsd.api.app` и почти всего набора тестов.

### Причина

`.gitignore:8` содержал паттерн `models/` без ведущего слэша. Паттерн матчит каталог `models`
на любой глубине, включая `src/shsd/models/`, поэтому исходный пакет никогда не попадал в коммит:

```text
$ git check-ignore -v src/shsd/models/artifacts.py
.gitignore:8:models/	src/shsd/models/artifacts.py
```

Проверено, что дефект опубликован, а не является артефактом песочницы: в upstream на `main`
(`30a6209`) в каталоге `src/shsd` каталога `models` тоже нет (GitHub Contents API).

### Исправление

1. `.gitignore`: `models/` → `/models/` с комментарием, что игнорируется только каталог
   загрузки весов в корне.
2. Восстановлен `src/shsd/models/` (`__init__.py`, `artifacts.py`) по контракту, заданному
   `tests/unit/test_model_artifacts.py` и восемью точками вызова: `MissingModelFiles`,
   `verify_local_artifacts(name, model, models_dir) -> dict[path, sha256]`, проверка размера и
   SHA-256 против `models.lock.json`, кэш хэшей по `(path, size, mtime_ns)`, сообщение об ошибке
   с точной командой `python scripts/download_models.py --model <id>` (или `--runtime llama_cpp`).
   Сеть не используется — runtime остаётся offline.
3. Добавлен регрессионный тест `tests/unit/test_package_imports.py`: обходит `pkgutil.walk_packages`
   и импортирует все модули пакета, отдельно требуя наличие `shsd.models.artifacts`.
   Негативный контроль выполнен: при временно убранном каталоге тест падает с явным сообщением,
   при возвращённом — проходит.

### Проверка после исправления

```text
pytest      -> 277 passed, 1 skipped
ruff        -> All checks passed!
shsd replay -> 1139 packets, C=20000 ms, drops=0
shsd analyze -> exit 2, «model unavailable: ... Fetch them explicitly with:
                python scripts/download_models.py --model embeddinggemma2»
```

Количество тестов совпадает с заявленным в `Todo.md` (F10.02): 276 + 3 torch-зависимых = 279,
что подтверждает корректность восстановленного контракта.

## 4. Остальные находки

### A-02 (P0): упаковка не устанавливается на заявленном Python

```text
$ pip install -e '.[dev]'
ERROR: Ignored the following versions that require a different python version:
  19.0.0 Requires-Python >=3.12; 19.0.1 ...; 19.0.2 ...
ERROR: Could not find a version that satisfies the requirement av<20,>=19.0.1
```

`pyproject.toml` объявляет `requires-python = ">=3.11"` (README: «Python 3.11 or newer»), но пин
`av>=19.0.1,<20` доступен только с 3.12. Инструкция из README на 3.11 невыполнима.
Нужно решение владельца: поднять `requires-python` до `>=3.12` (и обновить README/CI) либо
разрешить `av>=18,<20` и проверить тесты на 18.x (в этом аудите тесты на 18.1.0 зелёные).
Пока не исправлено, CI зафиксирован на 3.12.

### A-03 (P1): Windows-only путь Qwen, при заявленном Linux-таргете

`llama-cli.exe` захардкожен в `captions/narrator.py:821`, `captions/hypothesis_proposer.py:48`,
`scripts/smoke_models.py:192`, `scripts/benchmark_cpu.py:176`. В `models.lock.json` рантайм
`llama_cpp` описан единственным ассетом `llama-b11886-bin-win-cpu-x64.zip`. README при этом
объявляет целевыми платформами Windows x86_64 **и** Linux x86_64. Итог: L3-наррация и
hypothesis-предложения на Linux недостижимы, хотя остальной pipeline работает.
Рекомендация: выбор бинарника по `os.name`/`sys.platform` и отдельная запись рантайма в lock-файле.

### A-04 (P1): качество типов и отсутствие CI

`[tool.mypy] strict = true`, но проверка не была зелёной никогда (43 ошибки до вмешательства).
Разбор после исправлений (27 ошибок / 10 файлов):

| Файл | Ошибок | Характер |
| --- | --- | --- |
| `captions/narrator.py` | 19 | `object` из `dict[str, object]` передаётся в `sorted`/`list` без сужения |
| `bridge/dataset.py` | 9 | `start_ms`/`end_ms` теряют сужение через отдельный флаг `interval_valid` (стр. 176, 275, 335); `errors` переопределяется в одной функции (стр. 555) |
| `analyze.py` | 5 | `no-any-return` (стр. 391, 2255), отсутствующие стабы `psutil` |
| `embeddings/provider.py` | 4 | опциональные `torch`/`PIL`/`sentence_transformers`/`threadpoolctl` |
| `ingest/decoder.py`, `ingest/pipeline.py`, `analyze.py` | 4 | нет `types-psutil` в dev-extra |
| `workers/asr_worker.py`, `cli.py` | 3 | `transformers`, `uvicorn` не установлены |
| `memory/graph.py`, `api/exports.py` | 2 | `no-redef` (исправлено), лишний `len()` на `Any \| None` |

Сделано в этом аудите: `_integer` и `_has_text` в `bridge/dataset.py` стали `TypeGuard`
(43 → 27 ошибок), устранено затенение переменной `claims` в `memory/graph.py:491`.
Добавлен `.github/workflows/ci.yml` (ruff + pytest на 3.12 блокирующие, `mypy` — advisory
до закрытия остатка). Остаток закрывается сужением типов в `narrator.py` и
`[[tool.mypy.overrides]]` для опциональных зависимостей.

### A-05 (P1): evidence не воспроизводим

`benchmarks/reports/` — 80 записей, 48 МБ. При этом `.gitignore` исключает
`benchmarks/reports/**/*.jsonl`, `*.wav`, `*.npy`, а отчёты на эти файлы ссылаются.
Итог: **209 битых относительных ссылок**, из них 174 в `docs/archive`, 31 в `benchmarks`,
4 в активной документации (2 в `Todo.md`, 2 в `docs/adr/ADR-002`). Четыре активные ссылки
исправлены; остальные требуют решения: либо положить ключевые сырые артефакты в репозиторий
(выборочно, с проверкой размера), либо явно помечать в отчётах, что артефакт не публикуется.
Отдельная несогласованность: 6 `.jsonl` закоммичены вопреки собственному правилу
(`git ls-files -ci --exclude-standard`), то есть политика соблюдается непоследовательно.

### A-06 (P1): поверхность атаки локального API

`POST /v1/streams` принимает `source` произвольной длины (до 4096 символов): любой абсолютный
локальный путь (`Path(...).resolve()`, проверяется только `is_file()`) либо любой
`http/https/rtsp/rtsps` URL без allowlist хостов. Аутентификации нет. При дефолтном
`--host 127.0.0.1` риск ограничен локальными процессами, но `serve --host` принимает любое
значение, и тогда это чтение произвольных файлов + SSRF (включая внутренние адреса и
cloud-metadata) и запуск анализа на CPU без квоты по числу стримов.
Рекомендация: allowlist корней медиа (`--media-root`), запрет link-local/loopback/metadata
адресов, предупреждение при не-loopback bind, ограничение числа одновременных стримов.

### A-07/A-08 (P1/P2): дефекты API-контракта

* `POST /v1/streams/{id}/refine` отдаёт заголовок `Location: /v1/streams/{id}/refine/{job_id}`,
  но GET-маршрута для job нет (проверено перечислением `app.routes`). Клиент по контракту
  получает 404.
* WebSocket-цикл `while True: await websocket.send_json(await queue.get())` не имеет
  `receive()`/heartbeat: при отключении клиента и отсутствии новых событий корутина висит,
  подписка и очередь не освобождаются до следующего события. Для завершившегося стрима — утечка.
* `app = create_app()` выполняется на импорте модуля (побочные эффекты: чтение
  `models.lock.json`, создание `StreamManager`).
* `app.router.add_event_handler("shutdown", ...)` — устаревший API; нужен `lifespan`.

### A-09…A-12 (P2/P3)

* **Лицензия.** В корне нет `LICENSE`; при этом в `models.lock.json` фиксируются лицензии
  моделей, а в `benchmarks/fixtures/real_poc/README.md` — CC-BY атрибуция. Статус самого кода
  и прав на переиспользование не определён.
* **Бинарники в Git.** `benchmarks/fixtures/real_poc/tears_of_steel_120_210s.mp4` — 32 МБ,
  не описан в README фикстуры (там только 20-секундный клип с SHA-256 и атрибуцией), хэш и
  лицензионная ссылка для него не зафиксированы. Итого ~48 МБ медиа в истории.
* **Мёртвые артефакты.** `src/shsd.egg-info/` (6 файлов) был закоммичен — снят из индекса,
  `*.egg-info/` добавлен в `.gitignore`.
* **Структурный долг.** `analyze.py` 3348 строк, `analyze_media` 2202 строки; 38 функций ≥120 строк.
  `api/manager.py` импортирует приватные `_narration_batches` из `analyze`. Разбиение на стадии
  (ingest → detect → embed → match → temporal → narrate → persist) заметно упростило бы тесты.
* **Обработка ошибок.** 38 `except Exception` в `src/`; минимум одно место молча пропускает
  исключение в ingest-цикле (`analyze.py:212`), плюс `S110`/`S112` от bandit-правил ruff.
* **Покрытие.** Из 41 скрипта тестами покрыты 4; скрипты — это то, чем получены все benchmark-числа.
* **Прочее.** Нет `py.typed` при `strict`-конфиге mypy; нет lock-файла dev-зависимостей;
  в `Todo.md` остаются открытые P0 (F7.03, F7.04, F10.02 visual grounding) — это подтверждается
  самими отчётами и не является скрытым долгом.

## 5. Что в репозитории сделано хорошо (проверено)

* `ruff check .` — чисто; правило-набор `B,E,F,I,UP` покрывает bugbear.
* Разделение `E`/`C`/`D`/`R` watermarks, bounded ring 600 s, явные `skipped`/`unavailable` —
  в `shsd replay` подтверждено: 1139 пакетов, `C=20000 ms`, 0 дропов.
* Pydantic-модели API с `extra="forbid"` и диапазонами — вход валидируется строго.
* Веб-UI (`app.js`) строит DOM через `textContent`/`createElement`, `innerHTML` не используется —
  XSS-вектор через ASR/подписи закрыт.
* `scripts/download_models.py`: потоковая проверка SHA-256, докачка по `Range`, отказ при
  расхождении и защита от path traversal в zip рантайма.
* Секретов в дереве не найдено (grep по типовым ключам/паролям); `.gitignore` покрывает
  `.env`, ключи и сертификаты.
* `--no-shell` запуск внешних бинарников: `subprocess.run` со списком аргументов, без `shell=True`.
* Документация фиксирует отрицательные результаты и явно отделяет `hypothesis` от
  `smoke-test verified` — это соответствует заявленным правилам `Agents.md`.

## 6. Рекомендуемый порядок работ

1. **A-02** — выровнять `requires-python` и пин `av` (решение владельца), затем зафиксировать
   поддерживаемый Python в README и CI.
2. **A-03** — платформенно-независимый выбор llama.cpp бинарника и второй ассет в `models.lock.json`.
3. **A-05** — политика публикации evidence: какие `.jsonl`/`.json` попадают в репозиторий,
   какие — нет; починить 31 ссылку в `benchmarks/reports` или пометить артефакты как внешние.
4. **A-06/A-07/A-08** — allowlist медиа-корней и адресов, GET-эндпоинт refine-задачи,
   `receive()`-цикл и `lifespan` в WebSocket/старте приложения.
5. **A-04** — закрыть остаток mypy (сужение типов в `narrator.py`, overrides для optional deps,
   `types-psutil`) и сделать шаг блокирующим.
6. **A-09…A-12** — LICENSE, вынос крупных бинарников, декомпозиция `analyze.py`, тесты для
   benchmark-скриптов.

## 7. Изменения в этом аудите

```text
.gitignore                                   models/ -> /models/, + *.egg-info/
.github/workflows/ci.yml                     новый: ruff + pytest (3.12), mypy advisory
src/shsd/models/__init__.py                  новый: восстановленный пакет
src/shsd/models/artifacts.py                 новый: MissingModelFiles, verify_local_artifacts
tests/unit/test_package_imports.py           новый: регрессионный контроль импортов
tests/unit/test_embedding_provider_sequence.py  torch через pytest.importorskip (dev-install без torch)
src/shsd/bridge/dataset.py                   _integer/_has_text -> TypeGuard
src/shsd/memory/graph.py                     устранено затенение переменной claims
Todo.md                                      исправлены 2 битые ссылки на review
docs/adr/ADR-002-multimodal-bridge-evaluation.md  исправлены 2 относительные ссылки
src/shsd.egg-info/*                          снят из индекса Git
```

Итоговое состояние: `pytest` — 277 passed, 1 skipped; `ruff` — clean; `mypy` — 27 (было 43);
`shsd --version`, `shsd replay`, `shsd analyze` (с корректной ошибкой об отсутствии моделей) работают.
