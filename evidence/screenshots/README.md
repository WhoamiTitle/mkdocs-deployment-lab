# Скриншоты отчёта

- `actions-publish-success.png` — успешный Publish run `36943230708`;
- `actions-ci-intentional-failure.png` — намеренно проваленный CI run
  `36943920803` на временной ветке;
- `github-pages-home.png` — опубликованный GitHub Pages с видимыми URL и SHA;
- `helios-home.png` — опубликованный Helios с видимыми URL и SHA.

Репозиторий закрывает HTML-страницы GitHub Actions от анонимного Chromium и
возвращает 404. Поэтому первые два изображения являются явно обозначенными
карточками из аутентифицированных GitHub REST API-ответов и очищенного журнала,
а не снимками приватной HTML-страницы. Исходные поля сохранены в
`evidence/logs/ci-run-evidence.json`.

Снимки сайтов сделаны реальным Chromium. Верхняя служебная полоса добавлена
после захвата, чтобы в изображении были видны проверенный URL, HTTP 200 и SHA.
Копии четырёх изображений находятся в `docs/assets/screenshots` для публикации
в MkDocs-отчёте.
