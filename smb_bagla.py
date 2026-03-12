# -*- coding: utf-8 -*-
"""SMB Ağ Paylaşımı Bağlama Penceresi — fstab ile kalıcı mount işlemi yapar"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QPushButton, QLabel, QMessageBox, QFileDialog,
                             QHBoxLayout, QCheckBox, QComboBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import subprocess
import os
import re


class SmbBaglamaPenceresi(QDialog):
    """SMB ağ paylaşımını fstab ile kalıcı olarak mount eden pencere"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tahta Kilit — Ağ Klasörü Bağlama (SMB)")
        self.setFixedSize(500, 650)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self._arayuz_olustur()

    def _arayuz_olustur(self):
        ana = QVBoxLayout()

        baslik = QLabel("Ağ Klasörü Bağlama (SMB/CIFS)")
        baslik.setFont(QFont("Sans", 14, QFont.Bold))
        baslik.setAlignment(Qt.AlignCenter)
        baslik.setStyleSheet("color: #2196F3; margin-bottom: 5px;")
        ana.addWidget(baslik)

        aciklama = QLabel(
            "SMB paylaşımını kalıcı olarak bağlamak için\n"
            "aşağıdaki bilgileri doldurun.\n"
            "Sistem her açıldığında otomatik bağlanacaktır."
        )
        aciklama.setAlignment(Qt.AlignCenter)
        aciklama.setStyleSheet("color: #666; margin-bottom: 10px;")
        ana.addWidget(aciklama)

        form = QFormLayout()

        # Sunucu IP
        self._sunucu_girdi = QLineEdit()
        self._sunucu_girdi.setPlaceholderText("Örn: 192.168.1.100")
        self._sunucu_girdi.setMinimumHeight(35)
        self._sunucu_girdi.setContextMenuPolicy(Qt.NoContextMenu)
        form.addRow("Sunucu IP:", self._sunucu_girdi)

        # Paylaşım adı
        self._paylasim_girdi = QLineEdit()
        self._paylasim_girdi.setPlaceholderText("Örn: video")
        self._paylasim_girdi.setMinimumHeight(35)
        self._paylasim_girdi.setContextMenuPolicy(Qt.NoContextMenu)
        form.addRow("Paylaşım Adı:", self._paylasim_girdi)

        # Kullanıcı adı
        self._kullanici_girdi = QLineEdit()
        self._kullanici_girdi.setPlaceholderText("Örn: admin")
        self._kullanici_girdi.setMinimumHeight(35)
        self._kullanici_girdi.setContextMenuPolicy(Qt.NoContextMenu)
        form.addRow("Kullanıcı Adı:", self._kullanici_girdi)

        # Şifre
        self._sifre_girdi = QLineEdit()
        self._sifre_girdi.setPlaceholderText("Şifre")
        self._sifre_girdi.setEchoMode(QLineEdit.Password)
        self._sifre_girdi.setMinimumHeight(35)
        self._sifre_girdi.setContextMenuPolicy(Qt.NoContextMenu)
        form.addRow("Şifre:", self._sifre_girdi)

        # Mount noktası
        mount_layout = QHBoxLayout()
        self._mount_girdi = QLineEdit()
        self._mount_girdi.setText("/mnt/video")
        self._mount_girdi.setMinimumHeight(35)
        self._mount_girdi.setContextMenuPolicy(Qt.NoContextMenu)
        mount_layout.addWidget(self._mount_girdi)

        sec_btn = QPushButton("Seç...")
        sec_btn.setMinimumHeight(35)
        sec_btn.setMaximumWidth(60)
        sec_btn.clicked.connect(self._klasor_sec)
        mount_layout.addWidget(sec_btn)

        form.addRow("Mount Noktası:", mount_layout)

        # SMB sürümü
        self._surum_combo = QComboBox()
        self._surum_combo.addItems(["Otomatik", "3.0", "3.1.1", "2.1", "2.0", "1.0"])
        self._surum_combo.setMinimumHeight(35)
        form.addRow("SMB Sürümü:", self._surum_combo)

        # Kimlik doğrulama yöntemi
        self._sec_combo = QComboBox()
        self._sec_combo.addItems(["ntlmssp", "ntlmv2", "ntlm", "krb5", "none"])
        self._sec_combo.setMinimumHeight(35)
        form.addRow("Kimlik Doğrulama:", self._sec_combo)

        # Domain/Workgroup
        self._domain_girdi = QLineEdit()
        self._domain_girdi.setPlaceholderText("Örn: WORKGROUP (boş bırakılabilir)")
        self._domain_girdi.setMinimumHeight(35)
        self._domain_girdi.setContextMenuPolicy(Qt.NoContextMenu)
        form.addRow("Domain/Workgroup:", self._domain_girdi)

        # Misafir erişimi
        self._misafir_cb = QCheckBox("Misafir erişimi (kullanıcı/şifre gerekmez)")
        self._misafir_cb.toggled.connect(self._misafir_degisti)
        form.addRow("", self._misafir_cb)

        ana.addLayout(form)
        ana.addSpacing(10)

        # Bilgi etiketi
        self._bilgi_label = QLabel("")
        self._bilgi_label.setAlignment(Qt.AlignCenter)
        self._bilgi_label.setWordWrap(True)
        ana.addWidget(self._bilgi_label)

        # Butonlar
        btn_layout = QHBoxLayout()

        bagla_btn = QPushButton("Bağla ve Kaydet")
        bagla_btn.setMinimumHeight(40)
        bagla_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; color: white;
                border: none; border-radius: 5px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #388E3C; }
        """)
        bagla_btn.clicked.connect(self._bagla)
        btn_layout.addWidget(bagla_btn)

        kaldir_btn = QPushButton("Mevcut Bağlantıyı Kaldır")
        kaldir_btn.setMinimumHeight(40)
        kaldir_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336; color: white;
                border: none; border-radius: 5px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #D32F2F; }
        """)
        kaldir_btn.clicked.connect(self._kaldir)
        btn_layout.addWidget(kaldir_btn)

        ana.addLayout(btn_layout)

        kapat_btn = QPushButton("Kapat")
        kapat_btn.setMinimumHeight(35)
        kapat_btn.setStyleSheet("""
            QPushButton {
                background-color: #9E9E9E; color: white;
                border: none; border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #757575; }
        """)
        kapat_btn.clicked.connect(self.reject)
        ana.addWidget(kapat_btn)

        self.setLayout(ana)

        # Mevcut fstab ayarını yükle
        self._mevcut_ayari_yukle()

    def _misafir_degisti(self, checked):
        self._kullanici_girdi.setEnabled(not checked)
        self._sifre_girdi.setEnabled(not checked)
        if checked:
            self._kullanici_girdi.clear()
            self._sifre_girdi.clear()

    def _klasor_sec(self):
        dizin = QFileDialog.getExistingDirectory(self, "Mount Noktası Seçin", "/mnt")
        if dizin:
            self._mount_girdi.setText(dizin)

    def _mevcut_ayari_yukle(self):
        """fstab'da mevcut CIFS mount varsa bilgileri yükle"""
        try:
            with open("/etc/fstab", "r") as f:
                for satir in f:
                    satir = satir.strip()
                    if satir.startswith("#") or not satir:
                        continue
                    if "cifs" in satir and "# tahta-smb" in satir:
                        parcalar = satir.split()
                        if len(parcalar) >= 2:
                            kaynak = parcalar[0]  # //IP/paylasim
                            mount = parcalar[1]
                            # IP ve paylaşım adını ayıkla
                            eslesme = re.match(r"//([^/]+)/(.+)", kaynak)
                            if eslesme:
                                self._sunucu_girdi.setText(eslesme.group(1))
                                self._paylasim_girdi.setText(eslesme.group(2))
                            self._mount_girdi.setText(mount)
                            # Seçeneklerden kullanıcı adını çıkar
                            if len(parcalar) >= 4:
                                secenekler = parcalar[3]
                                for s in secenekler.split(","):
                                    if s.startswith("username="):
                                        self._kullanici_girdi.setText(s.split("=", 1)[1])
                                    elif s == "guest":
                                        self._misafir_cb.setChecked(True)
                            self._bilgi_label.setText("ℹ️ Mevcut SMB bağlantısı bulundu.")
                            self._bilgi_label.setStyleSheet("color: #2196F3;")
                        break
        except PermissionError:
            pass

    def _dogrula(self):
        """Girdi doğrulaması"""
        sunucu = self._sunucu_girdi.text().strip()
        paylasim = self._paylasim_girdi.text().strip()
        mount = self._mount_girdi.text().strip()

        if not sunucu:
            QMessageBox.warning(self, "Uyarı", "Sunucu IP adresi boş bırakılamaz!")
            return False
        if not paylasim:
            QMessageBox.warning(self, "Uyarı", "Paylaşım adı boş bırakılamaz!")
            return False
        if not mount:
            QMessageBox.warning(self, "Uyarı", "Mount noktası boş bırakılamaz!")
            return False
        if not mount.startswith("/"):
            QMessageBox.warning(self, "Uyarı", "Mount noktası mutlak yol olmalıdır! (/ ile başlamalı)")
            return False

        if not self._misafir_cb.isChecked():
            kullanici = self._kullanici_girdi.text().strip()
            if not kullanici:
                QMessageBox.warning(self, "Uyarı", "Kullanıcı adı boş bırakılamaz!\nMisafir erişimi için kutucuğu işaretleyin.")
                return False

        return True

    def _bagla(self):
        """fstab'a ekle ve mount et"""
        if not self._dogrula():
            return

        sunucu = self._sunucu_girdi.text().strip()
        paylasim = self._paylasim_girdi.text().strip()
        mount = self._mount_girdi.text().strip()
        kullanici = self._kullanici_girdi.text().strip()
        sifre = self._sifre_girdi.text().strip()
        misafir = self._misafir_cb.isChecked()

        # SMB sürümü
        surum = self._surum_combo.currentText()
        surum_param = "" if surum == "Otomatik" else f",vers={surum}"

        # Kimlik doğrulama
        sec = self._sec_combo.currentText()
        sec_param = f",sec={sec}"

        # Domain
        domain = self._domain_girdi.text().strip()
        domain_param = f",domain={domain}" if domain else ""

        # Seçenekleri oluştur
        if misafir:
            secenekler = f"guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777,nofail,_netdev,x-systemd.automount,x-systemd.after=network-online.target{surum_param}{sec_param}{domain_param}"
        else:
            secenekler = f"username={kullanici},password={sifre},uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777,nofail,_netdev,x-systemd.automount,x-systemd.after=network-online.target{surum_param}{sec_param}{domain_param}"

        fstab_satir = f"//{sunucu}/{paylasim}  {mount}  cifs  {secenekler}  0  0  # tahta-smb"

        try:
            # cifs-utils kurulu mu kontrol et
            sonuc = subprocess.run(["dpkg", "-s", "cifs-utils"],
                                   capture_output=True, text=True)
            if sonuc.returncode != 0:
                self._bilgi_label.setText("⏳ cifs-utils kuruluyor...")
                self._bilgi_label.setStyleSheet("color: #FF9800;")
                self._bilgi_label.repaint()
                subprocess.run(["pkexec", "apt", "install", "-y", "cifs-utils"],
                               check=True, capture_output=True, text=True)

            # Mount noktasını oluştur
            subprocess.run(["pkexec", "mkdir", "-p", mount],
                           check=True, capture_output=True, text=True)

            # Önce doğrudan mount dene (hata mesajı daha ayrıntılı)
            kaynak = f"//{sunucu}/{paylasim}"
            mount_sonuc = subprocess.run(
                ["pkexec", "mount", "-t", "cifs", kaynak, mount, "-o", secenekler.replace(',_netdev', '').replace(',x-systemd.automount', '').replace(',x-systemd.after=network-online.target', '').replace(',nofail', '')],
                capture_output=True, text=True
            )

            if mount_sonuc.returncode != 0:
                # Mount başarısız — ayrıntılı hata göster ama fstab'a yine de kaydet
                hata_mesaj = mount_sonuc.stderr.strip()
                cevap = QMessageBox.question(
                    self, "Mount Başarısız",
                    f"Doğrudan mount başarısız oldu:\n\n{hata_mesaj}\n\n"
                    f"Komut: mount -t cifs {kaynak} {mount}\n\n"
                    f"Yine de fstab'a kaydedilsin mi?\n"
                    f"(Yeniden başlatıldığında çalışabilir)",
                    QMessageBox.Yes | QMessageBox.No
                )
                if cevap == QMessageBox.Yes:
                    self._fstab_guncelle(fstab_satir)
                    self._bilgi_label.setText(f"⚠️ fstab'a kaydedildi ama mount şu an başarısız.")
                    self._bilgi_label.setStyleSheet("color: #FF9800; font-weight: bold;")
                else:
                    self._bilgi_label.setText(f"❌ Mount başarısız. Farklı seçenekler deneyin.")
                    self._bilgi_label.setStyleSheet("color: #f44336; font-weight: bold;")
                return

            # Mount başarılı — fstab'a kaydet
            self._fstab_guncelle(fstab_satir)

            self._bilgi_label.setText(f"✅ Başarılı! {mount} bağlandı.\nHer açılışta otomatik bağlanacak.")
            self._bilgi_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

            QMessageBox.information(self, "Başarılı",
                                    f"SMB paylaşımı başarıyla bağlandı!\n\n"
                                    f"Kaynak:  //{sunucu}/{paylasim}\n"
                                    f"Hedef:   {mount}\n\n"
                                    f"Sistem her açıldığında otomatik bağlanacaktır.")

        except subprocess.CalledProcessError as e:
            hata = e.stderr if e.stderr else str(e)
            self._bilgi_label.setText(f"❌ Hata oluştu!")
            self._bilgi_label.setStyleSheet("color: #f44336; font-weight: bold;")
            QMessageBox.critical(self, "Hata",
                                 f"Bağlama işlemi başarısız!\n\n{hata}")

    def _fstab_guncelle(self, yeni_satir):
        """fstab dosyasını güvenli şekilde güncelle"""
        # Geçici dosya ile güncelle
        import tempfile
        fstab_icerik = ""
        try:
            with open("/etc/fstab", "r") as f:
                fstab_icerik = f.read()
        except PermissionError:
            # pkexec ile oku
            sonuc = subprocess.run(["cat", "/etc/fstab"],
                                   capture_output=True, text=True)
            fstab_icerik = sonuc.stdout

        # Eski tahta-smb satırlarını kaldır
        satirlar = []
        for satir in fstab_icerik.splitlines():
            if "# tahta-smb" not in satir:
                satirlar.append(satir)

        # Yeni satırı ekle
        satirlar.append(yeni_satir)

        yeni_icerik = "\n".join(satirlar) + "\n"

        # Geçici dosyaya yaz, pkexec ile taşı
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fstab',
                                          delete=False) as tmp:
            tmp.write(yeni_icerik)
            tmp_yol = tmp.name

        try:
            subprocess.run(["pkexec", "cp", tmp_yol, "/etc/fstab"],
                           check=True, capture_output=True, text=True)
            # systemd automount birimlerini yeniden yükle
            subprocess.run(["pkexec", "systemctl", "daemon-reload"],
                           capture_output=True, text=True)
            # remote-fs.target etkinleştir (ağ dosya sistemleri için)
            subprocess.run(["pkexec", "systemctl", "enable", "remote-fs.target"],
                           capture_output=True, text=True)
        finally:
            os.unlink(tmp_yol)

    def _kaldir(self):
        """fstab'dan tahta-smb satırını kaldır ve umount et"""
        cevap = QMessageBox.question(
            self, "Onay",
            "Mevcut SMB bağlantısı kaldırılsın mı?\nfstab'dan silinecek ve umount edilecektir.",
            QMessageBox.Yes | QMessageBox.No
        )
        if cevap != QMessageBox.Yes:
            return

        try:
            mount = self._mount_girdi.text().strip()

            # Önce umount et
            if mount:
                subprocess.run(["pkexec", "umount", mount],
                               capture_output=True, text=True)

            # fstab'dan tahta-smb satırını kaldır
            fstab_icerik = ""
            try:
                with open("/etc/fstab", "r") as f:
                    fstab_icerik = f.read()
            except PermissionError:
                sonuc = subprocess.run(["cat", "/etc/fstab"],
                                       capture_output=True, text=True)
                fstab_icerik = sonuc.stdout

            satirlar = []
            kaldirildi = False
            for satir in fstab_icerik.splitlines():
                if "# tahta-smb" in satir:
                    kaldirildi = True
                else:
                    satirlar.append(satir)

            if kaldirildi:
                import tempfile
                yeni_icerik = "\n".join(satirlar) + "\n"
                with tempfile.NamedTemporaryFile(mode='w', suffix='.fstab',
                                                  delete=False) as tmp:
                    tmp.write(yeni_icerik)
                    tmp_yol = tmp.name

                try:
                    subprocess.run(["pkexec", "cp", tmp_yol, "/etc/fstab"],
                                   check=True, capture_output=True, text=True)
                finally:
                    os.unlink(tmp_yol)

                self._bilgi_label.setText("✅ SMB bağlantısı kaldırıldı.")
                self._bilgi_label.setStyleSheet("color: #4CAF50;")
                self._sunucu_girdi.clear()
                self._paylasim_girdi.clear()
                self._kullanici_girdi.clear()
                self._sifre_girdi.clear()
                self._mount_girdi.setText("/mnt/video")
                self._misafir_cb.setChecked(False)

                QMessageBox.information(self, "Başarılı",
                                        "SMB bağlantısı başarıyla kaldırıldı.")
            else:
                QMessageBox.information(self, "Bilgi",
                                        "fstab'da Tahta SMB bağlantısı bulunamadı.")

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Hata", f"Kaldırma başarısız!\n\n{e.stderr}")


def smb_penceresi_ac(parent=None):
    """Dışarıdan çağırmak için yardımcı fonksiyon"""
    pencere = SmbBaglamaPenceresi(parent)
    return pencere.exec_()


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    pencere = SmbBaglamaPenceresi()
    pencere.show()
    sys.exit(app.exec_())
