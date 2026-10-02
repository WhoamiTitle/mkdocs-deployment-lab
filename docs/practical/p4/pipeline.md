# Пайплайн публикации

```mermaid
flowchart LR
    A[push] --> B[CI workflow]
    P[pull request] --> B
    B --> C[lint, тесты, strict build]
    C --> D[проверенный site artifact]

    A --> E[Publish workflow]
    M[ручной dispatch] --> E
    E --> Q[встроенный quality gate]
    Q --> F{ветка}
    F -->|main| G[Pages build и deploy]
    F -->|main| H[Helios production]
    F -->|другая ветка| I[Helios preview]
    H --> J[healthcheck]
    I --> J
    J -->|ошибка production| K[автоматический rollback]

    X[удаление ветки] --> L[cleanup preview]
```

Workflow отвечает за событие, permissions, установку Python и получение
секретов. Последовательность прикладных действий реализована Python-командами,
которые одинаково запускаются локально и в CI.

`CI` и `Publish` остаются независимыми workflows одного push, однако `Publish`
содержит собственный полный quality job. Все jobs сборки и доставки прямо либо
транзитивно зависят от `quality`, поэтому upload или `rsync` не запускаются
после ошибки линтера, типизации, тестов, strict build или offline-check. Pull
request запускает только CI и не получает deploy-секреты.

Production job сохраняет отдельные JSON-квитанции сборки, `rsync` и
healthcheck как GitHub Actions artifact. В них нет закрытого ключа или строки
`known_hosts`; они содержат release ID, длительности, размеры и результат
проверки. Это позволяет собирать серию T4 без округления данных из интерфейса.

## Метаданные релиза

В каждый артефакт добавляются:

- идентификатор релиза;
- полный хеш коммита;
- имя ветки;
- дата и время сборки;
- признак незакоммиченных локальных изменений.

Наблюдатель удалённой публикации принимает только релиз с ожидаемым commit SHA
и временем сборки не раньше начала конкретного запуска. Поэтому повторные
workflow одного и того же коммита не могут ошибочно принять предыдущий релиз.

## Файлы автоматизации

| Файл | Назначение |
|---|---|
| `.github/workflows/ci.yml` | Ruff, форматирование, codespell, mypy, pytest, strict build и offline-check |
| `.github/workflows/publish.yml` | GitHub Pages, Helios production и branch preview |
| `.github/workflows/rollback.yml` | ручное переключение Helios на предыдущий релиз |
| `.github/workflows/cleanup-preview.yml` | ручная и автоматическая очистка preview после удаления ветки |
| `.github/workflows/helios-resilience.yml` | разрушительные испытания только в sandbox |

Все сторонние Actions закреплены полными commit SHA. Комментарий после SHA
указывает читаемую major-версию, но не участвует в разрешении зависимости.

## События и поведение

| Событие | CI | GitHub Pages | Helios | Результат |
|---|---|---|---|---|
| `push` в `main` | полный quality gate | production | production + healthcheck | две площадки публикуют один SHA |
| `push` в другую ветку | полный quality gate | пропуск | preview по branch slug | production не переключается |
| `pull_request` | полный quality gate | не запускается | не запускается | секреты deploy не требуются |
| ручной `Publish` на `main` | встроенный quality gate | production | production + healthcheck | используется для повторов T4 |
| ручной `Roll back Helios` | не запускается | без изменений | активируется `previous` | затем выполняется healthcheck |
| удаление ветки | не запускается | без изменений | удаляется preview этой ветки | ожидаемый HTTP 404 |
| ручной sandbox-тест | не запускается | без изменений | отдельные sandbox-пути | production проверяется на изоляцию |

## CI: качество и проверенный артефакт

Ниже приведён сокращённый текст `ci.yml`; комментарии поясняют назначение
ключевых строк отчёта:

```yaml
on:
  push:          # проверяется каждый отправленный commit
  pull_request:  # код из PR проверяется без deploy-секретов

permissions:
  contents: read # CI не изменяет репозиторий

env:
  UV_VERSION: "0.12.22" # версия менеджера окружения фиксирована

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
        with:
          python-version: "3.13" # версия раннера фиксирована
      - name: Install locked dependencies
        run: |
          python -m pip install "uv==$UV_VERSION"
          uv sync --locked # pyproject.toml обязан совпадать с uv.lock
      - name: Run quality gates and strict build
        run: make check
      - name: Upload verified site artifact
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: site/
          retention-days: 7
```

`make check` последовательно запускает линтеры, типизацию, автоматические тесты, строгую
сборку и проверку отсутствия внешних runtime-ресурсов. При любой ошибке
последующие команды и загрузка артефакта не выполняются.

## Маршрутизация production

Два production job получают один commit, но собирают сайт отдельно, поскольку
им нужны разные `SITE_URL`:

