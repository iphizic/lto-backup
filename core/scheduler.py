#!/usr/bin/env python3
"""
Scheduler module for automatic backup scheduling
"""

import schedule
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from core.config_manager import ConfigManager
from core.backup_engine import BackupEngine
from core.registry_manager import RegistryManager
from hardware.tape_driver import TapeDriver
from notification.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

class BackupScheduler:
    """Scheduler for automatic backup operations"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.scheduling_enabled = config.get('scheduling', 'enabled', False)
        self.schedule_params = config.get_scheduling_params()
        
        # Initialize components
        self.backup_engine = BackupEngine(config)
        self.registry = RegistryManager(config)
        self.tape_driver = TapeDriver(config)
        self.bot = TelegramBot(config)
        
        # Scheduler state
        self.scheduler_thread = None
        self.running = False
        self.jobs = {}
        
        logger.info("Backup scheduler initialized")
    
    def _create_backup_label(self, backup_type: str) -> str:
        """Create label for automated backup"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        
        if backup_type == 'daily':
            return f"Auto_Daily_{timestamp}"
        elif backup_type == 'weekly':
            return f"Auto_Weekly_{timestamp}"
        elif backup_type == 'monthly':
            return f"Auto_Monthly_{timestamp}"
        else:
            return f"Auto_{timestamp}"
    
    def _get_backup_paths(self) -> list:
        """Get paths to backup from configuration"""
        paths_config = self.config.get_section('paths')
        important_dirs = paths_config.get('important_dirs', [])
        excluded_dirs = paths_config.get('excluded_dirs', [])
        
        # Filter out excluded directories
        backup_paths = []
        for path in important_dirs:
            if path not in excluded_dirs and Path(path).exists():
                backup_paths.append(path)
        
        return backup_paths
    
    def _run_backup_job(self, backup_type: str) -> bool:
        """Execute backup job"""
        try:
            logger.info(f"Starting scheduled {backup_type} backup")
            
            # Get paths to backup
            backup_paths = self._get_backup_paths()
            if not backup_paths:
                logger.warning("No backup paths configured or found")
                self.bot.send_message("⚠️ Не удалось запустить автоматический бэкап: пути не настроены", "WARNING")
                return False
            
            # Create backup label
            label = self._create_backup_label(backup_type)
            
            # Create temporary directory for backup list
            import tempfile
            import os
            
            # Create file with list of directories to backup
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                for path in backup_paths:
                    f.write(f"{path}\n")
                list_file = f.name
            
            try:
                # Execute backup using the list file
                success = self.backup_engine.backup(f"@{list_file}", label)
                
                if success:
                    logger.info(f"Scheduled {backup_type} backup completed: {label}")
                    self.bot.send_message(
                        f"✅ Автоматический {backup_type} бэкап завершен: `{label}`",
                        "INFO"
                    )
                else:
                    logger.error(f"Scheduled {backup_type} backup failed: {label}")
                    self.bot.send_message(
                        f"❌ Автоматический {backup_type} бэкап не удался: `{label}`",
                        "ERROR"
                    )
                
                return success
                
            finally:
                # Clean up temporary file
                if os.path.exists(list_file):
                    os.unlink(list_file)
                    
        except Exception as e:
            logger.error(f"Error in scheduled backup job: {e}")
            self.bot.send_message(
                f"❌ Ошибка в автоматическом бэкапе: `{str(e)[:100]}`",
                "ERROR"
            )
            return False
    
    def _setup_daily_backup(self) -> None:
        """Setup daily backup schedule"""
        daily_time = self.schedule_params.get('daily_at', '02:00')
        
        try:
            # Parse time
            hour, minute = map(int, daily_time.split(':'))
            
            # Schedule daily job
            schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(
                self._run_backup_job, 'daily'
            ).tag('daily')
            
            logger.info(f"Daily backup scheduled at {daily_time}")
            
        except Exception as e:
            logger.error(f"Error setting up daily backup schedule: {e}")
    
    def _setup_weekly_backup(self) -> None:
        """Setup weekly backup schedule"""
        weekly_day = self.schedule_params.get('weekly_day', 'sunday').lower()
        daily_time = self.schedule_params.get('daily_at', '02:00')
        
        try:
            # Parse time
            hour, minute = map(int, daily_time.split(':'))
            
            # Map day names
            day_map = {
                'monday': schedule.every().monday,
                'tuesday': schedule.every().tuesday,
                'wednesday': schedule.every().wednesday,
                'thursday': schedule.every().thursday,
                'friday': schedule.every().friday,
                'saturday': schedule.every().saturday,
                'sunday': schedule.every().sunday
            }
            
            if weekly_day in day_map:
                day_map[weekly_day].at(f"{hour:02d}:{minute:02d}").do(
                    self._run_backup_job, 'weekly'
                ).tag('weekly')
                logger.info(f"Weekly backup scheduled on {weekly_day} at {daily_time}")
            else:
                logger.warning(f"Invalid weekly day: {weekly_day}")
                
        except Exception as e:
            logger.error(f"Error setting up weekly backup schedule: {e}")
    
    def _setup_monthly_backup(self) -> None:
        """Setup monthly backup schedule"""
        monthly_day = self.schedule_params.get('monthly_day', 1)
        daily_time = self.schedule_params.get('daily_at', '02:00')
        
        try:
            # Parse time
            hour, minute = map(int, daily_time.split(':'))
            
            # Schedule monthly job (simplified - runs on specific day of month)
            def monthly_job():
                today = datetime.now().day
                if today == monthly_day:
                    self._run_backup_job('monthly')
            
            schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(monthly_job).tag('monthly')
            logger.info(f"Monthly backup scheduled on day {monthly_day} at {daily_time}")
            
        except Exception as e:
            logger.error(f"Error setting up monthly backup schedule: {e}")
    
    def _cleanup_old_backups(self) -> None:
        """Cleanup old backups based on retention policy"""
        try:
            retention_policy = self.schedule_params.get('retention_policy', {})
            
            # Cleanup old registry entries
            retention_days = self.config.get('common', 'retention_days', 90)
            if retention_days > 0:
                deleted = self.registry.cleanup_old_backups(retention_days)
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old backup records")
            
            # Apply retention policy if configured
            if retention_policy:
                logger.info(f"Retention policy: {retention_policy}")
                
        except Exception as e:
            logger.error(f"Error in backup cleanup: {e}")
    
    def _scheduler_loop(self) -> None:
        """Main scheduler loop"""
        logger.info("Starting scheduler loop")
        
        # Setup scheduled jobs
        self._setup_daily_backup()
        self._setup_weekly_backup()
        self._setup_monthly_backup()
        
        # Schedule cleanup job (runs daily)
        schedule.every().day.at("03:00").do(self._cleanup_old_backups).tag('cleanup')
        
        # Send startup notification
        self.bot.send_message("🔄 Планировщик бэкапов запущен", "INFO")
        
        # Main scheduler loop
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(300)  # Wait 5 minutes on error
        
        logger.info("Scheduler loop stopped")
    
    def start(self) -> bool:
        """Start the backup scheduler"""
        if not self.scheduling_enabled:
            logger.warning("Scheduler is disabled in configuration")
            return False
        
        if self.running:
            logger.warning("Scheduler is already running")
            return False
        
        # Check if we have backup paths configured
        backup_paths = self._get_backup_paths()
        if not backup_paths:
            logger.error("Cannot start scheduler: no backup paths configured")
            self.bot.send_message(
                "❌ Не удалось запустить планировщик: пути для бэкапа не настроены",
                "ERROR"
            )
            return False
        
        self.running = True
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="BackupScheduler",
            daemon=True
        )
        self.scheduler_thread.start()
        
        logger.info("Backup scheduler started")
        return True
    
    def stop(self) -> None:
        """Stop the backup scheduler"""
        self.running = False
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=30)
        
        # Clear all scheduled jobs
        schedule.clear()
        
        logger.info("Backup scheduler stopped")
        self.bot.send_message("⏹️ Планировщик бэкапов остановлен", "INFO")
    
    def get_schedule_info(self) -> Dict[str, Any]:
        """Get information about scheduled jobs"""
        job_info = {
            'enabled': self.scheduling_enabled,
            'jobs': [],
            'next_run': None
        }
        
        if not self.scheduling_enabled:
            return job_info
        
        # Get information about scheduled jobs
        jobs = schedule.get_jobs()
        for job in jobs:
            job_info['jobs'].append({
                'function': job.job_func.__name__ if hasattr(job.job_func, '__name__') else str(job.job_func),
                'tags': list(job.tags),
                'next_run': str(job.next_run) if job.next_run else None
            })
        
        # Get next run time
        if jobs:
            next_job = min(jobs, key=lambda j: j.next_run if j.next_run else datetime.max)
            job_info['next_run'] = str(next_job.next_run) if next_job.next_run else None
        
        return job_info
    
    def run(self) -> bool:
        """Run the scheduler (blocking)"""
        if not self.scheduling_enabled:
            print("Scheduler is disabled in configuration")
            return False
        
        print("=" * 60)
        print("LTO Backup Scheduler")
        print("=" * 60)
        print(f"Config: {self.config.config_path}")
        print(f"Backup paths: {len(self._get_backup_paths())}")
        print("=" * 60)
        
        # Start the scheduler
        if self.start():
            print("✅ Scheduler started")
            print("Press Ctrl+C to stop")
            
            try:
                # Keep main thread alive
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping scheduler...")
                self.stop()
            
            return True
        else:
            print("❌ Failed to start scheduler")
            return False