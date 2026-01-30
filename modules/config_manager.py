#!/usr/bin/env python3
"""
Менеджер конфигурации с поддержкой YAML и JSON
Валидация схемы, работа только с YAML/JSON форматами
"""

import os
import sys
import json
import yaml
import logging
from typing import Dict, Any, Optional, Union
from pathlib import Path
import jsonschema
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger('config_manager')

class ConfigFormat(Enum):
    """Форматы конфигурации"""
    YAML = "yaml"
    JSON = "json"

@dataclass
class DatabaseConfig:
    """Конфигурация базы данных/реестра"""
    registry_file: str = "backup_registry.csv"
    manifest_dir: str = "./manifests"
    backup_dir: str = "./backups"
    log_dir: str = "./logs"
    cache_dir: str = "./cache"

@dataclass
class HardwareConfig:
    """Конфигурация оборудования"""
    tape_device: str = "/dev/nst0"
    robot_enabled: bool = False
    robot_device: str = "/dev/sg3"
    error_threshold: int = 50
    auto_clean: bool = True
    clean_interval_hours: int = 24

@dataclass
class BufferConfig:
    """Конфигурация буферизации"""
    size: str = "2G"
    fill_percent: str = "90%"
    block_size: str = "256k"
    auto_adjust: bool = True
    min_size: str = "512M"
    max_size: str = "4G"

@dataclass
class NotificationConfig:
    """Конфигурация уведомлений"""
    telegram_enabled: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    email_enabled: bool = False
    email_smtp_server: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_recipients: list = None
    
    def __post_init__(self):
        if self.email_recipients is None:
            self.email_recipients = []

@dataclass
class BackupConfig:
    """Конфигурация бэкапа"""
    default_excludes: list = None
    compress_before_backup: bool = False
    encryption_enabled: bool = False
    encryption_key: str = ""
    verify_after_backup: bool = True
    max_backup_age_days: int = 365
    retention_policy: str = "yearly"
    
    def __post_init__(self):
        if self.default_excludes is None:
            self.default_excludes = [
                "/proc", "/sys", "/dev", "/run", "/tmp",
                "*.log", "*.tmp", "*.temp", "*.cache"
            ]

@dataclass
class LoggingConfig:
    """Конфигурация логирования"""
    level: str = "INFO"
    console_enabled: bool = True
    file_enabled: bool = True
    max_file_size: int = 10485760
    backup_count: int = 7
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"

