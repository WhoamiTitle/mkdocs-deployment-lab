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

Имена переменных для удалённого развёртывания приведены в
`config/helios.env.example`. Публичные параметры Helios уже зафиксированы;
доверенный ключ сервера и отдельный deploy-ключ добавляются через GitHub
Actions Secrets перед первой публикацией.

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
