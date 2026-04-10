# 24 — Güvenlik Politikaları

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Kimlik doğrulama, MFA, oturum yönetimi, veri şifreleme, güvenlik izleme, olay yönetimi, OWASP önlemleri, yedekleme ve güvenlik testleri  
> **Faz:** Faz 5

---

## 1. Güvenlik Hedefleri

1. Çok kiracılı yapıda tenant izolasyonunu korumak.
2. Kişisel ve finansal veriye erişimi sıkı rol kontrolüyle sınırlandırmak.
3. Güvenlik olaylarını tespit, kayıt ve müdahale süreçleriyle yönetmek.

---

## 2. Kimlik Doğrulama ve Parola Politikası

### 2.1 Kimlik Doğrulama Mimarisi

| Bileşen | Tercih | Detay |
|---------|--------|-------|
| Yerel kimlik doğrulama | JWT (RS256) | Access token + refresh token |
| SSO | SAML 2.0, OIDC | Kurumsal IdP entegrasyonu (Azure AD, Okta, Keycloak) |
| API kimlik doğrulama | Bearer token | OAuth 2.0 client_credentials (B2B entegrasyonlar) |

### 2.2 Token Yönetimi

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| Access token TTL | 15 dakika | Kısa ömürlü; her istekte yenilenmez |
| Refresh token TTL | 7 gün | Sliding window, her kullanımda yenilenir |
| Refresh token rotation | Aktif | Kullanılan refresh token iptal edilir, yeni çift üretilir |
| Max aktif oturum | 3 cihaz / kullanıcı | Yeni oturum en eski oturumu düşürür |
| Token iptal | Token blacklist (Redis) | Logout, parola değişikliği, şüpheli aktivitede tüm token'lar iptal |
| Token depolama | httpOnly, Secure, SameSite=Strict cookie | XSS'e karşı JS erişimine kapalı |

### 2.3 Parola Politikası

| Kural | Değer |
|-------|-------|
| Minimum uzunluk | 12 karakter |
| Karmaşıklık | En az 1 büyük + 1 küçük + 1 rakam + 1 özel karakter |
| Parola geçmişi | Son 12 parola tekrar edilemez |
| Parola süresi | 90 gün (tenant yapılandırılabilir) |
| Hesap kilitleme | 5 başarısız deneme → 30 dk kilitleme |
| Kilitleme artışı | 3. kilitleme → kalıcı kilit (İK müdahalesi gerekir) |
| Hash algoritması | Argon2id (memory=65536, iterations=3, parallelism=4) |
| Zayıf parola kontrolü | HaveIBeenPwned API + yaygın parola listesi kontrolü |
| İlk giriş | Zorunlu parola değişikliği |

### 2.4 MFA (Çok Faktörlü Kimlik Doğrulama)

| Konfigürasyon | Değer |
|---------------|-------|
| Zorunlu roller | Süper admin, İK admin, finans |
| İsteğe bağlı | Diğer roller (tenant politikasına göre zorunlu yapılabilir) |
| Desteklenen yöntemler | TOTP (Google/Microsoft Authenticator), SMS (yedek) |
| TOTP kurtarma | 10 adet tek kullanımlık kurtarma kodu |
| MFA atlatma | İmkansız; admin bile MFA'yı devre dışı bırakamaz (süper admin hariç) |
| SMS güvenliği | Rate limit: 3 SMS / 10 dk, 10 SMS / saat |

---

## 3. Oturum Yönetimi

| Parametre | Değer |
|-----------|-------|
| Oturum inaktivite zaman aşımı | 30 dakika |
| Mutlak oturum süresi | 12 saat (yeniden login gerekir) |
| Eşzamanlı oturum limiti | 3 cihaz |
| Oturum sabitleme koruması | Her login'de yeni session ID |
| IP değişikliği kontrolü | Farklı IP bloğundan erişimde MFA sor |
| Cihaz parmak izi | User-Agent + ekran çözünürlüğü + dil tercihi hash |
| Çıkış sonrası | Token blacklist'e eklenir, cookie temizlenir |

### 3.1 Anomali Tespiti

| Senaryo | Aksiyon |
|---------|---------|
| Farklı ülkeden giriş | Oturum askıya, e-posta bildirimi, MFA zorunlu |
| Gece yarısı 00:00–05:00 giriş | Ekstra MFA doğrulaması |
| 10 dk içinde farklı IP'den giriş | Tüm oturumlar iptal, hesap geçici kilit |
| Başarısız MFA denemeleri (5) | Hesap kilitleme + admin bildirimi |

---

## 4. Uygulama Güvenliği (OWASP Top 10 Eşlemesi)

