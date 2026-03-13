/*
  ============================================================
  Tahta Kilit - Kapı Otomasyon Kontrolcüsü (WT32-ETH01)
  ============================================================
  Bu kod WT32-ETH01 kartına yüklenir.
  Sunucuya wss:// (TLS) üzerinden Ethernet ile bağlanır.
  MEB kök sertifikası ile güvenli bağlantı kurar.
  Panelden gelen "kapi_ac" komutunu dinler ve röleyi tetikler.

  Donanım:
    - WT32-ETH01 (ESP32 + Ethernet)
    - Röle modülü → GPIO2 pinine bağlı
    - Manyetik kapı sensörü (opsiyonel) → GPIO4 pinine bağlı

  Kütüphane gereksinimleri (Arduino IDE / PlatformIO):
    - ArduinoJson (>= 6.x)
    - WebSockets by Markus Sattler (>= 2.4.0)
    - ETH.h (ESP32 çekirdeğinde mevcut)
  ============================================================
*/

#include <ETH.h>
#include <WiFiClientSecure.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ===================== YAPILANDIRMA =====================

// Sunucu bilgileri
#define SUNUCU_HOST     "kulumtal.com"
#define SUNUCU_PORT     443
#define SOCKETIO_PATH   "/socket.io/?EIO=4&transport=websocket"

// Kurum bilgileri — HER KURUMUN KENDİ BİLGİLERİ GİRİLMELİ
#define KURUM_KODU      "000000"        // Kurumunuzun kodu
#define CIHAZ_ID        "kapi_ana_giris" // Bu cihazın benzersiz kimliği
#define CIHAZ_ADI       "Ana Giriş Kapısı" // Panelde görünecek ad

// Donanım pinleri
#define ROLE_PIN        2    // Röle kontrol pini
#define KAPI_SENSOR_PIN 4    // Manyetik kapı sensörü (opsiyonel, kullanılmıyorsa -1 yapın)
#define LED_PIN         5    // Durum LED'i (opsiyonel)

// Zamanlama
#define ROLE_SURE_MS        3000     // Röle açık kalma süresi (ms)
#define YENIDEN_BAGLANTI_MS 5000     // Bağlantı kopunca bekleme süresi (ms)
#define HEARTBEAT_MS        25000    // Sunucuya ping gönderme aralığı (ms)
#define HW_RESET_ARALIK_MS  21600000 // Donanım sıfırlama aralığı — 6 saat (ms)
#define ETH_BASLAMA_BEKLEME 10000    // Ethernet bağlantı bekleme süresi (ms)

