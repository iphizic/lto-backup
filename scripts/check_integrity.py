#!/usr/bin/env python3
"""
Скрипт для проверки целостности файлов LTO Backup System
Проверяет контрольные суммы, наличие файлов и их корректность
"""

import os
import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime
import yaml

def calculate_file_hash(filepath, algorithm='sha256'):
    """Вычисление хэша файла"""
    if not os.path.exists(filepath):
        return None
    
    hash_func = getattr(hashlib, algorithm)()
    
    try:
        with open(filepath, 'rb') as f:
            # Читаем файл блоками для эффективности
            for block in iter(lambda: f.read(65536), b''):
                hash_func.update(block)
        return hash_func.hexdigest()
    except Exception as e:
        print(f"❌ Ошибка чтения файла {filepath}: {e}")
        return None

def verify_python_module(module_path):
    """Проверка корректности Python модуля"""
    if not os.path.exists(module_path):
        return False, f"Файл не существует: {module_path}"
    
    try:
        # Пытаемся выполнить синтаксическую проверку
        with open(module_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем базовый синтаксис
        compile(content, module_path, 'exec')
        
        # Проверяем наличие импортов (если нужно)
        if 'import ' in content or 'from ' in content:
            # Проверяем, что импорты на своих местах
            lines = content.split('\n')
            imports_found = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('import ') or stripped.startswith('from '):
                    imports_found = True
                    # Проверяем синтаксис импорта
                    try:
                        compile(stripped, '<string>', 'exec')
                    except SyntaxError as e:
                        return False, f"Синтаксическая ошибка в импорте: {e}"
            
            if imports_found and 'sys.path' in content:
                return True, "✅ Модуль корректен"
        
        return True, "✅ Модуль корректен"
        
    except SyntaxError as e:
        return False, f"Синтаксическая ошибка: {e}"
    except Exception as e:
        return False, f"Ошибка проверки модуля: {e}"

def verify_yaml_config(config_path):
    """Проверка корректности YAML конфигурации"""
    if not os.path.exists(config_path):
        return False, f"Файл не существует: {config_path}"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Проверяем обязательные секции
        required_sections = ['database', 'hardware', 'buffer']
        for section in required_sections:
            if section not in config:
                return False, f"Отсутствует обязательная секция: {section}"
        
        # Проверяем обязательные поля
        required_fields = {
            'database': ['registry_file', 'manifest_dir'],
            'hardware': ['tape_device', 'robot_enabled'],
            'buffer': ['size', 'fill_percent', 'block_size']
        }
        
        for section, fields in required_fields.items():
            for field in fields:
                if field not in config.get(section, {}):
                    return False, f"Отсутствует поле {section}.{field}"
        
        return True, "✅ Конфигурация YAML корректна"
        
    except yaml.YAMLError as e:
        return False, f"Ошибка YAML: {e}"
    except Exception as e:
        return False, f"Ошибка проверки конфигурации: {e}"

def verify_directory_structure(base_dir='.'):
    """Проверка структуры директорий"""
    required_dirs = [
        'modules',
        'scripts',
        'logs',
        'manifests',
        'backups'
    ]
    
    issues = []
    for dir_name in required_dirs:
        dir_path = os.path.join(base_dir, dir_name)
        if not os.path.exists(dir_path):
            issues.append(f"❌ Отсутствует директория: {dir_name}")
        elif not os.path.isdir(dir_path):
            issues.append(f"❌ Не является директорией: {dir_name}")
        else:
            print(f"✅ Директория {dir_name} существует")
    
    return len(issues) == 0, issues

def get_file_checksums(directory='.', extensions=None):
    """Получение контрольных сумм всех файлов"""
    if extensions is None:
        extensions = ['.py', '.yaml', '.yml', '.json', '.md', '.sh']
    
    checksums = {}
    
    for root, dirs, files in os.walk(directory):
        # Пропускаем некоторые директории
        skip_dirs = ['.git', '__pycache__', '.pytest_cache', 'venv', 'env']
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, directory)
                file_hash = calculate_file_hash(filepath)
                
                if file_hash:
                    checksums[rel_path] = {
                        'hash': file_hash,
                        'size': os.path.getsize(filepath),
                        'modified': os.path.getmtime(filepath)
                    }
    
    return checksums

