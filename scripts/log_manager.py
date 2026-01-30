#!/usr/bin/env python3
"""
Утилита управления логами LTO Backup System
Просмотр, поиск, очистка и управление уровнем логирования
"""

import argparse
import sys
import os
from pathlib import Path

# Добавляем путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

import modules.lto_logger as lto_logger

def show_logs():
    """Показать информацию о лог-файлах"""
    logger = lto_logger.get_logger()
    log_files = logger.get_log_file_paths()
    
    if not log_files:
        print("📭 Лог-файлы не найдены")
        return
    
    print(f"📁 Директория логов: {logger.log_dir}")
    print("\n📊 Файлы логов:")
    print("-" * 60)
    print(f"{'Файл':<20} {'Размер':<15} {'Путь'}")
    print("-" * 60)
    
    total_size = 0
    for filename, info in sorted(log_files.items()):
        print(f"{filename:<20} {info['size_human']:<15} {info['path']}")
        total_size += info['size']
    
    print("-" * 60)
    print(f"Всего файлов: {len(log_files)}, Общий размер: "
          f"{logger._humanize_size(total_size)}")

def tail_log(log_name, lines=50):
    """Показать последние строки лога"""
    logger = lto_logger.get_logger()
    log_file = os.path.join(logger.log_dir, log_name)
    
    if not os.path.exists(log_file):
        print(f"❌ Файл лога не найден: {log_file}")
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        print(f"📄 Последние {lines} строк из {log_name}:")
        print("=" * 80)
        
        start = max(0, len(all_lines) - lines)
        for line in all_lines[start:]:
            print(line.rstrip())
            
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")

def search_logs(search_term, case_sensitive=False, max_results=100):
    """Поиск по всем лог-файлам"""
    logger = lto_logger.get_logger()
    log_files = logger.get_log_file_paths()
    
    if not search_term:
        print("❌ Укажите строку для поиска")
        return
    
    print(f"🔍 Поиск '{search_term}' в логах...")
    print("=" * 80)
    
    found_count = 0
    for filename, info in sorted(log_files.items()):
        try:
            with open(info['path'], 'r', encoding='utf-8', errors='ignore') as f:
                file_found = False
                
                for line_num, line in enumerate(f, 1):
                    if found_count >= max_results:
                        print(f"\n⚠️  Достигнут лимит результатов: {max_results}")
                        break
                    
                    if case_sensitive:
                        match = search_term in line
                    else:
                        match = search_term.lower() in line.lower()
                    
                    if match:
                        if not file_found:
                            print(f"\n📁 В файле {filename}:")
                            file_found = True
                        
                        # Подсветка найденного текста
                        if case_sensitive:
                            highlighted = line.replace(search_term, f"\033[91m{search_term}\033[0m")
                        else:
                            import re
                            pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                            highlighted = pattern.sub(lambda m: f"\033[91m{m.group()}\033[0m", line)
                        
                        print(f"  L{line_num:>5}: {highlighted.rstrip()}")
                        found_count += 1
                        
        except Exception as e:
            print(f"❌ Ошибка чтения {filename}: {e}")
    
    print(f"\n{'='*80}")
    if found_count > 0:
        print(f"🎯 Найдено совпадений: {found_count}")
    else:
        print("🔍 Совпадений не найдено")

def cleanup_logs(days=30):
    """Очистка старых логов"""
    logger = lto_logger.get_logger()
    
    print(f"🗑️  Очистка логов старше {days} дней...")
    
    # Подтверждение
    confirm = input(f"Вы уверены, что хотите удалить логи старше {days} дней? (y/N): ")
    if confirm.lower() != 'y':
        print("❌ Очистка отменена")
        return
    
    logger.cleanup_old_logs(days)
    print("✅ Очистка завершена")

def set_log_level(level):
    """Изменение уровня логирования"""
    logger = lto_logger.get_logger()
    
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if level.upper() not in valid_levels:
        print(f"❌ Неверный уровень. Допустимые: {', '.join(valid_levels)}")
        return
    
    new_config = {'log_level': level.upper()}
    logger.update_config(new_config)
    
    # Также обновляем конфигурационный файл если нужно
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yaml')
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if 'logging' not in config:
                config['logging'] = {}
            
            config['logging']['level'] = level.upper()
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            print(f"✅ Уровень логирования изменён на {level.upper()} (и в config.yaml)")
            
        except Exception as e:
            print(f"✅ Уровень логирования изменён на {level.upper()}")
            print(f"⚠️  Не удалось обновить config.yaml: {e}")
    else:
        print(f"✅ Уровень логирования изменён на {level.upper()}")

