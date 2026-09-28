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
