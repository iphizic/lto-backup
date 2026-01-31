import csv
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class RegistryManager:
    """Менеджер реестра бэкапов"""
    
    def __init__(self, config):
        self.config = config
        self.registry_file = config.get('common', 'registry_csv')
        self.stats_file = Path(self.registry_file).with_suffix('.json')
        self._ensure_registry_exists()
        self._load_stats()
    
    def _ensure_registry_exists(self):
        """Убедиться, что файл реестра существует"""
        if not os.path.exists(self.registry_file):
            Path(self.registry_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_file, 'w', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow([
                    'timestamp', 'label', 'tapes', 
                    'file_number', 'manifest_path', 'size_estimate'
                ])
            logger.info(f"Создан новый реестр: {self.registry_file}")
    
    def _load_stats(self):
        """Загрузить статистику"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    self.stats = json.load(f)
            except:
                self.stats = {}
        else:
            self.stats = {}
    
    def _save_stats(self):
        """Сохранить статистику"""
        with open(self.stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
    
    def add_backup(self, label: str, tapes: str, file_number: str, 
                  manifest_path: str, size_estimate: str = "") -> None:
        """Добавить запись о бэкапе в реестр"""
        timestamp = datetime.now().isoformat()
        
        with open(self.registry_file, 'a', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([
                timestamp,
                label,
                tapes,
                file_number,
                manifest_path,
                size_estimate
            ])
        
        # Обновляем статистику
        self.stats['total_backups'] = self.stats.get('total_backups', 0) + 1
        self.stats['last_backup'] = timestamp
        self.stats['last_backup_label'] = label
        
        # Увеличиваем счетчик лент
        if tapes != "N/A":
            tape_list = tapes.split()
            self.stats['total_tapes_used'] = self.stats.get('total_tapes_used', 0) + len(tape_list)
        
        self._save_stats()
        logger.info(f"Добавлен бэкап в реестр: {label}")
    
    def find_backup(self, label: str) -> Optional[Dict[str, str]]:
        """Найти информацию о бэкапе по метке"""
        if not os.path.exists(self.registry_file):
            return None
        
        with open(self.registry_file, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                if row['label'] == label:
                    return row
        
        return None
    
    def list_backups(self) -> List[Dict[str, str]]:
        """Получить список всех бэкапов"""
        if not os.path.exists(self.registry_file):
            return []
        
        backups = []
        with open(self.registry_file, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                backups.append(row)
        
        return backups
    
    def delete_backup(self, label: str) -> bool:
        """Удалить запись о бэкапе из реестра"""
        if not os.path.exists(self.registry_file):
            return False
        
        # Читаем все записи кроме удаляемой
        backups = []
        deleted = False
        
        with open(self.registry_file, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            fieldnames = reader.fieldnames
            
            for row in reader:
                if row['label'] != label:
                    backups.append(row)
                else:
                    deleted = True
        
        # Если ничего не удалили, возвращаем False
        if not deleted:
            return False
        
        # Перезаписываем файл
        with open(self.registry_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(backups)
        
        logger.info(f"Удален бэкап из реестра: {label}")
        return True
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Получить статистику бэкапов"""
        backups = self.list_backups()
        
        return {
            'total_backups': len(backups),
            'oldest_backup': min(backups, key=lambda x: x['timestamp'])['timestamp'] if backups else None,
            'newest_backup': max(backups, key=lambda x: x['timestamp'])['timestamp'] if backups else None,
            'unique_labels': len(set(b['label'] for b in backups)),
            'tapes_used': self.stats.get('total_tapes_used', 0)
        }
    
    def cleanup_old_backups(self, retention_days: int = 90) -> int:
        """Очистить старые записи из реестра"""
        if retention_days <= 0:
            return 0
        
        if not os.path.exists(self.registry_file):
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        kept_backups = []
        deleted_count = 0
        
        with open(self.registry_file, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            fieldnames = reader.fieldnames
            
            for row in reader:
                try:
                    backup_date = datetime.fromisoformat(row['timestamp'])
                    if backup_date >= cutoff_date:
                        kept_backups.append(row)
                    else:
                        deleted_count += 1
                except:
                    kept_backups.append(row)
        
        # Перезаписываем файл
        with open(self.registry_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(kept_backups)
        
        if deleted_count > 0:
            logger.info(f"Удалено {deleted_count} старых записей из реестра")
        
        return deleted_count