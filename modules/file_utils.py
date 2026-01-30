#!/usr/bin/env python3
"""
Утилиты для безопасной работы с файлами с поддержкой UTF-8
Обработка различных кодировок, безопасные операции с путями
"""

import os
import sys
import codecs
import chardet
from pathlib import Path
import logging
from typing import Optional, Union, List, Dict, Any
import traceback

logger = logging.getLogger('file_utils')

class FileEncodingError(Exception):
    """Исключение для ошибок кодировки файлов"""
    pass

class SafeFileHandler:
    """Безопасный обработчик файлов с автоматическим определением кодировки"""
    
    DEFAULT_ENCODING = 'utf-8'
    FALLBACK_ENCODINGS = ['utf-8', 'cp1251', 'koi8-r', 'iso-8859-5', 'ascii']
    
    @staticmethod
    def detect_encoding(file_path: str, sample_size: int = 1024) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(sample_size)
            
            if not raw_data:
                return SafeFileHandler.DEFAULT_ENCODING
            
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            
            if encoding and confidence > 0.7:
                logger.debug(f"Определена кодировка {encoding} с уверенностью {confidence:.2%} для {file_path}")
                return encoding.lower()
            else:
                logger.warning(f"Не удалось определить кодировку для {file_path}, использую {SafeFileHandler.DEFAULT_ENCODING}")
                return SafeFileHandler.DEFAULT_ENCODING
                
        except Exception as e:
            logger.error(f"Ошибка определения кодировки {file_path}: {e}")
            return SafeFileHandler.DEFAULT_ENCODING
    
    @staticmethod
    def read_file(file_path: str, encoding: str = None, 
                 errors: str = 'replace') -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        if encoding is None:
            encoding = SafeFileHandler.detect_encoding(file_path)
        
        try:
            with codecs.open(file_path, 'r', encoding=encoding, errors=errors) as f:
                content = f.read()
            
            logger.debug(f"Файл прочитан: {file_path} (кодировка: {encoding}, размер: {len(content)} символов)")
            return content
            
        except UnicodeDecodeError as e:
            logger.warning(f"Ошибка декодирования {file_path} как {encoding}, пробую другие кодировки...")
            
            for alt_encoding in SafeFileHandler.FALLBACK_ENCODINGS:
                if alt_encoding == encoding:
                    continue
                    
                try:
                    with codecs.open(file_path, 'r', encoding=alt_encoding, errors=errors) as f:
                        content = f.read()
                    
                    logger.info(f"Файл {file_path} прочитан как {alt_encoding} после неудачи с {encoding}")
                    return content
                    
                except UnicodeDecodeError:
                    continue
            
            raise FileEncodingError(f"Не удалось декодировать файл {file_path} ни в одной из поддерживаемых кодировок")
            
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            raise
    
    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = 'utf-8',
                  errors: str = 'strict', ensure_utf8: bool = True) -> bool:
        try:
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"Создана директория: {directory}")
            
            if ensure_utf8 and encoding.lower() == 'utf-8':
                if content and not content.startswith(codecs.BOM_UTF8.decode('utf-8')):
                    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                        content = codecs.BOM_UTF8.decode('utf-8') + content
            
            with codecs.open(file_path, 'w', encoding=encoding, errors=errors) as f:
                f.write(content)
            
            logger.debug(f"Файл записан: {file_path} (кодировка: {encoding}, размер: {len(content)} символов)")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка записи файла {file_path}: {e}")
            return False
    
    @staticmethod
    def read_lines(file_path: str, encoding: str = None, 
                  strip_lines: bool = True, skip_empty: bool = False) -> List[str]:
        content = SafeFileHandler.read_file(file_path, encoding)
        lines = content.splitlines()
        
        if strip_lines:
            lines = [line.strip() for line in lines]
        
        if skip_empty:
            lines = [line for line in lines if line]
        
        return lines
    
    @staticmethod
    def convert_file_encoding(source_path: str, target_path: str, 
                            source_encoding: str = None, target_encoding: str = 'utf-8'):
        try:
            content = SafeFileHandler.read_file(source_path, source_encoding)
            success = SafeFileHandler.write_file(target_path, content, target_encoding)
            
            if success:
                logger.info(f"Конвертирован {source_path} -> {target_path} ({target_encoding})")
            return success
            
        except Exception as e:
            logger.error(f"Ошибка конвертации {source_path}: {e}")
            return False
    
    @staticmethod
    def safe_path(path: str) -> str:
        try:
            normalized = os.path.normpath(path)
            normalized.encode('utf-8')
            return normalized
            
        except UnicodeEncodeError:
            logger.warning(f"Путь содержит не-ASCII символы: {path}")
            
            for encoding in ['utf-8', 'cp1251', 'koi8-r']:
                try:
                    return path.encode(encoding).decode(encoding)
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
            
            logger.error(f"Не удалось обработать путь: {path}, заменяю не-ASCII символы")
            return path.encode('ascii', 'replace').decode('ascii')

