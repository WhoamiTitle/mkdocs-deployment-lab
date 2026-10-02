# Материалы подтверждения

В этот каталог добавляются фактические результаты выполнения задания:

- `screenshots/` — успешные и проваленные запуски, preview и rollback;
- `logs/` — очищенные от секретов фрагменты журналов;
- `measurements/` — измерения времени и размера сайта.

Числовые результаты заносятся только после реального измерения.

Файл `logs/helios-resilience.json` содержит машиночитаемый результат реальных
sandbox-проверок Helios без закрытого ключа и содержимого `known_hosts`.
`logs/helios-resilience-actions.json` фиксирует повтор тех же сценариев из
GitHub Actions, `logs/preview-cleanup.json` — ручную и автоматическую очистку
настоящей preview-ветки, а `logs/t4-actions-runs.json` — исходные квитанции
трёх парных запусков T4 и результат проверки журналов на секреты.
`logs/ci-run-evidence.json` содержит API-поля успешной публикации и намеренно
проваленного CI, а `screenshots/` — четыре проверенных изображения для отчёта.

## Правила хранения измерений

- одна строка CSV соответствует одному наблюдению;
- время хранится в UTC ISO 8601, длительность — в секундах;
- `commit_sha` связывает результат с исходным кодом;
- `measurement_scope` не позволяет смешать локальный
  `deploy-command-to-healthcheck`, удалённый `push-start-to-healthcheck` и
  `workflow-dispatch-to-healthcheck`;
- пустое поле означает, что величина не измерялась; оно не заменяется нулём;
- исходные строки не округляются для отчёта и не удаляются из-за выбросов;
- повтор одного commit SHA различается по `release_id` и `release_built_at_utc`;
- JSON-квитанции Actions сохраняют исходные build, `rsync` и healthcheck
  показатели до переноса в CSV.

`measurements/ci-build-times.csv` хранит длительности удалённых strict-сборок,
а `measurements/helios-transfers.csv` — статистику `rsync` и встроенного
healthcheck. Интервал от запуска workflow до внешней доступности находится в
`measurements/deployment-times.csv`.

Локальная серия запускается командой:

```bash
RUNS=5 RUN_START=1 make benchmark-local
```

Методика удалённого наблюдения и команда для GitHub Pages приведены на странице
`docs/experiment/index.md`. Перед публикацией журнал проверяется на отсутствие
секретов и персональных данных.