// ===================== MEB KÖK SERTİFİKASI =====================
// https://sertifika.meb.gov.tr/MEB_SERTIFIKASI.cer
// PEM formatına dönüştürülmüş hali (openssl x509 -inform DER -in MEB_SERTIFIKASI.cer -out meb.pem)
// NOT: Bu sertifikayı indirip PEM formatına çevirmeniz gerekir.
// Aşağıda yer tutucu olarak bırakılmıştır. Gerçek sertifika ile değiştirin.
static const char* meb_kök_sertifika = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDfzCCAmegAwIBAgIQYazX7ESZkLxDARAO7Iyu2jANBgkqhkiG9w0BAQsFADBS
MRIwEAYKCZImiZPyLGQBGRYCdHIxEzARBgoJkiaJk/IsZAEZFgNnb3YxFTATBgoJ
kiaJk/IsZAEZFgVtZWJjYTEQMA4GA1UEAxMHZmF0aWhjYTAeFw0xNjAzMDkxNTM2
MjVaFw0zNjAzMDkxNTQ2MjVaMFIxEjAQBgoJkiaJk/IsZAEZFgJ0cjETMBEGCgmS
JomT8ixkARkWA2dvdjEVMBMGCgmSJomT8ixkARkWBW1lYmNhMRAwDgYDVQQDEwdm
YXRpaGNhMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwV3KFFTIoP3Q
j99VEocbGVYbRfAZ7i/tVsjeC7cdNc4m5UJginq68Pwu5Mk32G2Dy1zBoOJYyXyo
nf/KWnaMrp7N/5gCBLw7rNoSS8AXhmMQCw7AECDdcJT4jNIB2xuKY6+xq0SeqhB6
ZohFM/NIP9mEk1pa1RcM3BE/X8qLPxgqnJHCqceuqaut/J/dErcNW1WYjG7REf8G
v+h9bs+IDp0QUtXOt1/117c2aaGPUshXS5Vy4y3D61nDLQBF2sW+kjnVT8nheCkQ
4v5x4Aa9tT7IZJnWAaAAdRl61dZ3c2x+Lawd/47Jzwf3xGAowSV70ctteJ3vYp4O
xkMUa7vYFQIDAQABo1EwTzALBgNVHQ8EBAMCAYYwDwYDVR0TAQH/BAUwAwEB/zAd
BgNVHQ4EFgQU/vlLQqALawQN3grbFGcX13fSWkowEAYJKwYBBAGCNxUBBAMCAQAw
DQYJKoZIhvcNAQELBQADggEBAIEjFGJQjxqvATP9Lhq4TkuWcc6Pa0Nnc/fKVgsC
LASiDlF5HogcktDSjapO6w+oT3bHvUnEJVsr2TwW0YrdHbuD/ZEsmZ6dYTTPxZtQ
TFPFroMr8yAOs2F+rUOc2wVCmd7GmSz4TWWCsltl5kNrlHZ9/0aGwV2EXwBfmM9z
b8c4THA24LukeCrEGRPVb2IX4ZmG/a6pF1lBuFo27kh2nz98sB4H5sJG5SozWBF/
sfiOV5hYvXQpheBG8HaiMzhjekKgL0rQLno0fgasjrZX3KMkCcxPPoiitu0AFkEB
jB12iv+M0D3N9kmIxeFN6yH7k9rtHUUuXWTSjSB99Fdv6qA=
-----END CERTIFICATE-----
)EOF";

// ===================== GLOBAL DEĞİŞKENLER =====================
WebSocketsClient webSocket;
WiFiClientSecure *secureClient = nullptr;

bool ethBaglandi = false;
bool sunucuBagli = false;
bool kayitGonderildi = false;
unsigned long sonHeartbeat = 0;
unsigned long sonYenidenBaglanti = 0;
unsigned long baslamaZamani = 0;
unsigned long roleKapanmaZamani = 0;
bool roleAktif = false;

// ===================== ETHERNET OLAYLARI =====================
void ethOlay(WiFiEvent_t event) {
  switch (event) {
    case ARDUINO_EVENT_ETH_START:
      Serial.println("[ETH] Başlatıldı");
      ETH.setHostname("tahta-kapi");
      break;
    case ARDUINO_EVENT_ETH_CONNECTED:
      Serial.println("[ETH] Kablo bağlı");
      break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      Serial.print("[ETH] IP alındı: ");
      Serial.println(ETH.localIP());
      ethBaglandi = true;
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
      Serial.println("[ETH] Kablo çıktı!");
      ethBaglandi = false;
      sunucuBagli = false;
      kayitGonderildi = false;
      break;
    default:
      break;
  }
}

// ===================== SOCKET.IO MESAJ İŞLEME =====================
void socketIOEvent(WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] Bağlantı kesildi");
      sunucuBagli = false;
      kayitGonderildi = false;
      break;

    case WStype_CONNECTED:
      Serial.printf("[WS] Bağlandı: %s\n", payload);
      sunucuBagli = true;
      kayitGonderildi = false;
      break;

    case WStype_TEXT: {
      String mesaj = String((char *)payload);

      // Socket.IO handshake yanıtı (0{...})
      if (mesaj.startsWith("0{")) {
        Serial.println("[SIO] Handshake tamam");
        // Kayıt mesajı gönder
        kapiKayitGonder();
        break;
      }

      // Socket.IO ping (2) → pong (3) yanıtla
      if (mesaj == "2") {
        webSocket.sendTXT("3");
        break;
      }

      // Socket.IO event mesajı: 42["event", data]
      if (mesaj.startsWith("42")) {
        String jsonStr = mesaj.substring(2);
        eventIsle(jsonStr);
      }
      break;
    }

    case WStype_PING:
      Serial.println("[WS] Ping alındı");
      break;

    case WStype_PONG:
      Serial.println("[WS] Pong alındı");
      break;

    case WStype_ERROR:
      Serial.println("[WS] Hata!");
      break;
  }
}

