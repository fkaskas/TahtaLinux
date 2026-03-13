#!/bin/bash
# Tahta Kilit - Binary Derleme + .deb Paketleme
# PyInstaller ile binary derler, ardından .deb paketi oluşturur
set -e

BETIK_DIZINI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BETIK_DIZINI"
PAKET_ADI="tahta-kilit_1.2"
PAKET_DIZINI="$BETIK_DIZINI/paket-binary/$PAKET_ADI"

echo "=== Tahta Kilit Binary Derleme + Paketleme ==="

# ── 1. PyInstaller ile binary derle ──
echo ""
echo "[1/4] PyInstaller ile derleniyor..."
rm -rf build/ dist/ *.spec

pyinstaller \
    --name tahta-kilit \
    --onefile \
    --add-data "resim:resim" \
    --add-data "cevrimdisi.html:." \
    --add-data "smb_bagla.sh:." \
    --hidden-import=PyQt5.QtWebEngineWidgets \
    --hidden-import=PyQt5.QtWebEngine \
    --hidden-import=qtawesome \
    --hidden-import=vlc \
    --hidden-import=qrcode \
    --hidden-import=socketio \
    --hidden-import=engineio \
    --hidden-import=PIL \
    kilit.py

if [ ! -f "dist/tahta-kilit" ]; then
    echo "HATA: Binary derleme başarısız!"
    exit 1
fi
echo "[✓] Binary derlendi: dist/tahta-kilit"

# ── 2. Paket dizin yapısını oluştur ──
echo ""
echo "[2/4] Paket yapısı oluşturuluyor..."
rm -rf "$BETIK_DIZINI/paket-binary"
mkdir -p "$PAKET_DIZINI/DEBIAN"
mkdir -p "$PAKET_DIZINI/opt/tahta-kilit/resim/fonts"
mkdir -p "$PAKET_DIZINI/etc/systemd/system"
mkdir -p "$PAKET_DIZINI/etc/polkit-1/rules.d"
mkdir -p "$PAKET_DIZINI/usr/share/applications"
mkdir -p "$PAKET_DIZINI/var/lib/tahta-kilit"

# ── 3. Dosyaları yerleştir ──
echo "[3/4] Dosyalar yerleştiriliyor..."

# Binary
cp dist/tahta-kilit "$PAKET_DIZINI/opt/tahta-kilit/tahta-kilit"
chmod 755 "$PAKET_DIZINI/opt/tahta-kilit/tahta-kilit"

