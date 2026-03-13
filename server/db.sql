-- Tahta Kilit Online Sistem - MySQL Veritabanı Şeması
-- Bu dosyayı MySQL'de çalıştırarak veritabanını oluşturabilirsiniz.
-- Uygulama ilk çalıştırıldığında tabloları otomatik oluşturur.

CREATE DATABASE IF NOT EXISTS tahta_kilit CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE tahta_kilit;

-- Kurumlar tablosu
CREATE TABLE IF NOT EXISTS kurumlar (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kurum_kodu VARCHAR(20) NOT NULL UNIQUE,
    kurum_adi VARCHAR(255) NOT NULL,
    ders_saatleri_aktif TINYINT NOT NULL DEFAULT 0, -- 0=pasif, 1=aktif
    otomasyon_aktif TINYINT NOT NULL DEFAULT 0,     -- 0=pasif, 1=aktif (kapı otomasyon)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Tahtalar tablosu (kurumla ilişkili)
CREATE TABLE IF NOT EXISTS tahtalar (
    id VARCHAR(36) PRIMARY KEY,          -- Tahta kurulumunda üretilen UUID
    kurum_id INT NOT NULL,
    tahta_adi VARCHAR(255) NOT NULL DEFAULT '',
    durum TINYINT NOT NULL DEFAULT 0,    -- 0=açık, 1=kilitli
    ses TINYINT NOT NULL DEFAULT 1,      -- 0=kapalı, 1=açık
    cevrimici TINYINT NOT NULL DEFAULT 0,-- 0=çevrimdışı, 1=çevrimiçi
    ip_adresi VARCHAR(45) DEFAULT NULL,
    anahtar VARCHAR(255) NOT NULL DEFAULT '',  -- Doğrulama gizli anahtarı
    son_baglanti TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Kullanıcılar tablosu (kurumla ilişkili, roller: superadmin, yonetici, ogretmen)
CREATE TABLE IF NOT EXISTS kullanicilar (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kurum_id INT NOT NULL,
    kullanici_adi VARCHAR(100) NOT NULL UNIQUE,
    sifre_hash VARCHAR(255) NOT NULL,
    ad_soyad VARCHAR(255) NOT NULL,
    rol ENUM('superadmin', 'yonetici', 'ogretmen') NOT NULL DEFAULT 'ogretmen',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Ders çıkış saatleri tablosu (kurumla ilişkili, 10 saat)
CREATE TABLE IF NOT EXISTS ders_saatleri (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kurum_id INT NOT NULL,
    sira TINYINT NOT NULL,               -- 1-10 arası ders sırası
    saat VARCHAR(5) NOT NULL DEFAULT '',  -- HH:MM formatında
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unik_kurum_sira (kurum_id, sira),
    FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Ayın öğrencileri tablosu (kurumla ilişkili)
CREATE TABLE IF NOT EXISTS ayin_ogrencileri (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kurum_id INT NOT NULL,
    ekleyen_id INT NOT NULL,
    sira TINYINT NOT NULL DEFAULT 1,          -- 1=birinci, 2=ikinci, 3=üçüncü, 4=dördüncü
    ad_soyad VARCHAR(255) NOT NULL,
    sinif VARCHAR(50) NOT NULL DEFAULT '',     -- Örn: 9-A
    odul VARCHAR(255) NOT NULL DEFAULT '',     -- Örn: Matematik Başarı Ödülü
    aciklama TEXT DEFAULT NULL,
    foto_url VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unik_kurum_sira (kurum_id, sira),
    FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
    FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- İşlem kayıtları (loglar) tablosu — kurum özelinde max 1 aylık tutulur
CREATE TABLE IF NOT EXISTS tahta_loglari (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    kurum_id INT NOT NULL,
    tahta_id VARCHAR(36) DEFAULT NULL,
    tahta_adi VARCHAR(255) NOT NULL DEFAULT '',
    kullanici_id INT DEFAULT NULL,
    kullanici_adi VARCHAR(100) NOT NULL DEFAULT '',
    ad_soyad VARCHAR(255) NOT NULL DEFAULT '',
    rol ENUM('superadmin', 'yonetici', 'ogretmen') NOT NULL DEFAULT 'ogretmen',
    aksiyon ENUM('kilitle','kilidi_ac','ses_kapat','ses_ac','tahta_kapat','tumu_kilitle','tumu_ac','tumu_kapat') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kurum_created (kurum_id, created_at),
    INDEX idx_tahta (tahta_id),
    FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Günün sözleri tablosu (kurumla ilişkili)
CREATE TABLE IF NOT EXISTS gunun_sozleri (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kurum_id INT NOT NULL,
    ekleyen_id INT NOT NULL,
    soz TEXT NOT NULL,
    yazar VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
    FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
) ENGINE=InnoDB;
