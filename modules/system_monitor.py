#!/usr/bin/env python3
"""
Мониторинг системных ресурсов: RAM, диск, CPU
Проверка доступности ресурсов перед выполнением операций
"""

import os
import sys
import psutil
import logging
import subprocess
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger('system_monitor')

class ResourceStatus(Enum):
    """Статус доступности ресурсов"""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

@dataclass
class ResourceMetrics:
    """Метрики системных ресурсов"""
    memory_total: int
    memory_available: int
    memory_used_percent: float
    swap_total: int
    swap_used_percent: float
    cpu_percent: float
    disk_free: int
    disk_used_percent: float
    load_average: Tuple[float, float, float]

class SystemMonitor:
    """Монитор системных ресурсов"""
    
    MIN_MEMORY_FOR_MBUFFER = 512 * 1024 * 1024
    MIN_DISK_SPACE_FOR_TEMP = 1024 * 1024 * 1024
    WARNING_MEMORY_THRESHOLD = 0.85
    CRITICAL_MEMORY_THRESHOLD = 0.95
    
    def __init__(self, mbuffer_size: str = "2G"):
        self.mbuffer_size = self._parse_mbuffer_size(mbuffer_size)
        self._update_interval = 2
    
    def _parse_mbuffer_size(self, size_str: str) -> int:
        size_str = size_str.upper().strip()
        
        multipliers = {
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }
        
        for suffix, multiplier in multipliers.items():
            if size_str.endswith(suffix):
                number_str = size_str[:-1]
                try:
                    number = float(number_str)
                    return int(number * multiplier)
                except ValueError:
                    logger.error(f"Неверный формат размера: {size_str}")
                    break
        
        try:
            return int(size_str)
        except ValueError:
            logger.error(f"Не удалось распарсить размер: {size_str}")
            return 2 * 1024 * 1024 * 1024
    
    def get_system_metrics(self) -> ResourceMetrics:
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage('/')
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0.0, 0.0, 0.0)
            
            return ResourceMetrics(
                memory_total=memory.total,
                memory_available=memory.available,
                memory_used_percent=memory.percent,
                swap_total=swap.total,
                swap_used_percent=swap.percent,
                cpu_percent=cpu_percent,
                disk_free=disk.free,
                disk_used_percent=disk.percent,
                load_average=load_avg
            )
            
        except Exception as e:
            logger.error(f"Ошибка получения метрик системы: {e}")
            return ResourceMetrics(
                memory_total=0,
                memory_available=0,
                memory_used_percent=0.0,
                swap_total=0,
                swap_used_percent=0.0,
                cpu_percent=0.0,
                disk_free=0,
                disk_used_percent=0.0,
                load_average=(0.0, 0.0, 0.0)
            )
    
    def check_memory_for_mbuffer(self, metrics: Optional[ResourceMetrics] = None) -> Tuple[ResourceStatus, str, int]:
        if metrics is None:
            metrics = self.get_system_metrics()
        
        required_memory = self.mbuffer_size
        available_memory = metrics.memory_available - self.MIN_MEMORY_FOR_MBUFFER
        memory_usage_ratio = 1.0 - (metrics.memory_available / metrics.memory_total) if metrics.memory_total > 0 else 1.0
        
        if metrics.memory_available < self.MIN_MEMORY_FOR_MBUFFER:
            message = (f"Критически мало памяти: {self._format_bytes(metrics.memory_available)} доступно, "
                      f"требуется минимум {self._format_bytes(self.MIN_MEMORY_FOR_MBUFFER)}")
            return ResourceStatus.CRITICAL, message, 0
        
        elif available_memory < required_memory:
            if memory_usage_ratio > self.CRITICAL_MEMORY_THRESHOLD:
                status = ResourceStatus.CRITICAL
                severity = "критически высокое"
            elif memory_usage_ratio > self.WARNING_MEMORY_THRESHOLD:
                status = ResourceStatus.WARNING
                severity = "высокое"
            else:
                status = ResourceStatus.WARNING
                severity = "недостаточно"
            
            recommended_size = max(self.MIN_MEMORY_FOR_MBUFFER, int(available_memory * 0.8))
            
            message = (f"{severity.capitalize()} использование памяти: {memory_usage_ratio:.1%}. "
                      f"Доступно {self._format_bytes(available_memory)}, "
                      f"требуется {self._format_bytes(required_memory)}. "
                      f"Рекомендуемый размер буфера: {self._format_bytes(recommended_size)}")
            
            return status, message, recommended_size
        
        elif memory_usage_ratio > self.CRITICAL_MEMORY_THRESHOLD:
            message = (f"Критически высокое использование памяти: {memory_usage_ratio:.1%}. "
                      f"Доступно {self._format_bytes(available_memory)}")
            return ResourceStatus.CRITICAL, message, required_memory
        
        elif memory_usage_ratio > self.WARNING_MEMORY_THRESHOLD:
            message = (f"Высокое использование памяти: {memory_usage_ratio:.1%}. "
                      f"Доступно {self._format_bytes(available_memory)}")
            return ResourceStatus.WARNING, message, required_memory
        
        else:
            message = (f"Память в порядке: {memory_usage_ratio:.1%} использования, "
                      f"доступно {self._format_bytes(available_memory)}")
            return ResourceStatus.OK, message, required_memory
    
    def check_disk_space(self, path: str = "/", required_space: int = None) -> Tuple[ResourceStatus, str]:
        try:
            if required_space is None:
                required_space = self.MIN_DISK_SPACE_FOR_TEMP
            
            disk = psutil.disk_usage(path)
            free_space = disk.free
            used_percent = disk.percent
            
            if free_space < required_space:
                message = (f"Критически мало места на диске {path}: "
                          f"{self._format_bytes(free_space)} свободно, "
                          f"требуется {self._format_bytes(required_space)}")
                return ResourceStatus.CRITICAL, message
            
            elif free_space < required_space * 2:
                message = (f"Мало места на диске {path}: "
                          f"{self._format_bytes(free_space)} свободно, "
                          f"используется {used_percent:.1f}%")
                return ResourceStatus.WARNING, message
            
            else:
                message = (f"Место на диске {path} в порядке: "
                          f"{self._format_bytes(free_space)} свободно, "
                          f"используется {used_percent:.1f}%")
                return ResourceStatus.OK, message
                
        except Exception as e:
            logger.error(f"Ошибка проверки диска {path}: {e}")
            return ResourceStatus.UNKNOWN, f"Не удалось проверить диск {path}: {e}"
    
    def check_system_load(self) -> Tuple[ResourceStatus, str]:
        try:
            if not hasattr(os, 'getloadavg'):
                return ResourceStatus.UNKNOWN, "Load average не поддерживается на этой системе"
            
            load_1, load_5, load_15 = os.getloadavg()
            cpu_count = psutil.cpu_count()
            normalized_load_1 = load_1 / cpu_count if cpu_count > 0 else load_1
            
            if normalized_load_1 > 2.0:
                message = (f"Критически высокая загрузка системы: "
                          f"load average: {load_1:.2f}, {load_5:.2f}, {load_15:.2f} "
                          f"({cpu_count} CPU)")
                return ResourceStatus.CRITICAL, message
            
            elif normalized_load_1 > 1.0:
                message = (f"Высокая загрузка системы: "
                          f"load average: {load_1:.2f}, {load_5:.2f}, {load_15:.2f} "
                          f"({cpu_count} CPU)")
                return ResourceStatus.WARNING, message
            
            else:
                message = (f"Загрузка системы нормальная: "
                          f"load average: {load_1:.2f}, {load_5:.2f}, {load_15:.2f} "
                          f"({cpu_count} CPU)")
                return ResourceStatus.OK, message
                
        except Exception as e:
            logger.error(f"Ошибка проверки загрузки системы: {e}")
            return ResourceStatus.UNKNOWN, f"Не удалось проверить загрузку системы: {e}"
    
    def check_all_resources(self, temp_dir: str = "/tmp") -> Dict[str, Tuple[ResourceStatus, str]]:
        metrics = self.get_system_metrics()
        
        results = {}
        
        mem_status, mem_msg, recommended_size = self.check_memory_for_mbuffer(metrics)
        results['memory'] = (mem_status, mem_msg, recommended_size)
        
        disk_status, disk_msg = self.check_disk_space(temp_dir)
        results['disk'] = (disk_status, disk_msg)
        
        load_status, load_msg = self.check_system_load()
        results['load'] = (load_status, load_msg)
        
        swap_msg = f"Swap используется: {metrics.swap_used_percent:.1f}%"
        if metrics.swap_used_percent > 80:
            results['swap'] = (ResourceStatus.WARNING, swap_msg)
        else:
            results['swap'] = (ResourceStatus.OK, swap_msg)
        
        return results
    
    def adjust_mbuffer_size(self) -> str:
        metrics = self.get_system_metrics()
        status, message, recommended_bytes = self.check_memory_for_mbuffer(metrics)
        
        if recommended_bytes >= 1024 * 1024 * 1024:
            size = f"{recommended_bytes / (1024*1024*1024):.1f}G"
        elif recommended_bytes >= 1024 * 1024:
            size = f"{recommended_bytes / (1024*1024):.0f}M"
        elif recommended_bytes >= 1024:
            size = f"{recommended_bytes / 1024:.0f}K"
        else:
            size = f"{recommended_bytes}B"
        
        logger.info(f"Рекомендуемый размер mbuffer: {size} ({message})")
        return size
    
    def get_memory_stats(self) -> Dict[str, Any]:
        metrics = self.get_system_metrics()
        
        return {
            'total': self._format_bytes(metrics.memory_total),
            'available': self._format_bytes(metrics.memory_available),
            'used_percent': f"{metrics.memory_used_percent:.1f}%",
            'swap_total': self._format_bytes(metrics.swap_total),
            'swap_used_percent': f"{metrics.swap_used_percent:.1f}%",
            'mbuffer_requested': self._format_bytes(self.mbuffer_size),
            'min_required': self._format_bytes(self.MIN_MEMORY_FOR_MBUFFER),
            'status': self.check_memory_for_mbuffer(metrics)[0].value
        }
    
    def _format_bytes(self, bytes_value: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
    
    def log_resource_summary(self):
        results = self.check_all_resources()
        
        logger.info("📊 Сводка по ресурсам системы:")
        
        for resource, (status, *details) in results.items():
            emoji = {
                ResourceStatus.OK: "✅",
                ResourceStatus.WARNING: "⚠️",
                ResourceStatus.CRITICAL: "❌",
                ResourceStatus.UNKNOWN: "❓"
            }.get(status, "❓")
            
            if resource == 'memory':
                msg = details[0]
                rec_size = details[1] if len(details) > 1 else None
                if rec_size:
                    logger.info(f"  {emoji} {resource}: {msg} (рекомендуется: {self._format_bytes(rec_size)})")
                else:
                    logger.info(f"  {emoji} {resource}: {msg}")
            else:
                logger.info(f"  {emoji} {resource}: {details[0]}")

class MBufferOptimizer:
    """Оптимизатор параметров mbuffer на основе системных ресурсов"""
    
    @staticmethod
    def get_optimal_mbuffer_params(mbuffer_size: str = None, 
                                  system_monitor: SystemMonitor = None) -> Dict[str, str]:
        if system_monitor is None:
            system_monitor = SystemMonitor(mbuffer_size or "2G")
        
        results = system_monitor.check_all_resources()
        mem_status, mem_msg, recommended_size = results['memory']
        
        if mem_status == ResourceStatus.CRITICAL:
            buffer_size = max(system_monitor.MIN_MEMORY_FOR_MBUFFER, 
                            int(recommended_size * 0.5))
        elif mem_status == ResourceStatus.WARNING:
            buffer_size = int(recommended_size * 0.75)
        else:
            buffer_size = recommended_size
        
        if buffer_size >= 1024 * 1024 * 1024:
            size_str = f"{buffer_size / (1024*1024*1024):.1f}G"
        elif buffer_size >= 1024 * 1024:
            size_str = f"{buffer_size / (1024*1024):.0f}M"
        else:
            size_str = f"{buffer_size / 1024:.0f}K"
        
        if mem_status == ResourceStatus.CRITICAL:
            fill_percent = "70%"
        elif mem_status == ResourceStatus.WARNING:
            fill_percent = "80%"
        else:
            fill_percent = "90%"
        
        disk_status, _ = results['disk']
        if disk_status == ResourceStatus.CRITICAL:
            block_size = "512k"
        else:
            block_size = "1M" if buffer_size > 2 * 1024 * 1024 * 1024 else "256k"
        
        return {
            'size': size_str,
            'fill_percent': fill_percent,
            'block_size': block_size,
            'memory_status': mem_status.value,
            'warning': mem_msg if mem_status != ResourceStatus.OK else None
        }
    
    @staticmethod
    def build_mbuffer_command(input_file: str = None, 
                             output_file: str = None,
                             params: Dict[str, str] = None) -> str:
        if params is None:
            params = MBufferOptimizer.get_optimal_mbuffer_params()
        
        cmd_parts = ["mbuffer"]
        
        if 'size' in params:
            cmd_parts.append(f"-m {params['size']}")
        
        if 'fill_percent' in params:
            cmd_parts.append(f"-P {params['fill_percent']}")
        
        if 'block_size' in params:
            cmd_parts.append(f"-b {params['block_size']}")
        
        cmd_parts.extend(["-n 0", "-f"])
        
        if input_file:
            cmd_parts.append(f"-i {input_file}")
        
        if output_file:
            cmd_parts.append(f"-o {output_file}")
        
        cmd_parts.append("-A 'python3 tape_changer.py'")
        
        return " ".join(cmd_parts)

def check_system_readiness(mbuffer_size: str = "2G", temp_dir: str = "/tmp") -> bool:
    monitor = SystemMonitor(mbuffer_size)
    results = monitor.check_all_resources(temp_dir)
    
    critical_checks = ['memory', 'disk']
    
    for resource in critical_checks:
        if resource in results:
            status = results[resource][0]
            if status == ResourceStatus.CRITICAL:
                logger.error(f"Критическая проблема с {resource}: {results[resource][1]}")
                return False
    
    monitor.log_resource_summary()
    return True

def get_system_info() -> Dict[str, Any]:
    monitor = SystemMonitor()
    metrics = monitor.get_system_metrics()
    
    return {
        'memory': monitor.get_memory_stats(),
        'cpu_count': psutil.cpu_count(),
        'cpu_percent': f"{metrics.cpu_percent:.1f}%",
        'disk_free': monitor._format_bytes(metrics.disk_free),
        'disk_used_percent': f"{metrics.disk_used_percent:.1f}%",
        'load_average': metrics.load_average,
        'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    print("🧪 Тестирование system_monitor.py")
    print("=" * 60)
    
    monitor = SystemMonitor("2G")
    print("✅ Системный монитор инициализирован")
    
    metrics = monitor.get_system_metrics()
    print(f"📊 Метрики системы:")
    print(f"  Память: {monitor._format_bytes(metrics.memory_total)} всего, "
          f"{monitor._format_bytes(metrics.memory_available)} доступно")
    print(f"  Диск: {monitor._format_bytes(metrics.disk_free)} свободно")
    print(f"  CPU: {metrics.cpu_percent:.1f}%")
    
    status, message, recommended = monitor.check_memory_for_mbuffer(metrics)
    print(f"🧠 Проверка памяти: {status.value}")
    print(f"  {message}")
    if recommended:
        print(f"  Рекомендуемый размер: {monitor._format_bytes(recommended)}")
    
    print(f"\n🔍 Проверка всех ресурсов:")
    results = monitor.check_all_resources()
    
    for resource, (status, *details) in results.items():
        emoji = {
            ResourceStatus.OK: "✅",
            ResourceStatus.WARNING: "⚠️",
            ResourceStatus.CRITICAL: "❌",
            ResourceStatus.UNKNOWN: "❓"
        }.get(status, "❓")
        
        if resource == 'memory':
            print(f"  {emoji} {resource}: {details[0]}")
            if len(details) > 1:
                print(f"     Рекомендуется: {monitor._format_bytes(details[1])}")
        else:
            print(f"  {emoji} {resource}: {details[0]}")
    
    print(f"\n⚙️  Оптимизация параметров mbuffer:")
    params = MBufferOptimizer.get_optimal_mbuffer_params("2G", monitor)
    for key, value in params.items():
        if value:
            print(f"  {key}: {value}")
    
    print(f"\n🚀 Проверка готовности системы:")
    ready = check_system_readiness("2G")
    print(f"  Система {'готова' if ready else 'не готова'} к бэкапу")
    
    print("\n✅ Тестирование завершено")