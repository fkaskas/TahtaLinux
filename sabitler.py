# -*- coding: utf-8 -*-
"""Uygulama sabitleri"""

import os

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

# Online sunucu ayarları
SUNUCU_URL = "https://kulumtal.com"

# WebView mod geçiş gecikmeleri
OFFLINE_GECIKME_SANIYE = 15   # Bağlantı gidince çevrimdışı moda geçme süresi
ONLINE_GECIKME_SANIYE = 15    # Bağlantı gelince çevrimiçi moda geçme süresi
BASTANGIC_BEKLEME_SANIYE = 15  # Başlangıçta sunucu gelmezse offline geçme süresi
