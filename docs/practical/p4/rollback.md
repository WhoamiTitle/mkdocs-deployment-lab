# Откат

Для выбора старой версии без удаления новых используйте Select latest version.
Roll back GitHub Pages возвращает предыдущий стабильный снимок с нынешними
preview. На Helios Roll back Helios переключает полный набор версий одной
цели. Подробности хранения описаны в [структуре каталогов P5](../p5/layout.md).

Production использует две ссылки:

- `current` — активный релиз;
- `previous` — релиз, который был активен до последнего переключения.

При публикации новый каталог сначала полностью загружается и проверяется. Затем
`previous` получает прежнее значение `current`, публичная ссылка проверяется и
направляется на `current`, а последней операцией `current` атомарно
переключается на новый каталог. При ошибке до этой операции исходные ссылки
восстанавливаются, поэтому рабочая версия не меняется.

При ошибке healthcheck workflow вызывает rollback. Значения `current` и
`previous` меняются местами, после чего повторный HTTP healthcheck ищет метку
конкретного восстановленного release ID. Production deploy и ручной rollback
используют одну concurrency group и не изменяют ссылки одновременно.

Если процесс остановлен во время загрузки staging-каталога, `current` ещё не
изменён и пользователи продолжают получать предыдущий релиз.

## Изолированная проверка

Сценарии с намеренной ошибкой запускаются только по адресу
`mkdocs-deployment-lab-sandbox`. Скрипт проверяет фиксированные sandbox-пути до
SSH-подключения и удаляет их только при двойном разрешении через аргумент
`--cleanup` и переменную `ALLOW_DESTRUCTIVE_TEST_CLEANUP=1`:

```bash
export HELIOS_HOST=helios.cs.ifmo.ru
export HELIOS_USER=s507353
export HELIOS_PORT=2222
export HELIOS_SSH_KEY_PATH="$HOME/.ssh/mkdocs-deployment-lab-helios"
export HELIOS_KNOWN_HOSTS_PATH="$PWD/.secrets/known_hosts"
ALLOW_DESTRUCTIVE_TEST_CLEANUP=1 make test-helios-sandbox
```

Проверяются ручной и автоматический rollback, повтор существующего release ID,
частичная загрузка без переключения, невалидный новый релиз, очистка preview и
доступность основного production-сайта после всех операций.
Тот же сценарий запускается в GitHub через ручной workflow
`Verify Helios resilience`, который требует контрольную строку
`mkdocs-deployment-lab-sandbox`.

Контрольный локальный запуск на commit `39b45a8` успешно проверил все сценарии.
После записи JSON-доказательства sandbox был удалён; основной сайт и портфолио
продолжили отвечать HTTP 200.

Ручной GitHub Actions workflow повторил полный набор сценариев на commit
`c14c580` и также завершился успешно. После него удалённые sandbox-пути
отсутствовали, sandbox URL отвечал HTTP 404, а основной сайт и портфолио — HTTP
200. Квитанция сохранена в `evidence/logs/helios-resilience-actions.json`.
