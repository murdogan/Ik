# 09 — Entegrasyon Haritası

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** Dış sistem entegrasyonları, entegrasyon mimarisi, adaptör yapısı, veri akışları, güvenlik kuralları  
> **Referans:** 04-gereksinim-analizi.md (FR-ENT-01 – FR-ENT-11), 05-teknoloji-secimi.md, 06-sistem-mimarisi.md, 08-api-tasarimi.md

---

## 1. Amaç

Bu doküman, İK Yönetim Sistemi'nin dış sistemlerle entegrasyon haritasını çıkarır. Her entegrasyonun yönünü, veri formatını, teknik yaklaşımını ve fazını tanımlar.

---

## 2. Entegrasyon Genel Mimarisi

### 2.1 Adaptör Pattern

Tüm dış sistem entegrasyonları `integration` modülü altında, adaptör pattern ile yönetilir. Her dış sistem için ayrı bir adaptör sınıfı yazılır. Böylece dış sistemin API'si değiştiğinde sadece adaptör güncellenir, iş mantığı etkilenmez.

```
app/modules/integration/
├── __init__.py
├── router.py                  # Entegrasyon endpoint'leri
├── service.py                 # Orkestrasyon mantığı
│
├── adapters/
│   ├── base.py                # BaseAdapter (ortak arayüz)
│   ├── sgk_adapter.py         # SGK e-Bildirge
│   ├── edevlet_adapter.py     # e-Devlet sorguları
│   ├── bank_adapter.py        # Banka EFT dosyası
│   ├── accounting_adapter.py  # Muhasebe yazılımları (Logo, Mikro, Netsis)
│   ├── email_adapter.py       # E-posta servisi
│   ├── sms_adapter.py         # SMS gateway
│   ├── push_adapter.py        # Firebase Cloud Messaging
│   ├── calendar_adapter.py    # Google/Outlook takvim
│   ├── pdks_adapter.py        # PDKS cihaz
│   ├── job_board_adapter.py   # Kariyer.net, LinkedIn
│   └── collaboration_adapter.py  # Slack, Teams
│
├── schemas.py                 # Entegrasyon request/response modelleri
├── models.py                  # Entegrasyon log tablosu
└── exceptions.py              # Entegrasyon hata sınıfları
```

### 2.2 Adaptör Arayüzü

```python
# adapters/base.py
from abc import ABC, abstractmethod

class BaseAdapter(ABC):
    """Tüm entegrasyon adaptörlerinin uyacağı arayüz."""

    @abstractmethod
    async def send(self, payload: dict) -> dict:
        """Dış sisteme veri gönder."""
        pass

    @abstractmethod
    async def fetch(self, params: dict) -> dict:
        """Dış sistemden veri çek."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Dış sistemin erişilebilir olup olmadığını kontrol et."""
        pass
```

### 2.3 Entegrasyon Akış Deseni

Tüm entegrasyonlar aynı akışı takip eder:

```
İş Mantığı (service.py)
    │
    │  1. Veri hazırla
    ▼
Adaptör (sgk_adapter.py)
    │
    │  2. Formatla + gönder / dosya üret
    ▼
Dış Sistem veya Dosya Çıktısı
    │
    │  3. Sonucu logla
    ▼
integration_logs tablosu
```

### 2.4 Entegrasyon Log Tablosu

Her dış sistem çağrısı loglanır:

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `adapter` | VARCHAR(50) | Adaptör adı: `sgk`, `bank`, `email` |
| `direction` | VARCHAR(10) | `outbound` veya `inbound` |
| `action` | VARCHAR(100) | İşlem: `send_aphb`, `send_email`, `fetch_attendance` |
| `status` | VARCHAR(20) | `success`, `failed`, `pending`, `retrying` |
| `request_payload` | JSONB | Gönderilen veri (hassas alanlar maskelenir) |
| `response_payload` | JSONB | Alınan yanıt |
| `error_message` | TEXT | Hata varsa detay |
| `retry_count` | SMALLINT | Tekrar deneme sayısı |
| `duration_ms` | INTEGER | İşlem süresi (ms) |
| `triggered_by` | BIGINT, FK | İşlemi tetikleyen kullanıcı |
| `created_at` | TIMESTAMPTZ | |