class ManifestProcessor:
    """Обработчик файлов манифестов с поддержкой UTF-8"""
    
    @staticmethod
    def read_manifest(manifest_path: str) -> Dict[str, Any]:
        try:
            content = SafeFileHandler.read_file(manifest_path)
            lines = SafeFileHandler.read_lines(manifest_path, skip_empty=True)
            
            manifest_data = {
                'path': manifest_path,
                'encoding': SafeFileHandler.detect_encoding(manifest_path),
                'total_files': len(lines),
                'files': lines,
                'raw_content': content,
                'size': os.path.getsize(manifest_path)
            }
            
            filename = os.path.basename(manifest_path)
            if '_' in filename and filename.endswith('.txt'):
                parts = filename[:-4].split('_')
                if len(parts) >= 3:
                    manifest_data['date'] = f"{parts[0]}_{parts[1]}"
                    manifest_data['label'] = '_'.join(parts[2:])
            
            return manifest_data
            
        except Exception as e:
            logger.error(f"Ошибка чтения манифеста {manifest_path}: {e}")
            return {}
    
    @staticmethod
    def create_manifest(output_path: str, file_list: List[str], 
                       label: str = "") -> bool:
        try:
            content = codecs.BOM_UTF8.decode('utf-8')
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content += f"# Манифест бэкапа\n"
            content += f"# Дата создания: {timestamp}\n"
            content += f"# Метка: {label}\n"
            content += f"# Всего файлов: {len(file_list)}\n"
            content += "#" * 80 + "\n\n"
            
            for file_path in sorted(file_list):
                safe_path = SafeFileHandler.safe_path(file_path)
                content += safe_path + "\n"
            
            success = SafeFileHandler.write_file(output_path, content, ensure_utf8=True)
            
            if success:
                logger.info(f"Создан манифест: {output_path} ({len(file_list)} файлов)")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка создания манифеста {output_path}: {e}")
            return False

class RegistryFileHandler:
    """Обработчик файлов реестра с поддержкой UTF-8"""
    
    @staticmethod
    def read_registry(registry_path: str) -> List[Dict[str, str]]:
        if not os.path.exists(registry_path):
            logger.warning(f"Файл реестра не найден: {registry_path}")
            return []
        
        try:
            content = SafeFileHandler.read_file(registry_path)
            lines = SafeFileHandler.read_lines(registry_path, skip_empty=True)
            
            entries = []
            for line_num, line in enumerate(lines, 1):
                if line.strip().startswith('#'):
                    continue
                
                parts = [part.strip() for part in line.split(';')]
                
                if len(parts) >= 5:
                    entry = {
                        'timestamp': parts[0],
                        'label': parts[1],
                        'tapes': parts[2],
                        'file_index': parts[3],
                        'manifest': parts[4],
                        'line_number': line_num
                    }
                    entries.append(entry)
                else:
                    logger.warning(f"Пропущена строка {line_num}: неверный формат")
            
            logger.debug(f"Прочитан реестр: {registry_path} ({len(entries)} записей)")
            return entries
            
        except Exception as e:
            logger.error(f"Ошибка чтения реестра {registry_path}: {e}")
            return []
    
    @staticmethod
    def write_registry_entry(registry_path: str, entry: Dict[str, str]) -> bool:
        try:
            entries = RegistryFileHandler.read_registry(registry_path)
            entries.append(entry)
            
            lines = []
            for e in entries:
                line = f"{e.get('timestamp', '')};{e.get('label', '')};"
                line += f"{e.get('tapes', '')};{e.get('file_index', '')};"
                line += f"{e.get('manifest', '')}"
                lines.append(line)
            
            content = '\n'.join(lines)
            success = SafeFileHandler.write_file(registry_path, content, ensure_utf8=True)
            
            if success:
                logger.debug(f"Добавлена запись в реестр: {entry.get('label', 'N/A')}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка записи в реестр {registry_path}: {e}")
            return False

def safe_open(file_path: str, mode: str = 'r', encoding: str = 'utf-8', **kwargs):
    if 'b' in mode:
        return open(file_path, mode, **kwargs)
    else:
        return codecs.open(file_path, mode, encoding=encoding, **kwargs)

def ensure_utf8_string(text: str) -> str:
    if isinstance(text, bytes):
        try:
            return text.decode('utf-8')
        except UnicodeDecodeError:
            for encoding in SafeFileHandler.FALLBACK_ENCODINGS:
                try:
                    return text.decode(encoding)
                except UnicodeDecodeError:
                    continue
            return text.decode('utf-8', errors='replace')
    return text

def normalize_path_encoding(path: str) -> str:
    return SafeFileHandler.safe_path(path)

if __name__ == "__main__":
    import tempfile
    
    print("🧪 Тестирование file_utils.py")
    print("=" * 60)
    
    test_content = "Тестовый файл с русским текстом\nПроверка кодировки UTF-8\nСпецсимволы: €§¶∞"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(test_content)
        test_file = f.name
    
    print(f"📝 Создан тестовый файл: {test_file}")
    
    encoding = SafeFileHandler.detect_encoding(test_file)
    print(f"🔍 Определена кодировка: {encoding}")
    
    content = SafeFileHandler.read_file(test_file)
    print(f"📖 Прочитано символов: {len(content)}")
    
    new_file = test_file + '.new'
    success = SafeFileHandler.write_file(new_file, content + "\nДобавленная строка")
    print(f"📝 Запись файла: {'✅' if success else '❌'}")
    
    test_path = "/тест/директория/с русскими символами/file.txt"
    safe_path = SafeFileHandler.safe_path(test_path)
    print(f"🛡️  Безопасный путь: {safe_path}")
    
    os.unlink(test_file)
    if os.path.exists(new_file):
        os.unlink(new_file)
    
    print("\n✅ Тестирование завершено")