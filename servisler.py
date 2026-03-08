# -*- coding: utf-8 -*-
"""Challenge-Response doğrulama servisleri"""

import hmac
import hashlib
import random
import time

from sabitler import (
    KILIT_GIZLI_ANAHTAR, KOD_UZUNLUGU,
    YENILEME_ARALIGI_SANIYE, KARAKTERLER
)


class KodUretici:
    """TOTP benzeri challenge kodu üretir"""

    def __init__(self, gizli_anahtar=KILIT_GIZLI_ANAHTAR):
        self._gizli_anahtar = gizli_anahtar

    def _hashi_koda_donustur(self, hash_bytes, uzunluk):
        return "".join(str(b % len(KARAKTERLER)) for b in hash_bytes[:uzunluk])

    def kod_uret(self):
        """Zaman tabanlı challenge kodu üret (her 30 sn değişir)"""
        zaman_indeksi = int(time.time()) // YENILEME_ARALIGI_SANIYE
        hash_girdisi = f"{self._gizli_anahtar}:{zaman_indeksi}"
        h = hmac.new(
            self._gizli_anahtar.encode("utf-8"),
            hash_girdisi.encode("utf-8"),
            hashlib.sha256
        ).digest()
        return self._hashi_koda_donustur(h, KOD_UZUNLUGU)

    def rastgele_kod_uret(self):
        """3 hatalı girişte kullanılacak rastgele challenge kodu"""
        rastgele_sayi = random.randint(1000000, 9999999)
        zaman = time.time_ns()
        hash_girdisi = f"{self._gizli_anahtar}:{rastgele_sayi}:{zaman}"
        h = hmac.new(
            self._gizli_anahtar.encode("utf-8"),
            hash_girdisi.encode("utf-8"),
            hashlib.sha256
        ).digest()
        return self._hashi_koda_donustur(h, KOD_UZUNLUGU)

    def kalan_saniye(self):
        s = time.time()
        return YENILEME_ARALIGI_SANIYE - (s % YENILEME_ARALIGI_SANIYE)


class DogrulamaServisi:
    """Challenge kodundan response kodu üretir ve doğrular"""

    def __init__(self, gizli_anahtar=KILIT_GIZLI_ANAHTAR):
        self._gizli_anahtar = gizli_anahtar

    def yanit_uret(self, dogrulama_kodu):
        birlesmis = f"{dogrulama_kodu}:{self._gizli_anahtar}"
        h = hashlib.sha256(birlesmis.encode("utf-8")).digest()
        return "".join(str(b % len(KARAKTERLER)) for b in h[:KOD_UZUNLUGU])

    def yaniti_dogrula(self, dogrulama_kodu, yanit_kodu):
        return self.yanit_uret(dogrulama_kodu) == yanit_kodu
