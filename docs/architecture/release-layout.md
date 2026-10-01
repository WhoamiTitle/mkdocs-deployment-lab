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

public-path -> deployment-root/releases/<release-b>
```

Каждый production-релиз содержит ссылку `previews` на общий каталог preview.
Благодаря этому URL основной версии остаётся корневым, а preview доступны в
подкаталогах `previews/<branch-slug>/`.

Разрушительные проверки не используют эту production-структуру. Для них
создаётся отдельная пара путей:

```text
.deployments/mkdocs-deployment-lab-sandbox/
public_html/mkdocs-deployment-lab-sandbox -> sandbox release
```

Тестовый скрипт отклоняет любые другие deployment root, public path и URL.
