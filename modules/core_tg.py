#!/usr/bin/env python3
"""
Модуль для безопасной отправки уведомлений в Telegram
С маскировкой токенов, обработкой ошибок и логированием
"""

import requests
import logging
import hashlib
from typing import Optional, Tuple
from modules.lto_logger import get_logger

# Используем централизованный логгер
logger = get_logger()

class SecureConfig:
    """Безопасная загрузка конфигурации Telegram"""
    
    def __init__(self, config_manager):
        """
        Инициализация с использованием менеджера конфигурации
        
        Args:
            config_manager: Экземпляр LTOConfig из config_manager.py
        """
        self.config = config_manager
    
    def get_telegram_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Безопасное получение Telegram-учетных данных
        
        Returns:
            (токен, chat_id) или (None, None) если не настроено
        """
        try:
            # Получаем из конфигурации
            notification_config = self.config.notification
            
            if not notification_config.telegram_enabled:
                logger.debug("Telegram уведомления отключены в конфигурации")
                return None, None
            
            token = notification_config.telegram_token
            chat_id = notification_config.telegram_chat_id
            
            # Проверка заполненности
            if not token or not chat_id:
                logger.warning("Telegram токен или chat_id не настроены")
                return None, None
            
            # Проверка на значения по умолчанию
            if "ВАШ_ТОКЕН_БОТА" in token or "ВАШ_ID_ЧАТА" in chat_id:
                logger.warning("Используются значения Telegram по умолчанию")
                return None, None
            
            logger.debug(f"Токен получен: {self.mask_token(token)}, Chat ID: {chat_id[:4]}...")
            return token, chat_id
            
        except Exception as e:
            logger.error(f"Ошибка чтения Telegram конфигурации: {e}")
            return None, None
    
    @staticmethod
    def mask_token(token: str) -> str:
        """
        Маскирует токен для безопасного отображения в логах
        
        Args:
            token: Токен Telegram бота
            
        Returns:
            Маскированный токен (первые 4 и последние 4 символа)
        """
        if not token or len(token) < 10:
            return "[INVALID_TOKEN]"
        return f"{token[:4]}...{token[-4:]}"
    
    @staticmethod
    def obfuscate_token(token: str) -> str:
        """
        Обфускация токена для дополнительной безопасности
        
        Args:
            token: Исходный токен
            
        Returns:
            Хэш токена (первые 16 символов SHA256)
        """
        return hashlib.sha256(token.encode()).hexdigest()[:16]
    
    def validate_telegram_config(self) -> Tuple[bool, str]:
        """
        Проверка валидности Telegram конфигурации
        
        Returns:
            (валиден?, сообщение об ошибке)
        """
        token, chat_id = self.get_telegram_credentials()
        
        if not token or not chat_id:
            return False, "Токен или Chat ID не настроены"
        
        # Проверка формата токена
        if len(token) < 30:
            return False, f"Токен слишком короткий: {self.mask_token(token)}"
        
        # Проверка формата chat_id (должен быть числом)
        try:
            int(chat_id)
        except ValueError:
            return False, f"Chat ID не является числом: {chat_id}"
        
        return True, "Конфигурация валидна"

# Глобальный экземпляр конфигурации
_config_manager = None

def get_config_manager(config_instance=None):
    """
    Получение экземпляра менеджера конфигурации Telegram
    
    Args:
        config_instance: Экземпляр LTOConfig (если None, будет создан)
        
    Returns:
        Экземпляр SecureConfig
    """
    global _config_manager
    
    if _config_manager is None:
        if config_instance is None:
            # Импортируем здесь, чтобы избежать циклического импорта
            from modules.config_manager import get_config_instance
            config_instance = get_config_instance()
        
        _config_manager = SecureConfig(config_instance)
    
    return _config_manager

def send_tg(message: str, max_retries: int = 3, timeout: int = 15) -> bool:
    """
    Отправка сообщения в Telegram с улучшенной обработкой ошибок
    
    Args:
        message: Текст сообщения
        max_retries: Максимальное количество попыток
        timeout: Таймаут в секундах
        
    Returns:
        True если отправка успешна
    """
    config_manager = get_config_manager()
    token, chat_id = config_manager.get_telegram_credentials()
    
    # Если конфиг не настроен - тихо выходим
    if not token or not chat_id:
        logger.debug("Telegram не настроен, пропускаем отправку")
        return False
    
    # Проверка длины сообщения (ограничение Telegram API)
    if len(message) > 4096:
        message = message[:4000] + "...\n[сообщение обрезано]"
        logger.debug("Сообщение обрезано до 4000 символов")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_notification": False
    }
    
    logger.debug(f"Отправка в Telegram: {message[:100]}...")
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                data=payload,
                timeout=timeout,
                headers={'User-Agent': 'LTO-Backup-System/1.0'}
            )
            
            response.raise_for_status()
            
            result = response.json()
            if result.get("ok"):
                logger.debug(f"Сообщение отправлено успешно (попытка {attempt+1})")
                return True
            else:
                error_msg = result.get("description", "Unknown error")
                logger.error(f"Telegram API error: {error_msg}")
                
                # Если ошибка авторизации - не пытаемся снова
                if "401" in error_msg or "Unauthorized" in error_msg:
                    logger.error(f"Неверный токен: {config_manager.mask_token(token)}")
                    break
                    
        except requests.exceptions.Timeout:
            logger.warning(f"Таймаут отправки Telegram (попытка {attempt + 1}/{max_retries})")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Ошибка соединения Telegram (попытка {attempt + 1}/{max_retries})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса Telegram: {e}")
            break
        except Exception as e:
            logger.error(f"Неожиданная ошибка отправки Telegram: {e}")
            break
    
    logger.error(f"Не удалось отправить сообщение после {max_retries} попыток")
    return False

def send_tg_with_retry(message: str, max_retries: int = 5, 
                      initial_delay: float = 1.0, backoff_factor: float = 2.0) -> bool:
    """
    Отправка сообщения с экспоненциальной отсрочкой при повторах
    
    Args:
        message: Текст сообщения
        max_retries: Максимальное количество попыток
        initial_delay: Начальная задержка в секундах
        backoff_factor: Множитель для экспоненциальной отсрочки
        
    Returns:
        True если отправка успешна
    """
    import time
    
    for attempt in range(max_retries):
        success = send_tg(message, max_retries=1, timeout=15)
        
        if success:
            return True
        
        # Если это не последняя попытка, ждем перед повторной отправкой
        if attempt < max_retries - 1:
            delay = initial_delay * (backoff_factor ** attempt)
            logger.info(f"Повторная отправка через {delay:.1f} секунд...")
            time.sleep(delay)
    
    return False

def send_telegram_alert(alert_type: str, message: str, 
                       details: str = "", critical: bool = False) -> bool:
    """
    Отправка структурированного оповещения в Telegram
    
    Args:
        alert_type: Тип оповещения (INFO, WARNING, ERROR, SUCCESS)
        message: Основное сообщение
        details: Детали оповещения
        critical: Критическое оповещение (не будет отключено уведомление)
        
    Returns:
        True если отправка успешна
    """
    # Эмодзи для разных типов оповещений
    emoji_map = {
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'SUCCESS': '✅',
        'BACKUP': '💾',
        'RESTORE': '🔄',
        'CLEAN': '🧼',
        'TAPE': '📼'
    }
    
    emoji = emoji_map.get(alert_type, '📢')
    
    # Формируем сообщение
    formatted_message = f"{emoji} *{alert_type}*\n\n{message}"
    
    if details:
        formatted_message += f"\n\n```\n{details[:500]}\n```"
    
    # Для критических оповещений не отключаем уведомления
    if not critical:
        formatted_message += f"\n\n_Система: LTO Backup_"
    
    # Отправляем
    return send_tg_with_retry(formatted_message)

def send_backup_notification(label: str, status: str, 
                           details: str = "", tapes_used: list = None) -> bool:
    """
    Отправка уведомления о завершении бэкапа
    
    Args:
        label: Метка бэкапа
        status: Статус (SUCCESS, FAILED, IN_PROGRESS)
        details: Детали выполнения
        tapes_used: Список использованных лент
        
    Returns:
        True если отправка успешна
    """
    status_emoji = {
        'SUCCESS': '✅',
        'FAILED': '❌',
        'IN_PROGRESS': '⏳'
    }
    
    emoji = status_emoji.get(status, '📊')
    
    message = f"{emoji} *БЭКАП: {label}*\nСтатус: {status}\n"
    
    if tapes_used:
        tapes_str = ', '.join(tapes_used)
        message += f"Ленты: {tapes_str}\n"
    
    if details:
        message += f"\nДетали:\n```\n{details[:300]}\n```"
    
    return send_telegram_alert('BACKUP', message, critical=(status == 'FAILED'))

def send_tape_notification(event: str, tape_label: str = "", 
                          details: str = "", is_error: bool = False) -> bool:
    """
    Отправка уведомления о событии с лентой
    
    Args:
        event: Событие (LOAD, UNLOAD, CLEAN, ERROR)
        tape_label: Метка ленты
        details: Детали события
        is_error: Является ли событие ошибкой
        
    Returns:
        True если отправка успешна
    """
    event_emoji = {
        'LOAD': '📥',
        'UNLOAD': '📤',
        'CLEAN': '🧼',
        'ERROR': '⚠️',
        'CHANGE': '🔄',
        'REWIND': '⏪'
    }
    
    emoji = event_emoji.get(event, '📼')
    
    message = f"{emoji} *СОБЫТИЕ ЛЕНТЫ*\n"
    
    if tape_label:
        message += f"Лента: `{tape_label}`\n"
    
    message += f"Событие: {event}\n"
    
    if details:
        message += f"\n```\n{details[:200]}\n```"
    
    alert_type = 'ERROR' if is_error else 'TAPE'
    return send_telegram_alert(alert_type, message, critical=is_error)

def test_telegram_connection(config_instance=None) -> bool:
    """
    Тестирование соединения с Telegram
    
    Args:
        config_instance: Экземпляр LTOConfig для тестирования
        
    Returns:
        True если соединение успешно
    """
    if config_instance is None:
        from modules.config_manager import get_config_instance
        config_instance = get_config_instance()
    
    config_manager = SecureConfig(config_instance)
    
    print("🔍 Проверка конфигурации Telegram...")
    
    # Проверка валидности конфига
    is_valid, message = config_manager.validate_telegram_config()
    if not is_valid:
        print(f"❌ {message}")
        return False
    
    print("✅ Конфигурация валидна")
    
    # Пробная отправка
    import os
    from datetime import datetime
    
    test_msg = (f"🧪 *Тестовое сообщение от LTO Backup System*\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Хост: {os.uname().nodename if hasattr(os, 'uname') else 'unknown'}")
    
    print("📤 Отправка тестового сообщения...")
    success = send_tg(test_msg)
    
    if success:
        print("✅ Тестовое сообщение отправлено успешно!")
        return True
    else:
        print("❌ Не удалось отправить тестовое сообщение")
        return False

def send_daily_report(backup_count: int = 0, error_count: int = 0, 
                     total_size: str = "0", last_backup: str = "N/A") -> bool:
    """
    Отправка ежедневного отчета
    
    Args:
        backup_count: Количество бэкапов за день
        error_count: Количество ошибок за день
        total_size: Общий размер бэкапов
        last_backup: Время последнего бэкапа
        
    Returns:
        True если отправка успешна
    """
    from datetime import datetime
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    message = (f"📊 *ЕЖЕДНЕВНЫЙ ОТЧЕТ LTO BACKUP*\n"
               f"Дата: {today}\n\n"
               f"✅ Успешных бэкапов: {backup_count}\n"
               f"❌ Ошибок: {error_count}\n"
               f"📦 Общий размер: {total_size}\n"
               f"⏰ Последний бэкап: {last_backup}\n\n"
               f"_Система работает штатно_")
    
    return send_tg(message)

# Декоратор для логирования отправки уведомлений
def logged_notification(func):
    """
    Декоратор для логирования отправки уведомлений
    """
    def wrapper(*args, **kwargs):
        logger.debug(f"Отправка уведомления: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            if result:
                logger.debug(f"Уведомление отправлено успешно: {func.__name__}")
            else:
                logger.warning(f"Не удалось отправить уведомление: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления {func.__name__}: {e}")
            return False
    return wrapper

# Применяем декоратор к основным функциям
send_tg = logged_notification(send_tg)
send_telegram_alert = logged_notification(send_telegram_alert)
send_backup_notification = logged_notification(send_backup_notification)
send_tape_notification = logged_notification(send_tape_notification)

if __name__ == "__main__":
    # Тестирование модуля
    import sys
    
    # Настройка консольного логирования для тестов
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.system_logger.addHandler(console_handler)
    
    print("🧪 Тестирование core_tg.py")
    print("=" * 60)
    
    if "--test" in sys.argv:
        success = test_telegram_connection()
        sys.exit(0 if success else 1)
    else:
        print("Использование:")
        print("  python3 core_tg.py --test  # Тестирование соединения с Telegram")
        print("\nДоступные функции:")
        print("  send_tg(message)                    # Простая отправка сообщения")
        print("  send_telegram_alert(type, message)  # Структурированное оповещение")
        print("  send_backup_notification(...)       # Уведомление о бэкапе")
        print("  send_tape_notification(...)         # Уведомление о событии ленты")