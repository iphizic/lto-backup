#!/bin/bash
# Скрипт проверки системных зависимостей для LTO Backup System

set -e

echo "🔍 Проверка системы LTO Backup System"
echo "========================================"

# Функция проверки команды
check_command() {
    local cmd=$1
    local name=$2
    
    if command -v "$cmd" &> /dev/null; then
        echo "✅ $name ($cmd) установлен"
        return 0
    else
        echo "❌ $name ($cmd) отсутствует"
        return 1
    fi
}

# Основные системные утилиты
echo ""
echo "📦 Основные системные утилиты:"
echo "----------------------------"

ERRORS=0

check_command "tar" "Tar" || ERRORS=$((ERRORS + 1))
check_command "mt" "mt-st (mt)" || ERRORS=$((ERRORS + 1))
check_command "mtx" "mtx" || ERRORS=$((ERRORS + 1))
check_command "mbuffer" "mbuffer" || ERRORS=$((ERRORS + 1))
check_command "smartctl" "smartctl" || ERRORS=$((ERRORS + 1))
check_command "lsscsi" "lsscsi" || ERRORS=$((ERRORS + 1))
check_command "tapeinfo" "tapeinfo" || ERRORS=$((ERRORS + 1))
check_command "curl" "curl" || ERRORS=$((ERRORS + 1))

# Python и зависимости
echo ""
echo "🐍 Python и зависимости:"
echo "----------------------"

check_command "python3" "Python 3" || ERRORS=$((ERRORS + 1))

if command -v "python3" &> /dev/null; then
    # Проверка Python модулей
    echo ""
    echo "  Проверка Python модулей:"
    
    check_python_module() {
        local module=$1
        local name=$2
        
        if python3 -c "import $module" &> /dev/null; then
            echo "    ✅ $name ($module)"
        else
            echo "    ❌ $name ($module)"
            return 1
        fi
    }
    
    check_python_module "yaml" "PyYAML" || ERRORS=$((ERRORS + 1))
    check_python_module "jsonschema" "jsonschema" || ERRORS=$((ERRORS + 1))
    check_python_module "psutil" "psutil" || ERRORS=$((ERRORS + 1))
    check_python_module "chardet" "chardet" || ERRORS=$((ERRORS + 1))
    check_python_module "requests" "requests" || ERRORS=$((ERRORS + 1))
    check_python_module "configparser" "configparser" || ERRORS=$((ERRORS + 1))
    check_python_module "logging" "logging" || ERRORS=$((ERRORS + 1))
    check_python_module "subprocess" "subprocess" || ERRORS=$((ERRORS + 1))
fi

# Проверка устройств
echo ""
echo "💽 Проверка устройств:"
echo "-------------------"

TAPE_DEVICE="/dev/nst0"
if [ -e "$TAPE_DEVICE" ]; then
    echo "✅ Ленточное устройство найдено: $TAPE_DEVICE"
    
    # Проверка прав доступа
    if [ -w "$TAPE_DEVICE" ]; then
        echo "✅ Права на запись в $TAPE_DEVICE есть"
    else
        echo "⚠️  Нет прав на запись в $TAPE_DEVICE"
        echo "   Выполните: sudo chmod 666 $TAPE_DEVICE"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "❌ Ленточное устройство не найдено: $TAPE_DEVICE"
    echo "   Проверьте подключение и загружен ли модуль ядра:"
    echo "   lsmod | grep st"
    echo "   sudo modprobe st"
    ERRORS=$((ERRORS + 1))
fi

# Проверка директорий
echo ""
echo "📁 Проверка директорий:"
echo "-------------------"

check_directory() {
    local dir=$1
    local name=$2
    
    if [ -d "$dir" ]; then
        echo "✅ $name: $dir существует"
        
        # Проверка прав на запись
        if [ -w "$dir" ]; then
            echo "   ✅ Права на запись есть"
        else
            echo "   ⚠️  Нет прав на запись в $dir"
            echo "      Выполните: sudo chmod 755 $dir"
        fi
    else
        echo "⚠️  $name: $dir не существует"
        echo "   Будет создана автоматически при первом запуске"
    fi
}

check_directory "./logs" "Директория логов"
check_directory "./manifests" "Директория манифестов"
check_directory "./backups" "Директория бэкапов"

# Проверка конфигурации
echo ""
echo "⚙️  Проверка конфигурации:"
echo "----------------------"

if [ -f "config.yaml" ]; then
    echo "✅ Основная конфигурация: config.yaml"
    
    # Быстрая проверка YAML синтаксиса
    if command -v "python3" &> /dev/null && [ -f "config.yaml" ]; then
        if python3 -c "import yaml; yaml.safe_load(open('config.yaml'))" &> /dev/null; then
            echo "✅ Синтаксис YAML корректен"
        else
            echo "❌ Ошибка в синтаксисе YAML"
            ERRORS=$((ERRORS + 1))
        fi
    fi
elif [ -f "config.yml" ]; then
    echo "✅ Основная конфигурация: config.yml"
elif [ -f "config.json" ]; then
    echo "✅ Основная конфигурация: config.json"
else
    echo "⚠️  Конфигурационный файл не найден"
    echo "   Создайте config.yaml, config.yml или config.json"
    echo "   Или запустите: python3 -m modules.config_manager --create-default"
fi

# Итог
echo ""
echo "========================================"
echo "📊 Итог проверки:"

if [ $ERRORS -eq 0 ]; then
    echo "✅ Все проверки пройдены успешно!"
    echo "🚀 Система готова к работе"
    exit 0
elif [ $ERRORS -eq 1 ]; then
    echo "⚠️  Найдена 1 проблема"
    exit 1
else
    echo "❌ Найдено $ERRORS проблем"
    exit 1
fi