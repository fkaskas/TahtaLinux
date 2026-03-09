#!/bin/bash
# Tahta Kilit — SMB Ağ Klasörü Bağlama Scripti
# Kullanım: sudo ./smb_bagla.sh [bagla|kaldir|durum]

set -e

ETIKET="# tahta-smb"

if [ "$EUID" -ne 0 ]; then
    echo "Bu script root yetkisi ile çalıştırılmalıdır."
    echo "Kullanım: sudo $0 [bagla|kaldir|durum]"
    exit 1
fi

bagla() {
    echo "=== SMB Ağ Klasörü Bağlama ==="
    echo ""

    # cifs-utils kontrolü
    if ! dpkg -s cifs-utils &>/dev/null; then
        echo "cifs-utils kuruluyor..."
        apt install -y cifs-utils
        echo "[✓] cifs-utils kuruldu"
    fi

    read -rp "Sunucu IP adresi (Örn: 192.168.1.100): " SUNUCU
    read -rp "Paylaşım adı (Örn: video): " PAYLASIM
    read -rp "Kullanıcı adı (boş bırakırsan misafir erişimi): " KULLANICI
    if [ -n "$KULLANICI" ]; then
        read -rsp "Şifre: " SIFRE
        echo ""
    fi
    read -rp "Mount noktası (Örn: /mnt/video): " MOUNT_NOKTASI
    MOUNT_NOKTASI="${MOUNT_NOKTASI:-/mnt/video}"

    echo "SMB Sürümü seçin:"
    echo "  1) Otomatik (varsayılan)"
    echo "  2) 3.0"
    echo "  3) 3.1.1"
    echo "  4) 2.1"
    echo "  5) 2.0"
    echo "  6) 1.0"
    read -rp "Seçim [1]: " SMB_SURUM_SEC
    case "${SMB_SURUM_SEC:-1}" in
        2) SMB_SURUM=",vers=3.0" ;;
        3) SMB_SURUM=",vers=3.1.1" ;;
        4) SMB_SURUM=",vers=2.1" ;;
        5) SMB_SURUM=",vers=2.0" ;;
        6) SMB_SURUM=",vers=1.0" ;;
        *) SMB_SURUM="" ;;
    esac

    echo "Kimlik doğrulama yöntemi:"
    echo "  1) ntlmssp (varsayılan)"
    echo "  2) ntlmv2"
    echo "  3) ntlm"
    echo "  4) none"
    read -rp "Seçim [1]: " SEC_SEC
    case "${SEC_SEC:-1}" in
        2) SEC_PARAM=",sec=ntlmv2" ;;
        3) SEC_PARAM=",sec=ntlm" ;;
        4) SEC_PARAM=",sec=none" ;;
        *) SEC_PARAM=",sec=ntlmssp" ;;
    esac

    read -rp "Domain/Workgroup (boş bırakılabilir): " DOMAIN
    DOMAIN_PARAM=""
    [ -n "$DOMAIN" ] && DOMAIN_PARAM=",domain=$DOMAIN"

    # Doğrulama
    if [ -z "$SUNUCU" ] || [ -z "$PAYLASIM" ]; then
        echo "Hata: Sunucu IP ve paylaşım adı zorunludur!"
        exit 1
    fi

    # Mount noktasını oluştur
    mkdir -p "$MOUNT_NOKTASI"
    echo "[✓] Mount noktası oluşturuldu: $MOUNT_NOKTASI"

    # Seçenekleri oluştur
    if [ -z "$KULLANICI" ]; then
        SECENEKLER="guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777,nofail,_netdev,x-systemd.automount,x-systemd.after=network-online.target$SMB_SURUM$SEC_PARAM$DOMAIN_PARAM"
        MOUNT_SECENEKLER="guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777$SMB_SURUM$SEC_PARAM$DOMAIN_PARAM"
    else
        SECENEKLER="username=$KULLANICI,password=$SIFRE,uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777,nofail,_netdev,x-systemd.automount,x-systemd.after=network-online.target$SMB_SURUM$SEC_PARAM$DOMAIN_PARAM"
        MOUNT_SECENEKLER="username=$KULLANICI,password=$SIFRE,uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777$SMB_SURUM$SEC_PARAM$DOMAIN_PARAM"
    fi

    FSTAB_SATIR="//$SUNUCU/$PAYLASIM  $MOUNT_NOKTASI  cifs  $SECENEKLER  0  0  $ETIKET"

    # Önce doğrudan mount ile test et
    echo "[*] Bağlantı test ediliyor..."
    echo "    Komut: mount -t cifs //$SUNUCU/$PAYLASIM $MOUNT_NOKTASI"
    if ! mount -t cifs "//$SUNUCU/$PAYLASIM" "$MOUNT_NOKTASI" -o "$MOUNT_SECENEKLER" 2>&1; then
        echo ""
        echo "[✗] Doğrudan mount başarısız!"
        read -rp "Yine de fstab'a kaydedilsin mi? (e/h): " fstab_cevap
        if [[ ! "$fstab_cevap" =~ ^[eE]$ ]]; then
            echo "[ı] İşlem iptal edildi. Farklı seçenekler deneyin."
            exit 1
        fi
    else
        echo "[✓] Bağlantı başarılı!"
        # Test mountı kaldır, fstab üzerinden bağlanacak
        umount "$MOUNT_NOKTASI" 2>/dev/null || true
    fi

    # Eski tahta-smb satırını temizle
    if grep -q "$ETIKET" /etc/fstab; then
        sed -i "/$ETIKET/d" /etc/fstab
        echo "[✓] Eski SMB bağlantısı fstab'dan temizlendi"
    fi

    # fstab'a ekle
    echo "$FSTAB_SATIR" >> /etc/fstab
    echo "[✓] fstab'a eklendi"

    # systemd automount birimlerini yeniden yükle
    systemctl daemon-reload
    echo "[✓] systemd daemon-reload yapıldı"

    # remote-fs.target etkinleştir
    systemctl enable remote-fs.target 2>/dev/null || true
    echo "[✓] remote-fs.target etkinleştirildi"

    # Mount et
    mount -a
    echo "[✓] Mount edildi"

    echo ""
    echo "=== Bağlama Tamamlandı ==="
    echo "Kaynak:  //$SUNUCU/$PAYLASIM"
    echo "Hedef:   $MOUNT_NOKTASI"
    echo "Sistem her başlatıldığında otomatik bağlanacaktır."
}

