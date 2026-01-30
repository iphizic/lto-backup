#!/usr/bin/env python3
"""
Скрипт настройки безопасности LTO Backup System
Проверка прав доступа, настройка директорий, безопасная конфигурация
"""

import os
import sys
import stat
import getpass
import subprocess
from pathlib import Path

# Добавляем путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

def print_header(title):
    """Печать заголовка"""
    print("\n" + "="*60)
    print(f"🔒 {title}")
    print("="*60)

def check_config_permissions():
    """Проверка прав доступа к конфигурационным файлам"""
    print_header("ПРОВЕРКА ПРАВ ДОСТУПА К КОНФИГУРАЦИОННЫМ ФАЙЛАМ")
    
    config_files = [
        ("config.yaml", "YAML конфигурация"),
        ("config.yml", "YAML конфигурация (альтернативная)"),
        ("config.json", "JSON конфигурация"),
        ("backup_registry.csv", "Реестр бэкапов"),
        ("./manifests/", "Директория манифестов"),
        ("./logs/", "Директория логов"),
        ("./backups/", "Директория резервных копий")
    ]
    
    issues_found = 0
    
    for file_path, description in config_files:
        if not os.path.exists(file_path):
            if file_path.endswith('/'):
                print(f"ℹ️  {description} '{file_path}' не существует (будет создана)")
            else:
                print(f"ℹ️  {description} '{file_path}' не существует")
            continue
        
        try:
            st = os.stat(file_path)
            mode = st.st_mode
            
            # Проверяем доступность для других пользователей
            world_writable = bool(mode & stat.S_IWOTH)
            group_writable = bool(mode & stat.S_IWGRP)
            
            if file_path.endswith('/'):
                file_type = "директория"
                # Для директорий более строгие проверки
                if world_writable:
                    print(f"❌ {description} '{file_path}' доступна для записи ВСЕМ!")
                    print(f"   🔧 Рекомендуется: chmod o-w {file_path}")
                    issues_found += 1
                elif group_writable:
                    print(f"⚠️  {description} '{file_path}' доступна для записи ГРУППЕ")
                    print(f"   Проверьте, что это необходимо")
                else:
                    print(f"✅ {description} '{file_path}' - права в порядке (не writable для others)")
                    
            else:
                file_type = "файл"
                if world_writable:
                    print(f"❌ {description} '{file_path}' доступен для записи ВСЕМ!")
                    print(f"   🔧 Рекомендуется: chmod o-w {file_path}")
                    issues_found += 1
                elif group_writable and file_path not in ['backup_registry.csv']:
                    print(f"⚠️  {description} '{file_path}' доступен для записи ГРУППЕ")
                    print(f"   Проверьте, что это необходимо")
                else:
                    print(f"✅ {description} '{file_path}' - права в порядке")
                    
        except Exception as e:
            print(f"❌ Ошибка проверки {file_path}: {e}")
            issues_found += 1
    
    return issues_found

