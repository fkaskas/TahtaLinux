#!/bin/bash
# Ekran Kilitleme Uygulaması - Hızlı Başlatma Scripti

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCKER_SCRIPT="$SCRIPT_DIR/kilit.py"

if [ ! -f "$LOCKER_SCRIPT" ]; then
    echo "Hata: kilit.py bulunamadı!"
    exit 1
fi

echo "Ekran Kilitleme Uygulaması başlatılıyor..."
python3 "$LOCKER_SCRIPT"
