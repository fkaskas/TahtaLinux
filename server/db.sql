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
