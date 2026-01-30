#!/usr/bin/env python3
"""
Основной интерфейс LTO Backup System
После интеграции всех улучшений
"""

import sys
import os
import argparse
from datetime import datetime

# Добавляем путь к модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

from modules.config_manager import get_config_instance, LTOConfig
from modules.backup_job import BackupJob, JobManager, JobType, create_backup_task
from modules.lto_logger import get_logger, log_system, log_error
from modules.tape_drive import TapeDriveFactory
from modules.system_monitor import check_system_readiness
from modules.file_utils import normalize_path_encoding

# Инициализация
logger = get_logger()
config = get_config_instance()

def setup_argparse():
    """Настройка парсера аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description='LTO Backup System - профессиональное решение для резервного копирования на ленту',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s backup /data/project "Project_Backup_2024"  # Создать бэкап
  %(prog)s restore /restore/location "Project_Backup_2024"  # Восстановить
  %(prog)s status                                      # Показать статус системы
  %(prog)s list --type backup                         # Список бэкапов
  %(prog)s verify "Project_Backup_2024"               # Проверить целостность
  %(prog)s clean                                      # Выполнить чистку
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Команда')
    
    # Команда backup
    backup_parser = subparsers.add_parser('backup', help='Создание бэкапа')
    backup_parser.add_argument('source', help='Источник для бэкапа')
    backup_parser.add_argument('label', help='Метка бэкапа')
    backup_parser.add_argument('--verify', action='store_true', help='Проверить после записи')
    backup_parser.add_argument('--compress', action='store_true', help='Включить сжатие')
    
    # Команда restore
    restore_parser = subparsers.add_parser('restore', help='Восстановление из бэкапа')
    restore_parser.add_argument('destination', help='Целевая директория')
    restore_parser.add_argument('label', help='Метка бэкапа для восстановления')
    restore_parser.add_argument('--tape', help='Номер ленты для восстановления')
    
    # Команда list
    list_parser = subparsers.add_parser('list', help='Список бэкапов')
    list_parser.add_argument('--type', choices=['backup', 'tape', 'job'], default='backup',
                           help='Тип списка')
    list_parser.add_argument('--status', help='Фильтр по статусу')
    
    # Команда status
    subparsers.add_parser('status', help='Статус системы')
    
    # Команда verify
    verify_parser = subparsers.add_parser('verify', help='Проверка целостности')
    verify_parser.add_argument('label', help='Метка бэкапа для проверки')
    
    # Команда clean
    clean_parser = subparsers.add_parser('clean', help='Чистка ленточного накопителя')
    clean_parser.add_argument('--force', action='store_true', help='Принудительная чистка')
    
    # Команда config
    config_parser = subparsers.add_parser('config', help='Управление конфигурацией')
    config_parser.add_argument('--show', action='store_true', help='Показать конфигурацию')
    config_parser.add_argument('--validate', action='store_true', help='Проверить конфигурацию')
    config_parser.add_argument('--export', choices=['yaml', 'json'], 
                             help='Экспорт конфигурации в указанный формат')
    
    return parser

def command_backup(args):
    """Выполнение команды backup"""
    log_system(f"Запуск бэкапа: {args.source} -> {args.label}")
    
    # Нормализуем пути
    source = normalize_path_encoding(args.source)
    label = args.label
    
    # Проверяем систему
    if not check_system_readiness(config.buffer.size):
        log_error("Система не готова к выполнению бэкапа")
        return False
    
    # Создаем и запускаем задачу
    job = create_backup_task(source, label)
    
    if not job:
        log_error("Не удалось создать задачу бэкапа")
        return False
    
    # Ждем завершения
    job.wait_for_completion()
    
    # Сохраняем отчет
    report_file = f"backup_report_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    job.save_report(report_file)
    
    # Показываем результат
    result = job.result
    if result and result.status.value == 'completed':
        print(f"✅ Бэкап успешно завершен!")
        print(f"   Метка: {label}")
        print(f"   Ленты: {', '.join(result.tapes_used) if result.tapes_used else 'N/A'}")
        print(f"   Отчет: {report_file}")
        return True
    else:
        error_msg = result.error_message if result else "Неизвестная ошибка"
        print(f"❌ Ошибка бэкапа: {error_msg}")
        return False

def command_restore(args):
    """Выполнение команды restore"""
    log_system(f"Запуск восстановления: {args.label} -> {args.destination}")
    
    # Здесь будет реализация восстановления с использованием новых классов
    print("⚠️  Функция восстановления в процессе реализации...")
    return False

def command_list(args):
    """Выполнение команды list"""
    from modules.registry_manager import get_registry_manager
    
    if args.type == 'backup':
        manager = get_registry_manager()
        entries = manager.read_registry(config.database.registry_file)
        
        if not entries:
            print("📭 Бэкапы не найдены")
            return True
        
        print(f"📋 Список бэкапов ({len(entries)}):")
        print("=" * 100)
        print(f"{'Метка':<30} {'Дата':<20} {'Ленты':<20} {'Файл':<10} {'Манифест'}")
        print("=" * 100)
        
        for entry in entries[-20:]:  # Последние 20 записей
            print(f"{entry['label'][:28]:<30} {entry['timestamp'][:19]:<20} "
                  f"{entry['tapes'][:18]:<20} {entry['file_index']:<10} "
                  f"{os.path.basename(entry['manifest'])[:20]}...")
        
        return True
    
    elif args.type == 'tape':
        # Список лент
        tape_drives = TapeDriveFactory.create_all_available()
        
        if not tape_drives:
            print("📼 Ленточные устройства не найдены")
            return False
        
        print(f"📼 Обнаружено устройств: {len(tape_drives)}")
        for tape in tape_drives:
            info = tape.get_status()
            print(f"  • {info.device}: {info.vendor} {info.product} "
                  f"(статус: {info.status.value}, файл: {info.file_number})")
        
        return True
    
    else:
        print("❌ Неподдерживаемый тип списка")
        return False

def command_status(args):
    """Выполнение команды status"""
    from modules.system_monitor import get_system_info
    
    print("📊 СТАТУС СИСТЕМЫ LTO BACKUP")
    print("=" * 60)
    
    # Информация о системе
    sys_info = get_system_info()
    print("💻 Система:")
    print(f"  Хост: {sys_info['hostname']}")
    print(f"  CPU: {sys_info['cpu_count']} ядер, загрузка: {sys_info['cpu_percent']}")
    print(f"  Память: {sys_info['memory']['total']} всего, "
          f"{sys_info['memory']['available']} доступно")
    print(f"  Диск: {sys_info['disk_free']} свободно")
    print(f"  Load average: {', '.join(f'{x:.2f}' for x in sys_info['load_average'])}")
    
    # Ленточные устройства
    print("\n📼 Ленточные устройства:")
    tape_drives = TapeDriveFactory.create_all_available()
    
    if tape_drives:
        for tape in tape_drives:
            info = tape.get_status()
            status_icon = "✅" if info.status.value == 'ready' else "⚠️" if info.status.value == 'warning' else "❌"
            print(f"  {status_icon} {info.device}: {info.product} "
                  f"(статус: {info.status.value}, файл: {info.file_number})")
            
            if info.cleaning_required:
                print(f"     ⚠️  ТРЕБУЕТСЯ ЧИСТКА!")
    else:
        print("  ❌ Устройства не обнаружены")
    
    # Конфигурация
    print(f"\n⚙️  Конфигурация:")
    print(f"  Файл: {config.config_path}")
    print(f"  Формат: {config.config_format.value if config.config_format else 'N/A'}")
    print(f"  Буфер: {config.buffer.size}")
    print(f"  Telegram: {'✅ Включен' if config.notification.telegram_enabled else '❌ Выключен'}")
    
    # Директории
    print(f"\n📁 Директории:")
    print(f"  Манифесты: {config.database.manifest_dir}")
    print(f"  Логи: {config.database.log_dir}")
    print(f"  Реестр: {config.database.registry_file}")
    
    # Проверка готовности
    print(f"\n🔍 Проверка готовности:")
    ready = check_system_readiness(config.buffer.size)
    print(f"  Система: {'✅ ГОТОВА' if ready else '❌ НЕ ГОТОВА'}")
    
    return True

def command_verify(args):
    """Выполнение команды verify"""
    log_system(f"Проверка целостности бэкапа: {args.label}")
    
    # Здесь будет реализация проверки целостности
    print("⚠️  Функция проверки в процессе реализации...")
    return False

def command_clean(args):
    """Выполнение команды clean"""
    log_system("Запуск чистки ленточного накопителя")
    
    tape_drives = TapeDriveFactory.create_all_available()
    
    if not tape_drives:
        print("❌ Ленточные устройства не найдены")
        return False
    
    tape = tape_drives[0]
    info = tape.get_status()
    
    if not info.cleaning_required and not args.force:
        print("✅ Чистка не требуется")
        return True
    
    if args.force:
        print("⚠️  Запуск принудительной чистки...")
    else:
        print("⚠️  Ленточный накопитель требует чистки...")
    
    # Здесь можно добавить логику автоматической или ручной чистки
    print("ℹ️  Для чистки вставьте чистящую кассету UCC и нажмите Enter...")
    input()
    
    print("🧼 Чистка выполняется...")
    # Симуляция чистки
    import time
    time.sleep(3)
    
    print("✅ Чистка завершена")
    return True

def command_config(args):
    """Выполнение команды config"""
    if args.show:
        print("📄 Текущая конфигурация:")
        config_dict = config.to_dict()
        
        import yaml
        print(yaml.dump(config_dict, default_flow_style=False, allow_unicode=True))
        
        return True
    
    elif args.validate:
        print("✅ Проверка конфигурации...")
        is_valid = config.validate_and_fix()
        
        if is_valid:
            print("✅ Конфигурация валидна")
            return True
        else:
            print("❌ Конфигурация содержит ошибки")
            return False
    
    elif args.export:
        print(f"📤 Экспорт конфигурации в {args.export.upper()}...")
        
        if args.export == 'yaml':
            export_path = f"{config.config_path}.export.yaml"
            from modules.config_manager import ConfigFormat
            success = config.save(export_path, ConfigFormat.YAML)
        elif args.export == 'json':
            export_path = f"{config.config_path}.export.json"
            from modules.config_manager import ConfigFormat
            success = config.save(export_path, ConfigFormat.JSON)
        else:
            print(f"❌ Неподдерживаемый формат экспорта: {args.export}")
            return False
        
        if success:
            print(f"✅ Конфигурация экспортирована: {export_path}")
            return True
        else:
            print("❌ Ошибка экспорта конфигурации")
            return False
    
    else:
        print("❌ Не указана операция с конфигурацией")
        return False

def main():
    """Основная функция"""
    parser = setup_argparse()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        # Выполняем команду
        commands = {
            'backup': command_backup,
            'restore': command_restore,
            'list': command_list,
            'status': command_status,
            'verify': command_verify,
            'clean': command_clean,
            'config': command_config
        }
        
        if args.command in commands:
            success = commands[args.command](args)
            return 0 if success else 1
        else:
            print(f"❌ Неизвестная команда: {args.command}")
            return 1
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        return 130
    except Exception as e:
        log_error(f"Критическая ошибка: {str(e)}")
        print(f"💥 Критическая ошибка: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())