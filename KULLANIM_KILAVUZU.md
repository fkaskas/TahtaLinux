# Ekran Kilitleme Uygulaması - Kullanım Kılavuzu

## Genel Bilgi

Bu uygulamalar Pardus Linux Etap 23.4 sisteminde ekranı tamamen kilitlemek için tasarlanmıştır. Kilit aktifken kullanıcı hiçbir şekilde sistem ile etkileşim kuramaz. Kilidi açmak için sadece kırmızı "Kilidi Aç" butonu kullanılabilir.

## Dosyalar

- **screen_locker.py** - Ana Python uygulaması
- **run.sh** - Bash başlatma scripti
- **screen_locker.desktop** - KDE/Plasma uygulama başlatıcısı
- **README.md** - Hızlı başlangıç kılavuzu

## Kurulum

### 1. Gereksinimler Yüklemesi

```bash
sudo apt-get install python3-pyqt5
```

Uygulama zaten kurulu değilse PyQt5'i yukarıdaki komutla yükleyiniz.

### 2. Dosya İzinleri

Dosyalara çalışma izni verildi ancak gerekirse:

```bash
chmod +x screen_locker.py run.sh
```

## Başlatma Yöntemleri

### Yöntem 1: Bash Scripti ile
```bash
./run.sh
```

### Yöntem 2: Doğrudan Python ile
```bash
python3 screen_locker.py
```

### Yöntem 3: Masaüstüne Kısayol Ekleme

Desktop dosyasını masaüstüne kopyalayın:
```bash
cp screen_locker.desktop ~/Desktop/
```

Ardından masaüstündeki "Ekran Kilitleme" simgesine çift tıklayın.

### Yöntem 4: Arka Planda Çalıştırma

```bash
nohup python3 screen_locker.py > /dev/null 2>&1 &
```

## Özellikler

✓ **Tam Ekran Kaplar** - Tüm ekranı yönetilen pencereler olmadan kaplar  
✓ **Kilitler Tuş Girdisini** - Tüm tuşlar (Escape, Alt+F4 vb.) engellenir  
✓ **Kilitler Mouse Girdisini** - Mouse hareketleri yanıt vermez  
✓ **Kolay Açılır** - Kırmızı buton ile tek tıkla kilidi açın  
✓ **Güvenli Tasarım** - Alışıldık kapatma yöntemleri (Escape, Alt+F4) çalışmaz  

## Kilidi Açma

Ekranda gösterilen **kırmızı "Kilidi Aç" butonu**na tıklayın. Buton üzerine geldiğinde rengi değişir. Tıkladığınızda uygulama kapanır ve kilitleme sonlanır.

## İleri Özellikler

### Otomatik Başlatma (Sistem Açılışında)

KDE Plasma'nın oto-başlatma dizinine desktop dosyasını kopyalayın:

```bash
mkdir -p ~/.config/autostart
cp screen_locker.desktop ~/.config/autostart/
```

### Özelleştirme

`screen_locker.py` dosyasının aşağıdaki satırlarını düzenleyerek özelleştirebilirsiniz:

- **Renk Değişikliği**: `#2c3e50` - Arka plan rengi (16. satır)
- **Buton Rengi**: `#e74c3c` - Kırmızı renk (37. satır)
- **Metin Değişikliği**: "Sistem Kilitlenmiştir" (30. satır)
- **Font Boyutu**: `status_font.setPointSize(36)` (32. satır)

## Sorun Giderme

### Uygulama başlamıyor
1. PyQt5 yüklü mü kontrol edin:
   ```bash
   python3 -c "import PyQt5; print('PyQt5 OK')"
   ```

2. Python sürümü 3.x mi kontrol edin:
   ```bash
   python3 --version
   ```

### Uygulama donmuş görünüyor
- Bu normaldür. Uygulama sistem girdilerini engellediği için GUI donmuş gibi görünebilir.
- Butona tıklamayı deneyin veya terminal'den Ctrl+C ile sonlandırın.

### Kilitli kalındı
Başka bir terminal açıp (Ctrl+Alt+F2) sonlandırın:
```bash
pkill -f screen_locker
```

## Geliştirme ve Katkı

Kod dosyası [screen_locker.py](screen_locker.py) tamamen açık kaynaklı ve özelleştirilebilir.

### Potansiyel Geliştirmeler
- Şifre korumalı kilit
- Saat ve tarih gösterimi
- Özel arkaplan resmi
- Ekran koruma efektleri
- Sistem bilgileri gösterimi

## Lisans ve Kullanım

Bu yazılım eğitim ve sistem yönetimi amacıyla serbestçe kullanılabilir.

---

**Sürüm**: 1.0  
**Oluşturulma Tarihi**: 6 Mart 2026  
**Platform**: Pardus Linux Etap 23.4  
**Python**: 3.x  
