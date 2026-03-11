#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ekran Kilitleme Uygulaması
Pardus Linux Etap 23.4 için tasarlandı

X11 seviyesinde klavye ve fare yakalama ile
tüm sistem kısayollarını engeller.
"""

import sys
import os

# Root olarak çalışırken Chromium sandbox hatasını önle
if os.getuid() == 0:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox"
else:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu --disable-gpu-compositing"

# AT-SPI ve GPU kaynaklı zararsız uyarıları bastır
os.environ["QT_LOGGING_RULES"] = "qt.qpa.paint.warning=false;qt.accessibility.atspi.warning=false"
os.environ["NO_AT_BRIDGE"] = "1"

from PyQt5.QtCore import qInstallMessageHandler, QtWarningMsg

def _qt_mesaj_filtresi(msg_type, context, message):
    gizle = (
        "paintEngine" in message
        or "ContextResult" in message
        or "GpuChannel" in message
        or "AtSpiAdaptor" in message
        or "Accessible invalid" in message
        or "Cookie sqlite error" in message
    )
    if gizle:
        return
    if msg_type == QtWarningMsg:
        sys.stderr.write(f"Warning: {message}\n")
    else:
        sys.stderr.write(f"{message}\n")

qInstallMessageHandler(_qt_mesaj_filtresi)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings
from kilit_penceresi import Kilit
from veritabani import VeritabaniYoneticisi
from kurulum_penceresi import KurulumPenceresi
from sabitler import VARSAYILAN_KURUM_KODU, VARSAYILAN_TAHTA_ADI


def _ayar_dosyasi_sahipligini_duzelt():
    """Servis root olarak çalışırken oluşan ayar dosyasının sahipliğini düzelt"""
    if os.getuid() != 0:
        return
    ayarlar = QSettings("KulumTal", "Tahta")
    dosya = ayarlar.fileName()
    if not os.path.exists(dosya):
        return
    # HOME dizininin sahibini kullan
    home = os.environ.get("HOME", "/root")
    if home and home != "/root" and os.path.isdir(home):
        st = os.stat(home)
        os.chown(dosya, st.st_uid, st.st_gid)


def _veritabani_baslat():
    """Yerel veritabanını başlat ve varsayılan kaydı oluştur"""
    vt = VeritabaniYoneticisi()
    return vt


def _kurulum_gerekli_mi(vt):
    """DB'de geçerli bir kayıt ve anahtar var mı kontrol et"""
    kayit = vt.ilk_kaydi_al()
    if kayit is None:
        return True
    if not kayit.get("anahtar"):
        return True
    return False


def _kurulum_yap(vt):
    """Kurulum penceresi göster, bilgileri DB'ye kaydet. Başarısızsa çık."""
    pencere = KurulumPenceresi(
        mevcut_kurumkodu=VARSAYILAN_KURUM_KODU,
        mevcut_adi=VARSAYILAN_TAHTA_ADI
    )
    if pencere.exec_() == KurulumPenceresi.Accepted:
        vt.tahta_kaydi_olustur(
            kurumkodu=pencere.kurumkodu,
            adi=pencere.adi,
            durum=0,
            ses=1,
            anahtar=pencere.anahtar,
            kurum_adi=pencere.kurum_adi,
            url=pencere.url,
            tahta_id=pencere.tahta_id
        )
        return pencere.kurumkodu
    else:
        sys.exit(0)


def main():
    app = QApplication(sys.argv)
    _ayar_dosyasi_sahipligini_duzelt()
    vt = _veritabani_baslat()

    if _kurulum_gerekli_mi(vt):
        kurumkodu = _kurulum_yap(vt)
    else:
        kayit = vt.ilk_kaydi_al()
        kurumkodu = kayit["kurumkodu"]
        # Uygulama başlatıldığında kilitli duruma geç
        vt.durum_guncelle(kurumkodu, 0)

    kilit = Kilit(vt_yoneticisi=vt, kurumkodu=kurumkodu)
    kilit.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

