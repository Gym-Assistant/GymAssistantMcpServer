# CI MCP на локальном Mac

## Контекст

Лимит GitHub-hosted минут исчерпан. Владелец запросил продолжение сборок на своём Mac; production и ключи MCP не меняются.

## Текущее состояние

- `CI_RUNNER_MODE=local` выбирает официальный repo-level runner с метками `self-hosted`, `macOS`, `ARM64`, `gymassistant-mac`.
- При любом другом значении остаётся прежний `ubuntu-latest`; для возврата не нужен новый коммит.
- В локальном режиме публичные репозитории, pull request из fork и Dependabot пропускаются до выдачи задания runner. Внутри задания тот же запрет проверяется повторно.

## План и сделанное

- Все три CI-задания и release используют переключатель; прежние .NET/Python/stdio проверки сохранены.
- Локально используются уже установленные .NET 10 и Python 3.14, версии проверяются. `setup-dotnet` и `setup-python` сохранены для GitHub-hosted режима. Python-зависимости устанавливаются в отдельный venv внутри `RUNNER_TEMP`.
- Docker Desktop использует исходный локальный Unix socket. Перед login создаётся отдельный `DOCKER_CONFIG` с правами каталога 0700 и файла 0600; личный Docker config, credentials store и контексты не копируются и не изменяются.
- BuildKit-секреты имеют уникальную временную директорию и удаляются trap. CI-образ имеет уникальный run/attempt tag, удаляется только этот tag. `checkout` не оставляет токен в Git config.
- QEMU устанавливается только на Linux; на Mac используется поддержка Docker Desktop. Release проверяет наличие `linux/amd64` и `linux/arm64` у builder и продолжает выпуск обоих вариантов.
- Docker login-action выполняет штатный logout; job временные файлы очищаются runner. При аварийном выключении Mac перед повторным запуском следует убедиться, что прежний runner завершил cleanup своего `_temp`, не удаляя пользовательские каталоги Docker.

## Проверка

- **10/10 тестов PASS**: запрет публичного репозитория, fork, Dependabot, неправильной платформы, удалённого Docker и подстановки переменных через endpoint; поддержка hosted Linux и отдельного приватного config. Тесты используют fake Docker без ключей и API.
- `bash -n`, `shellcheck`, разбор трёх YAML и `git diff --check` — **PASS**.
- Реальный Docker Desktop preflight с временным `DOCKER_CONFIG`: Linux daemon и Buildx доступны; SHA личного `~/.docker/config.json` не изменился, auths/credsStore не скопированы. Временная директория удалена.
- Настоящий GitHub Actions run на зарегистрированном runner ещё не выполнен. Подготовленный workflow не равен подтверждённой работе CI.

## Ручная настройка

Владелец runner регистрируется отдельно через штатный GitHub Actions runner. В приватном репозитории выставляется `CI_RUNNER_MODE=local`; Mac должен быть включён, runner запущен, Docker Desktop доступен. Нужны .NET 10, Python 3.14 и Docker Buildx. Никакие production-подключения или дополнительные права ключа MCP не требуются.