---

## 3. Entegrasyon Haritası — Özet

| # | Entegrasyon | Yön | Protokol | Faz | Öncelik | Referans |
|---|-------------|-----|----------|-----|---------|----------|
| 1 | E-posta Servisi | Outbound | SMTP / HTTP API | MVP | Must | FR-ENT-09 |
| 2 | SMS Gateway | Outbound | HTTP API | MVP | Should | FR-ENT-08 |
| 3 | Push Notification (FCM) | Outbound | HTTP API | MVP | Must | Mobil gereksinim |
| 4 | SGK e-Bildirge | Outbound (dosya) | Dosya üretimi (XML/CSV) | Faz 3 | Must | FR-ENT-01 |
| 5 | e-Devlet | Inbound | SOAP / REST | Faz 3 | Should | FR-ENT-02 |
| 6 | Banka EFT Dosyası | Outbound (dosya) | Dosya üretimi (TXT/XML) | Faz 3 | Should | FR-ENT-03 |
| 7 | Muhasebe Yazılımları | Bi-directional | REST API / Dosya | Faz 3 | Should | FR-ENT-04 |
| 8 | Takvim (Google/Outlook) | Bi-directional | REST API (OAuth 2.0) | Faz 3 | Should | FR-ENT-05 |
| 9 | PDKS Cihazları | Inbound | REST API / Dosya import | Faz 3 | Should | FR-ENT-06 |
| 10 | İş İlanı Platformları | Outbound | REST API | Faz 3 | Could | FR-ENT-11 |
| 11 | İşbirliği Araçları (Slack/Teams) | Outbound | Webhook / REST API | Faz 3 | Could | FR-ENT-07 |
| 12 | SSO / LDAP / AD | Inbound | LDAP / SAML 2.0 / OIDC | Faz 3+ | Could | FR-AUTH-06, FR-AUTH-07 |
| 13 | Webhook (Genel) | Outbound | HTTP POST | MVP | Must | FR-ENT-10 |

---

## 4. Entegrasyon Detayları

### 4.1 E-posta Servisi

| Alan | Değer |
|------|-------|
| **Faz** | MVP |
| **Öncelik** | Must |
| **Yön** | Outbound |
| **Sağlayıcılar** | SendGrid (birincil), AWS SES (alternatif), SMTP (fallback) |
| **Protokol** | HTTP API (öncelikli), SMTP (fallback) |
| **Tetikleyici** | Celery task (asenkron) |

**Kullanım Alanları:**

| Senaryo | Şablon Kodu | Açıklama |
|---------|-------------|----------|
| Hoş geldin e-postası | `welcome_email` | Yeni çalışan kaydında |
| Şifre sıfırlama | `password_reset` | Token link ile |
| İzin talebi bildirimi | `leave_request_created` | Yöneticiye bildirim |
| İzin onay/red bildirimi | `leave_approved` / `leave_rejected` | Çalışana bildirim |
| Bordro hazır bildirimi | `payslip_ready` | Çalışana aylık |
| MFA doğrulama kodu | `mfa_code` | OTP gönderimi |

**Teknik Detaylar:**

- E-postalar Jinja2 şablonları ile HTML olarak üretilir.
- Her tenant kendi gönderici adresini tanımlayabilir (`noreply@firmam.com`).
- Gönderim Celery task olarak çalışır, ana transaction'ı bloklamaz.
- Başarısız gönderimler 3 kez tekrar denenir (exponential backoff).
- Gönderim logları `integration_logs` tablosuna yazılır.
- Bounce/complaint webhook'ları ile geri bildirim alınır.

**Konfigürasyon:**

```python
# Tenant bazlı veya global ayar
EMAIL_PROVIDER = "sendgrid"  # sendgrid | ses | smtp
SENDGRID_API_KEY = "env:SENDGRID_API_KEY"
EMAIL_FROM_DEFAULT = "noreply@ikplatform.com"
EMAIL_RETRY_COUNT = 3
EMAIL_RETRY_DELAY_SECONDS = [30, 120, 600]  # 30s, 2dk, 10dk
```

---

