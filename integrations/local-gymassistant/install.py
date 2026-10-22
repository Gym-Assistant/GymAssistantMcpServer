"""Установить локальный MCP из репозитория в отдельный каталог с резервной копией.

Запуск: python integrations/local-gymassistant/install.py /путь/к/установке [--dry-run]

Копирует server.py, модули и requirements.txt; run.sh — только если его ещё нет.
Не трогает .env, .venv, токены и прочие файлы. Прежние версии сохраняются в
.backups/repo-<время>; команды отката печатаются после установки.
Запущенные MCP-процессы продолжают старую версию до переподключения клиента.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys


SOURCE = Path(__file__).resolve().parent
MANAGED = ['server.py', 'core_tools.py', 'health_tools.py', 'plan_tools.py', 'workout_tools.py', 'requirements.txt']
WRAPPER = 'run.sh'


def _replace(source: Path, target: Path, mode: int | None = None):
    temporary = target.with_name(target.name + '.new')
    shutil.copyfile(source, temporary)
    if mode is not None:
        temporary.chmod(mode)
    os.replace(temporary, target)


def wrapper_sets_env_file(text: str) -> bool:
    return any(line.strip().startswith(('export GYM_MCP_ENV_FILE=', 'GYM_MCP_ENV_FILE='))
               for line in text.splitlines())


def has_default_env_file(target: Path, environ) -> bool:
    config_home = Path(environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return (target / '.env').is_file() or (config_home / 'gymassistant-mcp' / '.env').is_file()


def install(target, dry_run=False, environ=None):
    environ = os.environ if environ is None else environ
    target = Path(target).expanduser().resolve()
    if target == SOURCE:
        raise ValueError('Каталог установки совпадает с исходниками в репозитории.')
    for name in MANAGED:
        if name.endswith('.py'):
            compile((SOURCE / name).read_text(), str(SOURCE / name), 'exec')

    existing = [name for name in MANAGED + [WRAPPER] if (target / name).exists()]
    created = [name for name in MANAGED if name not in existing]
    if not (target / WRAPPER).exists():
        created.append(WRAPPER)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = target / '.backups' / f'repo-{stamp}'
    if dry_run:
        print(f'Проверка без изменений. Каталог: {target}')
        print(f'Будут заменены: {", ".join(n for n in existing if n != WRAPPER) or "—"}')
        print(f'Будут созданы: {", ".join(created) or "—"}')
        return backup

    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if existing:
        backup.mkdir(parents=True, mode=0o700)
        for name in existing:
            shutil.copy2(target / name, backup / name)
    # Сначала модули, затем server.py: новый процесс не увидит server.py без его модулей.
    for name in sorted(MANAGED, key=lambda n: n == 'server.py'):
        _replace(SOURCE / name, target / name, 0o644)
    if not (target / WRAPPER).exists():
        _replace(SOURCE / WRAPPER, target / WRAPPER, 0o755)

    print(f'Установлено в {target}.')
    if existing:
        print(f'Резервная копия: {backup}')
        print('Откат: cp ' + ' '.join(str(backup / n) for n in existing) + f' {target}/')
    if created:
        print('При откате удалить созданные файлы: ' + ', '.join(created))
    if not (target / '.venv' / 'bin' / 'python').exists():
        print(f'Нет виртуального окружения. Создайте: python3 -m venv {target / ".venv"} && '
              f'{target / ".venv" / "bin" / "pip"} install -r {target / "requirements.txt"}')
    else:
        print(f'Сверьте зависимости: {target / ".venv" / "bin" / "pip"} install -r {target / "requirements.txt"}')
    if not wrapper_sets_env_file((target / WRAPPER).read_text()) and not has_default_env_file(target, environ):
        print('Внимание: env-файл не найден, а run.sh не задаёт GYM_MCP_ENV_FILE. Задайте его в run.sh '
              'или в конфиге MCP-клиента, иначе GYM_API_TOKEN должен прийти из окружения процесса.')
    print('Ключи и .env не изменены. Переподключите MCP-клиент.')
    return backup


if __name__ == '__main__':
    arguments = [a for a in sys.argv[1:] if a != '--dry-run']
    if len(arguments) != 1:
        raise SystemExit('Использование: install.py /путь/к/установке [--dry-run]')
    install(arguments[0], dry_run='--dry-run' in sys.argv[1:])
