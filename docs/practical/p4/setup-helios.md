# Подключение Helios

Эта операция выполняется после получения имени сервера, учётной записи и
публичного URL от администратора Helios.

## 1. Отдельный deploy-ключ

Для CI создаётся отдельная пара Ed25519. Личный ключ пользователя в workflow не
передаётся. Открытая часть добавляется в `authorized_keys` на Helios, закрытая —
в GitHub Actions Secret `HELIOS_SSH_KEY`.

## 2. Доверенный ключ сервера

Отпечаток SSH-сервера получают по доверенному каналу и сверяют до добавления.
Строка `known_hosts` сохраняется как `HELIOS_KNOWN_HOSTS`. Workflow использует
`StrictHostKeyChecking=yes`.

## 3. Variables репозитория

Пример находится в `config/helios.env.example`. Перед публикацией задаются:

- `HELIOS_ENABLED=true`;
- `HELIOS_HOST` и `HELIOS_PORT`;
- `HELIOS_USER`;
- `HELIOS_DEPLOYMENT_ROOT`;
- `HELIOS_PUBLIC_PATH`;
- `HELIOS_BASE_URL`.

Путь deployment рекомендуется располагать внутри `public_html`, если политика
веб-сервера запрещает следовать по символическим ссылкам за его пределы.

## 4. Первая публикация

После заполнения Variables и Secrets push в `main` запускает production deploy.
Push в другую ветку создаёт адрес
`<HELIOS_BASE_URL>/previews/<branch-slug>/`.

Перед включением `HELIOS_ENABLED` необходимо проверить, что `public_path` не
занят обычным каталогом: pipeline управляет этим путём как символической
ссылкой.
