#!/usr/bin/env python3
"""
Централизованная система логирования для LTO Backup System
Поддерживает ротацию логов, разные уровни и форматы
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import configparser
import traceback
from typing import Optional, Dict, Any

# Уровни логирования для удобства
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

class LTOLogger:
    """Класс для управления логированием LTO системы"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LTOLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.config = self._load_config()
        self.log_dir = self._ensure_log_dir()
        self._setup_loggers()
        self._initialized = True
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации логирования"""
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        
        # Пытаемся загрузить из YAML
        try:
            import yaml
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                
                if 'logging' in yaml_config:
                    log_config = yaml_config['logging']
                    return {
                        'log_level': log_config.get('level', 'INFO'),
                        'log_to_console': str(log_config.get('console_enabled', True)).lower(),
                        'log_to_file': str(log_config.get('file_enabled', True)).lower(),
                        'max_log_size': str(log_config.get('max_file_size', 10485760)),
                        'backup_count': str(log_config.get('backup_count', 7)),
                        'log_format': log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                        'date_format': log_config.get('date_format', '%Y-%m-%d %H:%M:%S')
                    }
        except Exception as e:
            print(f"⚠️ Не удалось загрузить конфигурацию из YAML: {e}")
        
        # Значения по умолчанию
        defaults = {
            'log_level': 'INFO',
            'log_to_console': 'yes',
            'log_to_file': 'yes',
            'max_log_size': '10485760',
            'backup_count': '7',
            'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'date_format': '%Y-%m-%d %H:%M:%S'
        }
        
        return defaults
    
    def _ensure_log_dir(self) -> str:
        """Создание и настройка директории для логов"""
        # Пытаемся получить из конфигурации
        log_dir = './logs'
        
        # Проверяем конфигурацию YAML
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                
                if 'database' in yaml_config and 'log_dir' in yaml_config['database']:
                    log_dir = yaml_config['database']['log_dir']
            except Exception:
                pass
        
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, mode=0o750, exist_ok=True)
                self._log_to_console(f"Создана директория для логов: {log_dir}")
            except Exception as e:
                print(f"❌ Не удалось создать директорию логов: {e}")
                log_dir = os.path.dirname(__file__)
        
        return log_dir
    
    def _log_to_console(self, message: str, level: str = "INFO"):
        """Временное логирование в консоль до инициализации логгеров"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def _setup_loggers(self):
        """Настройка всех логгеров"""
        
        # Основной логгер системы
        self.system_logger = self._create_logger(
            name='lto_system',
            filename='lto_system.log',
            level=self.config['log_level']
        )
        
        # Логгер ошибок
        self.error_logger = self._create_logger(
            name='lto_errors',
            filename='lto_errors.log',
            level='ERROR',
            propagate=False
        )
        
        # Логгер отладки (если нужно)
        self.debug_logger = self._create_logger(
            name='lto_debug',
            filename='lto_debug.log',
            level='DEBUG',
            propagate=False
        )
        
        # Логгер работы с лентой
        self.tape_logger = self._create_logger(
            name='lto_tape',
            filename='lto_tape.log',
            level=self.config['log_level']
        )
        
        # Логгер производительности
        self.perf_logger = self._create_logger(
            name='lto_performance',
            filename='lto_performance.log',
            level='INFO'
        )
        
        # Настраиваем корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.WARNING)
        
        # Записываем событие инициализации
        self.system_logger.info(f"Система логирования инициализирована. Логи в: {self.log_dir}")
        self.system_logger.info(f"Уровень логирования: {self.config['log_level']}")
    
    def _create_logger(self, name: str, filename: str, level: str = 'INFO', 
                      propagate: bool = True) -> logging.Logger:
        """
        Создание и настройка логгера
        
        Args:
            name: Имя логгера
            filename: Имя файла лога
            level: Уровень логирования
            propagate: Передавать ли сообщения родительским логгерам
        """
        logger = logging.getLogger(name)
        logger.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))
        logger.propagate = propagate
        
        # Очищаем существующие обработчики
        logger.handlers.clear()
        
        # Форматтер
        formatter = logging.Formatter(
            fmt=self.config['log_format'],
            datefmt=self.config['date_format']
        )
        
        # Обработчик для файла
        if self.config.get('log_to_file', 'yes').lower() == 'yes':
            log_file = os.path.join(self.log_dir, filename)
            
            # Ротация по размеру
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=int(self.config['max_log_size']),
                backupCount=int(self.config['backup_count']),
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))
            logger.addHandler(file_handler)
        
        # Обработчик для консоли
        if self.config.get('log_to_console', 'yes').lower() == 'yes':
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))
            logger.addHandler(console_handler)
        
        return logger
    
    def log_command(self, command: str, success: bool = True, 
                   details: str = "", execution_time: float = None):
        """
        Логирование выполнения команды
        
        Args:
            command: Выполненная команда
            success: Успешно ли выполнена
            details: Детали выполнения
            execution_time: Время выполнения в секундах
        """
        status = "✅ УСПЕХ" if success else "❌ ОШИБКА"
        
        log_message = f"{status}: {command}"
        if details:
            log_message += f" | {details}"
        if execution_time is not None:
            log_message += f" | Время: {execution_time:.2f}с"
        
        if success:
            self.system_logger.info(log_message)
        else:
            self.system_logger.error(log_message)
            self.error_logger.error(log_message)
        
        # Логируем производительность если указано время
        if execution_time is not None and execution_time > 1.0:
            self.perf_logger.info(f"Команда '{command[:50]}...' выполнена за {execution_time:.2f}с")
    
    def log_backup_start(self, source: str, label: str):
        """Логирование начала бэкапа"""
        message = f"🚀 НАЧАЛО БЭКАПА: '{label}' | Источник: {source}"
        self.system_logger.info(message)
        self.tape_logger.info(f"Бэкап начат: {label}")
    
    def log_backup_complete(self, label: str, tapes: list, file_index: str, 
                          total_size: str = None, duration: float = None):
        """Логирование завершения бэкапа"""
        tapes_str = ', '.join(tapes) if tapes else "N/A"
        
        message = f"✅ БЭКАП ЗАВЕРШЕН: '{label}' | Ленты: [{tapes_str}] | FileIdx: {file_index}"
        if total_size:
            message += f" | Размер: {total_size}"
        if duration:
            message += f" | Время: {duration:.1f} мин"
        
        self.system_logger.info(message)
        self.tape_logger.info(f"Бэкап завершен: {label}, ленты: {tapes_str}")
        
        if duration:
            self.perf_logger.info(f"Бэкап '{label}' выполнен за {duration:.1f} мин")
    
    def log_restore_start(self, label: str, destination: str):
        """Логирование начала восстановления"""
        message = f"🔄 НАЧАЛО ВОССТАНОВЛЕНИЯ: '{label}' -> {destination}"
        self.system_logger.info(message)
        self.tape_logger.info(f"Восстановление начато: {label}")
    
    def log_restore_complete(self, label: str, destination: str, 
                           success: bool = True, details: str = ""):
        """Логирование завершения восстановления"""
        status = "✅ УСПЕХ" if success else "❌ ОШИБКА"
        message = f"{status} ВОССТАНОВЛЕНИЯ: '{label}' -> {destination}"
        if details:
            message += f" | {details}"
        
        if success:
            self.system_logger.info(message)
            self.tape_logger.info(f"Восстановление завершено: {label}")
        else:
            self.system_logger.error(message)
            self.error_logger.error(message)
            self.tape_logger.error(f"Ошибка восстановления: {label}")
    
    def log_tape_event(self, event: str, tape_label: str = "", 
                      details: str = "", is_error: bool = False):
        """Логирование событий работы с лентой"""
        message = f"📼 {event}"
        if tape_label:
            message += f": {tape_label}"
        if details:
            message += f" | {details}"
        
        if is_error:
            self.tape_logger.error(message)
            self.error_logger.error(message)
        else:
            self.tape_logger.info(message)
    
    def log_clean_event(self, drive_status: str, manual_mode: bool = False):
        """Логирование событий чистки"""
        mode = "РУЧНОЙ" if manual_mode else "АВТОМАТ"
        message = f"🧼 ЗАПРОС ЧИСТКИ | Режим: {mode} | Статус: {drive_status}"
        self.system_logger.warning(message)
        self.tape_logger.warning(message)
    
    def log_error(self, error_type: str, error_msg: str, 
                 traceback_info: str = None, context: str = ""):
        """
        Логирование ошибок с трейсбэком
        
        Args:
            error_type: Тип ошибки (например, 'IOError', 'ConfigError')
            error_msg: Сообщение об ошибке
            traceback_info: Информация о стеке вызовов
            context: Контекст возникновения ошибки
        """
        # Основное сообщение
        message = f"💥 {error_type}: {error_msg}"
        if context:
            message += f" | Контекст: {context}"
        
        # Логируем
        self.system_logger.error(message)
        self.error_logger.error(message)
        
        # Добавляем трейсбэк если есть
        if traceback_info:
            self.error_logger.error(f"Трейсбэк:\n{traceback_info}")
    
    def log_debug(self, module: str, message: str, data: Any = None):
        """
        Отладочное логирование
        
        Args:
            module: Модуль/компонент
            message: Отладочное сообщение
            data: Дополнительные данные для логирования
        """
        debug_msg = f"[{module}] {message}"
        if data is not None:
            # Ограничиваем вывод больших структур
            if isinstance(data, (dict, list, tuple)) and len(str(data)) > 500:
                data_str = str(data)[:500] + "... [обрезано]"
            else:
                data_str = str(data)
            debug_msg += f" | Данные: {data_str}"
        
        self.debug_logger.debug(debug_msg)
    
    def log_performance(self, operation: str, start_time: float, 
                       end_time: float = None, data_size: int = None):
        """
        Логирование производительности
        
        Args:
            operation: Операция (backup, restore, etc.)
            start_time: Время начала (timestamp)
            end_time: Время окончания (timestamp), если None - текущее время
            data_size: Размер данных в байтах
        """
        if end_time is None:
            end_time = datetime.now().timestamp()
        
        duration = end_time - start_time
        
        message = f"⏱️ {operation}: {duration:.2f}с"
        if data_size is not None:
            speed = data_size / duration if duration > 0 else 0
            speed_mb = speed / (1024 * 1024)
            message += f" | Размер: {data_size / (1024*1024):.1f}МБ | Скорость: {speed_mb:.1f} МБ/с"
        
        self.perf_logger.info(message)
    
    def get_log_file_paths(self) -> Dict[str, str]:
        """Получение путей ко всем файлам логов"""
        log_files = {}
        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log'):
                full_path = os.path.join(self.log_dir, filename)
                if os.path.isfile(full_path):
                    size = os.path.getsize(full_path)
                    log_files[filename] = {
                        'path': full_path,
                        'size': size,
                        'size_human': self._humanize_size(size)
                    }
        
        return log_files
    
    def _humanize_size(self, size_bytes: int) -> str:
        """Конвертация размера в читаемый формат"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} ТБ"
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """
        Очистка старых лог-файлов
        
        Args:
            days_to_keep: Сколько дней хранить логи
        """
        import time
        
        cutoff_time = time.time() - (days_to_keep * 86400)
        deleted_count = 0
        
        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log'):
                filepath = os.path.join(self.log_dir, filename)
                try:
                    # Удаляем только старые файлы
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        deleted_count += 1
                        self.system_logger.info(f"Удалён старый лог: {filename}")
                except Exception as e:
                    self.log_error('LogCleanupError', f"Не удалось удалить {filename}: {str(e)}")
        
        if deleted_count > 0:
            self.system_logger.info(f"Очистка логов: удалено {deleted_count} файлов старше {days_to_keep} дней")
    
    def update_config(self, new_config: Dict[str, str]):
        """
        Обновление конфигурации логирования на лету
        
        Args:
            new_config: Новые настройки
        """
        self.config.update(new_config)
        self._setup_loggers()
        self.system_logger.info("Конфигурация логирования обновлена")

# Глобальный экземпляр для простого доступа
_logger_instance = None

def get_logger() -> LTOLogger:
    """Получение глобального экземпляра логгера"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = LTOLogger()
    return _logger_instance

