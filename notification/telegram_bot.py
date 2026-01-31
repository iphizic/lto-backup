import logging
from typing import Optional, Dict, Any
from telegram import Bot
from telegram.error import TelegramError
from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class TelegramBot:
    """Класс для работы с Telegram Bot API"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.enabled = config.get_telegram_enabled()
        
        if self.enabled:
            self.token = config.get('telegram', 'token')
            self.chat_id = config.get('telegram', 'chat_id')
            self.notification_level = config.get('telegram', 'notification_level', 'INFO').upper()
            
            # Индивидуальные настройки уведомлений
            self.notify_backup_started = config.get('telegram', 'backup_started', True)
            self.notify_backup_completed = config.get('telegram', 'backup_completed', True)
            self.notify_backup_failed = config.get('telegram', 'backup_failed', True)
            self.notify_tape_change = config.get('telegram', 'tape_change', True)
            self.notify_cleaning_required = config.get('telegram', 'cleaning_required', True)
            
            if self.token and self.chat_id and self.token != 'YOUR_BOT_TOKEN_HERE':
                try:
                    self.bot = Bot(token=self.token)
                    logger.info("Telegram бот инициализирован")
                except Exception as e:
                    logger.error(f"Ошибка инициализации Telegram бота: {e}")
                    self.bot = None
            else:
                self.bot = None
                logger.warning("Telegram не настроен, уведомления отключены")
        else:
            self.bot = None
            logger.info("Telegram уведомления отключены в конфигурации")
    
    def _should_notify(self, level: str) -> bool:
        """Проверить, нужно ли отправлять уведомление данного уровня"""
        if not self.enabled or not self.bot:
            return False
        
        level_priority = {
            'DEBUG': 10,
            'INFO': 20,
            'WARNING': 30,
            'ERROR': 40,
            'CRITICAL': 50
        }
        
        current_level = level_priority.get(level.upper(), 20)
        config_level = level_priority.get(self.notification_level, 20)
        
        return current_level >= config_level
    
    def send_message(self, text: str, level: str = "INFO", parse_mode: Optional[str] = "Markdown") -> bool:
        """Отправить сообщение в Telegram"""
        if not self._should_notify(level):
            return False
        
        try:
            # Добавляем эмодзи в зависимости от уровня
            if level == "ERROR":
                text = f"❌ {text}"
            elif level == "WARNING":
                text = f"⚠️  {text}"
            elif level == "INFO":
                text = f"ℹ️  {text}"
            elif level == "SUCCESS":
                text = f"✅ {text}"
            
            self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=(level == "DEBUG")
            )
            
            logger.info(f"Telegram сообщение отправлено ({level}): {text[:100]}...")
            return True
            
        except TelegramError as e:
            logger.error(f"Ошибка отправки Telegram сообщения: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при отправке в Telegram: {e}")
            return False
    
    def send_backup_started(self, label: str, source: str, size_estimate: str = "") -> bool:
        """Отправить уведомление о начале бэкапа"""
        if not self.notify_backup_started:
            return False
        
        message = (
            f"🚀 *НАЧАЛО БЭКАПА*\n"
            f"📝 Метка: `{label}`\n"
            f"📁 Источник: `{source}`\n"
        )
        
        if size_estimate:
            message += f"📊 Оценка размера: `{size_estimate}`\n"
        
        message += f"⏰ Время: {self._get_current_time()}"
        
        return self.send_message(message, level="INFO")
    
    def send_backup_completed(self, label: str, tapes: str, file_number: str, 
                             duration: str = "", data_size: str = "", 
                             clean_time: str = "Нет") -> bool:
        """Отправить уведомление о завершении бэкапа"""
        if not self.notify_backup_completed:
            return False
        
        message = (
            f"✅ *БЭКАП ЗАВЕРШЕН*\n"
            f"📝 Метка: `{label}`\n"
            f"📼 Кассеты: `[{tapes}]`\n"
            f"🔢 Номер файла: `{file_number}`\n"
        )
        
        if duration:
            message += f"⏱️ Длительность: `{duration}`\n"
        
        if data_size:
            message += f"📊 Размер данных: `{data_size}`\n"
        
        message += f"🧼 Последняя чистка: `{clean_time}`\n"
        message += f"⏰ Время: {self._get_current_time()}"
        
        return self.send_message(message, level="INFO")
    
    def send_backup_failed(self, label: str, error: str, error_code: Optional[int] = None) -> bool:
        """Отправить уведомление об ошибке бэкапа"""
        if not self.notify_backup_failed:
            return False
        
        message = (
            f"❌ *ОШИБКА БЭКАПА*\n"
            f"📝 Метка: `{label}`\n"
        )
        
        if error_code:
            message += f"🔧 Код ошибки: `{error_code}`\n"
        
        message += f"💥 Ошибка: `{error[:200]}`\n"
        message += f"⏰ Время: {self._get_current_time()}"
        
        return self.send_message(message, level="ERROR")
    
    def send_restore_started(self, label: str, destination: str) -> bool:
        """Отправить уведомление о начале восстановления"""
        message = (
            f"📥 *НАЧАЛО ВОССТАНОВЛЕНИЯ*\n"
            f"📝 Метка: `{label}`\n"
            f"📁 Назначение: `{destination}`\n"
            f"⏰ Время: {self._get_current_time()}"
        )
        return self.send_message(message, level="INFO")
    
    def send_restore_completed(self, label: str, destination: str, file_count: int = 0) -> bool:
        """Отправить уведомление о завершении восстановления"""
        message = (
            f"✅ *ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО*\n"
            f"📝 Метка: `{label}`\n"
            f"📁 Назначение: `{destination}`\n"
        )
        
        if file_count > 0:
            message += f"📄 Восстановлено файлов: `{file_count}`\n"
        
        message += f"⏰ Время: {self._get_current_time()}"
        
        return self.send_message(message, level="INFO")
    
    def send_tape_change_request(self, current_label: str, next_label: str) -> bool:
        """Отправить уведомление о необходимости смены ленты"""
        if not self.notify_tape_change:
            return False
        
        message = (
            f"🔔 *ТРЕБУЕТСЯ СМЕНА ЛЕНТЫ*\n"
            f"📼 Текущая: `{current_label}`\n"
            f"📼 Следующая: `{next_label}`\n"
            f"⏰ Время: {self._get_current_time()}"
        )
        return self.send_message(message, level="WARNING")
    
    def send_cleaning_request(self) -> bool:
        """Отправить уведомление о необходимости чистки"""
        if not self.notify_cleaning_required:
            return False
        
        message = (
            f"🧼 *ТРЕБУЕТСЯ ЧИСТКА ЛЕНТЫ!*\n"
            f"⚠️ Немедленно вставьте чистящую кассету (UCC)\n"
            f"⏰ Время: {self._get_current_time()}"
        )
        return self.send_message(message, level="ERROR")
    
    def send_system_check(self, status: Dict[str, Any]) -> bool:
        """Отправить результаты проверки системы"""
        message = (
            f"🔧 *ПРОВЕРКА СИСТЕМЫ LTO*\n"
            f"📅 Дата: {self._get_current_time()}\n"
            f"---\n"
        )
        
        # Добавляем результаты проверки
        for key, value in status.items():
            if isinstance(value, bool):
                emoji = "✅" if value else "❌"
                message += f"{emoji} {key}: {'Да' if value else 'Нет'}\n"
            elif isinstance(value, str):
                message += f"📋 {key}: `{value}`\n"
        
        return self.send_message(message, level="INFO")
    
    def send_daily_report(self, stats: Dict[str, Any]) -> bool:
        """Отправить ежедневный отчет"""
        message = (
            f"📊 *ЕЖЕДНЕВНЫЙ ОТЧЕТ LTO*\n"
            f"📅 Дата: {self._get_current_time()}\n"
            f"---\n"
        )
        
        # Добавляем статистику
        if 'backups_today' in stats:
            message += f"📁 Бэкапов сегодня: `{stats['backups_today']}`\n"
        
        if 'total_backups' in stats:
            message += f"📁 Всего бэкапов: `{stats['total_backups']}`\n"
        
        if 'tapes_used' in stats:
            message += f"📼 Использовано лент: `{stats['tapes_used']}`\n"
        
        if 'last_cleaning' in stats:
            message += f"🧼 Последняя чистка: `{stats['last_cleaning']}`\n"
        
        if 'errors_today' in stats:
            if stats['errors_today'] > 0:
                message += f"❌ Ошибок сегодня: `{stats['errors_today']}`\n"
            else:
                message += f"✅ Ошибок сегодня: `0`\n"
        
        return self.send_message(message, level="INFO")
    
    @staticmethod
    def _get_current_time() -> str:
        """Получить текущее время в формате строки"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")