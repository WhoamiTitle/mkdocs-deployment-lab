# Структура релизов

```text
deployment-root/
├── releases/
│   ├── <release-a>/
│   └── <release-b>/
├── preview-releases/
│   └── <branch-slug>/
│       └── <release-id>/
├── shared-previews/
│   └── <branch-slug> -> ../preview-releases/<branch-slug>/<release-id>
├── current -> releases/<release-b>
└── previous -> releases/<release-a>

public-path -> deployment-root/current -> releases/<release-b>
```

Каждый production-релиз содержит ссылку `previews` на общий каталог preview.
В P5 внутри релиза находятся `v1.0/`, `v1.1/`, `latest/`, `versions.json` и
корневой redirect. Благодаря этому корень ведёт на выбранную версию, а preview доступны в
подкаталогах `previews/<branch-slug>/`.

Публичный путь постоянно указывает на `current`. Поэтому публикация меняет
видимую версию одной атомарной заменой `current`; отдельного переключения
публичной ссылки после активации релиза нет.

Разрушительные проверки не используют эту production-структуру. Для них
создаётся отдельная пара путей:

```text
.deployments/mkdocs-deployment-lab-sandbox/
public_html/mkdocs-deployment-lab-sandbox -> sandbox release
```

Тестовый скрипт отклоняет любые другие deployment root, public path и URL.
