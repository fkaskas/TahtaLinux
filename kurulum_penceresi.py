# -*- coding: utf-8 -*-
"""İlk kurulum ekranı — Tahta adı, kurum kodu ve gizli anahtar bilgilerini alır"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QLabel, QMessageBox,
                             QWidget, QScrollArea, QApplication)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QFont, QCursor, QPainter, QColor, QPen, QBrush
import qtawesome as qta
import uuid
from smb_bagla import SmbBaglamaPenceresi


class KartWidget(QWidget):
    """Beyaz arka planlı, kenarlıklı köşesi yuvarlatılmış kart."""
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


class KurulumPenceresi(QDialog):
    """DB'de kayıt/anahtar yoksa açılışta gösterilecek kurulum penceresi"""

    def __init__(self, parent=None, mevcut_kurumkodu="", mevcut_adi=""):
        super().__init__(parent)
        self.setWindowTitle("Tahta Kilit — Kurulum")
        self.setFixedSize(700, 640)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #F0F2F5; font-family: 'Exo 2', 'Exo2', sans-serif;")

        self._kurumkodu = ""
        self._adi = ""
        self._anahtar = ""
        self._kurum_adi = ""
        self._url = ""
        self._tahta_id = str(uuid.uuid4())

        self._arayuz_olustur(mevcut_kurumkodu, mevcut_adi)

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    @staticmethod
    def _etiket(metin):
        lbl = QLabel(metin)
        lbl.setFont(QFont("Exo 2", 11))
        lbl.setStyleSheet("color: #475569; font-weight: 600; background: transparent;")
        lbl.setFixedWidth(130)
        lbl.setFixedHeight(36)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        return lbl

    @staticmethod
    def _girdi(placeholder="", readonly=False):
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        w.setFixedHeight(36)
        w.setReadOnly(readonly)
        w.setFont(QFont("Exo 2", 11))
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
                "border-radius: 6px; padding: 0 10px; color: #1E293B;"
            )
        return w

    def _satir_ekle(self, hedef_layout, etiket_metni, widget):
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(12)
        row.addWidget(self._etiket(etiket_metni), 0, Qt.AlignVCenter)
        row.addWidget(widget, 1, Qt.AlignVCenter)
        hedef_layout.addLayout(row)

    def _kart_olustur(self, baslik, ikon=""):
        kart = KartWidget()
        ic = QVBoxLayout(kart)
        ic.setContentsMargins(16, 12, 16, 12)
        ic.setSpacing(8)

        lbl = QLabel(f"{ikon}  {baslik}" if ikon else baslik)
        lbl.setFont(QFont("Exo 2", 10, QFont.Bold))
        lbl.setStyleSheet("color: #34495e; background: transparent;")
        lbl.setFixedHeight(24)
        ic.addWidget(lbl)

        return kart, ic

    # ── Ana Arayüz ────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Dış kapatılma isteklerini (WM, X butonu, child widget close vb.) engelle"""
        event.ignore()

    def keyPressEvent(self, event):
        """Escape / Enter tuşlarıyla diyaloğun kapanmasını engelle"""
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            return
        super().keyPressEvent(event)

    def _arayuz_olustur(self, mevcut_kurumkodu, mevcut_adi):
        ana = QVBoxLayout(self)
        ana.setContentsMargins(0, 0, 0, 0)
        ana.setSpacing(0)

        # ── Başlık Bandı ─────────────────────────────────────────────────────
        bant = QWidget()
        bant.setFixedHeight(60)
        bant.setStyleSheet("background-color: #1a1a2e;")
        bant_ic = QHBoxLayout(bant)
        bant_ic.setContentsMargins(24, 0, 24, 0)

        baslik_lbl = QLabel("⚙  Tahta Kilit Kurulumu")
        baslik_lbl.setFont(QFont("Exo 2", 14, QFont.Bold))
        baslik_lbl.setStyleSheet("color: #FFFFFF; background: transparent;")

        alt_lbl = QLabel("Cihaz kimlik ve bağlantı bilgilerini girin")
        alt_lbl.setFont(QFont("Exo 2", 9))
        alt_lbl.setStyleSheet("color: #aab0b5; background: transparent;")

        yazi = QVBoxLayout()
        yazi.setSpacing(1)
        yazi.addWidget(baslik_lbl)
        yazi.addWidget(alt_lbl)
        bant_ic.addLayout(yazi)
        bant_ic.addStretch()
        ana.addWidget(bant)

        # ── İçerik ───────────────────────────────────────────────────────────
        icerik = QVBoxLayout()
        icerik.setContentsMargins(20, 14, 20, 14)
        icerik.setSpacing(10)

        # Kart 1: Cihaz Kimliği
        k1, k1_ic = self._kart_olustur("Cihaz Kimliği", "🖥")
        self._tahta_id_girdi = self._girdi(readonly=True)
        self._tahta_id_girdi.setText(self._tahta_id)
        # Tahta ID satırı + kopyala butonu
        tahta_id_row = QHBoxLayout()
        tahta_id_row.setContentsMargins(0, 2, 0, 2)
        tahta_id_row.setSpacing(12)
        tahta_id_row.addWidget(self._etiket("Tahta ID"), 0, Qt.AlignVCenter)
        tahta_id_row.addWidget(self._tahta_id_girdi, 1, Qt.AlignVCenter)
        kopyala_btn = QPushButton()
        kopyala_btn.setIcon(qta.icon("fa5s.copy", color="#FFFFFF"))
        kopyala_btn.setFixedSize(36, 36)
        kopyala_btn.setCursor(QCursor(Qt.PointingHandCursor))
        kopyala_btn.setToolTip("Tahta ID kopyala")
        kopyala_btn.setStyleSheet(
            "QPushButton{background:#3B82F6;border:none;border-radius:6px}"
            "QPushButton:pressed{background:#2563EB}")
        kopyala_btn.setAutoDefault(False)
        kopyala_btn.setDefault(False)
        kopyala_btn.clicked.connect(self._tahta_id_kopyala)
        tahta_id_row.addWidget(kopyala_btn, 0, Qt.AlignVCenter)
        k1_ic.addLayout(tahta_id_row)
        icerik.addWidget(k1)

        # Kart 2: Kurum Bilgileri
        k2, k2_ic = self._kart_olustur("Kurum Bilgileri", "🏫")
        self._kurumkodu_girdi = self._girdi("Örn: 0001")
        self._satir_ekle(k2_ic, "Kurum Kodu", self._kurumkodu_girdi)
        self._kurum_adi_girdi = self._girdi("Örn: Kulu Mesleki ve Teknik Anadolu Lisesi")
        self._satir_ekle(k2_ic, "Kurum Adı", self._kurum_adi_girdi)
        self._adi_girdi = self._girdi("Örn: 11E Sınıfı")
        self._satir_ekle(k2_ic, "Tahta Adı", self._adi_girdi)
        icerik.addWidget(k2)

        # Kart 3: Bağlantı Ayarları
        k3, k3_ic = self._kart_olustur("Bağlantı Ayarları", "🔐")
        self._anahtar_girdi = self._girdi("Gizli doğrulama anahtarı")
        self._anahtar_girdi.setEchoMode(QLineEdit.Password)
        self._satir_ekle(k3_ic, "Gizli Anahtar", self._anahtar_girdi)
        self._url_girdi = self._girdi("Örn: https://kulumtal.com")
        self._satir_ekle(k3_ic, "Sunucu URL", self._url_girdi)
        icerik.addWidget(k3)

        icerik.addStretch()

        # ── Butonlar ─────────────────────────────────────────────────────────
        buton = QHBoxLayout()
        buton.setSpacing(10)

        smb_btn = QPushButton("📁  Ağ Klasörü Bağla")
        smb_btn.setFixedSize(170, 38)
        smb_btn.setCursor(QCursor(Qt.PointingHandCursor))
        smb_btn.setStyleSheet(
            "background: #F97316; color: #FFF; border: none;"
            "border-radius: 7px; font-size: 12px; font-weight: bold;")
        smb_btn.setAutoDefault(False)
        smb_btn.setDefault(False)
        smb_btn.clicked.connect(self._smb_bagla)

        kaydet_btn = QPushButton("Kaydet ve Başlat")
        kaydet_btn.setFixedSize(170, 38)
        kaydet_btn.setCursor(QCursor(Qt.PointingHandCursor))
        kaydet_btn.setStyleSheet(
            "background: #3B82F6; color: #FFF; border: none;"
            "border-radius: 7px; font-size: 13px; font-weight: bold;")
        kaydet_btn.setAutoDefault(False)
        kaydet_btn.setDefault(False)
        kaydet_btn.clicked.connect(self._kaydet)

        buton.addWidget(smb_btn)
        buton.addStretch()
        buton.addWidget(kaydet_btn)
        icerik.addLayout(buton)

        ana.addLayout(icerik)

    def _kaydet(self):
        kurumkodu = self._kurumkodu_girdi.text().strip()
        adi = self._adi_girdi.text().strip()
        anahtar = self._anahtar_girdi.text().strip()
        kurum_adi = self._kurum_adi_girdi.text().strip()
        url = self._url_girdi.text().strip()

        if not kurumkodu:
            QMessageBox.warning(self, "Uyarı", "Kurum kodu boş bırakılamaz!")
            return
        if not adi:
            QMessageBox.warning(self, "Uyarı", "Tahta adı boş bırakılamaz!")
            return
        if not anahtar:
            QMessageBox.warning(self, "Uyarı", "Gizli anahtar boş bırakılamaz!")
            return

        self._kurumkodu = kurumkodu
        self._adi = adi
        self._anahtar = anahtar
        self._kurum_adi = kurum_adi
        self._url = url
        self.accept()

    def _smb_bagla(self):
        """SMB ağ klasörü bağlama penceresini aç"""
        pencere = SmbBaglamaPenceresi(self)
        pencere.exec_()

    def _tahta_id_kopyala(self):
        """Tahta ID değerini panoya kopyala"""
        metin = self._tahta_id_girdi.text().strip()
        if metin:
            QApplication.clipboard().setText(metin)

    @property
    def kurumkodu(self):
        return self._kurumkodu

    @property
    def adi(self):
        return self._adi

    @property
    def anahtar(self):
        return self._anahtar

    @property
    def kurum_adi(self):
        return self._kurum_adi

    @property
    def url(self):
        return self._url

    @property
    def tahta_id(self):
        return self._tahta_id