| # | OWASP 2021 | Risk | Uygulanan Kontrol |
|---|------------|------|-------------------|
| A01 | Broken Access Control | Kritik | RBAC + tenant scope + row-level security; her API'de yetki kontrolü |
| A02 | Cryptographic Failures | Yüksek | AES-256-GCM (at-rest), TLS 1.3 (transit), Argon2id (parola) |
| A03 | Injection | Yüksek | ORM (SQLAlchemy) — raw SQL yasak; parameterized sorgular |
| A04 | Insecure Design | Orta | Threat modeling her Sprint'te; abuse case'ler test senaryolarında |
| A05 | Security Misconfiguration | Orta | Hardened Docker image, security headers, CSP policy |
| A06 | Vulnerable Components | Yüksek | Dependabot + Snyk; CI'da bağımlılık taraması |
| A07 | Auth Failures | Kritik | MFA, account lockout, brute-force koruması (bkz. §2) |
| A08 | Data Integrity Failures | Orta | Signed JWT, SRI hash'leri (CDN kaynaklar), signed release |
| A09 | Logging Failures | Orta | Yapılandırılmış audit log; PII maskeleme logda |
| A10 | SSRF | Düşük | Webhook URL whitelist; iç ağ adresleri engelli |

### 4.1 API Güvenlik Kontrolleri

| Kontrol | Konfigürasyon |
|---------|---------------|
| Input validation | Pydantic v2 şema doğrulama; max body size 10 MB |
| Output encoding | JSON content-type zorunlu; HTML injection koruması |
| Rate limiting (genel) | 100 req/dk per user, 1000 req/dk per tenant |
| Rate limiting (auth) | 10 login / dk per IP, 30 / saat per hesap |
| Rate limiting (export) | 5 export / dk per user |
| CORS | Sadece izin verilen origin'ler; wildcard (*) yasak |
| CSRF | SameSite=Strict cookie + CSRF token (form bazlı işlemler) |
| Security headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000`, `Content-Security-Policy`, `Permissions-Policy` |
| Request ID | Her istekte UUID takip; hata yanıtlarında iç detay sızdırmama |

### 4.2 Dosya Yükleme Güvenliği

| Kontrol | Değer |
|---------|-------|
| İzin verilen tipler | PDF, DOCX, XLSX, PNG, JPG, CSV |
| Maks boyut | 20 MB (rapor/belge), 5 MB (profil fotoğrafı) |
| Dosya adı | UUID ile yeniden adlandırma; orijinal isim metadata |
| Virus taraması | ClamAV üzerinden yükleme anında |
| Depolama | MinIO, erişim signed URL (15 dk TTL) |
| Metadata kontrol | EXIF ve macro temizleme |

---

## 5. Altyapı Güvenliği

### 5.1 Ağ Güvenliği

```
İnternet
   │
   ▼
┌──────────────┐
│  CloudFlare  │  DDoS koruması + WAF
│  WAF / CDN   │
└──────┬───────┘
       │  (HTTPS)
       ▼
┌──────────────┐
│  Nginx       │  TLS 1.3 sonlandırma, rate limiting
│  Reverse P.  │  Security headers enjeksiyonu
└──────┬───────┘
       │  (HTTP internal)
       ▼
┌──────────────┐
│  Django App  │  Private subnet
│  (Gunicorn)  │  Port: 8000 (sadece Nginx erişir)
└──────┬───────┘
       │
  ┌────┼────────────┐
  ▼    ▼            ▼
PostgreSQL  Redis  MinIO
(5432)     (6379) (9000)
 Sadece app subnet erişimi
