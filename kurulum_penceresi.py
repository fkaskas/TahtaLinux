# -*- coding: utf-8 -*-
"""İlk kurulum ekranı — Tahta adı, kurum kodu ve gizli anahtar bilgilerini alır"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QPushButton, QLabel, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import uuid
from smb_bagla import SmbBaglamaPenceresi


class KurulumPenceresi(QDialog):
    """DB'de kayıt/anahtar yoksa açılışta gösterilecek kurulum penceresi"""

    def __init__(self, parent=None, mevcut_kurumkodu="", mevcut_adi=""):
        super().__init__(parent)
        self.setWindowTitle("Tahta Kilit — İlk Kurulum")
        self.setFixedSize(560, 540)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

        self._kurumkodu = ""
        self._adi = ""
        self._anahtar = ""
        self._kurum_adi = ""
        self._url = ""
        self._tahta_id = str(uuid.uuid4())

        self._arayuz_olustur(mevcut_kurumkodu, mevcut_adi)

    def _arayuz_olustur(self, mevcut_kurumkodu, mevcut_adi):
        ana = QVBoxLayout()

        baslik = QLabel("Tahta Kilit Kurulumu")
        baslik.setFont(QFont("Sans", 16, QFont.Bold))
        baslik.setAlignment(Qt.AlignCenter)
        baslik.setStyleSheet("color: #2196F3; margin-bottom: 10px;")
        ana.addWidget(baslik)

        aciklama = QLabel("Lütfen tahta bilgilerini girin.\nBu bilgiler kilit doğrulama sistemi için kullanılacaktır.")
        aciklama.setAlignment(Qt.AlignCenter)
        aciklama.setStyleSheet("color: #666; margin-bottom: 15px;")
        ana.addWidget(aciklama)

        form = QFormLayout()

        self._tahta_id_girdi = QLineEdit()
        self._tahta_id_girdi.setText(self._tahta_id)
        self._tahta_id_girdi.setReadOnly(True)
        self._tahta_id_girdi.setMinimumHeight(35)
        self._tahta_id_girdi.setStyleSheet("background-color: #eee; color: #555;")
        form.addRow("Tahta ID:", self._tahta_id_girdi)

        self._kurumkodu_girdi = QLineEdit()
        self._kurumkodu_girdi.setPlaceholderText("Örn: 0001")
        self._kurumkodu_girdi.setText(mevcut_kurumkodu)
        self._kurumkodu_girdi.setMinimumHeight(35)
        form.addRow("Kurum Kodu:", self._kurumkodu_girdi)

        self._kurum_adi_girdi = QLineEdit()
        self._kurum_adi_girdi.setPlaceholderText("Örn: Atatürk İlkokulu")
        self._kurum_adi_girdi.setMinimumHeight(35)
        form.addRow("Kurum Adı:", self._kurum_adi_girdi)

        self._adi_girdi = QLineEdit()
        self._adi_girdi.setPlaceholderText("Örn: 11E Sınıfı")
        self._adi_girdi.setText(mevcut_adi)
        self._adi_girdi.setMinimumHeight(35)
        form.addRow("Tahta Adı:", self._adi_girdi)

        self._anahtar_girdi = QLineEdit()
        self._anahtar_girdi.setPlaceholderText("Gizli doğrulama anahtarı")
        self._anahtar_girdi.setMinimumHeight(35)
        form.addRow("Gizli Anahtar:", self._anahtar_girdi)

        self._url_girdi = QLineEdit()
        self._url_girdi.setPlaceholderText("Örn: https://kulumtal.com/php/")
        self._url_girdi.setMinimumHeight(35)
        form.addRow("WebView URL:", self._url_girdi)

        ana.addLayout(form)
        ana.addSpacing(15)

        kaydet_btn = QPushButton("Kaydet ve Başlat")
        kaydet_btn.setMinimumHeight(40)
        kaydet_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white;
                border: none; border-radius: 5px;
                font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        kaydet_btn.clicked.connect(self._kaydet)
        ana.addWidget(kaydet_btn)

        # SMB Ağ Klasörü Bağlama butonu
        smb_btn = QPushButton("📁 Ağ Klasörü Bağla (SMB)")
        smb_btn.setMinimumHeight(35)
        smb_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800; color: white;
                border: none; border-radius: 5px;
                font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        smb_btn.clicked.connect(self._smb_bagla)
        ana.addWidget(smb_btn)

        self.setLayout(ana)

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
