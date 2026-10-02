# Публикация результатов исследований: T4 + P4

Репозиторий содержит статический сайт на MkDocs Material и воспроизводимый
pipeline публикации. Исследовательская часть T4 рассматривает риски способов
развёртывания. Практическая часть P4 реализует публикацию по SSH/rsync,
preview-сборки, healthcheck и откат.

## Опубликованные результаты

- репозиторий: <https://github.com/WhoamiTitle/mkdocs-deployment-lab>;
- GitHub Pages: <https://whoamititle.github.io/mkdocs-deployment-lab/>;
- Helios ИТМО: <https://se.ifmo.ru/~s507353/mkdocs-deployment-lab/>.

Готовый текст для отправки в учебную систему находится в `SUBMISSION.md`.

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
`config/helios.env.example`. Публичные параметры Helios уже зафиксированы;
доверенный ключ сервера и отдельный deploy-ключ добавляются через GitHub
Actions Secrets перед первой публикацией.

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

Локально проверены строгая сборка, 34 автоматических теста, production и
preview-публикация, HTTP healthcheck, rollback, локальная загрузка KaTeX и
русскоязычный поиск. GitHub Pages опубликован официальным Pages artifact
workflow; для него собраны три замера времени доставки и browser trace с
заблокированными внешними origin. SSH-доступ, совместимость Helios с FreeBSD и
переход nginx по ссылке из `public_html` в `~/.deployments` проверены.
Отдельный deploy-ключ установлен на Helios и проверен с удалёнными командами и
`rsync`. Ed25519 host key сервера сопоставлен с ранее доверенной записью и
ключом сервера, после чего строгое подключение проверено с отдельным
`known_hosts`. GitHub Variables/Secrets настроены, `HELIOS_ENABLED=true`;
первый production deploy и отдельный preview workflow завершились успешно.
Разрушительные проверки rollback, ошибок загрузки и очистки preview выполнены
в отдельном sandbox; production и портфолио после них остались доступны.
На одном commit SHA выполнены три парных запуска GitHub Pages и Helios;
сохранены время сборки, `rsync`, healthcheck и интервал до внешней доступности.
Числовые результаты не подменяются локальной имитацией.
