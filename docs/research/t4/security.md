# Модель угроз

## Секреты в pull request из форка

Код из внешнего форка контролируется автором pull request. Если передать такому
workflow секреты основного репозитория, изменённый шаг сможет отправить их на
чужой сервер. Поэтому workflow для внешнего pull request выполняет проверки и
сборку без deploy-секретов.

GitHub прямо указывает, что кроме ограниченного `GITHUB_TOKEN` секреты не
передаются runner при событии из fork. Источник:
[Using secrets in GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets#using-secrets-in-a-workflow).

## Фиксация Actions по SHA

Тег или ветка Git могут быть перемещены на другой коммит. Полный SHA связывает
workflow с конкретным просмотренным содержимым Action. Обновление Action в этом
случае становится отдельным видимым изменением репозитория.

GitHub называет полный commit SHA единственной неизменяемой ссылкой на Action.
Все внешние actions в workflow этого проекта закреплены 40-символьными SHA.
Источник: [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions).

## Supply chain атака

Если сторонний Action или его учётная запись скомпрометированы, вредоносный код
может прочитать доступные секреты, изменить артефакт или опубликовать подменённый
сайт. Снижение риска включает минимальные `permissions`, фиксацию зависимостей,
проверку артефакта и разделение build и deploy environment.

## Проверка ключа SSH-сервера

`known_hosts` должен содержать заранее проверенный открытый ключ сервера. Его
отпечаток получают по доверенному каналу и сверяют до добавления в настройки
репозитория. Отключение `StrictHostKeyChecking` лишает клиента защиты от
подмены сервера.

`ssh-keyscan` только получает предъявленный сетью ключ и сам не подтверждает
его подлинность. Поэтому результат сканирования нужно сверить по независимому
каналу, а CI запускать с `StrictHostKeyChecking=yes`. Источники:
[ssh-keyscan](https://man.openbsd.org/ssh-keyscan) и
[ssh_config](https://man.openbsd.org/ssh_config#StrictHostKeyChecking).

## Граница доступа deploy-ключа

Для публикации используется отдельная пара ключей. Открытый ключ добавляется на
Helios, закрытый хранится в GitHub Actions Secrets. Целевой аккаунт и права
каталогов должны позволять изменять только файлы данного сайта.
