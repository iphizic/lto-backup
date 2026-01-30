#!/usr/bin/env python3
"""
Менеджер реестра бэкапов с резервным копированием и восстановлением
"""

import os
import csv
import json
import hashlib
import configparser
from datetime import datetime
from pathlib import Path
import logging
import shutil
from typing import List, Dict, Any, Optional, Tuple

# Импортируем наши модули
from .file_utils import SafeFileHandler

# Настройка логирования
logger = logging.getLogger('registry_manager')

class RegistryManager:
    """Управление реестром бэкапов"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Инициализация менеджера реестра
        
        Args:
            config_path: Путь к файлу конфигурации
        """
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        
        self.config_path = config_path
        self._load_config()
        
        self.registry_file = self.config.get('database', {}).get('registry_file', 'backup_registry.csv')
        self.backup_dir = self._ensure_backup_dir()
        self.manifest_dir = self.config.get('database', {}).get('manifest_dir', './manifests')
        
    def _load_config(self):
        """Загрузка конфигурации из YAML файла"""
        try:
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            self.config = {}
    
    def _ensure_backup_dir(self) -> str:
        """Создаёт директорию для резервных копий реестра"""
        backup_dir = os.path.join(os.path.dirname(self.registry_file), "registry_backups")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
        return backup_dir
    
    def backup_registry(self) -> bool:
        """
        Создаёт резервную копию реестра
        
        Returns:
            True если успешно
        """
        if not os.path.exists(self.registry_file):
            logger.warning("Файл реестра не существует, резервная копия не создана")
            return False
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(self.backup_dir, f"registry_{timestamp}.csv")
        
        try:
            # Копируем реестр
            shutil.copy2(self.registry_file, backup_file)
            
            # Также сохраняем JSON версию для удобства
            json_file = backup_file.replace('.csv', '.json')
            self._export_to_json(json_file)
            
            # Удаляем старые резервные копии (оставляем последние 10)
            self._cleanup_old_backups()
            
            logger.info(f"Резервная копия реестра создана: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            return False
    
    def _cleanup_old_backups(self, keep_last: int = 10):
        """Удаляет старые резервные копии, оставляя только keep_last последних"""
        try:
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith("registry_") and file.endswith(".csv"):
                    file_path = os.path.join(self.backup_dir, file)
                    backups.append((file_path, os.path.getmtime(file_path)))
            
            # Сортируем по дате (старые сначала)
            backups.sort(key=lambda x: x[1])
            
            # Удаляем старые, оставляя только keep_last
            for i in range(len(backups) - keep_last):
                old_file = backups[i][0]
                try:
                    os.remove(old_file)
                    # Удаляем соответствующий JSON файл
                    json_file = old_file.replace('.csv', '.json')
                    if os.path.exists(json_file):
                        os.remove(json_file)
                    logger.debug(f"Удалена старая резервная копия: {old_file}")
                except Exception as e:
                    logger.error(f"Ошибка удаления старой копии {old_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка очистки старых бэкапов: {e}")
    
    def _export_to_json(self, json_file: str):
        """Экспортирует реестр в JSON формат"""
        try:
            entries = []
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                for row in reader:
                    if len(row) >= 5:
                        entry = {
                            'timestamp': row[0],
                            'label': row[1],
                            'tapes': row[2],
                            'file_index': row[3],
                            'manifest': row[4]
                        }
                        entries.append(entry)
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Ошибка экспорта в JSON: {e}")
    
    def verify_registry(self) -> Tuple[bool, List[str]]:
        """
        Проверяет целостность реестра
        
        Returns:
            (успех, список проблем)
        """
        issues = []
        
        if not os.path.exists(self.registry_file):
            return False, ["Файл реестра не существует"]
        
        try:
            # Читаем с использованием SafeFileHandler для корректной кодировки
            lines = SafeFileHandler.read_lines(self.registry_file, skip_empty=True)
                
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split(';')
                
                # Проверка количества полей
                if len(parts) < 5:
                    issues.append(f"Строка {line_num}: недостаточно полей ({len(parts)} вместо 5)")
                    continue
                
                # Проверка существования манифеста
                manifest_file = parts[4].strip()
                if not os.path.exists(manifest_file):
                    issues.append(f"Строка {line_num}: файл манифеста не найден: {manifest_file}")
                
                # Проверка формата метки
                label = parts[1]
                if not label or len(label) < 1:
                    issues.append(f"Строка {line_num}: пустая метка")
                
                # Проверка file_index (должен быть числом)
                try:
                    int(parts[3])
                except ValueError:
                    issues.append(f"Строка {line_num}: неверный file_index: {parts[3]}")
            
            if issues:
                return False, issues
            else:
                return True, ["Реестр проверен успешно"]
                
        except Exception as e:
            return False, [f"Ошибка чтения реестра: {str(e)}"]
    
    def find_backup_by_label(self, label: str) -> Optional[Dict[str, Any]]:
        """
        Поиск бэкапа по метке в реестре
        
        Args:
            label: Метка бэкапа
            
        Returns:
            Информация о бэкапе или None если не найден
        """
        if not os.path.exists(self.registry_file):
            logger.error("Файл реестра не существует")
            return None
        
        try:
            lines = SafeFileHandler.read_lines(self.registry_file, skip_empty=True)
            
            for line_num, line in enumerate(lines, 1):
                if label in line:
                    parts = line.strip().split(';')
                    if len(parts) >= 5:
                        return {
                            'line_number': line_num,
                            'timestamp': parts[0],
                            'label': parts[1],
                            'tapes': parts[2],
                            'file_index': parts[3],
                            'manifest': parts[4],
                            'raw_line': line.strip()
                        }
        except Exception as e:
            logger.error(f"Ошибка поиска в реестре: {e}")
        
        return None
    
    def search_in_manifests(self, label: str) -> List[Dict[str, Any]]:
        """
        Поиск бэкапа по метке в файлах манифестов
        
        Args:
            label: Метка для поиска
            
        Returns:
            Список найденных бэкапов
        """
        if not os.path.exists(self.manifest_dir):
            logger.error(f"Директория манифестов не существует: {self.manifest_dir}")
            return []
        
        found_files = []
        
        try:
            for manifest_file in Path(self.manifest_dir).glob("*.txt"):
                if label.lower() in manifest_file.name.lower():
                    # Пытаемся извлечь информацию из имени файла
                    filename = manifest_file.name
                    # Формат: YYYYMMDD_HHMM_label.txt
                    if '_' in filename:
                        parts = filename.split('_')
                        if len(parts) >= 3:
                            date_part = f"{parts[0]}_{parts[1]}"
                            label_from_file = '_'.join(parts[2:]).replace('.txt', '')
                            
                            found_files.append({
                                'manifest': str(manifest_file),
                                'label': label_from_file,
                                'date': date_part,
                                'type': 'manifest_only'
                            })
        
        except Exception as e:
            logger.error(f"Ошибка поиска в манифестах: {e}")
        
        return found_files
    
    def recover_registry_from_backup(self) -> bool:
        """
        Восстановление реестра из резервной копии
        
        Returns:
            True если успешно
        """
        if not os.path.exists(self.backup_dir):
            logger.error("Директория с резервными копиями не существует")
            return False
        
        try:
            # Ищем последнюю резервную копию
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith("registry_") and file.endswith(".csv"):
                    file_path = os.path.join(self.backup_dir, file)
                    backups.append((file_path, os.path.getmtime(file_path)))
            
            if not backups:
                logger.error("Резервные копии не найдены")
                return False
            
            # Берём самую свежую
            backups.sort(key=lambda x: x[1], reverse=True)
            latest_backup = backups[0][0]
            
            # Восстанавливаем
            shutil.copy2(latest_backup, self.registry_file)
            logger.info(f"Реестр восстановлен из резервной копии: {latest_backup}")
            
            # Создаём новую резервную копию после восстановления
            self.backup_registry()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка восстановления реестра: {e}")
            return False
    
    def interactive_recovery(self) -> bool:
        """
        Интерактивное восстановление реестра
        
        Returns:
            True если восстановление успешно
        """
        print("\n" + "="*60)
        print("🔄 ИНТЕРАКТИВНОЕ ВОССТАНОВЛЕНИЕ РЕЕСТРА")
        print("="*60)
        
        # Проверяем текущий реестр
        is_valid, issues = self.verify_registry()
        
        if is_valid:
            print("✅ Текущий реестр в порядке")
            return True
        
        print("❌ Проблемы с реестром:")
        for issue in issues:
            print(f"   • {issue}")
        
        print("\n📋 Доступные опции:")
        print("1. Восстановить из автоматической резервной копии")
        print("2. Поиск бэкапов по метке в файлах манифестов")
        print("3. Создать новый реестр из найденных манифестов")
        print("4. Восстановить вручную из бэкапа ленты")
        print("5. Выход")
        
        try:
            choice = input("\nВыберите опцию (1-5): ").strip()
            
            if choice == "1":
                success = self.recover_registry_from_backup()
                if success:
                    print("✅ Реестр восстановлен из резервной копии")
                    return True
                else:
                    print("❌ Не удалось восстановить из резервной копии")
                    
            elif choice == "2":
                label = input("Введите метку для поиска: ").strip()
                found = self.search_in_manifests(label)
                if found:
                    print(f"\nНайдено {len(found)} бэкапов:")
                    for i, item in enumerate(found, 1):
                        print(f"{i}. {item['label']} - {item['date']}")
                        print(f"   Манифест: {item['manifest']}")
                else:
                    print("❌ Бэкапы с такой меткой не найдены")
                    
            elif choice == "3":
                self.rebuild_registry_from_manifests()
                print("✅ Реестр перестроен из манифестов")
                return True
                
            elif choice == "4":
                print("\n⚠️  Ручное восстановление из ленты:")
                print("1. Вставьте нужную ленту")
                print("2. Запустите восстановление с указанием file index")
                print("3. После восстановления добавьте запись в реестр вручную")
                input("\nНажмите Enter для продолжения...")
                
            elif choice == "5":
                print("Выход...")
                return False
                
            else:
                print("❌ Неверный выбор")
                
        except KeyboardInterrupt:
            print("\n\n⚠️ Прервано пользователем")
            return False
        
        return False
    
    def rebuild_registry_from_manifests(self) -> bool:
        """
        Перестроение реестра из файлов манифестов
        
        Returns:
            True если успешно
        """
        if not os.path.exists(self.manifest_dir):
            print(f"❌ Директория манифестов не существует: {self.manifest_dir}")
            return False
        
        print("🔍 Сканирование манифестов...")
        
        entries = []
        manifest_files = list(Path(self.manifest_dir).glob("*.txt"))
        
        if not manifest_files:
            print("❌ Файлы манифестов не найдены")
            return False
        
        for manifest_file in manifest_files:
            try:
                filename = manifest_file.name
                # Парсим имя файла: YYYYMMDD_HHMM_label.txt
                if '_' in filename and filename.endswith('.txt'):
                    name_without_ext = filename[:-4]
                    parts = name_without_ext.split('_')
                    
                    if len(parts) >= 3:
                        date_str = f"{parts[0]}_{parts[1]}"
                        label = '_'.join(parts[2:])
                        
                        # Создаём запись
                        entry = {
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'label': label,
                            'tapes': "[N/A]",
                            'file_index': "0",
                            'manifest': str(manifest_file)
                        }
                        entries.append(entry)
                        
            except Exception as e:
                print(f"⚠️ Ошибка обработки файла {manifest_file}: {e}")
        
        if not entries:
            print("❌ Не удалось извлечь информацию из манифестов")
            return False
        
        # Сохраняем новый реестр
        try:
            # Создаём резервную копию старого реестра
            if os.path.exists(self.registry_file):
                backup_name = f"{self.registry_file}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.registry_file, backup_name)
                print(f"📦 Старый реестр сохранён как: {backup_name}")
            
            # Записываем новый реестр
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                for entry in entries:
                    line = f"{entry['timestamp']};{entry['label']};{entry['tapes']};{entry['file_index']};{entry['manifest']}\n"
                    f.write(line)
            
            print(f"✅ Создан новый реестр с {len(entries)} записями")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка записи реестра: {e}")
            return False
    
    def add_registry_entry(self, entry: Dict[str, str]) -> bool:
        """
        Добавление записи в реестр
        
        Args:
            entry: Словарь с данными записи
            
        Returns:
            True если успешно
        """
        try:
            # Форматируем строку
            line = f"{entry.get('timestamp', '')};{entry.get('label', '')};"
            line += f"{entry.get('tapes', '')};{entry.get('file_index', '')};"
            line += f"{entry.get('manifest', '')}"
            
            # Добавляем запись
            with open(self.registry_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            
            logger.info(f"Добавлена запись в реестр: {entry.get('label', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления записи в реестр: {e}")
            return False
    
    def get_all_backups(self) -> List[Dict[str, Any]]:
        """
        Получение всех записей из реестра
        
        Returns:
            Список всех бэкапов
        """
        if not os.path.exists(self.registry_file):
            return []
        
        backups = []
        try:
            lines = SafeFileHandler.read_lines(self.registry_file, skip_empty=True)
            
            for line_num, line in enumerate(lines, 1):
                parts = line.strip().split(';')
                if len(parts) >= 5:
                    backup = {
                        'line_number': line_num,
                        'timestamp': parts[0],
                        'label': parts[1],
                        'tapes': parts[2],
                        'file_index': parts[3],
                        'manifest': parts[4]
                    }
                    backups.append(backup)
                    
        except Exception as e:
            logger.error(f"Ошибка чтения реестра: {e}")
        
        return backups
    
    def cleanup_old_backups_from_registry(self, max_age_days: int = 365) -> int:
        """
        Очистка старых записей из реестра
        
        Args:
            max_age_days: Максимальный возраст записей в днях
            
        Returns:
            Количество удаленных записей
        """
        backups = self.get_all_backups()
        if not backups:
            return 0
        
        cutoff_date = datetime.now().timestamp() - (max_age_days * 86400)
        kept_backups = []
        removed_count = 0
        
        for backup in backups:
            try:
                # Парсим дату из timestamp
                backup_date = datetime.strptime(backup['timestamp'], "%Y-%m-%d %H:%M:%S")
                if backup_date.timestamp() > cutoff_date:
                    kept_backups.append(backup)
                else:
                    removed_count += 1
            except ValueError:
                # Если не удалось распарсить дату, оставляем запись
                kept_backups.append(backup)
        
        # Перезаписываем реестр только с актуальными записями
        if removed_count > 0:
            try:
                # Создаем резервную копию перед очисткой
                self.backup_registry()
                
                # Записываем обновленный реестр
                with open(self.registry_file, 'w', encoding='utf-8') as f:
                    for backup in kept_backups:
                        line = f"{backup['timestamp']};{backup['label']};"
                        line += f"{backup['tapes']};{backup['file_index']};"
                        line += f"{backup['manifest']}\n"
                        f.write(line)
                
                logger.info(f"Очищен реестр: удалено {removed_count} старых записей")
                
            except Exception as e:
                logger.error(f"Ошибка очистки реестра: {e}")
                return 0
        
        return removed_count

# Глобальные утилиты
def get_registry_manager(config_path: Optional[str] = None) -> RegistryManager:
    """
    Получение экземпляра менеджера реестра
    
    Args:
        config_path: Путь к конфигурационному файлу
        
    Returns:
        Экземпляр RegistryManager
    """
    return RegistryManager(config_path)

def emergency_recovery() -> bool:
    """
    Экстренное восстановление реестра
    
    Returns:
        True если восстановление успешно
    """
    manager = get_registry_manager()
    return manager.interactive_recovery()

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Тестирование функционала
    import sys
    
    manager = RegistryManager()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--verify":
            is_valid, issues = manager.verify_registry()
            if is_valid:
                print("✅ Реестр валиден")
            else:
                print("❌ Проблемы с реестром:")
                for issue in issues:
                    print(f"  • {issue}")
                    
        elif sys.argv[1] == "--backup":
            success = manager.backup_registry()
            if success:
                print("✅ Резервная копия создана")
            else:
                print("❌ Не удалось создать резервную копию")
                
        elif sys.argv[1] == "--recover":
            success = manager.interactive_recovery()
            if success:
                print("✅ Восстановление завершено")
            else:
                print("❌ Восстановление не удалось")
                
        elif sys.argv[1] == "--rebuild":
            success = manager.rebuild_registry_from_manifests()
            if success:
                print("✅ Реестр перестроен")
            else:
                print("❌ Не удалось перестроить реестр")
                
        elif sys.argv[1] == "--list":
            backups = manager.get_all_backups()
            if backups:
                print(f"📋 Найдено {len(backups)} бэкапов:")
                for backup in backups[-10:]:  # Последние 10
                    print(f"  • {backup['label']} - {backup['timestamp']}")
            else:
                print("📭 Бэкапы не найдены")
                
        elif sys.argv[1] == "--cleanup":
            removed = manager.cleanup_old_backups_from_registry(30)
            print(f"🗑️  Удалено {removed} старых записей")
    else:
        print("Использование:")
        print("  python3 registry_manager.py --verify")
        print("  python3 registry_manager.py --backup")
        print("  python3 registry_manager.py --recover")
        print("  python3 registry_manager.py --rebuild")
        print("  python3 registry_manager.py --list")
        print("  python3 registry_manager.py --cleanup")