#!/usr/bin/env python3
"""
LTO Backup System - Единый бинарный файл
Основное приложение для управления резервным копированием на ленту LTO
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Определяем, работаем ли мы внутри бинарника PyInstaller
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys._MEIPASS)
    IS_BINARY = True
else:
    BASE_DIR = Path(__file__).parent
    IS_BINARY = False

# Добавляем пути для импорта
sys.path.insert(0, str(BASE_DIR))

try:
    from core.config_manager import ConfigManager
    from core.backup_engine import BackupEngine
    from core.registry_manager import RegistryManager
    from core.scheduler import BackupScheduler
    from hardware.tape_driver import TapeDriver
    from notification.telegram_bot import TelegramBot
    from utils.dependencies import DependencyChecker
except ImportError as e:
    print(f"❌ Ошибка импорта модулей: {e}")
    print("Запустите setup.py для установки зависимостей")
    sys.exit(1)

class LTOBackupSystem:
    """Главный класс системы резервного копирования LTO"""
    
    def __init__(self, config_path=None):
        self.is_binary = IS_BINARY
        self.binary_dir = BASE_DIR
        self.logger = logging.getLogger(__name__)
        
        # Определяем путь к конфигурации
        if config_path is None:
            # Ищем config.yaml в стандартных расположениях
            possible_paths = [
                Path.cwd() / "config.yaml",
                Path.cwd() / "config.yml",
                self.binary_dir / "config.yaml",
                Path.home() / ".config" / "lto_backup" / "config.yaml",
                Path("/etc") / "lto_backup" / "config.yaml",
            ]
            
            for path in possible_paths:
                if path.exists():
                    config_path = str(path)
                    break
            else:
                # Если конфиг не найден, создаем в текущей директории
                config_path = str(Path.cwd() / "config.yaml")
                if not Path(config_path).exists():
                    self._create_default_config(config_path)
        
        self.config_path = config_path
        self.config = ConfigManager(config_path)
        
        # Инициализируем компоненты
        self.backup_engine = BackupEngine(self.config)
        self.registry = RegistryManager(self.config)
        self.tape_driver = TapeDriver(self.config)
        self.bot = TelegramBot(self.config)
        self.scheduler = BackupScheduler(self.config)
        
        # Создаем необходимые директории
        self._create_directories()
        
        self.logger.info(f"Инициализирована система LTO Backup")
        self.logger.info(f"Конфигурация: {self.config_path}")
    
    def _create_default_config(self, config_path):
        """Создать конфигурацию по умолчанию"""
        import yaml
        
        default_config = {
            'common': {
                'registry_csv': 'backup_registry.csv',
                'manifest_dir': './manifests',
                'log_level': 'INFO',
                'retention_days': 90
            },
            'hardware': {
                'has_robot': False,
                'robot_dev': '/dev/sg3',
                'tape_dev': '/dev/nst0',
                'err_threshold': 50,
                'auto_rewind': True
            },
            'mbuffer': {
                'size': '2G',
                'fill_percent': '90%',
                'block_size': '256k',
                'change_script': 'lto_backup change_tape',
                'min_rate': '100M',
                'max_rate': '150M'
            },
            'telegram': {
                'enabled': True,
                'token': 'YOUR_BOT_TOKEN_HERE',
                'chat_id': 'YOUR_CHAT_ID_HERE',
                'notification_level': 'INFO',
                'backup_started': True,
                'backup_completed': True,
                'backup_failed': True,
                'tape_change': True,
                'cleaning_required': True
            },
            'backup': {
                'compression': 'none',
                'verify_after_backup': True,
                'create_manifest': True,
                'max_file_size': '100G',
                'split_large_files': True
            },
            'exclude': {
                'patterns': [
                    '/proc', '/sys', '/dev', '/run', '/tmp',
                    '*.log', '*.tmp', '*.temp', '.git',
                    '.svn', '.hg', '.DS_Store', 'Thumbs.db',
                    '*.pyc', '__pycache__', '.cache', '.npm', '.yarn'
                ],
                'max_file_size': '10G',
                'min_file_size': '1k',
                'exclude_older_than': '365d',
                'exclude_newer_than': '0d'
            }
        }
        
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True, indent=2)
        
        print(f"📝 Создан файл конфигурации: {config_path}")
        print("⚠️  Отредактируйте его перед использованием!")
    
    def _create_directories(self):
        """Создать необходимые директории"""
        directories = [
            self.config.get('common', 'manifest_dir'),
            Path(self.config.get('common', 'registry_csv')).parent
        ]
        
        for dir_path in directories:
            if dir_path:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def _check_dependencies(self):
        """Проверить системные зависимости"""
        checker = DependencyChecker()
        return checker.check_all()
    
    def backup(self, source, label):
        """Выполнить резервное копирование"""
        print("=" * 60)
        print(f"LTO Backup: {label}")
        print(f"Source: {source}")
        print(f"Config: {self.config_path}")
        print("=" * 60)
        
        if not Path(source).exists():
            print(f"❌ Источник не существует: {source}")
            return False
        
        # Проверка зависимостей
        if not self._check_dependencies():
            response = input("Продолжить? (y/N): ").lower()
            if response != 'y':
                return False
        
        return self.backup_engine.backup(source, label)
    
    def restore(self, destination, label):
        """Восстановить данные"""
        print("=" * 60)
        print(f"LTO Restore: {label}")
        print(f"Destination: {destination}")
        print("=" * 60)
        
        return self.backup_engine.restore(destination, label)
    
    def change_tape(self):
        """Сменить ленту"""
        print("=" * 60)
        print("LTO Tape Change")
        print("=" * 60)
        
        # Проверка чистки
        if self.tape_driver.check_cleaning_needed():
            print("🧼 Требуется чистка ленты!")
            self.bot.send_cleaning_request()
            
            if not self.config.get('hardware', 'has_robot'):
                print("Вставьте чистящую кассету и нажмите Enter...")
                input()
            else:
                print("🤖 Автоматическая чистка...")
            
            self.tape_driver.record_cleaning_time()
        
        # Запрос новой ленты
        print("\n🔔 ТРЕБУЕТСЯ СЛЕДУЮЩАЯ ЛЕНТА")
        label = self.tape_driver.request_tape_change()
        
        # Уведомление в Telegram
        self.bot.send_message(f"⏳ Ожидание ленты: `{label}`")
        
        print(f"\n📥 Вставьте ленту [{label}] и нажмите ENTER...")
        input()
        
        # Перемотка новой ленты
        self.tape_driver.rewind()
        
        print(f"✅ Лента {label} установлена")
        return True
    
    def list_backups(self):
        """Показать список бэкапов"""
        backups = self.registry.list_backups()
        
        if not backups:
            print("📭 Реестр бэкапов пуст")
            return
        
        print(f"📋 Найдено бэкапов: {len(backups)}")
        print("=" * 80)
        
        for i, backup in enumerate(backups, 1):
            print(f"{i:3}. {backup['timestamp']} | {backup['label']:30} | "
                  f"Ленты: {backup['tapes']:20} | Файл: {backup['file_number']}")
    
    def check_system(self):
        """Проверить состояние системы"""
        print("=" * 60)
        print("LTO System Check")
        print("=" * 60)
        
        print(f"\n📁 Информация о системе:")
        print(f"  Версия бинарника: {'Да' if self.is_binary else 'Нет'}")
        print(f"  Путь к конфигурации: {self.config_path}")
        print(f"  Путь к реестру: {self.config.get('common', 'registry_csv')}")
        print(f"  Директория манифестов: {self.config.get('common', 'manifest_dir')}")
        
        print(f"\n🔧 Проверка зависимостей:")
        self._check_dependencies()
        
        print(f"\n💾 Проверка оборудования:")
        status = self.tape_driver.status()
        if status.get('online', False):
            print("✅ Ленточный накопитель доступен")
            print(f"   Файл: {status.get('file_number', 'N/A')}")
            print(f"   Блок: {status.get('block_number', 'N/A')}")
        else:
            print("❌ Ленточный накопитель недоступен")
        
        if self.tape_driver.check_cleaning_needed():
            print("⚠️  Требуется чистка ленты!")
        else:
            print("✅ Чистка ленты не требуется")
        
        print(f"\n🤖 Проверка Telegram:")
        if self.bot.send_message("✅ Тестовое сообщение от LTO Backup System"):
            print("✅ Telegram бот работает")
        else:
            print("⚠️  Telegram бот не настроен или недоступен")
        
        print(f"\n📊 Проверка реестра:")
        backups = self.registry.list_backups()
        print(f"   Записей в реестре: {len(backups)}")
        
        print("\n" + "=" * 60)
        print("✅ Проверка завершена")
    
    def show_config(self):
        """Показать текущую конфигурацию"""
        import yaml
        
        print("=" * 60)
        print("Текущая конфигурация LTO Backup")
        print(f"Файл: {self.config_path}")
        print("=" * 60)
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_content = yaml.safe_load(f)
            print(yaml.dump(config_content, default_flow_style=False, allow_unicode=True, indent=2))
    
    def validate_config(self):
        """Проверить валидность конфигурации"""
        errors = self.config.validate()
        
        if errors:
            print("❌ Ошибки конфигурации:")
            for error in errors:
                print(f"  • {error}")
            return False
        else:
            print("✅ Конфигурация валидна")
            return True
    
    def show_stats(self):
        """Показать статистику системы"""
        print("=" * 60)
        print("Статистика LTO Backup System")
        print("=" * 60)
        
        # Статистика реестра
        backups = self.registry.list_backups()
        print(f"\n📊 Статистика бэкапов:")
        print(f"  Всего бэкапов: {len(backups)}")
        
        if backups:
            oldest = min(backups, key=lambda x: x['timestamp'])
            newest = max(backups, key=lambda x: x['timestamp'])
            print(f"  Самый старый: {oldest['timestamp']} ({oldest['label']})")
            print(f"  Самый новый: {newest['timestamp']} ({newest['label']})")
        
        # Статистика оборудования
        print(f"\n💾 Статистика оборудования:")
        tape_stats = self.tape_driver.get_tape_statistics()
        print(f"  Количество чисток: {tape_stats.get('cleaning_count', 0)}")
        print(f"  Последняя чистка: {tape_stats.get('last_cleaning', 'Нет данных')}")
        
        # Статистика использования лент
        used_tapes = self.tape_driver.get_used_tapes()
        if used_tapes != "N/A":
            tape_count = len(used_tapes.split())
            print(f"  Использовано лент: {tape_count}")
        
        # Проверка дискового пространства
        print(f"\n💿 Дисковое пространство:")
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            print(f"  Всего: {total // (2**30)} GB")
            print(f"  Использовано: {used // (2**30)} GB")
            print(f"  Свободно: {free // (2**30)} GB ({free/total*100:.1f}%)")
        except:
            print("  Не удалось получить информацию о диске")
        
        print("\n" + "=" * 60)
    
    def version(self):
        """Показать версию"""
        version_info = f"""
