const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");
const fs = require("fs");
const mysql = require("mysql2/promise");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const crypto = require("crypto");
const multer = require("multer");

// ===================== Fotoğraf Yükleme =====================
const UPLOAD_DIR = path.join(__dirname, "public", "uploads", "ayin");
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const ayinStorage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, UPLOAD_DIR),
  filename: (req, file, cb) => {
    const uzanti = path.extname(file.originalname).toLowerCase();
    const benzersiz = Date.now() + '-' + crypto.randomBytes(6).toString('hex');
    cb(null, benzersiz + uzanti);
  }
});
const ayinUpload = multer({
  storage: ayinStorage,
  limits: { fileSize: 5 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const izinli = ['.jpg', '.jpeg', '.png', '.webp'];
    const uzanti = path.extname(file.originalname).toLowerCase();
    if (izinli.includes(uzanti)) cb(null, true);
    else cb(new Error('Sadece JPG, PNG ve WebP formatları kabul edilir'));
  }
});

// ---- Bulmaca Görsel Yükleme ----
const BULMACA_UPLOAD_DIR = path.join(__dirname, "public", "uploads", "bulmaca");
if (!fs.existsSync(BULMACA_UPLOAD_DIR)) fs.mkdirSync(BULMACA_UPLOAD_DIR, { recursive: true });

const bulmacaStorage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, BULMACA_UPLOAD_DIR),
  filename: (req, file, cb) => {
    const uzanti = path.extname(file.originalname).toLowerCase();
    const benzersiz = Date.now() + '-' + crypto.randomBytes(6).toString('hex');
    cb(null, benzersiz + uzanti);
  }
});
const bulmacaUpload = multer({
  storage: bulmacaStorage,
  limits: { fileSize: 2 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const izinli = ['.jpg', '.jpeg', '.png', '.webp'];
    const uzanti = path.extname(file.originalname).toLowerCase();
    if (izinli.includes(uzanti)) cb(null, true);
    else cb(new Error('Sadece JPG, PNG ve WebP formatları kabul edilir'));
  }
});

// ---- Slider Yükleme ----
const SLIDER_UPLOAD_DIR = path.join(__dirname, "public", "uploads", "slider");
if (!fs.existsSync(SLIDER_UPLOAD_DIR)) fs.mkdirSync(SLIDER_UPLOAD_DIR, { recursive: true });

const sliderStorage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, SLIDER_UPLOAD_DIR),
  filename: (req, file, cb) => {
    const uzanti = path.extname(file.originalname).toLowerCase();
    const benzersiz = Date.now() + '-' + crypto.randomBytes(6).toString('hex');
    cb(null, benzersiz + uzanti);
  }
});
const sliderUpload = multer({
  storage: sliderStorage,
  limits: { fileSize: 5 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const izinli = ['.jpg', '.jpeg', '.png', '.webp'];
    const uzanti = path.extname(file.originalname).toLowerCase();
    if (izinli.includes(uzanti)) cb(null, true);
    else cb(new Error('Sadece JPG, PNG ve WebP formatları kabul edilir'));
  }
});

// ===================== Yapılandırma =====================
const JWT_SECRET = process.env.JWT_SECRET || "tahta-kilit-gizli-anahtar-2024";

// İzin verilen ek origin'ler: ALLOWED_ORIGINS=https://panel.okul.com,https://panel2.com
// Boş bırakılırsa sadece aynı sunucudan çalışan panel (same-origin) izinlidir.
// Python tahta istemcileri tarayıcı olmadığından CORS kuralı uygulanmaz.
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(",").map((s) => s.trim()).filter(Boolean)
  : [];

function corsOriginKontrol(origin, callback) {
  // Origin başlığı yoksa: desktop istemci (Python tahta) — izin ver
  if (!origin) return callback(null, true);
  // Sunucunun kendi adresi (panel.html same-origin bağlantısı) — izin ver
  const PORT = process.env.PORT || 3000;
  const kendiOriginler = [
    `http://localhost:${PORT}`,
    `http://127.0.0.1:${PORT}`,
    "https://kulumtal.com",
    "https://www.kulumtal.com",
  ];
  if (process.env.SERVER_URL) kendiOriginler.push(process.env.SERVER_URL.replace(/\/$/, ""));
  if (kendiOriginler.includes(origin)) return callback(null, true);
  if (ALLOWED_ORIGINS.includes(origin)) return callback(null, true);
  callback(new Error(`CORS: ${origin} origin'ine izin verilmiyor`));
}
const DB_CONFIG = {
  host: process.env.DB_HOST || "localhost",
  user: process.env.DB_USER || "root",
  password: process.env.DB_PASS || "",
  database: process.env.DB_NAME || "tahta_kilit",
  waitForConnections: true,
  connectionLimit: 10,
  charset: "utf8mb4",
  dateStrings: ["DATE"],
};

const app = express();
app.set("trust proxy", true);
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: corsOriginKontrol, methods: ["GET", "POST"] },
  pingInterval: 10000,
  pingTimeout: 5000,
});

app.use(express.json());

let db;

