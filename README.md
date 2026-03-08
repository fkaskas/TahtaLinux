# Ekran Kilitleme Uygulaması

Pardus Linux Etap 23.4 için tasarlanmış, Challenge-Response ve QR kod tabanlı ekran kilitleme uygulaması.

## Özellikler

- Tam ekranı kaplayacak şekilde çalışır (X11 bypass)
- Tüm tuş ve mouse girdilerini engeller (Alt+F4, Alt+Tab, Escape dahil)
- Challenge-Response doğrulama sistemi (TOTP benzeri, 30 sn yenileme)
- QR kod ile mobil doğrulama desteği
- Dokunmatik ekran uyumlu nümerik klavye
- 3 hatalı girişte otomatik challenge yenileme
- Sol panelde saat, tarih, sınıf bilgisi ve QR kod
- Sağ panelde WebView ile web içeriği gösterimi

## Proje Yapısı

```
kilit.py                  → Ana giriş noktası
sabitler.py               → Sabitler (gizli anahtar, kod uzunluğu vb.)
servisler.py              → KodUretici ve DogrulamaServisi sınıfları
dogrulama_penceresi.py    → Kilit açma dialogu (nümerik klavyeli)
kilit_penceresi.py        → Ana kilit ekranı penceresi
resim/                    → Logo ve görsel dosyaları
```

## Gereksinimler

```bash
sudo apt-get install python3 python3-pyqt5 python3-pyqt5.qtwebengine xdotool
pip3 install qrcode pillow
```

## Çalıştırma

```bash
python3 kilit.py
```

## Kilidi Açma

1. Sidebar'daki QR kodu telefonla tarayın
2. Açılan sayfadaki yanıt kodunu alın
3. "Kilidi Aç" butonuna basın
4. Nümerik klavyeden yanıt kodunu girin
5. "Doğrula" butonuna basın

## Arka Planda Çalıştırma

```bash
nohup python3 kilit.py &
```

Otomatik başlatma için `/etc/xdg/autostart/` dizinine `.desktop` dosyası ekleyebilirsiniz.
