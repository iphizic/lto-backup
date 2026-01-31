import subprocess
import sys
import shutil
import logging

logger = logging.getLogger(__name__)

class DependencyChecker:
    """Проверка системных зависимостей"""
    
    DEPENDENCIES = [
        'tar', 'mbuffer', 'mt', 'tapeinfo'
    ]
    
    OPTIONAL_DEPENDENCIES = [
        'mtx', 'smartctl', 'lsscsi', 'curl', 'gzip', 'bzip2', 'xz'
    ]
    
    @staticmethod
    def check_all() -> bool:
        """Проверить все зависимости"""
        print("\n🔍 Проверка системных зависимостей:")
        print("-" * 40)
        
        all_ok = True
        
        # Обязательные зависимости
        print("📦 Обязательные утилиты:")
        for tool in DependencyChecker.DEPENDENCIES:
            if DependencyChecker._check_tool(tool):
                print(f"  ✅ {tool}")
            else:
                print(f"  ❌ {tool} - ОБЯЗАТЕЛЬНАЯ УТИЛИТА ОТСУТСТВУЕТ")
                all_ok = False
        
        # Опциональные зависимости
        print("\n📦 Опциональные утилиты:")
        for tool in DependencyChecker.OPTIONAL_DEPENDENCIES:
            if DependencyChecker._check_tool(tool):
                print(f"  ✅ {tool}")
            else:
                print(f"  ⚠️  {tool} - опциональная утилита отсутствует")
        
        # Проверка Python модулей
        print("\n🐍 Python модули:")
        python_modules = [
            'yaml',
            'telegram',
            'requests'
        ]
        
        for module in python_modules:
            try:
                __import__(module)
                print(f"  ✅ {module}")
            except ImportError:
                if module in ['yaml', 'telegram', 'requests']:
                    print(f"  ❌ {module} - ТРЕБУЕТСЯ УСТАНОВКА")
                    all_ok = False
                else:
                    print(f"  ⚠️  {module} - опциональный модуль отсутствует")
        
        # Проверка доступа к ленточному устройству
        print("\n💾 Проверка доступа к оборудованию:")
        
        # Пробуем получить устройство из конфига
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            tape_dev = config.get('hardware', 'tape_dev', '/dev/nst0')
            
            if Path(tape_dev).exists():
                try:
                    # Пробуем открыть устройство
                    with open(tape_dev, 'rb') as f:
                        pass
                    print(f"  ✅ Устройство ленты доступно: {tape_dev}")
                except PermissionError:
                    print(f"  ❌ Нет прав на запись в {tape_dev}")
                    print(f"     Выполните: sudo chmod 666 {tape_dev}")
                    all_ok = False
                except Exception as e:
                    print(f"  ❌ Ошибка доступа к {tape_dev}: {e}")
                    all_ok = False
            else:
                print(f"  ❌ Устройство ленты не найдено: {tape_dev}")
                all_ok = False
        except:
            # Если не можем загрузить конфиг, проверяем стандартное устройство
            tape_dev = "/dev/nst0"
            if Path(tape_dev).exists():
                print(f"  ✅ Устройство ленты существует: {tape_dev}")
            else:
                print(f"  ❌ Устройство ленты не найдено: {tape_dev}")
                all_ok = False
        
        print("\n" + "=" * 40)
        
        if all_ok:
            print("✅ Все обязательные зависимости удовлетворены")
        else:
            print("❌ Отсутствуют обязательные зависимости")
            print("\n💡 Рекомендации:")
            print("  Ubuntu/Debian: sudo apt-get install tar mt-st mbuffer mtx-tools")
            print("  CentOS/RHEL: sudo yum install tar mt-st mbuffer mtx-tools")
            print("  Python: pip install PyYAML python-telegram-bot requests")
        
        return all_ok
    
    @staticmethod
    def _check_tool(tool_name: str) -> bool:
        """Проверить наличие инструмента в системе"""
        return shutil.which(tool_name) is not None
    
    @staticmethod
    def check_specific(tool_name: str) -> bool:
        """Проверить наличие конкретного инструмента"""
        return DependencyChecker._check_tool(tool_name)
    
    @staticmethod
    def get_tool_version(tool_name: str) -> str:
        """Получить версию инструмента"""
        try:
            result = subprocess.run(
                [tool_name, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Парсим первую строку вывода
                first_line = result.stdout.split('\n')[0]
                return first_line.strip()
            else:
                return "Не удалось определить версию"
                
        except Exception as e:
            return f"Ошибка: {e}"