```

### 5.2 Port ve Servis Politikası

| Port | Servis | Erişim |
|------|--------|--------|
| 443 | HTTPS (Nginx) | Public |
| 80 | HTTP → 443 redirect | Public (otomatik yönlendirme) |
| 8000 | Django/Gunicorn | Sadece Nginx container |
| 5432 | PostgreSQL | Sadece app container |
| 6379 | Redis | Sadece app + Celery container |
| 9000 | MinIO | Sadece app container |

### 5.3 Secret Yönetimi

| Secret | Depolama | Rotasyon |
|--------|----------|----------|
| DB şifresi | Docker secret / Vault | 90 gün |
| JWT private key | Docker secret / Vault | 180 gün (key rotation) |
| MinIO access key | Docker secret / Vault | 90 gün |
| SMTP şifresi | Docker secret / Vault | 90 gün |
| 3. parti API key | Docker secret / Vault | Sağlayıcıya göre |
| Encryption key (AES) | Hardware Security Module / Vault | Yıllık (key versioning) |

### 5.4 Veritabanı Güvenliği

| Kontrol | Detay |
|---------|-------|
| Bağlantı şifreleme | `sslmode=verify-full` |
| Erişim | Ayrı read-only ve read-write kullanıcıları |
| Row-level security | `tenant_id` bazlı PostgreSQL RLS policy |
| Sorgu loglaması | Slow query (>1s) ve hatalı sorgular loglanır |
| Backup şifreleme | AES-256 ile şifrelenmiş yedek |

---

## 6. Şifreleme Politikası

| Katman | Yöntem | Detay |
|--------|--------|-------|
| Transit | TLS 1.3 | Nginx terminasyonu; HSTS etkin; TLS 1.0/1.1 devre dışı |
| At-rest (DB) | AES-256-GCM | TCKN, IBAN, maaş, sağlık verisi (django-fernet-fields) |
| At-rest (dosya) | AES-256 | MinIO server-side encryption |
| At-rest (yedek) | AES-256 | Yedekleme dosyaları şifreli (GPG veya age) |
| Parola | Argon2id | Bkz. §2.3 |
| Token | RS256 | JWT signing (2048-bit RSA key pair) |

### 6.1 Hassas Alan Şifreleme Haritası

| Tablo | Alan | Şifreleme | Maskeleme |
|-------|------|-----------|-----------|
| employees | tckn | AES-256-GCM | `***{son 4}` |
| employees | iban | AES-256-GCM | `TR** **** **{son 2} {son 2}` |
| payroll_slips | net_salary | AES-256-GCM | `***,** TL` |
| employees | phone | AES-256-GCM | `+90 5** *** {son 2} {son 2}` |
| health_records | diagnosis | AES-256-GCM | — (sadece yetkili erişim) |
| attendance_logs | biometric_hash | Hashed (SHA-256) | — (karşılaştırma amaçlı) |

---

## 7. Audit ve Loglama

### 7.1 Log Katmanları

| Katman | Araç | Saklama |
|--------|------|---------|
| Uygulama logları | Python logging → stdout | 30 gün (ELK/Loki) |
| Audit log | DB tablosu (audit_logs) | 5 yıl |
| Erişim logları | Nginx access log | 90 gün |
| Güvenlik olayları | Ayrı security_events tablosu | 5 yıl |

### 7.2 Audit Log Kapsamı

| Olay Tipi | Loglanan Bilgi |
|-----------|---------------|
| Giriş / çıkış | Kullanıcı, IP, cihaz, zaman, başarı/başarısız |
| Veri görüntüleme | Hassas veri erişimi (TCKN, maaş) |
| Veri değişikliği | Eski ve yeni değer (diff), kim değiştirdi |
| Export / download | Hangi rapor, kaç kayıt, format |
| Yetki değişikliği | Rol ataması, izin ekleme/çıkarma |
| Sistem yapılandırma | Tenant ayarları, parametre değişiklikleri |

### 7.3 PII Loglama Kuralları

| Kural | Açıklama |
|-------|----------|
| TCKN loglanmaz | Hash veya son 4 hane ile referans |
| Parola loglanmaz | Başarısız giriş bile parola içermez |
| Maaş loglanmaz | Değişiklik olayında "field: net_salary, changed: true" |
| Request body | Hassas alanlar otomatik maskelenir |

---

## 8. Olay Yönetimi (Incident Response)

### 8.1 Severity Sınıflandırması

| Seviye | Tanım | Yanıt SLA | Örnek |
|--------|-------|-----------|-------|
| P1 — Kritik | Veri sızıntısı, tüm sistem erişilemez | 15 dk | DB leak, ransomware |
| P2 — Yüksek | Yetkisiz erişim, tek modül down | 1 saat | Privilege escalation |
| P3 — Orta | Güvenlik açığı tespit, exploit yok | 4 saat | CVE bağımlılık |
| P4 — Düşük | Bilgilendirme, minor misconfiguration | 24 saat | Header eksikliği |

### 8.2 Olay Müdahale Akışı

```
Tespit (monitoring / alert / kullanıcı bildirimi)
    │
    ▼
Sınıflandırma (P1–P4 severity)
    │
    ├── P1/P2: On-call mühendis + İK güvenlik sorumlusu → WAR ROOM
    └── P3/P4: Security backlog'a eklenir
    │
    ▼
Kontrol altına alma (containment)
    ├── Token blacklist (tüm kullanıcı oturumları)
    ├── Etkilenen servis izolasyonu
    └── Firewall rule (saldırgan IP engelleme)
    │
    ▼
Kök neden analizi (RCA)
    │
    ▼