### 4.2 SMS Gateway

| Alan | Değer |
|------|-------|
| **Faz** | MVP |
| **Öncelik** | Should |
| **Yön** | Outbound |
| **Sağlayıcılar** | Netgsm (birincil), İleti Merkezi (alternatif) |
| **Protokol** | HTTP API |
| **Tetikleyici** | Celery task |

**Kullanım Alanları:**

| Senaryo | Açıklama |
|---------|----------|
| MFA doğrulama | OTP SMS gönderimi |
| İzin onayı | Yöneticiye acil onay bildirimi |
| Mülakat hatırlatma | Adaya mülakat saati hatırlatma |

**Teknik Detaylar:**

- Türkiye'deki SMS sağlayıcıları kullanılır (Netgsm, İleti Merkezi).
- İYS (İleti Yönetim Sistemi) uyumluluğu adaptör seviyesinde sağlanır.
- SMS içeriği 160 karakter sınırına dikkat edilerek hazırlanır.
- Gönderim DLR (delivery report) ile takip edilir.
- SMS maliyeti tenant bazlı kotalarla yönetilebilir.

---

### 4.3 Push Notification (Firebase Cloud Messaging)

| Alan | Değer |
|------|-------|
| **Faz** | MVP |
| **Öncelik** | Must |
| **Yön** | Outbound |
| **Servis** | Firebase Cloud Messaging (FCM) |
| **Protokol** | HTTP v1 API |
| **Tetikleyici** | Celery task |

**Kullanım Alanları:**

| Senaryo | Açıklama |
|---------|----------|
| İzin talebi/onayı | Anlık mobil bildirim |
| Duyuru | Tüm çalışanlara veya departmana |
| Vardiya değişikliği | Atanan çalışana bildirim |
| Onay bekleyen işlem | Yöneticiye badge güncelleme |

**Teknik Detaylar:**

