# -*- coding: utf-8 -*-
"""Ana kilit ekranı penceresi"""

import os
import glob
import json
import re
import time
import subprocess
import threading
import shutil
from io import BytesIO

# Ses akışı tespiti için regex
_RE_SINK_IDX = re.compile(r'^Sink Input #(\d+)$')
# Ses/video oynatan tarayıcıları tespit için binary isimleri
_TARAYICI_BINARIES = {
    "chromium", "chromium-browser",
    "brave", "brave-browser",
    "firefox", "firefox-esr",
    "google-chrome", "chrome",
    "opera", "opera-stable", "opera-beta", "opera-developer",
    "vivaldi", "vivaldi-stable",
}
# Kilit sırasında tamamen kapatılacak harici medya oynatıcılar
_MEDYA_OYNATICILARI = [
    "vlc", "mpv", "totem", "smplayer", "celluloid",
    "rhythmbox", "clementine", "audacious", "deadbeef",
]

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFrame, QApplication,
                             QDialog, QSizePolicy, QGridLayout, QComboBox,
                             QLineEdit, QFormLayout, QDialogButtonBox,
                             QFileDialog, QSystemTrayIcon, QMenu, QAction,
                             QProgressBar, QStackedWidget, QToolButton)
from PyQt5.QtCore import Qt, QTimer, QEvent, QUrl, QTime, QDate, QLocale, QSize, QSettings, pyqtSignal, QFileSystemWatcher
from PyQt5.QtGui import QFont, QCursor, QPixmap, QPainter, QColor, QBrush, QPainterPath, QIcon, QRegion, QPalette, QFontDatabase
import qtawesome as qta
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings, QWebEngineProfile
import vlc
import qrcode

from sabitler import BETIK_DIZINI, YENILEME_ARALIGI_SANIYE, VARSAYILAN_KURUM_KODU
from servisler import KodUretici, DogrulamaServisi
from dogrulama_penceresi import KodDogrulamaPenceresi
from veritabani import VeritabaniYoneticisi
from online_istemci import OnlineIstemci

def _fontlari_yukle():
    """Fontları yükle (QApplication oluştuktan sonra çağrılmalı)"""
    for dosya in ["Merriweather-Bold.ttf", "Merriweather-Regular.ttf"]:
        yol = os.path.join(BETIK_DIZINI, "resim", "fonts", dosya)
        if os.path.exists(yol):
            QFontDatabase.addApplicationFont(yol)


class YumusakIlerleme(QWidget):
    """Sub-piksel hassasiyette akıcı ilerleme çubuğu"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._oran = 1.0  # 0.0 – 1.0
        self._renk = QColor("#3498db")
        self._arka_renk = QColor("#e0e0e0")
        self._yuvarlak = 4.0
        self.setFixedHeight(8)

    def oran_ayarla(self, oran):
        self._oran = max(0.0, min(1.0, oran))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, r = self.width(), self.height(), self._yuvarlak

        # Arka plan
        arka = QPainterPath()
        arka.addRoundedRect(0, 0, w, h, r, r)
        p.fillPath(arka, QBrush(self._arka_renk))

        # Dolu kısım
        dolu_w = w * self._oran
        if dolu_w > 0.5:
            on = QPainterPath()
            on.addRoundedRect(0, 0, dolu_w, h, r, r)
            p.fillPath(on, QBrush(self._renk))

        p.end()


class AyarlarPenceresi(QDialog):
    """Kilit ekranı ayarlar penceresi"""

    def __init__(self, parent=None, vt_yoneticisi=None, kurumkodu=None):
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setFixedSize(450, 680)
        self.setStyleSheet("background-color: #f5f5f5;")

        self._vt = vt_yoneticisi or VeritabaniYoneticisi()
        self._kurumkodu = kurumkodu or VARSAYILAN_KURUM_KODU

        yerlesim = QVBoxLayout()
        yerlesim.setSpacing(18)
        yerlesim.setContentsMargins(35, 30, 35, 28)

        baslik = QLabel("Ayarlar")
        baslik_font = QFont("Noto Sans", 17)
        baslik_font.setWeight(QFont.DemiBold)
        baslik.setFont(baslik_font)
        baslik.setAlignment(Qt.AlignCenter)
        baslik.setStyleSheet("color: #2c3e50; background: transparent;")
        yerlesim.addWidget(baslik)

        ayirici = QFrame()
        ayirici.setFrameShape(QFrame.HLine)
        ayirici.setStyleSheet("color: #ddd; background: transparent;")
        yerlesim.addWidget(ayirici)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight)

        etiket_font = QFont("Noto Sans", 12)

        girdi_stili = """
            QLineEdit {
                padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px;
                background-color: #fafafa; color: #333; font-size: 13px;
            }
            QLineEdit:focus { border-color: #3498db; background-color: white; }
        """

        tahta_id_etiketi = QLabel("Tahta ID")
        tahta_id_etiketi.setFont(etiket_font)
        tahta_id_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        self._tahta_id_girisi = QLineEdit()
        self._tahta_id_girisi.setReadOnly(True)
        self._tahta_id_girisi.setStyleSheet("""
            QLineEdit {
                padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px;
                background-color: #eee; color: #555; font-size: 13px;
            }
        """)
        form.addRow(tahta_id_etiketi, self._tahta_id_girisi)

        kurum_etiketi = QLabel("Kurum Kodu")
        kurum_etiketi.setFont(etiket_font)
        kurum_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        self._kurum_girisi = QLineEdit()
        self._kurum_girisi.setPlaceholderText("Örn: 0001")
        self._kurum_girisi.setStyleSheet(girdi_stili)
        form.addRow(kurum_etiketi, self._kurum_girisi)

        kurum_adi_etiketi = QLabel("Kurum Adı")
        kurum_adi_etiketi.setFont(etiket_font)
        kurum_adi_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        self._kurum_adi_girisi = QLineEdit()
        self._kurum_adi_girisi.setPlaceholderText("Örn: Atatürk İlkokulu")
        self._kurum_adi_girisi.setStyleSheet(girdi_stili)
        form.addRow(kurum_adi_etiketi, self._kurum_adi_girisi)

        sinif_etiketi = QLabel("Tahta Adı")
        sinif_etiketi.setFont(etiket_font)
        sinif_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        self._sinif_girisi = QLineEdit()
        self._sinif_girisi.setPlaceholderText("Örn: 11E Sınıfı")
        self._sinif_girisi.setStyleSheet(girdi_stili)
        form.addRow(sinif_etiketi, self._sinif_girisi)

        anahtar_etiketi = QLabel("Gizli Anahtar")
        anahtar_etiketi.setFont(etiket_font)
        anahtar_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        self._anahtar_girisi = QLineEdit()
        self._anahtar_girisi.setPlaceholderText("Gizli doğrulama anahtarı")
        self._anahtar_girisi.setStyleSheet(girdi_stili)
        form.addRow(anahtar_etiketi, self._anahtar_girisi)

        url_etiketi = QLabel("WebView URL")
        url_etiketi.setFont(etiket_font)
        url_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        self._url_girisi = QLineEdit()
        self._url_girisi.setPlaceholderText("Örn: https://kulumtal.com/php/")
        self._url_girisi.setStyleSheet(girdi_stili)
        form.addRow(url_etiketi, self._url_girisi)

        logo_etiketi_form = QLabel("Kurum Logosu")
        logo_etiketi_form.setFont(etiket_font)
        logo_etiketi_form.setStyleSheet("color: #2c3e50; background: transparent;")
        logo_satir = QHBoxLayout()
        logo_satir.setSpacing(6)
        self._logo_yolu_girisi = QLineEdit()
        self._logo_yolu_girisi.setPlaceholderText("500x500 px PNG dosyası seçin")
        self._logo_yolu_girisi.setReadOnly(True)
        self._logo_yolu_girisi.setStyleSheet("""
            QLineEdit {
                padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px;
                background-color: #fafafa; color: #333; font-size: 13px;
            }
        """)
        logo_satir.addWidget(self._logo_yolu_girisi)
        logo_sec_btn = QPushButton("Seç...")
        logo_sec_btn.setCursor(QCursor(Qt.PointingHandCursor))
        logo_sec_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white; border: none;
                border-radius: 6px; padding: 8px 14px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        logo_sec_btn.clicked.connect(self._logo_sec)
        logo_satir.addWidget(logo_sec_btn)
        form.addRow(logo_etiketi_form, logo_satir)

        video_etiketi = QLabel("Video Klasörü")
        video_etiketi.setFont(etiket_font)
        video_etiketi.setStyleSheet("color: #2c3e50; background: transparent;")
        video_satir = QHBoxLayout()
        video_satir.setSpacing(6)
        self._video_girisi = QLineEdit()
        self._video_girisi.setPlaceholderText("Örn: /home/kullanici/Videolar")
        self._video_girisi.setReadOnly(True)
        self._video_girisi.setStyleSheet("""
            QLineEdit {
                padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px;
                background-color: #fafafa; color: #333; font-size: 13px;
            }
        """)
        video_satir.addWidget(self._video_girisi)
        gozat_btn = QPushButton("Gözat...")
        gozat_btn.setCursor(QCursor(Qt.PointingHandCursor))
        gozat_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white; border: none;
                border-radius: 6px; padding: 8px 14px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        gozat_btn.clicked.connect(self._klasor_sec)
        video_satir.addWidget(gozat_btn)
        form.addRow(video_etiketi, video_satir)

        # Kayıtlı ayarları yükle
        ayarlar = QSettings("KulumTal", "Tahta")
        self._video_girisi.setText(ayarlar.value("video_klasoru", ""))

        # Veritabanından mevcut verileri yükle
        kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        if kayit:
            self._tahta_id_girisi.setText(str(kayit.get("id", "")))
            self._kurum_girisi.setText(kayit.get("kurumkodu", ""))
            self._kurum_adi_girisi.setText(kayit.get("kurum_adi", ""))
            self._sinif_girisi.setText(kayit.get("adi", ""))
            self._anahtar_girisi.setText(kayit.get("anahtar", ""))
            self._url_girisi.setText(kayit.get("url", ""))

        yerlesim.addLayout(form)
        yerlesim.addStretch()

        btn_yerlesim = QHBoxLayout()
        btn_yerlesim.setSpacing(10)

        iptal_btn = QPushButton("İptal")
        iptal_btn.setCursor(QCursor(Qt.PointingHandCursor))
        iptal_btn.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1; color: #555; border: none;
                border-radius: 6px; padding: 9px 22px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #dfe4e6; }
        """)
        iptal_btn.clicked.connect(self.reject)
        btn_yerlesim.addWidget(iptal_btn)

        kaydet_btn = QPushButton("Kaydet")
        kaydet_btn.setCursor(QCursor(Qt.PointingHandCursor))
        kaydet_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db; color: white; border: none;
                border-radius: 6px; padding: 9px 22px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        kaydet_btn.clicked.connect(self._kaydet)
        btn_yerlesim.addWidget(kaydet_btn)

        yerlesim.addLayout(btn_yerlesim)
        self.setLayout(yerlesim)

    def _logo_sec(self):
        """Logo PNG seçme dialogu aç — 500x500 px zorunlu"""
        from PyQt5.QtWidgets import QMessageBox
        dosya, _ = QFileDialog.getOpenFileName(
            self, "Kurum Logosu Seç", os.path.expanduser("~"),
            "PNG Dosyası (*.png)",
            options=QFileDialog.DontUseNativeDialog
        )
        if not dosya:
            return
        pixmap = QPixmap(dosya)
        if pixmap.isNull():
            QMessageBox.warning(self, "Hata", "Geçersiz PNG dosyası!")
            return
        w, h = pixmap.width(), pixmap.height()
        if w != h:
            QMessageBox.warning(
                self, "Boyut Hatası",
                f"Logo kare olmalıdır (genişlik = yükseklik).\nSeçilen dosya: {w}x{h} px"
            )
            return
        if not (400 <= w <= 500):
            QMessageBox.warning(
                self, "Boyut Hatası",
                f"Logo 400x400 ile 500x500 px arasında olmalıdır.\nSeçilen dosya: {w}x{h} px"
            )
            return
        self._logo_yolu_girisi.setText(dosya)

    def _klasor_sec(self):
        """Klasör seçme dialogu aç"""
        mevcut = self._video_girisi.text().strip()
        baslangic = mevcut if mevcut and os.path.isdir(mevcut) else os.path.expanduser("~")
        klasor = QFileDialog.getExistingDirectory(
            self, "Video Klasörü Seç", baslangic,
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog
        )
        if klasor:
            self._video_girisi.setText(klasor)

    def _kaydet(self):
        """Ayarları QSettings'e ve veritabanına kaydet"""
        yeni_kurum = self._kurum_girisi.text().strip()
        yeni_adi = self._sinif_girisi.text().strip()
        yeni_anahtar = self._anahtar_girisi.text().strip()
        yeni_kurum_adi = self._kurum_adi_girisi.text().strip()
        yeni_url = self._url_girisi.text().strip()

        if not yeni_kurum:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Uyarı", "Kurum kodu boş bırakılamaz!")
            return
        if not yeni_adi:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Uyarı", "Tahta adı boş bırakılamaz!")
            return
        if not yeni_anahtar:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Uyarı", "Gizli anahtar boş bırakılamaz!")
            return

        # Mevcut kaydı güncelle
        mevcut = self._vt.tahta_kaydi_al(self._kurumkodu)
        if mevcut:
            durum = mevcut.get("durum", 0)
            ses = mevcut.get("ses", 1)
            # Kurum kodu değiştiyse eski kaydı güncelleyerek yeni kurum koduna taşı
            if self._kurumkodu != yeni_kurum:
                self._vt.kurumkodu_guncelle(self._kurumkodu, yeni_kurum)
            self._vt.tahta_kaydi_olustur(yeni_kurum, yeni_adi, durum=durum, ses=ses, anahtar=yeni_anahtar, kurum_adi=yeni_kurum_adi, url=yeni_url)

        # QSettings güncelle
        ayarlar = QSettings("KulumTal", "Tahta")
        dosya_yolu = ayarlar.fileName()
        if os.path.exists(dosya_yolu) and os.stat(dosya_yolu).st_uid != os.getuid():
            try:
                os.remove(dosya_yolu)
            except PermissionError:
                pass
            ayarlar = QSettings("KulumTal", "Tahta")
        ayarlar.setValue("video_klasoru", self._video_girisi.text().strip())
        ayarlar.sync()

        # Logo dosyasını kopyala
        logo_kaynak = self._logo_yolu_girisi.text().strip()
        if logo_kaynak and os.path.isfile(logo_kaynak):
            hedef = os.path.join(BETIK_DIZINI, "resim", "logo.png")
            try:
                shutil.copy2(logo_kaynak, hedef)
            except Exception as e:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Logo Kaydedilemedi", str(e))

        self.accept()


