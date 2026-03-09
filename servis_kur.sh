#!/bin/bash
# Tahta Ekran Kilitleme - Servis Kurulum / Kaldırma Scripti
# Root yetkisi gerektirir

set -e

SERVIS_ADI="tahta-kilit.service"
BETIK_DIZINI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVIS_KAYNAK="$BETIK_DIZINI/$SERVIS_ADI"
SERVIS_HEDEF="/etc/systemd/system/$SERVIS_ADI"
POLKIT_KAYNAK="$BETIK_DIZINI/49-tahta-kilit.rules"
POLKIT_HEDEF="/etc/polkit-1/rules.d/49-tahta-kilit.rules"

if [ "$EUID" -ne 0 ]; then
    echo "Bu script root yetkisi ile çalıştırılmalıdır."
    echo "Kullanım: sudo $0 [kur|kaldir|durum]"
    exit 1
fi

kur() {
    echo "=== Tahta Ekran Kilitleme Servisi Kuruluyor ==="

    if [ ! -f "$SERVIS_KAYNAK" ]; then
        echo "Hata: $SERVIS_KAYNAK bulunamadı!"
        exit 1
    fi

    # cifs-utils kontrolü (SMB bağlantısı için gerekli)
    if ! dpkg -s cifs-utils &>/dev/null; then
        echo "[*] cifs-utils kuruluyor (SMB desteği)..."
        apt install -y cifs-utils
        echo "[✓] cifs-utils kuruldu"
    fi

    # Veritabanı dizinini oluştur ve izinleri ayarla (sadece root okuyabilsin)
    mkdir -p /var/lib/tahta-kilit
    chmod 700 /var/lib/tahta-kilit
    chown root:root /var/lib/tahta-kilit
    # Mevcut DB varsa taşı
    if [ -f "$BETIK_DIZINI/tahta_kilit.db" ]; then
        cp "$BETIK_DIZINI/tahta_kilit.db" /var/lib/tahta-kilit/tahta_kilit.db
        chmod 600 /var/lib/tahta-kilit/tahta_kilit.db
        chown root:root /var/lib/tahta-kilit/tahta_kilit.db
        echo "[✓] Veritabanı /var/lib/tahta-kilit/ altına taşındı (sadece root erişebilir)"
    fi

    # Servis dosyasını kopyala
    cp "$SERVIS_KAYNAK" "$SERVIS_HEDEF"
    echo "[✓] Servis dosyası kopyalandı: $SERVIS_HEDEF"

    # Çalıştırma izni ver
    chmod 644 "$SERVIS_HEDEF"
    chmod +x "$BETIK_DIZINI/kilit.py"

    # Polkit kuralını kopyala (root dışında durdurmayı engeller)
    if [ -f "$POLKIT_KAYNAK" ]; then
        cp "$POLKIT_KAYNAK" "$POLKIT_HEDEF"
        chmod 644 "$POLKIT_HEDEF"
        echo "[✓] Polkit kuralı kopyalandı (sadece root durdurabilir)"
    fi

    # systemd'yi yeniden yükle ve servisi etkinleştir
    systemctl daemon-reload
    systemctl enable "$SERVIS_ADI"
    echo "[✓] Servis etkinleştirildi (açılışta otomatik başlayacak)"

    # Servisi şimdi başlat
    read -rp "Servis şimdi başlatılsın mı? (e/h): " cevap
    if [[ "$cevap" =~ ^[eE]$ ]]; then
        systemctl start "$SERVIS_ADI"
        echo "[✓] Servis başlatıldı"
    fi

    echo ""
    echo "=== Kurulum Tamamlandı ==="
    echo "Durum kontrolü: sudo systemctl status $SERVIS_ADI"
    echo "Loglar:          sudo journalctl -u $SERVIS_ADI -f"
}

kaldir() {
    echo "=== Tahta Ekran Kilitleme Servisi Kaldırılıyor ==="

    # Servisi durdur
    if systemctl is-active --quiet "$SERVIS_ADI" 2>/dev/null; then
        systemctl stop "$SERVIS_ADI"
        echo "[✓] Servis durduruldu"
    fi

    # Servisi devre dışı bırak
    if systemctl is-enabled --quiet "$SERVIS_ADI" 2>/dev/null; then
        systemctl disable "$SERVIS_ADI"
        echo "[✓] Servis devre dışı bırakıldı"
    fi

    # Servis dosyasını sil
    if [ -f "$SERVIS_HEDEF" ]; then
        rm "$SERVIS_HEDEF"
        echo "[✓] Servis dosyası silindi"
    fi

    # Polkit kuralını sil
    if [ -f "$POLKIT_HEDEF" ]; then
        rm "$POLKIT_HEDEF"
        echo "[✓] Polkit kuralı silindi"
    fi

    # Veritabanı dizinini sil
    if [ -d "/var/lib/tahta-kilit" ]; then
        read -rp "Veritabanı silinsin mi? (/var/lib/tahta-kilit) (e/h): " db_cevap
        if [[ "$db_cevap" =~ ^[eE]$ ]]; then
            rm -rf /var/lib/tahta-kilit
            echo "[✓] Veritabanı dizini silindi"
        else
            echo "[i] Veritabanı korundu: /var/lib/tahta-kilit"
        fi
    fi

    systemctl daemon-reload
    echo ""
    echo "=== Kaldırma Tamamlandı ==="
}

durum() {
    echo "=== Tahta Ekran Kilitleme Servisi Durumu ==="
    systemctl status "$SERVIS_ADI" --no-pager 2>/dev/null || echo "Servis kurulu değil."
}

case "${1:-}" in
    kur)
        kur
        ;;
    kaldir)
        kaldir
        ;;
    durum)
        durum
        ;;
    *)
        echo "Kullanım: sudo $0 {kur|kaldir|durum}"
        echo ""
        echo "  kur     - Servisi kurar ve etkinleştirir"
        echo "  kaldir  - Servisi durdurur ve kaldırır"
        echo "  durum   - Servis durumunu gösterir"
        exit 1
        ;;
esac
