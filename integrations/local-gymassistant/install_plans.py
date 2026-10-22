"""Установить модуль планов в существующий локальный сервер, сохранив откат."""
import ast
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import sys


def replace_body(source, name, argument_names, body):
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(functions) != 1 or [arg.arg for arg in functions[0].args.args] != argument_names:
        raise ValueError(f'Неизвестная сигнатура {name}; установка отменена.')
    function = functions[0]
    start = function.body[0].lineno - 1
    if isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant) and isinstance(function.body[0].value.value, str):
        start = function.body[0].end_lineno
    lines = source.splitlines(keepends=True)
    lines[start:function.end_lineno] = [line + '\n' for line in body.splitlines()]
    return ''.join(lines)


def measurement_source(source):
    source = replace_body(source, '_summarize_workout', ['w', 'ex_idx'],
                          '    return summarize_workout(w, ex_idx, _workout_date)')
    source = replace_body(source, 'gym_records', ['top_n'],
        '    data = _api_get("/workouts", {"offset": 0, "limit": 200})\n'
        '    items = data.get("items", []) if isinstance(data, dict) else data\n'
        '    return build_records(items, _exercises(), top_n, _workout_date, _epley)')
    marker = 'if __name__ == "__main__":'
    imports = 'from workout_tools import summarize_workout, build_records\n'
    if imports not in source:
        source = source.replace(marker, imports + '\n' + marker)
    return source


def install(target):
    target = Path(target).expanduser().resolve()
    server = target / 'server.py'
    source = server.read_text()
    marker = 'if __name__ == "__main__":'
    if marker not in source or 'register_health_tools(mcp, _api_get)' not in source:
        raise ValueError('Неизвестная версия локального сервера; автоматическая установка отменена.')
    old_registration = 'register_plan_tools(mcp, _api_get, make_plan_writer(API_URL, TOKEN))'
    registration = 'register_plan_tools(mcp, _api_get, make_plan_writer(API_URL, TOKEN), make_plan_appender(API_URL, TOKEN))'
    source = measurement_source(source)
    backup = target / '.backups' / ('plans-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True, mode=0o700)
    for name in ['server.py', 'run.sh', 'health_tools.py', 'plan_tools.py', 'workout_tools.py']:
        if (target / name).exists():
            shutil.copy2(target / name, backup / name)
            (backup / name).chmod(0o600)
    if old_registration in source:
        source = source.replace(old_registration, registration)
        source = source.replace('from plan_tools import register_plan_tools, make_plan_writer\n',
                                'from plan_tools import register_plan_tools, make_plan_writer, make_plan_appender\n')
    if registration not in source:
        source = source.replace(marker, 'from plan_tools import register_plan_tools, make_plan_writer, make_plan_appender\n'
                                + registration + '\n\n\n' + marker)
        source = source.replace('read-only обёртка', 'чтение данных и создание новых планов')
    compile(source, str(server), 'exec')
    modules = [Path(__file__).with_name(name) for name in ['plan_tools.py', 'workout_tools.py']]
    for module in modules:
        compile(module.read_text(), str(module), 'exec')
    # Сначала модуль, затем регистрация. Запущенные процессы продолжают старую версию.
    for module in modules:
        temporary = target / (module.name + '.new')
        shutil.copy2(module, temporary)
        os.replace(temporary, target / module.name)
    temp = target / 'server.py.new'
    temp.write_text(source)
    temp.chmod(server.stat().st_mode)
    os.replace(temp, server)
    print(f'Установлено. Резервная копия: {backup}')
    print('Ключи, окружение и Health не изменены. Переподключите MCP-клиент.')


if __name__ == '__main__':
    install(sys.argv[1])