class Kilit(QMainWindow):
    _video_hazir = pyqtSignal(str, list)

    def __init__(self, vt_yoneticisi=None, kurumkodu=None):
        super().__init__()
        self._video_hazir.connect(self._video_katman_olustur)
        self._kilit_acma_istendi = False
        # Gizli anahtarı veritabanından oku
        self._vt = vt_yoneticisi or VeritabaniYoneticisi()
        self._kurumkodu = kurumkodu or VARSAYILAN_KURUM_KODU
        db_anahtar = self._vt.anahtar_al(self._kurumkodu)
        self._kod_uretici = KodUretici(gizli_anahtar=db_anahtar)
        self._dogrulama_servisi = DogrulamaServisi(gizli_anahtar=db_anahtar)
        self._suanki_challenge = ""
        self._son_zaman_indeksi = -1
        self._aktif_dialog = None
        self._video_katmani = None
        self._video_btn = None
        self._video_gizli = False

        self._son_db_durum = None  # Son okunan DB durumu

        # Tahta ID'yi erken al (QR oluşturmada lazım)
        tahta_kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        tahta_adi = tahta_kayit["adi"] if tahta_kayit else "Tahta"
        tahta_id = tahta_kayit.get("id", "") if tahta_kayit else ""
        tahta_anahtar = tahta_kayit.get("anahtar", "") if tahta_kayit else ""
        self._tahta_id = tahta_id

        # Odak zamanlayıcısı (sistemi_kilitle'den önce oluştur)
        self._odak_zamanlayici = QTimer(self)
        self._odak_zamanlayici.timeout.connect(self._ustte_kal)

        self.arayuz_baslat()

        # Online istemciyi başlat
        self._online = OnlineIstemci(self._kurumkodu, tahta_adi, tahta_id=tahta_id, anahtar=tahta_anahtar, parent=self)
        self._online.kilitle_sinyali.connect(self._online_kilitle)
        self._online.kilidi_ac_sinyali.connect(self._online_kilidi_ac)
        self._online.ses_kapat_sinyali.connect(self._online_ses_kapat)
        self._online.ses_ac_sinyali.connect(self._online_ses_ac)
        self._online.baglanti_durumu_sinyali.connect(self._online_baglanti_degisti)
        self._online.durum_bilgisi_sinyali.connect(self._online_durum_senkronize)
        self._online.ders_saatleri_sinyali.connect(self._ders_saatleri_guncelle)
        self._online.tahta_adi_sinyali.connect(self._tahta_adi_guncelle)
        self._online.baslat()

        # Ders çıkış saatleri kontrolü (her saniye kontrol et)
        self._son_tetiklenen_ders_saati = ""
        self._son_tetiklenen_bildirim_saati = ""
        self._ders_saati_zamanlayici = QTimer(self)
        self._ders_saati_zamanlayici.timeout.connect(self._ders_saati_kontrol)
        self._ders_saati_zamanlayici.start(1000)

        # Başlangıçta DB durumuna göre kilitle veya açık bırak
        self._baslangic_durumu_uygula()

    def arayuz_baslat(self):
        """Arayüzü başlat"""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
        )

        ekran = QApplication.primaryScreen()
        geometri = ekran.geometry()
        self.setGeometry(geometri)

        ana_widget = QWidget()
        self.setCentralWidget(ana_widget)
        ana_yerlesim = QHBoxLayout()
        ana_yerlesim.setContentsMargins(0, 0, 0, 0)
        ana_yerlesim.setSpacing(0)

        # ===================== SOL SIDEBAR (300px) =====================
        kenar_cubugu = QFrame()
        kenar_cubugu.setFixedWidth(300)
        kenar_cubugu.setStyleSheet("QFrame { background-color: #f5f5f5; }")
        kenar_yerlesim = QVBoxLayout()
        kenar_yerlesim.setContentsMargins(20, 20, 20, 20)

        # Logolar (yan yana)
        logo_yerlesim = QHBoxLayout()
        logo_yerlesim.setSpacing(10)

        turk_etiketi = QLabel()
        turk_pixmap = QPixmap(os.path.join(BETIK_DIZINI, "resim", "turk.png"))
        if not turk_pixmap.isNull():
            turk_etiketi.setPixmap(turk_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        turk_etiketi.setAlignment(Qt.AlignCenter)
        turk_etiketi.setStyleSheet("border: none;")
        logo_yerlesim.addWidget(turk_etiketi)

        self._logo_etiketi = QLabel()
        logo_pixmap = QPixmap(os.path.join(BETIK_DIZINI, "resim", "logo.png"))
        if not logo_pixmap.isNull():
            self._logo_etiketi.setPixmap(logo_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._logo_etiketi.setAlignment(Qt.AlignCenter)
        self._logo_etiketi.setStyleSheet("border: none;")
        logo_yerlesim.addWidget(self._logo_etiketi)

        kenar_yerlesim.addLayout(logo_yerlesim)
        kenar_yerlesim.addSpacing(4)

        # Fontları yükle
        _fontlari_yukle()

        # Saat etiketi
        self.saat_etiketi = QLabel()
        saat_yazi_tipi = QFont("Merriweather", 50)
        saat_yazi_tipi.setWeight(QFont.Bold)
        self.saat_etiketi.setFont(saat_yazi_tipi)
        self.saat_etiketi.setStyleSheet("color: #1a2533; border: none; letter-spacing: 3px;")
        self.saat_etiketi.setAlignment(Qt.AlignCenter)
        kenar_yerlesim.addWidget(self.saat_etiketi)

        # Tarih etiketi
        self.tarih_etiketi = QLabel()
        tarih_yazi_tipi = QFont("Merriweather", 12)
        tarih_yazi_tipi.setWeight(QFont.DemiBold)
        self.tarih_etiketi.setFont(tarih_yazi_tipi)
        self.tarih_etiketi.setStyleSheet("color: #34495e; border: none; letter-spacing: 1px;")
        self.tarih_etiketi.setAlignment(Qt.AlignCenter)
        kenar_yerlesim.addWidget(self.tarih_etiketi)

        # Tahta adı etiketi
        ust_cizgi = QFrame()
        ust_cizgi.setFrameShape(QFrame.HLine)
        ust_cizgi.setStyleSheet("color: #d0d0d0;")
        kenar_yerlesim.addSpacing(10)
        kenar_yerlesim.addWidget(ust_cizgi)

        tahta_adi = self._vt.tahta_kaydi_al(self._kurumkodu)
        tahta_adi_metin = tahta_adi["adi"] if tahta_adi else "Tahta"
        self._tahta_adi_etiketi = QLabel(tahta_adi_metin)
        sinif_yazi_tipi = QFont("Merriweather", 12)
        sinif_yazi_tipi.setWeight(QFont.Bold)
        self._tahta_adi_etiketi.setFont(sinif_yazi_tipi)
        self._tahta_adi_etiketi.setStyleSheet("color: #2c3e50; border: none; padding: 10px;")
        self._tahta_adi_etiketi.setAlignment(Qt.AlignCenter)
        kenar_yerlesim.addWidget(self._tahta_adi_etiketi)

        alt_cizgi = QFrame()
        alt_cizgi.setFrameShape(QFrame.HLine)
        alt_cizgi.setStyleSheet("color: #d0d0d0;")
        kenar_yerlesim.addWidget(alt_cizgi)
        kenar_yerlesim.addSpacing(10)

        # Challenge sistemini başlat (widget'lar aşağıda oluşturulacak)

        # Saat ve tarihi güncelle
        self._saat_guncelle()
        self._saat_zamanlayici = QTimer(self)
        self._saat_zamanlayici.timeout.connect(self._saat_guncelle)
        self._saat_zamanlayici.start(1000)

        kenar_yerlesim.addStretch()

        qr_ust_cizgi = QFrame()
        qr_ust_cizgi.setFrameShape(QFrame.HLine)
        qr_ust_cizgi.setStyleSheet("color: #d0d0d0;")
        kenar_yerlesim.addWidget(qr_ust_cizgi)
        kenar_yerlesim.addSpacing(10)

        # QR Kod etiketi
        self._qr_etiketi = QLabel()
        self._qr_etiketi.setAlignment(Qt.AlignCenter)
        self._qr_etiketi.setStyleSheet("border: none;")
        self._qr_etiketi.setFixedSize(200, 200)
        kenar_yerlesim.addWidget(self._qr_etiketi, alignment=Qt.AlignHCenter)

        # Challenge kodu etiketi (gizli — sadece dahili kullanım)
        self._challenge_etiketi = QLabel()
        self._challenge_etiketi.hide()

        # Süre ilerleme çubuğu (QR ile aynı genişlikte)
        self._sure_cubugu = YumusakIlerleme()
        self._sure_cubugu.setFixedWidth(200)
        self._sure_cubugu.setFixedHeight(4)
        kenar_yerlesim.addWidget(self._sure_cubugu, alignment=Qt.AlignHCenter)

        # Challenge sistemini başlat
        self._challenge_guncelle()

        # Challenge yenileme zamanlayıcısı (akıcı ilerleme çubuğu için 50 ms)
        self._challenge_zamanlayici = QTimer(self)
        self._challenge_zamanlayici.timeout.connect(self._challenge_tikla)
        self._challenge_zamanlayici.start(50)

        kenar_yerlesim.addSpacing(8)

        # Alt buton satırı: Ayarlar | Kilidi Aç | Kapat
        buton_satiri = QHBoxLayout()
        buton_satiri.setSpacing(12)

        seffaf_buton_stili = """
            QPushButton {
                background-color: transparent; border: none;
                border-radius: 10px; padding: 12px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,30); }
            QPushButton:pressed { background-color: rgba(255,255,255,50); }
        """

        # Video aç/kapat butonu
        self._video_toggle_btn = QPushButton()
        self._video_toggle_btn.setIcon(qta.icon('fa5s.eye-slash', color='#95a5a6'))
        self._video_toggle_btn.setIconSize(QSize(28, 28))
        self._video_toggle_btn.setFixedSize(60, 50)
        self._video_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._video_toggle_btn.setToolTip("Video Göster/Gizle")
        self._video_toggle_btn.setStyleSheet(seffaf_buton_stili)
        self._video_toggle_btn.clicked.connect(self._video_gizle_goster)
        self._video_toggle_btn.hide()  # Video hazır olana kadar gizli
        buton_satiri.addWidget(self._video_toggle_btn)

        # Ayarlar butonu
        ayarlar_butonu = QPushButton()
        ayarlar_butonu.setIcon(qta.icon('fa5s.cog', color='#95a5a6'))
        ayarlar_butonu.setIconSize(QSize(28, 28))
        ayarlar_butonu.setFixedSize(60, 50)
        ayarlar_butonu.setCursor(QCursor(Qt.PointingHandCursor))
        ayarlar_butonu.setToolTip("Ayarlar")
        ayarlar_butonu.setStyleSheet(seffaf_buton_stili)
        ayarlar_butonu.clicked.connect(self._ayarlar_goster)
        buton_satiri.addWidget(ayarlar_butonu)

        # Kilidi Aç butonu
        self._kilit_ac_butonu = QPushButton()
        self._kilit_ac_butonu.setIcon(qta.icon('fa5s.lock-open', color='#e74c3c'))
        self._kilit_ac_butonu.setIconSize(QSize(28, 28))
        self._kilit_ac_butonu.setFixedSize(60, 50)
        self._kilit_ac_butonu.setCursor(QCursor(Qt.PointingHandCursor))
        self._kilit_ac_butonu.setToolTip("Kilidi Aç")
        self._kilit_ac_butonu.setStyleSheet(seffaf_buton_stili)
        self._kilit_ac_butonu.clicked.connect(self._kilidi_ac_dialogu_goster)
        buton_satiri.addWidget(self._kilit_ac_butonu)

        # Bilgisayarı Kapat butonu
        kapat_butonu = QPushButton()
        kapat_butonu.setIcon(qta.icon('fa5s.power-off', color='#95a5a6'))
        kapat_butonu.setIconSize(QSize(28, 28))
        kapat_butonu.setFixedSize(60, 50)
        kapat_butonu.setCursor(QCursor(Qt.PointingHandCursor))
        kapat_butonu.setToolTip("Bilgisayarı Kapat")
        kapat_butonu.setStyleSheet(seffaf_buton_stili)
        kapat_butonu.clicked.connect(self._bilgisayari_kapat)
        buton_satiri.addWidget(kapat_butonu)

        kenar_yerlesim.addLayout(buton_satiri)
        kenar_yerlesim.addSpacing(20)

        # İmza
        imza_etiketi = QLabel("@2026 KuluMtal")
        imza_etiketi.setAlignment(Qt.AlignCenter)
        imza_etiketi.setStyleSheet("color: #b0b0b0; border: none; font-size: 10px;")

        # Sidebar ana layout: içerik + alt bar
        sidebar_ana_yerlesim = QVBoxLayout()
        sidebar_ana_yerlesim.setContentsMargins(0, 0, 0, 0)
        sidebar_ana_yerlesim.setSpacing(0)
        sidebar_ana_yerlesim.addLayout(kenar_yerlesim)

        # İmza - progress bar'ın hemen üstünde
        imza_etiketi.setContentsMargins(0, 0, 0, 0)
        sidebar_ana_yerlesim.addWidget(imza_etiketi)
        sidebar_ana_yerlesim.addSpacing(2)

        # Kapanma geri sayım barı (en altta, kenarlara sıfır mesafe)
        self._kapanma_suresi = 15 * 60  # 15 dakika
        self._kapanma_kalan = self._kapanma_suresi
        self._kapanma_bar = YumusakIlerleme()
        self._kapanma_bar.setFixedHeight(6)
        self._kapanma_bar._renk = QColor("#e74c3c")
        self._kapanma_bar._arka_renk = QColor("#ddd")
        self._kapanma_bar._yuvarlak = 0.0
        self._kapanma_bar.oran_ayarla(1.0)
        sidebar_ana_yerlesim.addWidget(self._kapanma_bar)

        kenar_cubugu.setLayout(sidebar_ana_yerlesim)
        ana_yerlesim.addWidget(kenar_cubugu)

        # ===================== SAĞ İÇERİK ALANI (Stacked: Web + Video) =====================
        self._icerik_yigini = QStackedWidget()
        ana_yerlesim.addWidget(self._icerik_yigini)

        # Sayfa 0: Web
        self._web_alani = QWidget()
        self._web_yerlesim = QVBoxLayout()
        self._web_yerlesim.setContentsMargins(0, 0, 0, 0)
        self._web_alani.setLayout(self._web_yerlesim)
        self._icerik_yigini.addWidget(self._web_alani)

        # Sayfa 1: Video (başlangıçta boş, sonra doldurulacak)
        self._video_alani = QWidget()
        self._video_alani.setStyleSheet("background-color: black;")
        self._video_alani_yerlesim = QVBoxLayout()
        self._video_alani_yerlesim.setContentsMargins(0, 0, 0, 0)
        self._video_alani_yerlesim.setSpacing(0)
        self._video_alani.setLayout(self._video_alani_yerlesim)
        self._icerik_yigini.addWidget(self._video_alani)

        # WebView'ı hemen oluştur (Chromium motoru erken başlasın)
        profil = QWebEngineProfile.defaultProfile()
        profil.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        profil.setCachePath(os.path.join(os.path.expanduser('~'), '.cache', 'tahta-kilit'))
        profil.setPersistentStoragePath(os.path.join(os.path.expanduser('~'), '.cache', 'tahta-kilit', 'storage'))

        self.web_gorunum = QWebEngineView()
        self.web_gorunum.settings().setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        self.web_gorunum.settings().setAttribute(QWebEngineSettings.WebGLEnabled, True)
        # URL'yi veritabanından oku, yoksa varsayılanı kullan
        db_url = self._vt.url_al(self._kurumkodu)
        webview_url = db_url if db_url else "https://kulumtal.com/php/"
        self.web_gorunum.setUrl(QUrl(webview_url))
        self._web_yerlesim.addWidget(self.web_gorunum)

        ana_widget.setLayout(ana_yerlesim)
        self.setStyleSheet("background-color: #1a1a2e;")

        # Kapanma geri sayım zamanlayıcısı
        self._kapanma_zamanlayici = QTimer(self)
        self._kapanma_zamanlayici.timeout.connect(self._kapanma_tikla)
        self._kapanma_zamanlayici.start(1000)

    def _kapanma_tikla(self):
        """Kapanma geri sayımını güncelle"""
        self._kapanma_kalan -= 1
        self._kapanma_bar.oran_ayarla(max(self._kapanma_kalan, 0) / self._kapanma_suresi)
        # Her 30 saniyede bir veya son 60 saniyede her saniye sunucuya bildir
        if self._kapanma_kalan % 30 == 0 or self._kapanma_kalan <= 60:
            try:
                self._online.kapanma_bildir(self._kapanma_kalan)
            except Exception:
                pass
        if self._kapanma_kalan <= 0:
            self._kapanma_zamanlayici.stop()
            subprocess.Popen(["systemctl", "poweroff"])

    # ===================== VERİTABANI İZLEME =====================

    # ===================== ONLİNE KOMUT İŞLEYİCİLER =====================

    def _online_kilitle(self):
        """Sunucudan kilitle komutu geldi"""
        if not self._kilit_acma_istendi:
            return  # Zaten kilitli
        self._aktif_dialog_kapat()
        self._tekrar_kilitle()

    def _online_kilidi_ac(self):
        """Sunucudan kilidi aç komutu geldi"""
        if self._kilit_acma_istendi:
            return  # Zaten açık
        self._aktif_dialog_kapat()
        self.kilidi_ac(sure_dakika=40)

    def _aktif_dialog_kapat(self):
        """Açık doğrulama/ayar dialogunu kapat"""
        if self._aktif_dialog is not None:
            self._aktif_dialog.dogrulandi = False
            self._aktif_dialog.reject()
            self._aktif_dialog = None

    def _online_ses_kapat(self):
        """Sunucudan sesi kapat komutu geldi"""
        self._vt.ses_guncelle(self._kurumkodu, 0)
        self._ses_durumu_uygula()

    def _online_ses_ac(self):
        """Sunucudan sesi aç komutu geldi"""
        self._vt.ses_guncelle(self._kurumkodu, 1)
        self._ses_durumu_uygula()

    def _online_baglanti_degisti(self, bagli):
        """Sunucu bağlantı durumu değişti"""
        durum = "Bağlı" if bagli else "Çevrimdışı"
        print(f"[ONLİNE] Sunucu: {durum}")
        renk = '#27ae60' if bagli else '#e74c3c'
        self._kilit_ac_butonu.setIcon(qta.icon('fa5s.lock-open', color=renk))

    def _online_durum_senkronize(self, durum, ses):
        """Sunucudan gelen durum bilgisiyle senkronize ol (sunucu formatı: 1=kilitli, 0=açık)"""
        # Ses durumunu senkronize et
        if ses == 0:
            self._online_ses_kapat()
        else:
            self._online_ses_ac()

        # Kilit durumunu senkronize et
        if durum == 1:
            self._online_kilitle()
        elif durum == 0:
            self._online_kilidi_ac()

    def _ders_saatleri_guncelle(self, veri):
        """Sunucudan gelen ders çıkış saatlerini yerel DB'ye kaydet"""
        try:
            aktif = veri.get("aktif", 0)
            saatler = veri.get("saatler", [])
            self._vt.ders_saatleri_kaydet(saatler, aktif)
            print(f"[DERS SAATLERİ] Güncellendi: aktif={aktif}, {len(saatler)} saat")
        except Exception as e:
            print(f"[DERS SAATLERİ] Kaydetme hatası: {e}")

    def _ders_saati_kontrol(self):
        """Her saniye ders çıkış saati kontrolü yap"""
        try:
            veri = self._vt.ders_saatleri_al()
            if not veri or veri.get("aktif", 0) != 1:
                return

            simdi = QTime.currentTime()

            for item in veri.get("saatler", []):
                saat = item.get("saat", "")
                if not saat:
                    continue
                saat_obj = QTime.fromString(saat, "HH:mm")
                diff = simdi.secsTo(saat_obj)

                # 30 saniye öncesi bildirim (27-33 saniyelik eşleşme penceresi)
                if 27 <= diff <= 33 and saat != self._son_tetiklenen_bildirim_saati:
                    self._son_tetiklenen_bildirim_saati = saat
                    self._ders_bildirim_goster(saat)

                # Kilitleme zamanı (0-2 saniye tolerans)
                if 0 <= diff <= 2 and saat != self._son_tetiklenen_ders_saati:
                    self._son_tetiklenen_ders_saati = saat
                    print(f"[DERS SAATİ] Ders çıkış saati geldi: {saat} — kilitleniyor")
                    if self._kilit_acma_istendi:
                        self._aktif_dialog_kapat()
                        self._tekrar_kilitle()
                    return
        except Exception as e:
            print(f"[DERS SAATİ] Kontrol hatası: {e}")

    def _ders_bildirim_goster(self, saat):
        """Ders çıkış saatine 30 saniye kala ekranda bildirim göster"""
        if hasattr(self, '_ders_bildirimi') and self._ders_bildirimi:
            try:
                self._ders_bildirimi.close()
            except Exception:
                pass

        bildirim = QWidget()
        bildirim.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.X11BypassWindowManagerHint
        )
        bildirim.setAttribute(Qt.WA_TranslucentBackground)

        ekran = QApplication.primaryScreen().geometry()

        ana = QVBoxLayout(bildirim)
        ana.setContentsMargins(0, 0, 0, 0)

        cerceve = QFrame()
        cerceve.setStyleSheet("""
            QFrame {
                background-color: rgba(44, 62, 80, 210);
                border-radius: 10px;
            }
        """)
        ic = QHBoxLayout(cerceve)
        ic.setContentsMargins(16, 10, 16, 10)
        ic.setSpacing(8)

        ikon = QLabel()
        fa_ikon = qta.icon('fa5s.bell', color='#f0c040')
        ikon.setPixmap(fa_ikon.pixmap(24, 24))
        ikon.setStyleSheet("background: transparent;")
        ic.addWidget(ikon)

        metin = QLabel(f"Ders <b>{saat}</b>'de bitiyor — 30 saniye kaldı")
        metin.setFont(QFont("Noto Sans", 11))
        metin.setStyleSheet("color: #ecf0f1; background: transparent;")
        metin.setWordWrap(True)
        ic.addWidget(metin, 1)

        ana.addWidget(cerceve)

        bildirim.adjustSize()
        bildirim.setFixedWidth(min(bildirim.sizeHint().width() + 20, 420))
        bildirim.adjustSize()
        bildirim.move(ekran.center().x() - bildirim.width() // 2, 24)

        self._ders_bildirimi = bildirim
        bildirim.show()
        bildirim.raise_()
        QTimer.singleShot(10000, bildirim.close)

    def _baslangic_durumu_uygula(self):
        """Başlangıçta daima kilitli başla ve DB izleme başlat"""
        self._son_db_durum = 0
        self._ses_durumu_uygula()
        self.sistemi_kilitle()

        # DB dosya izleme (inotify tabanlı — anlık tepki)
        self._db_izleyici = QFileSystemWatcher([self._vt._db_yolu], self)
        self._db_izleyici.fileChanged.connect(self._db_dosya_degisti)

        # Güvenlik ağı: dosya izleyici kaçırırsa diye yedek kontrol (30 sn)
        self._db_yedek_zamanlayici = QTimer(self)
        self._db_yedek_zamanlayici.timeout.connect(self._db_durum_kontrol)
        self._db_yedek_zamanlayici.start(30000)

    def _db_dosya_degisti(self, yol):
        """DB dosyası değiştiğinde inotify tarafından tetiklenir"""
        # Bazı yazma işlemleri dosyayı silip yeniden oluşturur,
        # bu durumda izleyiciden düşer — tekrar ekle
        izlenen = self._db_izleyici.files()
        if self._vt._db_yolu not in izlenen:
            self._db_izleyici.addPath(self._vt._db_yolu)
        self._db_durum_kontrol()

    def _tahta_adi_guncelle(self, yeni_adi):
        """Sunucudan gelen tahta adı güncellemesini uygula ve yerel DB'ye kaydet"""
        if yeni_adi and self._tahta_adi_etiketi.text() != yeni_adi:
            self._tahta_adi_etiketi.setText(yeni_adi)
            self._vt.adi_guncelle(self._kurumkodu, yeni_adi)

    def _db_durum_kontrol(self):
        """Veritabanındaki durum değişikliğini kontrol et"""
        kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        if kayit is None:
            return

        # Tahta adı değiştiyse etiketi güncelle
        yeni_adi = kayit["adi"]
        if self._tahta_adi_etiketi.text() != yeni_adi:
            self._tahta_adi_etiketi.setText(yeni_adi)

        yeni_durum = kayit["durum"]
        yeni_ses = kayit["ses"]

        # Ses durumu değiştiyse uygula
        if not hasattr(self, '_son_ses_durum') or self._son_ses_durum != yeni_ses:
            self._son_ses_durum = yeni_ses
            self._ses_durumu_uygula()

        # Durum değişmediyse bir şey yapma
        if yeni_durum == self._son_db_durum:
            return

        eski_durum = self._son_db_durum
        self._son_db_durum = yeni_durum

        if yeni_durum == 0 and eski_durum == 1:
            # Açık → Kilitli: ekranı kilitle
            self._db_kilitle()
        elif yeni_durum == 1 and eski_durum == 0:
            # Kilitli → Açık: kilidi aç
            self._db_kilidi_ac()

    def _db_kilitle(self):
        """Veritabanı üzerinden gelen kilit komutu"""
        if not self._kilit_acma_istendi:
            return  # Zaten kilitli

        # Açık kilit penceresi varsa kapat
        if hasattr(self, '_geri_sayim_zamanlayici') and self._geri_sayim_zamanlayici.isActive():
            self._geri_sayim_zamanlayici.stop()
        if hasattr(self, '_tekrar_kilitle_zamanlayici') and self._tekrar_kilitle_zamanlayici.isActive():
            self._tekrar_kilitle_zamanlayici.stop()
        if hasattr(self, '_kilitle_pencere') and self._kilitle_pencere:
            self._kilitle_pencere.close()
            self._kilitle_pencere = None
        if hasattr(self, '_tray_icon') and self._tray_icon:
            self._tray_icon.hide()
            self._tray_icon = None

        self._tekrar_kilitle()

    def _db_kilidi_ac(self):
        """Veritabanı üzerinden gelen kilit açma komutu"""
        if self._kilit_acma_istendi:
            return  # Zaten açık

        self._kilit_acma_istendi = True
        self._odak_zamanlayici.stop()
        self._challenge_zamanlayici.stop()
        self._saat_zamanlayici.stop()
        self._kapanma_zamanlayici.stop()
        self.releaseKeyboard()

        # Videoyu duraklat
        if self._video_katmani and hasattr(self, '_vlc_list_player') and self._vlc_list_player:
            self._vlc_list_player.pause()

        self.hide()

    def _ses_durumu_uygula(self):
        """Ses durumunu sisteme uygula"""
        kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        if kayit is None:
            return
        ses = kayit["ses"]
        self._son_ses_durum = ses
        try:
            if ses == 0:
                subprocess.Popen(
                    ["amixer", "set", "Master", "mute"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["amixer", "set", "Master", "unmute"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except FileNotFoundError:
            pass

    def _saat_guncelle(self):
        """Saat ve tarihi güncelle"""
        simdi = QTime.currentTime()
        self.saat_etiketi.setText(simdi.toString("HH:mm"))

        yerel = QLocale(QLocale.Turkish)
        bugun = QDate.currentDate()
        gun = bugun.day()
        ay = yerel.monthName(bugun.month())
        yil = bugun.year()
        gun_adi = yerel.dayName(bugun.dayOfWeek())
        self.tarih_etiketi.setText(f"{gun} {ay} {yil} {gun_adi}")

    def _challenge_guncelle(self):
        """Challenge kodunu ve QR'ı güncelle"""
        self._suanki_challenge = self._kod_uretici.kod_uret()
        self._challenge_etiketi.setText(f"Kod: {self._suanki_challenge}")
        self._qr_olustur(self._suanki_challenge)
        self._son_zaman_indeksi = int(time.time()) // YENILEME_ARALIGI_SANIYE
        if self._aktif_dialog is not None:
            self._aktif_dialog.challenge_guncelle(self._suanki_challenge)

    def _challenge_tikla(self):
        """Sık çağrılır — süre çubuğu akıcı güncelleme + periyodik yenileme"""
        kalan = self._kod_uretici.kalan_saniye()
        self._sure_cubugu.oran_ayarla(kalan / YENILEME_ARALIGI_SANIYE)

        mevcut_indeks = int(time.time()) // YENILEME_ARALIGI_SANIYE
        if mevcut_indeks != self._son_zaman_indeksi:
            self._challenge_guncelle()

    def _yeni_rastgele_challenge(self):
        """3 hatalı girişte çağrılır — rastgele challenge üretir"""
        self._suanki_challenge = self._kod_uretici.rastgele_kod_uret()
        self._challenge_etiketi.setText(f"Kod: {self._suanki_challenge}")
        self._qr_olustur(self._suanki_challenge)
        return self._suanki_challenge

    def _qr_olustur(self, challenge_kodu):
        """Tahta UUID ve challenge kodundan QR kodu oluştur"""
        import json
        qr_veri = json.dumps({"uuid": self._tahta_id, "challenge": challenge_kodu}, ensure_ascii=False)
        qr_url = qr_veri
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=8, border=2)
        qr.add_data(qr_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        self._qr_etiketi.setPixmap(
            pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _kilidi_ac_dialogu_goster(self):
        """Doğrulama dialogunu göster"""
        # Zaten açık bir doğrulama penceresi varsa kapat
        if self._aktif_dialog is not None:
            self._aktif_dialog.reject()
            self._aktif_dialog = None

        self.releaseKeyboard()
        self._odak_zamanlayici.stop()

        dialog = KodDogrulamaPenceresi(
            self._suanki_challenge,
            self._dogrulama_servisi,
            self._yeni_rastgele_challenge,
            parent=self
        )
        self._aktif_dialog = dialog
        ekran = QApplication.primaryScreen().geometry()
        dialog.move(
            ekran.center().x() - dialog.width() // 2,
            ekran.center().y() - dialog.height() // 2
        )
        dialog.show()
        dialog.activateWindow()
        dialog.raise_()
        dialog.grabKeyboard()
        dialog._giris_kutusu.setFocus()

        dialog.exec_()
        self._aktif_dialog = None
        if dialog.dogrulandi:
            self.kilidi_ac(dialog.acik_kalma_suresi)
        elif not self._kilit_acma_istendi:
            self._odak_zamanlayici.start(1000)
            QTimer.singleShot(200, self._girisleri_yakala)

    def _ayarlar_goster(self):
        """Doğrulama sonrası ayarlar penceresini göster"""
        # Zaten açık bir doğrulama penceresi varsa kapat
        if self._aktif_dialog is not None:
            self._aktif_dialog.reject()
            self._aktif_dialog = None

        self.releaseKeyboard()
        self._odak_zamanlayici.stop()

        # Önce doğrulama yap
        dialog = KodDogrulamaPenceresi(
            self._suanki_challenge,
            self._dogrulama_servisi,
            self._yeni_rastgele_challenge,
            parent=self,
            sure_goster=False
        )
        self._aktif_dialog = dialog
        ekran = QApplication.primaryScreen().geometry()
        dialog.move(
            ekran.center().x() - dialog.width() // 2,
            ekran.center().y() - dialog.height() // 2
        )
        dialog.show()
        dialog.activateWindow()
        dialog.raise_()
        dialog.grabKeyboard()
        dialog._giris_kutusu.setFocus()
        dialog.exec_()
        self._aktif_dialog = None

        if not dialog.dogrulandi:
            if not self._kilit_acma_istendi:
                self._odak_zamanlayici.start(1000)
                QTimer.singleShot(200, self._girisleri_yakala)
            return

        # Doğrulama başarılı — kilit ekranını gizle, ayarları aç
        self.hide()
        ayarlar = AyarlarPenceresi(parent=None, vt_yoneticisi=self._vt, kurumkodu=self._kurumkodu)
        ayarlar.move(
            ekran.center().x() - ayarlar.width() // 2,
            ekran.center().y() - ayarlar.height() // 2
        )
        ayarlar.show()
        ayarlar.activateWindow()
        ayarlar.raise_()
        sonuc = ayarlar.exec_()

        # Ayarlar kapandı — kilidi tekrar etkinleştir
        self.show()
        if sonuc == QDialog.Accepted:
            self._video_yenile()
            self._logo_yenile()
            self._webview_url_yenile()
            # Ayarlardan anahtar/kurum değişmiş olabilir — online istemciyi güncelle
            yeni_kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
            if yeni_kayit:
                yeni_anahtar = yeni_kayit.get("anahtar", "")
                if yeni_anahtar != self._online._anahtar:
                    self._online._anahtar = yeni_anahtar
                    self._online.baglantiyi_kontrol_et()
                    print(f"[ONLİNE] Anahtar güncellendi, yeniden bağlanılıyor")
        self._odak_zamanlayici.start(1000)
        QTimer.singleShot(200, self._girisleri_yakala)

    def _bilgisayari_kapat(self):
        """Onay alarak bilgisayarı kapat"""
        self.releaseKeyboard()
        self._odak_zamanlayici.stop()

        onay = QDialog(self)
        onay.setWindowTitle("Kapatma Onayı")
        onay.setFixedSize(420, 180)
        onay.setWindowFlags(
            Qt.Dialog
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
        )
        onay.setStyleSheet("background-color: #f5f5f5;")

        oy = QVBoxLayout()
        oy.setContentsMargins(25, 20, 25, 20)
        oy.setSpacing(15)

        mesaj = QLabel("Bilgisayarı kapatmak istediğinize\nemin misiniz?")
        mesaj.setAlignment(Qt.AlignCenter)
        mesaj_font = QFont("Noto Sans", 13)
        mesaj_font.setWeight(QFont.DemiBold)
        mesaj.setFont(mesaj_font)
        mesaj.setStyleSheet("color: #2c3e50;")
        oy.addWidget(mesaj)

        btn_yerlesim = QHBoxLayout()
        btn_yerlesim.setSpacing(10)

        iptal_btn = QPushButton("İptal")
        iptal_btn.setCursor(QCursor(Qt.PointingHandCursor))
        iptal_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6; color: white; border: none;
                border-radius: 6px; padding: 10px 25px; font-weight: bold;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        iptal_btn.clicked.connect(onay.reject)
        btn_yerlesim.addWidget(iptal_btn)

        evet_btn = QPushButton("Kapat")
        evet_btn.setCursor(QCursor(Qt.PointingHandCursor))
        evet_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; color: white; border: none;
                border-radius: 6px; padding: 10px 25px; font-weight: bold;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        evet_btn.clicked.connect(onay.accept)
        btn_yerlesim.addWidget(evet_btn)

        oy.addLayout(btn_yerlesim)
        onay.setLayout(oy)

        ekran = QApplication.primaryScreen().geometry()
        onay.move(
            ekran.center().x() - onay.width() // 2,
            ekran.center().y() - onay.height() // 2
        )
        onay.show()
        onay.activateWindow()
        onay.raise_()
        onay.grabKeyboard()
        sonuc = onay.exec_()
        onay.releaseKeyboard()

        if sonuc == QDialog.Accepted:
            subprocess.Popen(
                ["systemctl", "poweroff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            self._odak_zamanlayici.start(1000)
            QTimer.singleShot(200, self._girisleri_yakala)

    def _icerik_yukle(self):
        """Pencere göründükten sonra video katmanını yükle"""
        self._video_olustur()

    def _smb_yolunu_cevir(self, smb_url):
        """smb:// URL'sini GVFS yerel yoluna dönüştür"""
        # smb://192.168.1.123/Okul -> /run/user/<uid>/gvfs/smb-share:server=192.168.1.123,share=okul
        # smb://192.168.1.123/Okul/alt/klasor -> .../smb-share:server=...,share=okul/alt/klasor
        yol = smb_url[6:]  # "smb://" kısmını kaldır
        parcalar = yol.split('/', 2)  # ['192.168.1.123', 'Okul', 'alt/klasor']
        sunucu = parcalar[0]
        paylasim = parcalar[1].lower() if len(parcalar) > 1 else ''
        alt_yol = parcalar[2] if len(parcalar) > 2 else ''
        uid = os.getuid()
        gvfs_yolu = f"/run/user/{uid}/gvfs/smb-share:server={sunucu},share={paylasim}"
        if alt_yol:
            gvfs_yolu = os.path.join(gvfs_yolu, alt_yol)
        # Mount değilse gio ile mount etmeyi dene
        if not os.path.isdir(gvfs_yolu):
            try:
                subprocess.run(
                    ["gio", "mount", smb_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            except Exception:
                pass
        return gvfs_yolu

    def _logo_yenile(self):
        """Ayarlar kaydedildikten sonra logoyu yeniden yükle"""
        logo_pixmap = QPixmap(os.path.join(BETIK_DIZINI, "resim", "logo.png"))
        if not logo_pixmap.isNull():
            self._logo_etiketi.setPixmap(logo_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _webview_url_yenile(self):
        """Ayarlar kaydedildikten sonra web görünüm URL'sini güncelle"""
        db_url = self._vt.url_al(self._kurumkodu)
        yeni_url = db_url if db_url else "https://kulumtal.com/php/"
        mevcut_url = self.web_gorunum.url().toString()
        if mevcut_url != yeni_url:
            self.web_gorunum.setUrl(QUrl(yeni_url))

    def _video_yenile(self):
        """Mevcut video katmanını temizle ve yeniden oluştur"""
        if hasattr(self, '_vlc_list_player') and self._vlc_list_player:
            self._vlc_list_player.stop()
            self._vlc_list_player = None
        if hasattr(self, '_vlc_player') and self._vlc_player:
            self._vlc_player = None
        if hasattr(self, '_vlc_instance') and self._vlc_instance:
            self._vlc_instance.release()
            self._vlc_instance = None
        if hasattr(self, '_video_frame') and self._video_frame:
            self._video_alani_yerlesim.removeWidget(self._video_frame)
            self._video_frame.deleteLater()
            self._video_frame = None
        self._video_katmani = None
        self._video_gizli = False
        self._video_toggle_btn.hide()
        self._icerik_yigini.setCurrentWidget(self._web_alani)
        self._video_olustur()

    def _video_olustur(self):
        """Video katmanını arka planda hazırla (UI donmasını önler)"""
        ayarlar = QSettings("KulumTal", "Tahta")
        video_klasoru = ayarlar.value("video_klasoru", "")
        if not video_klasoru:
            return

        def _arka_plan_kontrol():
            klasor = video_klasoru
            if klasor.lower().startswith("smb://"):
                klasor = self._smb_yolunu_cevir(klasor)
            try:
                if not os.path.isdir(klasor):
                    return
                video_uzantilari = ('.mp4', '.webm', '.ogg', '.mkv', '.avi', '.mov')
                dosyalar = sorted(
                    f for f in os.listdir(klasor)
                    if os.path.splitext(f)[1].lower() in video_uzantilari
                )
                if dosyalar:
                    self._video_hazir.emit(klasor, dosyalar)
            except (OSError, PermissionError):
                pass

        t = threading.Thread(target=_arka_plan_kontrol, daemon=True)
        t.start()

    def _video_katman_olustur(self, video_klasoru, video_dosyalari):
        """Video katmanını UI thread'inde oluştur (VLC tabanlı)"""
        self._video_dosyalari = video_dosyalari
        self._video_klasoru = video_klasoru

        QApplication.processEvents()

        # VLC çıktı frame'i
        self._video_frame = QFrame()
        self._video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video_frame.setMinimumSize(1, 1)
        self._video_frame.setStyleSheet("background-color: black;")
        self._video_alani_yerlesim.addWidget(self._video_frame)
        self._video_alani_yerlesim.setContentsMargins(0, 0, 0, 0)

        # VLC instance ve media list player
        self._vlc_instance = vlc.Instance('--no-xlib', '--quiet', '--no-video-title-show')
        self._vlc_list_player = self._vlc_instance.media_list_player_new()
        self._vlc_player = self._vlc_list_player.get_media_player()

        # Media list oluştur
        media_list = self._vlc_instance.media_list_new()
        for dosya in video_dosyalari:
            tam_yol = os.path.join(video_klasoru, dosya)
            media_list.add_media(self._vlc_instance.media_new(tam_yol))
        self._vlc_list_player.set_media_list(media_list)
        self._vlc_list_player.set_playback_mode(vlc.PlaybackMode.loop)

        self._video_katmani = True
        self._video_gizli = False
        self._icerik_yigini.setCurrentWidget(self._video_alani)

        QApplication.processEvents()
        self._video_boyut_ayarla()
        QTimer.singleShot(300, self._video_boyut_ayarla)
        QTimer.singleShot(1000, self._video_boyut_ayarla)
        QTimer.singleShot(3000, self._video_boyut_ayarla)
        # VLC'ye pencere kimliğini ver ve oynat
        QTimer.singleShot(500, self._vlc_oynat)

        self._video_toggle_btn.show()

    def _vlc_oynat(self):
        """VLC'ye X11 pencere kimliğini ver ve oynatmayı başlat"""
        if not hasattr(self, '_vlc_player') or not self._vlc_player:
            return
        if not hasattr(self, '_video_frame') or not self._video_frame:
            return
        win_id = int(self._video_frame.winId())
        self._vlc_player.set_xwindow(win_id)
        self._vlc_list_player.play()
        # VLC PulseAudio sink-input'unu oluşturduktan sonra sesini güvenceye al
        QTimer.singleShot(500, self._vlc_unmute_guvence)
        QTimer.singleShot(1500, self._vlc_unmute_guvence)

    def _video_boyut_ayarla(self):
        """Video frame'ini üst konteyner boyutuna sığdır"""
        if not hasattr(self, '_video_frame') or not self._video_frame:
            return
        ekran = QApplication.primaryScreen()
        if ekran:
            geometri = ekran.geometry()
            if self.geometry() != geometri:
                self.setGeometry(geometri)
                self.showFullScreen()
        QApplication.processEvents()
        alan_boyut = self._video_alani.size()
        if alan_boyut.width() > 100 and alan_boyut.height() > 100:
            self._video_frame.resize(alan_boyut)
        self._video_frame.updateGeometry()
        self._video_alani.updateGeometry()
        # VLC'ye pencere kimliğini güncelle
        if hasattr(self, '_vlc_player') and self._vlc_player:
            win_id = int(self._video_frame.winId())
            self._vlc_player.set_xwindow(win_id)

    def _video_gizle_goster(self):
        """Video katmanını gizle veya göster"""
        if self._video_katmani is None:
            return

        if self._video_gizli:
            self._icerik_yigini.setCurrentWidget(self._video_alani)
            if hasattr(self, '_vlc_list_player') and self._vlc_list_player:
                # stop() edilmiş olabilir — önce xwindow'u yenile, sonra oynat
                if hasattr(self, '_vlc_player') and self._vlc_player and hasattr(self, '_video_frame') and self._video_frame:
                    self._vlc_player.set_xwindow(int(self._video_frame.winId()))
                self._vlc_list_player.play()
                QTimer.singleShot(300, self._vlc_unmute_guvence)
            self._video_toggle_btn.setIcon(qta.icon('fa5s.eye-slash', color='#95a5a6'))
            self._video_toggle_btn.setToolTip("Videoyu Gizle")
            self._video_gizli = False
        else:
            if hasattr(self, '_vlc_list_player') and self._vlc_list_player:
                self._vlc_list_player.pause()
            self._icerik_yigini.setCurrentWidget(self._web_alani)
            self._video_toggle_btn.setIcon(qta.icon('fa5s.eye', color='#95a5a6'))
            self._video_toggle_btn.setToolTip("Videoyu Göster")
            self._video_gizli = True

    def _vlc_unmute_guvence(self):
        """Kilit uygulamasının kendi VLC player'ını kesinlikle unmute/sesli yap"""
        try:
            if hasattr(self, '_vlc_player') and self._vlc_player:
                self._vlc_player.audio_set_mute(False)
            if hasattr(self, '_vlc_list_player') and self._vlc_list_player:
                p = self._vlc_list_player.get_media_player()
                if p:
                    p.audio_set_mute(False)
        except Exception:
            pass

    def _tarayici_sustur(self):
        """Ses/video oynatan tarayıcıları kapat (medya yoksa dokunma); harici medya oynatıcıları kapat"""
        kendi_pid = str(os.getpid())
        kapatilacak_binary_ler = set()
        # PulseAudio'dan aktif ses akışı olan tarayıcı binary isimlerini bul
        try:
            cikti = subprocess.check_output(
                ["pactl", "list", "sink-inputs"], text=True, stderr=subprocess.DEVNULL
            )
            mevcut_pid = None
            mevcut_binary = None
            for satir in cikti.splitlines():
                s = satir.strip()
                m = _RE_SINK_IDX.match(s)
                if m:
                    # Önceki akışı işle
                    if mevcut_pid and mevcut_pid != kendi_pid and mevcut_binary in _TARAYICI_BINARIES:
                        kapatilacak_binary_ler.add(mevcut_binary)
                    mevcut_pid = None
                    mevcut_binary = None
                elif "application.process.id" in s:
                    m2 = re.search(r'"(\d+)"', s)
                    if m2:
                        mevcut_pid = m2.group(1)
                elif "application.process.binary" in s:
                    m2 = re.search(r'"([^"]+)"', s)
                    if m2:
                        mevcut_binary = os.path.basename(m2.group(1)).lower()
            # Son akış
            if mevcut_pid and mevcut_pid != kendi_pid and mevcut_binary in _TARAYICI_BINARIES:
                kapatilacak_binary_ler.add(mevcut_binary)
        except Exception:
            pass
        # Ses/video oynatan tarayıcıları killall ile kapat (tüm alt process'ler dahil)
        for binary in kapatilacak_binary_ler:
            try:
                subprocess.Popen(
                    ["killall", binary],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass
        # Harici medya oynatıcıları tamamen kapat
        for oynatici in _MEDYA_OYNATICILARI:
            try:
                subprocess.Popen(
                    ["killall", oynatici],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def sistemi_kilitle(self):
        """Sistemi kilitle: klavyeyi yakala"""
        self._tarayici_sustur()
        # Kendi VLC'mizin kesinlikle sesli kaldığından emin ol
        self._vlc_unmute_guvence()
        # Ekran geometrisini yeniden al (boot sırasında değişmiş olabilir)
        ekran = QApplication.primaryScreen()
        if ekran:
            geometri = ekran.geometry()
            self.setGeometry(geometri)
        self.showFullScreen()
        QApplication.processEvents()
        QTimer.singleShot(200, self._icerik_yukle)
        QTimer.singleShot(500, self._girisleri_yakala)

        self._odak_zamanlayici.start(1000)

    def _girisleri_yakala(self):
        """Klavyeyi yakala"""
        if not self.isVisible():
            return
        self.grabKeyboard()
        try:
            wid = int(self.winId())
            subprocess.Popen(
                ["xdotool", "windowfocus", str(wid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def _ustte_kal(self):
        """Pencerenin her zaman en üstte ve odakta olmasını sağla"""
        if self._kilit_acma_istendi or not self.isVisible():
            return
        self.raise_()
        self.activateWindow()

    def kilidi_ac(self, sure_dakika=5):
        """Kilidi geçici olarak aç, süre sonunda tekrar kilitle"""
        self._kilit_acma_istendi = True
        self._odak_zamanlayici.stop()
        self._challenge_zamanlayici.stop()
        self._saat_zamanlayici.stop()
        self._kapanma_zamanlayici.stop()
        self.releaseKeyboard()

        # Veritabanını güncelle (açık olarak işaretle)
        self._vt.durum_guncelle(self._kurumkodu, 1)
        self._son_db_durum = 1

        # Sunucuya bildir
        self._online.durum_bildir(0, self._son_ses_durum if hasattr(self, '_son_ses_durum') else 1)
        try:
            self._online.kapanma_bildir(-1)
        except Exception:
            pass

        # Videoyu duraklat veya durdur
        if self._video_katmani and hasattr(self, '_vlc_list_player') and self._vlc_list_player:
            if self._video_gizli:
                self._vlc_list_player.stop()
            else:
                self._vlc_list_player.pause()

        self.hide()

        # Sol alt köşede "Hemen Kilitle" penceresi göster
        self._hemen_kilitle_goster(sure_dakika)

        # Süre sonunda tekrar kilitle
        self._tekrar_kilitle_zamanlayici = QTimer(self)
        self._tekrar_kilitle_zamanlayici.setSingleShot(True)
        self._tekrar_kilitle_zamanlayici.timeout.connect(self._tekrar_kilitle)
        self._tekrar_kilitle_zamanlayici.start(sure_dakika * 60 * 1000)

        # Kilit geri sayımını sunucuya bildir
        try:
            self._online.kilit_bildir(sure_dakika * 60)
        except Exception:
            pass

    def _hemen_kilitle_goster(self, sure_dakika):
        """System tray icon + kontrol penceresi göster"""
        self._kalan_saniye = sure_dakika * 60
        self._toplam_saniye = sure_dakika * 60

        # --- Kontrol penceresi ---
        self._kilitle_pencere = QWidget()
        self._kilitle_pencere.setWindowTitle("Tahta Kilit")
        self._kilitle_pencere.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self._kilitle_pencere.setAttribute(Qt.WA_TranslucentBackground)
        self._kilitle_pencere.setFixedSize(280, 80)

        ekran = QApplication.primaryScreen().geometry()
        self._kilitle_pencere.move(ekran.width() - 310, ekran.height() - 170)

        ana_yerlesim = QVBoxLayout(self._kilitle_pencere)
        ana_yerlesim.setContentsMargins(0, 0, 0, 0)

        cerceve = QFrame()
        cerceve.setStyleSheet("""
            QFrame {
                background-color: rgba(32, 32, 32, 200);
                border-radius: 10px;
            }
        """)
        cerceve_yerlesim = QVBoxLayout(cerceve)
        cerceve_yerlesim.setContentsMargins(14, 10, 14, 10)
        cerceve_yerlesim.setSpacing(6)

        # Üst satır: süre + kilitle butonu
        ust_satir = QHBoxLayout()
        ust_satir.setSpacing(8)

        self._sure_etiketi = QLabel(self._kalan_sure_metni())
        self._sure_etiketi.setFont(QFont("Noto Sans", 13))
        self._sure_etiketi.setStyleSheet("color: #ccc; background: transparent;")
        ust_satir.addWidget(self._sure_etiketi, 1)

        kilitle_btn = QPushButton("Kilitle")
        kilitle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        kilitle_btn.setFont(QFont("Noto Sans", 12))
        kilitle_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                color: #ddd; border: none;
                border-radius: 8px; padding: 8px 18px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.2); }
        """)
        kilitle_btn.clicked.connect(self._hemen_kilitle)
        ust_satir.addWidget(kilitle_btn)

        cerceve_yerlesim.addLayout(ust_satir)

        # İlerleme çubuğu
        self._sure_ilerleme = QProgressBar()
        self._sure_ilerleme.setRange(0, self._toplam_saniye)
        self._sure_ilerleme.setValue(self._kalan_saniye)
        self._sure_ilerleme.setTextVisible(False)
        self._sure_ilerleme.setFixedHeight(4)
        self._sure_ilerleme.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.06);
                border: none; border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: rgba(255, 255, 255, 0.3);
                border-radius: 1px;
            }
        """)
        cerceve_yerlesim.addWidget(self._sure_ilerleme)

        # Pencereye tıklanınca gizle (kilitle butonu hariç)
        cerceve.mousePressEvent = lambda e: self._kilitle_pencere.hide()

        ana_yerlesim.addWidget(cerceve)

        # --- System tray icon ---
        tray_ikon_yolu = os.path.join(BETIK_DIZINI, "resim", "tahta-kilit-icon-symbolic.svg")
        ikon = QIcon(tray_ikon_yolu)

        self._tray_icon = QSystemTrayIcon(ikon, self)
        self._tray_icon.setToolTip(self._kalan_sure_metni())
        self._tray_icon.activated.connect(self._tray_tiklandi)
        self._tray_icon.show()
        self._tray_icon.showMessage(
            "Tahta Kilit",
            f"Kilit {sure_dakika} dakika açık kalacak.\nPanelden kontrol edebilirsiniz.",
            QSystemTrayIcon.Information, 3000
        )

        # Pencereyi göster
        self._kilitle_pencere.show()
        # 15 saniye sonra otomatik gizle
        QTimer.singleShot(15000, self._kilitle_penceresi_otomatik_gizle)

        # Geri sayım zamanlayıcısı
        self._geri_sayim_zamanlayici = QTimer(self)
        self._geri_sayim_zamanlayici.timeout.connect(self._geri_sayim_guncelle)
        self._geri_sayim_zamanlayici.start(1000)

    def _kilitle_penceresi_otomatik_gizle(self):
        """15 saniye sonra köşe penceresini otomatik gizle"""
        if hasattr(self, '_kilitle_pencere') and self._kilitle_pencere and self._kilitle_pencere.isVisible():
            self._kilitle_pencere.hide()

    def _tray_tiklandi(self, reason):
        """Tray icon tıklandığında pencereyi göster/gizle"""
        if reason == QSystemTrayIcon.Trigger:
            if hasattr(self, '_kilitle_pencere') and self._kilitle_pencere:
                if self._kilitle_pencere.isVisible():
                    self._kilitle_pencere.hide()
                else:
                    self._kilitle_pencere.show()
                    self._kilitle_pencere.raise_()
                    self._kilitle_pencere.activateWindow()

    def _kalan_sure_metni(self):
        dk = self._kalan_saniye // 60
        sn = self._kalan_saniye % 60
        return f"Kalan: {dk:02d}:{sn:02d}"

    def _geri_sayim_guncelle(self):
        self._kalan_saniye -= 1
        if self._kalan_saniye <= 0:
            self._geri_sayim_zamanlayici.stop()
            try:
                self._online.kilit_bildir(-1)
            except Exception:
                pass
            return
        metin = self._kalan_sure_metni()
        self._sure_etiketi.setText(metin)

        # İlerleme çubuğu güncelle
        if hasattr(self, '_sure_ilerleme') and self._sure_ilerleme:
            self._sure_ilerleme.setValue(self._kalan_saniye)
            # Son 60 saniyede hafif vurgula
            if self._kalan_saniye <= 60:
                self._sure_etiketi.setStyleSheet("color: #e88; background: transparent;")
                self._sure_ilerleme.setStyleSheet("""
                    QProgressBar {
                        background: rgba(255, 255, 255, 0.06);
                        border: none; border-radius: 1px;
                    }
                    QProgressBar::chunk {
                        background-color: rgba(230, 100, 100, 0.5);
                        border-radius: 1px;
                    }
                """)

        if hasattr(self, '_tray_icon') and self._tray_icon:
            self._tray_icon.setToolTip(metin)
        # Her 10 saniyede bir veya son 60 saniyede her saniye sunucuya bildir
        if self._kalan_saniye % 10 == 0 or self._kalan_saniye <= 60:
            try:
                self._online.kilit_bildir(self._kalan_saniye)
            except Exception:
                pass

    def _hemen_kilitle(self):
        """Hemen kilitle"""
        if hasattr(self, '_geri_sayim_zamanlayici'):
            self._geri_sayim_zamanlayici.stop()
        if hasattr(self, '_tekrar_kilitle_zamanlayici'):
            self._tekrar_kilitle_zamanlayici.stop()
        if hasattr(self, '_kilitle_pencere') and self._kilitle_pencere:
            self._kilitle_pencere.close()
            self._kilitle_pencere = None
        if hasattr(self, '_tray_icon') and self._tray_icon:
            self._tray_icon.hide()
            self._tray_icon = None
        self._tekrar_kilitle()

    def _tekrar_kilitle(self):
        """Süre dolduğunda ekranı tekrar kilitle"""
        if hasattr(self, '_geri_sayim_zamanlayici'):
            self._geri_sayim_zamanlayici.stop()
        if hasattr(self, '_kilitle_pencere') and self._kilitle_pencere:
            self._kilitle_pencere.close()
            self._kilitle_pencere = None
        if hasattr(self, '_tray_icon') and self._tray_icon:
            self._tray_icon.hide()
            self._tray_icon = None

        self._tarayici_sustur()
        # Kendi VLC'mizin kesinlikle sesli kaldığından emin ol
        self._vlc_unmute_guvence()

        # Veritabanını güncelle (kilitli olarak işaretle)
        self._vt.durum_guncelle(self._kurumkodu, 0)
        self._son_db_durum = 0

        # Sunucuya bildir
        self._online.durum_bildir(1, self._son_ses_durum if hasattr(self, '_son_ses_durum') else 1)
        try:
            self._online.kilit_bildir(-1)
        except Exception:
            pass

        self._kilit_acma_istendi = False
        self._challenge_guncelle()
        self._saat_guncelle()
        self._saat_zamanlayici.start(1000)
        self._challenge_zamanlayici.start(50)
        self.showFullScreen()

        # Videoyu devam ettir
        if self._video_katmani and hasattr(self, '_vlc_list_player') and self._vlc_list_player and not self._video_gizli:
            self._vlc_list_player.play()
        # VLC sesini güvenceye al (susturma sonrası)
        QTimer.singleShot(300, self._vlc_unmute_guvence)

        QTimer.singleShot(500, self._girisleri_yakala)
        self._odak_zamanlayici.start(1000)
        self._kapanma_kalan = self._kapanma_suresi
        self._kapanma_bar.oran_ayarla(1.0)
        self._kapanma_zamanlayici.start(1000)
        try:
            self._online.kapanma_bildir(self._kapanma_suresi)
        except Exception:
            pass

    def keyPressEvent(self, event):
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()

    def closeEvent(self, event):
        if self._kilit_acma_istendi:
            self.releaseKeyboard()
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                self.showFullScreen()
        super().changeEvent(event)

    def focusOutEvent(self, event):
        if not self._kilit_acma_istendi:
            QTimer.singleShot(100, self._girisleri_yakala)
        super().focusOutEvent(event)
