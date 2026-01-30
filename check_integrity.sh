#!/bin/bash
# Быстрая проверка целостности LTO Backup System

echo "🔍 Быстрая проверка целостности LTO Backup System"
echo "=================================================="

# Проверка наличия основных файлов
echo ""
echo "📋 Проверка основных файлов:"

check_file() {
    if [ -f "$1" ]; then
        echo "✅ $1"
        return 0
    else
        echo "❌ $1 - ОТСУТСТВУЕТ"
        return 1
    fi
}

errors=0

check_file "lto_main.py"
errors=$((errors + $?))

check_file "config.yaml"
errors=$((errors + $?))

check_file "README.md"
errors=$((errors + $?))

# Проверка директорий
echo ""
echo "📁 Проверка директорий:"

check_dir() {
    if [ -d "$1" ]; then
        echo "✅ $1/"
        return 0
    else
        echo "❌ $1/ - ОТСУТСТВУЕТ"
        return 1
    fi
}

check_dir "modules"
errors=$((errors + $?))

check_dir "scripts"
errors=$((errors + $?))

# Проверка модулей
echo ""
echo "🐍 Проверка основных модулей:"

check_module() {
    if [ -f "modules/$1" ]; then
        if python3 -m py_compile "modules/$1" 2>/dev/null; then
            echo "✅ modules/$1"
            return 0
        else
            echo "❌ modules/$1 - СИНТАКСИЧЕСКАЯ ОШИБКА"
            return 1
        fi
    else
        echo "❌ modules/$1 - ОТСУТСТВУЕТ"
        return 1
    fi
}

check_module "config_manager.py"
errors=$((errors + $?))

check_module "file_utils.py"
errors=$((errors + $?))

check_module "system_monitor.py"
errors=$((errors + $?))

check_module "tape_drive.py"
errors=$((errors + $?))

check_module "backup_job.py"
errors=$((errors + $?))

check_module "lto_logger.py"
errors=$((errors + $?))

check_module "registry_manager.py"
errors=$((errors + $?))

check_module "core_tg.py"

# Итог
echo ""
echo "=================================================="
if [ $errors -eq 0 ]; then
    echo "🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!"
    echo "Система готова к использованию."
    exit 0
else
    echo "⚠️  ОБНАРУЖЕНО ОШИБОК: $errors"
    echo "Пожалуйста, исправьте указанные проблемы."
    exit 1
fi