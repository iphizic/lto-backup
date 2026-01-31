#!/bin/bash
set -e

echo "=================================================="
echo "      LTO Backup System - Binary Builder"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function for colored output
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "ℹ️  $1"
}

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python3 не найден"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
print_info "Python версия: $PYTHON_VERSION"

# Check Python version
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ $PYTHON_MAJOR -lt 3 ] || ([ $PYTHON_MAJOR -eq 3 ] && [ $PYTHON_MINOR -lt 7 ]); then
    print_error "Требуется Python 3.7 или выше"
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    print_info "Создание виртуального окружения..."
    python3 -m venv venv
fi

# Activate virtual environment
print_info "Активация виртуального окружения..."
source venv/bin/activate

# Upgrade pip
print_info "Обновление pip..."
pip install --upgrade pip --quiet

# Install dependencies
print_info "Установка зависимостей..."
pip install -r requirements.txt --quiet

# Install PyInstaller
print_info "Установка PyInstaller..."
pip install pyinstaller --quiet

# Check project structure
print_info "Проверка структуры проекта..."
required_dirs=("core" "hardware" "notification" "utils")
missing_dirs=()

for dir in "${required_dirs[@]}"; do
    if [ ! -d "$dir" ]; then
        missing_dirs+=("$dir")
    fi
done

