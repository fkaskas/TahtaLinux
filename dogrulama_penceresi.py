# -*- coding: utf-8 -*-
"""Kilit doğrulama penceresi — nümerik klavyeli dialog"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLabel, QLineEdit, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QCursor, QPainter, QColor
from PyQt5.QtCore import QSize
import qtawesome as qta

from sabitler import KOD_UZUNLUGU, MAX_DENEME


class KodDogrulamaPenceresi(QDialog):
    """Kilidi açmak için response kodu girme dialogu"""

    def __init__(self, challenge_kodu, dogrulama_servisi, yeni_challenge_uret, parent=None, sure_goster=True):
        super().__init__(parent)
        self._challenge_kodu = challenge_kodu
        self._dogrulama_servisi = dogrulama_servisi
        self._yeni_challenge_uret = yeni_challenge_uret
        self._hatali_deneme = 0
        self.dogrulandi = False
        self.acik_kalma_suresi = 40
        self._sure_odakli = False
        self._sure_goster = sure_goster
        self._arayuz_olustur()

    def _arayuz_olustur(self):
        self.setWindowTitle("Kilit Doğrulama")
        self.setFixedSize(420, 680)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
        )
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WA_TranslucentBackground)

        yerlesim = QVBoxLayout()
        yerlesim.setContentsMargins(30, 30, 30, 30)
        yerlesim.setSpacing(6)

        baslik = QLabel("Kilidi Açmak İçin\nYanıt Kodunu Girin")
        baslik_font = QFont("Noto Sans", 14)
        baslik_font.setWeight(QFont.DemiBold)
        baslik.setFont(baslik_font)
        baslik.setAlignment(Qt.AlignCenter)
        baslik.setStyleSheet("color: #2c3e50;")
        yerlesim.addWidget(baslik)

        self._challenge_etiketi = QLabel(f"Challenge: {self._challenge_kodu}")
        self._challenge_etiketi.setFont(QFont("Noto Sans", 12))
        self._challenge_etiketi.setAlignment(Qt.AlignCenter)
        self._challenge_etiketi.setStyleSheet("color: #7f8c8d;")
        yerlesim.addWidget(self._challenge_etiketi)

        self._giris_kutusu = QLineEdit()
        self._giris_kutusu.setPlaceholderText("Yanıt kodu...")
        self._giris_kutusu.setMaxLength(KOD_UZUNLUGU)
        self._giris_kutusu.setAlignment(Qt.AlignCenter)
        self._giris_kutusu.setFont(QFont("", 20, QFont.Bold))
        self._giris_kutusu.setStyleSheet("""
            QLineEdit {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                padding: 10px;
                background-color: white;
                color: #2c3e50;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
        """)
        self._giris_kutusu.setReadOnly(True)
        self._giris_kutusu.mousePressEvent = lambda e: self._sure_odak_degistir(False)
        yerlesim.addWidget(self._giris_kutusu)

        self._durum_etiketi = QLabel("")
        self._durum_etiketi.setAlignment(Qt.AlignCenter)
        self._durum_etiketi.setStyleSheet("color: #e74c3c;")
        yerlesim.addWidget(self._durum_etiketi)

        # Açık kalma süresi seçici
        if self._sure_goster:
            sure_yerlesim = QHBoxLayout()
            sure_yerlesim.setSpacing(8)

            sure_baslik = QLabel("Süre (dk):")
            sure_baslik.setFont(QFont("Noto Sans", 11))
            sure_baslik.setStyleSheet("color: #7f8c8d;")
            sure_yerlesim.addWidget(sure_baslik)

            self._sure_girisi = QLineEdit("40")
            self._sure_girisi.setMaxLength(3)
            self._sure_girisi.setAlignment(Qt.AlignCenter)
            self._sure_girisi.setFont(QFont("", 16, QFont.Bold))
            self._sure_girisi.setReadOnly(True)
            self._sure_girisi.setFixedWidth(80)
            self._sure_girisi.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #bdc3c7;
                    border-radius: 8px;
                    padding: 6px;
                    background-color: white;
                    color: #2c3e50;
                }
            """)
            self._sure_girisi.mousePressEvent = lambda e: self._sure_odak_degistir(True)
            sure_yerlesim.addWidget(self._sure_girisi)

            sure_yerlesim.addStretch()
            yerlesim.addLayout(sure_yerlesim)
            yerlesim.addSpacing(4)
        else:
            self._sure_girisi = None

        # Nümerik klavye
        klavye_yerlesim = QGridLayout()
        klavye_yerlesim.setSpacing(10)

        numpad_stil = """
            QPushButton {
                background-color: #ecf0f1; color: #2c3e50; border: 1px solid #bdc3c7;
                border-radius: 10px; font-size: 22px; font-weight: bold;
                min-height: 60px; min-width: 60px;
            }
            QPushButton:hover { background-color: #d5dbdb; }
            QPushButton:pressed { background-color: #bdc3c7; }
        """

        for i in range(1, 10):
            btn = QPushButton(str(i))
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setStyleSheet(numpad_stil)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.clicked.connect(lambda checked, d=str(i): self._rakam_ekle(d))
            satir = (i - 1) // 3
            sutun = (i - 1) % 3
            klavye_yerlesim.addWidget(btn, satir, sutun)

        sil_btn = QPushButton()
        sil_btn.setIcon(qta.icon('fa5s.backspace', color='#e74c3c'))
        sil_btn.setIconSize(QSize(28, 28))
        sil_btn.setCursor(QCursor(Qt.PointingHandCursor))
        sil_btn.setStyleSheet(numpad_stil.replace("#ecf0f1", "#fadbd8").replace("#2c3e50", "#e74c3c"))
        sil_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sil_btn.clicked.connect(self._son_rakam_sil)
        klavye_yerlesim.addWidget(sil_btn, 3, 0)

        sifir_btn = QPushButton("0")
        sifir_btn.setCursor(QCursor(Qt.PointingHandCursor))
        sifir_btn.setStyleSheet(numpad_stil)
        sifir_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sifir_btn.clicked.connect(lambda: self._rakam_ekle("0"))
        klavye_yerlesim.addWidget(sifir_btn, 3, 1)

        temizle_btn = QPushButton()
        temizle_btn.setIcon(qta.icon('fa5s.eraser', color='#e67e22'))
        temizle_btn.setIconSize(QSize(28, 28))
        temizle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        temizle_btn.setStyleSheet(numpad_stil.replace("#ecf0f1", "#fdebd0").replace("#2c3e50", "#e67e22"))
        temizle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        temizle_btn.clicked.connect(self._temizle)
        klavye_yerlesim.addWidget(temizle_btn, 3, 2)

        yerlesim.addLayout(klavye_yerlesim)

        buton_yerlesim = QHBoxLayout()
        buton_yerlesim.setSpacing(10)

        iptal_butonu = QPushButton("İptal")
        iptal_butonu.setCursor(QCursor(Qt.PointingHandCursor))
        iptal_butonu.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6; color: white; border: none;
                border-radius: 10px; padding: 14px 20px; font-weight: bold;
                font-size: 16px; min-height: 40px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        iptal_butonu.clicked.connect(self.reject)
        buton_yerlesim.addWidget(iptal_butonu)

        dogrula_butonu = QPushButton("Doğrula")
        dogrula_butonu.setCursor(QCursor(Qt.PointingHandCursor))
        dogrula_butonu.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; border: none;
                border-radius: 10px; padding: 14px 20px; font-weight: bold;
                font-size: 16px; min-height: 40px;
            }
            QPushButton:hover { background-color: #219a52; }
        """)
        dogrula_butonu.clicked.connect(self._kodu_dogrula)
        buton_yerlesim.addWidget(dogrula_butonu)

        yerlesim.addLayout(buton_yerlesim)

        # TEST BUTONU — her şartta kilidi açar (geliştirme aşaması)
        test_butonu = QPushButton("⚠ TEST: Kilidi Aç")
        test_butonu.setCursor(QCursor(Qt.PointingHandCursor))
        test_butonu.setStyleSheet("""
            QPushButton {
                background-color: #f39c12; color: white; border: none;
                border-radius: 6px; padding: 8px 20px; font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #e67e22; }
        """)
        test_butonu.clicked.connect(self._test_kilidi_ac)
        yerlesim.addWidget(test_butonu)

        self.setLayout(yerlesim)

    def paintEvent(self, event):
        """Oval köşeli düz arka plan çiz"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f5f5f5"))
        painter.drawRoundedRect(self.rect(), 20, 20)
        painter.end()

    def challenge_guncelle(self, yeni_challenge):
        """Dışarıdan challenge kodu güncellemesi (timer değiştiğinde)"""
        self._challenge_kodu = yeni_challenge
        self._challenge_etiketi.setText(f"Challenge: {self._challenge_kodu}")
        self._giris_kutusu.clear()
        self._hatali_deneme = 0

    def _rakam_ekle(self, rakam):
        """Nümerik klavyeden rakam ekle"""
        if self._sure_odakli and self._sure_girisi:
            mevcut = self._sure_girisi.text()
            if len(mevcut) < 3:
                yeni = mevcut + rakam
                self._sure_girisi.setText(yeni)
                self.acik_kalma_suresi = int(yeni) if yeni else 0
        else:
            mevcut = self._giris_kutusu.text()
            if len(mevcut) < KOD_UZUNLUGU:
                yeni = mevcut + rakam
                self._giris_kutusu.setText(yeni)
                if len(yeni) == KOD_UZUNLUGU:
                    self._kodu_dogrula()

    def _son_rakam_sil(self):
        """Son girilen rakamı sil"""
        if self._sure_odakli and self._sure_girisi:
            mevcut = self._sure_girisi.text()
            self._sure_girisi.setText(mevcut[:-1])
            kalan = mevcut[:-1]
            self.acik_kalma_suresi = int(kalan) if kalan else 0
        else:
            mevcut = self._giris_kutusu.text()
            self._giris_kutusu.setText(mevcut[:-1])

    def _sure_odak_degistir(self, odak):
        """Süre alanına odaklan/odaktan çık"""
        if not self._sure_girisi:
            return
        self._sure_odakli = odak
        if odak:
            self._sure_girisi.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #3498db;
                    border-radius: 8px;
                    padding: 6px;
                    background-color: white;
                    color: #2c3e50;
                }
            """)
            self._giris_kutusu.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #bdc3c7;
                    border-radius: 8px;
                    padding: 10px;
                    background-color: white;
                    color: #2c3e50;
                }
            """)
        else:
            self._sure_girisi.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #bdc3c7;
                    border-radius: 8px;
                    padding: 6px;
                    background-color: white;
                    color: #2c3e50;
                }
            """)
            self._giris_kutusu.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #bdc3c7;
                    border-radius: 8px;
                    padding: 10px;
                    background-color: white;
                    color: #2c3e50;
                }
                QLineEdit:focus {
                    border-color: #3498db;
                }
            """)

    def _temizle(self):
        """Aktif alana göre temizle"""
        if self._sure_odakli and self._sure_girisi:
            self._sure_girisi.clear()
            self.acik_kalma_suresi = 0
        else:
            self._giris_kutusu.clear()

    def _test_kilidi_ac(self):
        """Test amaçlı — doğrulama olmadan kilidi açar"""
        self.dogrulandi = True
        self.releaseKeyboard()
        self.accept()

    def reject(self):
        self.releaseKeyboard()
        super().reject()

    def _kodu_dogrula(self):
        girilen_kod = self._giris_kutusu.text().strip()
        if self._dogrulama_servisi.yaniti_dogrula(self._challenge_kodu, girilen_kod):
            self.dogrulandi = True
            self._hatali_deneme = 0
            self.releaseKeyboard()
            self.accept()
        else:
            self._hatali_deneme += 1
            if self._hatali_deneme >= MAX_DENEME:
                self._challenge_kodu = self._yeni_challenge_uret()
                self._challenge_etiketi.setText(f"Challenge: {self._challenge_kodu}")
                self._hatali_deneme = 0
                self._durum_etiketi.setText("3 hatalı giriş! Yeni kod üretildi.")
            else:
                self._durum_etiketi.setText(f"Yanlış kod! ({self._hatali_deneme}/{MAX_DENEME})")
            self._giris_kutusu.clear()