class LTOConfig:
    """Основной класс конфигурации LTO системы"""
    
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "database": {
                "type": "object",
                "properties": {
                    "registry_file": {"type": "string"},
                    "manifest_dir": {"type": "string"},
                    "backup_dir": {"type": "string"},
                    "log_dir": {"type": "string"},
                    "cache_dir": {"type": "string"}
                },
                "required": ["registry_file", "manifest_dir"]
            },
            "hardware": {
                "type": "object",
                "properties": {
                    "tape_device": {"type": "string"},
                    "robot_enabled": {"type": "boolean"},
                    "robot_device": {"type": "string"},
                    "error_threshold": {"type": "integer", "minimum": 0, "maximum": 100},
                    "auto_clean": {"type": "boolean"},
                    "clean_interval_hours": {"type": "integer", "minimum": 1}
                },
                "required": ["tape_device", "robot_enabled"]
            },
            "buffer": {
                "type": "object",
                "properties": {
                    "size": {"type": "string"},
                    "fill_percent": {"type": "string"},
                    "block_size": {"type": "string"},
                    "auto_adjust": {"type": "boolean"},
                    "min_size": {"type": "string"},
                    "max_size": {"type": "string"}
                },
                "required": ["size", "fill_percent", "block_size"]
            },
            "notification": {
                "type": "object",
                "properties": {
                    "telegram_enabled": {"type": "boolean"},
                    "telegram_token": {"type": "string"},
                    "telegram_chat_id": {"type": "string"},
                    "email_enabled": {"type": "boolean"},
                    "email_smtp_server": {"type": "string"},
                    "email_smtp_port": {"type": "integer"},
                    "email_username": {"type": "string"},
                    "email_password": {"type": "string"},
                    "email_recipients": {"type": "array", "items": {"type": "string"}}
                }
            },
            "backup": {
                "type": "object",
                "properties": {
                    "default_excludes": {"type": "array", "items": {"type": "string"}},
                    "compress_before_backup": {"type": "boolean"},
                    "encryption_enabled": {"type": "boolean"},
                    "encryption_key": {"type": "string"},
                    "verify_after_backup": {"type": "boolean"},
                    "max_backup_age_days": {"type": "integer", "minimum": 1},
                    "retention_policy": {"type": "string", "enum": ["yearly", "monthly", "weekly", "daily"]}
                }
            },
            "logging": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
                    "console_enabled": {"type": "boolean"},
                    "file_enabled": {"type": "boolean"},
                    "max_file_size": {"type": "integer"},
                    "backup_count": {"type": "integer"},
                    "format": {"type": "string"},
                    "date_format": {"type": "string"}
                },
                "required": ["level"]
            }
        },
        "required": ["database", "hardware", "buffer"]
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config_data: Dict[str, Any] = {}
        self.config_format: Optional[ConfigFormat] = None
        
        self.database = DatabaseConfig()
        self.hardware = HardwareConfig()
        self.buffer = BufferConfig()
        self.notification = NotificationConfig()
        self.backup = BackupConfig()
        self.logging = LoggingConfig()
        
        if config_path:
            self.load(config_path)
        else:
            self._initialize_defaults()
    
    def _initialize_defaults(self):
        self.config_data = {
            'database': asdict(self.database),
            'hardware': asdict(self.hardware),
            'buffer': asdict(self.buffer),
            'notification': asdict(self.notification),
            'backup': asdict(self.backup),
            'logging': asdict(self.logging)
        }
    
    def load(self, config_path: str) -> bool:
        self.config_path = config_path
        
        if not os.path.exists(config_path):
            logger.error(f"Файл конфигурации не найден: {config_path}")
            return False
        
        ext = Path(config_path).suffix.lower()
        
        if ext in ['.yaml', '.yml']:
            return self._load_yaml(config_path)
        elif ext == '.json':
            return self._load_json(config_path)
        else:
            logger.error(f"Неподдерживаемый формат конфигурации: {ext}. Поддерживаются только YAML и JSON.")
            return False
    
    def _load_yaml(self, config_path: str) -> bool:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f)
            
            self.config_format = ConfigFormat.YAML
            
            if not self._validate_config():
                return False
            
            self._populate_config_objects()
            
            logger.info(f"YAML конфигурация загружена: {config_path}")
            return True
            
        except yaml.YAMLError as e:
            logger.error(f"Ошибка парсинга YAML: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки YAML: {e}")
            return False
    
    def _load_json(self, config_path: str) -> bool:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            
            self.config_format = ConfigFormat.JSON
            
            if not self._validate_config():
                return False
            
            self._populate_config_objects()
            
            logger.info(f"JSON конфигурация загружена: {config_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки JSON: {e}")
            return False
    
    def _populate_config_objects(self):
        if 'database' in self.config_data:
            db_data = self.config_data['database']
            self.database = DatabaseConfig(
                registry_file=db_data.get('registry_file', self.database.registry_file),
                manifest_dir=db_data.get('manifest_dir', self.database.manifest_dir),
                backup_dir=db_data.get('backup_dir', self.database.backup_dir),
                log_dir=db_data.get('log_dir', self.database.log_dir),
                cache_dir=db_data.get('cache_dir', self.database.cache_dir)
            )
        
        if 'hardware' in self.config_data:
            hw_data = self.config_data['hardware']
            self.hardware = HardwareConfig(
                tape_device=hw_data.get('tape_device', self.hardware.tape_device),
                robot_enabled=hw_data.get('robot_enabled', self.hardware.robot_enabled),
                robot_device=hw_data.get('robot_device', self.hardware.robot_device),
                error_threshold=hw_data.get('error_threshold', self.hardware.error_threshold),
                auto_clean=hw_data.get('auto_clean', self.hardware.auto_clean),
                clean_interval_hours=hw_data.get('clean_interval_hours', self.hardware.clean_interval_hours)
            )
        
        if 'buffer' in self.config_data:
            buf_data = self.config_data['buffer']
            self.buffer = BufferConfig(
                size=buf_data.get('size', self.buffer.size),
                fill_percent=buf_data.get('fill_percent', self.buffer.fill_percent),
                block_size=buf_data.get('block_size', self.buffer.block_size),
                auto_adjust=buf_data.get('auto_adjust', self.buffer.auto_adjust),
                min_size=buf_data.get('min_size', self.buffer.min_size),
                max_size=buf_data.get('max_size', self.buffer.max_size)
            )
        
        if 'notification' in self.config_data:
            notif_data = self.config_data['notification']
            self.notification = NotificationConfig(
                telegram_enabled=notif_data.get('telegram_enabled', self.notification.telegram_enabled),
                telegram_token=notif_data.get('telegram_token', self.notification.telegram_token),
                telegram_chat_id=notif_data.get('telegram_chat_id', self.notification.telegram_chat_id),
                email_enabled=notif_data.get('email_enabled', self.notification.email_enabled),
                email_smtp_server=notif_data.get('email_smtp_server', self.notification.email_smtp_server),
                email_smtp_port=notif_data.get('email_smtp_port', self.notification.email_smtp_port),
                email_username=notif_data.get('email_username', self.notification.email_username),
                email_password=notif_data.get('email_password', self.notification.email_password),
                email_recipients=notif_data.get('email_recipients', self.notification.email_recipients)
            )
        
        if 'backup' in self.config_data:
            backup_data = self.config_data['backup']
            self.backup = BackupConfig(
                default_excludes=backup_data.get('default_excludes', self.backup.default_excludes),
                compress_before_backup=backup_data.get('compress_before_backup', self.backup.compress_before_backup),
                encryption_enabled=backup_data.get('encryption_enabled', self.backup.encryption_enabled),
                encryption_key=backup_data.get('encryption_key', self.backup.encryption_key),
                verify_after_backup=backup_data.get('verify_after_backup', self.backup.verify_after_backup),
                max_backup_age_days=backup_data.get('max_backup_age_days', self.backup.max_backup_age_days),
                retention_policy=backup_data.get('retention_policy', self.backup.retention_policy)
            )
        
        if 'logging' in self.config_data:
            log_data = self.config_data['logging']
            self.logging = LoggingConfig(
                level=log_data.get('level', self.logging.level),
                console_enabled=log_data.get('console_enabled', self.logging.console_enabled),
                file_enabled=log_data.get('file_enabled', self.logging.file_enabled),
                max_file_size=log_data.get('max_file_size', self.logging.max_file_size),
                backup_count=log_data.get('backup_count', self.logging.backup_count),
                format=log_data.get('format', self.logging.format),
                date_format=log_data.get('date_format', self.logging.date_format)
            )
    
    def _validate_config(self) -> bool:
        try:
            jsonschema.validate(instance=self.config_data, schema=self.CONFIG_SCHEMA)
            return True
        except jsonschema.ValidationError as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при валидации: {e}")
            return False
    
    def save(self, config_path: Optional[str] = None, 
             format: ConfigFormat = ConfigFormat.YAML) -> bool:
        if config_path:
            self.config_path = config_path
        elif not self.config_path:
            logger.error("Не указан путь для сохранения конфигурации")
            return False
        
        self._update_config_data()
        
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            
            if format == ConfigFormat.YAML:
                return self._save_yaml()
            elif format == ConfigFormat.JSON:
                return self._save_json()
            else:
                logger.error(f"Неподдерживаемый формат: {format}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка сохранения конфигурации: {e}")
            return False
    
    def _update_config_data(self):
        self.config_data = {
            'database': asdict(self.database),
            'hardware': asdict(self.hardware),
            'buffer': asdict(self.buffer),
            'notification': asdict(self.notification),
            'backup': asdict(self.backup),
            'logging': asdict(self.logging)
        }
        
        for section in self.config_data:
            self.config_data[section] = {
                k: v for k, v in self.config_data[section].items() 
                if v not in [None, '', [], {}]
            }
    
    def _save_yaml(self) -> bool:
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, 
                         allow_unicode=True, indent=2, sort_keys=False)
            
            logger.info(f"Конфигурация сохранена в YAML: {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения YAML: {e}")
            return False
    
    def _save_json(self) -> bool:
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Конфигурация сохранена в JSON: {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения JSON: {e}")
            return False
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        if section in self.config_data and key in self.config_data[section]:
            return self.config_data[section][key]
        return default
    
    def set(self, section: str, key: str, value: Any):
        if section not in self.config_data:
            self.config_data[section] = {}
        
        self.config_data[section][key] = value
        
        self._update_config_object(section, key, value)
    
    def _update_config_object(self, section: str, key: str, value: Any):
        if section == 'database' and hasattr(self.database, key):
            setattr(self.database, key, value)
        elif section == 'hardware' and hasattr(self.hardware, key):
            setattr(self.hardware, key, value)
        elif section == 'buffer' and hasattr(self.buffer, key):
            setattr(self.buffer, key, value)
        elif section == 'notification' and hasattr(self.notification, key):
            setattr(self.notification, key, value)
        elif section == 'backup' and hasattr(self.backup, key):
            setattr(self.backup, key, value)
        elif section == 'logging' and hasattr(self.logging, key):
            setattr(self.logging, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        self._update_config_data()
        return self.config_data.copy()
    
    def validate_and_fix(self) -> bool:
        try:
            self._ensure_directories()
            self._validate_devices()
            self._validate_parameters()
            return self._validate_config()
            
        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False
    
    def _ensure_directories(self):
        directories = [
            self.database.manifest_dir,
            self.database.backup_dir,
            self.database.log_dir,
            self.database.cache_dir
        ]
        
        for directory in directories:
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Создана директория: {directory}")
    
    def _validate_devices(self):
        if not os.path.exists(self.hardware.tape_device):
            logger.warning(f"Ленточное устройство не найдено: {self.hardware.tape_device}")
        
        if self.hardware.robot_enabled and not os.path.exists(self.hardware.robot_device):
            logger.warning(f"Устройство робота не найдено: {self.hardware.robot_device}")
    
    def _validate_parameters(self):
        import re
        size_pattern = r'^(\d+)([KMGTP]?)$'
        
        for size_param in ['size', 'min_size', 'max_size']:
            size_value = getattr(self.buffer, size_param, '')
            if not re.match(size_pattern, size_value.upper()):
                logger.warning(f"Некорректный размер буфера: {size_value}")
                setattr(self.buffer, size_param, '2G')

def create_default_config(config_path: str, format: ConfigFormat = ConfigFormat.YAML) -> bool:
    try:
        config = LTOConfig()
        return config.save(config_path, format)
    except Exception as e:
        logger.error(f"Ошибка создания конфигурации по умолчанию: {e}")
        return False

def get_config_instance(config_path: Optional[str] = None) -> LTOConfig:
    if config_path is None:
        possible_paths = [
            'config.yaml',
            'config.yml', 
            'config.json',
            '/etc/lto-backup/config.yaml',
            '/etc/lto-backup/config.json'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if config_path is None:
            config_path = 'config.yaml'
            logger.info(f"Конфигурация не найдена, создаю по умолчанию: {config_path}")
            create_default_config(config_path)
    
    return LTOConfig(config_path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    print("🧪 Тестирование config_manager.py")
    print("=" * 60)
    
    config = LTOConfig()
    print(f"✅ Конфигурация создана")
    print(f"📁 Database: {config.database.manifest_dir}")
    print(f"📼 Hardware: {config.hardware.tape_device}")
    print(f"📦 Buffer: {config.buffer.size}")
    
    print("\n✅ Тестирование завершено")