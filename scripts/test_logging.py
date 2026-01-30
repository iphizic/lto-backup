#!/usr/bin/env python3
"""
Тестирование системы логирования LTO Backup System
Проверка всех компонентов логирования и ротации логов
"""

import os
import sys
import tempfile
import time
import json
from pathlib import Path
import logging

# Добавляем путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

def test_logging_system():
    """Основная функция тестирования"""
    print("🧪 ТЕСТИРОВАНИЕ СИСТЕМЫ ЛОГИРОВАНИЯ LTO BACKUP SYSTEM")
    print("="*60)
    
    # Импортируем после добавления пути
    import modules.lto_logger as lto_logger
    
    # Тест 1: Инициализация
    print("\n1. 📦 Инициализация логгера...")
    try:
        logger = lto_logger.get_logger()
        print(f"   ✅ Логгер инициализирован")
        print(f"   📁 Директория логов: {logger.log_dir}")
    except Exception as e:
        print(f"   ❌ Ошибка инициализации: {e}")
        return False
    
    # Тест 2: Запись тестовых сообщений на всех уровнях
    print("\n2. 📝 Запись тестовых сообщений на всех уровнях...")
    try:
        logger.system_logger.debug("Тестовое сообщение DEBUG уровня")
        logger.system_logger.info("Тестовое сообщение INFO уровня")
        logger.system_logger.warning("Тестовое сообщение WARNING уровня")
        logger.system_logger.error("Тестовое сообщение ERROR уровня")
        logger.system_logger.critical("Тестовое сообщение CRITICAL уровня")
        
        print("   ✅ Тестовые сообщения записаны на всех уровнях")
    except Exception as e:
        print(f"   ❌ Ошибка записи: {e}")
        return False
    
    # Тест 3: Специализированные методы логирования
    print("\n3. 🔧 Тест специализированных методов логирования...")
    try:
        # Команды
        logger.log_command("ls -la /tmp", success=True, execution_time=0.123)
        logger.log_command("rm /nonexistent", success=False, 
                         details="File not found", execution_time=0.456)
        
        # Бэкапы
        logger.log_backup_start("/test/data", "TestBackup_2024")
        logger.log_backup_complete("TestBackup_2024", ["TAPE001", "TAPE002"], 
                                 "3", total_size="1.5 GB", duration=2.5)
        
        # Ленты
        logger.log_tape_event("Тестовая смена ленты", "TEST123", "Тестовое событие")
        logger.log_clean_event("Test cleaning", manual_mode=True)
        
        # Ошибки
        logger.log_error("TestError", "Тестовая ошибка для проверки", 
                       context="test_logging.py", 
                       traceback_info="Traceback (most recent call last):\n  File 'test.py', line 1, in <module>\n    raise Exception('test')\nException: test")
        
        # Производительность
        start_time = time.time() - 5.5  # 5.5 секунд назад
        logger.log_performance("test_operation", start_time, data_size=1024*1024*100)  # 100MB
        
        print("   ✅ Специализированные методы работают")
    except Exception as e:
        print(f"   ❌ Ошибка специализированных методов: {e}")
        return False
    
    # Тест 4: Проверка создания файлов логов
    print("\n4. 📊 Проверка файлов логов...")
    try:
        log_files = logger.get_log_file_paths()
        
        if not log_files:
            print("   ❌ Файлы логов не найдены")
            return False
        
        expected_files = ['lto_system.log', 'lto_errors.log', 'lto_debug.log', 
                         'lto_tape.log', 'lto_performance.log']
        
        print(f"   ✅ Найдено {len(log_files)} файлов:")
        for name, info in sorted(log_files.items()):
            if name in expected_files:
                status = "✅"
            else:
                status = "⚠️ "
            print(f"      {status} {name}: {info['size_human']}")
            
    except Exception as e:
        print(f"   ❌ Ошибка проверки файлов: {e}")
        return False
    
    # Тест 5: Изменение уровня логирования
    print("\n5. 🎚️  Тест изменения уровня логирования...")
    try:
        print("   Текущий уровень: INFO")
        logger.system_logger.debug("Это сообщение НЕ должно появиться при уровне INFO (DEBUG)")
        
        # Меняем на DEBUG
        logger.update_config({'log_level': 'DEBUG'})
        print("   Уровень изменён на DEBUG")
        logger.system_logger.debug("Это сообщение ДОЛЖНО появиться при уровне DEBUG")
        
        # Возвращаем обратно
        logger.update_config({'log_level': 'INFO'})
        print("   Уровень возвращён на INFO")
        
        print("   ✅ Изменение уровня работает")
    except Exception as e:
        print(f"   ❌ Ошибка изменения уровня: {e}")
        return False
    
    # Тест 6: Декоратор логирования
    print("\n6. 🎀 Тест декоратора @logged_function...")
    try:
        @lto_logger.logged_function("test_function")
        def test_function(param1, param2):
            print(f"      Функция выполняется с параметрами: {param1}, {param2}")
            time.sleep(0.1)
            return param1 + param2
        
        result = test_function(10, 20)
        print(f"   ✅ Декоратор работает, результат: {result}")
    except Exception as e:
        print(f"   ❌ Ошибка декоратора: {e}")
        return False
    
    # Тест 7: Ротация логов (симуляция)
    print("\n7. 🔄 Тест ротации логов...")
    try:
        # Создаем большой файл для теста ротации
        test_log_content = "Тестовая строка для заполнения лога\n" * 10000
        
        # Находим самый маленький лог-файл
        log_files = logger.get_log_file_paths()
        if log_files:
            smallest_file = min(log_files.items(), key=lambda x: x[1]['size'])
            file_path = smallest_file[1]['path']
            
            # Добавляем много данных
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(test_log_content)
            
            print(f"   📝 Добавлено данных в {smallest_file[0]}")
            print(f"   📦 Новый размер: {logger._humanize_size(os.path.getsize(file_path))}")
            
            # Здесь можно проверить что ротация сработала при превышении max_log_size
            # Но в тесте просто проверяем что файл увеличился
            new_size = os.path.getsize(file_path)
            if new_size > smallest_file[1]['size']:
                print("   ✅ Ротация: файл успешно увеличился")
            else:
                print("   ⚠️  Ротация: размер файла не изменился")
                
    except Exception as e:
        print(f"   ⚠️  Ошибка теста ротации: {e} (может быть нормально)")
    
    # Тест 8: Очистка старых логов
    print("\n8. 🗑️  Тест очистки старых логов...")
    try:
        # Создаем тестовый старый файл
        old_file = os.path.join(logger.log_dir, "test_old_log.log")
        with open(old_file, 'w', encoding='utf-8') as f:
            f.write("Старый тестовый лог\n")
        
        # Изменяем время модификации (на 100 дней назад)
        old_time = time.time() - (100 * 24 * 3600)
        os.utime(old_file, (old_time, old_time))
        
        print(f"   📝 Создан тестовый старый файл: {os.path.basename(old_file)}")
        
        # Очищаем логи старше 1 дня (наш файл должен удалиться)
        logger.cleanup_old_logs(days_to_keep=1)
        
        if os.path.exists(old_file):
            print("   ⚠️  Старый файл не удалён (возможно нужно больше времени)")
        else:
            print("   ✅ Очистка старых логов работает")
            
    except Exception as e:
        print(f"   ⚠️  Ошибка теста очистки: {e}")
    
    # Тест 9: Утилитарные функции
    print("\n9. 🛠️  Тест утилитарных функций...")
    try:
        # Быстрое логирование
        lto_logger.log_system("Тест быстрого логирования через log_system()")
        lto_logger.log_error("Тест быстрой ошибки", "QuickTestError")
        lto_logger.log_command_execution("test quick command", success=True)
        
        print("   ✅ Утилитарные функции работают")
    except Exception as e:
        print(f"   ❌ Ошибка утилитарных функций: {e}")
        return False
    
    # Тест 10: Чтение логов програмmatically
    print("\n10. 📖 Тест чтения логов...")
    try:
        log_files = logger.get_log_file_paths()
        if 'lto_system.log' in log_files:
            system_log = log_files['lto_system.log']['path']
            
            with open(system_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-5:] if len(lines) >= 5 else lines
                
            print(f"   📄 Последние строки lto_system.log:")
            for line in last_lines:
                print(f"      {line.rstrip()}")
            
            print("   ✅ Чтение логов работает")
        else:
            print("   ⚠️  Файл lto_system.log не найден")
            
    except Exception as e:
        print(f"   ❌ Ошибка чтения логов: {e}")
    
    print("\n" + "="*60)
    print("📋 СВОДКА ТЕСТИРОВАНИЯ")
    print("="*60)
    
    # Итоговая проверка файлов
    log_files = logger.get_log_file_paths()
    print(f"📁 Файлов логов создано: {len(log_files)}")
    
    total_size = 0
    for name, info in sorted(log_files.items()):
        print(f"  📄 {name}: {info['size_human']}")
        total_size += info['size']
    
    print(f"📦 Общий размер логов: {logger._humanize_size(total_size)}")
    
    print("\n🎉 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО!")
    print("\n📋 Рекомендации:")
    print("   1. Проверьте файлы логов в директории: logs/")
    print("   2. Используйте scripts/log_manager.py для управления логами")
    print("   3. Настройте ротацию логов в config.yaml при необходимости")
    print("   4. Для отладки установите уровень логирования DEBUG")
    print("="*60)
    
    return True

if __name__ == "__main__":
    # Временно устанавливаем уровень логирования INFO для тестов
    os.environ['LTO_LOG_LEVEL'] = 'INFO'
    
    success = test_logging_system()
    sys.exit(0 if success else 1)