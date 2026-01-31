#!/usr/bin/env python3
"""
Setup script for LTO Backup System
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from setuptools import setup, find_packages

def get_version():
    """Get version from package"""
    try:
        with open('core/__init__.py', 'r') as f:
            for line in f:
                if line.startswith('__version__'):
                    return line.split('=')[1].strip().strip('"\'')
    except:
        return "2.0.0"

def check_dependencies():
    """Check system dependencies"""
    print("🔍 Проверка системных зависимостей...")
    
    from utils.dependencies import DependencyChecker
    return DependencyChecker.check_all()

def install_python_deps():
    """Install Python dependencies"""
    print("📦 Установка Python зависимостей...")
    
    try:
        # Upgrade pip
        subprocess.run([
            sys.executable, "-m", "pip", "install", "--upgrade", "pip"
        ], check=True, capture_output=True)
        
        # Install requirements
        result = subprocess.run([
            sys.executable, "-m", "pip", "install",
            "-r", "requirements.txt"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Python зависимости установлены")
            return True
        else:
            print(f"❌ Ошибка установки зависимостей:")
            print(result.stderr)
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки зависимостей: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

def create_default_config():
    """Create default configuration"""
    config_path = Path("config.yaml")
    
    if not config_path.exists():
        print("📝 Создание конфигурации по умолчанию...")
        
        # Read example config
        example_path = Path("config.yaml.example")
        if example_path.exists():
            shutil.copy(example_path, config_path)
            print(f"✅ Конфигурация создана: {config_path}")
            print("⚠️  Отредактируйте config.yaml перед использованием!")
        else:
            print("❌ Файл config.yaml.example не найден")
    else:
        print(f"📝 Конфигурация уже существует: {config_path}")

def setup_logging_directory():
    """Setup logging directory"""
    log_dir = Path("/var/log/lto_backup")
    
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to set permissions
        try:
            os.chmod(log_dir, 0o755)
        except:
            pass
            
        print(f"📁 Директория логов: {log_dir}")
        
    except PermissionError:
        print(f"⚠️  Не удалось создать директорию логов {log_dir}")
        print(f"   Создайте вручную: sudo mkdir -p {log_dir}")
        print(f"   Установите права: sudo chmod 755 {log_dir}")

def create_systemd_service():
    """Create systemd service file"""
    if not os.path.exists("/usr/lib/systemd/system"):
        return
    
    service_content = """[Unit]
Description=LTO Backup System Scheduler
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lto_backup
ExecStart=/opt/lto_backup/lto_backup scheduler
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    service_path = "/usr/lib/systemd/system/lto-backup.service"
    
    try:
        with open(service_path, 'w') as f:
            f.write(service_content)
        
        print(f"✅ Сервис systemd создан: {service_path}")
        print("   Для включения: sudo systemctl enable lto-backup")
        print("   Для запуска: sudo systemctl start lto-backup")
        
    except PermissionError:
        print(f"⚠️  Не удалось создать сервис systemd")
        print(f"   Создайте файл вручную: {service_path}")

def install_to_system():
    """Install to system directories"""
    print("\n📦 Установка в системные директории...")
    
    install_dir = Path("/opt/lto_backup")
    
    try:
        # Create installation directory
        install_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all files
        files_to_copy = [
            "lto_backup.py",
            "config.yaml.example",
            "requirements.txt",
            "README.md"
        ]
        
        dirs_to_copy = [
            "core",
            "hardware", 
            "notification",
            "utils"
        ]
        
        for file in files_to_copy:
            if Path(file).exists():
                shutil.copy(file, install_dir / file)
        
        for directory in dirs_to_copy:
            if Path(directory).exists():
                shutil.copytree(
                    directory,
                    install_dir / directory,
                    dirs_exist_ok=True
                )
        
        # Make main script executable
        main_script = install_dir / "lto_backup.py"
        main_script.chmod(0o755)
        
        # Create symlink in /usr/local/bin
        symlink_path = Path("/usr/local/bin/lto_backup")
        if symlink_path.exists():
            symlink_path.unlink()
        
        symlink_path.symlink_to(main_script)
        
        print(f"✅ Установлено в: {install_dir}")
        print(f"✅ Симлинк создан: {symlink_path}")
        
        return True
        
    except PermissionError:
        print("❌ Требуются права администратора")
        print(f"   Выполните: sudo python3 {sys.argv[0]}")
        return False
    except Exception as e:
        print(f"❌ Ошибка установки: {e}")
        return False