kaldir() {
    echo "=== SMB Bağlantısı Kaldırılıyor ==="

    if ! grep -q "$ETIKET" /etc/fstab; then
        echo "fstab'da Tahta SMB bağlantısı bulunamadı."
        exit 0
    fi

    # Mount noktasını bul
    MOUNT_NOKTASI=$(grep "$ETIKET" /etc/fstab | awk '{print $2}')

    # Umount et
    if mountpoint -q "$MOUNT_NOKTASI" 2>/dev/null; then
        umount "$MOUNT_NOKTASI" 2>/dev/null || true
        echo "[✓] Umount edildi: $MOUNT_NOKTASI"
    fi

    # fstab'dan kaldır
    sed -i "/$ETIKET/d" /etc/fstab
    echo "[✓] fstab'dan kaldırıldı"

    echo ""
    echo "=== Kaldırma Tamamlandı ==="
}

durum() {
    echo "=== SMB Bağlantı Durumu ==="
    if grep -q "$ETIKET" /etc/fstab; then
        echo "fstab kaydı:"
        grep "$ETIKET" /etc/fstab
        echo ""
        MOUNT_NOKTASI=$(grep "$ETIKET" /etc/fstab | awk '{print $2}')
        if mountpoint -q "$MOUNT_NOKTASI" 2>/dev/null; then
            echo "Durum: ✅ Bağlı"
            echo "İçerik:"
            ls "$MOUNT_NOKTASI" 2>/dev/null | head -10
        else
            echo "Durum: ❌ Bağlı değil"
        fi
    else
        echo "Tahta SMB bağlantısı yapılandırılmamış."
    fi
}

case "${1:-}" in
    bagla)
        bagla
        ;;
    kaldir)
        kaldir
        ;;
    durum)
        durum
        ;;
    *)
        echo "Kullanım: sudo $0 {bagla|kaldir|durum}"
        echo ""
        echo "  bagla   - SMB paylaşımını bağlar ve fstab'a ekler"
        echo "  kaldir  - SMB bağlantısını kaldırır"
        echo "  durum   - Bağlantı durumunu gösterir"
        exit 1
        ;;
esac