Düzeltme ve doğrulama
    │
    ▼
Post-mortem raporu (5 iş günü içinde)
    │
    ▼
KVKK bildirimi (veri ihlali ise 72 saat içinde Kurul'a)
```

### 8.3 Veri İhlali Bildirim Planı

| Adım | Süre | Sorumlu |
|------|------|---------|
| İhlal tespiti | - | Güvenlik ekibi |
| İç değerlendirme | 24 saat içinde | DPO + CTO |
| KVKK Kurulu bildirimi | 72 saat içinde | DPO |
| Veri sahiplerini bilgilendirme | "En kısa sürede" | DPO + İK |
| Düzeltici aksiyon raporu | 5 iş günü | Güvenlik ekibi |

---

## 9. Yedekleme ve Felaket Kurtarma

| Parametre | Değer |
|-----------|-------|
| Yedekleme sıklığı | Günlük tam yedek + saatlik incremental (WAL) |
| Yedekleme hedefi | Farklı availability zone (S3 uyumlu) |
| Yedek şifreleme | AES-256 (GPG) |
| Yedek saklama süresi | 30 gün (günlük), 12 ay (aylık anlık görüntü) |
| RPO (Recovery Point Objective) | ≤ 1 saat |
| RTO (Recovery Time Objective) | ≤ 4 saat |
| Geri dönüş testi | Üç aylık otomatik restore + doğrulama |
| Yedek erişim | Sadece DevOps lead + CTO (2-person rule) |

---

## 10. Güvenlik Testleri

| Test Tipi | Araç | Sıklık | Kapsam |
|-----------|------|--------|--------|
| Bağımlılık taraması (SCA) | Dependabot + Snyk | Her CI çalışması | Python + JS bağımlılıkları |
| SAST (statik analiz) | Bandit (Python), ESLint security | Her CI çalışması | Kaynak kod |
| Secret taraması | Gitleaks / TruffleHog | Her commit | Repo geçmişi |
| DAST (dinamik analiz) | OWASP ZAP | Her release öncesi | Staging ortamı |
| Penetrasyon testi | Dış firma | 6 aylık | Tüm sistem |
| Sosyal mühendislik | Phishing simülasyonu | Yıllık | Tüm kullanıcılar |
| Yedek geri dönüş | Otomatik script | 3 aylık | DB + dosya restore |
| Load / stress test | Locust / k6 | Her major release | API endpoint'leri |

### 10.1 CI Güvenlik Pipeline Adımları

```
Code push → Gitleaks (secret scan)
    │
    ▼
Bandit + ESLint-security (SAST)
    │
    ▼
Snyk / Dependabot (SCA)
    │
    ▼
Docker image scan (Trivy)
    │
    ▼
Unit + Integration tests
    │
    ▼
OWASP ZAP baseline (staging)
    │
    ▼
Deploy (eğer tüm gate'ler geçtiyse)
```

---

## 11. Güvenlik Eğitimi ve Farkındalık

| Hedef Kitle | İçerik | Sıklık |
|-------------|--------|--------|
| Tüm çalışanlar | Phishing, sosyal mühendislik | Yıllık |
| Geliştirici ekip | OWASP Top 10, secure coding | 6 aylık |
| DevOps ekip | Container güvenliği, secret yönetimi | 6 aylık |
| İK / DPO | KVKK, veri koruma | Yıllık |

---

## 12. Güvenlik Kontrol Listesi (Checklist)

| # | Kontrol | Durum |
|---|---------|-------|
| 1 | TLS 1.3 aktif, eski TLS devre dışı | ☐ |
| 2 | Argon2id parola hash kullanılıyor | ☐ |
| 3 | MFA admin roller için zorunlu | ☐ |
| 4 | Rate limiting tüm API'lerde aktif | ☐ |
| 5 | CORS whitelist konfigüre edildi | ☐ |
| 6 | Security headers eklendi (CSP, HSTS vb.) | ☐ |
| 7 | Row-level security (tenant izolasyonu) aktif | ☐ |
| 8 | Hassas alanlar şifreli (AES-256-GCM) | ☐ |
| 9 | Audit log tüm kritik işlemleri kapsar | ☐ |
| 10 | PII log'larda maskeleniyor | ☐ |
| 11 | Dosya yükleme ClamAV taramasından geçiyor | ☐ |
| 12 | Container imajları Trivy ile taranıyor | ☐ |
| 13 | Yedekler şifreli ve farklı zone'da | ☐ |
| 14 | Penetrasyon testi yapıldı | ☐ |
| 15 | Veri ihlali bildirim planı hazır | ☐ |
