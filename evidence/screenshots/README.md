# Скриншоты отчёта

- `actions-publish-success.png` — успешный Publish run `36943230708`;
- `actions-ci-intentional-failure.png` — намеренно проваленный CI run
  `36943920803` на временной ветке;
- `github-pages-home.png` — опубликованный GitHub Pages с видимыми URL и SHA;
- `helios-home.png` — опубликованный Helios с видимыми URL и SHA.

Первые два изображения сделаны в авторизованном веб-интерфейсе GitHub Actions.
Исходные поля запусков дополнительно сохранены в
`evidence/logs/ci-run-evidence.json`, поэтому статусы, SHA и состав jobs можно
проверить независимо от снимков.

Снимки сайтов сделаны реальным Chromium. Верхняя служебная полоса добавлена
после захвата, чтобы в изображении были видны проверенный URL, HTTP 200 и SHA.
Копии четырёх изображений находятся в `docs/assets/screenshots` для публикации
в MkDocs-отчёте.
