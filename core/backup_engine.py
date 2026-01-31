import subprocess
import os
import signal
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from core.config_manager import ConfigManager
from core.registry_manager import RegistryManager
from hardware.tape_driver import TapeDriver
from notification.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

class BackupEngine:
    """Движок для выполнения операций резервного копирования"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.tape_driver = TapeDriver(config)
        self.registry = RegistryManager(config)
        self.bot = TelegramBot(config)
        
        # Обработка прерываний
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        
        logger.info("Инициализирован движок резервного копирования")
    
    def _handle_interrupt(self, signum, frame):
        """Обработка прерывания"""
        logger.warning(f"Получен сигнал прерывания {signum}")
        self.bot.send_message(f"⚠️ Операция прервана сигналом {signum}")
        raise KeyboardInterrupt
    
    def create_manifest_path(self, label: str) -> str:
        """Создать путь для файла манифеста"""
        manifest_dir = self.config.get('common', 'manifest_dir')
        Path(manifest_dir).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_label = "".join(c for c in label if c.isalnum() or c in ('_', '-'))
        return str(Path(manifest_dir) / f"{timestamp}_{safe_label}.txt")
    
    def build_exclude_list(self) -> List[str]:
        """Построить список исключений для tar"""
        exclude_str = self.config.get('exclude', 'patterns', [])
        return exclude_str
    
    def build_tar_command(self, source: str, manifest: str, block_size: str) -> str:
        """Построить команду tar для архивации"""
        excludes = self.build_exclude_list()
        exclude_args = " ".join([f'--exclude="{pattern}"' for pattern in excludes])
        
        backup_params = self.config.get_backup_params()
        compression = backup_params.get('compression', 'none')
        
        # Добавляем параметры сжатия если нужно
        compression_args = ""
        if compression != 'none':
            compression_args = f"--{compression}"
        
        return (
            f"tar -cv {exclude_args} {compression_args} "
            f"--record-size={block_size} "
            f"--index-file={manifest} "
            f"{source}"
        )
    
    def build_mbuffer_command(self, block_size: str, change_script: str) -> str:
        """Построить команду mbuffer для буферизации"""
        mbuffer_params = self.config.get_mbuffer_params()
        
        buffer_size = mbuffer_params['size']
        fill_percent = mbuffer_params['fill_percent']
        min_rate = mbuffer_params.get('min_rate', '100M')
        max_rate = mbuffer_params.get('max_rate', '150M')
        tape_dev = self.config.get('hardware', 'tape_dev')
        
        performance_params = self.config.get_performance_params()
        use_direct_io = performance_params.get('use_direct_io', True)
        
        direct_io_arg = "-D" if use_direct_io else ""
        
        return (
            f"mbuffer -m {buffer_size} "
            f"-P {fill_percent} "
            f"-b {block_size} "
            f"-n 0 -f {direct_io_arg} "
            f"-A '{change_script}' "
            f"-o {tape_dev}"
        )
    
    def estimate_backup_size(self, source: str) -> str:
        """Оценить размер бэкапа"""
        try:
            # Используем du для оценки размера
            cmd = f"du -sb {source} 2>/dev/null | cut -f1"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                size_bytes = int(result.stdout.strip())
                
                # Преобразуем в читаемый формат
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if size_bytes < 1024.0:
                        return f"{size_bytes:.1f} {unit}"
                    size_bytes /= 1024.0
                
                return f"{size_bytes:.1f} PB"
            else:
                return "Неизвестно"
                
        except Exception as e:
            logger.warning(f"Не удалось оценить размер бэкапа: {e}")
            return "Неизвестно"
    
    def backup(self, source_path: str, label: str) -> bool:
        """Выполнить резервное копирование"""
        start_time = datetime.now()
        
        try:
            # Очистка временных файлов
            self.tape_driver.clear_temp_files()
            
            # Проверка необходимости чистки
            if self.tape_driver.check_cleaning_needed():
                self.bot.send_cleaning_request()
                logger.warning("Требуется чистка ленты перед началом бэкапа")
            
            # Создание пути для манифеста
            manifest_path = self.create_manifest_path(label)
            
            # Получение параметров конфигурации
            mbuffer_params = self.config.get_mbuffer_params()
            block_size = mbuffer_params['block_size']
            change_script = mbuffer_params['change_script']
            
            # Оценка размера бэкапа
            size_estimate = self.estimate_backup_size(source_path)
            
            # Построение команд
            tar_cmd = self.build_tar_command(source_path, manifest_path, block_size)
            mbuffer_cmd = self.build_mbuffer_command(block_size, change_script)
            
            # Полная команда для выполнения
            full_cmd = f"{tar_cmd} | {mbuffer_cmd} 2>&1"
            
            print("=" * 60)
            print(f"🚀 Начало бэкапа: {label}")
            print(f"📁 Источник: {source_path}")
            print(f"📊 Оценка размера: {size_estimate}")
            print(f"📝 Манифест: {manifest_path}")
            print("=" * 60)
            
            # Отправка уведомления
            self.bot.send_backup_started(label, source_path, size_estimate)
            
            # Выполнение команды
            logger.info(f"Выполнение команды бэкапа: {label}")
            proc = subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Вывод прогресса в реальном времени
            for line in proc.stdout:
                print(line, end='')
            
            proc.wait()
            
            end_time = datetime.now()
            duration = end_time - start_time
            
            if proc.returncode == 0:
                self._finalize_backup(label, manifest_path, duration, size_estimate)
                return True
            else:
                error_msg = f"Код ошибки: {proc.returncode}"
                logger.error(f"Ошибка бэкапа {label}: {error_msg}")
                self.bot.send_backup_failed(label, error_msg, proc.returncode)
                return False
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Критическая ошибка при бэкапе {label}: {error_msg}")
            self.bot.send_backup_failed(label, error_msg)
            return False
    
    def _finalize_backup(self, label: str, manifest_path: str, duration, size_estimate: str) -> None:
        """Завершить бэкап и обновить реестр"""
        # Получение информации о лентах
        tapes = self.tape_driver.get_used_tapes()
        clean_time = self.tape_driver.get_last_clean_time()
        file_number = self.tape_driver.get_file_number()
        
        # Форматирование длительности
        duration_str = str(duration).split('.')[0]  # Убираем микросекунды
        
        # Отправка уведомления о завершении
        self.bot.send_backup_completed(label, tapes, file_number, duration_str, size_estimate, clean_time)
        
        # Обновление реестра
        self.registry.add_backup(label, tapes, file_number, manifest_path)
        
        print("\n" + "=" * 60)
        print(f"✅ Бэкап '{label}' успешно завершен")
        print(f"📼 Использованные ленты: {tapes}")
        print(f"🔢 Номер файла: {file_number}")
        print(f"⏱️  Длительность: {duration_str}")
        print(f"📊 Оценка размера: {size_estimate}")
        print("=" * 60)
        
        logger.info(f"Бэкап {label} завершен успешно")
    
    def restore(self, destination_path: str, label: str) -> bool:
        """Восстановить данные из резервной копии"""
        start_time = datetime.now()
        
        try:
            # Создание директории назначения
            Path(destination_path).mkdir(parents=True, exist_ok=True)
            
            # Поиск бэкапа в реестре
            backup_info = self.registry.find_backup(label)
            
            if not backup_info:
                error_msg = f"Бэкап с меткой '{label}' не найден"
                print(f"❌ {error_msg}")
                self.bot.send_message(f"❌ Бэкап `{label}` не найден в реестре")
                return False
            
            # Позиционирование ленты
            print(f"🔍 Найден бэкап: {label}")
            print(f"📼 Ленты: {backup_info['tapes']}")
            print(f"🔢 Позиция файла: {backup_info['file_number']}")
            
            self.tape_driver.rewind()
            
            if backup_info['file_number'].isdigit():
                file_num = int(backup_info['file_number'])
                if file_num > 0:
                    print(f"⏩ Перематывание к файлу {file_num}...")
                    self.tape_driver.forward_space_files(file_num)
            
            # Отправка уведомления о начале восстановления
            self.bot.send_restore_started(label, destination_path)
            
            # Получение параметров для восстановления
            mbuffer_params = self.config.get_mbuffer_params()
            block_size = mbuffer_params['block_size']
            change_script = mbuffer_params['change_script']
            tape_dev = self.config.get('hardware', 'tape_dev')
            
            # Команда восстановления
            restore_cmd = (
                f"mbuffer -i {tape_dev} "
                f"-m 1G -b {block_size} -n 0 "
                f"-A '{change_script}' | "
                f"tar -xvM --record-size={block_size} -f - -C {destination_path}"
            )
            
            print(f"📥 Начало восстановления...")
            logger.info(f"Начало восстановления {label} в {destination_path}")
            
            # Выполнение восстановления
            result = subprocess.run(
                restore_cmd,
                shell=True,
                capture_output=True,
                text=True
            )
            
            end_time = datetime.now()
            duration = end_time - start_time
            
            if result.returncode == 0:
                # Подсчет восстановленных файлов
                file_count = 0
                try:
                    # Простой подсчет по выводу tar
                    file_count = len([line for line in result.stdout.split('\n') 
                                    if line and not line.startswith('tar:')])
                except:
                    pass
                
                print(f"✅ Восстановление '{label}' завершено")
                print(f"📁 Назначение: {destination_path}")
                print(f"⏱️  Длительность: {str(duration).split('.')[0]}")
                
                self.bot.send_restore_completed(label, destination_path, file_count)
                logger.info(f"Восстановление {label} завершено успешно")
                return True
            else:
                error_msg = result.stderr[:200] if result.stderr else "Неизвестная ошибка"
                print(f"❌ Ошибка восстановления")
                print(f"stderr: {error_msg}")
                
                self.bot.send_error(label, f"Ошибка восстановления: {error_msg}")
                logger.error(f"Ошибка восстановления {label}: {error_msg}")
                return False
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Критическая ошибка при восстановлении: {error_msg}")
            self.bot.send_error(label, error_msg)
            logger.error(f"Критическая ошибка при восстановлении {label}: {error_msg}")
            return False