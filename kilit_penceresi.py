# -*- coding: utf-8 -*-
"""Ana kilit ekranı penceresi"""

import os
import sys
import glob
import json
import re
import time
import subprocess
from datetime import datetime
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
                             QProgressBar, QStackedWidget, QToolButton,
                             QScrollArea)
from PyQt5.QtCore import Qt, QTimer, QEvent, QUrl, QTime, QDate, QLocale, QSize, QSettings, pyqtSignal, QFileSystemWatcher
from PyQt5.QtGui import QFont, QCursor, QPixmap, QPainter, QColor, QBrush, QPainterPath, QIcon, QRegion, QPalette, QFontDatabase, QPen
import qtawesome as qta
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings, QWebEngineProfile
import vlc
import qrcode

from sabitler import BETIK_DIZINI, YENILEME_ARALIGI_SANIYE, VARSAYILAN_KURUM_KODU, OFFLINE_GECIKME_SANIYE, BASTANGIC_BEKLEME_SANIYE
from servisler import KodUretici, DogrulamaServisi
from dogrulama_penceresi import KodDogrulamaPenceresi
from veritabani import VeritabaniYoneticisi
from online_istemci import OnlineIstemci
from smb_bagla import SmbBaglamaPenceresi

def _fontlari_yukle():
    """Fontları yükle (QApplication oluştuktan sonra çağrılmalı)"""
    for dosya in ["Merriweather-Bold.ttf", "Merriweather-Regular.ttf",
                  "Exo2-Regular.ttf", "Exo2-SemiBold.ttf", "Exo2-Bold.ttf"]:
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