// ===================== KAPI KAYIT =====================
void kapiKayitGonder() {
  if (kayitGonderildi) return;

  // Socket.IO event formatı: 42["kapi_kayit", { ... }]
  StaticJsonDocument<256> doc;
  JsonArray arr = doc.to<JsonArray>();
  arr.add("kapi_kayit");

  JsonObject veri = arr.createNestedObject();
  veri["cihaz_id"] = CIHAZ_ID;
  veri["cihaz_adi"] = CIHAZ_ADI;
  veri["kurum_kodu"] = KURUM_KODU;

  String mesaj;
  serializeJson(doc, mesaj);

  String socketMesaj = "42" + mesaj;
  webSocket.sendTXT(socketMesaj);
  kayitGonderildi = true;
  Serial.println("[KAYIT] Kapı cihazı kaydedildi: " + String(CIHAZ_ID));
}

// ===================== EVENT İŞLEME =====================
void eventIsle(const String &jsonStr) {
  StaticJsonDocument<512> doc;
  DeserializationError hata = deserializeJson(doc, jsonStr);
  if (hata) {
    Serial.println("[JSON] Ayrıştırma hatası: " + String(hata.c_str()));
    return;
  }

  const char *eventAdi = doc[0];
  if (!eventAdi) return;

  // ---- Kapı Aç Komutu ----
  if (strcmp(eventAdi, "kapi_ac") == 0) {
    Serial.println("[KOMUT] Kapı açılıyor!");
    kapiAc();
  }

  // ---- Hata Mesajı ----
  else if (strcmp(eventAdi, "hata") == 0) {
    const char *mesaj = doc[1]["mesaj"];
    Serial.printf("[HATA] Sunucu: %s\n", mesaj ? mesaj : "Bilinmeyen");
  }

  // ---- Kayıt Onayı ----
  else if (strcmp(eventAdi, "kapi_kayit_onay") == 0) {
    Serial.println("[ONAY] Sunucu tarafından kayıt onaylandı");
    ledBlink(3, 200);
  }
}

// ===================== KAPI KONTROL =====================
void kapiAc() {
  if (roleAktif) {
    Serial.println("[KAPI] Röle zaten aktif, yoksayıldı");
    return;
  }

  digitalWrite(ROLE_PIN, HIGH);
  roleAktif = true;
  roleKapanmaZamani = millis() + ROLE_SURE_MS;
  Serial.printf("[KAPI] Röle AKTİF — %d ms sonra kapanacak\n", ROLE_SURE_MS);

  // Durum bildir
  durumGonder("acik");

  if (LED_PIN >= 0) {
    digitalWrite(LED_PIN, HIGH);
  }
}

void kapiKapat() {
  digitalWrite(ROLE_PIN, LOW);
  roleAktif = false;
  Serial.println("[KAPI] Röle KAPANDI");

  durumGonder("kapali");

  if (LED_PIN >= 0) {
    digitalWrite(LED_PIN, LOW);
  }
}

// ===================== DURUM BİLDİRİM =====================
void durumGonder(const char *durum) {
  if (!sunucuBagli) return;

  StaticJsonDocument<256> doc;
  JsonArray arr = doc.to<JsonArray>();
  arr.add("kapi_durum");

  JsonObject veri = arr.createNestedObject();
  veri["cihaz_id"] = CIHAZ_ID;
  veri["durum"] = durum;

  // Kapı sensörü varsa oku
  if (KAPI_SENSOR_PIN >= 0) {
    veri["sensor"] = digitalRead(KAPI_SENSOR_PIN) == LOW ? "kapali" : "acik";
  }

  String mesaj;
  serializeJson(doc, mesaj);
  webSocket.sendTXT("42" + mesaj);
}

// ===================== LED YARDIMCI =====================
void ledBlink(int kez, int aralik) {
  if (LED_PIN < 0) return;
  for (int i = 0; i < kez; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(aralik);
    digitalWrite(LED_PIN, LOW);
    delay(aralik);
  }
}

