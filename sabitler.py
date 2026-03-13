# -*- coding: utf-8 -*-
"""Uygulama sabitleri"""

import os
import sys

# PyInstaller binary modunda _MEIPASS kullanılır
if getattr(sys, 'frozen', False):
    BETIK_DIZINI = sys._MEIPASS
else:
    BETIK_DIZINI = os.path.dirname(os.path.abspath(__file__))

KILIT_GIZLI_ANAHTAR = "tahta_ekran_secret_2024"
KOD_UZUNLUGU = 4
YENILEME_ARALIGI_SANIYE = 30
KARAKTERLER = "0123456789"
MAX_DENEME = 3

# Veritabanı ayarları
# Servis (root) olarak çalışırsa korumalı dizini, test modunda yerel dizini kullan
if os.geteuid() == 0:
    VERITABANI_YOLU = "/var/lib/tahta-kilit/tahta_kilit.db"
else:
    VERITABANI_YOLU = os.path.join(BETIK_DIZINI, "tahta_kilit.db")
VARSAYILAN_KURUM_KODU = "755555"
VARSAYILAN_TAHTA_ADI = "11E"

# Cache dosyası (kurum sayfası HTML cache'i)
if os.geteuid() == 0:
    CACHE_HTML_YOLU = "/var/lib/tahta-kilit/kurum_cache.html"
else:
    CACHE_HTML_YOLU = os.path.join(BETIK_DIZINI, "kurum_cache.html")

# Online sunucu ayarları
SUNUCU_URL = "https://kulumtal.com"
