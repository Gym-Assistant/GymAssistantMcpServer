# Ранний запуск: текст отказа старта из плана

**Дата:** 2026-11-08  
**Ветка:** `feature/early-launch-fixes`

## Context

Backend отвечает 403 `type: plan_workout_start`, иногда вместе с `error: subscription_required`. MCP должен показывать отдельный код и короткий текст без слова «подписка».

## Current State

Сделано, не закоммичено.

## Plan / Done

- Проверка `type`/`feature == plan_workout_start` уже стоит первой (`integrations/local-gymassistant/http_transport.py`, `_send`); код `plan_workout_start` отдельный.
- Текст ошибки: «plan_workout_start: Старт из плана — в Плюсе.» (`ApiError`).
- Тесты: `test_compat_tools.py` — проверка текста при записи и новый `test_plan_start_is_recognized_before_a_subscription_error_in_the_same_body`.

## Verification

`python -m unittest discover -s integrations/local-gymassistant -q` — 111 тестов, OK.