// ===================== WEBSOCKET BAĞLANTISI =====================
void websocketBaslat() {
  if (secureClient) {
    delete secureClient;
  }
  secureClient = new WiFiClientSecure();
  secureClient->setCACert(meb_kök_sertifika);

  webSocket.beginSslWithCA(SUNUCU_HOST, SUNUCU_PORT, SOCKETIO_PATH, meb_kök_sertifika, "");
  webSocket.onEvent(socketIOEvent);
  webSocket.setReconnectInterval(YENIDEN_BAGLANTI_MS);
  webSocket.enableHeartbeat(HEARTBEAT_MS, 3000, 2);

  Serial.println("[WS] TLS bağlantısı başlatılıyor...");
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("============================================");
  Serial.println("  Tahta Kilit - Kapı Otomasyon Kontrolcüsü  ");
  Serial.println("  Cihaz: " + String(CIHAZ_ADI));
  Serial.println("  Kurum: " + String(KURUM_KODU));
  Serial.println("============================================");

  // Pin ayarları
  pinMode(ROLE_PIN, OUTPUT);
  digitalWrite(ROLE_PIN, LOW);

  if (KAPI_SENSOR_PIN >= 0) {
    pinMode(KAPI_SENSOR_PIN, INPUT_PULLUP);
  }

  if (LED_PIN >= 0) {
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
  }

  // Ethernet başlat
  WiFi.onEvent(ethOlay);
  ETH.begin();

  // Ethernet bağlantısını bekle
  Serial.println("[ETH] Bağlantı bekleniyor...");
  unsigned long beklemeBas = millis();
  while (!ethBaglandi && (millis() - beklemeBas < ETH_BASLAMA_BEKLEME)) {
    delay(100);
  }

  if (ethBaglandi) {
    Serial.println("[ETH] Bağlantı hazır, WebSocket başlatılıyor...");
    websocketBaslat();
  } else {
    Serial.println("[ETH] Bağlantı henüz yok, döngüde denenecek...");
  }

  baslamaZamani = millis();
  ledBlink(2, 300);
}

// ===================== LOOP =====================
void loop() {
  unsigned long simdi = millis();

  // --- Periyodik donanım sıfırlama (stabilite için) ---
  if (simdi - baslamaZamani >= HW_RESET_ARALIK_MS) {
    Serial.println("[SİSTEM] Planlı yeniden başlatma...");
    delay(1000);
    ESP.restart();
  }

  // --- Ethernet bağlandıysa WebSocket'i yönet ---
  if (ethBaglandi) {
    if (!sunucuBagli && !kayitGonderildi) {
      // İlk bağlantı veya yeniden bağlantı
      static bool wsBaslatildi = false;
      if (!wsBaslatildi) {
        websocketBaslat();
        wsBaslatildi = true;
      }
    }
    webSocket.loop();
  }

  // --- Röle zamanlama kontrolü ---
  if (roleAktif && simdi >= roleKapanmaZamani) {
    kapiKapat();
  }

  // --- Periyodik durum bildirimi (her 30 sn) ---
  static unsigned long sonDurumBildirim = 0;
  if (sunucuBagli && (simdi - sonDurumBildirim >= 30000)) {
    durumGonder(roleAktif ? "acik" : "kapali");
    sonDurumBildirim = simdi;
  }

  // --- Seri port komutları (test amaçlı) ---
  if (Serial.available()) {
    String komut = Serial.readStringUntil('\n');
    komut.trim();
    if (komut == "ac") {
      Serial.println("[TEST] Manuel kapı açma");
      kapiAc();
    } else if (komut == "durum") {
      Serial.printf("[DURUM] ETH: %s | WS: %s | Röle: %s\n",
        ethBaglandi ? "Bağlı" : "Yok",
        sunucuBagli ? "Bağlı" : "Yok",
        roleAktif ? "Aktif" : "Pasif");
      Serial.printf("[DURUM] IP: %s | Çalışma: %lu sn\n",
        ETH.localIP().toString().c_str(),
        (simdi - baslamaZamani) / 1000);
    } else if (komut == "reset") {
      Serial.println("[TEST] Yeniden başlatılıyor...");
      delay(500);
      ESP.restart();
    }
  }

  delay(1); // Watchdog beslemesi
}