LTO Backup System v2.0.0
Binary: {'Yes' if self.is_binary else 'No'}
Python: {sys.version}
Platform: {sys.platform}
Config: {self.config_path}
YAML Config: Yes
        """
        print(version_info.strip())
    
    def run_scheduler(self):
        """Запустить планировщик"""
        if not self.config.get('scheduling', 'enabled'):
            print("❌ Планировщик отключен в конфигурации")
            return False
        
        print("=" * 60)
        print("Запуск планировщика LTO Backup")
        print("=" * 60)
        
        return self.scheduler.run()

def main():
    """Точка входа"""
    parser = argparse.ArgumentParser(
        description="LTO Backup System - Профессиональная система резервного копирования на ленту",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s backup /home/user/data "MyBackup_2024"
  %(prog)s restore /home/user/restore "MyBackup_2024"
  %(prog)s change_tape
  %(prog)s list
  %(prog)s check
  %(prog)s config
  %(prog)s stats
  %(prog)s validate
  %(prog)s version
  %(prog)s scheduler
        """
    )
    
    parser.add_argument(
        'command',
        nargs='?',
        choices=['backup', 'restore', 'change_tape', 'list', 'check', 
                'config', 'stats', 'validate', 'version', 'scheduler'],
        help='Команда для выполнения'
    )
    
    parser.add_argument(
        'args',
        nargs='*',
        help='Аргументы команды'
    )
    
    parser.add_argument(
        '--config',
        help='Путь к файлу конфигурации YAML'
    )
    
    parser.add_argument(
        '--version',
        action='store_true',
        help='Показать версию'
    )
    
    args = parser.parse_args()
    
    # Показать версию если запрошено
    if args.version:
        system = LTOBackupSystem(args.config)
        system.version()
        sys.exit(0)
    
    # Если команда не указана, показать помощь
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Создаем экземпляр системы
    try:
        system = LTOBackupSystem(args.config)
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        sys.exit(1)
    
    # Выполняем команду
    try:
        if args.command == 'backup':
            if len(args.args) != 2:
                print("❌ Ошибка: для backup требуется источник и метка")
                print("   Пример: backup /path/to/data \"My Backup\"")
                sys.exit(1)
            success = system.backup(args.args[0], args.args[1])
            sys.exit(0 if success else 1)
        
        elif args.command == 'restore':
            if len(args.args) != 2:
                print("❌ Ошибка: для restore требуется назначение и метка")
                print("   Пример: restore /path/for/restore \"My Backup\"")
                sys.exit(1)
            success = system.restore(args.args[0], args.args[1])
            sys.exit(0 if success else 1)
        
        elif args.command == 'change_tape':
            system.change_tape()
        
        elif args.command == 'list':
            system.list_backups()
        
        elif args.command == 'check':
            system.check_system()
        
        elif args.command == 'config':
            system.show_config()
        
        elif args.command == 'stats':
            system.show_stats()
        
        elif args.command == 'validate':
            success = system.validate_config()
            sys.exit(0 if success else 1)
        
        elif args.command == 'version':
            system.version()
        
        elif args.command == 'scheduler':
            success = system.run_scheduler()
            sys.exit(0 if success else 1)
    
    except KeyboardInterrupt:
        print("\n⚠️  Операция прервана пользователем")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()