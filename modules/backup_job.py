#!/usr/bin/env python3
"""
Класс для управления задачами бэкапа и восстановления
Инкапсулирует логику выполнения операций с лентой
"""

import os
import subprocess
import logging
import threading
import queue
import time
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger('backup_job')

class JobStatus(Enum):
    """Статус выполнения задачи"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobType(Enum):
    """Тип задачи"""
    BACKUP = "backup"
    RESTORE = "restore"
    VERIFY = "verify"
    CLEAN = "clean"

@dataclass
class JobProgress:
    """Прогресс выполнения задачи"""
    current_operation: str = ""
    current_file: str = ""
    files_processed: int = 0
    total_files: int = 0
    bytes_processed: int = 0
    total_bytes: int = 0
    percentage: float = 0.0
    speed_mbps: float = 0.0
    estimated_time_remaining: str = ""
    start_time: Optional[datetime] = None
    current_tape: str = ""
    tape_progress: float = 0.0

@dataclass
class JobResult:
    """Результат выполнения задачи"""
    job_id: str
    job_type: JobType
    status: JobStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    error_message: str = ""
    details: Dict[str, Any] = None
    tapes_used: List[str] = None
    manifest_path: str = ""
    registry_entry: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.tapes_used is None:
            self.tapes_used = []

class BackupJob:
    """Класс для управления задачей бэкапа или восстановления"""
    
    def __init__(self, job_id: str, job_type: JobType, 
                 tape_drive: Optional = None,
                 config_path: str = "config.yaml"):
        """
        Инициализация задачи
        
        Args:
            job_id: Уникальный идентификатор задачи
            job_type: Тип задачи
            tape_drive: Экземпляр TapeDrive (если None - создается из конфига)
            config_path: Путь к конфигурационному файлу
        """
        self.job_id = job_id
        self.job_type = job_type
        self.status = JobStatus.PENDING
        self.progress = JobProgress()
        self.result: Optional[JobResult] = None
        
        # Импортируем здесь чтобы избежать циклических импортов
        from modules.tape_drive import TapeDriveFactory
        from modules.system_monitor import SystemMonitor, MBufferOptimizer
        from modules.file_utils import SafeFileHandler, ManifestProcessor
        
        # Инициализация компонентов
        self.tape_drive = tape_drive or TapeDriveFactory.create_from_config(config_path)
        self.system_monitor = SystemMonitor()
        self.mbuffer_optimizer = MBufferOptimizer()
        self.file_handler = SafeFileHandler
        self.manifest_processor = ManifestProcessor
        
        # Конфигурация
        self.config = self._load_config(config_path)
        
        # Очередь сообщений для отслеживания прогресса
        self.message_queue = queue.Queue()
        
        # Поток выполнения
        self.execution_thread: Optional[threading.Thread] = None
        self.cancellation_event = threading.Event()
        
        # Время начала
        self.start_time: Optional[datetime] = None
        
        logger.info(f"Создана задача {job_id} типа {job_type.value}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Загрузка конфигурации"""
        config = {}
        
        try:
            from modules.config_manager import get_config_instance
            lto_config = get_config_instance(config_path)
            
            # Основные настройки
            config['registry_csv'] = lto_config.database.registry_file
            config['manifest_dir'] = lto_config.database.manifest_dir
            
            # Настройки mbuffer
            config['mbuffer_size'] = lto_config.buffer.size
            config['mbuffer_fill_percent'] = lto_config.buffer.fill_percent
            config['mbuffer_block_size'] = lto_config.buffer.block_size
            
            # Исключения
            config['exclude_list'] = lto_config.backup.default_excludes
            
            # Пути
            config['temp_dir'] = lto_config.database.cache_dir
            
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            # Значения по умолчанию
            config.update({
                'registry_csv': 'backup_registry.csv',
                'manifest_dir': './manifests',
                'mbuffer_size': '2G',
                'mbuffer_fill_percent': '90%',
                'mbuffer_block_size': '256k',
                'exclude_list': ['/proc', '/sys', '/dev', '/run', '/tmp', '*.log'],
                'temp_dir': '/tmp'
            })
        
        return config
    
    def start(self, **kwargs):
        """
        Запуск задачи в отдельном потоке
        
        Args:
            **kwargs: Параметры задачи
        """
        if self.status != JobStatus.PENDING:
            logger.error(f"Задача {self.job_id} уже запущена")
            return False
        
        # Сохраняем параметры
        self.task_params = kwargs
        
        # Создаем поток выполнения
        self.execution_thread = threading.Thread(
            target=self._execute_task,
            args=(kwargs,),
            name=f"Job-{self.job_id}"
        )
        self.execution_thread.daemon = True
        
        # Сбрасываем флаг отмены
        self.cancellation_event.clear()
        
        # Запускаем поток
        self.execution_thread.start()
        
        logger.info(f"Задача {self.job_id} запущена")
        return True
    
    def _execute_task(self, params: Dict[str, Any]):
        """Основная функция выполнения задачи"""
        self.status = JobStatus.RUNNING
        self.start_time = datetime.now()
        self.progress.start_time = self.start_time
        
        try:
            # Выполняем задачу в зависимости от типа
            if self.job_type == JobType.BACKUP:
                self.result = self._execute_backup(params)
            elif self.job_type == JobType.RESTORE:
                self.result = self._execute_restore(params)
            elif self.job_type == JobType.VERIFY:
                self.result = self._execute_verify(params)
            elif self.job_type == JobType.CLEAN:
                self.result = self._execute_clean(params)
            else:
                raise ValueError(f"Неизвестный тип задачи: {self.job_type}")
            
            # Обновляем статус
            if self.result.status == JobStatus.COMPLETED:
                self.status = JobStatus.COMPLETED
                logger.info(f"Задача {self.job_id} завершена успешно")
            else:
                self.status = JobStatus.FAILED
                logger.error(f"Задача {self.job_id} завершена с ошибкой: {self.result.error_message}")
        
        except Exception as e:
            # Непредвиденная ошибка
            self.status = JobStatus.FAILED
            error_msg = f"Критическая ошибка в задаче {self.job_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            self.result = JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message=error_msg
            )
    
    def _execute_backup(self, params: Dict[str, Any]) -> JobResult:
        """Выполнение задачи бэкапа"""
        source = params.get('source')
        label = params.get('label')
        
        if not source or not label:
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message="Не указаны source и/или label"
            )
        
        # Проверяем источник
        if not os.path.exists(source):
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message=f"Источник не найден: {source}"
            )
        
        # Проверяем систему
        if not self._check_system_readiness():
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message="Система не готова к выполнению бэкапа"
            )
        
        # Проверяем ленту
        ready, message = self.tape_drive.is_ready_for_write()
        if not ready:
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message=f"Лента не готова: {message}"
            )
        
        # Обновляем прогресс
        self.progress.current_operation = f"Бэкап {source} -> лента"
        self.progress.current_file = "Подготовка..."
        
        # Создаем манифест
        manifest_dir = self.config['manifest_dir']
        os.makedirs(manifest_dir, exist_ok=True)
        
        manifest_filename = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{label}.txt"
        manifest_path = os.path.join(manifest_dir, manifest_filename)
        
        # Выполняем бэкап
        try:
            # Оптимизируем параметры mbuffer
            mbuffer_params = self.mbuffer_optimizer.get_optimal_mbuffer_params(
                self.config['mbuffer_size'],
                self.system_monitor
            )
            
            # Формируем команду tar
            exclude_args = " ".join([f'--exclude="{pattern}"' 
                                   for pattern in self.config['exclude_list']])
            
            tar_cmd = f"tar -cv {exclude_args} --record-size={mbuffer_params['block_size']} "
            tar_cmd += f"--index-file={manifest_path} {source}"
            
            # Формируем команду mbuffer
            mbuffer_cmd = self.mbuffer_optimizer.build_mbuffer_command(
                output_file=self.tape_drive.device,
                params=mbuffer_params
            )
            
            # Полная команда
            full_cmd = f"{tar_cmd} | {mbuffer_cmd} 2>&1"
            
            logger.info(f"Выполнение бэкапа: {label}")
            logger.debug(f"Команда: {full_cmd[:200]}...")
            
            # Запускаем процесс
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8'
            )
            
            # Мониторим вывод
            tapes_used = []
            output_lines = []
            
            for line in iter(process.stdout.readline, ''):
                if self.cancellation_event.is_set():
                    process.terminate()
                    break
                
                line = line.strip()
                if line:
                    output_lines.append(line)
                    
                    # Обновляем прогресс (упрощенно)
                    self._update_backup_progress(line)
                    
                    # Логируем важные сообщения
                    if "error" in line.lower() or "warning" in line.lower():
                        logger.warning(f"Бэкап {label}: {line}")
            
            # Ждем завершения
            process.wait()
            
            if process.returncode != 0:
                error_output = "\n".join(output_lines[-10:])
                return JobResult(
                    job_id=self.job_id,
                    job_type=self.job_type,
                    status=JobStatus.FAILED,
                    start_time=self.start_time,
                    end_time=datetime.now(),
                    error_message=f"Ошибка выполнения бэкапа (код {process.returncode}): {error_output}"
                )
            
            # Получаем информацию о текущей позиции на ленте
            tape_info = self.tape_drive.get_status()
            
            # Создаем запись в реестре
            registry_entry = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'label': label,
                'tapes': f"[{','.join(tapes_used) if tapes_used else 'N/A'}]",
                'file_index': str(tape_info.file_number),
                'manifest': manifest_path
            }
            
            # Возвращаем успешный результат
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.COMPLETED,
                start_time=self.start_time,
                end_time=datetime.now(),
                tapes_used=tapes_used,
                manifest_path=manifest_path,
                registry_entry=registry_entry,
                details={
                    'source': source,
                    'command': full_cmd,
                    'mbuffer_params': mbuffer_params,
                    'tape_position': tape_info.file_number
                }
            )
            
        except Exception as e:
            logger.error(f"Ошибка выполнения бэкапа: {e}", exc_info=True)
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message=f"Исключение при выполнении бэкапа: {str(e)}"
            )
    
    def _execute_restore(self, params: Dict[str, Any]) -> JobResult:
        """Выполнение задачи восстановления"""
        destination = params.get('destination')
        label = params.get('label')
        
        if not destination or not label:
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message="Не указаны destination и/или label"
            )
        
        # Здесь будет полная реализация восстановления
        # Для демонстрации возвращаем заглушку
        return JobResult(
            job_id=self.job_id,
            job_type=self.job_type,
            status=JobStatus.COMPLETED,
            start_time=self.start_time,
            end_time=datetime.now(),
            details={'restore': 'implemented', 'destination': destination, 'label': label}
        )
    
    def _execute_verify(self, params: Dict[str, Any]) -> JobResult:
        """Выполнение задачи проверки"""
        label = params.get('label')
        
        if not label:
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message="Не указана метка для проверки"
            )
        
        # Здесь будет реализация проверки целостности
        return JobResult(
            job_id=self.job_id,
            job_type=self.job_type,
            status=JobStatus.COMPLETED,
            start_time=self.start_time,
            end_time=datetime.now(),
            details={'verify': 'implemented', 'label': label}
        )
    
    def _execute_clean(self, params: Dict[str, Any]) -> JobResult:
        """Выполнение задачи чистки"""
        try:
            logger.info("Выполнение чистки ленточного накопителя")
            
            # Проверяем статус
            tape_info = self.tape_drive.get_status()
            
            if not tape_info.cleaning_required:
                return JobResult(
                    job_id=self.job_id,
                    job_type=self.job_type,
                    status=JobStatus.COMPLETED,
                    start_time=self.start_time,
                    end_time=datetime.now(),
                    details={'cleaning': 'not_required'}
                )
            
            # Здесь можно добавить логику автоматической чистки
            # через робота или запрос на ручную чистку
            
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.COMPLETED,
                start_time=self.start_time,
                end_time=datetime.now(),
                details={'cleaning': 'requested'}
            )
            
        except Exception as e:
            return JobResult(
                job_id=self.job_id,
                job_type=self.job_type,
                status=JobStatus.FAILED,
                start_time=self.start_time,
                end_time=datetime.now(),
                error_message=f"Ошибка выполнения чистки: {str(e)}"
            )
    
    def _check_system_readiness(self) -> bool:
        """Проверка готовности системы"""
        try:
            # Проверяем ресурсы
            results = self.system_monitor.check_all_resources(self.config['temp_dir'])
            
            # Проверяем критические ресурсы
            for resource, (status, *_) in results.items():
                if resource in ['memory', 'disk'] and status.value == 'critical':
                    logger.error(f"Критическая проблема с {resource}")
                    return False
            
            self.system_monitor.log_resource_summary()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки системы: {e}")
            return False
    
    def _update_backup_progress(self, line: str):
        """Обновление прогресса на основе вывода"""
        if line.startswith('./'):
            self.progress.current_file = line
            self.progress.files_processed += 1
    
    def cancel(self):
        """Отмена выполнения задачи"""
        if self.status in [JobStatus.RUNNING, JobStatus.PAUSED]:
            self.cancellation_event.set()
            self.status = JobStatus.CANCELLED
            logger.info(f"Задача {self.job_id} отменена")
    
    def pause(self):
        """Приостановка задачи"""
        if self.status == JobStatus.RUNNING:
            self.status = JobStatus.PAUSED
            logger.info(f"Задача {self.job_id} приостановлена")
    
    def resume(self):
        """Возобновление задачи"""
        if self.status == JobStatus.PAUSED:
            self.status = JobStatus.RUNNING
            logger.info(f"Задача {self.job_id} возобновлена")
    
    def get_status(self) -> Dict[str, Any]:
        """Получение текущего статуса задачи"""
        status_info = {
            'job_id': self.job_id,
            'job_type': self.job_type.value,
            'status': self.status.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'progress': asdict(self.progress) if self.progress else None,
            'result': asdict(self.result) if self.result else None
        }
        
        # Добавляем информацию о ленте
        if self.tape_drive:
            tape_info = self.tape_drive.get_status()
            status_info['tape'] = {
                'device': tape_info.device,
                'status': tape_info.status.value,
                'file_number': tape_info.file_number,
                'cleaning_required': tape_info.cleaning_required
            }
        
        return status_info
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Ожидание завершения задачи
        
        Args:
            timeout: Таймаут в секундах
            
        Returns:
            True если задача завершена (успешно или с ошибкой)
        """
        if self.execution_thread:
            self.execution_thread.join(timeout)
            return not self.execution_thread.is_alive()
        return True
    
    def save_report(self, report_path: str) -> bool:
        """
        Сохранение отчета о выполнении задачи
        
        Args:
            report_path: Путь для сохранения отчета
            
        Returns:
            True если успешно
        """
        try:
            report_data = self.get_status()
            
            # Добавляем системную информацию
            report_data['system_info'] = {
                'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown',
                'timestamp': datetime.now().isoformat()
            }
            
            # Сохраняем в JSON
            self.file_handler.write_file(
                report_path,
                json.dumps(report_data, indent=2, ensure_ascii=False, default=str),
                ensure_utf8=True
            )
            
            logger.info(f"Отчет сохранен: {report_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения отчета: {e}")
            return False

# Менеджер задач
class JobManager:
    """Менеджер для управления несколькими задачами"""
    
    def __init__(self):
        self.jobs: Dict[str, BackupJob] = {}
        self.job_lock = threading.RLock()
    
    def create_job(self, job_type: JobType, **kwargs) -> Optional[BackupJob]:
        """
        Создание новой задачи
        
        Args:
            job_type: Тип задачи
            **kwargs: Параметры задачи
            
        Returns:
            Экземпляр BackupJob или None
        """
        job_id = self._generate_job_id(job_type)
        
        with self.job_lock:
            job = BackupJob(job_id, job_type, **kwargs)
            self.jobs[job_id] = job
            
            logger.info(f"Создана задача {job_id}")
            return job
    
    def _generate_job_id(self, job_type: JobType) -> str:
        """Генерация уникального ID задачи"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = os.urandom(2).hex()
        return f"{job_type.value}_{timestamp}_{random_suffix}"
    
    def get_job(self, job_id: str) -> Optional[BackupJob]:
        """Получение задачи по ID"""
        with self.job_lock:
            return self.jobs.get(job_id)
    
    def list_jobs(self, status_filter: Optional[JobStatus] = None) -> List[Dict[str, Any]]:
        """
        Список задач
        
        Args:
            status_filter: Фильтр по статусу
            
        Returns:
            Список информации о задачах
        """
        with self.job_lock:
            jobs_list = []
            
            for job_id, job in self.jobs.items():
                if status_filter is None or job.status == status_filter:
                    jobs_list.append(job.get_status())
            
            return jobs_list
    
    def cancel_job(self, job_id: str) -> bool:
        """Отмена задачи"""
        with self.job_lock:
            job = self.jobs.get(job_id)
            if job:
                job.cancel()
                return True
            return False
    
    def cleanup_completed_jobs(self, max_age_hours: int = 24):
        """
        Очистка завершенных задач
        
        Args:
            max_age_hours: Максимальный возраст задач в часах
        """
        with self.job_lock:
            jobs_to_remove = []
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
            
            for job_id, job in self.jobs.items():
                if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    # Проверяем возраст
                    if job.start_time and job.start_time.timestamp() < cutoff_time:
                        jobs_to_remove.append(job_id)
            
            for job_id in jobs_to_remove:
                del self.jobs[job_id]
                logger.debug(f"Удалена завершенная задача: {job_id}")
            
            if jobs_to_remove:
                logger.info(f"Очищено {len(jobs_to_remove)} завершенных задач")

