#!/usr/bin/env python3
"""
Tape changer script for mbuffer
Called by mbuffer when tape needs to be changed
"""

import sys
import os
import logging
from pathlib import Path

# Add path for module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config_manager import ConfigManager
from hardware.tape_driver import TapeDriver
from notification.telegram_bot import TelegramBot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('/tmp/lto_tape_changer.log')
    ]
)
logger = logging.getLogger(__name__)

class TapeChanger:
    """Handles tape changing operations for mbuffer"""
    
    def __init__(self):
        try:
            self.config = ConfigManager()
            self.tape_driver = TapeDriver(self.config)
            self.bot = TelegramBot(self.config)
            logger.info("Tape changer initialized")
        except Exception as e:
            logger.error(f"Failed to initialize tape changer: {e}")
            raise
    
    def check_and_handle_cleaning(self) -> bool:
        """Check if cleaning is needed and handle it"""
        try:
            if self.tape_driver.check_cleaning_needed():
                print("🧼 Требуется чистка ленты!", file=sys.stderr)
                logger.warning("Tape cleaning required")
                
                # Send Telegram notification
                self.bot.send_cleaning_request()
                
                has_robot = self.config.get('hardware', 'has_robot', False)
                
                if not has_robot:
                    print("\n🧼 ПРИВОД ЗАПРОСИЛ ЧИСТКУ!", file=sys.stderr)
                    print("Вставьте чистящую кассету (UCC) и нажмите Enter...", file=sys.stderr)
                    
                    # Wait for user input
                    try:
                        input()
                    except EOFError:
                        # Handle case when called non-interactively
                        print("⏳ Ожидание 30 секунд...", file=sys.stderr)
                        import time
                        time.sleep(30)
                else:
                    # Handle robot cleaning
                    print(f"🤖 Автоматическая чистка через робота...", file=sys.stderr)
                    from hardware.robot_controller import RobotController
                    
                    robot_dev = self.config.get('hardware', 'robot_dev', '/dev/sg3')
                    robot = RobotController(robot_dev)
                    
                    # Assuming cleaning tape is in slot 0
                    cleaning_slot = 0
                    if robot.load_cleaning_tape(cleaning_slot):
                        print(f"✅ Чистящая лента загружена", file=sys.stderr)
                        
                        # Wait for cleaning to complete
                        print("⏳ Очистка... (ожидание 60 секунд)", file=sys.stderr)
                        import time
                        time.sleep(60)
                        
                        # Unload cleaning tape
                        robot.unload_tape(0, cleaning_slot)
                        print(f"✅ Чистящая лента выгружена", file=sys.stderr)
                    else:
                        print(f"❌ Не удалось загрузить чистящую ленту", file=sys.stderr)
                
                # Record cleaning time
                self.tape_driver.record_cleaning_time()
                logger.info("Tape cleaning completed")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error in cleaning handling: {e}")
            print(f"❌ Ошибка обработки чистки: {e}", file=sys.stderr)
            return False
    
    def request_tape_change(self) -> str:
        """Request tape change from operator"""
        try:
            # Play sound alert
            sound_enabled = self.config.get('notifications', 'sound_alerts', True)
            if sound_enabled:
                self.tape_driver.beep()
            
            print("\n" + "=" * 50, file=sys.stderr)
            print("🔔 ТРЕБУЕТСЯ СЛЕДУЮЩАЯ ЛЕНТА LTO", file=sys.stderr)
            print("=" * 50, file=sys.stderr)
            
            # Get current tapes if any
            current_tapes = self.tape_driver.get_used_tapes()
            if current_tapes != "N/A" and current_tapes:
                tape_list = current_tapes.split()
                if tape_list:
                    print(f"📼 Предыдущие ленты: {current_tapes}", file=sys.stderr)
            
            # Request new tape label
            while True:
                try:
                    print("📝 Введите метку следующей кассеты: ", file=sys.stderr, end='', flush=True)
                    
                    # Read input
                    label = sys.stdin.readline().strip()
                    
                    if label:
                        # Save tape information
                        with open(self.tape_driver.tmp_tapes_file, "a") as f:
                            f.write(f"{label} ")
                        
                        logger.info(f"New tape requested: {label}")
                        return label
                    else:
                        print("❌ Метка не может быть пустой. Попробуйте еще раз.", file=sys.stderr)
                        
                except KeyboardInterrupt:
                    print("\n⏹️  Прервано пользователем", file=sys.stderr)
                    raise
                except Exception as e:
                    print(f"❌ Ошибка ввода: {e}", file=sys.stderr)
                    raise
                    
        except Exception as e:
            logger.error(f"Error requesting tape change: {e}")
            raise
    
    def change_tape(self) -> bool:
        """Perform complete tape change procedure"""
        try:
            # Step 1: Check and handle cleaning
            self.check_and_handle_cleaning()
            
            # Step 2: Request new tape
            label = self.request_tape_change()
            
            # Step 3: Send Telegram notification
            self.bot.send_message(f"⏳ Ожидание ленты: `{label}`")
            self.bot.send_tape_change_request("previous", label)
            
            # Step 4: Wait for tape insertion
            print(f"\n📥 Вставьте ленту [{label}] и нажмите ENTER...", file=sys.stderr)
            try:
                sys.stdin.readline()
            except:
                # If stdin is closed, wait a bit
                import time
                time.sleep(5)
            
            # Step 5: Rewind new tape
            print(f"⏪ Перемотка новой ленты...", file=sys.stderr)
            if self.tape_driver.rewind():
                print(f"✅ Лента {label} установлена и перемотана", file=sys.stderr)
                logger.info(f"Tape {label} changed successfully")
                return True
            else:
                print(f"❌ Ошибка перемотки ленты {label}", file=sys.stderr)
                logger.error(f"Failed to rewind tape {label}")
                return False
                
        except KeyboardInterrupt:
            print("\n⏹️  Смена ленты прервана", file=sys.stderr)
            logger.warning("Tape change interrupted by user")
            raise
        except Exception as e:
            print(f"❌ Ошибка смены ленты: {e}", file=sys.stderr)
            logger.error(f"Tape change error: {e}")
            return False

def main():
    """Main function for tape changer"""
    try:
        # Initialize tape changer
        changer = TapeChanger()
        
        # Perform tape change
        success = changer.change_tape()
        
        if success:
            logger.info("Tape change completed successfully")
            return 0
        else:
            logger.error("Tape change failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Критическая ошибка смены ленты: {e}", file=sys.stderr)
        logger.critical(f"Critical tape change error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())