class PastaGeriSayim(QWidget):
    """Yuvarlak pasta şeklinde azalan geri sayım widget'ı"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._oran = 1.0  # 1.0 = tam, 0.0 = bitti

    def oran_ayarla(self, oran):
        self._oran = max(0.0, min(1.0, oran))
        self.update()

    def _renk_hesapla(self):
        if self._oran > 0.5:
            return QColor("#28a745")  # yeşil
        elif self._oran > 0.2:
            return QColor("#e6930a")  # turuncu
        else:
            return QColor("#e74c3c")  # kırmızı

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        x = (self.width() - s) / 2
        y = (self.height() - s) / 2
        m = 1  # kenar boşluğu
        r = s - 2 * m

        # Arka plan daire (gri)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ddd")))
        p.drawEllipse(int(x + m), int(y + m), int(r), int(r))

        # Dolu pasta dilimi
        renk = self._renk_hesapla()
        p.setBrush(QBrush(renk))
        aci = int(self._oran * 360 * 16)  # Qt 1/16 derece kullanır
        if aci > 0:
            p.drawPie(int(x + m), int(y + m), int(r), int(r), 90 * 16, -aci)

        p.end()


class _AyarlarKartWidget(QWidget):
    """Beyaz arka planlı, kenarlıklı köşesi yuvarlatılmış kart (CSS yok)."""
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#E2E8F0"), 1))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        p.end()


class _DokunmatikMenu(QWidget):
    """QMenu yerine touch-safe bağlam menüsü.
    QMenu dahili olarak Qt.Popup bayrağı kullanır ve dokunmatik
    girişi grab’ler; bu widget Qt.Tool kullandığı için grab yapmaz."""
    _aktif = None

    def __init__(self, hedef, global_pos):
        if _DokunmatikMenu._aktif is not None:
            try:
                _DokunmatikMenu._aktif.close()
            except RuntimeError:
                pass
        # hedefin üst penceresi parent olmalı ki menü onun önünde çıksın
        ust_pencere = hedef.window()
        super().__init__(ust_pencere)
        _DokunmatikMenu._aktif = self
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(
            "background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px;"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)

        secili = bool(hedef.selectedText())
        if not hedef.isReadOnly():
            self._btn(lay, "Kes", hedef.cut, secili)
        self._btn(lay, "Kopyala", hedef.copy, secili)
        if not hedef.isReadOnly():
            self._btn(lay, "Yapıştır", hedef.paste, True)
        self._btn(lay, "Tümünü Seç", hedef.selectAll, True)

        self.adjustSize()
        self.move(global_pos.x() - self.width() // 2,
                  global_pos.y() - self.height() - 8)
        self.show()
        self.raise_()
        QApplication.instance().installEventFilter(self)

    def _btn(self, lay, metin, slot, etkin):
        b = QPushButton(metin)
        b.setEnabled(etkin)
        b.setFocusPolicy(Qt.NoFocus)
        b.setStyleSheet(
            "QPushButton{background:transparent;border:none;padding:10px 16px;"
            "font-size:13px;color:#1E293B;border-radius:4px}"
            "QPushButton:pressed{background:#E2E8F0}"
            "QPushButton:disabled{color:#94A3B8}"
        )
        b.clicked.connect(slot)
        b.clicked.connect(self.close)
        lay.addWidget(b)

    # -- dışına tıklayınca kapat --
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPos()):
                self.close()
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        _DokunmatikMenu._aktif = None
        super().closeEvent(event)


class AyarlarPenceresi(QDialog):
    """Kilit ekranı ayarlar penceresi"""

    def __init__(self, parent=None, vt_yoneticisi=None, kurumkodu=None):
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setFixedSize(740, 760)

        self._vt = vt_yoneticisi or VeritabaniYoneticisi()
        self._kurumkodu = kurumkodu or VARSAYILAN_KURUM_KODU

        self.setStyleSheet("background-color: #F0F2F5;")

        self._arayuz_olustur()
        self._verileri_yukle()

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    @staticmethod
    def _etiket(metin):
        lbl = QLabel(metin)
        lbl.setFont(QFont("Sans", 11))
        lbl.setStyleSheet("color: #475569; font-weight: 600; background: transparent;")
        lbl.setFixedWidth(130)
        lbl.setFixedHeight(36)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        return lbl

    def _satir_olustur(self, etiket_metni, widget):
        konteyner = QWidget()
        konteyner.setFixedHeight(44)
        satir = QHBoxLayout(konteyner)
        satir.setContentsMargins(0, 0, 0, 0)
        satir.setSpacing(12)
        satir.addWidget(self._etiket(etiket_metni), 0, Qt.AlignVCenter)
        satir.addWidget(widget, 1, Qt.AlignVCenter)
        return konteyner

    @staticmethod
    def _girdi(placeholder="", readonly=False):
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        w.setFixedHeight(36)
        w.setReadOnly(readonly)
        w.setFont(QFont("Sans", 11))
        # Dokunmatik için özel menü: QTimer ile erteleyerek touch grab sorununu önler,
        # kopyala/yapıştır/seç işlemlerine dokunmatik ekrandan erişim sağlar.
        w.setContextMenuPolicy(Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(
            lambda pos, wgt=w: _DokunmatikMenu(wgt, wgt.mapToGlobal(pos))
        )
        if readonly:
            w.setStyleSheet(
                "background: #E8ECF0; border: 1px solid #CBD5E1;"
                "border-radius: 6px; padding: 0 10px; color: #64748B;")
        else:
            w.setStyleSheet(
                "background: #FFFFFF; border: 1px solid #CBD5E1;"
                "border-radius: 6px; padding: 0 10px; color: #1E293B;")
        return w

    def _kart_olustur(self, baslik, ikon=""):
        kart = _AyarlarKartWidget()
        ic = QVBoxLayout(kart)
        ic.setContentsMargins(18, 14, 18, 14)
        ic.setSpacing(4)

        lbl = QLabel(f"{ikon}  {baslik}" if ikon else baslik)
        lbl.setFont(QFont("Sans", 10, QFont.Bold))
        lbl.setStyleSheet("color: #3B82F6; background: transparent;")
        lbl.setFixedHeight(24)
        ic.addWidget(lbl)

        return kart, ic

    def _dosya_sec_satiri(self, etiket_metni, placeholder, slot):
        girdi = self._girdi(placeholder, readonly=True)
        btn = QPushButton("Seç…")
        btn.setFixedSize(70, 36)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet(
            "background: #3B82F6; color: #FFFFFF; border: none;"
            "border-radius: 6px; font-size: 12px; font-weight: bold;")
        btn.clicked.connect(slot)

        konteyner = QWidget()
        konteyner.setFixedHeight(44)
        satir = QHBoxLayout(konteyner)
        satir.setContentsMargins(0, 0, 0, 0)
        satir.setSpacing(12)
        satir.addWidget(self._etiket(etiket_metni), 0, Qt.AlignVCenter)
        satir.addWidget(girdi, 1, Qt.AlignVCenter)
        satir.addWidget(btn, 0, Qt.AlignVCenter)
        return konteyner, girdi

    # ── Ana Arayüz ────────────────────────────────────────────────────────────

    def _arayuz_olustur(self):
        ana = QVBoxLayout(self)
        ana.setContentsMargins(0, 0, 0, 0)
        ana.setSpacing(0)

        # ── Başlık Bandı ─────────────────────────────────────────────────────
        bant = QFrame()
        bant.setFixedHeight(64)
        bant.setStyleSheet("background-color: #1E40AF;")
        bant_ic = QHBoxLayout(bant)
        bant_ic.setContentsMargins(24, 0, 24, 0)

        baslik_lbl = QLabel("⚙  Ayarlar")
        baslik_lbl.setFont(QFont("Noto Sans", 15, QFont.Bold))
        baslik_lbl.setStyleSheet("color: #FFFFFF;")

        alt_lbl = QLabel("Cihaz, kurum ve bağlantı bilgilerini düzenleyin")
        alt_lbl.setFont(QFont("Noto Sans", 9))
        alt_lbl.setStyleSheet("color: #93C5FD;")

        yazi = QVBoxLayout()
        yazi.setSpacing(2)
        yazi.addWidget(baslik_lbl)
        yazi.addWidget(alt_lbl)
        bant_ic.addLayout(yazi)
        bant_ic.addStretch()
        ana.addWidget(bant)

        # ── İçerik Alanı ─────────────────────────────────────────────────────
        icerik_ic = QVBoxLayout()
        icerik_ic.setContentsMargins(20, 16, 20, 16)
        icerik_ic.setSpacing(12)

        # Kart 1: Cihaz Kimliği
        kart1, k1 = self._kart_olustur("Cihaz Kimliği", "🖥")
        self._tahta_id_girisi = self._girdi(readonly=True)
        # Tahta ID satırı + kopyala butonu
        tahta_id_konteyner = QWidget()
        tahta_id_konteyner.setFixedHeight(44)
        tahta_id_satir = QHBoxLayout(tahta_id_konteyner)
        tahta_id_satir.setContentsMargins(0, 0, 0, 0)
        tahta_id_satir.setSpacing(12)
        tahta_id_satir.addWidget(self._etiket("Tahta ID"), 0, Qt.AlignVCenter)
        tahta_id_satir.addWidget(self._tahta_id_girisi, 1, Qt.AlignVCenter)
        kopyala_btn = QPushButton()
        kopyala_btn.setIcon(qta.icon("fa5s.copy", color="#FFFFFF"))
        kopyala_btn.setFixedSize(36, 36)
        kopyala_btn.setCursor(QCursor(Qt.PointingHandCursor))
        kopyala_btn.setToolTip("Tahta ID kopyala")
        kopyala_btn.setStyleSheet(
            "QPushButton{background:#3B82F6;border:none;border-radius:6px}"
            "QPushButton:pressed{background:#2563EB}")
        kopyala_btn.clicked.connect(self._tahta_id_kopyala)
        tahta_id_satir.addWidget(kopyala_btn, 0, Qt.AlignVCenter)
        k1.addWidget(tahta_id_konteyner)
        icerik_ic.addWidget(kart1)

        # Kart 2: Kurum Bilgileri
        kart2, k2 = self._kart_olustur("Kurum Bilgileri", "🏫")
        self._kurum_girisi = self._girdi("Örn: 0001")
        k2.addWidget(self._satir_olustur("Kurum Kodu", self._kurum_girisi))
        self._kurum_adi_girisi = self._girdi("Örn: Atatürk İlkokulu")
        k2.addWidget(self._satir_olustur("Kurum Adı", self._kurum_adi_girisi))
        self._sinif_girisi = self._girdi("Örn: 11E Sınıfı")
        k2.addWidget(self._satir_olustur("Tahta Adı", self._sinif_girisi))
        icerik_ic.addWidget(kart2)

        # Kart 3: Bağlantı Ayarları
        kart3, k3 = self._kart_olustur("Bağlantı Ayarları", "🔐")
        self._anahtar_girisi = self._girdi("Gizli doğrulama anahtarı")
        self._anahtar_girisi.setEchoMode(QLineEdit.Password)
        k3.addWidget(self._satir_olustur("Gizli Anahtar", self._anahtar_girisi))
        self._url_girisi = self._girdi("Örn: https://kulumtal.com/php/")
        k3.addWidget(self._satir_olustur("WebView URL", self._url_girisi))
        icerik_ic.addWidget(kart3)

        # Kart 4: Medya & Logo
        kart4, k4 = self._kart_olustur("Medya & Logo", "🖼")
        logo_satir, self._logo_yolu_girisi = self._dosya_sec_satiri(
            "Kurum Logosu", "500x500 px PNG seçin", self._logo_sec)
        k4.addWidget(logo_satir)
        video_satir, self._video_girisi = self._dosya_sec_satiri(
            "Video Klasörü", "Örn: /home/kullanici/Videolar", self._klasor_sec)
        # Video satırının yanına SMB butonu ekle
        smb_btn = QPushButton()
        smb_btn.setIcon(qta.icon("fa5s.network-wired", color="#FFFFFF"))
        smb_btn.setFixedSize(36, 36)
        smb_btn.setCursor(QCursor(Qt.PointingHandCursor))
        smb_btn.setToolTip("Ağ Klasörü Bağla (SMB)")
        smb_btn.setStyleSheet(
            "QPushButton{background:#F97316;border:none;border-radius:6px}"
            "QPushButton:pressed{background:#EA580C}")
        smb_btn.clicked.connect(self._smb_bagla)
        video_satir.layout().addWidget(smb_btn, 0, Qt.AlignVCenter)
        k4.addWidget(video_satir)
        icerik_ic.addWidget(kart4)

        icerik_ic.addStretch()

        # ── Alt Buton Satırı ─────────────────────────────────────────────────
        buton_satir = QHBoxLayout()
        buton_satir.setSpacing(10)

        iptal_btn = QPushButton("İptal")
        iptal_btn.setFixedSize(110, 40)
        iptal_btn.setCursor(QCursor(Qt.PointingHandCursor))
        iptal_btn.setStyleSheet("""
            QPushButton {
                background-color: #E2E8F0; color: #1E293B; border: none;
                border-radius: 7px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #CBD5E1; }
        """)
        iptal_btn.clicked.connect(self.reject)

        kaydet_btn = QPushButton("Kaydet")
        kaydet_btn.setFixedSize(150, 40)
        kaydet_btn.setCursor(QCursor(Qt.PointingHandCursor))
        kaydet_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: #FFFFFF; border: none;
                border-radius: 7px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)
        kaydet_btn.clicked.connect(self._kaydet)

        sifirla_btn = QPushButton()
        sifirla_btn.setIcon(qta.icon("fa5s.trash-alt", color="#FFFFFF"))
        sifirla_btn.setText(" Sıfırla")
        sifirla_btn.setFixedSize(130, 40)
        sifirla_btn.setCursor(QCursor(Qt.PointingHandCursor))
        sifirla_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444; color: #FFFFFF; border: none;
                border-radius: 7px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #DC2626; }
        """)
        sifirla_btn.clicked.connect(self._sifirla)

        buton_satir.addWidget(sifirla_btn)
        buton_satir.addStretch()
        buton_satir.addWidget(iptal_btn)
        buton_satir.addWidget(kaydet_btn)
        icerik_ic.addLayout(buton_satir)

        ana.addLayout(icerik_ic)

    def _verileri_yukle(self):
        ayarlar = QSettings("KulumTal", "Tahta")
        self._video_girisi.setText(ayarlar.value("video_klasoru", ""))

        kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        if kayit:
            self._tahta_id_girisi.setText(str(kayit.get("id", "")))
            self._kurum_girisi.setText(kayit.get("kurumkodu", ""))
            self._kurum_adi_girisi.setText(kayit.get("kurum_adi", ""))
            self._sinif_girisi.setText(kayit.get("adi", ""))
            self._anahtar_girisi.setText(kayit.get("anahtar", ""))
            self._url_girisi.setText(kayit.get("url", ""))

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

    def _tahta_id_kopyala(self):
        """Tahta ID değerini panoya kopyala"""
        metin = self._tahta_id_girisi.text().strip()
        if metin:
            QApplication.clipboard().setText(metin)

    def _smb_bagla(self):
        """SMB ağ klasörü bağlama penceresini aç"""
        pencere = SmbBaglamaPenceresi(self)
        pencere.exec_()

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

    def _sifirla(self):
        """Veritabanını sıfırla ve kurulum penceresini başlat"""
        from PyQt5.QtWidgets import QMessageBox
        cevap = QMessageBox.question(
            self, "Sıfırlama Onayı",
            "Tüm ayarlar ve veritabanı sıfırlanacak.\n"
            "Uygulama yeniden başlatılacak ve kurulum penceresi açılacaktır.\n\n"
            "Devam etmek istiyor musunuz?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if cevap != QMessageBox.Yes:
            return
        # Veritabanı dosyasını sil
        try:
            db_yolu = self._vt._db_yolu
            if os.path.exists(db_yolu):
                os.remove(db_yolu)
        except Exception:
            pass
        # QSettings temizle
        try:
            ayarlar = QSettings("KulumTal", "Tahta")
            ayarlar.clear()
            ayarlar.sync()
        except Exception:
            pass
        # Uygulamayı yeniden başlat
        os.execv(sys.executable, [sys.executable] + sys.argv)


class Kilit(QMainWindow):
    _video_hazir = pyqtSignal(str, list)

    # Başlangıçta WebView'da gösterilecek inline yükleniyor sayfası
    _YUKLENIYOR_HTML = """<!DOCTYPE html>
<html lang='tr'><head><meta charset='UTF-8'/><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #f0f2f5;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #475569;
    user-select: none;
  }
  .spinner {
    width: 52px; height: 52px;
    border: 4px solid #e2e8f0;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.85s linear infinite;
    margin-bottom: 22px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  p { font-size: 15px; font-weight: 500; letter-spacing: 0.3px; opacity: 0.65; }
</style></head>
<body>
  <div class='spinner'></div>
  <p>Yükleniyor\u2026</p>
</body></html>"""

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
        self._online.kapat_sinyali.connect(self._online_kapat)
        self._online.baglanti_durumu_sinyali.connect(self._online_baglanti_degisti)
        self._online.durum_bilgisi_sinyali.connect(self._online_durum_senkronize)
        self._online.ders_saatleri_sinyali.connect(self._ders_saatleri_guncelle)
        self._online.tahta_adi_sinyali.connect(self._tahta_adi_guncelle)
        self._online.kurum_adi_sinyali.connect(self._kurum_adi_guncelle)
        self._online.kurum_kodu_sinyali.connect(self._kurum_kodu_guncelle)
        self._online.sinavlar_sinyali.connect(self._sinavlari_guncelle)
        self._online.icerik_guncellendi_sinyali.connect(self._icerik_guncellendi)
        self._online.hata_sinyali.connect(self._online_hata_geldi)
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
        ust_cizgi.setStyleSheet("color: #b0b0b0;")
        kenar_yerlesim.addSpacing(10)
        kenar_yerlesim.addWidget(ust_cizgi)

        tahta_kayit_veri = self._vt.tahta_kaydi_al(self._kurumkodu)
        tahta_adi_metin = tahta_kayit_veri["adi"] if tahta_kayit_veri else "Tahta"
        kurum_adi_metin = tahta_kayit_veri.get("kurum_adi", "") if tahta_kayit_veri else ""

        # ── Kurum & Tahta bilgi kartı ──
        bilgi_karti = QFrame()
        bilgi_karti.setStyleSheet("""
            QFrame#bilgiKarti {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ffffff, stop:1 #eef1f5);
                border: none;
                border-radius: 10px;
            }
        """)
        bilgi_karti.setObjectName("bilgiKarti")
        bilgi_kart_yerlesim = QVBoxLayout()
        bilgi_kart_yerlesim.setContentsMargins(14, 10, 14, 10)
        bilgi_kart_yerlesim.setSpacing(2)

        # Kurum adı
        self._kurum_adi_etiketi = QLabel(kurum_adi_metin)
        kurum_font = QFont("Exo 2", 13)
        kurum_font.setWeight(QFont.DemiBold)
        self._kurum_adi_etiketi.setFont(kurum_font)
        self._kurum_adi_etiketi.setStyleSheet(
            "color: #34495e; border: none; background: transparent;"
        )
        self._kurum_adi_etiketi.setAlignment(Qt.AlignCenter)
        self._kurum_adi_etiketi.setWordWrap(True)
        if not kurum_adi_metin:
            self._kurum_adi_etiketi.hide()
        bilgi_kart_yerlesim.addWidget(self._kurum_adi_etiketi)

        # İnce ayırıcı çizgi
        self._bilgi_ayirici = QFrame()
        self._bilgi_ayirici.setFrameShape(QFrame.HLine)
        self._bilgi_ayirici.setFixedWidth(40)
        self._bilgi_ayirici.setStyleSheet("color: #d0d5dc; background: #d0d5dc; border: none; max-height: 1px;")
        if not kurum_adi_metin:
            self._bilgi_ayirici.hide()
        ayirici_yerlesim = QHBoxLayout()
        ayirici_yerlesim.addStretch()
        ayirici_yerlesim.addWidget(self._bilgi_ayirici)
        ayirici_yerlesim.addStretch()
        bilgi_kart_yerlesim.addLayout(ayirici_yerlesim)

        # Tahta adı
        self._tahta_adi_etiketi = QLabel(tahta_adi_metin)
        sinif_yazi_tipi = QFont("Exo 2", 14)
        sinif_yazi_tipi.setWeight(QFont.Bold)
        self._tahta_adi_etiketi.setFont(sinif_yazi_tipi)
        self._tahta_adi_etiketi.setStyleSheet(
            "color: #2c3e50; border: none; background: transparent;"
        )
        self._tahta_adi_etiketi.setAlignment(Qt.AlignCenter)
        self._tahta_adi_etiketi.setWordWrap(True)
        bilgi_kart_yerlesim.addWidget(self._tahta_adi_etiketi)

        bilgi_karti.setLayout(bilgi_kart_yerlesim)
        kenar_yerlesim.addSpacing(6)
        kenar_yerlesim.addWidget(bilgi_karti)
        kenar_yerlesim.addSpacing(10)

        # ========== Sınav Takvimi ==========
        self._sinav_kart_yukseklik = 62
        self._sinav_kart_bosluk = 6

        self._sinav_scroll = QScrollArea()
        self._sinav_scroll.setWidgetResizable(True)
        self._sinav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sinav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sinav_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
        """)
        # Başlangıçta sabit yükseklik yok — içeriğe göre ayarlanacak
        self._sinav_scroll.setMinimumHeight(0)
        self._sinav_scroll.setMaximumHeight(16777215)
        self._sinav_icerik = QWidget()
        self._sinav_icerik.setStyleSheet("background: transparent;")
        self._sinav_yerlesim = QVBoxLayout()
        self._sinav_yerlesim.setContentsMargins(0, 5, 0, 5)
        self._sinav_yerlesim.setSpacing(self._sinav_kart_bosluk)

        self._sinav_icerik.setLayout(self._sinav_yerlesim)
        self._sinav_scroll.setWidget(self._sinav_icerik)
        self._sinav_scroll.hide()

        self._sinav_ust_cizgi = QFrame()
        self._sinav_ust_cizgi.setFrameShape(QFrame.HLine)
        self._sinav_ust_cizgi.setStyleSheet("color: #b0b0b0;")
        kenar_yerlesim.addWidget(self._sinav_ust_cizgi)
        kenar_yerlesim.addSpacing(5)

        kenar_yerlesim.addWidget(self._sinav_scroll)
        kenar_yerlesim.addSpacing(5)

        self._sinav_alt_cizgi = QFrame()
        self._sinav_alt_cizgi.setFrameShape(QFrame.HLine)
        self._sinav_alt_cizgi.setStyleSheet("color: #b0b0b0;")
        kenar_yerlesim.addWidget(self._sinav_alt_cizgi)

        kenar_yerlesim.addStretch(1)

        # Challenge sistemini başlat (widget'lar aşağıda oluşturulacak)

        # Saat ve tarihi güncelle
        self._saat_guncelle()
        self._saat_zamanlayici = QTimer(self)
        self._saat_zamanlayici.timeout.connect(self._saat_guncelle)
        self._saat_zamanlayici.start(1000)

        qr_ust_cizgi = QFrame()
        qr_ust_cizgi.setFrameShape(QFrame.HLine)
        qr_ust_cizgi.setStyleSheet("color: #b0b0b0;")
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
        kenar_yerlesim.addSpacing(10)

        # Sidebar ana layout: üst bar + içerik + alt bar
        sidebar_ana_yerlesim = QVBoxLayout()
        sidebar_ana_yerlesim.setContentsMargins(0, 0, 0, 0)
        sidebar_ana_yerlesim.setSpacing(0)

        sidebar_ana_yerlesim.addLayout(kenar_yerlesim)

        # ── Alt Bar (kurum.html tarzı — pasta geri sayım) ──
        self._kapanma_suresi = 15 * 60  # 15 dakika
        self._kapanma_kalan = self._kapanma_suresi

        alt_bar = QFrame()
        alt_bar.setObjectName("altBar")
        alt_bar.setFixedHeight(21)
        alt_bar.setStyleSheet("""
            QFrame#altBar {
                background-color: #ffffff;
                border-top: 1px solid #d0d5dc;
            }
        """)
        alt_bar_yerlesim = QHBoxLayout()
        alt_bar_yerlesim.setContentsMargins(4, 1, 4, 1)
        alt_bar_yerlesim.setSpacing(0)

        self._pasta_sayac = PastaGeriSayim()
        self._pasta_sayac.setFixedSize(17, 17)
        alt_bar_yerlesim.addWidget(self._pasta_sayac)
        alt_bar_yerlesim.addStretch(1)

        alt_bar.setLayout(alt_bar_yerlesim)
        sidebar_ana_yerlesim.addWidget(alt_bar)

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
        self.web_gorunum.setContextMenuPolicy(Qt.NoContextMenu)
        self.web_gorunum.settings().setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        self.web_gorunum.settings().setAttribute(QWebEngineSettings.WebGLEnabled, True)
        # URL'yi veritabanından oku, yoksa varsayılanı kullan
        db_url = self._vt.url_al(self._kurumkodu)
        webview_url = db_url if db_url else "https://kulumtal.com/php/"
        webview_url = self._url_kurum_kodu_ekle(webview_url)
        self._webview_hedef_url = webview_url  # Çevrimiçi hedef URL
        # WebView durum yönetimi: tek değişken, 3 durum
        # 'yukluyor' = başlangıç spinner, 'online' = kurum sayfası, 'offline' = çevrimdışı HTML
        self._webview_durum = 'yukluyor'
        self._sunucu_bagli = False    # Socket.IO bağlantı durumu

        # Offline gecikme zamanlayıcısı: bağlantı koptuğunda ani geçiş olmasın
        self._offline_gecikme_zamanlayici = QTimer(self)
        self._offline_gecikme_zamanlayici.setSingleShot(True)
        self._offline_gecikme_zamanlayici.timeout.connect(self._cevrimdisi_moda_gec)
        # Başlangıç zaman aşımı: bu sürede sunucu gelmezse offline moda geç
        self._baslangic_zamanlayici = QTimer(self)
        self._baslangic_zamanlayici.setSingleShot(True)
        self._baslangic_zamanlayici.timeout.connect(self._baslangic_zaman_asimi)
        self._baslangic_zamanlayici.start(BASTANGIC_BEKLEME_SANIYE * 1000)

        self.web_gorunum.loadFinished.connect(self._webview_yukleme_bitti)
        # Başlangıçta inline yükleniyor sayfası göster (dosya bağımlılığı yok)
        self.web_gorunum.setHtml(self._YUKLENIYOR_HTML)
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
        oran = max(self._kapanma_kalan, 0) / self._kapanma_suresi
        self._pasta_sayac.oran_ayarla(oran)
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

    def _online_kapat(self):
        """Sunucudan kapat komutu geldi — bilgisayarı kapat"""
        subprocess.Popen(["systemctl", "poweroff"])

    def _online_hata_geldi(self, mesaj):
        """Sunucudan hata geldi — kayıtlı değil ise online moda geçme"""
        if "kayıtlı değil" in mesaj.lower():
            self._offline_gecikme_zamanlayici.stop()
            if self._webview_durum == 'online':
                self._webview_sayfa_yukle('offline')
            elif self._webview_durum == 'yukluyor':
                self._webview_sayfa_yukle('offline')

    def _online_baglanti_degisti(self, bagli):
        """Sunucu bağlantı durumu değişti"""
        durum_str = "Bağlı" if bagli else "Çevrimdışı"
        print(f"[ONLİNE] Sunucu: {durum_str}")
        self._sunucu_bagli = bagli
        renk = '#27ae60' if bagli else '#e74c3c'
        self._kilit_ac_butonu.setIcon(qta.icon('fa5s.lock-open', color=renk))
        if bagli:
            # Tüm bekleme zamanlayıcılarını iptal et
            self._baslangic_zamanlayici.stop()
            self._offline_gecikme_zamanlayici.stop()
            # Kurum sayfası göstermiyorsak hemen yükle
            if self._webview_durum != 'online':
                self._webview_sayfa_yukle('online')
        else:
            if self._webview_durum == 'yukluyor':
                # Henüz yükleniyor modunda, başlangıç timer'ı yoksa başlat
                if not self._baslangic_zamanlayici.isActive():
                    self._baslangic_zamanlayici.start(BASTANGIC_BEKLEME_SANIYE * 1000)
            elif self._webview_durum == 'online':
                # Çevrimiçiyken bağlantı koptu → gecikmeli offline geçiş
                if not self._offline_gecikme_zamanlayici.isActive():
                    print(f"[ONLİNE] {OFFLINE_GECIKME_SANIYE}s sonra çevrimdışı moda geçilecek")
                    self._offline_gecikme_zamanlayici.start(OFFLINE_GECIKME_SANIYE * 1000)
            # Zaten offline ise bir şey yapma

    def _webview_sayfa_yukle(self, hedef):
        """WebView'ı hedef duruma geçir: 'online' veya 'offline'"""
        # Stacked widget'ı her zaman web alanına geçir (video üstünde kalmasın)
        self._icerik_yigini.setCurrentWidget(self._web_alani)
        if hedef == 'online':
            url = self._webview_hedef_url
            print(f"[WEBVIEW] Kurum sayfası yükleniyor: {url}")
            self._webview_durum = 'online'
            self.web_gorunum.setUrl(QUrl(url))
        elif hedef == 'offline':
            url = self._cevrimdisi_url_olustur()
            print(f"[WEBVIEW] Çevrimdışı sayfa yükleniyor: {url}")
            self._webview_durum = 'offline'
            self.web_gorunum.setUrl(QUrl(url))

    def _webview_online_yenile(self):
        """Online sayfayı güvenli yenile — URL henüz yüklenmemişse setUrl kullan"""
        hedef = QUrl(self._webview_hedef_url)
        if self.web_gorunum.url() == hedef:
            self.web_gorunum.reload()
        else:
            print(f"[WEBVIEW] URL uyumsuz, setUrl ile yeniden yükleniyor: {self._webview_hedef_url}")
            self.web_gorunum.setUrl(hedef)

    def _cevrimdisi_moda_gec(self):
        """Gecikme süresi doldu — hala bağlı değilse offline geç"""
        if not self._sunucu_bagli and self._webview_durum != 'offline':
            self._webview_sayfa_yukle('offline')

    def _baslangic_zaman_asimi(self):
        """Başlangıçta sunucuya bağlanılamadı → çevrimdışı moda geç"""
        if self._webview_durum == 'yukluyor' and not self._sunucu_bagli:
            self._webview_sayfa_yukle('offline')

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

    def _kurum_adi_guncelle(self, yeni_kurum_adi):
        """Sunucudan gelen kurum adını güncelle"""
        if yeni_kurum_adi and self._kurum_adi_etiketi.text() != yeni_kurum_adi:
            self._kurum_adi_etiketi.setText(yeni_kurum_adi)
            self._kurum_adi_etiketi.show()
            self._bilgi_ayirici.show()
            kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
            if kayit:
                self._vt.tahta_kaydi_olustur(
                    self._kurumkodu, kayit["adi"],
                    durum=kayit["durum"], ses=kayit["ses"],
                    anahtar=kayit["anahtar"], kurum_adi=yeni_kurum_adi,
                    url=kayit.get("url", "")
                )

    def _kurum_kodu_guncelle(self, sunucu_kurum_kodu):
        """Sunucudan gelen gerçek kurum kodunu yerelde güncelle"""
        if not sunucu_kurum_kodu or sunucu_kurum_kodu == self._kurumkodu:
            return
        kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        if kayit:
            # Sadece kurumkodu alanını güncelle (id ve diğer alanlar aynı kalır)
            self._vt.kurumkodu_guncelle(self._kurumkodu, sunucu_kurum_kodu)
        self._kurumkodu = sunucu_kurum_kodu

    def _sinavlari_guncelle(self, sinavlar):
        """Sunucudan gelen sınav listesini kilit ekranında göster"""
        # Otomatik kaydırma timer'ını durdur
        if hasattr(self, '_sinav_kaydirma_timer'):
            self._sinav_kaydirma_timer.stop()

        # Mevcut widget'ları temizle
        while self._sinav_yerlesim.count():
            item = self._sinav_yerlesim.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Bugün ve sonrası olan sınavları filtrele
        bugun = datetime.now().strftime("%Y-%m-%d")
        gelecek = [s for s in sinavlar if s.get("sinav_tarihi", "") >= bugun]
        self._sinav_listesi_boyut = len(gelecek)

        if not gelecek:
            self._sinav_scroll.hide()
        else:
            # Tüm kartları ekle
            for sinav in gelecek:
                self._sinav_yerlesim.addWidget(self._sinav_karti_olustur(sinav))

            # Sonsuz kaydırma için kartları iki kez daha ekle (toplam 3 kopya)
            for sinav in gelecek:
                self._sinav_yerlesim.addWidget(self._sinav_karti_olustur(sinav))
            for sinav in gelecek:
                self._sinav_yerlesim.addWidget(self._sinav_karti_olustur(sinav))

            # Tam 3 kart sığacak yükseklik
            sinav_gorunen = min(len(gelecek), 3) * self._sinav_kart_yukseklik + (min(len(gelecek), 3) - 1) * self._sinav_kart_bosluk + 10
            self._sinav_scroll.setFixedHeight(sinav_gorunen)
            self._sinav_scroll.show()

            # Scroll'u başa al ve timer başlat
            self._sinav_scroll.verticalScrollBar().setValue(0)
            self._sinav_kaydirma_bekleme = 60  # Başta 3sn bekle
            if not hasattr(self, '_sinav_kaydirma_timer'):
                self._sinav_kaydirma_timer = QTimer(self)
                self._sinav_kaydirma_timer.timeout.connect(self._sinav_otomatik_kaydir)
            self._sinav_kaydirma_timer.start(80)

    def _sinav_otomatik_kaydir(self):
        """Sınav listesini sonsuz döngüde aşağı kaydır"""
        sb = self._sinav_scroll.verticalScrollBar()
        maks = sb.maximum()
        if maks <= 0:
            return

        # Başlangıçta ve sıfırlama sonrası kısa bekleme
        if self._sinav_kaydirma_bekleme > 0:
            self._sinav_kaydirma_bekleme -= 1
            return

        # İlk setin piksel yüksekliği (kartlar 3 kopya eklendi, 1/3'te sıfırla)
        bir_set = self._sinav_listesi_boyut * (self._sinav_kart_yukseklik + self._sinav_kart_bosluk)
        if sb.value() >= bir_set:
            sb.setValue(sb.value() - bir_set)
            return

        sb.setValue(sb.value() + 1)

    def _sinav_karti_olustur(self, sinav):
        """Tek bir sınav kartı widget'ı oluştur — flat tasarım"""
        from datetime import timedelta
        ay_kisa = {
            1: "OCA", 2: "ŞUB", 3: "MAR", 4: "NİS",
            5: "MAY", 6: "HAZ", 7: "TEM", 8: "AĞU",
            9: "EYL", 10: "EKİ", 11: "KAS", 12: "ARA"
        }

        tarih_str = sinav.get("sinav_tarihi", "")
        baslangic = sinav.get("ders_saati_baslangic", 1)
        bitis = sinav.get("ders_saati_bitis", 1)
        ders_adi = sinav.get("ders_adi", "")
        ekleyen_adi = sinav.get("ekleyen_adi", "")

        bugun = datetime.now().date()
        try:
            sinav_tarih = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            gun = str(sinav_tarih.day)
            ay = ay_kisa.get(sinav_tarih.month, "")
            fark = (sinav_tarih - bugun).days
        except Exception:
            gun = "?"
            ay = ""
            fark = 99

        # Renk şeması: bugün=mavi, yarın=turuncu, 2 gün sonra=yeşil, diğer=gri
        if fark == 0:
            tema_renk = "#3498db"
            kart_bg = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #eaf4fc,stop:1 #f7fbff)"
            ders_renk = "#1a5276"
            etiket_metin = "BUGÜN"
        elif fark == 1:
            tema_renk = "#e67e22"
            kart_bg = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #fef5ec,stop:1 #fffbf5)"
            ders_renk = "#7e4a12"
            etiket_metin = "YARIN"
        elif fark == 2:
            tema_renk = "#27ae60"
            kart_bg = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #eafaf1,stop:1 #f5fdf9)"
            ders_renk = "#1a7a42"
            gun_adlari = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]
            etiket_metin = gun_adlari[sinav_tarih.weekday()]
        else:
            tema_renk = "#bdc3c7"
            kart_bg = "#f8f9fa"
            ders_renk = "#4a4a4a"
            gun_adlari = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]
            etiket_metin = gun_adlari[sinav_tarih.weekday()] if fark != 99 else ""

        # Ders saati metni
        if baslangic == bitis:
            saat_metin = f"{baslangic}. Ders"
        else:
            saat_metin = f"{baslangic}-{bitis}. Ders"

        # === Ana kart ===
        kart = QFrame()
        kart.setFixedHeight(self._sinav_kart_yukseklik)
        kart.setStyleSheet(f"""
            QFrame {{
                background: {kart_bg};
                border: none; border-radius: 6px;
            }}
        """)

        ana_yerlesim = QHBoxLayout()
        ana_yerlesim.setContentsMargins(0, 0, 10, 0)
        ana_yerlesim.setSpacing(0)

        # === Sol: Tarih bloğu ===
        tarih_blok = QFrame()
        tarih_blok.setStyleSheet(f"""
            QFrame {{
                background-color: {tema_renk};
                border: none;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
        """)
        tarih_blok.setFixedWidth(44)
        tarih_yerlesim = QVBoxLayout()
        tarih_yerlesim.setContentsMargins(0, 6, 0, 6)
        tarih_yerlesim.setSpacing(0)
        tarih_yerlesim.setAlignment(Qt.AlignCenter)

        gun_lbl = QLabel(gun)
        gun_lbl.setFont(QFont("Exo 2", 15, QFont.Bold))
        gun_lbl.setAlignment(Qt.AlignCenter)
        gun_lbl.setStyleSheet("color: white; border: none; background: transparent;")
        tarih_yerlesim.addWidget(gun_lbl)

        ay_lbl = QLabel(ay)
        ay_lbl.setFont(QFont("Exo 2", 7, QFont.Bold))
        ay_lbl.setAlignment(Qt.AlignCenter)
        ay_lbl.setStyleSheet("color: rgba(255,255,255,0.85); border: none; background: transparent;")
        tarih_yerlesim.addWidget(ay_lbl)

        tarih_blok.setLayout(tarih_yerlesim)
        ana_yerlesim.addWidget(tarih_blok)

        # === Sağ: Detay bloğu ===
        detay_yerlesim = QVBoxLayout()
        detay_yerlesim.setContentsMargins(10, 5, 0, 5)
        detay_yerlesim.setSpacing(3)

        # Ders adı
        ders = QLabel(ders_adi)
        ders.setFont(QFont("Exo 2", 10, QFont.Bold))
        ders.setStyleSheet(f"color: {ders_renk}; border: none; background: transparent;")
        ders.setWordWrap(True)
        detay_yerlesim.addWidget(ders)

        # Ders saati satırı
        saat_satir = QHBoxLayout()
        saat_satir.setSpacing(5)
        saat_ikon = QLabel()
        saat_ikon.setPixmap(qta.icon('fa5s.clock', color=tema_renk).pixmap(QSize(12, 12)))
        saat_ikon.setStyleSheet("border: none; background: transparent;")
        saat_ikon.setFixedSize(14, 14)
        saat_satir.addWidget(saat_ikon)
        saat_lbl = QLabel(saat_metin)
        saat_lbl.setFont(QFont("Exo 2", 9))
        saat_lbl.setStyleSheet(f"color: {tema_renk}; border: none; background: transparent;")
        saat_satir.addWidget(saat_lbl)

        # Etiket (BUGÜN / YARIN)
        if etiket_metin:
            etiket_lbl = QLabel(etiket_metin)
            etiket_lbl.setFont(QFont("Exo 2", 7, QFont.Bold))
            etiket_lbl.setStyleSheet(f"""
                color: white; background-color: {tema_renk};
                border: none; border-radius: 3px;
                padding: 1px 6px;
            """)
            saat_satir.addWidget(etiket_lbl)

        saat_satir.addStretch()
        detay_yerlesim.addLayout(saat_satir)

        # Öğretmen adı
        if ekleyen_adi:
            ogr_satir = QHBoxLayout()
            ogr_satir.setSpacing(5)
            ogr_ikon = QLabel()
            ogr_ikon.setPixmap(qta.icon('fa5s.user', color='#aab0b5').pixmap(QSize(10, 10)))
            ogr_ikon.setStyleSheet("border: none; background: transparent;")
            ogr_ikon.setFixedSize(14, 14)
            ogr_satir.addWidget(ogr_ikon)
            ogr_lbl = QLabel(ekleyen_adi)
            ogr_lbl.setFont(QFont("Exo 2", 8))
            ogr_lbl.setStyleSheet("color: #aab0b5; border: none; background: transparent;")
            ogr_satir.addWidget(ogr_lbl)
            ogr_satir.addStretch()
            detay_yerlesim.addLayout(ogr_satir)

        ana_yerlesim.addLayout(detay_yerlesim, 1)
        kart.setLayout(ana_yerlesim)
        return kart

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

    def _url_kurum_kodu_ekle(self, url):
        """URL'ye kurum kodu ve tahta id parametresini ekle"""
        if '/kurum' in url and 'kod=' not in url:
            ayrac = '&' if '?' in url else '?'
            url = f"{url}{ayrac}kod={self._kurumkodu}"
            if hasattr(self, '_tahta_id') and self._tahta_id:
                url = f"{url}&tahta_id={self._tahta_id}"
        return url

    def _webview_url_yenile(self):
        """Ayarlar kaydedildikten sonra web görünüm URL'sini güncelle"""
        db_url = self._vt.url_al(self._kurumkodu)
        yeni_url = db_url if db_url else "https://kulumtal.com/php/"
        yeni_url = self._url_kurum_kodu_ekle(yeni_url)
        self._webview_hedef_url = yeni_url
        if self._sunucu_bagli:
            self._baslangic_zamanlayici.stop()
            self._offline_gecikme_zamanlayici.stop()
            mevcut_url = self.web_gorunum.url().toString()
            if mevcut_url != yeni_url:
                self._webview_sayfa_yukle('online')

    # ===================== ÇEVRİMDIŞI FALLBACK =====================

    def _cevrimdisi_url_olustur(self):
        """Yerel çevrimdışı HTML sayfasının URL'sini oluştur"""
        from urllib.parse import quote
        tahta_kayit = self._vt.tahta_kaydi_al(self._kurumkodu)
        kurum_adi = tahta_kayit.get("kurum_adi", "") if tahta_kayit else ""
        sinif_adi = tahta_kayit.get("adi", "") if tahta_kayit else ""
        logo_yolu = os.path.join(BETIK_DIZINI, "resim", "logo.png")
        logo_param = "file://" + logo_yolu if os.path.isfile(logo_yolu) else ""
        html_yol = os.path.join(BETIK_DIZINI, "cevrimdisi.html")
        return (f"file://{html_yol}?kurum={quote(kurum_adi)}"
                f"&sinif={quote(sinif_adi)}&logo={quote(logo_param)}")

    def _webview_yukleme_bitti(self, basarili):
        """WebView sayfa yükleme sonucu — başarısızsa çevrimdışı sayfaya geç"""
        # Yakınlaştırma/uzaklaştırma ve sağ tık menüsünü devre dışı bırak
        self.web_gorunum.page().runJavaScript("""
            document.addEventListener('contextmenu', function(e) { e.preventDefault(); }, true);
            document.addEventListener('keydown', function(e) {
                if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '-' || e.key === '=' || e.key === '0')) {
                    e.preventDefault();
                }
            }, true);
            document.addEventListener('wheel', function(e) {
                if (e.ctrlKey) { e.preventDefault(); }
            }, {passive: false, capture: true});
            document.addEventListener('touchmove', function(e) {
                if (e.touches.length > 1) { e.preventDefault(); }
            }, {passive: false, capture: true});
            document.addEventListener('touchstart', function(e) {
                if (e.touches.length > 1) { e.preventDefault(); }
            }, {passive: false, capture: true});
            var meta = document.querySelector('meta[name=viewport]');
            if (!meta) { meta = document.createElement('meta'); meta.name = 'viewport'; document.head.appendChild(meta); }
            meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no';
        """)
        mevcut_url = self.web_gorunum.url().toString()
        url_goster = mevcut_url if not mevcut_url.startswith("data:") else mevcut_url[:40] + "…"
        print(f"[WEBVIEW] loadFinished: basarili={basarili}, durum={self._webview_durum}, url={url_goster}")
        if self._webview_durum == 'online' and not basarili:
            # Kurum sayfası yüklenemedi — sunucu hala bağlıysa 5s sonra tekrar dene
            if self._sunucu_bagli:
                print("[WEBVIEW] Sayfa yüklenemedi, 5s sonra tekrar denenecek")
                QTimer.singleShot(5000, self._kurum_sayfasi_tekrar_dene)

    def _kurum_sayfasi_tekrar_dene(self):
        """Sunucu bağlıysa ve hala online moddaysak kurum sayfasını tekrar yükle"""
        if self._sunucu_bagli and self._webview_durum == 'online':
            print("[WEBVIEW] Kurum sayfası yeniden deneniyor")
            self.web_gorunum.setUrl(QUrl(self._webview_hedef_url))

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
        # WebView sayfasını duruma göre yükle
        if self._sunucu_bagli:
            if self._webview_durum != 'online':
                self._webview_sayfa_yukle('online')
            else:
                self._webview_online_yenile()
        elif self._webview_durum == 'yukluyor':
            # Henüz bağlantı yok, yükleniyor ekranını korr
            pass
        elif self._webview_durum != 'offline':
            self._webview_sayfa_yukle('offline')
        self.showFullScreen()
        QApplication.processEvents()
        QTimer.singleShot(200, self._icerik_yukle)
        QTimer.singleShot(500, self._girisleri_yakala)

        self._odak_zamanlayici.start(1000)

    def _icerik_yenile(self):
        """Kilit ekranı açıkken periyodik olarak webview'ı yenile"""
        if not self._kilit_acma_istendi and self.isVisible():
            if self._webview_durum == 'online':
                self._webview_online_yenile()

    def _icerik_guncellendi(self):
        """Sunucudan içerik güncellemesi bildirimi geldi → webview yenile"""
        if not self._kilit_acma_istendi and self.isVisible():
            if self._webview_durum == 'online':
                self._webview_online_yenile()
            else:
                # Sunucudan sinyal geldi → bağlantı kesin var, hemen online geç
                self._baslangic_zamanlayici.stop()
                self._offline_gecikme_zamanlayici.stop()
                self._webview_sayfa_yukle('online')

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
        # Varsa önceki geri sayım zamanlayici ve tekrar kilitle zamanlayicisini durdur
        if hasattr(self, '_geri_sayim_zamanlayici') and self._geri_sayim_zamanlayici.isActive():
            self._geri_sayim_zamanlayici.stop()
        if hasattr(self, '_tekrar_kilitle_zamanlayici') and self._tekrar_kilitle_zamanlayici.isActive():
            self._tekrar_kilitle_zamanlayici.stop()
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

        # WebView sayfasını yenile (arka planda)
        if self._webview_durum == 'online':
            self._webview_online_yenile()

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

        # Varsa eski pencereyi kapat
        if hasattr(self, '_kilitle_pencere') and self._kilitle_pencere is not None:
            try:
                self._kilitle_pencere.close()
            except Exception:
                pass
            self._kilitle_pencere = None

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
        if self._webview_durum == 'online':
            self._webview_online_yenile()
        elif self._sunucu_bagli:
            self._webview_sayfa_yukle('online')
        self.showFullScreen()

        # Videoyu devam ettir
        if self._video_katmani and hasattr(self, '_vlc_list_player') and self._vlc_list_player and not self._video_gizli:
            self._vlc_list_player.play()
        # VLC sesini güvenceye al (susturma sonrası)
        QTimer.singleShot(300, self._vlc_unmute_guvence)

        QTimer.singleShot(500, self._girisleri_yakala)
        self._odak_zamanlayici.start(1000)
        self._kapanma_kalan = self._kapanma_suresi
        self._pasta_sayac.oran_ayarla(1.0)
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
