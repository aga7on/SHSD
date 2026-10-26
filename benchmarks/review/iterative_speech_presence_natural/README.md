# Набор для слепой ручной разметки аудио

Набор содержит 40 перемешанных фрагментов по пять секунд для оси `speech_presence`. Плеер не раскрывает метки или описания источников. Откройте `player/review.html`, прослушайте каждый фрагмент, выберите разметку и сохраните CSV. Файл `review_key/answer_key.csv` открывайте только после завершения разметки: в нём ID связаны с исходными интервалами и метками.

`speech_present` — слышна человеческая речь, включая фоновый разговор; `speech_absent` — музыка, пение/хор или окружающий звук без речи; `uncertain` — надёжно определить нельзя. Фрагменты предназначены только для оценки и не являются обучающими данными. Источники, лицензии и хэши указаны в `review_key/provenance.md`.

После экспорта выполните:

```powershell
python scripts/import_audio_review_labels.py human_labels.csv benchmarks/review/iterative_speech_presence_natural/review_key/answer_key.csv --output benchmarks/review/iterative_speech_presence_natural/reviewed_labels.jsonl
python scripts/evaluate_iterative_hypotheses.py benchmarks/reports/iterative_speech_presence_natural/iterations.jsonl benchmarks/review/iterative_speech_presence_natural/reviewed_labels.jsonl --output benchmarks/review/iterative_speech_presence_natural/reviewed_evaluation.json
```
Разметки `uncertain` сохраняются в summary, но не участвуют в бинарном A/B scoring.
