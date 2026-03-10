# -*- coding: utf-8 -*-
"""Yerel SQLite veritabanı yönetimi"""

import sqlite3
import os
import threading
import uuid

from sabitler import VERITABANI_YOLU


class VeritabaniYoneticisi:
    """Tahta kilit durumunu yöneten yerel SQLite veritabanı"""

    def __init__(self, db_yolu=None):
        self._db_yolu = db_yolu or VERITABANI_YOLU
        self._kilit = threading.Lock()
        self._baglanti_olustur()
        self._tablo_olustur()

    def _baglanti_olustur(self):
        """Veritabanı bağlantısını oluştur"""
        db_dizini = os.path.dirname(self._db_yolu)
        if db_dizini and not os.path.exists(db_dizini):
            os.makedirs(db_dizini, exist_ok=True)

    def _baglan(self):
        """Thread-safe bağlantı döndür"""
        conn = sqlite3.connect(self._db_yolu)
        conn.row_factory = sqlite3.Row
        return conn

    def _tablo_olustur(self):
        """tahta tablosunu oluştur (yoksa)"""
        with self._kilit:
            conn = self._baglan()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tahta (
                        id TEXT PRIMARY KEY,
                        kurumkodu TEXT NOT NULL,
                        adi TEXT NOT NULL,
                        durum INTEGER NOT NULL DEFAULT 0,
                        ses INTEGER NOT NULL DEFAULT 1,
                        anahtar TEXT NOT NULL DEFAULT '',
                        kurum_adi TEXT NOT NULL DEFAULT '',
                        url TEXT NOT NULL DEFAULT ''
                    )
                """)
                # Mevcut tabloya eksik sütunları ekle
                for sutun in [
                    "anahtar TEXT NOT NULL DEFAULT ''",
                    "kurum_adi TEXT NOT NULL DEFAULT ''",
                    "url TEXT NOT NULL DEFAULT ''",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE tahta ADD COLUMN {sutun}")
                    except sqlite3.OperationalError:
                        pass  # Sütun zaten var
                # Eski tablo varsa verileri taşı
                try:
                    conn.execute("""
                        INSERT INTO tahta (kurumkodu, adi, durum, ses, anahtar)
                        SELECT kurumkodu, adi, durum, ses, anahtar FROM tahta_durum
                        WHERE NOT EXISTS (SELECT 1 FROM tahta WHERE tahta.kurumkodu = tahta_durum.kurumkodu)
                    """)
                    conn.execute("DROP TABLE tahta_durum")
                except sqlite3.OperationalError:
                    pass  # Eski tablo yok
                # Ders çıkış saatleri tablosu
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ders_saatleri (
                        sira INTEGER NOT NULL PRIMARY KEY,
                        saat TEXT NOT NULL DEFAULT ''
                    )
                """)
                # Ayarlar tablosu (ders_saatleri_aktif vb.)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ayarlar (
                        anahtar TEXT PRIMARY KEY,
                        deger TEXT NOT NULL DEFAULT ''
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def tahta_kaydi_al(self, kurumkodu):
        """Kurum koduna göre tahta kaydını getir"""
        with self._kilit:
            conn = self._baglan()
            try:
                satir = conn.execute(
                    "SELECT id, kurumkodu, adi, durum, ses, anahtar, kurum_adi, url FROM tahta WHERE kurumkodu = ?",
                    (kurumkodu,)
                ).fetchone()
                if satir:
                    return dict(satir)
                return None
            except sqlite3.OperationalError:
                return None
            finally:
                conn.close()

    def tahta_kaydi_olustur(self, kurumkodu, adi, durum=0, ses=1, anahtar='', kurum_adi='', url='', tahta_id=None):
        """Yeni tahta kaydı oluştur veya mevcutu güncelle"""
        with self._kilit:
            conn = self._baglan()
            try:
                mevcut = conn.execute(
                    "SELECT id FROM tahta WHERE kurumkodu = ?",
                    (kurumkodu,)
                ).fetchone()
                if mevcut:
                    conn.execute(
                        "UPDATE tahta SET adi = ?, durum = ?, ses = ?, anahtar = ?, kurum_adi = ?, url = ? WHERE kurumkodu = ?",
                        (adi, durum, ses, anahtar, kurum_adi, url, kurumkodu)
                    )
                else:
                    yeni_id = tahta_id or str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO tahta (id, kurumkodu, adi, durum, ses, anahtar, kurum_adi, url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (yeni_id, kurumkodu, adi, durum, ses, anahtar, kurum_adi, url)
                    )
                conn.commit()
            finally:
                conn.close()

    def durum_guncelle(self, kurumkodu, durum):
        """Tahta kilit durumunu güncelle (0=kilitli, 1=açık)"""
        with self._kilit:
            conn = self._baglan()
            try:
                conn.execute(
                    "UPDATE tahta SET durum = ? WHERE kurumkodu = ?",
                    (durum, kurumkodu)
                )
                conn.commit()
            finally:
                conn.close()

    def ses_guncelle(self, kurumkodu, ses):
        """Ses durumunu güncelle (0=kapalı, 1=açık)"""
        with self._kilit:
            conn = self._baglan()
            try:
                conn.execute(
                    "UPDATE tahta SET ses = ? WHERE kurumkodu = ?",
                    (ses, kurumkodu)
                )
                conn.commit()
            finally:
                conn.close()

    def adi_guncelle(self, kurumkodu, yeni_adi):
        """Tahta adını güncelle"""
        with self._kilit:
            conn = self._baglan()
            try:
                conn.execute(
                    "UPDATE tahta SET adi = ? WHERE kurumkodu = ?",
                    (yeni_adi, kurumkodu)
                )
                conn.commit()
            finally:
                conn.close()

    def durum_al(self, kurumkodu):
        """Tahta kilit durumunu getir: 0=kilitli, 1=açık, None=kayıt yok"""
        kayit = self.tahta_kaydi_al(kurumkodu)
        if kayit:
            return kayit["durum"]
        return None

    def ses_al(self, kurumkodu):
        """Ses durumunu getir: 0=kapalı, 1=açık, None=kayıt yok"""
        kayit = self.tahta_kaydi_al(kurumkodu)
        if kayit:
            return kayit["ses"]
        return None

    def anahtar_guncelle(self, kurumkodu, anahtar):
        """Gizli anahtarı güncelle"""
        with self._kilit:
            conn = self._baglan()
            try:
                conn.execute(
                    "UPDATE tahta SET anahtar = ? WHERE kurumkodu = ?",
                    (anahtar, kurumkodu)
                )
                conn.commit()
            finally:
                conn.close()

    def kurumkodu_guncelle(self, eski_kurumkodu, yeni_kurumkodu):
        """Kurum kodunu güncelle"""
        with self._kilit:
            conn = self._baglan()
            try:
                conn.execute(
                    "UPDATE tahta SET kurumkodu = ? WHERE kurumkodu = ?",
                    (yeni_kurumkodu, eski_kurumkodu)
                )
                conn.commit()
            finally:
                conn.close()

    def anahtar_al(self, kurumkodu):
        """Gizli anahtarı getir"""
        kayit = self.tahta_kaydi_al(kurumkodu)
        if kayit:
            return kayit["anahtar"]
        return None

    def url_al(self, kurumkodu):
        """WebView URL'sini getir"""
        kayit = self.tahta_kaydi_al(kurumkodu)
        if kayit:
            return kayit.get("url", "")
        return ""

    def ilk_kaydi_al(self):
        """Tablodaki ilk kaydı getir (kurulum kontrolü için)"""
        with self._kilit:
            conn = self._baglan()
            try:
                satir = conn.execute(
                    "SELECT id, kurumkodu, adi, durum, ses, anahtar, kurum_adi, url FROM tahta LIMIT 1"
                ).fetchone()
                if satir:
                    return dict(satir)
                return None
            except sqlite3.OperationalError:
                return None
            finally:
                conn.close()

    def ders_saatleri_kaydet(self, saatler, aktif):
        """Ders çıkış saatlerini ve aktif durumunu kaydet
        saatler: [{"sira": 1, "saat": "09:40"}, ...]
        aktif: 0 veya 1
        """
        with self._kilit:
            conn = self._baglan()
            try:
                for item in saatler:
                    sira = int(item.get("sira", 0))
                    saat = item.get("saat", "")
                    if sira < 1 or sira > 10:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO ders_saatleri (sira, saat) VALUES (?, ?)",
                        (sira, saat)
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)",
                    ("ders_saatleri_aktif", str(aktif))
                )
                conn.commit()
            finally:
                conn.close()

    def ders_saatleri_al(self):
        """Ders çıkış saatlerini getir. Döndürür: {"aktif": 0/1, "saatler": ["09:40", ...]}"""
        with self._kilit:
            conn = self._baglan()
            try:
                satirlar = conn.execute(
                    "SELECT sira, saat FROM ders_saatleri ORDER BY sira"
                ).fetchall()
                saatler = [dict(s) for s in satirlar] if satirlar else []

                ayar = conn.execute(
                    "SELECT deger FROM ayarlar WHERE anahtar = ?",
                    ("ders_saatleri_aktif",)
                ).fetchone()
                aktif = int(ayar["deger"]) if ayar else 0

                return {"aktif": aktif, "saatler": saatler}
            except sqlite3.OperationalError:
                return {"aktif": 0, "saatler": []}
            finally:
                conn.close()
