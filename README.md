# Публикация результатов исследований: T4 + P4

Репозиторий содержит статический сайт на MkDocs Material и воспроизводимый
pipeline публикации. Исследовательская часть T4 рассматривает риски способов
развёртывания. Практическая часть P4 реализует публикацию по SSH/rsync,
preview-сборки, healthcheck и откат.

## Опубликованные результаты

- репозиторий: <https://github.com/WhoamiTitle/mkdocs-deployment-lab>;
- GitHub Pages: <https://whoamititle.github.io/mkdocs-deployment-lab/>;
- Helios ИТМО: <https://se.ifmo.ru/~s507353/mkdocs-deployment-lab/>.

## Локальный запуск

Требуется Python 3.13. Перед первоначальной настройкой проверяются Python и
`pip`, затем через `pip` устанавливается зафиксированная версия `uv`:

```bash
python3 --version
python3 -m pip --version
python3 -m pip install "uv==0.12.22"
uv sync --locked
```

Команда `uv sync --locked` проверяет соответствие `pyproject.toml` файлу
`uv.lock` и создаёт проектное виртуальное окружение `.venv`; отдельная команда
`virtualenv` не требуется. После настройки проект проверяется и запускается так:

```bash
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

Настройки удалённой публикации задаются в GitHub Actions Variables и Secrets.
Variable `HELIOS_ENABLED=true` включает публикацию по SSH. Обязательная
Variable `DEPLOY_TARGETS` содержит JSON-массив целей: SSH-сервер, порт,
пользователь, URL, пути и имена секретов для каждой цели. Пример формата
находится в `config/deploy-targets.example.json`; workflow не читает этот
файл и завершается с ошибкой, если `DEPLOY_TARGETS` не задана.

Закрытые deploy-ключи и доверенные записи `known_hosts` хранятся в Secrets.
Для одного SSH-сервера несколько целей могут использовать общий секрет
`known_hosts`, сохраняя отдельные ключи доступа. Чтобы добавить хостинг,
добавьте необходимые Secrets и запись в `DEPLOY_TARGETS`. Изменять workflow
не требуется. Изменение настроек само по себе не запускает публикацию:
нужен push или ручной запуск Publish.

Одна job `build-helios` собирает отдельный артефакт для URL каждой цели и
передаёт их deploy-матрице. Каждая цель независимо выполняет доставку и
healthcheck; ошибка одной цели не отменяет остальные. Production публикуется
из `main`, другие ветки — в `previews/<branch-slug>/` на каждом аккаунте.
Все production-релизы сохраняют прежний механизм атомарного переключения
и автоматического отката после неудачного healthcheck.

Ручной workflow Roll back Helios требует ID одной цели, например
`helios-jenya`. Clean Helios preview позволяет выбрать одну цель или очистить
preview указанной ветки на всех целях. Verify Helios resilience тоже требует
выбора одной цели и выполняет прежние проверки только в отдельном sandbox.

Для локального CLI прежние переменные `HELIOS_*` из
`config/helios.env.example` по-прежнему поддерживаются. В новых workflow
параметры доставки берутся из списка целей, а не из этих старых Variables.

## Архитектура

CLI в `src/publication_pipeline/presentation` служит входным адаптером, а
`src/publication_pipeline/main.py` — composition root. Сценарии сборки, публикации,
проверки и отката находятся в `src/publication_pipeline/application`.
Взаимодействие с MkDocs, Git, HTTP, локальной файловой системой и SSH/rsync
реализовано в инфраструктурных шлюзах.

## Лицензии

- исходный код: MIT, файл `LICENSE`;
- текст сайта и авторские иллюстрации: CC BY 4.0, файл `LICENSE-CONTENT.md`;
- сторонние ресурсы сохраняют собственные лицензии в каталогах `docs/assets/vendor`.
