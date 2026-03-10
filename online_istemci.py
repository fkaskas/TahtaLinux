# -*- coding: utf-8 -*-
"""Socket.IO istemcisi — sunucuyla gerçek zamanlı iletişim"""

import threading
import time
import socketio
from PyQt5.QtCore import QObject, pyqtSignal

from sabitler import SUNUCU_URL


class OnlineIstemci(QObject):
    """Sunucuya Socket.IO ile bağlanıp komutları PyQt sinyalleri olarak yayar"""

    # Sinyaller (ana thread'de güvenli şekilde işlenmesi için)
    kilitle_sinyali = pyqtSignal()
    kilidi_ac_sinyali = pyqtSignal()
    ses_kapat_sinyali = pyqtSignal()
    ses_ac_sinyali = pyqtSignal()
    baglanti_durumu_sinyali = pyqtSignal(bool)  # True=bağlı, False=koptu
    hata_sinyali = pyqtSignal(str)  # Sunucudan gelen hata mesajı
    durum_bilgisi_sinyali = pyqtSignal(int, int)  # durum, ses
    ders_saatleri_sinyali = pyqtSignal(dict)  # {"aktif": 0/1, "saatler": [...]}
    tahta_adi_sinyali = pyqtSignal(str)  # Sunucudan gelen yeni tahta adı

    def __init__(self, kurum_kodu, tahta_adi, tahta_id="", anahtar="", parent=None):
        super().__init__(parent)
        self._kurum_kodu = kurum_kodu
        self._tahta_adi = tahta_adi
        self._tahta_id = tahta_id
        self._anahtar = anahtar
        self._aktif = False
        self._durum = 1   # 1=kilitli, 0=açık (sunucu formatı)
        self._ses = 1     # 1=açık, 0=kapalı
        self._sio = None

    def _yeni_istemci_olustur(self):
        """Her bağlantı denemesinde temiz bir socketio.Client oluştur"""
        sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,  # Sınırsız deneme
            reconnection_delay=1,
            reconnection_delay_max=5,
            logger=False,
            engineio_logger=False,
        )

        @sio.event
        def connect():
            print("[ONLİNE] Sunucuya bağlandı")
            sio.emit("tahta_kayit", {
                "kurumKodu": self._kurum_kodu,
                "tahtaAdi": self._tahta_adi,
                "tahtaId": self._tahta_id,
                "durum": self._durum,
                "ses": self._ses,
                "anahtar": self._anahtar,
            })
            self.baglanti_durumu_sinyali.emit(True)

        @sio.event
        def disconnect():
            print("[ONLİNE] Sunucu bağlantısı koptu")
            self.baglanti_durumu_sinyali.emit(False)

        @sio.on("komut")
        def komut_geldi(veri):
            aksiyon = veri.get("aksiyon", "")
            if aksiyon == "kilitle":
                self.kilitle_sinyali.emit()
            elif aksiyon == "kilidi_ac":
                self.kilidi_ac_sinyali.emit()
            elif aksiyon == "ses_kapat":
                self.ses_kapat_sinyali.emit()
            elif aksiyon == "ses_ac":
                self.ses_ac_sinyali.emit()

        @sio.on("hata")
        def hata_geldi(veri):
            mesaj = veri.get("mesaj", "Bilinmeyen hata")
            print(f"[ONLİNE] Sunucu hatası: {mesaj}")
            self.hata_sinyali.emit(mesaj)

        @sio.on("durum_bilgisi")
        def durum_geldi(veri):
            durum = veri.get("durum", 0)
            ses = veri.get("ses", 1)
            self._durum = durum
            self._ses = ses
            self.durum_bilgisi_sinyali.emit(durum, ses)
            tahta_adi = veri.get("tahta_adi", "")
            if tahta_adi:
                self.tahta_adi_sinyali.emit(tahta_adi)

        @sio.on("ders_saatleri")
        def ders_saatleri_geldi(veri):
            if isinstance(veri, dict):
                self.ders_saatleri_sinyali.emit(veri)

        @sio.on("tahta_adi_guncellendi")
        def tahta_adi_geldi(veri):
            yeni_adi = veri.get("tahta_adi", "")
            if yeni_adi:
                self.tahta_adi_sinyali.emit(yeni_adi)

        return sio

    def baslat(self):
        """Arka planda sunucuya bağlan"""
        if self._aktif:
            return
        self._aktif = True
        t = threading.Thread(target=self._baglan, daemon=True)
        t.start()

    def _baglan(self):
        """Bağlantıyı kur — koparsa hemen yeniden bağlan"""
        while self._aktif:
            try:
                # Her denemede temiz bir istemci oluştur
                self._sio = self._yeni_istemci_olustur()
                print(f"[ONLİNE] Bağlanılıyor: {SUNUCU_URL}")
                self._sio.connect(
                    SUNUCU_URL,
                    transports=["polling", "websocket"],
                    wait_timeout=10,
                )
                self._sio.wait()  # Bağlantı tamamen kopana kadar bekle
            except Exception as e:
                print(f"[ONLİNE] Bağlantı hatası: {e}")

            # Eski istemciyi temizle
            try:
                if self._sio and self._sio.connected:
                    self._sio.disconnect()
            except Exception:
                pass

            if not self._aktif:
                return
            self.baglanti_durumu_sinyali.emit(False)
            time.sleep(1)  # Sunucuyu yormamak için minimum bekleme

    def durdur(self):
        """Bağlantıyı kapat"""
        self._aktif = False
        try:
            if self._sio:
                self._sio.disconnect()
        except Exception:
            pass

    def durum_bildir(self, durum, ses):
        """Tahtanın güncel durumunu sunucuya bildir"""
        self._durum = durum
        self._ses = ses
        if self._sio and self._sio.connected:
            self._sio.emit("tahta_durum_guncelle", {"durum": durum, "ses": ses})

    def kapanma_bildir(self, kalan_saniye):
        """Tahtanın kapanma geri sayımını sunucuya bildir"""
        if self._sio and self._sio.connected:
            self._sio.emit("kapanma_geri_sayim", {"kalan": kalan_saniye})

    def kilit_bildir(self, kalan_saniye):
        """Kilidin aktifleşmesine kalan süreyi sunucuya bildir"""
        if self._sio and self._sio.connected:
            self._sio.emit("kilit_geri_sayim", {"kalan": kalan_saniye})

    @property
    def bagli(self):
        return self._sio is not None and self._sio.connected