- Flutter uygulaması FCM token'ı backend'e kaydeder.
- Her kullanıcının birden fazla cihazı (token'ı) olabilir.
- Topic bazlı gönderim: departman, şube, tüm firma.
- Token geçersiz olduğunda (unregistered) otomatik temizlenir.
- Bildirim verisi `notif_logs` tablosuna da yazılır (in-app bildirim ile senkron).

---

### 4.4 SGK e-Bildirge

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 (Bordro modülü ile birlikte) |
| **Öncelik** | Must |
| **Yön** | Outbound (dosya üretimi) |
| **Format** | SGK APHB XML/CSV formatı |
| **Tetikleyici** | İK kullanıcısı veya zamanlanmış görev |

**Kapsam:**

| Veri | Açıklama |
|------|----------|
| Aylık Prim ve Hizmet Belgesi (APHB) | Çalışan bazlı SGK gün, kazanç, eksik gün verileri |
| İşe giriş bildirimi | Yeni çalışan SGK bildirim verisi |
| İşten çıkış bildirimi | Ayrılan çalışan SGK bildirim verisi |
| Eksik gün nedenleri | İzin, rapor, ücretsiz izin gibi nedenler |

**Teknik Yaklaşım:**

- SGK'nın doğrudan API'si bulunmadığından, sistemimiz **SGK formatına uygun dosya üretir**.
- İK kullanıcısı bu dosyayı indirip SGK e-Bildirge portalına yükler.
- Dosya formatı SGK'nın yayınladığı teknik kılavuza uygun olarak hazırlanır.
- Üretilen dosyalar MinIO'da saklanır ve indirme geçmişi loglanır.
- İleride SGK web servis API'si açılırsa doğrudan entegrasyon adaptöre eklenir.

**Üretilen Dosya Alanları (APHB):**

| Alan | Açıklama |
|------|----------|
| TC Kimlik No | Çalışanın TC'si |
| Ad Soyad | |
| İşyeri sicil no | Firmanın SGK sicil numarası |
| Prim gün sayısı | Ayda çalışılan gün |
| Prime esas kazanç | Brüt ücret |
| Eksik gün sayısı | Çalışılmayan günler |
| Eksik gün nedeni | 01-Hastalık, 04-Ücretsiz izin, 07-Diğer vs. |

---

### 4.5 e-Devlet Sorguları

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 |
| **Öncelik** | Should |
| **Yön** | Inbound (veri çekme) |
| **Protokol** | KPS (Kimlik Paylaşım Sistemi) SOAP |
| **Gereklilik** | Kamu kurumları için KPS erişim yetkisi gerekir; özel sektör için sınırlı |

**Kullanım Alanları:**

| Sorgu | Açıklama |
|-------|----------|
| TC Kimlik doğrulama | Ad, soyad, doğum yılı ile TC doğrulama |
| Adres bilgisi | Mernis adres sorgulama |

**Teknik Yaklaşım:**

- KPS SOAP servisi için `zeep` kütüphanesi ile Python client.
- Özel sektör firmaları için genellikle TC doğrulama Nüfus ve Vatandaşlık İşleri Genel Müdürlüğü'nün açık SOAP servisi üzerinden yapılır.
- Sorgu sonuçları cache'lenmez (güncel veri gerekli).
- KPS erişim belgesi olmayan firmalar için bu özellik pasif kalır.

---

### 4.6 Banka EFT Dosyası

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 (Bordro modülü ile birlikte) |
| **Öncelik** | Should |
| **Yön** | Outbound (dosya üretimi) |
| **Format** | Banka bazlı TXT/XML |
| **Tetikleyici** | Bordro onayı sonrası İK talebi |

**Desteklenecek Bankalar (başlangıç):**

| Banka | Format | Açıklama |
|-------|--------|----------|
| Ziraat Bankası | TXT (sabit genişlik) | Kamu ve özel sektör yaygın |
| İş Bankası | TXT | Yaygın kullanım |
| Garanti BBVA | XML | XML tabanlı format |
| Yapı Kredi | TXT | |
| Akbank | TXT | |
| Genel format | CSV | Diğer bankalar için genel |

**Teknik Yaklaşım:**

- Her banka formatı için ayrı bir formatter sınıfı yazılır (`bank_adapter.py` içinde).
- Bordro onaylandıktan sonra İK kullanıcısı hedef bankayı seçer ve dosyayı indirir.
- Dosya çalışan IBAN'larına göre otomatik gruplandırılır.
- Üretilen dosyalar MinIO'da saklanır.
- Yeni banka formatı eklemek için sadece yeni formatter sınıfı eklenir.

**Dosya İçeriği:**

| Alan | Açıklama |
|------|----------|
| IBAN | Çalışanın banka hesabı |
| Ad Soyad | Alıcı adı |
| Tutar | Net maaş |
| Açıklama | "2026 Nisan Maaş" gibi |
| Referans | Bordro numarası |

---

### 4.7 Muhasebe Yazılımı Entegrasyonu

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 |
| **Öncelik** | Should |
| **Yön** | Bi-directional (veri aktarımı + dosya) |
| **Hedef Sistemler** | Logo, Mikro, Netsis, Luca, Paraşüt |

**Veri Akışı:**

| Yön | Veri | Açıklama |
|-----|------|----------|
| IK → Muhasebe | Maaş tahakkuk fişi | Bordro hesaplaması sonrası muhasebe kaydı |
| IK → Muhasebe | Masraf kalemleri | Personel giderleri, SGK işveren payı |
| Muhasebe → IK | Ödeme onayı | Maaş ödemesinin gerçekleştiği bilgisi |

**Teknik Yaklaşım:**

Muhasebe yazılımlarının entegrasyon yetenekleri farklıdır:

| Yazılım | Entegrasyon Yöntemi |
|---------|---------------------|
| Logo | REST API (Logo Connect) veya XML dosya import |
| Mikro | Veritabanı bazlı veya dosya import |
| Netsis | SOAP/REST API veya dosya import |
| Luca | REST API |
| Paraşüt | REST API (modern) |

- MVP'de muhasebe entegrasyonu yoktur.
- İlk aşamada **standart muhasebe dosyası export** (CSV/XML) sağlanır.
- Belirli muhasebe yazılımları için API entegrasyonu öncelik ve talebe göre eklenir.
- Her muhasebe yazılımı için ayrı adaptör sınıfı.

---

### 4.8 Takvim Entegrasyonu

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 |
| **Öncelik** | Should |
| **Yön** | Bi-directional |
| **Servisler** | Google Calendar API, Microsoft Graph API (Outlook) |
| **Protokol** | REST API + OAuth 2.0 |

**Kullanım Alanları:**

| Senaryo | Açıklama |
|---------|----------|
| İzin takvimi senkronizasyonu | Onaylanan izinler kişisel takvime eklenir |
| Mülakat planlama | ATS'ten mülakat takvime yansır |
| Toplantı planlama | Performans görüşmesi takvime eklenir |

**Teknik Yaklaşım:**

- OAuth 2.0 ile kullanıcıdan takvim erişim izni alınır.
- Token'lar şifreli olarak DB'de saklanır, otomatik refresh yapılır.
- Takvim event'leri Celery task olarak gönderilir.
- Kullanıcı takvim bağlantısını dilediği zaman kesebilir.
- Çift yönlü senkronizasyon opsiyonel; başlangıçta tek yönlü (İK → Takvim).

---

### 4.9 PDKS Cihaz Entegrasyonu

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 (Vardiya modülü ile birlikte) |
| **Öncelik** | Should |
| **Yön** | Inbound (veri çekme) |
| **Cihaz Markaları** | Suprema, ZKTeco, Anviz |

**Veri Akışı:**

```
PDKS Cihazı
    │
    │  Giriş/çıkış kaydı (parmak izi, kart, yüz tanıma)
    ▼
PDKS Sunucusu / Cihaz API'si
    │
    │  REST API veya dosya export (CSV/TXT)
    ▼
PDKS Adaptörü (pdks_adapter.py)
    │
    │  Veriyi normalize et
    ▼
shift_attendance tablosu
    │
    │  Vardiya eşleştirme, mesai hesaplama
    ▼
Vardiya Modülü
```

**Teknik Yaklaşım:**

| Yöntem | Açıklama | Kullanım |
|--------|----------|----------|
| API polling | Cihaz API'sinden periyodik veri çekme | Suprema BioStar 2 API, ZKTeco ZKBioAccess |
| Dosya import | Cihazdan export edilen CSV/TXT dosyasını yükleme | Tüm cihazlar |
| Webhook/push | Cihazın anlık veri göndermesi | Destekleyen cihazlar |

- Her PDKS markası için ayrı adaptör alt sınıfı.
- Yerel ağ erişimi gerektiğinde müşteri tarafında agent kurulumu gerekebilir.
- Veri çekme sıklığı konfigüre edilebilir (5dk, 15dk, saatlik).
- Çakışma ve tutarsızlık kontrolü (aynı dakikada birden fazla kayıt).

---

### 4.10 İş İlanı Platformları

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3 (ATS modülü ile birlikte) |
| **Öncelik** | Could |
| **Yön** | Outbound (ilan yayınlama) + Inbound (başvuru çekme) |
| **Platformlar** | Kariyer.net, LinkedIn, Indeed |

**Kullanım:**

| Akış | Açıklama |
|------|----------|
| İlan yayınlama | ATS'ten ilan oluştur → platforma otomatik gönder |
| Başvuru çekme | Platformdaki başvuruları ATS'e çek |
| İlan güncelleme/kapatma | ATS'ten ilan durumu değişince platforma senkronla |

**Teknik Yaklaşım:**

- Kariyer.net ve LinkedIn API'leri için ayrı adaptörler.
- Her platformun API erişim koşulları farklıdır (partnership gerekebilir).
- İlk aşamada manuel ilan yönetimi (ATS modülü), API entegrasyonu sonraki iterasyonlarda.

---

### 4.11 İşbirliği Araçları (Slack / Microsoft Teams)

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3+ |
| **Öncelik** | Could |
| **Yön** | Outbound |
| **Protokol** | Webhook (basit) / REST API (gelişmiş) |

**Kullanım:**

| Senaryo | Açıklama |
|---------|----------|
| İzin bildirimi | Yöneticiye Slack/Teams mesajı |
| Duyuru | İK duyurularını kanala gönderme |
| Onay butonu | Slack interactive message ile izin onayı (gelişmiş) |

**Teknik Yaklaşım:**

- Başlangıçta incoming webhook ile basit mesaj gönderimi.
- Gelişmiş aşamada Slack Bot / Teams Bot ile interactive mesajlar.
- Tenant bazlı webhook URL konfigürasyonu.

---

### 4.12 SSO / LDAP / Active Directory

| Alan | Değer |
|------|-------|
| **Faz** | Faz 3+ |
| **Öncelik** | Could |
| **Protokol** | LDAP / SAML 2.0 / OpenID Connect |
| **Hedef** | Kurumsal müşteriler |

**Kullanım:**

| Senaryo | Açıklama |
|---------|----------|
| LDAP/AD senkronizasyonu | Firma Active Directory'den kullanıcı listesini çekme |
| SSO Login | Firma IdP'si (Okta, Azure AD) ile tek oturum açma |
| Otomatik provisioning | AD'ye eklenen çalışanın İK sistemine otomatik oluşması |

**Teknik Yaklaşım:**

- LDAP entegrasyonu için `ldap3` Python kütüphanesi.
- SAML 2.0 için `python3-saml` kütüphanesi.
- OpenID Connect için `authlib` kütüphanesi.
- MVP'de bu entegrasyon yoktur; ancak auth modülü SSO'ya genişleyebilir tasarlanmıştır (06-sistem-mimarisi.md, bölüm 8).
- Tenant bazlı IdP konfigürasyonu: her firma kendi SSO ayarlarını tanımlar.

---

### 4.13 Webhook Sistemi (Outbound)

| Alan | Değer |
|------|-------|
| **Faz** | MVP |
| **Öncelik** | Must |
| **Yön** | Outbound |
| **Protokol** | HTTP POST (JSON payload) |

Sistemde belirli olaylar gerçekleştiğinde, tenant'ın tanımladığı webhook URL'lerine HTTP POST gönderilir. Bu, 3. parti sistemlerle genel entegrasyon sağlar.

**Desteklenen Olaylar (MVP):**

| Olay | Açıklama |
|------|----------|
| `employee.created` | Yeni çalışan oluşturuldu |
| `employee.updated` | Çalışan bilgisi güncellendi |
| `employee.terminated` | Çalışan ayrıldı |
| `leave.requested` | İzin talebi oluşturuldu |
| `leave.approved` | İzin talebi onaylandı |
| `leave.rejected` | İzin talebi reddedildi |

**Webhook Payload Formatı:**

```json
{
  "event": "leave.approved",
  "timestamp": "2026-04-09T15:00:00Z",
  "tenant_id": 1,
  "data": {
    "id": 234,
    "employee_id": 42,
    "leave_type": "annual",
    "start_date": "2026-04-14",
    "end_date": "2026-04-18",
    "status": "approved"
  },
  "webhook_id": "wh_abc123"
}
```

**Güvenlik:**

- Her webhook kaydında bir `secret` tanımlanır.
- Payload HMAC-SHA256 ile imzalanır, `X-Webhook-Signature` header'ında gönderilir.
- Alıcı taraf imzayı doğrulayarak mesajın sahiciliğini kontrol eder.

**Teknik Detaylar:**

- Webhook gönderimi Celery task olarak çalışır.
- Başarısız gönderimler 3 kez tekrar denenir (exponential backoff: 1dk, 5dk, 30dk).
- 3 başarısız denemeden sonra webhook otomatik devre dışı bırakılır, tenant bilgilendirilir.
- Gönderim geçmişi `integration_logs` tablosunda saklanır.

---

## 5. Entegrasyon Güvenlik Kuralları

| Kural | Açıklama |
|-------|----------|
| API key'ler ortam değişkeninde saklanır | `.env` dosyası, asla kod içinde değil |
| 3. parti API credential'ları şifrelenir | DB'de AES-256 ile şifreli saklama |
| Hassas veriler loglanmaz | TC kimlik, IBAN, maaş gibi alanlar maskeli loglanır |
| Webhook imzalama zorunludur | HMAC-SHA256 ile payload imzalama |
| Timeout zorunludur | Her dış çağrıda 30s timeout, uzun işler Celery'de |
| Rate limit uygulanır | 3. parti API'lerin rate limitine uyum |
| SSL/TLS zorunludur | Tüm dış çağrılar HTTPS üzerinden |
| Token'lar rotate edilir | OAuth token'ları otomatik refresh, API key'ler periyodik değişim |

---

## 6. Hata Yönetimi ve Retry Stratejisi

### 6.1 Retry Politikası

| Entegrasyon | Max Retry | Backoff | Açıklama |
|-------------|-----------|---------|----------|
| E-posta | 3 | 30s, 2dk, 10dk | Exponential |
| SMS | 3 | 30s, 2dk, 10dk | Exponential |
| Push notification | 2 | 30s, 2dk | |
| Webhook | 3 | 1dk, 5dk, 30dk | Exponential |
| PDKS veri çekme | 3 | 5dk, 15dk, 1 saat | Periyodik tekrar |
| Dosya üretimi (SGK, banka) | 1 | Yok | Kullanıcı tekrar tetikler |

### 6.2 Circuit Breaker

Dış sistem sürekli hata dönüyorsa, circuit breaker devreye girer:

- **Eşik:** Son 10 çağrıda 5'i başarısızsa devre açılır.
- **Bekleme:** 5 dakika boyunca çağrı yapılmaz.
- **Half-open:** 5 dk sonra tek deneme yapılır; başarılıysa devre kapanır.
- **Bildirim:** Circuit açıldığında Sentry alert ve admin bilgilendirmesi.

---

## 7. MVP Entegrasyon Checklist

MVP'de aktif olacak entegrasyonlar:

| Entegrasyon | Durum | Notlar |
|-------------|-------|--------|
| E-posta (SendGrid/SMTP) | Aktif | Tüm bildirimler |
| SMS (Netgsm) | Aktif | MFA, acil bildirimler |
| Push (FCM) | Aktif | Mobil bildirimler |
| Webhook (outbound) | Aktif | 3. parti entegrasyon altyapısı |
| SGK e-Bildirge | Pasif | Faz 3 — Bordro modülü ile |
| Banka EFT | Pasif | Faz 3 — Bordro modülü ile |
| Muhasebe | Pasif | Faz 3 |
| Takvim | Pasif | Faz 3 |
| PDKS | Pasif | Faz 3 — Vardiya modülü ile |
| İş ilanı platformları | Pasif | Faz 3 — ATS modülü ile |
| Slack/Teams | Pasif | Faz 3+ |
| SSO/LDAP | Pasif | Faz 3+ |

---

## 8. Faz 3 İçin Not

Her entegrasyonun detaylı implementasyon kararları ilgili modül dokümanlarında verilecektir:

| Entegrasyon | İlgili Modül Dokümanı |
|-------------|----------------------|
| SGK e-Bildirge | 14-modul-bordro-maas.md |
| Banka EFT dosyası | 14-modul-bordro-maas.md |
| Muhasebe yazılımları | 14-modul-bordro-maas.md |
| PDKS cihazları | 16-modul-vardiya-mesai.md |
| İş ilanı platformları | 11-modul-ise-alim-ats.md |
| Takvim entegrasyonu | 12-modul-izin-devamsizlik.md, 11-modul-ise-alim-ats.md |

---

## 9. Sonuç

Entegrasyon haritası aşağıdaki temeller üzerine kurulmuştur:

- **Adaptör pattern:** Her dış sistem için izole adaptör, değişiklikler iş mantığını etkilemez
- **Asenkron gönderim:** Tüm dış çağrılar Celery task ile arka planda çalışır
- **Dosya tabanlı başlangıç:** SGK ve banka entegrasyonları MVP'de dosya üretimi ile başlar, API entegrasyonu ilerleyen fazlarda
- **Retry + circuit breaker:** Dış sistem hatalarına dayanıklılık
- **Merkezi loglama:** Tüm entegrasyon çağrıları `integration_logs` tablosunda izlenebilir
- **MVP odaklı:** E-posta, SMS, push ve webhook MVP'de aktif; kalanı Faz 3'te

Bu doküman ile Faz 2 tamamlanmıştır. Bir sonraki adımda Faz 3 modül dokümanlarına geçilecektir.