# Resimler
cp -r resim/* "$PAKET_DIZINI/opt/tahta-kilit/resim/"
chmod 644 "$PAKET_DIZINI/opt/tahta-kilit/resim/"* 2>/dev/null || true
if [ -d "$PAKET_DIZINI/opt/tahta-kilit/resim/fonts" ]; then
    chmod 755 "$PAKET_DIZINI/opt/tahta-kilit/resim/fonts"
    chmod 644 "$PAKET_DIZINI/opt/tahta-kilit/resim/fonts/"* 2>/dev/null || true
fi

# smb_bagla.sh
cp smb_bagla.sh "$PAKET_DIZINI/opt/tahta-kilit/smb_bagla.sh"
chmod 755 "$PAKET_DIZINI/opt/tahta-kilit/smb_bagla.sh"

# Çevrimdışı HTML
cp cevrimdisi.html "$PAKET_DIZINI/opt/tahta-kilit/cevrimdisi.html"
chmod 644 "$PAKET_DIZINI/opt/tahta-kilit/cevrimdisi.html"

# Başlatıcı script (binary'yi çalıştıracak şekilde)
cat > "$PAKET_DIZINI/opt/tahta-kilit/baslatici.sh" << 'BASLATICI_EOF'
#!/bin/bash
# Tahta Kilit - Dinamik Başlatıcı
# GUI kullanıcısını otomatik algılar ve uygulamayı başlatır

GUI_USER=""

# 1. who ile display kullanan kullanıcıyı bul
if command -v who &>/dev/null; then
    GUI_USER=$(who | grep -E '\(:0\)|\(tty' | head -1 | awk '{print $1}')
fi

# 2. loginctl ile grafiksel oturum kullanıcısını bul
if [ -z "$GUI_USER" ] && command -v loginctl &>/dev/null; then
    SESSION_ID=$(loginctl list-sessions --no-legend | grep -v root | head -1 | awk '{print $1}')
    if [ -n "$SESSION_ID" ]; then
        GUI_USER=$(loginctl show-session "$SESSION_ID" -p Name --value 2>/dev/null)
    fi
fi

# 3. /home altındaki .Xauthority sahibini bul
if [ -z "$GUI_USER" ]; then
    XAUTH_FILE=$(find /home -maxdepth 2 -name .Xauthority -newer /proc/1 2>/dev/null | head -1)
    if [ -n "$XAUTH_FILE" ]; then
        GUI_USER=$(stat -c '%U' "$XAUTH_FILE")
    fi
fi

# 4. Fallback: /home altındaki ilk kullanıcı
if [ -z "$GUI_USER" ]; then
    GUI_USER=$(ls /home/ | head -1)
fi

if [ -z "$GUI_USER" ]; then
    echo "HATA: GUI kullanıcısı bulunamadı!"
    exit 1
fi

GUI_HOME="/home/$GUI_USER"
GUI_UID=$(id -u "$GUI_USER" 2>/dev/null || echo "1000")

export DISPLAY=:0
export XAUTHORITY="$GUI_HOME/.Xauthority"
export HOME="$GUI_HOME"
export XDG_RUNTIME_DIR="/run/user/$GUI_UID"
export PULSE_SERVER="unix:/run/user/$GUI_UID/pulse/native"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$GUI_UID/bus"
export QT_QPA_PLATFORM=xcb
export QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox"
export GST_PLUGIN_SYSTEM_PATH=/usr/lib/x86_64-linux-gnu/gstreamer-1.0
export VLC_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/vlc/plugins

echo "Tahta Kilit başlatılıyor: kullanıcı=$GUI_USER, UID=$GUI_UID"

cd /opt/tahta-kilit
# PyInstaller LD_LIBRARY_PATH değişikliğinin VLC eklentilerini bozmasını önle
export LD_LIBRARY_PATH_ORIG="${LD_LIBRARY_PATH:-}"
exec /opt/tahta-kilit/tahta-kilit
BASLATICI_EOF
chmod 755 "$PAKET_DIZINI/opt/tahta-kilit/baslatici.sh"

# Systemd servis dosyası
cat > "$PAKET_DIZINI/etc/systemd/system/tahta-kilit.service" << 'SERVICE_EOF'
[Unit]
Description=Tahta Ekran Kilitleme Servisi
After=graphical.target lightdm.service
Wants=graphical.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/opt/tahta-kilit
ExecStartPre=/bin/sleep 2
ExecStart=/bin/bash /opt/tahta-kilit/baslatici.sh
Restart=always
RestartSec=3

[Install]
WantedBy=graphical.target
SERVICE_EOF

# Polkit kuralı
cat > "$PAKET_DIZINI/etc/polkit-1/rules.d/49-tahta-kilit.rules" << 'POLKIT_EOF'
polkit.addRule(function(action, subject) {
    if (action.id === "org.freedesktop.systemd1.manage-units" &&
        action.lookup("unit") === "tahta-kilit.service" &&
        subject.user !== "root") {
        return polkit.Result.NO;
    }
});
POLKIT_EOF

# Desktop dosyası
cat > "$PAKET_DIZINI/usr/share/applications/tahta-kilit.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Tahta Ekran Kilitleme
Comment=Tahta ekranını kilitler ve yönetir
Exec=/opt/tahta-kilit/tahta-kilit
Path=/opt/tahta-kilit
Icon=/opt/tahta-kilit/resim/tahta-kilit-icon.png
Terminal=false
Categories=Utility;System;
DESKTOP_EOF

# DEBIAN/control
cat > "$PAKET_DIZINI/DEBIAN/control" << 'CONTROL_EOF'
Package: tahta-kilit
Version: 1.2
Section: utils
Priority: optional
Architecture: amd64
Depends: vlc,
 libgl1,
 libxcb-xinerama0,
 libxkbcommon-x11-0,
 libnss3,
 libxcomposite1,
 libxrandr2,
 libxdamage1,
 xdotool,
 alsa-utils,
 gvfs-backends,
 cifs-utils
Maintainer: EtapAdmin <fk@fatihkaskas.com>
Description: Tahta Kilit Uygulaması (Binary)
 Etkileşimli tahta ekranlarını uzaktan veya yerelden kilitleme,
 açma ve yönetme uygulaması. Kurum kodu ve TOTP tabanlı doğrulama
 sistemi ile güvenli erişim sağlar. Derlenmiş binary sürümü.
Homepage: https://kulumtal.com
CONTROL_EOF

# DEBIAN/postinst
cat > "$PAKET_DIZINI/DEBIAN/postinst" << 'POSTINST_EOF'
#!/bin/bash
echo "=== Tahta Kilit kurulum sonrası yapılandırma ==="

# Veritabanı dizini izinleri
mkdir -p /var/lib/tahta-kilit
chmod 700 /var/lib/tahta-kilit
chown root:root /var/lib/tahta-kilit

# Dosya izinleri
chmod +x /opt/tahta-kilit/tahta-kilit
chmod +x /opt/tahta-kilit/baslatici.sh
chown -R root:root /opt/tahta-kilit
chown root:root /etc/systemd/system/tahta-kilit.service

# Systemd servisini etkinleştir ve başlat
systemctl daemon-reload
systemctl enable tahta-kilit.service || true
systemctl start tahta-kilit.service || true

echo "[✓] Tahta Kilit başarıyla kuruldu ve servis başlatıldı."
exit 0
POSTINST_EOF
chmod 755 "$PAKET_DIZINI/DEBIAN/postinst"

# DEBIAN/prerm
cat > "$PAKET_DIZINI/DEBIAN/prerm" << 'PRERM_EOF'
#!/bin/bash
set -e
echo "=== Tahta Kilit kaldırılıyor ==="
systemctl stop tahta-kilit.service 2>/dev/null || true
systemctl disable tahta-kilit.service 2>/dev/null || true
systemctl daemon-reload
echo "[✓] Tahta Kilit servisi durduruldu ve devre dışı bırakıldı."
PRERM_EOF
chmod 755 "$PAKET_DIZINI/DEBIAN/prerm"

# DEBIAN/postrm
cat > "$PAKET_DIZINI/DEBIAN/postrm" << 'POSTRM_EOF'
#!/bin/bash
set -e
if [ "$1" = "purge" ]; then
    rm -rf /var/lib/tahta-kilit
    echo "[✓] Veritabanı dosyaları temizlendi."
fi
echo "[✓] Tahta Kilit kaldırıldı."
POSTRM_EOF
chmod 755 "$PAKET_DIZINI/DEBIAN/postrm"

# ── 4. .deb paketini oluştur ──
echo ""
echo "[4/4] .deb paketi oluşturuluyor..."
dpkg-deb --build "$PAKET_DIZINI"

# Temizlik
rm -rf build/ *.spec

DEB_BOYUT=$(du -h "$BETIK_DIZINI/paket-binary/$PAKET_ADI.deb" | cut -f1)
echo ""
echo "=== Paket Hazır ==="
echo "Dosya: paket-binary/$PAKET_ADI.deb ($DEB_BOYUT)"
echo ""
echo "Kurulum:  sudo dpkg -i paket-binary/$PAKET_ADI.deb"
echo "Kaldırma: sudo dpkg -r tahta-kilit"