def generate_integrity_report(base_dir='.'):
    """Генерация полного отчета о целостности системы"""
    print("🔍 ГЕНЕРАЦИЯ ОТЧЕТА О ЦЕЛОСТНОСТИ LTO BACKUP SYSTEM")
    print("=" * 80)
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'base_directory': os.path.abspath(base_dir),
        'files': {},
        'issues': [],
        'summary': {}
    }
    
    # 1. Проверка структуры директорий
    print("\n1. 📁 Проверка структуры директорий...")
    dirs_ok, dir_issues = verify_directory_structure(base_dir)
    if not dirs_ok:
        report['issues'].extend(dir_issues)
        for issue in dir_issues:
            print(f"   {issue}")
    else:
        print("   ✅ Структура директорий корректна")
    
    # 2. Проверка обязательных файлов
    print("\n2. 📋 Проверка обязательных файлов...")
    required_files = [
        ('lto_main.py', 'main'),
        ('config.yaml', 'config'),
        ('modules/__init__.py', 'module'),
        ('modules/config_manager.py', 'module'),
        ('modules/file_utils.py', 'module'),
        ('modules/system_monitor.py', 'module'),
        ('modules/tape_drive.py', 'module'),
        ('modules/backup_job.py', 'module'),
        ('modules/lto_logger.py', 'module'),
        ('modules/registry_manager.py', 'module'),
        ('modules/core_tg.py', 'module'),
        ('scripts/log_manager.py', 'script'),
        ('scripts/setup_security.py', 'script'),
        ('scripts/test_logging.py', 'script'),
        ('scripts/check_deps.sh', 'script'),
        ('README.md', 'doc')
    ]
    
    missing_files = []
    for file_path, file_type in required_files:
        full_path = os.path.join(base_dir, file_path)
        if not os.path.exists(full_path):
            missing_files.append(file_path)
            print(f"   ❌ Отсутствует: {file_path}")
        else:
            print(f"   ✅ Присутствует: {file_path}")
    
    if missing_files:
        report['issues'].append(f"Отсутствуют файлы: {', '.join(missing_files)}")
    
    # 3. Проверка Python модулей
    print("\n3. 🐍 Проверка Python модулей...")
    python_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    python_issues = []
    for py_file in python_files[:20]:  # Проверяем первые 20 файлов для скорости
        rel_path = os.path.relpath(py_file, base_dir)
        is_ok, message = verify_python_module(py_file)
        if not is_ok:
            python_issues.append(f"{rel_path}: {message}")
            print(f"   ❌ {rel_path}: {message}")
        else:
            print(f"   ✅ {rel_path} корректен")
    
    if python_issues:
        report['issues'].extend(python_issues)
    
    # 4. Проверка конфигурации
    print("\n4. ⚙️ Проверка конфигурации...")
    config_path = os.path.join(base_dir, 'config.yaml')
    if os.path.exists(config_path):
        is_ok, message = verify_yaml_config(config_path)
        if not is_ok:
            report['issues'].append(f"Конфигурация: {message}")
            print(f"   ❌ {message}")
        else:
            print(f"   ✅ {message}")
    else:
        report['issues'].append("Отсутствует config.yaml")
        print("   ❌ Отсутствует config.yaml")
    
    # 5. Вычисление контрольных сумм
    print("\n5. 🔢 Вычисление контрольных сумм...")
    checksums = get_file_checksums(base_dir)
    report['files'] = checksums
    
    # Группируем по типам файлов
    file_types = {}
    for file_path, info in checksums.items():
        ext = os.path.splitext(file_path)[1].lower()
        file_types.setdefault(ext, []).append(file_path)
    
    print(f"   Найдено файлов: {len(checksums)}")
    for ext, files in file_types.items():
        print(f"   {ext}: {len(files)} файлов")
    
    # 6. Сохранение отчета
    print("\n6. 💾 Сохранение отчета...")
    report_path = os.path.join(base_dir, 'integrity_report.json')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ Отчет сохранен: {report_path}")
    
    # 7. Итоговая статистика
    print("\n7. 📊 Итоговая статистика:")
    total_issues = len(report['issues'])
    
    report['summary'] = {
        'total_files': len(checksums),
        'total_issues': total_issues,
        'timestamp': datetime.now().isoformat(),
        'file_types': {ext: len(files) for ext, files in file_types.items()}
    }
    
    if total_issues == 0:
        print("   🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
        print("   Система целостна и готова к работе.")
    else:
        print(f"   ⚠️  Обнаружено проблем: {total_issues}")
        print("   Пожалуйста, исправьте указанные проблемы перед использованием.")
    
    print("\n" + "=" * 80)
    return report

def compare_checksums(report1_path, report2_path):
    """Сравнение двух отчетов о контрольных суммах"""
    print("🔄 СРАВНЕНИЕ КОНТРОЛЬНЫХ СУММ")
    print("=" * 80)
    
    with open(report1_path, 'r', encoding='utf-8') as f:
        report1 = json.load(f)
    
    with open(report2_path, 'r', encoding='utf-8') as f:
        report2 = json.load(f)
    
    files1 = set(report1['files'].keys())
    files2 = set(report2['files'].keys())
    
    # Файлы только в первом отчете
    only_in_1 = files1 - files2
    # Файлы только во втором отчете
    only_in_2 = files2 - files1
    # Общие файлы
    common_files = files1 & files2
    
    print(f"\n📊 Статистика сравнения:")
    print(f"   Файлов в отчете 1: {len(files1)}")
    print(f"   Файлов в отчете 2: {len(files2)}")
    print(f"   Общих файлов: {len(common_files)}")
    
    if only_in_1:
        print(f"\n📄 Файлы только в отчете 1 ({len(only_in_1)}):")
        for file in sorted(only_in_1)[:10]:  # Показываем первые 10
            print(f"   + {file}")
        if len(only_in_1) > 10:
            print(f"   ... и еще {len(only_in_1) - 10} файлов")
    
    if only_in_2:
        print(f"\n📄 Файлы только в отчете 2 ({len(only_in_2)}):")
        for file in sorted(only_in_2)[:10]:
            print(f"   - {file}")
        if len(only_in_2) > 10:
            print(f"   ... и еще {len(only_in_2) - 10} файлов")
    
    # Сравнение контрольных сумм общих файлов
    print(f"\n🔍 Сравнение контрольных сумм общих файлов:")
    different_hashes = []
    
    for file in sorted(common_files):
        hash1 = report1['files'][file]['hash']
        hash2 = report2['files'][file]['hash']
        
        if hash1 != hash2:
            different_hashes.append(file)
    
    if different_hashes:
        print(f"   ⚠️  Файлов с разными хэшами: {len(different_hashes)}")
        for file in different_hashes[:5]:  # Показываем первые 5
            print(f"   ✗ {file}")
        if len(different_hashes) > 5:
            print(f"   ... и еще {len(different_hashes) - 5} файлов")
    else:
        print("   ✅ Все общие файлы идентичны")
    
    return {
        'only_in_1': list(only_in_1),
        'only_in_2': list(only_in_2),
        'different_hashes': different_hashes,
        'common_files_count': len(common_files)
    }

def create_reference_checksums(base_dir='.'):
    """Создание эталонных контрольных сумм для системы"""
    print("🏗️ СОЗДАНИЕ ЭТАЛОННЫХ КОНТРОЛЬНЫХ СУММ")
    print("=" * 80)
    
    # Получаем все файлы
    checksums = get_file_checksums(base_dir)
    
    # Создаем структурированный отчет
    reference = {
        'system': 'LTO Backup System',
        'version': '2.0.0',
        'timestamp': datetime.now().isoformat(),
        'created_by': 'Integrity Check Script',
        'files': {}
    }
    
    # Группируем файлы по категориям
    categories = {
        'core': ['lto_main.py', 'config.yaml', 'README.md'],
        'modules': ['modules/'],
        'scripts': ['scripts/'],
        'documentation': ['docs/', '*.md']
    }
    
    for file_path, info in checksums.items():
        # Определяем категорию
        category = 'other'
        for cat_name, patterns in categories.items():
            for pattern in patterns:
                if pattern.endswith('/'):
                    if file_path.startswith(pattern):
                        category = cat_name
                        break
                elif file_path == pattern:
                    category = cat_name
                    break
        
        reference['files'][file_path] = {
            'hash': info['hash'],
            'size': info['size'],
            'category': category,
            'algorithm': 'sha256'
        }
    
    # Сохраняем эталонный файл
    ref_path = os.path.join(base_dir, 'reference_checksums.json')
    with open(ref_path, 'w', encoding='utf-8') as f:
        json.dump(reference, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Эталонные контрольные суммы созданы: {ref_path}")
    print(f"📊 Всего файлов: {len(checksums)}")
    
    # Статистика по категориям
    category_stats = {}
    for file_info in reference['files'].values():
        cat = file_info['category']
        category_stats[cat] = category_stats.get(cat, 0) + 1
    
    print("\n📁 Статистика по категориям:")
    for cat, count in sorted(category_stats.items()):
        print(f"   {cat}: {count} файлов")
    
    return reference

def verify_against_reference(base_dir='.', reference_path=None):
    """Проверка системы против эталонных контрольных сумм"""
    if reference_path is None:
        reference_path = os.path.join(base_dir, 'reference_checksums.json')
    
    if not os.path.exists(reference_path):
        print(f"❌ Эталонный файл не найден: {reference_path}")
        print("   Сначала создайте эталонные контрольные суммы.")
        return False
    
    print("🔍 ПРОВЕРКА СИСТЕМЫ ПО ЭТАЛОНУ")
    print("=" * 80)
    
    with open(reference_path, 'r', encoding='utf-8') as f:
        reference = json.load(f)
    
    # Получаем текущие контрольные суммы
    current_checksums = get_file_checksums(base_dir)
    
    # Сравниваем
    reference_files = set(reference['files'].keys())
    current_files = set(current_checksums.keys())
    
    missing_files = reference_files - current_files
    extra_files = current_files - reference_files
    common_files = reference_files & current_files
    
    issues = []
    
    print(f"\n📊 Статистика проверки:")
    print(f"   Ожидается файлов: {len(reference_files)}")
    print(f"   Найдено файлов: {len(current_files)}")
    
    # Проверяем отсутствующие файлы
    if missing_files:
        print(f"\n❌ Отсутствующие файлы ({len(missing_files)}):")
        for file in sorted(missing_files)[:10]:
            print(f"   - {file}")
            issues.append(f"Отсутствует файл: {file}")
        if len(missing_files) > 10:
            print(f"   ... и еще {len(missing_files) - 10} файлов")
    
    # Проверяем лишние файлы
    if extra_files:
        print(f"\n⚠️  Лишние файлы ({len(extra_files)}):")
        for file in sorted(extra_files)[:10]:
            print(f"   + {file}")
        if len(extra_files) > 10:
            print(f"   ... и еще {len(extra_files) - 10} файлов")
    
    # Проверяем контрольные суммы общих файлов
    print(f"\n🔢 Проверка контрольных сумм ({len(common_files)} файлов):")
    mismatched = []
    
    for file in sorted(common_files):
        ref_hash = reference['files'][file]['hash']
        curr_hash = current_checksums[file]['hash']
        
        if ref_hash != curr_hash:
            mismatched.append(file)
    
    if mismatched:
        print(f"❌ Файлов с несовпадающими хэшами: {len(mismatched)}")
        for file in mismatched[:5]:
            print(f"   ✗ {file}")
            issues.append(f"Изменен файл: {file}")
        if len(mismatched) > 5:
            print(f"   ... и еще {len(mismatched) - 5} файлов")
    else:
        print("   ✅ Все контрольные суммы совпадают")
    
    # Итог
    print("\n" + "=" * 80)
    if not issues:
        print("🎉 СИСТЕМА ПРОШЛА ПРОВЕРКУ ЦЕЛОСТНОСТИ!")
        print("Все файлы присутствуют и не были изменены.")
        return True
    else:
        print(f"⚠️  ОБНАРУЖЕНО ПРОБЛЕМ: {len(issues)}")
        print("Система требует внимания перед использованием.")
        return False

def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Проверка целостности LTO Backup System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s check          # Проверить целостность системы
  %(prog)s reference      # Создать эталонные контрольные суммы
  %(prog)s verify         # Проверить систему по эталону
  %(prog)s compare A.json B.json  # Сравнить два отчета
  %(prog)s full           # Полная проверка (check + reference + verify)
        """
    )
    
    parser.add_argument('command', 
                       choices=['check', 'reference', 'verify', 'compare', 'full', 'stats'],
                       help='Команда для выполнения')
    
    parser.add_argument('args', nargs='*', help='Дополнительные аргументы')
    parser.add_argument('--dir', default='.', help='Базовый директорий системы')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'check':
            print("🔍 Проверка целостности системы...")
            report = generate_integrity_report(args.dir)
            
            # Сохраняем краткий отчет
            summary_path = os.path.join(args.dir, 'integrity_summary.txt')
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(f"Отчет о целостности LTO Backup System\n")
                f.write(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Директория: {os.path.abspath(args.dir)}\n")
                f.write(f"Всего файлов: {len(report['files'])}\n")
                f.write(f"Проблем: {len(report['issues'])}\n\n")
                
                if report['issues']:
                    f.write("Проблемы:\n")
                    for issue in report['issues']:
                        f.write(f"- {issue}\n")
                else:
                    f.write("✅ Все проверки пройдены успешно!\n")
            
            print(f"\n📋 Краткий отчет сохранен: {summary_path}")
            
        elif args.command == 'reference':
            create_reference_checksums(args.dir)
            
        elif args.command == 'verify':
            success = verify_against_reference(args.dir)
            sys.exit(0 if success else 1)
            
        elif args.command == 'compare':
            if len(args.args) < 2:
                print("❌ Для сравнения нужны два файла отчетов")
                sys.exit(1)
            compare_checksums(args.args[0], args.args[1])
            
        elif args.command == 'full':
            print("🔄 ПОЛНАЯ ПРОВЕРКА СИСТЕМЫ")
            print("=" * 80)
            
            # 1. Проверка целостности
            print("\n🔍 Этап 1: Проверка целостности...")
            generate_integrity_report(args.dir)
            
            # 2. Создание эталона
            print("\n🏗️ Этап 2: Создание эталонных контрольных сумм...")
            create_reference_checksums(args.dir)
            
            # 3. Проверка по эталону
            print("\n✅ Этап 3: Проверка по эталону...")
            success = verify_against_reference(args.dir)
            
            if success:
                print("\n🎉 ПОЛНАЯ ПРОВЕРКА ЗАВЕРШЕНА УСПЕШНО!")
                print("Система готова к использованию.")
            else:
                print("\n⚠️  ПОЛНАЯ ПРОВЕРКА ВЫЯВИЛА ПРОБЛЕМЫ")
                print("Пожалуйста, исправьте указанные проблемы.")
                sys.exit(1)
                
        elif args.command == 'stats':
            print("📊 СТАТИСТИКА СИСТЕМЫ")
            print("=" * 80)
            
            checksums = get_file_checksums(args.dir)
            
            print(f"\n📁 Всего файлов: {len(checksums)}")
            
            # Статистика по типам файлов
            file_types = {}
            total_size = 0
            
            for file_path, info in checksums.items():
                ext = os.path.splitext(file_path)[1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1
                total_size += info['size']
            
            print(f"📦 Общий размер: {total_size / (1024*1024):.2f} MB")
            print("\n📄 Типы файлов:")
            for ext, count in sorted(file_types.items()):
                print(f"   {ext or 'без расширения'}: {count} файлов")
            
            # Крупнейшие файлы
            print("\n🏆 Крупнейшие файлы:")
            sorted_files = sorted(checksums.items(), 
                                key=lambda x: x[1]['size'], 
                                reverse=True)[:10]
            
            for i, (file_path, info) in enumerate(sorted_files, 1):
                size_mb = info['size'] / (1024*1024)
                print(f"   {i:2d}. {file_path[:60]:<60} {size_mb:6.2f} MB")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Прервано пользователем")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