// ===================== Veritabanı Başlatma =====================
async function veritabaniBaslat() {
  db = await mysql.createPool(DB_CONFIG);

  await db.execute(`
    CREATE TABLE IF NOT EXISTS kurumlar (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_kodu VARCHAR(20) NOT NULL UNIQUE,
      kurum_adi VARCHAR(255) NOT NULL,
      anahtar VARCHAR(255) NOT NULL DEFAULT '',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
  `);

  // Mevcut kurumlar tablosuna anahtar sütunu ekle (yoksa)
  try {
    await db.execute(`ALTER TABLE kurumlar ADD COLUMN anahtar VARCHAR(255) NOT NULL DEFAULT ''`);
  } catch (e) { /* sütun zaten var */ }

  // Anahtarı olmayan kurumlara otomatik anahtar üret
  try {
    const [anahtarsizKurumlar] = await db.execute("SELECT id FROM kurumlar WHERE anahtar = ''");
    for (const k of anahtarsizKurumlar) {
      const yeniAnahtar = crypto.randomBytes(32).toString('hex');
      await db.execute("UPDATE kurumlar SET anahtar = ? WHERE id = ?", [yeniAnahtar, k.id]);
      console.log(`[ANAHTAR] Kurum #${k.id} için anahtar üretildi`);
    }
  } catch (e) { console.error('Kurum anahtarı üretme hatası:', e); }

  await db.execute(`
    CREATE TABLE IF NOT EXISTS tahtalar (
      id VARCHAR(36) PRIMARY KEY,
      kurum_id INT NOT NULL,
      tahta_adi VARCHAR(255) NOT NULL DEFAULT '',
      durum TINYINT NOT NULL DEFAULT 0,
      ses TINYINT NOT NULL DEFAULT 1,
      cevrimici TINYINT NOT NULL DEFAULT 0,
      ip_adresi VARCHAR(45) DEFAULT NULL,
      anahtar VARCHAR(255) NOT NULL DEFAULT '',
      son_baglanti TIMESTAMP NULL DEFAULT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Mevcut tabloya anahtar sütununu ekle (yoksa)
  try {
    await db.execute(`ALTER TABLE tahtalar ADD COLUMN anahtar VARCHAR(255) NOT NULL DEFAULT ''`);
  } catch (e) { /* sütun zaten var */ }

  await db.execute(`
    CREATE TABLE IF NOT EXISTS kullanicilar (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      kullanici_adi VARCHAR(100) NOT NULL UNIQUE,
      sifre_hash VARCHAR(255) NOT NULL,
      ad_soyad VARCHAR(255) NOT NULL,
      rol ENUM('superadmin', 'yonetici', 'ogretmen') NOT NULL DEFAULT 'ogretmen',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Mevcut tablodaki ENUM'u güncelle (superadmin yoksa ekle)
  try {
    await db.execute(`ALTER TABLE kullanicilar MODIFY COLUMN rol ENUM('superadmin', 'yonetici', 'ogretmen') NOT NULL DEFAULT 'ogretmen'`);
  } catch (e) { /* zaten güncel */ }

  // Branş ve doğum tarihi sütunlarını ekle (yoksa)
  try {
    await db.execute(`ALTER TABLE kullanicilar ADD COLUMN brans VARCHAR(100) DEFAULT NULL`);
  } catch (e) { /* sütun zaten var */ }
  try {
    await db.execute(`ALTER TABLE kullanicilar ADD COLUMN dogum_tarihi DATE DEFAULT NULL`);
  } catch (e) { /* sütun zaten var */ }

  // Ders çıkış saatleri tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS ders_saatleri (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      sira TINYINT NOT NULL,
      saat VARCHAR(5) NOT NULL DEFAULT '',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY unik_kurum_sira (kurum_id, sira),
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Kurumlara ders saatleri aktif/pasif sütunu ekle
  try {
    await db.execute(`ALTER TABLE kurumlar ADD COLUMN ders_saatleri_aktif TINYINT NOT NULL DEFAULT 0`);
  } catch (e) { /* sütun zaten var */ }

  // Sınavlar tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS sinavlar (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      ekleyen_id INT NOT NULL,
      ders_adi VARCHAR(255) NOT NULL,
      sinav_tarihi DATE NOT NULL,
      ders_saati_baslangic TINYINT NOT NULL,
      ders_saati_bitis TINYINT NOT NULL,
      tahtalar JSON NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
      FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Ayın öğrencileri tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS ayin_ogrencileri (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      ekleyen_id INT NOT NULL,
      sira TINYINT NOT NULL DEFAULT 1,
      ad_soyad VARCHAR(255) NOT NULL,
      sinif VARCHAR(50) NOT NULL DEFAULT '',
      odul VARCHAR(255) NOT NULL DEFAULT '',
      aciklama TEXT DEFAULT NULL,
      foto_url VARCHAR(500) DEFAULT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY unik_kurum_sira (kurum_id, sira),
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
      FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Slider tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS slider (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      ekleyen_id INT NOT NULL,
      sira INT NOT NULL DEFAULT 1,
      baslik VARCHAR(255) NOT NULL,
      alt_yazi TEXT DEFAULT NULL,
      badge_turu ENUM('duyuru','basari','etkinlik','yeni') NOT NULL DEFAULT 'duyuru',
      foto_url VARCHAR(500) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
      FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Duyurular tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS duyurular (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      ekleyen_id INT NOT NULL,
      baslik VARCHAR(255) NOT NULL,
      icerik TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
      FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  await db.execute(`
    CREATE TABLE IF NOT EXISTS duyuru_tahtalar (
      duyuru_id INT NOT NULL,
      tahta_id VARCHAR(36) NOT NULL,
      PRIMARY KEY (duyuru_id, tahta_id),
      FOREIGN KEY (duyuru_id) REFERENCES duyurular(id) ON DELETE CASCADE,
      FOREIGN KEY (tahta_id) REFERENCES tahtalar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // İşlem kayıtları (loglar) tablosu
  await db.execute(`
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
    ) ENGINE=InnoDB
  `);

  // Günün sözleri tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS gunun_sozleri (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      ekleyen_id INT NOT NULL,
      soz TEXT NOT NULL,
      yazar VARCHAR(255) NOT NULL DEFAULT '',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
      FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  // Zeka bulmacaları tablosu
  await db.execute(`
    CREATE TABLE IF NOT EXISTS zeka_bulmacalari (
      id INT AUTO_INCREMENT PRIMARY KEY,
      kurum_id INT NOT NULL,
      ekleyen_id INT NOT NULL,
      soru_metni TEXT DEFAULT NULL,
      soru_gorsel VARCHAR(500) DEFAULT NULL,
      cevap TEXT NOT NULL,
      aktif_tarih DATE NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY unik_kurum_tarih (kurum_id, aktif_tarih),
      FOREIGN KEY (kurum_id) REFERENCES kurumlar(id) ON DELETE CASCADE,
      FOREIGN KEY (ekleyen_id) REFERENCES kullanicilar(id) ON DELETE CASCADE
    ) ENGINE=InnoDB
  `);

  console.log("Veritabanı tabloları hazır.");
}

// ===================== İlk Kurulum =====================
async function ilkKurulum() {
  const [admins] = await db.execute(
    "SELECT COUNT(*) as sayi FROM kullanicilar WHERE rol = 'superadmin'"
  );

  if (admins[0].sayi === 0) {
    console.log("\n=== İLK KURULUM ===");

    await db.execute(
      "INSERT IGNORE INTO kurumlar (kurum_kodu, kurum_adi) VALUES (?, ?)",
      ["000000", "Merkez Yönetim"]
    );

    const [kurumRows] = await db.execute(
      "SELECT id FROM kurumlar WHERE kurum_kodu = ?",
      ["000000"]
    );

    const hash = await bcrypt.hash("admin123", 10);
    await db.execute(
      "INSERT INTO kullanicilar (kurum_id, kullanici_adi, sifre_hash, ad_soyad, rol) VALUES (?, ?, ?, ?, ?)",
      [kurumRows[0].id, "superadmin", hash, "Süper Yönetici", "superadmin"]
    );

    console.log("Varsayılan süper yönetici oluşturuldu:");
    console.log("  Kullanıcı adı : superadmin");
    console.log("  Şifre          : admin123");
    console.log("  ⚠  İlk girişten sonra şifrenizi değiştirin!");
    console.log("===================\n");
  }
}

// ===================== Auth Middleware =====================
function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return res.status(401).json({ hata: "Yetkilendirme gerekli" });
  }
  try {
    req.kullanici = jwt.verify(authHeader.split(" ")[1], JWT_SECRET);
    next();
  } catch {
    return res.status(401).json({ hata: "Geçersiz veya süresi dolmuş token" });
  }
}

function adminMiddleware(req, res, next) {
  if (req.kullanici.rol !== "yonetici" && req.kullanici.rol !== "superadmin") {
    return res.status(403).json({ hata: "Bu işlem için yönetici rolü gerekli" });
  }
  next();
}

function superadminMiddleware(req, res, next) {
  if (req.kullanici.rol !== "superadmin") {
    return res.status(403).json({ hata: "Bu işlem için süper yönetici rolü gerekli" });
  }
  next();
}

// ===================== REST API =====================

// --- Giriş ---
app.post("/api/giris", async (req, res) => {
  const { kullanici_adi, sifre } = req.body;
  if (!kullanici_adi || !sifre) {
    return res.status(400).json({ hata: "Kullanıcı adı ve şifre gerekli" });
  }

  try {
    const [rows] = await db.execute(
      `SELECT k.*, ku.kurum_kodu, ku.kurum_adi
       FROM kullanicilar k
       JOIN kurumlar ku ON k.kurum_id = ku.id
       WHERE k.kullanici_adi = ?`,
      [kullanici_adi]
    );

    if (rows.length === 0) {
      return res.status(401).json({ hata: "Geçersiz kullanıcı adı veya şifre" });
    }

    const kullanici = rows[0];
    const sifreGecerli = await bcrypt.compare(sifre, kullanici.sifre_hash);
    if (!sifreGecerli) {
      return res.status(401).json({ hata: "Geçersiz kullanıcı adı veya şifre" });
    }

    const tokenVerisi = {
      id: kullanici.id,
      kullanici_adi: kullanici.kullanici_adi,
      ad_soyad: kullanici.ad_soyad,
      rol: kullanici.rol,
      kurum_id: kullanici.kurum_id,
      kurum_kodu: kullanici.kurum_kodu,
      kurum_adi: kullanici.kurum_adi,
    };

    const bpiHatirla = req.body.bpiHatirla === true;
    const token = jwt.sign(tokenVerisi, JWT_SECRET, { expiresIn: bpiHatirla ? "30d" : "8h" });

    res.json({
      token,
      kullanici: {
        id: kullanici.id,
        kullanici_adi: kullanici.kullanici_adi,
        ad_soyad: kullanici.ad_soyad,
        rol: kullanici.rol,
        kurum_kodu: kullanici.kurum_kodu,
        kurum_adi: kullanici.kurum_adi,
      },
    });
  } catch (err) {
    console.error("Giriş hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// --- Şifre Değiştir ---
app.post("/api/sifre-degistir", authMiddleware, async (req, res) => {
  const { mevcut_sifre, yeni_sifre } = req.body;
  if (!mevcut_sifre || !yeni_sifre) {
    return res.status(400).json({ hata: "Mevcut ve yeni şifre gerekli" });
  }
  if (yeni_sifre.length < 6) {
    return res.status(400).json({ hata: "Yeni şifre en az 6 karakter olmalı" });
  }

  try {
    const [rows] = await db.execute(
      "SELECT sifre_hash FROM kullanicilar WHERE id = ?",
      [req.kullanici.id]
    );
    if (rows.length === 0) {
      return res.status(404).json({ hata: "Kullanıcı bulunamadı" });
    }

    const gecerli = await bcrypt.compare(mevcut_sifre, rows[0].sifre_hash);
    if (!gecerli) {
      return res.status(401).json({ hata: "Mevcut şifre yanlış" });
    }

    const hash = await bcrypt.hash(yeni_sifre, 10);
    await db.execute("UPDATE kullanicilar SET sifre_hash = ? WHERE id = ?", [
      hash,
      req.kullanici.id,
    ]);
    res.json({ mesaj: "Şifre başarıyla değiştirildi" });
  } catch (err) {
    console.error("Şifre değiştirme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// --- Tahtalar ---
app.get("/api/tahtalar", authMiddleware, async (req, res) => {
  try {
    let rows;
    if (req.kullanici.rol === "superadmin" && !req.query.kurum_id) {
      // Superadmin kurum belirtmezse tüm tahtaları görür
      [rows] = await db.execute(
        `SELECT t.*, k.kurum_kodu, k.kurum_adi
         FROM tahtalar t
         JOIN kurumlar k ON t.kurum_id = k.id
         ORDER BY k.kurum_adi, t.tahta_adi`
      );
    } else {
      const kurumId = req.query.kurum_id && req.kullanici.rol === "superadmin"
        ? req.query.kurum_id
        : req.kullanici.kurum_id;
      [rows] = await db.execute(
        `SELECT t.*, k.kurum_kodu, k.kurum_adi
         FROM tahtalar t
         JOIN kurumlar k ON t.kurum_id = k.id
         WHERE t.kurum_id = ?
         ORDER BY t.tahta_adi`,
        [kurumId]
      );
    }
    res.json(rows);
  } catch (err) {
    console.error("Tahta listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

app.post("/api/tahtalar", authMiddleware, adminMiddleware, async (req, res) => {
  const { tahta_id, tahta_adi, kurum_id } = req.body;
  if (!tahta_id) {
    return res.status(400).json({ hata: "Tahta ID gerekli" });
  }

  // Superadmin farklı kuruma tahta ekleyebilir
  const hedefKurumId = (kurum_id && req.kullanici.rol === "superadmin")
    ? kurum_id
    : req.kullanici.kurum_id;

  try {
    await db.execute(
      "INSERT INTO tahtalar (id, kurum_id, tahta_adi) VALUES (?, ?, ?)",
      [tahta_id, hedefKurumId, tahta_adi || ""]
    );
    // Panellere güncel listeyi gönder
    panellereGonder(req.kullanici.kurum_id).catch(() => {});
    res.json({ mesaj: "Tahta başarıyla eklendi" });
  } catch (err) {
    if (err.code === "ER_DUP_ENTRY") {
      return res.status(409).json({ hata: "Bu tahta ID zaten kayıtlı" });
    }
    console.error("Tahta ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

app.put(
  "/api/tahtalar/:id",
  authMiddleware,
  adminMiddleware,
  async (req, res) => {
    const { tahta_adi, kurum_id, yeni_tahta_id } = req.body;
    try {
      const mevcutId = req.params.id;
      if (req.kullanici.rol === "superadmin") {
        const alanlar = [];
        const degerler = [];
        if (yeni_tahta_id !== undefined && yeni_tahta_id !== mevcutId) { alanlar.push("id = ?"); degerler.push(yeni_tahta_id); }
        if (tahta_adi !== undefined) { alanlar.push("tahta_adi = ?"); degerler.push(tahta_adi); }
        if (kurum_id !== undefined) { alanlar.push("kurum_id = ?"); degerler.push(kurum_id); }
        if (alanlar.length === 0) return res.status(400).json({ hata: "Güncellenecek alan yok" });
        degerler.push(mevcutId);
        await db.execute(`UPDATE tahtalar SET ${alanlar.join(", ")} WHERE id = ?`, degerler);
      } else {
        const alanlar = [];
        const degerler = [];
        if (yeni_tahta_id !== undefined && yeni_tahta_id !== mevcutId) { alanlar.push("id = ?"); degerler.push(yeni_tahta_id); }
        if (tahta_adi !== undefined) { alanlar.push("tahta_adi = ?"); degerler.push(tahta_adi); }
        if (alanlar.length === 0) return res.status(400).json({ hata: "Güncellenecek alan yok" });
        degerler.push(mevcutId, req.kullanici.kurum_id);
        await db.execute(`UPDATE tahtalar SET ${alanlar.join(", ")} WHERE id = ? AND kurum_id = ?`, degerler);
      }
      panellereGonder(req.kullanici.kurum_id).catch(() => {});

      // Bağlı tahtaya ad güncellemesini bildir
      if (tahta_adi !== undefined) {
        const hedefId = (yeni_tahta_id && yeni_tahta_id !== mevcutId) ? yeni_tahta_id : mevcutId;
        for (const [sid, info] of Object.entries(bagliTahtalar)) {
          if (info.tahtaId === mevcutId || info.tahtaId === hedefId) {
            io.to(sid).emit("tahta_adi_guncellendi", { tahta_adi });
            break;
          }
        }
      }

      res.json({ mesaj: "Tahta güncellendi" });
    } catch (err) {
      console.error("Tahta güncelleme hatası:", err);
      res.status(500).json({ hata: "Sunucu hatası" });
    }
  }
);

app.delete(
  "/api/tahtalar/:id",
  authMiddleware,
  adminMiddleware,
  async (req, res) => {
    try {
      if (req.kullanici.rol === "superadmin") {
        await db.execute("DELETE FROM tahtalar WHERE id = ?", [req.params.id]);
      } else {
        await db.execute(
          "DELETE FROM tahtalar WHERE id = ? AND kurum_id = ?",
          [req.params.id, req.kullanici.kurum_id]
        );
      }
      // Panellere güncel listeyi gönder
      panellereGonder(req.kullanici.kurum_id).catch(() => {});
      res.json({ mesaj: "Tahta silindi" });
    } catch (err) {
      console.error("Tahta silme hatası:", err);
      res.status(500).json({ hata: "Sunucu hatası" });
    }
  }
);

// --- Kullanıcılar ---
app.get(
  "/api/kullanicilar",
  authMiddleware,
  adminMiddleware,
  async (req, res) => {
    try {
      const kurumId = req.query.kurum_id && req.kullanici.rol === "superadmin"
        ? req.query.kurum_id
        : req.kullanici.kurum_id;

      let rows;
      if (req.kullanici.rol === "superadmin" && !req.query.kurum_id) {
        // Superadmin kurum belirtmezse tüm kullanıcıları görür
        [rows] = await db.execute(
          "SELECT k.id, k.kullanici_adi, k.ad_soyad, k.rol, k.brans, k.dogum_tarihi, k.kurum_id, k.created_at, ku.kurum_adi FROM kullanicilar k JOIN kurumlar ku ON k.kurum_id = ku.id ORDER BY ku.kurum_adi, k.ad_soyad"
        );
      } else {
        [rows] = await db.execute(
          "SELECT k.id, k.kullanici_adi, k.ad_soyad, k.rol, k.brans, k.dogum_tarihi, k.kurum_id, k.created_at, ku.kurum_adi FROM kullanicilar k JOIN kurumlar ku ON k.kurum_id = ku.id WHERE k.kurum_id = ? ORDER BY k.ad_soyad",
          [kurumId]
        );
      }
      res.json(rows);
    } catch (err) {
      console.error("Kullanıcı listesi hatası:", err);
      res.status(500).json({ hata: "Sunucu hatası" });
    }
  }
);

app.post(
  "/api/kullanicilar",
  authMiddleware,
  adminMiddleware,
  async (req, res) => {
    const { kullanici_adi, sifre, ad_soyad, rol, kurum_id, brans, dogum_tarihi } = req.body;
    if (!kullanici_adi || !sifre || !ad_soyad) {
      return res.status(400).json({ hata: "Tüm alanlar gerekli" });
    }
    if (sifre.length < 6) {
      return res.status(400).json({ hata: "Şifre en az 6 karakter olmalı" });
    }

    // Geçerli roller
    const gecerliRoller = ["yonetici", "ogretmen"];
    if (req.kullanici.rol === "superadmin") gecerliRoller.push("superadmin");
    if (rol && !gecerliRoller.includes(rol)) {
      return res.status(400).json({ hata: "Geçersiz rol" });
    }

    // Superadmin farklı kuruma kullanıcı ekleyebilir
    const hedefKurumId = (kurum_id && req.kullanici.rol === "superadmin")
      ? kurum_id
      : req.kullanici.kurum_id;

    try {
      const hash = await bcrypt.hash(sifre, 10);
      await db.execute(
        "INSERT INTO kullanicilar (kurum_id, kullanici_adi, sifre_hash, ad_soyad, rol, brans, dogum_tarihi) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [hedefKurumId, kullanici_adi, hash, ad_soyad, rol || "ogretmen", brans || null, dogum_tarihi || null]
      );
      res.json({ mesaj: "Kullanıcı eklendi" });
    } catch (err) {
      if (err.code === "ER_DUP_ENTRY") {
        return res.status(409).json({ hata: "Bu kullanıcı adı zaten mevcut" });
      }
      console.error("Kullanıcı ekleme hatası:", err);
      res.status(500).json({ hata: "Sunucu hatası" });
    }
  }
);

app.put(
  "/api/kullanicilar/:id",
  authMiddleware,
  adminMiddleware,
  async (req, res) => {
    const { ad_soyad, rol, sifre, kurum_id, brans, dogum_tarihi } = req.body;
    const hedefId = parseInt(req.params.id);

    // Kendi rolünü değiştiremez
    if (hedefId === req.kullanici.id && rol && rol !== req.kullanici.rol) {
      return res.status(400).json({ hata: "Kendi rolünüzü değiştiremezsiniz" });
    }

    // Geçerli roller kontrolü
    if (rol) {
      const gecerliRoller = ["ogretmen", "yonetici"];
      if (req.kullanici.rol === "superadmin") gecerliRoller.push("superadmin");
      if (!gecerliRoller.includes(rol)) {
        return res.status(400).json({ hata: "Geçersiz rol" });
      }
    }

    // Şifre uzunluk kontrolü
    if (sifre && sifre.length < 6) {
      return res.status(400).json({ hata: "Şifre en az 6 karakter olmalı" });
    }

    try {
      // Yönetici sadece kendi kurumundaki öğretmenleri düzenleyebilir
      if (req.kullanici.rol !== "superadmin") {
        const [rows] = await db.execute(
          "SELECT rol, kurum_id FROM kullanicilar WHERE id = ?", [hedefId]
        );
        if (rows.length === 0) return res.status(404).json({ hata: "Kullanıcı bulunamadı" });
        if (rows[0].kurum_id !== req.kullanici.kurum_id) {
          return res.status(403).json({ hata: "Bu kullanıcıyı düzenleme yetkiniz yok" });
        }
        if (rows[0].rol !== "ogretmen" && hedefId !== req.kullanici.id) {
          return res.status(403).json({ hata: "Sadece öğretmen kullanıcılarını düzenleyebilirsiniz" });
        }
        // Yönetici rol atamasını sadece ogretmen yapabilir
        if (rol && rol !== "ogretmen") {
          return res.status(403).json({ hata: "Bu rolü atama yetkiniz yok" });
        }
      }

      const alanlar = [];
      const degerler = [];
      if (ad_soyad) { alanlar.push("ad_soyad = ?"); degerler.push(ad_soyad); }
      if (rol) { alanlar.push("rol = ?"); degerler.push(rol); }
      if (kurum_id && req.kullanici.rol === "superadmin") { alanlar.push("kurum_id = ?"); degerler.push(kurum_id); }
      if (brans !== undefined) { alanlar.push("brans = ?"); degerler.push(brans || null); }
      if (dogum_tarihi !== undefined) { alanlar.push("dogum_tarihi = ?"); degerler.push(dogum_tarihi || null); }
      if (sifre) {
        const hash = await bcrypt.hash(sifre, 10);
        alanlar.push("sifre_hash = ?"); degerler.push(hash);
      }

      if (alanlar.length === 0) return res.status(400).json({ hata: "Güncellenecek alan yok" });
      degerler.push(hedefId);
      await db.execute(`UPDATE kullanicilar SET ${alanlar.join(", ")} WHERE id = ?`, degerler);
      res.json({ mesaj: "Kullanıcı güncellendi" });
    } catch (err) {
      console.error("Kullanıcı güncelleme hatası:", err);
      res.status(500).json({ hata: "Sunucu hatası" });
    }
  }
);

app.delete(
  "/api/kullanicilar/:id",
  authMiddleware,
  adminMiddleware,
  async (req, res) => {
    if (parseInt(req.params.id) === req.kullanici.id) {
      return res.status(400).json({ hata: "Kendinizi silemezsiniz" });
    }
    try {
      if (req.kullanici.rol === "superadmin") {
        await db.execute("DELETE FROM kullanicilar WHERE id = ?", [req.params.id]);
      } else {
        // Yönetici sadece kendi kurumundaki öğretmenleri silebilir
        const [rows] = await db.execute(
          "SELECT rol, kurum_id FROM kullanicilar WHERE id = ?", [req.params.id]
        );
        if (rows.length === 0) return res.status(404).json({ hata: "Kullanıcı bulunamadı" });
        if (rows[0].kurum_id !== req.kullanici.kurum_id) {
          return res.status(403).json({ hata: "Bu kullanıcıyı silme yetkiniz yok" });
        }
        if (rows[0].rol !== "ogretmen") {
          return res.status(403).json({ hata: "Sadece öğretmen kullanıcılarını silebilirsiniz" });
        }
        await db.execute("DELETE FROM kullanicilar WHERE id = ?", [req.params.id]);
      }
      res.json({ mesaj: "Kullanıcı silindi" });
    } catch (err) {
      console.error("Kullanıcı silme hatası:", err);
      res.status(500).json({ hata: "Sunucu hatası" });
    }
  }
);

// --- Kurumlar (superadmin) ---
app.get("/api/kurumlar", authMiddleware, superadminMiddleware, async (req, res) => {
  try {
    const [rows] = await db.execute(
      "SELECT * FROM kurumlar ORDER BY kurum_adi"
    );
    res.json(rows);
  } catch (err) {
    console.error("Kurum listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

app.post("/api/kurumlar", authMiddleware, superadminMiddleware, async (req, res) => {
  const { kurum_kodu, kurum_adi } = req.body;
  if (!kurum_kodu || !kurum_adi) {
    return res.status(400).json({ hata: "Kurum kodu ve adı gerekli" });
  }
  try {
    const anahtar = crypto.randomBytes(32).toString('hex');
    await db.execute(
      "INSERT INTO kurumlar (kurum_kodu, kurum_adi, anahtar) VALUES (?, ?, ?)",
      [kurum_kodu, kurum_adi, anahtar]
    );
    res.json({ mesaj: "Kurum eklendi" });
  } catch (err) {
    if (err.code === "ER_DUP_ENTRY") {
      return res.status(409).json({ hata: "Bu kurum kodu zaten mevcut" });
    }
    console.error("Kurum ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

app.put("/api/kurumlar/:id", authMiddleware, superadminMiddleware, async (req, res) => {
  const { kurum_kodu, kurum_adi } = req.body;
  try {
    const alanlar = [];
    const degerler = [];
    if (kurum_kodu) { alanlar.push("kurum_kodu = ?"); degerler.push(kurum_kodu); }
    if (kurum_adi) { alanlar.push("kurum_adi = ?"); degerler.push(kurum_adi); }
    if (alanlar.length === 0) return res.status(400).json({ hata: "Güncellenecek alan yok" });
    degerler.push(req.params.id);
    const [result] = await db.execute(`UPDATE kurumlar SET ${alanlar.join(", ")} WHERE id = ?`, degerler);
    if (result.affectedRows === 0) return res.status(404).json({ hata: "Kurum bulunamadı" });
    res.json({ mesaj: "Kurum güncellendi" });
  } catch (err) {
    if (err.code === "ER_DUP_ENTRY") return res.status(409).json({ hata: "Bu kurum kodu zaten mevcut" });
    console.error("Kurum güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

app.delete("/api/kurumlar/:id", authMiddleware, superadminMiddleware, async (req, res) => {
  try {
    const [result] = await db.execute("DELETE FROM kurumlar WHERE id = ?", [req.params.id]);
    if (result.affectedRows === 0) {
      return res.status(404).json({ hata: "Kurum bulunamadı" });
    }
    res.json({ mesaj: "Kurum silindi" });
  } catch (err) {
    console.error("Kurum silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ---- Kurum anahtarını yenile (superadmin: herhangi kurum, yönetici: kendi kurumu) ----
app.post("/api/kurumlar/:id/anahtar-yenile", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const kurumId = parseInt(req.params.id);
    // Yönetici sadece kendi kurumunun anahtarını yenileyebilir
    if (req.kullanici.rol !== "superadmin" && req.kullanici.kurum_id !== kurumId) {
      return res.status(403).json({ hata: "Sadece kendi kurumunuzun anahtarını yenileyebilirsiniz" });
    }
    const yeniAnahtar = crypto.randomBytes(32).toString('hex');
    const [result] = await db.execute("UPDATE kurumlar SET anahtar = ? WHERE id = ?", [yeniAnahtar, kurumId]);
    if (result.affectedRows === 0) return res.status(404).json({ hata: "Kurum bulunamadı" });
    res.json({ mesaj: "Anahtar yenilendi", anahtar: yeniAnahtar });
  } catch (err) {
    console.error("Anahtar yenileme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ---- Yönetici: kendi kurumunun anahtarını görüntüle ----
app.get("/api/kurum-anahtari", authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const [rows] = await db.execute("SELECT anahtar FROM kurumlar WHERE id = ?", [req.kullanici.kurum_id]);
    if (rows.length === 0) return res.status(404).json({ hata: "Kurum bulunamadı" });
    res.json({ anahtar: rows[0].anahtar });
  } catch (err) {
    console.error("Kurum anahtarı getirme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Ders Çıkış Saatleri =====================

// Ders saatlerini getir
app.get("/api/ders-saatleri", authMiddleware, async (req, res) => {
  try {
    const kurumId = req.query.kurum_id && req.kullanici.rol === "superadmin"
      ? req.query.kurum_id
      : req.kullanici.kurum_id;

    const [saatler] = await db.execute(
      "SELECT sira, saat FROM ders_saatleri WHERE kurum_id = ? ORDER BY sira",
      [kurumId]
    );

    const [kurumRows] = await db.execute(
      "SELECT ders_saatleri_aktif FROM kurumlar WHERE id = ?",
      [kurumId]
    );

    const aktif = kurumRows.length > 0 ? kurumRows[0].ders_saatleri_aktif : 0;

    res.json({ aktif, saatler });
  } catch (err) {
    console.error("Ders saatleri getirme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Ders saatlerini kaydet/güncelle
app.post("/api/ders-saatleri", authMiddleware, adminMiddleware, async (req, res) => {
  const { saatler, aktif, kurum_id } = req.body;

  const kurumId = (kurum_id && req.kullanici.rol === "superadmin")
    ? kurum_id
    : req.kullanici.kurum_id;

  try {
    // aktif/pasif durumu güncelle
    if (aktif !== undefined) {
      await db.execute(
        "UPDATE kurumlar SET ders_saatleri_aktif = ? WHERE id = ?",
        [aktif ? 1 : 0, kurumId]
      );
    }

    // Saatleri kaydet
    if (Array.isArray(saatler)) {
      for (const item of saatler) {
        const sira = parseInt(item.sira);
        const saat = (item.saat || "").trim();
        if (sira < 1 || sira > 10) continue;
        // HH:MM format doğrulama
        if (saat && !/^\d{2}:\d{2}$/.test(saat)) continue;

        await db.execute(
          `INSERT INTO ders_saatleri (kurum_id, sira, saat) VALUES (?, ?, ?)
           ON DUPLICATE KEY UPDATE saat = VALUES(saat)`,
          [kurumId, sira, saat]
        );
      }
    }

    // Bağlı tahtaları güncelle
    const dersSaatleriVerisi = await dersSaatleriAl(kurumId);
    Object.entries(bagliTahtalar).forEach(([sid, bilgi]) => {
      if (bilgi.kurumId === parseInt(kurumId)) {
        io.to(sid).emit("ders_saatleri", dersSaatleriVerisi);
      }
    });

    res.json({ mesaj: "Ders saatleri kaydedildi" });
  } catch (err) {
    console.error("Ders saatleri kaydetme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Sınavlar =====================

// Sınav listesi
app.get("/api/sinavlar", authMiddleware, async (req, res) => {
  try {
    const kurumId = req.query.kurum_id && req.kullanici.rol === "superadmin"
      ? req.query.kurum_id
      : req.kullanici.kurum_id;
    const [rows] = await db.execute(
      `SELECT s.*, k.ad_soyad AS ekleyen_adi
       FROM sinavlar s
       JOIN kullanicilar k ON s.ekleyen_id = k.id
       WHERE s.kurum_id = ?
       ORDER BY s.sinav_tarihi ASC, s.ders_saati_baslangic ASC`,
      [kurumId]
    );
    res.json(rows);
  } catch (err) {
    console.error("Sınav listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Sınav ekle
app.post("/api/sinavlar", authMiddleware, async (req, res) => {
  if (req.kullanici.rol !== "ogretmen" && req.kullanici.rol !== "yonetici") {
    return res.status(403).json({ hata: "Bu işlem için yetkiniz yok" });
  }
  const { ders_adi, sinav_tarihi, ders_saati_baslangic, ders_saati_bitis, tahtalar } = req.body;
  if (!ders_adi || !sinav_tarihi || !ders_saati_baslangic || !ders_saati_bitis) {
    return res.status(400).json({ hata: "Tüm alanlar gerekli" });
  }
  if (parseInt(ders_saati_baslangic) > parseInt(ders_saati_bitis)) {
    return res.status(400).json({ hata: "Başlangıç ders saati bitiş ders saatinden büyük olamaz" });
  }
  if (!Array.isArray(tahtalar) || tahtalar.length === 0) {
    return res.status(400).json({ hata: "En az bir tahta seçilmelidir" });
  }
  const kurumId = req.kullanici.kurum_id;
  try {
    // Aynı tarihte en fazla 3 sınav kontrolü
    const [mevcutSinavlar] = await db.execute(
      `SELECT s.ders_adi, s.ders_saati_baslangic, s.ders_saati_bitis, k.ad_soyad AS ekleyen_adi
       FROM sinavlar s JOIN kullanicilar k ON s.ekleyen_id = k.id
       WHERE s.kurum_id = ? AND s.sinav_tarihi = ?`,
      [kurumId, sinav_tarihi]
    );
    if (mevcutSinavlar.length >= 3) {
      const detay = mevcutSinavlar.map(s => {
        const saat = s.ders_saati_baslangic === s.ders_saati_bitis ? s.ders_saati_baslangic + '. Ders' : s.ders_saati_baslangic + '-' + s.ders_saati_bitis + '. Ders';
        return s.ders_adi + ' (' + saat + ') - ' + s.ekleyen_adi;
      }).join('\n');
      return res.status(400).json({ hata: "Aynı tarihte en fazla 3 sınav olabilir.\n\nMevcut sınavlar:\n" + detay });
    }
    // Aynı tarihte aynı ders saatlerine çakışma kontrolü
    const [cakisanlar] = await db.execute(
      `SELECT s.ders_adi, s.ders_saati_baslangic, s.ders_saati_bitis, k.ad_soyad AS ekleyen_adi
       FROM sinavlar s JOIN kullanicilar k ON s.ekleyen_id = k.id
       WHERE s.kurum_id = ? AND s.sinav_tarihi = ?
       AND s.ders_saati_baslangic <= ? AND s.ders_saati_bitis >= ?`,
      [kurumId, sinav_tarihi, parseInt(ders_saati_bitis), parseInt(ders_saati_baslangic)]
    );
    if (cakisanlar.length > 0) {
      const detay = cakisanlar.map(s => {
        const saat = s.ders_saati_baslangic === s.ders_saati_bitis ? s.ders_saati_baslangic + '. Ders' : s.ders_saati_baslangic + '-' + s.ders_saati_bitis + '. Ders';
        return s.ders_adi + ' (' + saat + ') - ' + s.ekleyen_adi;
      }).join('\n');
      return res.status(400).json({ hata: "Bu tarihte seçilen ders saatleriyle çakışan sınav var:\n" + detay });
    }
    await db.execute(
      `INSERT INTO sinavlar (kurum_id, ekleyen_id, ders_adi, sinav_tarihi, ders_saati_baslangic, ders_saati_bitis, tahtalar)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [kurumId, req.kullanici.id, ders_adi, sinav_tarihi, parseInt(ders_saati_baslangic), parseInt(ders_saati_bitis), JSON.stringify(tahtalar)]
    );
    // Bağlı tahtaları güncelle
    await sinavlariGuncelleTahtalar(kurumId);
    res.json({ mesaj: "Sınav eklendi" });
  } catch (err) {
    console.error("Sınav ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Sınav güncelle
app.put("/api/sinavlar/:id", authMiddleware, async (req, res) => {
  const { ders_adi, sinav_tarihi, ders_saati_baslangic, ders_saati_bitis, tahtalar } = req.body;
  const sinavId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM sinavlar WHERE id = ?", [sinavId]);
    if (mevcut.length === 0) {
      return res.status(404).json({ hata: "Sınav bulunamadı" });
    }
    const sinav = mevcut[0];
    // Yetki kontrolü
    if (req.kullanici.rol === "superadmin") {
      return res.status(403).json({ hata: "Süper yönetici sınav düzenleyemez" });
    }
    if (req.kullanici.rol === "ogretmen" && sinav.ekleyen_id !== req.kullanici.id) {
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz sınavları düzenleyebilirsiniz" });
    }
    if (sinav.kurum_id !== req.kullanici.kurum_id) {
      return res.status(403).json({ hata: "Bu sınavı düzenleme yetkiniz yok" });
    }
    const yeniDersAdi = ders_adi || sinav.ders_adi;
    const yeniTarih = sinav_tarihi || sinav.sinav_tarihi;
    const yeniBaslangic = ders_saati_baslangic ? parseInt(ders_saati_baslangic) : sinav.ders_saati_baslangic;
    const yeniBitis = ders_saati_bitis ? parseInt(ders_saati_bitis) : sinav.ders_saati_bitis;
    const yeniTahtalar = tahtalar || (typeof sinav.tahtalar === 'string' ? JSON.parse(sinav.tahtalar) : sinav.tahtalar);
    if (yeniBaslangic > yeniBitis) {
      return res.status(400).json({ hata: "Başlangıç ders saati bitiş ders saatinden büyük olamaz" });
    }
    // Max 3 sınav kontrolü (mevcut sınav hariç)
    const [sayim] = await db.execute(
      "SELECT COUNT(*) AS sayi FROM sinavlar WHERE kurum_id = ? AND sinav_tarihi = ? AND id != ?",
      [sinav.kurum_id, yeniTarih, sinavId]
    );
    if (sayim[0].sayi >= 3) {
      return res.status(400).json({ hata: "Aynı tarihte en fazla 3 sınav olabilir" });
    }
    // Çakışma kontrolü (mevcut sınav hariç)
    const [cakisma] = await db.execute(
      `SELECT COUNT(*) AS sayi FROM sinavlar
       WHERE kurum_id = ? AND sinav_tarihi = ? AND id != ?
       AND ders_saati_baslangic <= ? AND ders_saati_bitis >= ?`,
      [sinav.kurum_id, yeniTarih, sinavId, yeniBitis, yeniBaslangic]
    );
    if (cakisma[0].sayi > 0) {
      return res.status(400).json({ hata: "Bu tarihte seçilen ders saatleriyle çakışan bir sınav zaten var" });
    }
    await db.execute(
      `UPDATE sinavlar SET ders_adi = ?, sinav_tarihi = ?, ders_saati_baslangic = ?, ders_saati_bitis = ?, tahtalar = ? WHERE id = ?`,
      [yeniDersAdi, yeniTarih, yeniBaslangic, yeniBitis, JSON.stringify(yeniTahtalar), sinavId]
    );
    await sinavlariGuncelleTahtalar(sinav.kurum_id);
    res.json({ mesaj: "Sınav güncellendi" });
  } catch (err) {
    console.error("Sınav güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Sınav sil
app.delete("/api/sinavlar/:id", authMiddleware, async (req, res) => {
  const sinavId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM sinavlar WHERE id = ?", [sinavId]);
    if (mevcut.length === 0) {
      return res.status(404).json({ hata: "Sınav bulunamadı" });
    }
    const sinav = mevcut[0];
    // Yetki kontrolü
    if (req.kullanici.rol === "superadmin") {
      return res.status(403).json({ hata: "Süper yönetici sınav silemez" });
    }
    if (req.kullanici.rol === "ogretmen" && sinav.ekleyen_id !== req.kullanici.id) {
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz sınavları silebilirsiniz" });
    }
    if (sinav.kurum_id !== req.kullanici.kurum_id) {
      return res.status(403).json({ hata: "Bu sınavı silme yetkiniz yok" });
    }
    await db.execute("DELETE FROM sinavlar WHERE id = ?", [sinavId]);
    await sinavlariGuncelleTahtalar(sinav.kurum_id);
    res.json({ mesaj: "Sınav silindi" });
  } catch (err) {
    console.error("Sınav silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Ayın Öğrencisi =====================

// Ayın öğrencilerini listele
app.get("/api/ayin-ogrencileri", authMiddleware, async (req, res) => {
  try {
    const kurumId = req.query.kurum_id && req.kullanici.rol === "superadmin"
      ? req.query.kurum_id
      : req.kullanici.kurum_id;
    const [rows] = await db.execute(
      `SELECT a.*, k.ad_soyad AS ekleyen_adi
       FROM ayin_ogrencileri a
       JOIN kullanicilar k ON a.ekleyen_id = k.id
       WHERE a.kurum_id = ?
       ORDER BY a.sira ASC`,
      [kurumId]
    );
    res.json(rows);
  } catch (err) {
    console.error("Ayın öğrencileri listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Ayın öğrencilerini herkese açık listeleme (kurum.html için, auth gerektirmez)
app.get("/api/ayin-ogrencileri-genel", async (req, res) => {
  const { kod, tahta_id } = req.query;
  if (!kod && !tahta_id) return res.json([]);
  try {
    let kurumId = null;
    if (kod) {
      const [rows] = await db.execute("SELECT id FROM kurumlar WHERE kurum_kodu = ?", [kod]);
      if (rows.length > 0) kurumId = rows[0].id;
    }
    if (!kurumId && tahta_id) {
      const [rows2] = await db.execute("SELECT kurum_id FROM tahtalar WHERE id = ?", [tahta_id]);
      if (rows2.length > 0) kurumId = rows2[0].kurum_id;
    }
    if (!kurumId) return res.json([]);
    const [ogrenciler] = await db.execute(
      `SELECT ad_soyad, sinif, odul, aciklama, foto_url, sira
       FROM ayin_ogrencileri
       WHERE kurum_id = ?
       ORDER BY sira ASC`,
      [kurumId]
    );
    res.json(ogrenciler);
  } catch (e) {
    res.json([]);
  }
});

// Fotoğraf dosyasını silen yardımcı fonksiyon
function ayinFotoSil(fotoUrl) {
  if (!fotoUrl) return;
  const dosyaAdi = path.basename(fotoUrl);
  const dosyaYolu = path.join(UPLOAD_DIR, dosyaAdi);
  fs.unlink(dosyaYolu, () => {});
}

// Ayın öğrencisi ekle (multipart/form-data)
app.post("/api/ayin-ogrencileri", authMiddleware, (req, res, next) => {
  ayinUpload.single('foto')(req, res, (err) => {
    if (err) return res.status(400).json({ hata: err.message });
    next();
  });
}, async (req, res) => {
  if (req.kullanici.rol !== "ogretmen" && req.kullanici.rol !== "yonetici") {
    if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
    return res.status(403).json({ hata: "Bu işlem için yetkiniz yok" });
  }
  const { ad_soyad, sinif, odul, aciklama, sira } = req.body;
  if (!ad_soyad || !sinif || !sira) {
    if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
    return res.status(400).json({ hata: "Ad soyad, sınıf ve sıra gerekli" });
  }
  if (!req.file) {
    return res.status(400).json({ hata: "Fotoğraf zorunludur" });
  }
  const siraNum = parseInt(sira);
  if (siraNum < 1 || siraNum > 4) {
    ayinFotoSil('/uploads/ayin/' + req.file.filename);
    return res.status(400).json({ hata: "Sıra 1-4 arasında olmalıdır" });
  }
  const kurumId = req.kullanici.kurum_id;
  const fotoUrl = '/uploads/ayin/' + req.file.filename;
  try {
    const [mevcut] = await db.execute(
      "SELECT id FROM ayin_ogrencileri WHERE kurum_id = ? AND sira = ?",
      [kurumId, siraNum]
    );
    if (mevcut.length > 0) {
      ayinFotoSil(fotoUrl);
      return res.status(400).json({ hata: `${siraNum}. sırada zaten bir öğrenci var. Önce silin veya düzenleyin.` });
    }
    await db.execute(
      `INSERT INTO ayin_ogrencileri (kurum_id, ekleyen_id, sira, ad_soyad, sinif, odul, aciklama, foto_url)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [kurumId, req.kullanici.id, siraNum, ad_soyad, sinif, odul || '', aciklama || null, fotoUrl]
    );
    icerikGuncellendiGonder(kurumId);
    res.json({ mesaj: "Ayın öğrencisi eklendi" });
  } catch (err) {
    ayinFotoSil(fotoUrl);
    console.error("Ayın öğrencisi ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Ayın öğrencisi güncelle (multipart/form-data)
app.put("/api/ayin-ogrencileri/:id", authMiddleware, (req, res, next) => {
  ayinUpload.single('foto')(req, res, (err) => {
    if (err) return res.status(400).json({ hata: err.message });
    next();
  });
}, async (req, res) => {
  const ogrenciId = parseInt(req.params.id);
  const { ad_soyad, sinif, odul, aciklama, sira } = req.body;
  try {
    const [mevcut] = await db.execute("SELECT * FROM ayin_ogrencileri WHERE id = ?", [ogrenciId]);
    if (mevcut.length === 0) {
      if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
      return res.status(404).json({ hata: "Öğrenci bulunamadı" });
    }
    const ogrenci = mevcut[0];
    if (req.kullanici.rol === "superadmin") {
      if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
      return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    }
    if (req.kullanici.rol === "ogretmen" && ogrenci.ekleyen_id !== req.kullanici.id) {
      if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz öğrencileri düzenleyebilirsiniz" });
    }
    if (ogrenci.kurum_id !== req.kullanici.kurum_id) {
      if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
      return res.status(403).json({ hata: "Bu öğrenciyi düzenleme yetkiniz yok" });
    }
    const yeniAdSoyad = ad_soyad || ogrenci.ad_soyad;
    const yeniSinif = sinif || ogrenci.sinif;
    const yeniOdul = odul !== undefined ? odul : ogrenci.odul;
    const yeniAciklama = aciklama !== undefined ? aciklama : ogrenci.aciklama;
    const yeniSira = sira ? parseInt(sira) : ogrenci.sira;
    // Yeni fotoğraf yüklendiyse eski dosyayı sil
    let yeniFotoUrl = ogrenci.foto_url;
    if (req.file) {
      ayinFotoSil(ogrenci.foto_url);
      yeniFotoUrl = '/uploads/ayin/' + req.file.filename;
    }
    if (yeniSira < 1 || yeniSira > 4) {
      if (req.file) ayinFotoSil(yeniFotoUrl);
      return res.status(400).json({ hata: "Sıra 1-4 arasında olmalıdır" });
    }
    if (yeniSira !== ogrenci.sira) {
      const [cakisma] = await db.execute(
        "SELECT id FROM ayin_ogrencileri WHERE kurum_id = ? AND sira = ? AND id != ?",
        [ogrenci.kurum_id, yeniSira, ogrenciId]
      );
      if (cakisma.length > 0) {
        // UNIQUE kısıtlamasını aşmak için: çakışan kaydı geçici sira=0'a al
        await db.execute("UPDATE ayin_ogrencileri SET sira = 0 WHERE id = ?", [cakisma[0].id]);
        // Ana kaydı yeni sıraya al
        await db.execute(
          `UPDATE ayin_ogrencileri SET ad_soyad = ?, sinif = ?, odul = ?, aciklama = ?, foto_url = ?, sira = ? WHERE id = ?`,
          [yeniAdSoyad, yeniSinif, yeniOdul, yeniAciklama, yeniFotoUrl, yeniSira, ogrenciId]
        );
        // Çakışan kaydı eski sıramıza al (yer değiştirme tamamlandı)
        await db.execute("UPDATE ayin_ogrencileri SET sira = ? WHERE id = ?", [ogrenci.sira, cakisma[0].id]);
        icerikGuncellendiGonder(ogrenci.kurum_id);
        return res.json({ mesaj: "Ayın öğrencisi güncellendi" });
      }
    }
    await db.execute(
      `UPDATE ayin_ogrencileri SET ad_soyad = ?, sinif = ?, odul = ?, aciklama = ?, foto_url = ?, sira = ? WHERE id = ?`,
      [yeniAdSoyad, yeniSinif, yeniOdul, yeniAciklama, yeniFotoUrl, yeniSira, ogrenciId]
    );
    icerikGuncellendiGonder(ogrenci.kurum_id);
    res.json({ mesaj: "Ayın öğrencisi güncellendi" });
  } catch (err) {
    if (req.file) ayinFotoSil('/uploads/ayin/' + req.file.filename);
    console.error("Ayın öğrencisi güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Ayın öğrencisi sil
app.delete("/api/ayin-ogrencileri/:id", authMiddleware, async (req, res) => {
  const ogrenciId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM ayin_ogrencileri WHERE id = ?", [ogrenciId]);
    if (mevcut.length === 0) {
      return res.status(404).json({ hata: "Öğrenci bulunamadı" });
    }
    const ogrenci = mevcut[0];
    if (req.kullanici.rol === "superadmin") {
      return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    }
    if (req.kullanici.rol === "ogretmen" && ogrenci.ekleyen_id !== req.kullanici.id) {
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz öğrencileri silebilirsiniz" });
    }
    if (ogrenci.kurum_id !== req.kullanici.kurum_id) {
      return res.status(403).json({ hata: "Bu öğrenciyi silme yetkiniz yok" });
    }
    ayinFotoSil(ogrenci.foto_url);
    await db.execute("DELETE FROM ayin_ogrencileri WHERE id = ?", [ogrenciId]);
    icerikGuncellendiGonder(ogrenci.kurum_id);
    res.json({ mesaj: "Ayın öğrencisi silindi" });
  } catch (err) {
    console.error("Ayın öğrencisi silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Slider =====================

// Slider fotoğrafını silen yardımcı fonksiyon
function sliderFotoSil(fotoUrl) {
  if (!fotoUrl) return;
  const dosyaAdi = path.basename(fotoUrl);
  const dosyaYolu = path.join(SLIDER_UPLOAD_DIR, dosyaAdi);
  fs.unlink(dosyaYolu, () => {});
}

// Slider listele (auth gerekli)
app.get("/api/slider", authMiddleware, async (req, res) => {
  try {
    const kurumId = req.query.kurum_id && req.kullanici.rol === "superadmin"
      ? req.query.kurum_id
      : req.kullanici.kurum_id;
    const [rows] = await db.execute(
      `SELECT s.*, k.ad_soyad AS ekleyen_adi
       FROM slider s
       JOIN kullanicilar k ON s.ekleyen_id = k.id
       WHERE s.kurum_id = ?
       ORDER BY s.sira ASC, s.created_at ASC`,
      [kurumId]
    );
    res.json(rows);
  } catch (err) {
    console.error("Slider listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Slider herkese açık (kurum.html için)
app.get("/api/slider-genel", async (req, res) => {
  const { kod, tahta_id } = req.query;
  if (!kod && !tahta_id) return res.json([]);
  try {
    let kurumId = null;
    if (kod) {
      const [rows] = await db.execute("SELECT id FROM kurumlar WHERE kurum_kodu = ?", [kod]);
      if (rows.length > 0) kurumId = rows[0].id;
    }
    if (!kurumId && tahta_id) {
      const [rows2] = await db.execute("SELECT kurum_id FROM tahtalar WHERE id = ?", [tahta_id]);
      if (rows2.length > 0) kurumId = rows2[0].kurum_id;
    }
    if (!kurumId) return res.json([]);
    const [slides] = await db.execute(
      `SELECT id, baslik, alt_yazi, badge_turu, foto_url, sira
       FROM slider
       WHERE kurum_id = ?
       ORDER BY sira ASC, created_at ASC`,
      [kurumId]
    );
    res.json(slides);
  } catch (e) {
    res.json([]);
  }
});

// Slider ekle
app.post("/api/slider", authMiddleware, (req, res, next) => {
  sliderUpload.single('foto')(req, res, (err) => {
    if (err) return res.status(400).json({ hata: err.message });
    next();
  });
}, async (req, res) => {
  if (req.kullanici.rol !== "ogretmen" && req.kullanici.rol !== "yonetici") {
    if (req.file) sliderFotoSil('/uploads/slider/' + req.file.filename);
    return res.status(403).json({ hata: "Bu işlem için yetkiniz yok" });
  }
  const { baslik, alt_yazi, badge_turu, sira } = req.body;
  if (!baslik) {
    if (req.file) sliderFotoSil('/uploads/slider/' + req.file.filename);
    return res.status(400).json({ hata: "Başlık gerekli" });
  }
  if (!req.file) {
    return res.status(400).json({ hata: "Görsel zorunludur" });
  }
  const gecerliBadgeTurleri = ['duyuru', 'basari', 'etkinlik', 'yeni'];
  const gecerliBadge = gecerliBadgeTurleri.includes(badge_turu) ? badge_turu : 'duyuru';
  const siraNum = parseInt(sira) || 1;
  const kurumId = req.kullanici.kurum_id;
  const fotoUrl = '/uploads/slider/' + req.file.filename;
  try {
    await db.execute(
      `INSERT INTO slider (kurum_id, ekleyen_id, sira, baslik, alt_yazi, badge_turu, foto_url)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [kurumId, req.kullanici.id, siraNum, baslik, alt_yazi || null, gecerliBadge, fotoUrl]
    );
    icerikGuncellendiGonder(kurumId);
    res.json({ mesaj: "Slide eklendi" });
  } catch (err) {
    sliderFotoSil(fotoUrl);
    console.error("Slider ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Slider güncelle
app.put("/api/slider/:id", authMiddleware, (req, res, next) => {
  sliderUpload.single('foto')(req, res, (err) => {
    if (err) return res.status(400).json({ hata: err.message });
    next();
  });
}, async (req, res) => {
  const slideId = parseInt(req.params.id);
  const { baslik, alt_yazi, badge_turu, sira } = req.body;
  try {
    const [mevcut] = await db.execute("SELECT * FROM slider WHERE id = ?", [slideId]);
    if (mevcut.length === 0) {
      if (req.file) sliderFotoSil('/uploads/slider/' + req.file.filename);
      return res.status(404).json({ hata: "Slide bulunamadı" });
    }
    const slide = mevcut[0];

    // Yetki kontrolü
    if (req.kullanici.rol === "ogretmen" && slide.ekleyen_id !== req.kullanici.id) {
      if (req.file) sliderFotoSil('/uploads/slider/' + req.file.filename);
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz slideleri düzenleyebilirsiniz" });
    }
    if (req.kullanici.rol !== "superadmin" && slide.kurum_id !== req.kullanici.kurum_id) {
      if (req.file) sliderFotoSil('/uploads/slider/' + req.file.filename);
      return res.status(403).json({ hata: "Bu slideı düzenleme yetkiniz yok" });
    }

    const gecerliBadgeTurleri = ['duyuru', 'basari', 'etkinlik', 'yeni'];
    const yeniBaslik = baslik || slide.baslik;
    const yeniAltYazi = alt_yazi !== undefined ? (alt_yazi || null) : slide.alt_yazi;
    const yeniBadge = gecerliBadgeTurleri.includes(badge_turu) ? badge_turu : slide.badge_turu;
    const yeniSira = sira ? parseInt(sira) : slide.sira;

    let yeniFotoUrl = slide.foto_url;
    if (req.file) {
      sliderFotoSil(slide.foto_url);
      yeniFotoUrl = '/uploads/slider/' + req.file.filename;
    }

    await db.execute(
      `UPDATE slider SET baslik = ?, alt_yazi = ?, badge_turu = ?, sira = ?, foto_url = ? WHERE id = ?`,
      [yeniBaslik, yeniAltYazi, yeniBadge, yeniSira, yeniFotoUrl, slideId]
    );
    icerikGuncellendiGonder(slide.kurum_id);
    res.json({ mesaj: "Slide güncellendi" });
  } catch (err) {
    if (req.file) sliderFotoSil('/uploads/slider/' + req.file.filename);
    console.error("Slider güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Slider sil
app.delete("/api/slider/:id", authMiddleware, async (req, res) => {
  const slideId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM slider WHERE id = ?", [slideId]);
    if (mevcut.length === 0) {
      return res.status(404).json({ hata: "Slide bulunamadı" });
    }
    const slide = mevcut[0];

    // Yetki kontrolü
    if (req.kullanici.rol === "ogretmen" && slide.ekleyen_id !== req.kullanici.id) {
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz slideleri silebilirsiniz" });
    }
    if (req.kullanici.rol !== "superadmin" && slide.kurum_id !== req.kullanici.kurum_id) {
      return res.status(403).json({ hata: "Bu slideı silme yetkiniz yok" });
    }

    sliderFotoSil(slide.foto_url);
    await db.execute("DELETE FROM slider WHERE id = ?", [slideId]);
    icerikGuncellendiGonder(slide.kurum_id);
    res.json({ mesaj: "Slide silindi" });
  } catch (err) {
    console.error("Slider silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Günün Sözleri =====================

// Söz listele (auth gerekli)
app.get("/api/gunun-sozleri", authMiddleware, async (req, res) => {
  try {
    let rows;
    if (req.kullanici.rol === "superadmin") {
      const kurumId = req.query.kurum_id ? parseInt(req.query.kurum_id) : null;
      if (kurumId) {
        [rows] = await db.execute(
          `SELECT g.*, k.ad_soyad AS ekleyen_adi
           FROM gunun_sozleri g
           JOIN kullanicilar k ON g.ekleyen_id = k.id
           WHERE g.kurum_id = ? ORDER BY g.created_at DESC`,
          [kurumId]
        );
      } else {
        [rows] = await db.execute(
          `SELECT g.*, k.ad_soyad AS ekleyen_adi
           FROM gunun_sozleri g
           JOIN kullanicilar k ON g.ekleyen_id = k.id
           ORDER BY g.created_at DESC`
        );
      }
    } else {
      [rows] = await db.execute(
        `SELECT g.*, k.ad_soyad AS ekleyen_adi
         FROM gunun_sozleri g
         JOIN kullanicilar k ON g.ekleyen_id = k.id
         WHERE g.kurum_id = ? ORDER BY g.created_at DESC`,
        [req.kullanici.kurum_id]
      );
    }
    res.json(rows);
  } catch (err) {
    console.error("Söz listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Günün sözü (genel, kurum bilgi ekranı için — tarih bazlı rastgele)
app.get("/api/gunun-sozu-genel", async (req, res) => {
  try {
    const { kod, tahta_id } = req.query;
    let kurumId = null;
    if (tahta_id) {
      const [t] = await db.execute("SELECT kurum_id FROM tahtalar WHERE id = ?", [tahta_id]);
      if (t.length > 0) kurumId = t[0].kurum_id;
    } else if (kod) {
      const [k] = await db.execute("SELECT id FROM kurumlar WHERE kurum_kodu = ?", [kod]);
      if (k.length > 0) kurumId = k[0].id;
    }
    if (!kurumId) return res.json(null);

    const [rows] = await db.execute(
      "SELECT id, soz, yazar FROM gunun_sozleri WHERE kurum_id = ? ORDER BY id",
      [kurumId]
    );
    if (rows.length === 0) return res.json(null);

    // Tarih bazlı rastgele seçim: bugünün tarihi seed olarak kullanılır
    const bugun = new Date();
    const tarihSeed = bugun.getFullYear() * 10000 + (bugun.getMonth() + 1) * 100 + bugun.getDate();
    const idx = tarihSeed % rows.length;
    res.json(rows[idx]);
  } catch (err) {
    console.error("Günün sözü genel hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Söz ekle
app.post("/api/gunun-sozleri", authMiddleware, async (req, res) => {
  if (req.kullanici.rol !== "ogretmen" && req.kullanici.rol !== "yonetici") {
    return res.status(403).json({ hata: "Bu işlem için yetkiniz yok" });
  }
  const { soz, yazar } = req.body;
  if (!soz || !soz.trim()) {
    return res.status(400).json({ hata: "Söz metni gerekli" });
  }
  try {
    await db.execute(
      "INSERT INTO gunun_sozleri (kurum_id, ekleyen_id, soz, yazar) VALUES (?, ?, ?, ?)",
      [req.kullanici.kurum_id, req.kullanici.id, soz.trim(), (yazar || "").trim()]
    );
    icerikGuncellendiGonder(req.kullanici.kurum_id);
    res.json({ mesaj: "Söz eklendi" });
  } catch (err) {
    console.error("Söz ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Söz güncelle
app.put("/api/gunun-sozleri/:id", authMiddleware, async (req, res) => {
  const sozId = parseInt(req.params.id);
  const { soz, yazar } = req.body;
  if (!soz || !soz.trim()) {
    return res.status(400).json({ hata: "Söz metni gerekli" });
  }
  try {
    const [mevcut] = await db.execute("SELECT * FROM gunun_sozleri WHERE id = ?", [sozId]);
    if (mevcut.length === 0) return res.status(404).json({ hata: "Söz bulunamadı" });
    const s = mevcut[0];
    if (req.kullanici.rol === "superadmin") return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    if (req.kullanici.rol === "ogretmen" && s.ekleyen_id !== req.kullanici.id) return res.status(403).json({ hata: "Sadece kendi sözlerinizi düzenleyebilirsiniz" });
    if (s.kurum_id !== req.kullanici.kurum_id) return res.status(403).json({ hata: "Bu sözü düzenleme yetkiniz yok" });
    await db.execute(
      "UPDATE gunun_sozleri SET soz = ?, yazar = ? WHERE id = ?",
      [soz.trim(), (yazar || "").trim(), sozId]
    );
    icerikGuncellendiGonder(s.kurum_id);
    res.json({ mesaj: "Söz güncellendi" });
  } catch (err) {
    console.error("Söz güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Söz sil
app.delete("/api/gunun-sozleri/:id", authMiddleware, async (req, res) => {
  const sozId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM gunun_sozleri WHERE id = ?", [sozId]);
    if (mevcut.length === 0) return res.status(404).json({ hata: "Söz bulunamadı" });
    const s = mevcut[0];
    if (req.kullanici.rol === "superadmin") return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    if (req.kullanici.rol === "ogretmen" && s.ekleyen_id !== req.kullanici.id) return res.status(403).json({ hata: "Sadece kendi sözlerinizi silebilirsiniz" });
    if (s.kurum_id !== req.kullanici.kurum_id) return res.status(403).json({ hata: "Bu sözü silme yetkiniz yok" });
    await db.execute("DELETE FROM gunun_sozleri WHERE id = ?", [sozId]);
    icerikGuncellendiGonder(s.kurum_id);
    res.json({ mesaj: "Söz silindi" });
  } catch (err) {
    console.error("Söz silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== İçerik Güncelleme Bildirimi =====================
function icerikGuncellendiGonder(kurumId) {
  if (kurumId) {
    io.to(`kurum_${kurumId}`).emit("icerik_guncellendi", {});
  }
}

// ===================== Zeka Bulmacaları =====================

// Bulmaca görseli silen yardımcı
function bulmacaGorselSil(gorselUrl) {
  if (!gorselUrl) return;
  const dosyaAdi = path.basename(gorselUrl);
  const dosyaYolu = path.join(BULMACA_UPLOAD_DIR, dosyaAdi);
  fs.unlink(dosyaYolu, () => {});
}

// Bulmaca listele (auth gerekli)
app.get("/api/zeka-bulmacalari", authMiddleware, async (req, res) => {
  try {
    let url_kurum_id;
    if (req.kullanici.rol === "superadmin" && req.query.kurum_id) {
      url_kurum_id = parseInt(req.query.kurum_id);
    } else {
      url_kurum_id = req.kullanici.kurum_id;
    }
    const [rows] = await db.execute(
      `SELECT z.*, k.ad_soyad AS ekleyen_adi
       FROM zeka_bulmacalari z
       JOIN kullanicilar k ON z.ekleyen_id = k.id
       WHERE z.kurum_id = ?
       ORDER BY z.aktif_tarih DESC`,
      [url_kurum_id]
    );
    res.json(rows);
  } catch (err) {
    console.error("Bulmaca listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Bulmaca genel (kurum.html için — auth gerektirmez)
app.get("/api/zeka-bulmacasi-genel", async (req, res) => {
  try {
    const { kod, tahta_id } = req.query;
    let kurumId = null;
    if (tahta_id) {
      const [t] = await db.execute("SELECT kurum_id FROM tahtalar WHERE id = ?", [tahta_id]);
      if (t.length > 0) kurumId = t[0].kurum_id;
    } else if (kod) {
      const [k] = await db.execute("SELECT id FROM kurumlar WHERE kurum_kodu = ?", [kod]);
      if (k.length > 0) kurumId = k[0].id;
    }
    if (!kurumId) return res.json({ bugunun: null, oncekinin_cevabi: null });

    // Bugünün bulmacası
    const [bugun] = await db.execute(
      "SELECT soru_metni, soru_gorsel, aktif_tarih FROM zeka_bulmacalari WHERE kurum_id = ? AND aktif_tarih = CURDATE()",
      [kurumId]
    );

    // Bir önceki günün bulmacası (cevabını göstermek için)
    const [onceki] = await db.execute(
      `SELECT soru_metni, soru_gorsel, cevap, aktif_tarih FROM zeka_bulmacalari
       WHERE kurum_id = ? AND aktif_tarih < CURDATE()
       ORDER BY aktif_tarih DESC LIMIT 1`,
      [kurumId]
    );

    res.json({
      bugunun: bugun.length > 0 ? bugun[0] : null,
      oncekinin_cevabi: onceki.length > 0 ? onceki[0] : null,
    });
  } catch (err) {
    console.error("Bulmaca genel hatası:", err);
    res.json({ bugunun: null, oncekinin_cevabi: null });
  }
});

// Bulmaca ekle (multipart/form-data)
app.post("/api/zeka-bulmacalari", authMiddleware, (req, res, next) => {
  bulmacaUpload.single('gorsel')(req, res, (err) => {
    if (err) return res.status(400).json({ hata: err.message });
    next();
  });
}, async (req, res) => {
  if (req.kullanici.rol !== "ogretmen" && req.kullanici.rol !== "yonetici") {
    if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
    return res.status(403).json({ hata: "Bu işlem için yetkiniz yok" });
  }
  const { soru_metni, cevap, aktif_tarih } = req.body;
  if (!cevap || !cevap.trim()) {
    if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
    return res.status(400).json({ hata: "Cevap alanı zorunludur" });
  }
  if (!aktif_tarih) {
    if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
    return res.status(400).json({ hata: "Tarih alanı zorunludur" });
  }
  // Soru metni veya görsel en az birisi olmalı
  if ((!soru_metni || !soru_metni.trim()) && !req.file) {
    return res.status(400).json({ hata: "Soru metni veya görsel en az birisi gereklidir" });
  }

  const kurumId = req.kullanici.kurum_id;
  const gorselUrl = req.file ? '/uploads/bulmaca/' + req.file.filename : null;

  try {
    await db.execute(
      `INSERT INTO zeka_bulmacalari (kurum_id, ekleyen_id, soru_metni, soru_gorsel, cevap, aktif_tarih)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [kurumId, req.kullanici.id, (soru_metni || '').trim() || null, gorselUrl, cevap.trim(), aktif_tarih]
    );
    icerikGuncellendiGonder(kurumId);
    res.json({ mesaj: "Bulmaca eklendi" });
  } catch (err) {
    if (req.file) bulmacaGorselSil(gorselUrl);
    if (err.code === "ER_DUP_ENTRY") {
      return res.status(400).json({ hata: "Bu tarihte zaten bir bulmaca mevcut" });
    }
    console.error("Bulmaca ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Bulmaca güncelle
app.put("/api/zeka-bulmacalari/:id", authMiddleware, (req, res, next) => {
  bulmacaUpload.single('gorsel')(req, res, (err) => {
    if (err) return res.status(400).json({ hata: err.message });
    next();
  });
}, async (req, res) => {
  const bulmacaId = parseInt(req.params.id);
  const { soru_metni, cevap, aktif_tarih } = req.body;
  try {
    const [mevcut] = await db.execute("SELECT * FROM zeka_bulmacalari WHERE id = ?", [bulmacaId]);
    if (mevcut.length === 0) {
      if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
      return res.status(404).json({ hata: "Bulmaca bulunamadı" });
    }
    const b = mevcut[0];
    if (req.kullanici.rol === "superadmin") {
      if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
      return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    }
    if (req.kullanici.rol === "ogretmen" && b.ekleyen_id !== req.kullanici.id) {
      if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
      return res.status(403).json({ hata: "Sadece kendi eklediğiniz bulmacaları düzenleyebilirsiniz" });
    }
    if (b.kurum_id !== req.kullanici.kurum_id) {
      if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
      return res.status(403).json({ hata: "Bu bulmacayı düzenleme yetkiniz yok" });
    }

    const yeniSoruMetni = soru_metni !== undefined ? ((soru_metni || '').trim() || null) : b.soru_metni;
    const yeniCevap = cevap ? cevap.trim() : b.cevap;
    const yeniTarih = aktif_tarih || b.aktif_tarih;

    let yeniGorselUrl = b.soru_gorsel;
    if (req.file) {
      bulmacaGorselSil(b.soru_gorsel);
      yeniGorselUrl = '/uploads/bulmaca/' + req.file.filename;
    }

    // Soru metni veya görsel en az birisi olmalı
    if (!yeniSoruMetni && !yeniGorselUrl) {
      if (req.file) bulmacaGorselSil(yeniGorselUrl);
      return res.status(400).json({ hata: "Soru metni veya görsel en az birisi gereklidir" });
    }

    await db.execute(
      `UPDATE zeka_bulmacalari SET soru_metni = ?, soru_gorsel = ?, cevap = ?, aktif_tarih = ? WHERE id = ?`,
      [yeniSoruMetni, yeniGorselUrl, yeniCevap, yeniTarih, bulmacaId]
    );
    icerikGuncellendiGonder(b.kurum_id);
    res.json({ mesaj: "Bulmaca güncellendi" });
  } catch (err) {
    if (req.file) bulmacaGorselSil('/uploads/bulmaca/' + req.file.filename);
    if (err.code === "ER_DUP_ENTRY") {
      return res.status(400).json({ hata: "Bu tarihte zaten bir bulmaca mevcut" });
    }
    console.error("Bulmaca güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Bulmaca sil
app.delete("/api/zeka-bulmacalari/:id", authMiddleware, async (req, res) => {
  const bulmacaId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM zeka_bulmacalari WHERE id = ?", [bulmacaId]);
    if (mevcut.length === 0) return res.status(404).json({ hata: "Bulmaca bulunamadı" });
    const b = mevcut[0];
    if (req.kullanici.rol === "superadmin") return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    if (req.kullanici.rol === "ogretmen" && b.ekleyen_id !== req.kullanici.id) return res.status(403).json({ hata: "Sadece kendi eklediğiniz bulmacaları silebilirsiniz" });
    if (b.kurum_id !== req.kullanici.kurum_id) return res.status(403).json({ hata: "Bu bulmacayı silme yetkiniz yok" });
    bulmacaGorselSil(b.soru_gorsel);
    await db.execute("DELETE FROM zeka_bulmacalari WHERE id = ?", [bulmacaId]);
    icerikGuncellendiGonder(b.kurum_id);
    res.json({ mesaj: "Bulmaca silindi" });
  } catch (err) {
    console.error("Bulmaca silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Duyurular =====================

// Duyuru listele (auth gerekli)
app.get("/api/duyurular", authMiddleware, async (req, res) => {
  try {
    let rows;
    if (req.kullanici.rol === "superadmin") {
      const kurumId = req.query.kurum_id ? parseInt(req.query.kurum_id) : null;
      if (kurumId) {
        [rows] = await db.execute(
          `SELECT d.*, k.ad_soyad AS ekleyen_adi,
                  GROUP_CONCAT(dt.tahta_id ORDER BY dt.tahta_id SEPARATOR ',') AS tahta_ids_str
           FROM duyurular d
           JOIN kullanicilar k ON d.ekleyen_id = k.id
           LEFT JOIN duyuru_tahtalar dt ON dt.duyuru_id = d.id
           WHERE d.kurum_id = ? GROUP BY d.id ORDER BY d.created_at DESC`,
          [kurumId]
        );
      } else {
        [rows] = await db.execute(
          `SELECT d.*, k.ad_soyad AS ekleyen_adi,
                  GROUP_CONCAT(dt.tahta_id ORDER BY dt.tahta_id SEPARATOR ',') AS tahta_ids_str
           FROM duyurular d
           JOIN kullanicilar k ON d.ekleyen_id = k.id
           LEFT JOIN duyuru_tahtalar dt ON dt.duyuru_id = d.id
           GROUP BY d.id ORDER BY d.created_at DESC`
        );
      }
    } else {
      [rows] = await db.execute(
        `SELECT d.*, k.ad_soyad AS ekleyen_adi,
                GROUP_CONCAT(dt.tahta_id ORDER BY dt.tahta_id SEPARATOR ',') AS tahta_ids_str
         FROM duyurular d
         JOIN kullanicilar k ON d.ekleyen_id = k.id
         LEFT JOIN duyuru_tahtalar dt ON dt.duyuru_id = d.id
         WHERE d.kurum_id = ? GROUP BY d.id ORDER BY d.created_at DESC`,
        [req.kullanici.kurum_id]
      );
    }
    res.json(rows);
  } catch (err) {
    console.error("Duyuru listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Duyuru listele (genel, tahta iklimleri için — kurum kodu veya tahta_id ile)
app.get("/api/duyurular-genel", async (req, res) => {
  try {
    const { kod, tahta_id } = req.query;
    let kurumId = null;
    if (tahta_id) {
      const [t] = await db.execute("SELECT kurum_id FROM tahtalar WHERE id = ?", [tahta_id]);
      if (t.length > 0) kurumId = t[0].kurum_id;
    } else if (kod) {
      const [k] = await db.execute("SELECT id FROM kurumlar WHERE kurum_kodu = ?", [kod]);
      if (k.length > 0) kurumId = k[0].id;
    }
    if (!kurumId) return res.json([]);
    let rows;
    if (tahta_id) {
      [rows] = await db.execute(
        `SELECT d.id, d.baslik, d.icerik, d.created_at, k.ad_soyad AS ekleyen_adi
         FROM duyurular d
         JOIN kullanicilar k ON d.ekleyen_id = k.id
         JOIN duyuru_tahtalar dt ON dt.duyuru_id = d.id
         WHERE d.kurum_id = ? AND dt.tahta_id = ? ORDER BY d.created_at DESC`,
        [kurumId, tahta_id]
      );
    } else {
      [rows] = await db.execute(
        `SELECT d.id, d.baslik, d.icerik, d.created_at, k.ad_soyad AS ekleyen_adi
         FROM duyurular d JOIN kullanicilar k ON d.ekleyen_id = k.id
         WHERE d.kurum_id = ? ORDER BY d.created_at DESC`,
        [kurumId]
      );
    }
    res.json(rows);
  } catch (err) {
    console.error("Duyuru genel listesi hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Duyuru ekle
app.post("/api/duyurular", authMiddleware, async (req, res) => {
  if (req.kullanici.rol !== "ogretmen" && req.kullanici.rol !== "yonetici") {
    return res.status(403).json({ hata: "Bu işlem için yetkiniz yok" });
  }
  const { baslik, icerik, tahta_ids } = req.body;
  if (!baslik || !icerik || !Array.isArray(tahta_ids) || tahta_ids.length === 0) {
    return res.status(400).json({ hata: "Başlık, içerik ve en az bir tahta gerekli" });
  }
  try {
    const [result] = await db.execute(
      "INSERT INTO duyurular (kurum_id, ekleyen_id, baslik, icerik) VALUES (?, ?, ?, ?)",
      [req.kullanici.kurum_id, req.kullanici.id, baslik.trim(), icerik.trim()]
    );
    const newId = result.insertId;
    for (const tid of tahta_ids) {
      await db.execute("INSERT IGNORE INTO duyuru_tahtalar (duyuru_id, tahta_id) VALUES (?, ?)", [newId, String(tid)]);
    }
    icerikGuncellendiGonder(req.kullanici.kurum_id);
    res.json({ mesaj: "Duyuru eklendi" });
  } catch (err) {
    console.error("Duyuru ekleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Duyuru güncelle
app.put("/api/duyurular/:id", authMiddleware, async (req, res) => {
  const duyuruId = parseInt(req.params.id);
  const { baslik, icerik, tahta_ids } = req.body;
  if (!baslik || !icerik || !Array.isArray(tahta_ids) || tahta_ids.length === 0) {
    return res.status(400).json({ hata: "Başlık, içerik ve en az bir tahta gerekli" });
  }
  try {
    const [mevcut] = await db.execute("SELECT * FROM duyurular WHERE id = ?", [duyuruId]);
    if (mevcut.length === 0) return res.status(404).json({ hata: "Duyuru bulunamadı" });
    const d = mevcut[0];
    if (req.kullanici.rol === "superadmin") return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    if (req.kullanici.rol === "ogretmen" && d.ekleyen_id !== req.kullanici.id) return res.status(403).json({ hata: "Sadece kendi duyurularınızı düzenleyebilirsiniz" });
    if (d.kurum_id !== req.kullanici.kurum_id) return res.status(403).json({ hata: "Bu duyuruyu düzenleme yetkiniz yok" });
    await db.execute(
      "UPDATE duyurular SET baslik = ?, icerik = ? WHERE id = ?",
      [baslik.trim(), icerik.trim(), duyuruId]
    );
    await db.execute("DELETE FROM duyuru_tahtalar WHERE duyuru_id = ?", [duyuruId]);
    for (const tid of tahta_ids) {
      await db.execute("INSERT INTO duyuru_tahtalar (duyuru_id, tahta_id) VALUES (?, ?)", [duyuruId, String(tid)]);
    }
    icerikGuncellendiGonder(d.kurum_id);
    res.json({ mesaj: "Duyuru güncellendi" });
  } catch (err) {
    console.error("Duyuru güncelleme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// Duyuru sil
app.delete("/api/duyurular/:id", authMiddleware, async (req, res) => {
  const duyuruId = parseInt(req.params.id);
  try {
    const [mevcut] = await db.execute("SELECT * FROM duyurular WHERE id = ?", [duyuruId]);
    if (mevcut.length === 0) return res.status(404).json({ hata: "Duyuru bulunamadı" });
    const d = mevcut[0];
    if (req.kullanici.rol === "superadmin") return res.status(403).json({ hata: "Süper yönetici bu işlemi yapamaz" });
    if (req.kullanici.rol === "ogretmen" && d.ekleyen_id !== req.kullanici.id) return res.status(403).json({ hata: "Sadece kendi duyurularınızı silebilirsiniz" });
    if (d.kurum_id !== req.kullanici.kurum_id) return res.status(403).json({ hata: "Bu duyuruyu silme yetkiniz yok" });
    await db.execute("DELETE FROM duyurular WHERE id = ?", [duyuruId]);
    icerikGuncellendiGonder(d.kurum_id);
    res.json({ mesaj: "Duyuru silindi" });
  } catch (err) {
    console.error("Duyuru silme hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== Doğrulama Kodu Üretici =====================
const KILIT_GIZLI_ANAHTAR = "tahta_ekran_secret_2024";
const KOD_UZUNLUGU = 4;
const KARAKTERLER = "0123456789";

function yanitUret(challengeKodu, gizliAnahtar) {
  const birlesmis = `${challengeKodu}:${gizliAnahtar}`;
  const h = crypto.createHash("sha256").update(birlesmis, "utf-8").digest();
  let kod = "";
  for (let i = 0; i < KOD_UZUNLUGU; i++) {
    kod += String(h[i] % KARAKTERLER.length);
  }
  return kod;
}

// Zaman tabanlı challenge kodu üret (Python tarafıyla aynı mantık)
const YENILEME_ARALIGI_SANIYE = 30;

function challengeUret(gizliAnahtar, zamanIndeksi) {
  const hashGirdisi = `${gizliAnahtar}:${zamanIndeksi}`;
  const h = crypto.createHmac("sha256", gizliAnahtar).update(hashGirdisi, "utf-8").digest();
  let kod = "";
  for (let i = 0; i < KOD_UZUNLUGU; i++) {
    kod += String(h[i] % KARAKTERLER.length);
  }
  return kod;
}

function challengeDogrula(challenge, gizliAnahtar) {
  // Mevcut ve ±1 zaman penceresini kontrol et (zamanlama toleransı)
  const simdikiIndeks = Math.floor(Date.now() / 1000 / YENILEME_ARALIGI_SANIYE);
  for (let ofset = -1; ofset <= 1; ofset++) {
    const beklenen = challengeUret(gizliAnahtar, simdikiIndeks + ofset);
    if (beklenen === challenge) return true;
  }
  return false;
}

app.post("/api/dogrulama-kodu", authMiddleware, async (req, res) => {
  const { challenge, tahtaId } = req.body;
  if (!challenge || typeof challenge !== "string") {
    return res.status(400).json({ hata: "Challenge kodu gerekli" });
  }
  if (!tahtaId || typeof tahtaId !== "string") {
    return res.status(400).json({ hata: "Tahta ID gerekli" });
  }
  try {
    let rows;
    if (req.kullanici.rol === "superadmin") {
      [rows] = await db.execute(
        `SELECT k.anahtar AS kurum_anahtari FROM tahtalar t
         JOIN kurumlar k ON t.kurum_id = k.id
         WHERE t.id = ?`, [tahtaId]);
    } else {
      [rows] = await db.execute(
        `SELECT k.anahtar AS kurum_anahtari FROM tahtalar t
         JOIN kurumlar k ON t.kurum_id = k.id
         WHERE t.id = ? AND t.kurum_id = ?`, [tahtaId, req.kullanici.kurum_id]);
    }
    if (rows.length === 0) {
      return res.status(404).json({ hata: "Tahta bulunamadı" });
    }
    const anahtar = rows[0].kurum_anahtari || KILIT_GIZLI_ANAHTAR;
    const yanit = yanitUret(challenge, anahtar);
    res.json({ yanit });
  } catch (err) {
    console.error("Doğrulama kodu hatası:", err);
    res.status(500).json({ hata: "Sunucu hatası" });
  }
});

// ===================== İşlem Kayıt Yardımcı Fonksiyonları =====================
async function logKaydet(kurumId, tahtaId, tahtaAdi, kullaniciId, kullaniciAdi, adSoyad, rol, aksiyon) {
  try {
    await db.execute(
      `INSERT INTO tahta_loglari (kurum_id, tahta_id, tahta_adi, kullanici_id, kullanici_adi, ad_soyad, rol, aksiyon)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [kurumId, tahtaId || null, tahtaAdi || '', kullaniciId || null, kullaniciAdi || '', adSoyad || '', rol || 'ogretmen', aksiyon]
    );
  } catch (e) {
    console.error('[LOG] Kayıt hatası:', e.message);
  }
}

async function eskiLoglariTemizle() {
  try {
    const [result] = await db.execute(
      `DELETE FROM tahta_loglari WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 MONTH)`
    );
    if (result.affectedRows > 0) {
      console.log(`[LOG TEMİZLİK] ${result.affectedRows} eski kayıt silindi`);
    }
  } catch (e) {
    console.error('[LOG TEMİZLİK] Hata:', e.message);
  }
}

// ===================== İşlem Kayıtları API =====================
app.get('/api/loglar', authMiddleware, adminMiddleware, async (req, res) => {
  try {
    const { tahta_id, aksiyon, tarih_baslangic, tarih_bitis, arama } = req.query;
    const limitNum = Math.min(parseInt(req.query.limit) || 50, 200);
    const offsetNum = Math.max(parseInt(req.query.offset) || 0, 0);

    const kurumId = req.query.kurum_id && req.kullanici.rol === 'superadmin'
      ? parseInt(req.query.kurum_id)
      : req.kullanici.kurum_id;

    const kosullar = ['kurum_id = ?'];
    const params = [kurumId];

    if (tahta_id) { kosullar.push('tahta_id = ?'); params.push(tahta_id); }
    if (aksiyon) { kosullar.push('aksiyon = ?'); params.push(aksiyon); }
    if (tarih_baslangic) { kosullar.push('created_at >= ?'); params.push(tarih_baslangic + ' 00:00:00'); }
    if (tarih_bitis) { kosullar.push('created_at <= ?'); params.push(tarih_bitis + ' 23:59:59'); }
    if (arama) {
      kosullar.push('(ad_soyad LIKE ? OR kullanici_adi LIKE ? OR tahta_adi LIKE ?)');
      params.push(`%${arama}%`, `%${arama}%`, `%${arama}%`);
    }

    const where = kosullar.join(' AND ');
    const [rows] = await db.execute(
      `SELECT * FROM tahta_loglari WHERE ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`,
      [...params, limitNum, offsetNum]
    );
    const [[{ toplam }]] = await db.execute(
      `SELECT COUNT(*) AS toplam FROM tahta_loglari WHERE ${where}`,
      params
    );

    res.json({ loglar: rows, toplam });
  } catch (err) {
    console.error('Log listesi hatası:', err);
    res.status(500).json({ hata: 'Sunucu hatası' });
  }
});

// ===================== Statik Dosyalar =====================
app.use(express.static(path.join(__dirname, "public")));

// Ana sayfa → panel
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "panel.html"));
});

// Kurum bilgi sayfası (webview için)
app.get("/kurum", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "kurum.html"));
});

// Kurum adı API (kurum kodu ile sorgulama — auth gerektirmez)
app.get("/api/kurum-adi", async (req, res) => {
  const { kod, tahta_id } = req.query;
  if (!kod && !tahta_id) return res.json({ kurum_adi: "" });
  try {
    // Önce kurum_kodu ile ara
    if (kod) {
      const [rows] = await db.execute("SELECT kurum_adi FROM kurumlar WHERE kurum_kodu = ?", [kod]);
      if (rows.length > 0) return res.json({ kurum_adi: rows[0].kurum_adi });
    }
    // Fallback: tahta_id üzerinden kurum adını bul
    if (tahta_id) {
      const [rows2] = await db.execute(
        "SELECT k.kurum_adi FROM kurumlar k INNER JOIN tahtalar t ON t.kurum_id = k.id WHERE t.id = ? LIMIT 1",
        [tahta_id]
      );
      if (rows2.length > 0) return res.json({ kurum_adi: rows2[0].kurum_adi });
    }
    res.json({ kurum_adi: "" });
  } catch (e) {
    res.json({ kurum_adi: "" });
  }
});

// ===================== Socket.IO =====================
// Bağlı tahtaları takip eden obje: { socketId: { tahtaId, kurumId, kurumKodu } }
const bagliTahtalar = {};
// Kapanma geri sayımı (bellekte, VT'de değil): { tahtaId: kalanSaniye }
const kapanmaGeriSayim = {};
// Kilit geri sayımı (bellekte, VT'de değil): { tahtaId: kalanSaniye }
const kilitGeriSayim = {};

io.on("connection", (socket) => {
  console.log(`[+] Bağlantı: ${socket.id}`);

  // ---- Tahta kendini kayıt eder ----
  socket.on("tahta_kayit", async (veri) => {
    const tahtaId = veri.tahtaId;
    if (!tahtaId) {
      socket.emit("hata", { mesaj: "Tahta ID gerekli" });
      socket.disconnect();
      return;
    }

    try {
      // Veritabanında kayıtlı mı kontrol et (kurum anahtarını da çek)
      const [rows] = await db.execute(
        `SELECT t.*, k.kurum_kodu, k.anahtar AS kurum_anahtari, k.kurum_adi
         FROM tahtalar t
         JOIN kurumlar k ON t.kurum_id = k.id
         WHERE t.id = ?`,
        [tahtaId]
      );

      if (rows.length === 0) {
        socket.emit("hata", {
          mesaj: "Bu tahta kayıtlı değil. Yöneticinize başvurun.",
        });
        socket.disconnect();
        return;
      }

      const tahta = rows[0];

      const ipAdresi = socket.handshake.headers["x-forwarded-for"]?.split(",")[0]?.trim() || socket.handshake.address;
      const ilkBaglanti = tahta.son_baglanti === null;

      // HMAC tabanlı anahtar doğrulaması (kurum anahtarı kullanılır)
      if (tahta.kurum_anahtari) {
        const hmacImza = veri.hmac || '';
        const zamanDamgasi = veri.zaman || 0;
        // Zaman damgası ±60 saniye tolerans
        const simdiki = Math.floor(Date.now() / 1000);
        if (Math.abs(simdiki - zamanDamgasi) > 60) {
          console.warn(`[GÜVENLİK] ${tahtaId} — zaman damgası geçersiz (fark: ${simdiki - zamanDamgasi}s)`);
          socket.emit("hata", { mesaj: "Kimlik doğrulama başarısız. Zaman damgası geçersiz." });
          socket.disconnect();
          return;
        }
        // HMAC doğrula: HMAC-SHA256(tahtaId:zaman, kurumAnahtari)
        const beklenenHmac = crypto.createHmac('sha256', tahta.kurum_anahtari)
          .update(`${tahtaId}:${zamanDamgasi}`)
          .digest('hex');
        if (hmacImza !== beklenenHmac) {
          console.warn(`[GÜVENLİK] ${tahtaId} — geçersiz HMAC imza, bağlantı reddedildi`);
          socket.emit("hata", { mesaj: "Kimlik doğrulama başarısız. Geçersiz anahtar." });
          socket.disconnect();
          return;
        }
      }

      if (ilkBaglanti) {
        // İlk bağlantı: tahta bilgilerini sunucuya kaydet (tahta durumu baz alınır)
        const gercekDurum = veri.durum !== undefined ? veri.durum : tahta.durum;
        const gercekSes = veri.ses !== undefined ? veri.ses : tahta.ses;
        await db.execute(
          `UPDATE tahtalar SET tahta_adi = ?, cevrimici = 1, ip_adresi = ?, son_baglanti = NOW(), durum = ?, ses = ? WHERE id = ?`,
          [veri.tahtaAdi || tahta.tahta_adi, ipAdresi, gercekDurum, gercekSes, tahtaId]
        );
        // İlk bağlantıda tahtanın kendi durumunu geri gönder
        socket.emit("durum_bilgisi", { durum: gercekDurum, ses: gercekSes, kurum_adi: tahta.kurum_adi, kurum_kodu: tahta.kurum_kodu });
      } else {
        // Sonraki bağlantılar: sunucu durumu baz alınır (tahta_adi, durum/ses ve anahtar güncellenmez)
        await db.execute(
          `UPDATE tahtalar SET cevrimici = 1, ip_adresi = ?, son_baglanti = NOW() WHERE id = ?`,
          [ipAdresi, tahtaId]
        );
        // Sunucudaki mevcut durumu ve adı tahtaya gönder (tahta buna göre senkronize olacak)
        socket.emit("durum_bilgisi", { durum: tahta.durum, ses: tahta.ses, tahta_adi: tahta.tahta_adi, kurum_adi: tahta.kurum_adi, kurum_kodu: tahta.kurum_kodu });
      }

      bagliTahtalar[socket.id] = {
        tahtaId,
        kurumId: tahta.kurum_id,
        kurumKodu: tahta.kurum_kodu,
      };

      socket.join(`kurum_${tahta.kurum_id}`);
      socket.tahtaId = tahtaId;

      console.log(
        `[KAYIT] Tahta: ${veri.tahtaAdi || tahtaId} (Kurum: ${tahta.kurum_kodu})${ilkBaglanti ? " [İLK BAĞLANTI]" : ""}`
      );

      // Ders çıkış saatlerini tahtaya gönder
      try {
        const dersSaatleriVerisi = await dersSaatleriAl(tahta.kurum_id);
        socket.emit("ders_saatleri", dersSaatleriVerisi);
      } catch (e) {
        console.error("Ders saatleri gönderilemedi:", e);
      }

      // Sınavları tahtaya gönder
      try {
        const sinavVerisi = await sinavlarAlTahta(tahtaId);
        socket.emit("sinavlar", sinavVerisi);
      } catch (e) {
        console.error("Sınavlar gönderilemedi:", e);
      }

      // Panellere güncel listeyi gönder
      await panellereGonder(tahta.kurum_id);
    } catch (err) {
      console.error("Tahta kayıt hatası:", err);
      socket.emit("hata", { mesaj: "Sunucu hatası" });
      socket.disconnect();
    }
  });

  // ---- Panel kendini kayıt eder (JWT ile) ----
  socket.on("panel_kayit", async (token) => {
    try {
      const decoded = jwt.verify(token, JWT_SECRET);
      socket.kullanici = decoded;
      socket.join(`panel_kurum_${decoded.kurum_id}`);
      socket.join("panel");

      let liste;
      if (decoded.rol === "superadmin") {
        // Superadmin tüm kurumların tahtalarını görür
        socket.join("panel_superadmin");
        liste = await tahtaListesiAlTumu();
      } else {
        liste = await tahtaListesiAl(decoded.kurum_id);
      }
      socket.emit("tahta_listesi", liste);
      console.log(
        `[PANEL] ${decoded.ad_soyad} (${decoded.rol}) bağlandı`
      );
    } catch {
      socket.emit("hata", { mesaj: "Geçersiz oturum" });
      socket.disconnect();
    }
  });

  // ---- Kilitle ----
  socket.on("kilitle", async (tahtaId) => {
    if (!socket.kullanici) return;
    try {
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) return;

      await db.execute("UPDATE tahtalar SET durum = 1 WHERE id = ?", [tahtaId]);
      tahtayaKomutGonder(tahtaId, "kilitle");
      await panellereGonder(tahta.kurum_id);
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'kilitle');
      console.log(
        `[KİLİT] ${tahta.tahta_adi} kilitlendi (${socket.kullanici.ad_soyad})`
      );
    } catch (err) {
      console.error("Kilitleme hatası:", err);
    }
  });

  // ---- Kilidi Aç ----
  socket.on("kilidi_ac", async (tahtaId) => {
    if (!socket.kullanici) return;
    try {
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) return;

      await db.execute("UPDATE tahtalar SET durum = 0 WHERE id = ?", [tahtaId]);
      tahtayaKomutGonder(tahtaId, "kilidi_ac");
      await panellereGonder(tahta.kurum_id);
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'kilidi_ac');
      console.log(
        `[AÇ] ${tahta.tahta_adi} açıldı (${socket.kullanici.ad_soyad})`
      );
    } catch (err) {
      console.error("Kilit açma hatası:", err);
    }
  });

  // ---- QR ile Kilidi Aç (challenge doğrulamalı) ----
  socket.on("kilidi_ac_qr", async (veri, geriCagir) => {
    if (!socket.kullanici) return;
    const cb = typeof geriCagir === "function" ? geriCagir : () => {};
    try {
      const { tahtaId, challenge } = veri || {};
      if (!tahtaId || !challenge) {
        return cb({ basarili: false, hata: "Tahta ID ve challenge kodu gerekli" });
      }
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) {
        return cb({ basarili: false, hata: "Tahta bulunamadı" });
      }
      // Challenge kodunu doğrula (kurum anahtarı kullanılır)
      const anahtar = tahta.kurum_anahtari || KILIT_GIZLI_ANAHTAR;
      if (!challengeDogrula(challenge, anahtar)) {
        console.log(`[QR REDDEDILDI] ${tahta.tahta_adi} — geçersiz/süresi dolmuş challenge (${socket.kullanici.ad_soyad})`);
        return cb({ basarili: false, hata: "Challenge kodu geçersiz veya süresi dolmuş. Lütfen güncel QR kodu okutun." });
      }
      await db.execute("UPDATE tahtalar SET durum = 0 WHERE id = ?", [tahtaId]);
      tahtayaKomutGonder(tahtaId, "kilidi_ac");
      await panellereGonder(tahta.kurum_id);
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'kilidi_ac');
      console.log(`[QR AÇ] ${tahta.tahta_adi} açıldı (${socket.kullanici.ad_soyad})`);
      cb({ basarili: true });
    } catch (err) {
      console.error("QR kilit açma hatası:", err);
      cb({ basarili: false, hata: "Sunucu hatası" });
    }
  });

  // ---- Sesi Kapat ----
  socket.on("ses_kapat", async (tahtaId) => {
    if (!socket.kullanici) return;
    try {
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) return;

      await db.execute("UPDATE tahtalar SET ses = 0 WHERE id = ?", [tahtaId]);
      tahtayaKomutGonder(tahtaId, "ses_kapat");
      await panellereGonder(tahta.kurum_id);
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'ses_kapat');
    } catch (err) {
      console.error("Ses kapatma hatası:", err);
    }
  });

  // ---- Sesi Aç ----
  socket.on("ses_ac", async (tahtaId) => {
    if (!socket.kullanici) return;
    try {
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) return;

      await db.execute("UPDATE tahtalar SET ses = 1 WHERE id = ?", [tahtaId]);
      tahtayaKomutGonder(tahtaId, "ses_ac");
      await panellereGonder(tahta.kurum_id);
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'ses_ac');
    } catch (err) {
      console.error("Ses açma hatası:", err);
    }
  });

  // ---- Video Aç/Kapat ----
  socket.on("video_toggle", async (tahtaId) => {
    if (!socket.kullanici) return;
    try {
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) return;
      tahtayaKomutGonder(tahtaId, "video_toggle");
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'video_toggle');
    } catch (err) {
      console.error("Video toggle hatası:", err);
    }
  });

  // ---- Tahta Kapat ----
  socket.on("tahta_kapat", async (tahtaId) => {
    if (!socket.kullanici) return;
    if (socket.kullanici.rol === "ogretmen") return;
    try {
      const tahta = await tahtaBul(tahtaId, socket.kullanici.kurum_id, socket.kullanici.rol);
      if (!tahta) return;

      tahtayaKomutGonder(tahtaId, "tahta_kapat");
      await panellereGonder(tahta.kurum_id);
      logKaydet(tahta.kurum_id, tahtaId, tahta.tahta_adi,
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'tahta_kapat');
      console.log(
        `[KAPAT] ${tahta.tahta_adi} kapatıldı (${socket.kullanici.ad_soyad})`
      );
    } catch (err) {
      console.error("Tahta kapatma hatası:", err);
    }
  });

  // ---- Tümünü Kapat ----
  socket.on("tumu_kapat", async () => {
    if (!socket.kullanici) return;
    if (socket.kullanici.rol === "ogretmen") return;

    try {
      if (socket.kullanici.rol === "superadmin") {
        Object.entries(bagliTahtalar).forEach(([sid]) => {
          io.to(sid).emit("komut", { aksiyon: "tahta_kapat" });
        });
        const [kurumlar] = await db.execute("SELECT id FROM kurumlar");
        for (const k of kurumlar) {
          await panellereGonder(k.id);
        }
      } else {
        const kurumId = socket.kullanici.kurum_id;
        Object.entries(bagliTahtalar).forEach(([sid, t]) => {
          if (t.kurumId === kurumId) {
            io.to(sid).emit("komut", { aksiyon: "tahta_kapat" });
          }
        });
        await panellereGonder(kurumId);
      }
      logKaydet(socket.kullanici.kurum_id, null, 'Tüm Tahtalar',
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'tumu_kapat');
      console.log(
        `[TOPLU KAPAT] ${socket.kullanici.rol} (${socket.kullanici.ad_soyad})`
      );
    } catch (err) {
      console.error("Toplu kapatma hatası:", err);
    }
  });

  // ---- Tümünü Kilitle ----
  socket.on("tumu_kilitle", async () => {
    if (!socket.kullanici) return;
    if (socket.kullanici.rol === "ogretmen") return;

    try {
      if (socket.kullanici.rol === "superadmin") {
        await db.execute("UPDATE tahtalar SET durum = 1");
        Object.entries(bagliTahtalar).forEach(([sid, t]) => {
          io.to(sid).emit("komut", { aksiyon: "kilitle" });
        });
        // Tüm kurumlara bildir
        const [kurumlar] = await db.execute("SELECT id FROM kurumlar");
        for (const k of kurumlar) {
          await panellereGonder(k.id);
        }
      } else {
        const kurumId = socket.kullanici.kurum_id;
        await db.execute("UPDATE tahtalar SET durum = 1 WHERE kurum_id = ?", [
          kurumId,
        ]);
        Object.entries(bagliTahtalar).forEach(([sid, t]) => {
          if (t.kurumId === kurumId) {
            io.to(sid).emit("komut", { aksiyon: "kilitle" });
          }
        });
        await panellereGonder(kurumId);
      }
      logKaydet(socket.kullanici.kurum_id, null, 'Tüm Tahtalar',
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'tumu_kilitle');
      console.log(
        `[TOPLU KİLİT] ${socket.kullanici.rol} (${socket.kullanici.ad_soyad})`
      );
    } catch (err) {
      console.error("Toplu kilitleme hatası:", err);
    }
  });

  // ---- Tümünü Aç ----
  socket.on("tumu_ac", async () => {
    if (!socket.kullanici) return;
    if (socket.kullanici.rol === "ogretmen") return;

    try {
      if (socket.kullanici.rol === "superadmin") {
        await db.execute("UPDATE tahtalar SET durum = 0");
        Object.entries(bagliTahtalar).forEach(([sid, t]) => {
          io.to(sid).emit("komut", { aksiyon: "kilidi_ac" });
        });
        const [kurumlar] = await db.execute("SELECT id FROM kurumlar");
        for (const k of kurumlar) {
          await panellereGonder(k.id);
        }
      } else {
        const kurumId = socket.kullanici.kurum_id;
        await db.execute("UPDATE tahtalar SET durum = 0 WHERE kurum_id = ?", [
          kurumId,
        ]);
        Object.entries(bagliTahtalar).forEach(([sid, t]) => {
          if (t.kurumId === kurumId) {
            io.to(sid).emit("komut", { aksiyon: "kilidi_ac" });
          }
        });
        await panellereGonder(kurumId);
      }
      logKaydet(socket.kullanici.kurum_id, null, 'Tüm Tahtalar',
        socket.kullanici.id, socket.kullanici.kullanici_adi,
        socket.kullanici.ad_soyad, socket.kullanici.rol, 'tumu_ac');
      console.log(
        `[TOPLU AÇ] ${socket.kullanici.rol} (${socket.kullanici.ad_soyad})`
      );
    } catch (err) {
      console.error("Toplu açma hatası:", err);
    }
  });

  // ---- Tahta durum güncelleme (tahtadan gelen) ----
  socket.on("tahta_durum_guncelle", async (veri) => {
    const bilgi = bagliTahtalar[socket.id];
    if (!bilgi) return;

    const durum = veri.durum !== undefined ? veri.durum : null;
    const ses = veri.ses !== undefined ? veri.ses : null;

    try {
      if (durum !== null && ses !== null) {
        await db.execute("UPDATE tahtalar SET durum = ?, ses = ? WHERE id = ?", [durum, ses, bilgi.tahtaId]);
      } else if (durum !== null) {
        await db.execute("UPDATE tahtalar SET durum = ? WHERE id = ?", [durum, bilgi.tahtaId]);
      } else if (ses !== null) {
        await db.execute("UPDATE tahtalar SET ses = ? WHERE id = ?", [ses, bilgi.tahtaId]);
      }

      await panellereGonder(bilgi.kurumId);
      console.log(`[DURUM] Tahta ${bilgi.tahtaId}: durum=${durum}, ses=${ses}`);
    } catch (err) {
      console.error("Tahta durum güncelleme hatası:", err);
    }
  });

  // ---- Kapanma Geri Sayımı (bellekte, VT'de değil) ----
  socket.on("kapanma_geri_sayim", (veri) => {
    const bilgi = bagliTahtalar[socket.id];
    if (!bilgi) return;
    const kalan = typeof veri.kalan === "number" ? veri.kalan : -1;
    kapanmaGeriSayim[bilgi.tahtaId] = kalan;
    // Panellere güncel listeyi gönder
    panellereGonder(bilgi.kurumId).catch(() => {});
  });

  // ---- Kilit Geri Sayımı (bellekte, VT'de değil) ----
  socket.on("kilit_geri_sayim", (veri) => {
    const bilgi = bagliTahtalar[socket.id];
    if (!bilgi) return;
    const kalan = typeof veri.kalan === "number" ? veri.kalan : -1;
    if (kalan < 0) {
      delete kilitGeriSayim[bilgi.tahtaId];
    } else {
      kilitGeriSayim[bilgi.tahtaId] = kalan;
    }
    panellereGonder(bilgi.kurumId).catch(() => {});
  });

  // ---- Bağlantı Koptu ----
  socket.on("disconnect", async () => {
    const bilgi = bagliTahtalar[socket.id];
    if (bilgi) {
      try {
        delete bagliTahtalar[socket.id];
        delete kapanmaGeriSayim[bilgi.tahtaId];
        delete kilitGeriSayim[bilgi.tahtaId];

        // Aynı tahta için başka aktif socket var mı kontrol et
        const baskaAktifVar = Object.values(bagliTahtalar).some(
          (t) => t.tahtaId === bilgi.tahtaId
        );
        if (!baskaAktifVar) {
          await db.execute("UPDATE tahtalar SET cevrimici = 0 WHERE id = ?", [
            bilgi.tahtaId,
          ]);
        }
        await panellereGonder(bilgi.kurumId);
        console.log(`[-] Tahta ayrıldı: ${bilgi.tahtaId} (başka aktif: ${baskaAktifVar})`);
      } catch (err) {
        console.error("Disconnect hatası:", err);
      }
    }
  });
});

// ===================== Yardımcı Fonksiyonlar =====================
async function tahtaBul(tahtaId, kurumId, rol) {
  let rows;
  if (rol === "superadmin") {
    // Superadmin tüm tahtaları kontrol edebilir
    [rows] = await db.execute(
      `SELECT t.*, k.anahtar AS kurum_anahtari FROM tahtalar t
       JOIN kurumlar k ON t.kurum_id = k.id
       WHERE t.id = ?`,
      [tahtaId]
    );
  } else {
    [rows] = await db.execute(
      `SELECT t.*, k.anahtar AS kurum_anahtari FROM tahtalar t
       JOIN kurumlar k ON t.kurum_id = k.id
       WHERE t.id = ? AND t.kurum_id = ?`,
      [tahtaId, kurumId]
    );
  }
  return rows.length > 0 ? rows[0] : null;
}

async function dersSaatleriAl(kurumId) {
  const [saatler] = await db.execute(
    "SELECT sira, saat FROM ders_saatleri WHERE kurum_id = ? ORDER BY sira",
    [kurumId]
  );
  const [kurumRows] = await db.execute(
    "SELECT ders_saatleri_aktif FROM kurumlar WHERE id = ?",
    [kurumId]
  );
  const aktif = kurumRows.length > 0 ? kurumRows[0].ders_saatleri_aktif : 0;
  return { aktif, saatler };
}

async function sinavlarAlTahta(tahtaId) {
  const [rows] = await db.execute(
    `SELECT s.id, s.ders_adi, s.sinav_tarihi, s.ders_saati_baslangic, s.ders_saati_bitis,
            k.ad_soyad AS ekleyen_adi
     FROM sinavlar s
     LEFT JOIN kullanicilar k ON s.ekleyen_id = k.id
     WHERE s.sinav_tarihi >= CURDATE()
       AND JSON_CONTAINS(s.tahtalar, ?)
     ORDER BY s.sinav_tarihi ASC, s.ders_saati_baslangic ASC
     LIMIT 20`,
    [JSON.stringify(tahtaId)]
  );
  return rows;
}

async function sinavlariGuncelleTahtalar(kurumId) {
  for (const [sid, bilgi] of Object.entries(bagliTahtalar)) {
    if (bilgi.kurumId === parseInt(kurumId)) {
      try {
        const sinavlar = await sinavlarAlTahta(bilgi.tahtaId);
        io.to(sid).emit("sinavlar", sinavlar);
      } catch (e) {
        console.error("Sınav güncelleme hatası:", e);
      }
    }
  }
}

function tahtayaKomutGonder(tahtaId, aksiyon) {
  for (const [sid, bilgi] of Object.entries(bagliTahtalar)) {
    if (bilgi.tahtaId === tahtaId) {
      io.to(sid).emit("komut", { aksiyon });
      break;
    }
  }
}

async function tahtaListesiAl(kurumId) {
  const [rows] = await db.execute(
    `SELECT t.*, k.kurum_kodu, k.kurum_adi
     FROM tahtalar t
     JOIN kurumlar k ON t.kurum_id = k.id
     WHERE t.kurum_id = ?
     ORDER BY t.tahta_adi`,
    [kurumId]
  );
  return rows.map(r => ({ ...r, kapanma_kalan: kapanmaGeriSayim[r.id] ?? null, kilit_kalan: kilitGeriSayim[r.id] ?? null }));
}

async function tahtaListesiAlTumu() {
  const [rows] = await db.execute(
    `SELECT t.*, k.kurum_kodu, k.kurum_adi
     FROM tahtalar t
     JOIN kurumlar k ON t.kurum_id = k.id
     ORDER BY k.kurum_adi, t.tahta_adi`
  );
  return rows.map(r => ({ ...r, kapanma_kalan: kapanmaGeriSayim[r.id] ?? null, kilit_kalan: kilitGeriSayim[r.id] ?? null }));
}

async function panellereGonder(kurumId) {
  const liste = await tahtaListesiAl(kurumId);
  io.to(`panel_kurum_${kurumId}`).emit("tahta_listesi", liste);
  // Superadmin panellerine de tüm listeyi gönder
  const tumListe = await tahtaListesiAlTumu();
  io.to("panel_superadmin").emit("tahta_listesi", tumListe);
}

// ===================== Sunucuyu Başlat =====================
const PORT = process.env.PORT || 3000;

veritabaniBaslat()
  .then(() => ilkKurulum())
  .then(() => {
    // Eski logları temizle (başlangıçta ve her 24 saatte bir)
    eskiLoglariTemizle();
    setInterval(eskiLoglariTemizle, 24 * 60 * 60 * 1000);

    server.listen(PORT, () => {
      console.log(`Tahta Kilit Sunucusu çalışıyor → http://localhost:${PORT}`);
    });
  })
  .catch((err) => {
    console.error("Sunucu başlatılamadı:", err);
    process.exit(1);
  });