```yaml
jobs:
  quality:
    steps:
      - name: Run quality gates and strict build
        run: make check

  build-pages:
    if: github.ref == 'refs/heads/main' # Pages только из main
    needs: quality                      # публикация только после всех проверок
    permissions:
      contents: read
      pages: read

  deploy-pages:
    needs: build-pages                 # deploy только после Pages build
    permissions:
      pages: write
      id-token: write

  deploy-helios-production:
    if: github.ref == 'refs/heads/main' && vars.HELIOS_ENABLED == 'true'
    needs: quality
    environment: helios-production     # отдельная граница секретов и настроек
    concurrency:
      group: helios-production         # общий lock с ручным rollback
```

Pages использует официальный artifact deployment. Helios получает отдельный
ключ только внутри production environment.

## Helios: доставка, проверка и откат

Секреты сначала записываются во временные файлы с режимом `0600`. В репозитории
и artifact они не сохраняются:

```yaml
- name: Prepare protected SSH files
  env:
    HELIOS_SSH_KEY: ${{ secrets.HELIOS_SSH_KEY }}
    HELIOS_KNOWN_HOSTS: ${{ secrets.HELIOS_KNOWN_HOSTS }}
  run: |
    install -d -m 700 .secrets
    install -m 600 /dev/null .secrets/helios_key
    install -m 600 /dev/null .secrets/known_hosts
    printf '%s\n' "$HELIOS_SSH_KEY" > .secrets/helios_key
    printf '%s\n' "$HELIOS_KNOWN_HOSTS" > .secrets/known_hosts

- name: Deploy production release
  id: deploy
  run: .venv/bin/python -m publication_pipeline deploy-ssh --site-dir site

- name: Verify production release
  run: >-
    .venv/bin/python -m publication_pipeline healthcheck
    --url "$HELIOS_BASE_URL"
    --release-file site/release.json
    --attempts 5
    --delay-seconds 5

- name: Roll back after a failed production healthcheck
  id: rollback
  if: failure() && steps.deploy.outcome == 'success'
  run: >-
    .venv/bin/python -m publication_pipeline rollback-ssh
    | tee "$RUNNER_TEMP/helios-rollback.json"

- name: Verify restored production release
  if: failure() && steps.rollback.outcome == 'success'
  run: |
    release_id="$(python -c 'import json, sys; print(json.load(open(sys.argv[1]))["release_id"])' \
      "$RUNNER_TEMP/helios-rollback.json")"
    .venv/bin/python -m publication_pipeline healthcheck \
      --url "$HELIOS_BASE_URL" \
      --expected-text "deployment-marker:${release_id}:"
```

Условие rollback различает ошибку загрузки и ошибку после переключения. Если
`deploy-ssh` не завершился, активная ссылка ещё не менялась. Если deploy прошёл,
но HTTP-проверка упала, workflow возвращает `previous`, извлекает release ID из
JSON-квитанции и подтверждает по HTTP метку именно этого релиза.

## Preview и очистка

```yaml
deploy-helios-preview:
  if: github.ref != 'refs/heads/main' && vars.HELIOS_ENABLED == 'true'
  concurrency:
    group: helios-preview-${{ github.ref_name }}
    cancel-in-progress: false
  environment: helios-preview

# В cleanup-preview.yml:
on:
  workflow_dispatch: # ручная очистка с точным именем ветки
  delete:            # автоматическая очистка после удаления ветки

jobs:
  cleanup-preview:
    concurrency:
      group: >-
        helios-preview-${{ github.event_name == 'delete' && github.event.ref || inputs.branch }}
      cancel-in-progress: false
```

Имя ветки преобразуется в slug с коротким хешем. Cleanup требует совпадения
`branch` и `confirm-branch`, удаляет только каталог вычисленного slug и
подтверждает недоступность URL кодом HTTP 404. Публикация и очистка одной ветки
используют одинаковую concurrency group, поэтому не могут одновременно менять
её preview-ссылку и каталог релизов.

## Артефакты

| Артефакт | Источник | Срок | Содержимое |
|---|---|---:|---|
| `site-build-<sha>` | CI | 7 дней | проверенный статический сайт |
| Pages artifact | `build-pages` | управляется Pages | сайт для официального deployment |
| `pages-measurement-<run-id>` | `build-pages` | 30 дней | время и размер сборки |
| `helios-measurement-<run-id>` | Helios production | 30 дней | build, `rsync`, healthcheck |
| `helios-rollback-<run-id>` | ручной rollback | 30 дней | release ID отката и повторный healthcheck |
| `helios-resilience-<run-id>` | sandbox workflow | 30 дней | результаты отказоустойчивости |
| `preview-cleanup-<run-id>` | cleanup workflow | 30 дней | branch slug и число удалённых релизов |
