# Подключение Helios

Для проекта подтверждены следующие параметры:

- SSH: `s507353@helios.cs.ifmo.ru:2222`;
- домашний каталог: `/home/studs/s507353`;
- публичный каталог: `/home/studs/s507353/public_html`;
- URL сайта: `https://se.ifmo.ru/~s507353/mkdocs-deployment-lab/`;
- серверная ОС: FreeBSD 14.5;
- удалённый `rsync`: версия 3.4.1.

## 1. Отдельный deploy-ключ

Для CI создаётся отдельная пара Ed25519. Личный ключ пользователя в workflow не
передаётся. Открытая часть добавляется в `authorized_keys` на Helios, закрытая —
в GitHub Actions Secret `HELIOS_SSH_KEY`.

Проектный ключ создан 2 октября 2026 года и хранится локально вне репозитория:

```text
~/.ssh/mkdocs-deployment-lab-helios
~/.ssh/mkdocs-deployment-lab-helios.pub
```

Fingerprint открытого ключа:

```text
SHA256:+kxtTMGqedbzDTYS+ZMg5JTDV9JjKgOwmXCPBfJpUZw
```

Открытая часть добавлена в `authorized_keys` с ограничениями
`no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty`. Проверены
неинтерактивная аутентификация, выполнение удалённых команд и запуск `rsync`
через этот ключ. Закрытая часть не добавляется в Git и должна передаваться
только через GitHub Actions Secrets.

## 2. Доверенный ключ сервера

Отпечаток SSH-сервера получают по доверенному каналу и сверяют до добавления.
Строка `known_hosts` сохраняется как `HELIOS_KNOWN_HOSTS`. Workflow использует
`StrictHostKeyChecking=yes`.

Для Helios подтверждён Ed25519 fingerprint:

```text
SHA256:3n1x6Bq0hnfyxrWB/YeQQPaxUkE/GCX2vKKtl0nzGgM
```

Официально опубликованный fingerprint ИТМО обнаружить не удалось. Значение
проверено по трём совпавшим источникам: ранее принятой записи в пользовательском
`known_hosts`, свежему результату `ssh-keyscan` и
`/etc/ssh/ssh_host_ed25519_key.pub`, прочитанному через уже доверенное SSH-
соединение. Сравнение подтвердило совпадение полных открытых ключей, а не только
их отображаемых fingerprints.

Проверенная строка сохранена локально в игнорируемом файле
`.secrets/known_hosts` с режимом `600`. Строгое подключение отдельным deploy-
ключом прошло с отключённым глобальным `known_hosts`; контрольное подключение с
пустым файлом было отклонено. Именно одна строка из `.secrets/known_hosts`
передаётся в GitHub Actions Secret `HELIOS_KNOWN_HOSTS`.

## 3. Variables репозитория

Пример находится в `config/helios.env.example`. Перед публикацией задаются:

- `HELIOS_ENABLED=true`;
- `HELIOS_HOST` и `HELIOS_PORT`;
- `HELIOS_USER`;
- `HELIOS_DEPLOYMENT_ROOT`;
- `HELIOS_PUBLIC_PATH`;
- `HELIOS_BASE_URL`.

Рекомендуемая схема изолирует неизменяемые релизы от портфолио:

```text
/home/studs/s507353/
├── .deployments/mkdocs-deployment-lab/
└── public_html/mkdocs-deployment-lab -> активный релиз
```

Соседний проект `web-languages-portfolio` синхронизирует содержимое в корень
`public_html` с `rsync --delete`. Поэтому его deploy-скрипт обязан исключать
корневой путь `/mkdocs-deployment-lab` и не должен использовать
`--delete-excluded`.

Если веб-сервер запрещает переход по символической ссылке за пределы
`public_html`, deployment root переносится в
`public_html/.mkdocs-deployment-lab-deploy`. В таком случае этот скрытый путь
также добавляется в исключения deploy-скрипта портфолио.

## 4. Совместимость с FreeBSD

Адаптер определяет удалённую ОС перед атомарным переключением ссылки:

- Linux использует `mv -Tf`;
- FreeBSD использует `mv -fh`;
- неизвестная платформа останавливает публикацию до переключения ссылки.

## 5. Первая публикация

После заполнения Variables и Secrets push в `main` запускает production deploy.
Push в другую ветку создаёт адрес
`<HELIOS_BASE_URL>/previews/<branch-slug>/`.

Перед включением `HELIOS_ENABLED` необходимо проверить, что `public_path` не
занят обычным каталогом: pipeline управляет этим путём как символической
ссылкой.

Проверка от 2 октября 2026 года подтвердила выбранную схему: временная ссылка
из `public_html` на каталог внутри `~/.deployments` вернула HTTP 200 и
ожидаемый marker через nginx. После проверки временные файл, ссылка и каталоги
были удалены, а сайт портфолио остался доступен. Отдельный deploy-ключ,
Variables и Secrets добавлены в GitHub; `HELIOS_ENABLED` остаётся равным
`false` до контрольного прохождения CI и GitHub Pages без публикации на Helios.
