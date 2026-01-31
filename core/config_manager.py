import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

class ConfigManager:
    """Менеджер конфигурации с поддержкой YAML"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = self._resolve_config_path(config_path)
        self.config = self._load_config()
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
    
    def _resolve_config_path(self, config_path: Optional[str]) -> Path:
        """Определить путь к конфигурационному файлу"""
        search_paths = []
        
        if config_path:
            search_paths.append(Path(config_path))
        
        # Стандартные пути поиска
        search_paths.extend([
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path(__file__).parent.parent / "config.yaml",
            Path.home() / ".config" / "lto_backup" / "config.yaml",
            Path("/etc") / "lto_backup" / "config.yaml",
        ])
        
        for path in search_paths:
            if path.exists():
                self.logger.info(f"Найден файл конфигурации: {path}")
                return path.resolve()
        
        # Если файл не найден, создаем в текущей директории
        default_path = Path.cwd() / "config.yaml"
        self._create_default_config(default_path)
        return default_path
    
    def _create_default_config(self, config_path: Path) -> None:
        """Создать конфигурацию по умолчанию"""
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
            },
            'paths': {
                'important_dirs': ['/etc', '/home', '/var/www', '/var/lib'],
                'excluded_dirs': ['/var/tmp', '/var/cache']
            },
            'scheduling': {
                'enabled': False,
                'daily_at': '02:00',
                'weekly_day': 'sunday',
                'monthly_day': 1,
                'retention_policy': {
                    'daily': 7,
                    'weekly': 4,
                    'monthly': 12
                }
            },
            'performance': {
                'tar_threads': 2,
                'io_buffer_size': '64M',
                'use_direct_io': True,
                'sync_after_write': True
            },
            'monitoring': {
                'disk_space_warning': 10,
                'tape_usage_warning': 90,
                'email_alerts': False,
                'email_to': 'admin@example.com'
            },
            'logging': {
                'file': '/var/log/lto_backup.log',
                'max_size': '100M',
                'backup_count': 5,
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'date_format': '%Y-%m-%d %H:%M:%S'
            },
            'security': {
                'encrypt_backups': False,
                'gpg_key': '',
                'hash_verification': True,
                'hash_algorithm': 'sha256'
            },
            'notifications': {
                'sound_alerts': True,
                'desktop_notifications': False,
                'syslog_integration': True
            }
        }
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True, indent=2)
        
        self.logger.info(f"Создан файл конфигурации по умолчанию: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузить конфигурацию из YAML файла"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config:
                raise ValueError("Конфигурационный файл пуст")
            
            self.logger.info(f"Конфигурация загружена из {self.config_path}")
            return config
            
        except yaml.YAMLError as e:
            self.logger.error(f"Ошибка синтаксиса YAML: {e}")
            raise ValueError(f"Ошибка синтаксиса YAML: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {e}")
            raise ValueError(f"Ошибка загрузки конфигурации: {e}")
    
    def _setup_logging(self) -> None:
        """Настроить логирование на основе конфигурации"""
        log_config = self.config.get('logging', {})
        
        log_level = getattr(logging, self.get('common', 'log_level', 'INFO').upper(), logging.INFO)
        
        # Базовые настройки
        logging.basicConfig(
            level=log_level,
            format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            datefmt=log_config.get('date_format', '%Y-%m-%d %H:%M:%S')
        )
        
        # Файловый обработчик
        log_file = log_config.get('file')
        if log_file:
            try:
                from logging.handlers import RotatingFileHandler
                
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=self._parse_size(log_config.get('max_size', '100M')),
                    backupCount=log_config.get('backup_count', 5)
                )
                file_handler.setLevel(log_level)
                file_handler.setFormatter(
                    logging.Formatter(
                        log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                        datefmt=log_config.get('date_format', '%Y-%m-%d %H:%M:%S')
                    )
                )
                logging.getLogger().addHandler(file_handler)
                self.logger.info(f"Логирование в файл: {log_file}")
            except Exception as e:
                self.logger.error(f"Ошибка настройки файлового логирования: {e}")
    
    def _parse_size(self, size_str: str) -> int:
        """Преобразовать строку размера в байты"""
        size_str = size_str.strip().upper()
        
        multipliers = {
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }
        
        if size_str[-1] in multipliers:
            number = float(size_str[:-1])
            multiplier = multipliers[size_str[-1]]
            return int(number * multiplier)
        else:
            return int(size_str)
    
    def _parse_time(self, time_str: str) -> timedelta:
        """Преобразовать строку времени в timedelta"""
        time_str = time_str.strip().lower()
        
        multipliers = {
            's': 1,
            'm': 60,
            'h': 60 * 60,
            'd': 24 * 60 * 60,
            'w': 7 * 24 * 60 * 60
        }
        
        if time_str[-1] in multipliers:
            number = int(time_str[:-1])
            multiplier = multipliers[time_str[-1]]
            return timedelta(seconds=number * multiplier)
        else:
            return timedelta(seconds=int(time_str))
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Получить значение из конфигурации"""
        try:
            keys = [section] + key.split('.')
            value = self.config
            
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
            
            return value if value is not None else default
            
        except (KeyError, AttributeError):
            return default
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Получить всю секцию конфигурации"""
        return self.config.get(section, {})
    
    def get_telegram_enabled(self) -> bool:
        """Проверить, включены ли уведомления Telegram"""
        return self.get('telegram', 'enabled', False)
    
    def get_exclude_patterns(self) -> List[str]:
        """Получить список паттернов для исключения"""
        return self.get('exclude', 'patterns', [])
    
    def get_mbuffer_params(self) -> Dict[str, str]:
        """Получить параметры mbuffer"""
        return {
            'size': self.get('mbuffer', 'size', '2G'),
            'fill_percent': self.get('mbuffer', 'fill_percent', '90%'),
            'block_size': self.get('mbuffer', 'block_size', '256k'),
            'change_script': self.get('mbuffer', 'change_script', 'lto_backup change_tape'),
            'min_rate': self.get('mbuffer', 'min_rate', '100M'),
            'max_rate': self.get('mbuffer', 'max_rate', '150M')
        }
    
    def get_backup_params(self) -> Dict[str, Any]:
        """Получить параметры бэкапа"""
        return {
            'compression': self.get('backup', 'compression', 'none'),
            'verify_after_backup': self.get('backup', 'verify_after_backup', True),
            'create_manifest': self.get('backup', 'create_manifest', True),
            'max_file_size': self._parse_size(self.get('backup', 'max_file_size', '100G')),
            'split_large_files': self.get('backup', 'split_large_files', True)
        }
    
    def get_hardware_params(self) -> Dict[str, Any]:
        """Получить параметры оборудования"""
        return {
            'has_robot': self.get('hardware', 'has_robot', False),
            'robot_dev': self.get('hardware', 'robot_dev', '/dev/sg3'),
            'tape_dev': self.get('hardware', 'tape_dev', '/dev/nst0'),
            'err_threshold': self.get('hardware', 'err_threshold', 50),
            'auto_rewind': self.get('hardware', 'auto_rewind', True)
        }
    
    def get_scheduling_params(self) -> Dict[str, Any]:
        """Получить параметры планировщика"""
        return self.get_section('scheduling')
    
    def get_performance_params(self) -> Dict[str, Any]:
        """Получить параметры производительности"""
        return self.get_section('performance')
    
    def get_security_params(self) -> Dict[str, Any]:
        """Получить параметры безопасности"""
        return self.get_section('security')
    
    def save(self) -> None:
        """Сохранить конфигурацию в файл"""
        config_dir = self.config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, indent=2)
        
        self.logger.info(f"Конфигурация сохранена в {self.config_path}")
    
    def update(self, section: str, key: str, value: Any) -> None:
        """Обновить значение в конфигурации"""
        keys = [section] + key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def validate(self) -> List[str]:
        """Проверить валидность конфигурации"""
        errors = []
        
        # Проверка обязательных полей
        required_fields = [
            ('hardware', 'tape_dev'),
            ('mbuffer', 'size'),
            ('mbuffer', 'block_size'),
        ]
        
        for section, key in required_fields:
            if not self.get(section, key):
                errors.append(f"Отсутствует обязательное поле: {section}.{key}")
        
        # Проверка Telegram настроек если включен
        if self.get_telegram_enabled():
            token = self.get('telegram', 'token')
            chat_id = self.get('telegram', 'chat_id')
            
            if not token or token == 'YOUR_BOT_TOKEN_HERE':
                errors.append("Telegram token не настроен")
            if not chat_id or chat_id == 'YOUR_CHAT_ID_HERE':
                errors.append("Telegram chat_id не настроен")
        
        # Проверка существования устройства ленты
        tape_dev = self.get('hardware', 'tape_dev')
        if tape_dev and not Path(tape_dev).exists():
            errors.append(f"Устройство ленты не найдено: {tape_dev}")
        
        # Проверка правильности размера буфера
        try:
            buffer_size = self.get('mbuffer', 'size')
            self._parse_size(buffer_size)
        except:
            errors.append(f"Некорректный размер буфера: {buffer_size}")
        
        # Проверка уровня логирования
        log_level = self.get('common', 'log_level', 'INFO').upper()
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if log_level not in valid_log_levels:
            errors.append(f"Некорректный уровень логирования: {log_level}")
        
        return errors