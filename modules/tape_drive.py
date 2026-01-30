#!/usr/bin/env python3
"""
Класс для управления ленточным накопителем LTO
Инкапсулирует все операции с лентой: позиционирование, статус, управление
"""

import os
import re
import subprocess
import logging
from typing import Optional, Dict, Any, Tuple, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger('tape_drive')

class TapeStatus(Enum):
    """Статус ленточного накопителя"""
    READY = "ready"
    BUSY = "busy"
    OFFLINE = "offline"
    CLEANING_REQUIRED = "cleaning_required"
    ERROR = "error"
    UNKNOWN = "unknown"

class TapeMode(Enum):
    """Режим работы с лентой"""
    READ = "read"
    WRITE = "write"
    APPEND = "append"
    NO_REWIND = "no_rewind"

@dataclass
class TapeInfo:
    """Информация о ленточном накопителе"""
    device: str
    vendor: str = ""
    product: str = ""
    revision: str = ""
    serial: str = ""
    block_size: int = 0
    density: str = ""
    status: TapeStatus = TapeStatus.UNKNOWN
    file_number: int = 0
    block_number: int = 0
    is_write_protected: bool = False
    cleaning_required: bool = False
    last_error: str = ""

class TapeDrive:
    """Класс для управления ленточным накопителем LTO"""
    
    def __init__(self, device_path: str = "/dev/nst0", 
                 use_no_rewind: bool = True):
        """
        Инициализация ленточного накопителя
        
        Args:
            device_path: Путь к устройству (например /dev/nst0)
            use_no_rewind: Использовать no-rewind устройство
        """
        self.device = device_path
        self.use_no_rewind = use_no_rewind
        self.current_mode: Optional[TapeMode] = None
        self.last_operation_time: Optional[datetime] = None
        self.error_count = 0
        self.max_retries = 3
        
        # Проверяем доступность устройства
        self._validate_device()
    
    def _validate_device(self) -> bool:
        """Проверка доступности устройства"""
        if not os.path.exists(self.device):
            logger.error(f"Устройство не найдено: {self.device}")
            return False
        
        # Проверяем права доступа
        if not os.access(self.device, os.R_OK | os.W_OK):
            logger.error(f"Нет прав доступа к устройству: {self.device}")
            return False
        
        # Проверяем что это ленточное устройство
        try:
            result = subprocess.run(
                ["mt", "-f", self.device, "status"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.error(f"Устройство {self.device} не отвечает на команды mt")
                return False
            
            logger.info(f"Ленточное устройство инициализировано: {self.device}")
            return True
            
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError) as e:
            logger.error(f"Ошибка доступа к устройству {self.device}: {e}")
            return False
    
    def _execute_mt_command(self, command: str, args: str = "", 
                          retry_on_error: bool = True) -> Tuple[bool, str]:
        """
        Выполнение команды mt с обработкой ошибок
        
        Args:
            command: Команда mt (status, rewind, fsf, etc.)
            args: Дополнительные аргументы
            retry_on_error: Повторять при ошибке
            
        Returns:
            (успех, вывод команды)
        """
        full_command = ["mt", "-f", self.device]
        
        if command:
            full_command.append(command)
        
        if args:
            full_command.extend(args.split())
        
        for attempt in range(self.max_retries if retry_on_error else 1):
            try:
                logger.debug(f"Выполнение mt: {' '.join(full_command)} (попытка {attempt+1})")
                
                result = subprocess.run(
                    full_command,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8'
                )
                
                self.last_operation_time = datetime.now()
                
                if result.returncode == 0:
                    return True, result.stdout
                else:
                    error_msg = result.stderr.strip()
                    logger.warning(f"Ошибка mt команды: {error_msg}")
                    
                    if attempt < self.max_retries - 1 and retry_on_error:
                        logger.debug(f"Повтор через 2 секунды...")
                        import time
                        time.sleep(2)
                        continue
                    else:
                        return False, error_msg
                        
            except subprocess.TimeoutExpired:
                error_msg = f"Таймаут выполнения команды mt {command}"
                logger.error(error_msg)
                return False, error_msg
            except Exception as e:
                error_msg = f"Исключение при выполнении mt: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
        
        return False, "Превышено количество попыток"
    
    def get_status(self) -> TapeInfo:
        """
        Получение статуса ленточного накопителя
        
        Returns:
            Объект TapeInfo с информацией о состоянии
        """
        success, output = self._execute_mt_command("status")
        
        info = TapeInfo(device=self.device)
        
        if not success:
            info.status = TapeStatus.ERROR
            info.last_error = output
            return info
        
        # Парсим вывод mt status
        info.vendor = self._extract_from_output(output, r"vendor\s*=\s*(.+)")
        info.product = self._extract_from_output(output, r"product\s*=\s*(.+)")
        info.revision = self._extract_from_output(output, r"revision\s*=\s*(.+)")
        info.serial = self._extract_from_output(output, r"serial\s*=\s*(.+)")
        
        # Парсим file number и block number
        file_match = re.search(r"file number=([0-9]+)", output)
        if file_match:
            info.file_number = int(file_match.group(1))
        
        block_match = re.search(r"block number=([0-9]+)", output)
        if block_match:
            info.block_number = int(block_match.group(1))
        
        # Проверяем write protect
        if "WRITE PROTECT" in output and "ON" in output:
            info.is_write_protected = True
        
        # Проверяем общий статус
        if "ONLINE" in output:
            info.status = TapeStatus.READY
        elif "DR_OPEN" in output or "OFFLINE" in output:
            info.status = TapeStatus.OFFLINE
        else:
            info.status = TapeStatus.UNKNOWN
        
        # Получаем дополнительную информацию через tapeinfo
        try:
            tapeinfo_result = subprocess.run(
                ["tapeinfo", "-f", self.device],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if tapeinfo_result.returncode == 0:
                tapeinfo_output = tapeinfo_result.stdout
                
                # Проверяем cleaning bit
                if "Cleaning bit: yes" in tapeinfo_output:
                    info.cleaning_required = True
                    info.status = TapeStatus.CLEANING_REQUIRED
                
                # Парсим density
                density_match = re.search(r"Density code:\s*([^\n]+)", tapeinfo_output)
                if density_match:
                    info.density = density_match.group(1).strip()
                
                # Парсим block size
                block_match = re.search(r"Block size:\s*([0-9]+)", tapeinfo_output)
                if block_match:
                    info.block_size = int(block_match.group(1))
                    
        except Exception as e:
            logger.debug(f"Не удалось получить tapeinfo: {e}")
        
        return info
    
    def _extract_from_output(self, output: str, pattern: str) -> str:
        """Извлечение значения из вывода команды"""
        match = re.search(pattern, output, re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    def rewind(self) -> bool:
        """
        Перемотка ленты к началу
        
        Returns:
            True если успешно
        """
        logger.info(f"Перемотка ленты: {self.device}")
        success, output = self._execute_mt_command("rewind")
        
        if success:
            logger.debug("Лента перемотана")
        else:
            logger.error(f"Ошибка перемотки: {output}")
        
        return success
    
    def forward_space_file(self, count: int = 1) -> bool:
        """
        Перемещение вперед на указанное количество файлов
        
        Args:
            count: Количество файлов для пропуска
            
        Returns:
            True если успешно
        """
        if count <= 0:
            return True
        
        logger.info(f"Перемещение вперед на {count} файлов")
        success, output = self._execute_mt_command("fsf", str(count))
        
        if success:
            logger.debug(f"Перемещено на {count} файлов")
        else:
            logger.error(f"Ошибка перемещения: {output}")
        
        return success
    
    def backward_space_file(self, count: int = 1) -> bool:
        """
        Перемещение назад на указанное количество файлов
        
        Args:
            count: Количество файлов для перемещения назад
            
        Returns:
            True если успешно
        """
        if count <= 0:
            return True
        
        logger.info(f"Перемещение назад на {count} файлов")
        success, output = self._execute_mt_command("bsf", str(count))
        
        if success:
            logger.debug(f"Перемещено назад на {count} файлов")
        else:
            logger.error(f"Ошибка перемещения назад: {output}")
        
        return success
    
    def seek_to_file(self, file_number: int) -> bool:
        """
        Позиционирование на конкретный файл
        
        Args:
            file_number: Номер файла (0-based)
            
        Returns:
            True если успешно
        """
        logger.info(f"Позиционирование на файл {file_number}")
        
        # Сначала перематываем
        if not self.rewind():
            return False
        
        # Если нужен не первый файл, перемещаемся вперед
        if file_number > 0:
            return self.forward_space_file(file_number)
        
        return True
    
    def erase(self, quick: bool = True) -> bool:
        """
        Стирание ленты
        
        Args:
            quick: Быстрое стирание (только заголовки)
            
        Returns:
            True если успешно
        """
        logger.warning(f"Стирание ленты: {self.device} (quick={quick})")
        
        command = "erase" if quick else "weof"
        success, output = self._execute_mt_command(command)
        
        if success:
            logger.info("Лента стерта")
        else:
            logger.error(f"Ошибка стирания: {output}")
        
        return success
    
    def write_file_mark(self) -> bool:
        """
        Запись файловой метки (маркера конца файла)
        
        Returns:
            True если успешно
        """
        logger.debug("Запись файловой метки")
        success, output = self._execute_mt_command("weof")
        
        if not success:
            logger.error(f"Ошибка записи файловой метки: {output}")
        
        return success
    
    def set_block_size(self, size: int) -> bool:
        """
        Установка размера блока
        
        Args:
            size: Размер блока в байтах
            
        Returns:
            True если успешно
        """
        if size <= 0 or size > 1048576:
            logger.error(f"Недопустимый размер блока: {size}")
            return False
        
        logger.info(f"Установка размера блока: {size} байт")
        success, output = self._execute_mt_command("setblk", str(size))
        
        if success:
            logger.debug(f"Размер блока установлен: {size}")
        else:
            logger.error(f"Ошибка установки размера блока: {output}")
        
        return success
    
    def set_compression(self, enable: bool = True) -> bool:
        """
        Включение/выключение аппаратного сжатия
        
        Args:
            enable: Включить сжатие
            
        Returns:
            True если успешно
        """
        command = "compression" if enable else "compressionoff"
        logger.info(f"{'Включение' if enable else 'Выключение'} сжатия")
        
        success, output = self._execute_mt_command(command)
        
        if success:
            logger.debug(f"Сжатие {'включено' if enable else 'выключено'}")
        else:
            logger.warning(f"Не удалось {'включить' if enable else 'выключить'} сжатие: {output}")
        
        return success
    
    def load(self) -> bool:
        """
        Загрузка ленты (для роботизированных библиотек)
        
        Returns:
            True если успешно
        """
        logger.info("Загрузка ленты")
        success, output = self._execute_mt_command("load")
        
        if success:
            logger.debug("Лента загружена")
        else:
            logger.error(f"Ошибка загрузки ленты: {output}")
        
        return success
    
    def unload(self) -> bool:
        """
        Выгрузка ленты (для роботизированных библиотеки)
        
        Returns:
            True если успешно
        """
        logger.info("Выгрузка ленты")
        success, output = self._execute_mt_command("unload")
        
        if success:
            logger.debug("Лента выгружена")
        else:
            logger.error(f"Ошибка выгрузки ленты: {output}")
        
        return success
    
    def get_remaining_capacity(self) -> Optional[int]:
        """
        Получение оставшейся емкости ленты в байтах
        
        Returns:
            Оставшаяся емкость в байтах или None если невозможно определить
        """
        logger.debug("Получение оставшейся емкости (оценочное)")
        return None
    
    def is_ready_for_write(self) -> Tuple[bool, str]:
        """
        Проверка готовности ленты к записи
        
        Returns:
            (готовность, сообщение)
        """
        info = self.get_status()
        
        if info.status == TapeStatus.OFFLINE:
            return False, "Ленточный накопитель оффлайн"
        
        if info.status == TapeStatus.ERROR:
            return False, f"Ошибка накопителя: {info.last_error}"
        
        if info.cleaning_required:
            return False, "Требуется чистка ленточного накопителя"
        
        if info.is_write_protected:
            return False, "Лента защищена от записи"
        
        return True, "Лента готова к записи"
    
    def reset_stats(self):
        """Сброс счетчиков ошибок"""
        self.error_count = 0
        logger.debug("Статистика сброшена")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики работы"""
        return {
            'device': self.device,
            'error_count': self.error_count,
            'last_operation': self.last_operation_time.isoformat() if self.last_operation_time else None,
            'current_mode': self.current_mode.value if self.current_mode else None
        }

# Фабрика для создания экземпляров TapeDrive
class TapeDriveFactory:
    """Фабрика для создания и управления ленточными накопителями"""
    
    @staticmethod
    def autodetect_devices() -> List[str]:
        """
        Автообнаружение ленточных устройств в системе
        
        Returns:
            Список путей к ленточным устройствам
        """
        devices = []
        
        # Проверяем стандартные пути
        standard_paths = [
            "/dev/nst0", "/dev/nst1", "/dev/nst2", "/dev/nst3",
            "/dev/st0", "/dev/st1", "/dev/st2", "/dev/st3"
        ]
        
        for path in standard_paths:
            if os.path.exists(path):
                devices.append(path)
        
        # Ищем через lsscsi
        try:
            result = subprocess.run(
                ["lsscsi"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "tape" in line.lower():
                        parts = line.split()
                        if len(parts) >= 6:
                            device_path = parts[-1]
                            if os.path.exists(device_path):
                                devices.append(device_path)
        
        except Exception as e:
            logger.debug(f"Не удалось выполнить lsscsi: {e}")
        
        # Удаляем дубликаты
        return list(set(devices))
    
    @staticmethod
    def create_from_config(config_path: str = "config.yaml") -> Optional[TapeDrive]:
        """
        Создание TapeDrive из конфигурационного файла
        
        Args:
            config_path: Путь к конфигурационному файлу
            
        Returns:
            Экземпляр TapeDrive или None
        """
        try:
            from modules.config_manager import get_config_instance
            config = get_config_instance(config_path)
            
            return TapeDrive(config.hardware.tape_device)
            
        except Exception as e:
            logger.error(f"Ошибка создания TapeDrive из конфига: {e}")
            return None
    
    @staticmethod
    def create_all_available() -> List[TapeDrive]:
        """
        Создание TapeDrive для всех обнаруженных устройств
        
        Returns:
            Список экземпляров TapeDrive
        """
        devices = TapeDriveFactory.autodetect_devices()
        tape_drives = []
        
        for device in devices:
            try:
                tape_drive = TapeDrive(device)
                info = tape_drive.get_status()
                
                if info.status != TapeStatus.ERROR:
                    tape_drives.append(tape_drive)
                    logger.info(f"Обнаружено ленточное устройство: {device} ({info.vendor} {info.product})")
                else:
                    logger.warning(f"Пропущено устройство с ошибкой: {device}")
                    
            except Exception as e:
                logger.warning(f"Не удалось инициализировать устройство {device}: {e}")
        
        return tape_drives

if __name__ == "__main__":
    # Настройка логирования для тестов
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    print("🧪 Тестирование tape_drive.py")
    print("=" * 60)
    
    print("\n1. 🔍 Автообнаружение ленточных устройств:")
    devices = TapeDriveFactory.autodetect_devices()
    
    if devices:
        for i, device in enumerate(devices, 1):
            print(f"   {i}. {device}")
    else:
        print("   ❌ Ленточные устройства не обнаружены")
        print("   ℹ️  Создаю тестовый экземпляр с /dev/nst0")
        devices = ["/dev/nst0"]
    
    if devices:
        device = devices[0]
        print(f"\n2. 🎛️  Инициализация устройства: {device}")
        
        try:
            tape = TapeDrive(device)
            print(f"   ✅ Устройство инициализировано")
            
            print(f"\n3. 📊 Получение статуса устройства:")
            info = tape.get_status()
            
            print(f"   Устройство: {info.device}")
            print(f"   Статус: {info.status.value}")
            print(f"   Производитель: {info.vendor}")
            print(f"   Модель: {info.product}")
            print(f"   Текущий файл: {info.file_number}")
            print(f"   Требуется чистка: {'Да' if info.cleaning_required else 'Нет'}")
            print(f"   Защита от записи: {'Да' if info.is_write_protected else 'Нет'}")
            
            print(f"\n4. ✍️  Проверка готовности к записи:")
            ready, message = tape.is_ready_for_write()
            print(f"   Готовность: {'✅ Да' if ready else '❌ Нет'}")
            print(f"   Сообщение: {message}")
            
            print(f"\n5. 📈 Статистика работы:")
            stats = tape.get_stats()
            for key, value in stats.items():
                print(f"   {key}: {value}")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print(f"\n6. ⚙️  Тест фабрики из конфигурации:")
    if os.path.exists("config.yaml"):
        tape_from_config = TapeDriveFactory.create_from_config()
        if tape_from_config:
            print(f"   ✅ TapeDrive создан из config.yaml")
        else:
            print(f"   ❌ Не удалось создать TapeDrive из config.yaml")
    else:
        print(f"   ℹ️  config.yaml не найден, пропускаю тест")
    
    print("\n✅ Тестирование завершено")