def check_tape_device():
    """Проверка ленточного устройства"""
    print_header("ПРОВЕРКА ЛЕНТОЧНОГО УСТРОЙСТВА")
    
    # Стандартные пути к ленточным устройствам
    tape_devices = [
        "/dev/nst0", "/dev/nst1", "/dev/nst2", "/dev/nst3",
        "/dev/st0", "/dev/st1", "/dev/st2", "/dev/st3"
    ]
    
    found_devices = []
    
    for device in tape_devices:
        if os.path.exists(device):
            found_devices.append(device)
    
    if not found_devices:
        print("❌ Ленточные устройства не обнаружены")
        print("   Проверьте:")
        print("   1. Подключено ли устройство")
        print("   2. Загружен ли модуль ядра: lsmod | grep st")
        print("   3. Загрузите модуль: sudo modprobe st")
        return 1
    
    print(f"✅ Обнаружено ленточных устройств: {len(found_devices)}")
    
    for device in found_devices:
        print(f"\n📼 Устройство: {device}")
        
        # Проверка прав доступа
        if os.access(device, os.R_OK | os.W_OK):
            print(f"   ✅ Права доступа: чтение/запись разрешены")
        else:
            print(f"❌ Права доступа: нет прав чтения/записи")
            print(f"   🔧 Выполните: sudo chmod 666 {device}")
            print(f"   🔧 Или добавьте пользователя в группу: sudo usermod -a -G tape {getpass.getuser()}")
            return 1
        
        # Проверка что это действительно ленточное устройство
        try:
            result = subprocess.run(
                ["mt", "-f", device, "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                print(f"   ✅ Устройство отвечает на команды mt")
                
                # Извлекаем информацию
                for line in result.stdout.split('\n'):
                    if 'product' in line.lower():
                        product = line.split('=')[-1].strip()
                        print(f"   📋 Модель: {product}")
                    elif 'vendor' in line.lower():
                        vendor = line.split('=')[-1].strip()
                        print(f"   🏭 Производитель: {vendor}")
                        
            else:
                print(f"⚠️  Устройство не отвечает на команды mt")
                print(f"   Проверьте подключение и настройки")
                
        except FileNotFoundError:
            print(f"❌ Команда 'mt' не найдена")
            print(f"   🔧 Установите: sudo apt-get install mt-st")
            return 1
        except subprocess.TimeoutExpired:
            print(f"⚠️  Таймаут проверки устройства")
        except Exception as e:
            print(f"⚠️  Ошибка проверки устройства: {e}")
    
    return 0

def setup_secure_directories():
    """Настройка безопасных директорий"""
    print_header("НАСТРОЙКА БЕЗОПАСНЫХ ДИРЕКТОРИЙ")
    
    directories = [
        ("./logs", "Директория логов", 0o750),
        ("./manifests", "Директория манифестов", 0o750),
        ("./backups", "Директория резервных копий", 0o750),
        ("./cache", "Директория кэша", 0o700),  # Более строгие права
    ]
    
    for dir_path, description, mode in directories:
        try:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, mode=mode, exist_ok=True)
                print(f"✅ Создана {description}: {dir_path} (права: {oct(mode)})")
            else:
                # Обновляем права если нужно
                current_mode = os.stat(dir_path).st_mode & 0o777
                if current_mode != mode:
                    os.chmod(dir_path, mode)
                    print(f"✅ Обновлены права {description}: {dir_path} -> {oct(mode)}")
                else:
                    print(f"ℹ️  {description}: {dir_path} уже с правильными правами")
                    
        except Exception as e:
            print(f"❌ Ошибка настройки {dir_path}: {e}")

def check_telegram_config():
    """Проверка конфигурации Telegram"""
    print_header("ПРОВЕРКА КОНФИГУРАЦИИ TELEGRAM")
    
    config_files = ['config.yaml', 'config.yml', 'config.json']
    config_found = None
    
    for config_file in config_files:
        if os.path.exists(config_file):
            config_found = config_file
            break
    
    if not config_found:
        print("❌ Конфигурационный файл не найден")
        print("   Создайте config.yaml, config.yml или config.json")
        return 1
    
    print(f"📄 Используется конфигурация: {config_found}")
    
    try:
        import yaml
        import json
        
        if config_found.endswith('.yaml') or config_found.endswith('.yml'):
            with open(config_found, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        elif config_found.endswith('.json'):
            with open(config_found, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            print(f"❌ Неподдерживаемый формат конфигурации: {config_found}")
            return 1
        
        # Проверяем секцию notification
        if 'notification' not in config:
            print("ℹ️  Секция 'notification' не найдена в конфигурации")
            print("   Telegram уведомления будут отключены")
            return 0
        
        notification = config['notification']
        
        if not notification.get('telegram_enabled', False):
            print("ℹ️  Telegram уведомления отключены в конфигурации")
            return 0
        
        token = notification.get('telegram_token', '')
        chat_id = notification.get('telegram_chat_id', '')
        
        if not token or token in ['ВАШ_ТОКЕН_БОТА', '']:
            print("❌ Токен Telegram не настроен!")
            print("   Получите токен у @BotFather и укажите в config.yaml")
            return 1
        
        if not chat_id or chat_id in ['ВАШ_ID_ЧАТА', '']:
            print("❌ Chat ID не настроен!")
            print("   Узнайте свой Chat ID и укажите в config.yaml")
            return 1
        
        # Маскируем токен для вывода
        masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "****"
        print(f"✅ Токен Telegram: {masked_token}")
        print(f"✅ Chat ID: {chat_id}")
        
        # Проверяем подключение (опционально)
        test = input("\n🔍 Протестировать подключение к Telegram? (y/N): ").lower()
        if test == 'y':
            try:
                import requests
                url = f"https://api.telegram.org/bot{token}/getMe"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    print("✅ Подключение к Telegram успешно")
                    bot_info = response.json()
                    if bot_info.get('ok'):
                        print(f"   🤖 Бот: @{bot_info['result'].get('username', 'N/A')}")
                else:
                    print(f"⚠️  Ошибка подключения к Telegram: {response.status_code}")
                    
            except Exception as e:
                print(f"⚠️  Ошибка тестирования Telegram: {e}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка проверки конфигурации Telegram: {e}")
        return 1

def create_backup_scripts():
    """Создание скриптов для регулярного резервного копирования"""
    print_header("СОЗДАНИЕ СКРИПТОВ РЕЗЕРВНОГО КОПИРОВАНИЯ")
    
    # Скрипт для ежедневного бэкапа реестра
    backup_script_content = """#!/bin/bash
# Ежедневный бэкап реестра LTO Backup System
# Автоматически создается скриптом setup_security.py

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[$(date)] Начало ежедневного бэкапа реестра"

# Проверяем наличие модулей
if [ ! -f "modules/registry_manager.py" ]; then
    echo "Ошибка: модуль registry_manager.py не найден"
    exit 1
fi

# Выполняем бэкап реестра
python3 -m modules.registry_manager --backup

# Очищаем старые бэкапы (старше 30 дней)
BACKUP_DIR="./backups"
if [ -d "$BACKUP_DIR" ]; then
    echo "Очистка старых бэкапов..."
    find "$BACKUP_DIR" -name "registry_*.csv" -mtime +30 -delete
    find "$BACKUP_DIR" -name "registry_*.json" -mtime +30 -delete
    echo "Очистка завершена"
fi

echo "[$(date)] Ежедневный бэкап реестра завершен"
"""

    backup_script_path = "backup_registry_daily.sh"
    
    try:
        with open(backup_script_path, 'w', encoding='utf-8') as f:
            f.write(backup_script_content)
        
        os.chmod(backup_script_path, 0o750)
        print(f"✅ Создан скрипт: {backup_script_path}")
        
        print("\n📋 Для автоматического бэкапа реестра добавьте в crontab:")
        print("   crontab -e")
        print("   Добавьте строку:")
        absolute_path = os.path.abspath(backup_script_path)
        print(f"   0 2 * * * {absolute_path} >> /var/log/lto_backup.log 2>&1")
        print("\n   Или для текущего пользователя:")
        print(f"   0 2 * * * cd {os.path.dirname(absolute_path)} && ./backup_registry_daily.sh >> ~/lto_backup.log 2>&1")
        
    except Exception as e:
        print(f"❌ Ошибка создания скрипта: {e}")

def check_python_dependencies():
    """Проверка Python зависимостей"""
    print_header("ПРОВЕРКА PYTHON ЗАВИСИМОСТЕЙ")
    
    dependencies = [
        ("yaml", "PyYAML", "pip install pyyaml"),
        ("jsonschema", "jsonschema", "pip install jsonschema"),
        ("psutil", "psutil", "pip install psutil"),
        ("chardet", "chardet", "pip install chardet"),
        ("requests", "requests", "pip install requests"),
    ]
    
    missing_deps = []
    
    for module, name, install_cmd in dependencies:
        try:
            __import__(module)
            print(f"✅ {name} ({module}) установлен")
        except ImportError:
            print(f"❌ {name} ({module}) отсутствует")
            missing_deps.append((name, install_cmd))
    
    if missing_deps:
        print(f"\n⚠️  Отсутствуют зависимости: {len(missing_deps)}")
        print("   Установите командами:")
        for name, install_cmd in missing_deps:
            print(f"   {install_cmd}  # {name}")
        
        install_all = input("\n📦 Установить все недостающие зависимости? (y/N): ").lower()
        if install_all == 'y':
            for _, install_cmd in missing_deps:
                print(f"\n🔧 Выполняю: {install_cmd}")
                try:
                    subprocess.run(install_cmd.split(), check=True)
                    print(f"✅ Установлено")
                except Exception as e:
                    print(f"❌ Ошибка установки: {e}")
    
    return len(missing_deps)

def generate_secure_config_template():
    """Генерация безопасного шаблона конфигурации"""
    print_header("ГЕНЕРАЦИЯ БЕЗОПАСНОГО ШАБЛОНА КОНФИГУРАЦИИ")
    
    if os.path.exists("config.yaml"):
        overwrite = input("config.yaml уже существует. Перезаписать? (y/N): ").lower()
        if overwrite != 'y':
            print("ℹ️  Генерация шаблона пропущена")
            return
    
    template = """# Безопасная конфигурация LTO Backup System
# Сгенерировано скриптом setup_security.py

database:
  registry_file: "backup_registry.csv"
  manifest_dir: "./manifests"
  backup_dir: "./backups"
  log_dir: "./logs"
  cache_dir: "./cache"

hardware:
  tape_device: "/dev/nst0"
  robot_enabled: false
  robot_device: "/dev/sg3"
  error_threshold: 50
  auto_clean: true
  clean_interval_hours: 24

buffer:
  size: "2G"
  fill_percent: "90%"
  block_size: "256k"
  auto_adjust: true
  min_size: "512M"
  max_size: "4G"

notification:
  telegram_enabled: false
  # Получите токен у @BotFather
  telegram_token: "ВАШ_ТОКЕН_БОТА"
  # Узнайте свой Chat ID
  telegram_chat_id: "ВАШ_ID_ЧАТА"
  email_enabled: false
  email_smtp_server: "smtp.example.com"
  email_smtp_port: 587
  email_username: ""
  email_password: ""
  email_recipients: []

backup:
  default_excludes:
    - "/proc"
    - "/sys"
    - "/dev"
    - "/run"
    - "/tmp"
    - "*.log"
    - "*.tmp"
    - "*.temp"
    - "*.cache"
  compress_before_backup: false
  encryption_enabled: false
  encryption_key: ""
  verify_after_backup: true
  max_backup_age_days: 365
  retention_policy: "yearly"

logging:
  level: "INFO"
  console_enabled: true
  file_enabled: true
  max_file_size: 10485760
  backup_count: 7
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  date_format: "%Y-%m-%d %H:%M:%S"
"""
    
    try:
        with open("config.yaml", 'w', encoding='utf-8') as f:
            f.write(template)
        
        os.chmod("config.yaml", 0o640)  # Чтение для владельца и группы, только запись для владельца
        print("✅ Создан безопасный шаблон конфигурации: config.yaml")
        print("   🔒 Права установлены: 640 (владелец: rw, группа: r, другие: нет)")
        
    except Exception as e:
        print(f"❌ Ошибка создания шаблона: {e}")

def main():
    """Основная функция настройки"""
    print("="*60)
    print("🔐 НАСТРОЙКА БЕЗОПАСНОСТИ LTO BACKUP SYSTEM")
    print("="*60)
    
    # Проверяем, что мы в нужной директории
    if not os.path.exists("lto_main.py") and not os.path.exists("modules/"):
        print("❌ Запустите скрипт из директории с LTO Backup System")
        print("   Текущая директория должна содержать lto_main.py или modules/")
        sys.exit(1)
    
    total_issues = 0
    
    # 1. Проверка Python зависимостей
    total_issues += check_python_dependencies()
    
    # 2. Проверка конфигурации Telegram
    total_issues += check_telegram_config()
    
    # 3. Проверка прав доступа
    total_issues += check_config_permissions()
    
    # 4. Проверка ленточного устройства
    total_issues += check_tape_device()
    
    # 5. Настройка директорий
    setup_secure_directories()
    
    # 6. Создание скриптов бэкапа
    create_backup_scripts()
    
    # 7. Генерация шаблона конфигурации (опционально)
    gen_config = input("\n📝 Сгенерировать безопасный шаблон конфигурации? (y/N): ").lower()
    if gen_config == 'y':
        generate_secure_config_template()
    
    print("\n" + "="*60)
    print("📊 ИТОГ НАСТРОЙКИ")
    print("="*60)
    
    if total_issues == 0:
        print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
        print("\n✅ Система готова к работе")
    else:
        print(f"⚠️  Найдено проблем: {total_issues}")
        print("\n🔧 Необходимо устранить указанные проблемы перед началом работы")
    
    print("\n🚀 Рекомендуемые действия:")
    print("1. Настройте config.yaml под вашу систему")
    print("2. Протестируйте систему: python3 lto_main.py status")
    print("3. Создайте тестовый бэкап: python3 lto_main.py backup /tmp/test TEST_BACKUP")
    print("4. Настройте автоматический бэкап реестра в crontab")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Настройка прервана пользователем")
        sys.exit(1)