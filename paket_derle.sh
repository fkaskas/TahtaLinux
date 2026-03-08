#!/bin/bash
# Tahta Kilit .deb Paket Derleme Scripti
# PyInstaller ile binary derleme + .deb paketleme
set -e

BETIK_DIZINI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAKET_DIZINI="$BETIK_DIZINI/paket"
PAKET_ADI="tahta-kilit_1.0"
KAYNAK="$BETIK_DIZINI"
HEDEF="$PAKET_DIZINI/$PAKET_ADI"

echo "=== Tahta Kilit .deb Paketi Derleniyor ==="

# 1) PyInstaller ile binary derle
echo "[*] Python kaynak kodu binary'ye derleniyor (PyInstaller)..."
cd "$KAYNAK"
pyinstaller --onefile --name tahta-kilit \
  --add-data "resim:resim" \
  --hidden-import PyQt5.QtWebEngineWidgets \
  --hidden-import PyQt5.QtWebChannel \
  --hidden-import qtawesome \
  --hidden-import qrcode \
  --hidden-import hmac \
  --hidden-import hashlib \
  --distpath "$KAYNAK/dist" \
  --workpath "$KAYNAK/build" \
  --specpath "$KAYNAK" \
  --clean \
  kilit.py 2>&1 | grep -E "(INFO: Build|ERROR|WARNING:)" || true

if [ ! -f "$KAYNAK/dist/tahta-kilit" ]; then
    echo "HATA: Binary derleme başarısız!"
    exit 1
fi
echo "[✓] Binary derlendi: $(ls -lh "$KAYNAK/dist/tahta-kilit" | awk '{print $5}')"

# 2) Paket dizinini hazırla — eski .py dosyalarını temizle
echo "[*] Paket dizini hazırlanıyor..."
rm -f "$HEDEF/opt/tahta-kilit/"*.py
rm -f "$HEDEF/opt/tahta-kilit/__pycache__" 2>/dev/null || true

# 3) Derlenen binary ve resim dosyalarını kopyala
cp "$KAYNAK/dist/tahta-kilit" "$HEDEF/opt/tahta-kilit/tahta-kilit"
mkdir -p "$HEDEF/opt/tahta-kilit/resim"
cp "$KAYNAK/resim/"* "$HEDEF/opt/tahta-kilit/resim/"

# 4) İzinleri ayarla — binary root sahipliğinde, sadece root yazabilir
chmod 755 "$HEDEF/DEBIAN/postinst" "$HEDEF/DEBIAN/prerm"
chmod 755 "$HEDEF/opt/tahta-kilit/tahta-kilit"
chmod 644 "$HEDEF/opt/tahta-kilit/resim/"*

# 5) .deb paketini derle
echo "[*] .deb paketi oluşturuluyor..."
dpkg-deb --build "$HEDEF"

echo ""
echo "=== Paket Hazır ==="
echo "Dosya: $PAKET_DIZINI/$PAKET_ADI.deb"
echo "Binary boyut: $(ls -lh "$KAYNAK/dist/tahta-kilit" | awk '{print $5}')"
echo ""
echo "Kurulum:  sudo dpkg -i $PAKET_DIZINI/$PAKET_ADI.deb"
echo "          sudo apt-get install -f   (eksik bağımlılıklar için)"
echo "Kaldırma: sudo dpkg -r tahta-kilit"
echo ""
echo "NOT: Artık .py dosyaları pakete dahil EDİLMEMEKTEDİR."
echo "     Kaynak kod derlenmiş binary içinde korunmaktadır."
