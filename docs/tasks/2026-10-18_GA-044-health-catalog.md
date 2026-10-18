# GA-044 — каталог Apple Health в MCP

Новый read-only инструмент get_apple_health_metrics возвращает серверный каталог ключей, единиц и агрегации. Дневной инструмент сохраняет новые метрики и ValueReadAt/ValueDeviceIds, не агрегирует повторно. Используется прежнее право health:read.

Клиент обновляется до 0.13.0 по опубликованному Swagger. Проверки: synthetic HTTP forwarding/metadata/null, полный dotnet test и Docker/CI; после выпуска — реальный read-only MCP. Проверки и публикация в работе.

## Проверка

Бэкенд 0.13.0 опубликован после fresh backup, isolated restore и protected-copy gates (run 39138126635). Клиент 0.13.0 опубликован по фактическому Swagger (run 39139032211). Release build: 0 ошибок/0 предупреждений; 16 тестов PASS. Проверка stdio initialize/tools/health выполнена отдельно. Публикация контейнера отслеживается после CI.
