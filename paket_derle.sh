#!/bin/bash
# Tahta Kilit .deb Paket Derleme Scripti
# Python kaynak dosyalarını doğrudan paketler (binary olmadan)
set -e

BETIK_DIZINI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAKET_DIZINI="$BETIK_DIZINI/paket"
PAKET_ADI="tahta-kilit_1.1"
KAYNAK="$BETIK_DIZINI"
HEDEF="$PAKET_DIZINI/$PAKET_ADI"

# Paketlenecek Python kaynak dosyaları
PYTHON_DOSYALARI=(
    kilit.py
    kilit_penceresi.py
    dogrulama_penceresi.py
    kurulum_penceresi.py
    smb_bagla.py
    online_istemci.py
    sabitler.py
    servisler.py
    veritabani.py
)

echo "=== Tahta Kilit .deb Paketi Oluşturuluyor ==="

# 1) Eski dosyaları temizle
echo "[*] Paket dizini hazırlanıyor..."
rm -f "$HEDEF/opt/tahta-kilit/"*.py 2>/dev/null || true
rm -f "$HEDEF/opt/tahta-kilit/tahta-kilit" 2>/dev/null || true
rm -rf "$HEDEF/opt/tahta-kilit/__pycache__" 2>/dev/null || true

# 2) Python kaynak dosyalarını kopyala
echo "[*] Python kaynak dosyaları kopyalanıyor..."
for dosya in "${PYTHON_DOSYALARI[@]}"; do
    if [ ! -f "$KAYNAK/$dosya" ]; then
        echo "HATA: $dosya bulunamadı!"
        exit 1
    fi
    cp "$KAYNAK/$dosya" "$HEDEF/opt/tahta-kilit/$dosya"
done
echo "[✓] ${#PYTHON_DOSYALARI[@]} Python dosyası kopyalandı"

# 3) Resim dosyalarını kopyala
echo "[*] Resim dosyaları kopyalanıyor..."
mkdir -p "$HEDEF/opt/tahta-kilit/resim"
cp -r "$KAYNAK/resim/"* "$HEDEF/opt/tahta-kilit/resim/"
echo "[✓] Resim dosyaları kopyalandı"

# 3.5) Shell scriptlerini kopyala
echo "[*] Shell scriptleri kopyalanıyor..."
cp "$KAYNAK/smb_bagla.sh" "$HEDEF/opt/tahta-kilit/smb_bagla.sh"
chmod 755 "$HEDEF/opt/tahta-kilit/smb_bagla.sh"
echo "[✓] Shell scriptleri kopyalandı"

# 4) İzinleri ayarla
chmod 755 "$HEDEF/DEBIAN/postinst" "$HEDEF/DEBIAN/prerm" "$HEDEF/DEBIAN/postrm"
chmod 755 "$HEDEF/opt/tahta-kilit/kilit.py"
chmod 755 "$HEDEF/opt/tahta-kilit/baslatici.sh"
chmod 644 "$HEDEF/opt/tahta-kilit/resim/"*
# Font dosyaları izinleri
if [ -d "$HEDEF/opt/tahta-kilit/resim/fonts" ]; then
    chmod 755 "$HEDEF/opt/tahta-kilit/resim/fonts"
    chmod 644 "$HEDEF/opt/tahta-kilit/resim/fonts/"* 2>/dev/null || true
fi
for dosya in "${PYTHON_DOSYALARI[@]}"; do
    [ "$dosya" != "kilit.py" ] && chmod 644 "$HEDEF/opt/tahta-kilit/$dosya"
done

# 5) .deb paketini oluştur
echo "[*] .deb paketi oluşturuluyor..."
dpkg-deb --build "$HEDEF"

echo ""
echo "=== Paket Hazır ==="
echo "Dosya: $PAKET_DIZINI/$PAKET_ADI.deb"
echo ""
echo "Kurulum:  sudo dpkg -i $PAKET_DIZINI/$PAKET_ADI.deb"
echo "          sudo apt-get install -f   (eksik bağımlılıklar için)"
echo "Kaldırma: sudo dpkg -r tahta-kilit"