def build_binary():
    """Build standalone binary"""
    print("\n🔨 Сборка бинарного файла...")
    
    if not os.path.exists("build_binary.sh"):
        print("❌ Скрипт build_binary.sh не найден")
        return False
    
    try:
        result = subprocess.run(
            ["bash", "build_binary.sh"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Бинарный файл создан")
            print(result.stdout)
            return True
        else:
            print("❌ Ошибка сборки бинарника")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при сборке: {e}")
        return False

def show_help():
    """Show help message"""
    print("""
LTO Backup System - Установка
=============================

Использование:
  python3 setup.py [опции]

Опции:
  --install      Установить в систему (/opt/lto_backup)
  --binary       Собрать бинарный файл
  --service      Создать сервис systemd
  --help         Показать эту справку

Примеры:
  python3 setup.py                    # Базовая установка
  python3 setup.py --install          # Установка в систему
  python3 setup.py --binary           # Сборка бинарника
  python3 setup.py --install --binary # Полная установка
""")

def main():
    """Main setup function"""
    print("=" * 60)
    print("       LTO Backup System - Установка")
    print("=" * 60)
    
    # Parse arguments
    args = sys.argv[1:]
    do_install = "--install" in args
    do_binary = "--binary" in args
    do_service = "--service" in args
    show_help_flag = "--help" in args
    
    if show_help_flag:
        show_help()
        return
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Требуется Python 3.7 или выше")
        sys.exit(1)
    
    print(f"🐍 Python версия: {sys.version_info.major}.{sys.version_info.minor}")
    
    # Check system dependencies
    print("\n" + "=" * 40)
    if not check_dependencies():
        response = input("\nПродолжить установку? (y/N): ").lower()
        if response != 'y':
            sys.exit(1)
    
    # Install Python dependencies
    print("\n" + "=" * 40)
    if not install_python_deps():
        sys.exit(1)
    
    # Create configuration
    print("\n" + "=" * 40)
    create_default_config()
    
    # Setup logging
    print("\n" + "=" * 40)
    setup_logging_directory()
    
    # Build binary if requested
    if do_binary:
        print("\n" + "=" * 40)
        if not build_binary():
            print("⚠️  Сборка бинарника пропущена")
    
    # Install to system if requested
    if do_install:
        print("\n" + "=" * 40)
        if install_to_system():
            # Create systemd service if requested
            if do_service:
                create_systemd_service()
    
    print("\n" + "=" * 60)
    print("✅ Установка завершена успешно!")
    print("=" * 60)
    
    # Show next steps
    print("\n📖 Следующие шаги:")
    
    if do_install:
        print("""
  1. Настройте конфигурацию:
     sudo nano /opt/lto_backup/config.yaml
     
  2. Проверьте систему:
     lto_backup check
     
  3. Создайте первый бэкап:
     lto_backup backup /путь/к/данным 'Первый_бэкап'
     
  4. (Опционально) Включите планировщик:
     sudo systemctl enable lto-backup
     sudo systemctl start lto-backup
""")
    else:
        print("""
  1. Отредактируйте конфигурацию:
     nano config.yaml
     
  2. Проверьте систему:
     python3 lto_backup.py check
     
  3. Создайте первый бэкап:
     python3 lto_backup.py backup /путь/к/данным 'Первый_бэкап'
     
  4. (Опционально) Запустите планировщик:
     python3 lto_backup.py scheduler
""")
    
    print("\n📚 Полная документация в README.md")

if __name__ == "__main__":
    main()