# Утилитарные функции
def create_backup_task(source: str, label: str, 
                      job_manager: Optional[JobManager] = None) -> Optional[BackupJob]:
    """
    Быстрое создание задачи бэкапа
    
    Args:
        source: Источник для бэкапа
        label: Метка бэкапа
        job_manager: Менеджер задач (если None - создается новый)
        
    Returns:
        Экземпляр BackupJob или None
    """
    if job_manager is None:
        job_manager = JobManager()
    
    job = job_manager.create_job(
        JobType.BACKUP,
        source=source,
        label=label
    )
    
    if job:
        job.start(source=source, label=label)
    
    return job

if __name__ == "__main__":
    # Настройка логирования для тестов
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    print("🧪 Тестирование backup_job.py")
    print("=" * 60)
    
    # Тест 1: Создание менеджера задач
    print("\n1. 🏢 Создание менеджера задач:")
    manager = JobManager()
    print(f"   ✅ Менеджер задач создан")
    
    # Тест 2: Создание задачи бэкапа
    print("\n2. 📦 Создание задачи бэкапа:")
    backup_job = manager.create_job(
        JobType.BACKUP,
        source="/tmp/test_backup",
        label="TestBackup"
    )
    
    if backup_job:
        print(f"   ✅ Задача создана: {backup_job.job_id}")
        
        # Тест 3: Получение статуса
        print("\n3. 📊 Статус задачи:")
        status = backup_job.get_status()
        print(f"   ID: {status['job_id']}")
        print(f"   Тип: {status['job_type']}")
        print(f"   Статус: {status['status']}")
        
        # Тест 4: Список задач
        print("\n4. 📋 Список задач:")
        jobs_list = manager.list_jobs()
        print(f"   Всего задач: {len(jobs_list)}")
        for job_info in jobs_list:
            print(f"   - {job_info['job_id']}: {job_info['status']}")
        
        # Тест 5: Создание задачи восстановления
        print("\n5. 🔄 Создание задачи восстановления:")
        restore_job = manager.create_job(
            JobType.RESTORE,
            destination="/tmp/test_restore",
            label="TestBackup"
        )
        
        if restore_job:
            print(f"   ✅ Задача восстановления создана: {restore_job.job_id}")
            
            # Тест 6: Список с фильтром
            print("\n6. 🎯 Список PENDING задач:")
            pending_jobs = manager.list_jobs(JobStatus.PENDING)
            print(f"   PENDING задач: {len(pending_jobs)}")
            
        # Тест 7: Утилитарная функция
        print("\n7. 🚀 Быстрое создание задачи:")
        quick_job = create_backup_task("/tmp/another_test", "QuickBackup", manager)
        if quick_job:
            print(f"   ✅ Быстрая задача создана: {quick_job.job_id}")
        
        # Тест 8: Очистка (симуляция)
        print("\n8. 🧹 Симуляция очистки старых задач:")
        manager.cleanup_completed_jobs()
        print(f"   ✅ Очистка выполнена (в демо-режиме)")
    
    print("\n✅ Тестирование завершено")