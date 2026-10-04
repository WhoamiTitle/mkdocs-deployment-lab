# Preview-сборки

Push любой ветки, включая `main`, публикуется на всех площадках в
`previews/<branch-slug>/`. Корень и `latest` обновляются только стабильной
публикацией. На Pages весь набор preview сохраняется в `site-builds` и
включается в следующий общий artifact.

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

## Очистка

На Pages выбранное preview удаляется из общего artifact. Параметр `target`
ограничивает очистку Helios одной целью; preview Pages удаляется в любом случае.

Workflow `Clean site previews` запускается вручную с точным именем ветки или
автоматически после удаления ветки. Команда требует повторного подтверждения,
удаляет только ссылку и каталоги одного вычисленного slug и завершается
проверкой HTTP 404:

```bash
python -m publication_pipeline cleanup-preview-ssh \
  --branch feature/report \
  --confirm-branch feature/report
```

Совпадение `--branch` и `--confirm-branch` обязательно; production-релизы эта
операция не затрагивает.

Проверка на ветке `test/helios-preview` удалила четыре preview-релиза и вернула
HTTP 404. После удаления самой ветки автоматический повтор успешно удалил ноль
уже отсутствующих релизов, подтвердив идемпотентность операции. Production URL
при этом продолжил отвечать HTTP 200.