if [ ${#missing_dirs[@]} -gt 0 ]; then
    print_error "Отсутствуют директории: ${missing_dirs[*]}"
    exit 1
fi

required_files=("lto_backup.py" "config.yaml.example" "requirements.txt" "README.md")
missing_files=()

for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        missing_files+=("$file")
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    print_error "Отсутствуют файлы: ${missing_files[*]}"
    exit 1
fi

print_success "Структура проекта проверена"

# Create icon if needed (for Windows/macOS)
if [ ! -f "icon.ico" ] && [ ! -f "icon.png" ]; then
    print_info "Создание иконки..."
    # Create a simple icon using ImageMagick if available
    if command -v convert &> /dev/null; then
        convert -size 256x256 xc:#4A90E2 -fill white \
                -draw "circle 128,128 128,64" \
                -draw "text 80,140 'LTO'" \
                -font Arial -pointsize 48 \
                icon.png 2>/dev/null || true
        
        if [ -f "icon.png" ]; then
            print_success "Иконка создана: icon.png"
        fi
    else
        print_warning "ImageMagick не найден, иконка не создана"
    fi
fi

# Clean previous builds
print_info "Очистка предыдущих сборок..."
rm -rf build/ dist/ *.spec 2>/dev/null || true

# Create spec file
print_info "Создание spec файла..."
cat > lto_backup.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path

block_cipher = None

# Add paths for module search
sys.path.insert(0, os.path.abspath('.'))

def collect_data_files():
    """Collect all necessary data files"""
    data_files = []
    
    # Add Python modules
    for module in ['core', 'hardware', 'notification', 'utils']:
        module_path = os.path.join('.', module)
        if os.path.exists(module_path):
            for root, dirs, files in os.walk(module_path):
                for file in files:
                    if file.endswith('.py'):
                        full_path = os.path.join(root, file)
                        dest_path = os.path.dirname(full_path)
                        data_files.append((full_path, dest_path))
    
    # Add static files
    static_files = ['config.yaml.example', 'README.md']
    for file in static_files:
        if os.path.exists(file):
            data_files.append((file, '.'))
    
    # Add icon if exists
    for icon_file in ['icon.ico', 'icon.png', 'icon.icns']:
        if os.path.exists(icon_file):
            data_files.append((icon_file, '.'))
            break
    
    return data_files

def get_hidden_imports():
    """Get hidden imports for PyInstaller"""
    return [
        'yaml',
        'telegram',
        'telegram.ext',
        'telegram._vendor.ptb_urllib3',
        'telegram._vendor.ptb_urllib3.urllib3',
        'telegram._vendor.ptb_urllib3.urllib3.contrib',
        'telegram._vendor.ptb_urllib3.urllib3.contrib.pyopenssl',
        'requests',
        'urllib3',
        'charset_normalizer',
        'idna',
        'schedule'
    ]

a = Analysis(
    ['lto_backup.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=collect_data_files(),
    hiddenimports=get_hidden_imports(),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'PyQt5', 'PyQt6', 'wx', 'matplotlib',
        'pandas', 'numpy', 'scipy', 'sympy', 'django',
        'test', 'tests', 'unittest'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=2
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='lto_backup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico', 'icon.png', 'icon.icns']
)
EOF

print_success "Spec файл создан"

# Run PyInstaller
print_info "Запуск PyInstaller..."
pyinstaller \
    --onefile \
    --clean \
    --distpath ./dist \
    --workpath ./build \
    --specpath . \
    lto_backup.spec 2>&1 | while read line; do
    if [[ $line == *"ERROR"* ]]; then
        print_error "$line"
    elif [[ $line == *"WARNING"* ]]; then
        print_warning "$line"
    elif [[ $line == *"INFO"* ]]; then
        print_info "$line"
    fi
done

# Check result
if [ -f "./dist/lto_backup" ]; then
    # Get binary size
    if command -v stat &> /dev/null; then
        if stat -f%z "./dist/lto_backup" &>/dev/null; then
            # macOS
            BINARY_SIZE=$(stat -f%z "./dist/lto_backup")
        else
            # Linux
            BINARY_SIZE=$(stat -c%s "./dist/lto_backup")
        fi
    else
        BINARY_SIZE=$(wc -c < "./dist/lto_backup")
    fi
    
    BINARY_SIZE_MB=$(echo "scale=2; $BINARY_SIZE / 1024 / 1024" | bc)
    
    # Make binary executable
    chmod +x "./dist/lto_backup"
    
    echo ""
    echo "=================================================="
    print_success "Бинарный файл успешно создан!"
    echo "📁 Расположение: ./dist/lto_backup"
    echo "📏 Размер: ${BINARY_SIZE_MB} MB"
    echo "=================================================="
    
    # Test the binary
    print_info "Тестирование бинарного файла..."
    if ./dist/lto_backup --version &>/dev/null; then
        print_success "Бинарный файл работает"
        ./dist/lto_backup --version
    else
        print_warning "Бинарный файл создан, но тест не пройден"
    fi
    
    # Create README
    cat > ./dist/README.txt << 'EOF'
LTO Backup System - Standalone Binary
=====================================

This is a standalone binary of LTO Backup System containing all Python
dependencies and modules.

System Requirements:
- Tape drive: LTO-4 or compatible
- System utilities: tar, mbuffer, mt, tapeinfo
- Write access to tape device (default: /dev/nst0)

Quick Start:
1. Create config.yaml (copy from config.yaml.example)
2. Configure your settings in config.yaml
3. Check system: ./lto_backup check
4. Create backup: ./lto_backup backup /path/to/data "Label"

Commands:
  backup <source> <label>    Create backup
  restore <dest> <label>     Restore from backup
  list                       List backups
  check                      Check system
  change_tape                Change tape
  config                     Show configuration
  stats                      Show statistics
  validate                   Validate configuration
  version                    Show version
  scheduler                  Run scheduler

Configuration Format: YAML

For mbuffer integration, set in config.yaml:
  mbuffer:
    change_script: "lto_backup change_tape"

Source Code: https://github.com/your-repo/lto_backup
License: MIT
EOF
    
    print_success "README создан: ./dist/README.txt"
    
    # Create installation script
    cat > ./dist/install.sh << 'EOF'
#!/bin/bash

echo "LTO Backup System Installation"
echo "==============================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script requires root privileges."
    echo "Please run with sudo: sudo ./install.sh"
    exit 1
fi

# Copy binary
echo "Installing binary to /usr/local/bin..."
cp lto_backup /usr/local/bin/
chmod +x /usr/local/bin/lto_backup

# Create config directory
echo "Creating configuration directory..."
mkdir -p /etc/lto_backup

# Copy example config if config doesn't exist
if [ ! -f /etc/lto_backup/config.yaml ]; then
    if [ -f config.yaml.example ]; then
        cp config.yaml.example /etc/lto_backup/config.yaml
        echo "Configuration created: /etc/lto_backup/config.yaml"
        echo "Please edit this file before use."
    fi
fi

# Create log directory
echo "Creating log directory..."
mkdir -p /var/log/lto_backup
chmod 755 /var/log/lto_backup

# Create systemd service
if [ -d "/usr/lib/systemd/system" ]; then
    echo "Creating systemd service..."
    cat > /usr/lib/systemd/system/lto-backup.service << SERVICE_EOF
[Unit]
Description=LTO Backup System Scheduler
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/etc/lto_backup
Environment="LTO_CONFIG=/etc/lto_backup/config.yaml"
ExecStart=/usr/local/bin/lto_backup scheduler
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF

    echo "Systemd service created: /usr/lib/systemd/system/lto-backup.service"
    echo ""
    echo "To enable and start the service:"
    echo "  sudo systemctl enable lto-backup"
    echo "  sudo systemctl start lto-backup"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit configuration: sudo nano /etc/lto_backup/config.yaml"
echo "2. Check system: lto_backup check"
echo "3. Create test backup: lto_backup backup /tmp/test 'Test_Backup'"
EOF
    
    chmod +x ./dist/install.sh
    print_success "Инсталляционный скрипт создан: ./dist/install.sh"
    
else
    print_error "Ошибка при создании бинарного файла"
    exit 1
fi

# Deactivate virtual environment
deactivate

echo ""
echo "=================================================="
print_success "Сборка завершена успешно!"
echo "=================================================="
echo ""
echo "Для установки в систему выполните:"
echo "  cd dist"
echo "  sudo ./install.sh"
echo ""
echo "Или вручную:"
echo "  sudo cp lto_backup /usr/local/bin/"
echo "  sudo chmod +x /usr/local/bin/lto_backup"
echo "  sudo mkdir -p /etc/lto_backup"
echo "  sudo cp config.yaml.example /etc/lto_backup/config.yaml"