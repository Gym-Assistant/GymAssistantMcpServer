"""Установить модуль планов в существующий локальный сервер, сохранив откат."""
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import sys


def install(target):
    target = Path(target).expanduser().resolve()
    server = target / 'server.py'
    source = server.read_text()
    marker = 'if __name__ == "__main__":'
    if marker not in source or 'register_health_tools(mcp, _api_get)' not in source:
        raise ValueError('Неизвестная версия локального сервера; автоматическая установка отменена.')
    old_registration = 'register_plan_tools(mcp, _api_get, make_plan_writer(API_URL, TOKEN))'
    registration = 'register_plan_tools(mcp, _api_get, make_plan_writer(API_URL, TOKEN), make_plan_appender(API_URL, TOKEN))'
    backup = target / '.backups' / ('plans-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True, mode=0o700)
    for name in ['server.py', 'run.sh', 'health_tools.py', 'plan_tools.py']:
        if (target / name).exists():
            shutil.copy2(target / name, backup / name)
    if old_registration in source:
        source = source.replace(old_registration, registration)
        source = source.replace('from plan_tools import register_plan_tools, make_plan_writer\n',
                                'from plan_tools import register_plan_tools, make_plan_writer, make_plan_appender\n')
    if registration not in source:
        source = source.replace(marker, 'from plan_tools import register_plan_tools, make_plan_writer, make_plan_appender\n'
                                + registration + '\n\n\n' + marker)
        source = source.replace('read-only обёртка', 'чтение данных и создание новых планов')
    compile(source, str(server), 'exec')
    module = Path(__file__).with_name('plan_tools.py')
    compile(module.read_text(), str(module), 'exec')
    # Сначала модуль, затем регистрация. Запущенные процессы продолжают старую версию.
    shutil.copy2(module, target / 'plan_tools.py.new')
    os.replace(target / 'plan_tools.py.new', target / 'plan_tools.py')
    temp = target / 'server.py.new'
    temp.write_text(source)
    temp.chmod(server.stat().st_mode)
    os.replace(temp, server)
    print(f'Установлено. Резервная копия: {backup}')
    print('Ключи, окружение и Health не изменены. Переподключите MCP-клиент.')


if __name__ == '__main__':
    install(sys.argv[1])
