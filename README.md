# Публикация результатов исследований: T4 + P4 + P5

Репозиторий содержит статический сайт на MkDocs Material и воспроизводимый
pipeline публикации. Исследовательская часть T4 рассматривает риски способов
развёртывания. Практическая часть P4 реализует публикацию по SSH/rsync,
preview-сборки, healthcheck и откат. P5 добавляет версии по git-тегам,
переключатель версий, алиас `latest` и проверку русского локального поиска.

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

Для новой, ещё не инициализированной Helios-цели сначала опубликуйте
существующий стабильный тег через Publish с полем `version`: preview требует
готовую публичную ссылку production. Включение цели не создаёт её на сервере.

После quality gate одна job `prepare` собирает артефакты для всех URL,
сохраняя опубликованные версии и preview в служебной ветке `site-builds`.
Jobs доставки скачивают готовые файлы. Helios использует матрицу целей с
`fail-fast: false`: ошибка одной цели не отменяет остальные.

Push в любую ветку, включая `main`, обновляет только
`previews/<branch-slug>/` на Pages и Helios. Корень ведёт на `latest/`, а
`latest/` — на выбранную стабильную версию. Push тега `v1.1` публикует `v1.1/`
из его коммита и выбирает максимальную числовую версию как `latest`.
Поддерживаются теги `vMAJOR.MINOR` и `vMAJOR.MINOR.PATCH` без суффиксов.
Повторная публикация сохраняет готовые версии; перемещение опубликованного
тега на другой commit завершается ошибкой. Служебная ветка исключена из CI.

Первоначальная публикация двух срезов после проверки изменений:

```bash
git tag v1.0 0e19a7a
git tag v1.1
git push origin main --tags
```

`v1.0` фиксирует исходный срез, `v1.1` — commit с P5. Коммит изменений следует
сделать **до** тега `v1.1`. Первый запуск нового workflow обнаружит и соберёт
оба стабильных тега: старый commit сам ещё не содержит автоматизации P5.
В дальнейшем достаточно `git tag v1.2 && git push origin v1.2`. Тег можно
создать на commit другой ветки без слияния; в нём должен быть новый workflow.
Ручной Publish с полем `version` позволяет опубликовать уже существующий тег.

Workflow Select latest version выбирает существующую опубликованную версию
на всех площадках. Preview этот выбор не меняет; следующая публикация тега
снова выбирает максимальную версию. Roll back GitHub Pages возвращает
предыдущий стабильный снимок и сохраняет нынешние preview. После неудачного
Pages healthcheck автоматически возвращается предыдущая полная доставка.
Helios сохраняет прежние атомарные `current`/`previous` и автоматический откат.

Pages должен использовать источник GitHub Actions. В environment
`github-pages` разрешите deployment из используемых веток и тегов; ограничение
только на `main` помешает preview и tag deployment. Права `contents: write`
нужны jobs сохранения и подтверждения состояния служебной ветки, сама job доставки Pages использует
`pages: write` и `id-token: write`. Защита `site-builds` должна допускать запись
от workflow. Общая очередь `site-publication` исключает одновременную запись
снимков; GitHub concurrency может заменять ожидающий запуск более новым.

Ручной workflow Roll back Helios требует ID одной цели, например
`helios-jenya`. Clean site previews удаляет preview с Pages и выбранной цели
Helios либо всех целей. Удаление ветки запускает очистку всех площадок.
Verify Helios resilience тоже требует
выбора одной цели и выполняет прежние проверки только в отдельном sandbox.

Для локального CLI прежние переменные `HELIOS_*` из
`config/helios.env.example` по-прежнему поддерживаются. В новых workflow
параметры доставки берутся из списка целей, а не из этих старых Variables.

Структура URL, различия версий и таблица пяти поисковых запросов описаны
в `docs/practical/p5/`. Замеры прежней серии T4 сохранены как исторические;
новые значения времени доставки не подставляются без измерений.

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
