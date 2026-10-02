# Текст для раздела «Ход работы»

Выполнены исследовательское задание T4 «Безопасность способов развёртывания» и
практическое задание P4 «Публикация на Helios по SSH/rsync».

Ссылки:

- репозиторий: https://github.com/WhoamiTitle/mkdocs-deployment-lab
- отчёт на GitHub Pages: https://whoamititle.github.io/mkdocs-deployment-lab/
- публикация на Helios: https://se.ifmo.ru/~s507353/mkdocs-deployment-lab/
- результаты измерений: https://whoamititle.github.io/mkdocs-deployment-lab/experiment/results/
- описание пайплайна: https://whoamititle.github.io/mkdocs-deployment-lab/practical/p4/pipeline/
- отладка и намеренно проваленный CI: https://whoamititle.github.io/mkdocs-deployment-lab/debugging/
- итоговый вывод: https://whoamititle.github.io/mkdocs-deployment-lab/conclusion/

Реализованы GitHub Pages и Helios production, preview для веток, HTTP
healthcheck, immutable-релизы, ручной и автоматический rollback, очистка
preview, строгая сборка и работа без внешних CDN. Проведены три парных запуска
на одном commit SHA; исходные CSV и JSON-квитанции находятся в репозитории.

Намеренно проваленный CI run:
https://github.com/WhoamiTitle/mkdocs-deployment-lab/actions/runs/36943920803

Успешный Publish run:
https://github.com/WhoamiTitle/mkdocs-deployment-lab/actions/runs/36943230708
