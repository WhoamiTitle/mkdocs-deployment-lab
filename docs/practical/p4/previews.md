# Preview-сборки

Имя ветки преобразуется в безопасный slug. К slug добавляется короткий хеш
исходного имени, поэтому ветки `feature/a` и `feature-a` не конфликтуют.

Пример:

```text
feature/report -> feature-report-a13f7c21
```

Preview-релизы хранятся отдельно от production:

```text
preview-releases/<branch-slug>/<release-id>/
```

Публичная ссылка `previews/<branch-slug>` атомарно переключается на последнюю
сборку соответствующей ветки.
