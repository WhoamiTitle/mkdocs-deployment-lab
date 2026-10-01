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

## Очистка

Workflow `Clean Helios preview` запускается вручную с точным именем ветки или
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
