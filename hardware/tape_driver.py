import subprocess
import re
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class TapeDriver:
    """Драйвер для управления ленточным накопителем"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        hardware_params = config.get_hardware_params()
        
        self.tape_dev = hardware_params['tape_dev']
        self.has_robot = hardware_params['has_robot']
        self.robot_dev = hardware_params['robot_dev']
        self.err_threshold = hardware_params['err_threshold']
        self.auto_rewind = hardware_params['auto_rewind']
        
        self.tmp_tapes_file = "/tmp/current_backup_tapes.txt"
        self.last_clean_file = "/tmp/last_clean_time.txt"
        self.tape_stats_file = "/tmp/tape_statistics.json"
        
        # Инициализируем временные файлы
        self._init_temp_files()
        
        logger.info(f"Инициализирован драйвер ленты для устройства: {self.tape_dev}")
        if self.has_robot:
            logger.info(f"Автоматический робот: {self.robot_dev}")
    
    def _init_temp_files(self) -> None:
        """Инициализировать временные файлы"""
        for file_path in [self.tmp_tapes_file, self.last_clean_file, self.tape_stats_file]:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            if not Path(file_path).exists():
                Path(file_path).touch()
    
    def run_command(self, cmd: str, timeout: int = 30) -> Tuple[str, str, int]:
        """Выполнить системную команду с таймаутом"""
        try:
            result = subprocess.run(
                cmd, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут выполнения команды: {cmd}")
            return "", "Command timeout", 124
        except Exception as e:
            logger.error(f"Ошибка выполнения команды {cmd}: {e}")
            return "", str(e), 1
    
    def beep(self) -> None:
        """Подать звуковой сигнал"""
        sound_enabled = self.config.get('notifications', 'sound_alerts', True)
        
        if sound_enabled:
            print('\a', end='', flush=True)
            
            # Альтернативные методы звукового сигнала
            try:
                subprocess.run(["echo", "-e", "\a"], capture_output=True, check=False)
            except:
                pass
    
    def rewind(self) -> bool:
        """Перемотать ленту к началу"""
        if self.auto_rewind:
            stdout, stderr, code = self.run_command(f"mt -f {self.tape_dev} rewind")
            
            if code == 0:
                logger.info("Лента перемотана к началу")
                return True
            else:
                logger.error(f"Ошибка перемотки ленты: {stderr}")
                return False
        return True
    
    def status(self) -> Dict[str, Any]:
        """Получить подробный статус ленты"""
        status_info = {}
        
        # Базовая команда статуса
        stdout, stderr, code = self.run_command(f"mt -f {self.tape_dev} status")
        
        if code == 0:
            # Парсим вывод команды mt
            patterns = {
                'file_number': r"file number=([0-9]+)",
                'block_number': r"block number=([0-9]+)",
                'partition': r"partition=([0-9]+)",
                'density': r"density code=([0-9x]+)",
                'soft_errors': r"soft errors=([0-9]+)",
                'general_status': r"general status bits.*?\((.*?)\)"
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, stdout, re.IGNORECASE)
                if match:
                    status_info[key] = match.group(1)
            
            # Проверка на ошибки
            if "ONLINE" in stdout:
                status_info['online'] = True
            else:
                status_info['online'] = False
            
            # Проверка на чистку
            stdout_clean, _, _ = self.run_command(f"tapeinfo -f {self.tape_dev}")
            status_info['cleaning_needed'] = "Cleaning bit: yes" in stdout_clean
            
            # Получение информации о емкости
            if self._supports_tapeinfo():
                stdout_cap, _, _ = self.run_command(f"tapeinfo -f {self.tape_dev} | grep -i capacity")
                if stdout_cap:
                    match = re.search(r"([0-9.]+)\s*(GB|TB|MB)", stdout_cap)
                    if match:
                        status_info['capacity'] = f"{match.group(1)} {match.group(2)}"
        else:
            logger.error(f"Ошибка получения статуса ленты: {stderr}")
            status_info['error'] = stderr
        
        return status_info
    
    def _supports_tapeinfo(self) -> bool:
        """Проверить поддержку команды tapeinfo"""
        stdout, stderr, code = self.run_command("which tapeinfo")
        return code == 0
    
    def get_file_number(self) -> str:
        """Получить текущий номер файла на ленте"""
        status = self.status()
        return status.get('file_number', '0')
    
    def forward_space_files(self, count: int) -> bool:
        """Перемотать вперед на указанное количество файлов"""
        stdout, stderr, code = self.run_command(f"mt -f {self.tape_dev} fsf {count}")
        
        if code == 0:
            logger.info(f"Перемотано вперед на {count} файлов")
            return True
        else:
            logger.error(f"Ошибка перемотки вперед: {stderr}")
            return False
    
    def check_cleaning_needed(self) -> bool:
        """Проверить, требуется ли чистка"""
        status = self.status()
        return status.get('cleaning_needed', False)
    
    def request_tape_change(self, current_label: Optional[str] = None) -> str:
        """Запросить смену ленты у оператора"""
        sound_enabled = self.config.get('notifications', 'sound_alerts', True)
        
        if sound_enabled:
            self.beep()
        
        print("\n" + "=" * 50)
        print("🔔 ТРЕБУЕТСЯ СМЕНА ЛЕНТЫ LTO")
        print("=" * 50)
        
        if current_label:
            print(f"📼 Текущая лента: {current_label}")
        
        # Запрашиваем метку новой ленты
        while True:
            label = input("📝 Введите метку следующей кассеты: ").strip()
            
            if label:
                # Сохраняем информацию о ленте
                with open(self.tmp_tapes_file, "a") as f:
                    f.write(f"{label} ")
                
                logger.info(f"Запрошена лента с меткой: {label}")
                return label
            else:
                print("❌ Метка не может быть пустой. Попробуйте еще раз.")
    
    def record_cleaning_time(self) -> None:
        """Записать время последней чистки"""
        clean_time = datetime.now().isoformat()
        
        try:
            stats = {}
            
            if Path(self.tape_stats_file).exists():
                with open(self.tape_stats_file, 'r') as f:
                    stats = json.load(f)
            
            stats['last_cleaning'] = clean_time
            stats['cleaning_count'] = stats.get('cleaning_count', 0) + 1
            
            with open(self.tape_stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
            
            # Также сохраняем в простом текстовом формате для совместимости
            with open(self.last_clean_file, "w") as f:
                f.write(clean_time)
            
            logger.info(f"Записано время чистки: {clean_time}")
            
        except Exception as e:
            logger.error(f"Ошибка записи времени чистки: {e}")
    
    def get_last_clean_time(self) -> str:
        """Получить время последней чистки"""
        try:
            if Path(self.tape_stats_file).exists():
                with open(self.tape_stats_file, 'r') as f:
                    stats = json.load(f)
                    last_clean = stats.get('last_cleaning', '')
                    
                    if last_clean:
                        clean_dt = datetime.fromisoformat(last_clean)
                        return clean_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # Запасной вариант - текстовый файл
            if Path(self.last_clean_file).exists():
                with open(self.last_clean_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        try:
                            clean_dt = datetime.fromisoformat(content)
                            return clean_dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            return content
            
        except Exception as e:
            logger.error(f"Ошибка чтения времени чистки: {e}")
        
        return "Нет данных"
    
    def get_used_tapes(self) -> str:
        """Получить список использованных лент"""
        try:
            if Path(self.tmp_tapes_file).exists():
                with open(self.tmp_tapes_file, "r") as f:
                    tapes = f.read().strip()
                    if tapes:
                        # Убираем дубликаты и сортируем
                        tape_list = list(set(tapes.split()))
                        tape_list.sort()
                        return " ".join(tape_list)
        except Exception as e:
            logger.error(f"Ошибка чтения списка лент: {e}")
        
        return "N/A"
    
    def clear_temp_files(self) -> None:
        """Очистить временные файлы"""
        try:
            for file_path in [self.tmp_tapes_file, self.last_clean_file]:
                if Path(file_path).exists():
                    Path(file_path).unlink()
            
            # Файл статистики не удаляем, только очищаем текущие ленты
            if Path(self.tmp_tapes_file).exists():
                Path(self.tmp_tapes_file).touch()
            
            self._init_temp_files()
            logger.info("Временные файлы очищены")
            
        except Exception as e:
            logger.error(f"Ошибка очистки временных файлов: {e}")
    
    def get_tape_statistics(self) -> Dict[str, Any]:
        """Получить статистику использования лент"""
        try:
            if Path(self.tape_stats_file).exists():
                with open(self.tape_stats_file, 'r') as f:
                    return json.load(f)
            
        except Exception as e:
            logger.error(f"Ошибка чтения статистики: {e}")
        
        return {
            'backup_count': 0,
            'cleaning_count': 0,
            'last_cleaning': '',
            'total_data_written': '0 GB'
        }