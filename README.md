
# Tahta Ekran Kilitleme Uygulaması

>Pardus Linux Etap 23.4 ve benzeri sistemler için geliştirilmiş, offline ve online çalışabilen, Challenge-Response ve QR kod tabanlı ekran kilitleme ve yönetim uygulaması.

---

## Özellikler

- Tam ekranı kaplayarak tüm kullanıcı etkileşimini engeller (X11 bypass)
- Tüm tuş ve mouse girdilerini devre dışı bırakır (Alt+F4, Alt+Tab, Escape dahil)
- Challenge-Response doğrulama (TOTP benzeri, 30 sn yenileme)
- QR kod ile mobil doğrulama desteği
- Dokunmatik ekran uyumlu nümerik klavye
- 3 hatalı girişte otomatik challenge yenileme
- Sınıf/kurum bilgisi ve offline HTML arayüz desteği
- Online yönetim ve uzaktan açma (isteğe bağlı sunucu)
- Otomasyon için Arduino/ESP32 tabanlı kapı kontrolü
- Binary derleme ve .deb paket desteği (PyInstaller + Debian)
- Systemd servisi ve polkit ile güvenli başlatma
- Yerel font dosyaları ile tamamen offline çalışma

---

## Proje Yapısı

```
kilit.py                  → Ana giriş noktası (Python)
sabitler.py               → Sabitler (gizli anahtar, kod uzunluğu vb.)
servisler.py              → Kod üretici ve doğrulama servisleri
dogrulama_penceresi.py    → Kilit açma dialogu (nümerik klavyeli)
kilit_penceresi.py        → Ana kilit ekranı penceresi
kurulum_penceresi.py      → İlk kurulum ve ayar ekranı
veritabani.py             → SQLite tabanlı veri işlemleri
smb_bagla.py              → SMB paylaşım bağlama arayüzü
cevrimdisi.html           → Offline HTML kilit ekranı (sade, fontlar yerel)
resim/                    → Logo, ikon ve font dosyaları (TTF)
otomasyon/kapi_kontrol.ino→ Arduino/ESP32 kapı kontrol yazılımı
paket/                    → Debian paketleme dosyaları (kaynak)
paket-binary/             → Derlenmiş binary ve .deb paket yapısı
tahta-kilit.service       → systemd servis dosyası
49-tahta-kilit.rules      → polkit yetkilendirme kuralı
servis_kur.sh             → Servis kur/kaldır scripti
binary_derle.sh           → Binary derleme ve .deb paketleme scripti
server/                   → Online yönetim sunucusu (Node.js, socket.io)
```

---

## Gereksinimler

### Uygulama (Python)
```bash
sudo apt-get install python3 python3-pyqt5 python3-pyqt5.qtwebengine xdotool cifs-utils vlc python3-vlc
pip3 install qrcode pillow
```

### Binary Derleme
```bash
sudo apt-get install python3-pyinstaller
```

### Online Sunucu (isteğe bağlı)
```bash
cd server
npm install
```

---

## Çalıştırma

### Geliştirici Modu (Kaynak)
```bash
python3 kilit.py
```

### Binary Modu
```bash
./dist/tahta-kilit
```

### Debian Paketi ile Kurulum
```bash
sudo dpkg -i paket-binary/tahta-kilit_1.2.deb
```

---

## Servis Olarak Çalıştırma

```bash
sudo bash servis_kur.sh kur
# veya
sudo systemctl start tahta-kilit.service
```

---

## Offline HTML Arayüz

- cevrimdisi.html dosyası, internet olmadan tamamen offline çalışır.
- Tüm fontlar ve görseller yerel olarak resim/fonts klasöründe bulunur.
- QR kod ve saat/tarih gösterimi sadeleştirilmiş ve kart yapısı kaldırılmıştır.

---

## Debian Paketleme

- Paketleme scriptleri ve .deb dosyası ile kolay kurulum
- postinst/prerm/postrm ile otomatik servis yönetimi ve izinler
- /opt/tahta-kilit altında binary ve kaynaklar
- /etc/systemd/system/ ve /etc/polkit-1/rules.d/ ile tam entegrasyon

---

## Systemd & Polkit

- tahta-kilit.service ile açılışta otomatik başlatma
- 49-tahta-kilit.rules ile sadece root yetkisiyle servis yönetimi

---

## Otomasyon & Donanım

- otomasyon/kapi_kontrol.ino: ESP32/WT32-ETH01 ile kapı açma
- WebSocket ile sunucuya güvenli bağlantı

---

## Online Yönetim Sunucusu (Opsiyonel)

- server/ dizininde Node.js tabanlı yönetim paneli
- socket.io, express, mysql2, bcryptjs, jsonwebtoken kullanır

---

## Kullanılan Teknolojiler

Detaylı liste için bkz: `teknolojiler.md`

---

## Lisans

Bu proje açık kaynak değildir. Tüm hakları saklıdır.