# Функции для удобного использования
def log_system(message: str, level: str = "INFO"):
    """Быстрое логирование в системный лог"""
    logger = get_logger()
    log_method = getattr(logger.system_logger, level.lower(), logger.system_logger.info)
    log_method(message)

def log_error(error_msg: str, error_type: str = "GeneralError", traceback_info: str = None):
    """Быстрое логирование ошибки"""
    logger = get_logger()
    logger.log_error(error_type, error_msg, traceback_info)

def log_command_execution(command: str, success: bool = True, details: str = ""):
    """Быстрое логирование выполнения команды"""
    logger = get_logger()
    logger.log_command(command, success, details)

# Декоратор для логирования выполнения функций
def logged_function(func_name: str = None):
    """
    Декоратор для автоматического логирования вызова и завершения функций
    
    Пример использования:
        @logged_function("backup_operation")
        def backup(...):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger()
            name = func_name or func.__name__
            
            # Логируем начало выполнения
            logger.log_debug("decorator", f"Начало выполнения функции: {name}")
            
            try:
                start_time = datetime.now().timestamp()
                result = func(*args, **kwargs)
                end_time = datetime.now().timestamp()
                
                # Логируем успешное завершение
                duration = end_time - start_time
                logger.log_debug("decorator", 
                               f"Функция {name} выполнена успешно за {duration:.2f}с")
                
                return result
                
            except Exception as e:
                # Логируем ошибку
                error_msg = f"Ошибка в функции {name}: {str(e)}"
                logger.log_error(type(e).__name__, error_msg, traceback.format_exc())
                raise
        
        return wrapper
    return decorator

if __name__ == "__main__":
    # Тестирование модуля логирования
    logger = get_logger()
    
    print("🔍 Тестирование системы логирования LTO")
    print(f"📁 Директория логов: {logger.log_dir}")
    
    # Тестовые сообщения
    logger.system_logger.info("Тестовое информационное сообщение")
    logger.system_logger.warning("Тестовое предупреждение")
    logger.system_logger.error("Тестовая ошибка")
    
    logger.log_command("ls -la", success=True, execution_time=0.5)
    logger.log_command("rm -rf /", success=False, details="Permission denied")
    
    logger.log_backup_start("/home/user/data", "TestBackup_2024")
    logger.log_backup_complete("TestBackup_2024", ["LTO001", "LTO002"], "5", 
                             total_size="150 GB", duration=45.5)
    
    logger.log_tape_event("Смена ленты", "LTO003", "Требуется следующая лента")
    logger.log_clean_event("Cleaning bit set", manual_mode=True)
    
    logger.log_error("IOError", "Не удалось прочитать файл", 
                    context="/var/log/system.log")
    
    # Показать файлы логов
    print("\n📊 Файлы логов:")
    for name, info in logger.get_log_file_paths().items():
        print(f"  {name}: {info['size_human']}")
    
    print("\n✅ Тестирование завершено")