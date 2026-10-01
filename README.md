# Публикация результатов исследований: T4 + P4

Репозиторий содержит статический сайт на MkDocs Material и воспроизводимый
pipeline публикации. Исследовательская часть T4 рассматривает риски способов
развёртывания. Практическая часть P4 реализует публикацию по SSH/rsync,
preview-сборки, healthcheck и откат.

## Локальный запуск

Требуется Python 3.13.

```bash
make setup
make check
make serve
```

Сайт будет доступен по адресу `http://127.0.0.1:8000/`.

## Локальная имитация публикации

```bash
make deploy-local
python3 -m http.server 8080 --directory .local-deploy/public-site
```

В другом терминале можно проверить опубликованную версию:

```bash
.venv/bin/python -m publication_pipeline healthcheck \
  --url http://127.0.0.1:8080/ \
  --release-file site/release.json
```

Preview текущей ветки:

```bash
BRANCH=feature/report make preview-local
```

Имена переменных для удалённого развёртывания приведены в
`config/helios.env.example`. Значения хоста, пользователя, URL, доверенного
ключа сервера и deploy-ключа добавляются после получения доступа к Helios.

## Архитектура

Workflow и Makefile служат входными адаптерами. Сценарии сборки, публикации,
проверки и отката находятся в `src/publication_pipeline/application`.
Взаимодействие с MkDocs, Git, HTTP, локальной файловой системой и SSH/rsync
реализовано в инфраструктурных шлюзах.

## Лицензии

- исходный код: MIT, файл `LICENSE`;
- текст сайта и авторские иллюстрации: CC BY 4.0, файл `LICENSE-CONTENT.md`;
- сторонние ресурсы сохраняют собственные лицензии в каталогах `docs/assets/vendor`.

## Текущее состояние

Локально проверены строгая сборка, 20 автоматических тестов, production и
preview-публикация, HTTP healthcheck, rollback, локальная загрузка KaTeX и
русскоязычный поиск. GitHub Pages опубликован официальным Pages artifact
workflow; для него собраны три замера времени доставки и browser trace с
заблокированными внешними origin. Публикация на Helios ожидает доступ; её
числовые результаты не подменяются локальной имитацией.