def stats_logs():
    """Статистика по логам"""
    logger = lto_logger.get_logger()
    log_files = logger.get_log_file_paths()
    
    if not log_files:
        print("📭 Лог-файлы не найдены")
        return
    
    print("📊 Статистика логов:")
    print("=" * 60)
    
    total_files = len(log_files)
    total_size = 0
    lines_count = 0
    error_count = 0
    warning_count = 0
    
    for filename, info in sorted(log_files.items()):
        total_size += info['size']
        
        try:
            with open(info['path'], 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    lines_count += 1
                    if 'ERROR' in line:
                        error_count += 1
                    elif 'WARNING' in line:
                        warning_count += 1
        except:
            pass
    
    print(f"📁 Файлов: {total_files}")
    print(f"📦 Общий размер: {logger._humanize_size(total_size)}")
    print(f"📝 Строк всего: {lines_count:,}")
    print(f"❌ Ошибок (ERROR): {error_count}")
    print(f"⚠️  Предупреждений (WARNING): {warning_count}")
    
    if lines_count > 0:
        error_percent = (error_count / lines_count) * 100
        warning_percent = (warning_count / lines_count) * 100
        print(f"📈 Ошибок: {error_percent:.2f}%")
        print(f"📈 Предупреждений: {warning_percent:.2f}%")
    
    # Самые большие файлы
    print(f"\n🏆 Самые большие файлы:")
    sorted_by_size = sorted(log_files.items(), key=lambda x: x[1]['size'], reverse=True)
    for i, (filename, info) in enumerate(sorted_by_size[:5], 1):
        print(f"  {i}. {filename}: {info['size_human']}")

def rotate_logs_now():
    """Принудительная ротация логов"""
    logger = lto_logger.get_logger()
    
    print("🔄 Принудительная ротация логов...")
    
    log_files = logger.get_log_file_paths()
    rotated = 0
    
    for filename, info in log_files.items():
        if info['size'] > 5 * 1024 * 1024:  # 5MB
            try:
                # Создаем копию с timestamp
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{info['path']}.{timestamp}.bak"
                
                import shutil
                shutil.copy2(info['path'], backup_name)
                
                # Очищаем файл
                open(info['path'], 'w').close()
                
                print(f"  ✅ Ротирован: {filename}")
                rotated += 1
                
            except Exception as e:
                print(f"  ❌ Ошибка ротации {filename}: {e}")
    
    if rotated > 0:
        print(f"✅ Ротировано файлов: {rotated}")
    else:
        print("ℹ️  Нет файлов для ротации (все меньше 5MB)")

def main():
    """Основная функция утилиты"""
    parser = argparse.ArgumentParser(
        description='Утилита управления логами LTO Backup System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s show                    - Показать все лог-файлы
  %(prog)s tail lto_system.log     - Посмотреть конец системного лога
  %(prog)s tail -n 100 errors.log  - Посмотреть 100 строк из лога ошибок
  %(prog)s search "ERROR"          - Найти все ошибки в логах
  %(prog)s search "backup" -i      - Найти 'backup' без учёта регистра
  %(prog)s cleanup                 - Удалить логи старше 30 дней
  %(prog)s cleanup --days 7        - Удалить логи старше 7 дней
  %(prog)s level DEBUG             - Установить уровень логирования DEBUG
  %(prog)s stats                   - Статистика по логам
  %(prog)s rotate                  - Принудительная ротация логов
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Команда')
    
    # Команда show
    subparsers.add_parser('show', help='Показать информацию о лог-файлах')
    
    # Команда tail
    tail_parser = subparsers.add_parser('tail', help='Показать конец лог-файла')
    tail_parser.add_argument('logfile', help='Имя лог-файла')
    tail_parser.add_argument('-n', '--lines', type=int, default=50, 
                           help='Количество строк (по умолчанию: 50)')
    
    # Команда search
    search_parser = subparsers.add_parser('search', help='Поиск по логам')
    search_parser.add_argument('term', help='Строка для поиска')
    search_parser.add_argument('-i', '--ignore-case', action='store_true',
                             help='Игнорировать регистр')
    search_parser.add_argument('--max-results', type=int, default=100,
                             help='Максимальное количество результатов (по умолчанию: 100)')
    
    # Команда cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Очистка старых логов')
    cleanup_parser.add_argument('--days', type=int, default=30,
                              help='Удалять логи старше N дней (по умолчанию: 30)')
    
    # Команда level
    level_parser = subparsers.add_parser('level', help='Изменение уровня логирования')
    level_parser.add_argument('level', help='Уровень: DEBUG, INFO, WARNING, ERROR, CRITICAL')
    
    # Команда stats
    subparsers.add_parser('stats', help='Статистика по логам')
    
    # Команда rotate
    subparsers.add_parser('rotate', help='Принудительная ротация логов')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'show':
            show_logs()
        elif args.command == 'tail':
            tail_log(args.logfile, args.lines)
        elif args.command == 'search':
            search_logs(args.term, not args.ignore_case, args.max_results)
        elif args.command == 'cleanup':
            cleanup_logs(args.days)
        elif args.command == 'level':
            set_log_level(args.level)
        elif args.command == 'stats':
            stats_logs()
        elif args.command == 'rotate':
            rotate_logs_now()
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Прервано пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()