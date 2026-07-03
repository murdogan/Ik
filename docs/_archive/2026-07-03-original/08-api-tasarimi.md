# 08 — API Tasarımı

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** REST API tasarım prensipleri, URL yapısı, response formatları, hata yönetimi, sayfalama, filtreleme, rate limiting, MVP endpoint listesi  
> **Referans:** 04-gereksinim-analizi.md, 05-teknoloji-secimi.md, 06-sistem-mimarisi.md, 07-veritabani-tasarimi.md

---

## 1. Amaç

Bu doküman, İK Yönetim Sistemi API'sinin genel kurallarını, standartlarını ve MVP kapsamındaki endpoint listesini tanımlar.

**Kapsam sınırı:** Bordro, performans, ATS, eğitim, vardiya gibi modüllerin endpoint detayları Faz 3'teki modül dokümanlarında tanımlanacaktır. Bu doküman tüm modüllerin uyacağı API kurallarını belirler.

---

## 2. Genel Prensipler

| Prensip | Karar |
|---------|-------|
| Protokol | REST (RESTful) |
| Veri formatı | JSON (request ve response) |
| Karakter seti | UTF-8 |
| Versiyonlama | URL bazlı: `/api/v1/...` |
| Kimlik doğrulama | Bearer Token (JWT) |
| Dokümantasyon | OpenAPI 3.1 (FastAPI otomatik üretim) |
| Content-Type | `application/json` (dosya upload hariç: `multipart/form-data`) |

---

## 3. URL Yapısı ve Kuralları

### 3.1 URL Formatı

```
https://{domain}/api/v{version}/{module}/{resource}
```

**Örnekler:**

```
GET    /api/v1/personnel/employees
GET    /api/v1/personnel/employees/42
POST   /api/v1/personnel/employees
PUT    /api/v1/personnel/employees/42
DELETE /api/v1/personnel/employees/42

GET    /api/v1/leave/requests
POST   /api/v1/leave/requests
PATCH  /api/v1/leave/requests/15/approve
```

### 3.2 URL Kuralları

| Kural | Doğru | Yanlış |
|-------|-------|--------|
| Çoğul isim kullanılır | `/employees` | `/employee` |
| Snake_case kullanılmaz, kebab-case tercih edilir | `/leave-types` | `/leave_types` |
| Fiil kullanılmaz (CRUD için) | `POST /employees` | `POST /create-employee` |
| İş aksiyonları için fiil kullanılabilir | `PATCH /requests/15/approve` | `PATCH /requests/15` body: {action: "approve"} |
| Nested resource en fazla 2 seviye | `/employees/42/documents` | `/departments/1/employees/42/documents/5` |
| Trailing slash kullanılmaz | `/employees` | `/employees/` |
| ID path'te, filtreler query string'de | `/employees/42`, `/employees?status=active` | |

### 3.3 Modül Prefixleri

| Modül | Prefix | Örnek |
|-------|--------|-------|
| Kimlik doğrulama | `/api/v1/auth` | `/api/v1/auth/login` |
| Personel | `/api/v1/personnel` | `/api/v1/personnel/employees` |
| İzin | `/api/v1/leave` | `/api/v1/leave/requests` |
| Self-servis | `/api/v1/me` | `/api/v1/me/profile` |
| Organizasyon | `/api/v1/organization` | `/api/v1/organization/departments` |
| Bildirim | `/api/v1/notifications` | `/api/v1/notifications` |
| Dosya | `/api/v1/documents` | `/api/v1/documents/upload` |
| Bordro | `/api/v1/payroll` | Faz 3 |
| Performans | `/api/v1/performance` | Faz 3 |
| İşe alım | `/api/v1/recruitment` | Faz 3 |
| Eğitim | `/api/v1/training` | Faz 3 |
| Vardiya | `/api/v1/shift` | Faz 3 |
| Raporlama | `/api/v1/reports` | Faz 3 |
| Entegrasyon | `/api/v1/integrations` | Faz 3 |
| Platform (admin) | `/api/v1/platform` | Tenant yönetimi |

---

## 4. HTTP Method Kullanımı

| Method | Amaç | Idempotent | Body | Örnek |
|--------|------|------------|------|-------|
| `GET` | Veri okuma (liste veya tekil) | Evet | Yok | `GET /employees`, `GET /employees/42` |
| `POST` | Yeni kayıt oluşturma | Hayır | Var | `POST /employees` |
| `PUT` | Kaydın tamamını güncelleme | Evet | Var | `PUT /employees/42` |
| `PATCH` | Kaydın kısmi güncellemesi veya iş aksiyonu | Hayır | Var | `PATCH /requests/15/approve` |
| `DELETE` | Kayıt silme (soft delete) | Evet | Yok | `DELETE /employees/42` |

### 4.1 PUT vs PATCH Ayrımı

| Durum | Method | Açıklama |
|-------|--------|----------|
| Çalışan profilinin tamamını güncelle | `PUT /employees/42` | Tüm alanlar gönderilir |
| Sadece telefon numarasını güncelle | `PATCH /employees/42` | Sadece değişen alan gönderilir |
| İzin talebini onayla | `PATCH /leave/requests/15/approve` | İş aksiyonu |
| İzin talebini reddet | `PATCH /leave/requests/15/reject` | İş aksiyonu |

---

## 5. Response Formatları

### 5.1 Başarılı Response — Tekil Kayıt

```json
{
  "success": true,
  "data": {
    "id": 42,
    "first_name": "Ahmet",
    "last_name": "Yılmaz",
    "email": "ahmet@firma.com",
    "department": {
      "id": 3,
      "name": "Yazılım Geliştirme"
    },
    "status": "active",
    "hire_date": "2024-03-15",
    "created_at": "2024-03-15T10:30:00Z",
    "updated_at": "2026-01-10T14:22:00Z"
  }
}
```

**HTTP Status:** `200 OK` (GET, PUT, PATCH) veya `201 Created` (POST)

### 5.2 Başarılı Response — Liste (Sayfalı)

```json
{
  "success": true,
  "data": [
    {
      "id": 42,
      "first_name": "Ahmet",
      "last_name": "Yılmaz",
      "status": "active"
    },
    {
      "id": 43,
      "first_name": "Elif",
      "last_name": "Kaya",
      "status": "active"
    }
  ],
  "pagination": {
    "page": 1,
    "size": 20,
    "total_items": 156,
    "total_pages": 8,
    "has_next": true,
    "has_previous": false
  }
}
```

### 5.3 Başarılı Response — Silme

```json
{
  "success": true,
  "message": "Kayıt başarıyla silindi."
}
```

**HTTP Status:** `200 OK`

### 5.4 Hata Response — Genel

```json
{
  "success": false,
  "error": {
    "code": "EMPLOYEE_NOT_FOUND",
    "message": "Çalışan bulunamadı.",
    "details": null
  }
}
```

### 5.5 Hata Response — Validasyon

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Giriş verileri geçersiz.",
    "details": [
      {
        "field": "email",
        "message": "Geçerli bir e-posta adresi giriniz."
      },
      {
        "field": "hire_date",
        "message": "İşe giriş tarihi bugünden sonra olamaz."
      }
    ]
  }
}
```

### 5.6 Boş Liste Response

```json
{
  "success": true,
  "data": [],
  "pagination": {
    "page": 1,
    "size": 20,
    "total_items": 0,
    "total_pages": 0,
    "has_next": false,
    "has_previous": false
  }
}
```

**Not:** Boş liste `200 OK` döner, `404` dönmez.

---

## 6. HTTP Status Kodları

### 6.1 Başarılı

| Kod | Kullanım |
|-----|----------|
| `200 OK` | GET, PUT, PATCH, DELETE başarılı |
| `201 Created` | POST ile yeni kayıt oluşturuldu |
| `204 No Content` | Başarılı ama dönecek veri yok (opsiyonel) |

### 6.2 İstemci Hataları

| Kod | Kullanım | Hata Kodu Örneği |
|-----|----------|-----------------|
| `400 Bad Request` | Geçersiz istek, validasyon hatası | `VALIDATION_ERROR`, `INVALID_DATE_RANGE` |
| `401 Unauthorized` | Token yok veya geçersiz | `TOKEN_EXPIRED`, `INVALID_TOKEN` |
| `403 Forbidden` | Yetki yok | `INSUFFICIENT_PERMISSIONS`, `TENANT_MISMATCH` |
| `404 Not Found` | Kayıt bulunamadı | `EMPLOYEE_NOT_FOUND`, `LEAVE_REQUEST_NOT_FOUND` |
| `409 Conflict` | Çakışma (unique ihlali, iş kuralı) | `EMAIL_ALREADY_EXISTS`, `LEAVE_OVERLAP` |
| `422 Unprocessable Entity` | İş kuralı hatası | `INSUFFICIENT_LEAVE_BALANCE`, `APPROVAL_NOT_ALLOWED` |
| `429 Too Many Requests` | Rate limit aşıldı | `RATE_LIMIT_EXCEEDED` |

### 6.3 Sunucu Hataları

| Kod | Kullanım | Hata Kodu Örneği |
|-----|----------|-----------------|
| `500 Internal Server Error` | Beklenmeyen hata | `INTERNAL_ERROR` |
| `503 Service Unavailable` | Bakım modu veya geçici kapasite sorunu | `SERVICE_UNAVAILABLE` |

---

## 7. Sayfalama (Pagination)

### 7.1 Query Parametreleri

| Parametre | Tip | Varsayılan | Açıklama |
|-----------|-----|-----------|----------|
| `page` | integer | 1 | Sayfa numarası (1'den başlar) |
| `size` | integer | 20 | Sayfa başına kayıt (max: 100) |

**Örnek:**

```
GET /api/v1/personnel/employees?page=2&size=20
```

### 7.2 Kurallar

- `size` değeri 1-100 arasında olmalıdır. 100'den büyük gönderilirse 100'e sabitlenir.
- `page` 0 veya negatif gönderilirse 1'e sabitlenir.
- Toplam kayıt sayısı `total_items` alanında döner.
- `has_next` ve `has_previous` boolean alanları navigasyonu kolaylaştırır.

---

## 8. Filtreleme ve Sıralama

### 8.1 Filtreleme

Filtreler query string üzerinden gönderilir:

```
GET /api/v1/personnel/employees?status=active&department_id=3&employment_type=full_time
```

**Özel filtre operatörleri:**

| Operatör | Format | Örnek | Açıklama |
|----------|--------|-------|----------|
| Eşittir | `field=value` | `status=active` | Basit eşitlik |
| Birden fazla değer | `field=val1,val2` | `status=active,on_leave` | OR koşulu |
| Tarih aralığı | `field_from`, `field_to` | `hire_date_from=2024-01-01&hire_date_to=2024-12-31` | Aralık |
| Arama | `search=text` | `search=ahmet` | Ad, soyad, sicil no üzerinde arama |

### 8.2 Sıralama

```
GET /api/v1/personnel/employees?sort=last_name        # A-Z
GET /api/v1/personnel/employees?sort=-created_at       # En yeni önce
GET /api/v1/personnel/employees?sort=department_id,-hire_date  # Çoklu sıralama
```

| Format | Açıklama |
|--------|----------|
| `sort=field` | Artan sıra (ASC) |
| `sort=-field` | Azalan sıra (DESC) |
| `sort=field1,-field2` | Çoklu sıralama |

### 8.3 Varsayılan Sıralama

Sıralama parametresi verilmezse varsayılan `sort=-created_at` (en yeni önce) uygulanır.

---

## 9. Kimlik Doğrulama ve Yetkilendirme

### 9.1 Auth Header

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 9.2 Public Endpoint'ler (Token Gerektirmeyen)

| Endpoint | Açıklama |
|----------|----------|
| `POST /api/v1/auth/login` | Giriş |
| `POST /api/v1/auth/refresh` | Token yenileme |
| `POST /api/v1/auth/forgot-password` | Şifre sıfırlama isteği |
| `POST /api/v1/auth/reset-password` | Şifre sıfırlama |
| `GET /api/v1/health` | Sistem sağlık kontrolü |

### 9.3 Yetki Kontrolü

Her endpoint için gerekli yetki `permission` olarak tanımlanır:

```
GET /api/v1/personnel/employees  →  personnel:employee:read
POST /api/v1/personnel/employees →  personnel:employee:create
PATCH /api/v1/leave/requests/15/approve →  leave:request:approve
```

**Format:** `{module}:{resource}:{action}`

Yetkisiz erişim durumunda `403 Forbidden` döner.

### 9.4 Veri Kapsamı

Yetki kontrolü iki katmandadır:

| Katman | Açıklama | Örnek |
|--------|----------|-------|
| Endpoint erişim | Kullanıcının bu endpoint'i çağırma yetkisi var mı | Çalışan rolü bordro endpoint'ine erişemez |
| Veri kapsamı | Kullanıcı hangi verileri görebilir | Dept. yöneticisi sadece kendi ekibini görür |

---

## 10. Rate Limiting

### 10.1 Limitler

| Endpoint Grubu | Limit | Pencere |
|----------------|-------|---------|
| Auth (login, refresh) | 10 istek | 1 dakika |
| Auth (forgot-password) | 3 istek | 15 dakika |
| Genel API (okuma) | 100 istek | 1 dakika |
| Genel API (yazma) | 30 istek | 1 dakika |
| Dosya upload | 10 istek | 1 dakika |
| Rapor üretimi | 5 istek | 5 dakika |

### 10.2 Rate Limit Header'ları

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1712678400
```

### 10.3 Aşıldığında

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Çok fazla istek gönderildi. Lütfen bekleyiniz.",
    "details": {
      "retry_after_seconds": 42
    }
  }
}
```

**HTTP Status:** `429 Too Many Requests`  
**Header:** `Retry-After: 42`

---

## 11. Dosya İşlemleri

### 11.1 Dosya Yükleme

```
POST /api/v1/documents/upload
Content-Type: multipart/form-data

file: (binary)
type: "health_report"
entity_type: "employee"
entity_id: 42
```

**Response:**

```json
{
  "success": true,
  "data": {
    "id": 128,
    "file_name": "saglik_raporu.pdf",
    "file_url": "/api/v1/documents/128/download",
    "file_size": 245760,
    "mime_type": "application/pdf",
    "created_at": "2026-04-09T10:00:00Z"
  }
}
```

### 11.2 Dosya Kuralları

| Kural | Değer |
|-------|-------|
| Maksimum dosya boyutu | 10 MB |
| İzin verilen tipler | PDF, DOCX, XLSX, JPEG, PNG |
| Dosya adı sanitizasyonu | Özel karakterler temizlenir, UUID prefix eklenir |
| Depolama | MinIO (S3 uyumlu) |
| Erişim | Signed URL ile, doğrudan MinIO erişimi yok |

---

## 12. Tarih ve Saat Formatları

| Alan | Format | Örnek |
|------|--------|-------|
| Tarih + saat (response) | ISO 8601, UTC, Z soneki | `2026-04-09T14:30:00Z` |
| Tarih + saat (request) | ISO 8601 | `2026-04-09T14:30:00Z` veya `2026-04-09T17:30:00+03:00` |
| Sadece tarih | `YYYY-MM-DD` | `2026-04-09` |
| DB'de saklama | `TIMESTAMPTZ` (UTC) | |
| İstemcide gösterim | Kullanıcının timezone'una göre dönüştürülür | Frontend/mobil sorumluluğu |

---

## 13. Versiyonlama

### 13.1 Strateji

API versiyonu URL path'inde tutulur:

```
/api/v1/personnel/employees
/api/v2/personnel/employees
```

### 13.2 Versiyonlama Kuralları

| Durum | Yeni Versiyon Gerekir mi? |
|-------|--------------------------|
| Yeni endpoint ekleme | Hayır — aynı versiyona eklenir |
| Response'a yeni alan ekleme | Hayır — geriye uyumlu |
| Opsiyonel request alanı ekleme | Hayır — geriye uyumlu |
| Zorunlu request alanı ekleme | Evet — breaking change |
| Response alanını kaldırma | Evet — breaking change |
| URL yapısını değiştirme | Evet — breaking change |

### 13.3 Deprecation Politikası

- Eski versiyon en az 6 ay desteklenir.
- Deprecated endpoint'ler `Sunset` header'ı ile bildirilir.
- OpenAPI spec'te deprecated olarak işaretlenir.

---

## 14. Health Check

```
GET /api/v1/health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-04-09T14:30:00Z",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "minio": "healthy",
    "celery": "healthy"
  }
}
```

**HTTP Status:** `200 OK` (tüm servisler sağlıklı), `503 Service Unavailable` (en az biri sağlıksız)

---

## 15. MVP Endpoint Listesi

### 15.1 Auth Modülü

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/auth/login` | Giriş | Public |
| `POST` | `/auth/logout` | Çıkış | Auth |
| `POST` | `/auth/refresh` | Token yenileme | Public (refresh token) |
| `POST` | `/auth/forgot-password` | Şifre sıfırlama e-postası | Public |
| `POST` | `/auth/reset-password` | Şifre sıfırlama | Public (token) |
| `POST` | `/auth/change-password` | Şifre değiştirme | Auth |
| `POST` | `/auth/verify-mfa` | MFA doğrulama | Auth |
| `POST` | `/auth/enable-mfa` | MFA etkinleştirme | Auth |
| `POST` | `/auth/disable-mfa` | MFA devre dışı bırakma | Auth |

### 15.2 Self-Servis Modülü (`/me`)

Giriş yapmış kullanıcının kendi verileri:

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/profile` | Kendi profil bilgilerini görüntüle | Auth |
| `PATCH` | `/me/profile` | Kısıtlı alanları güncelle (telefon, adres, acil durum) | Auth |
| `GET` | `/me/leaves` | Kendi izin talepleri | Auth |
| `POST` | `/me/leaves` | Yeni izin talebi oluştur | Auth |
| `DELETE` | `/me/leaves/{id}` | İzin talebini iptal et | Auth (pending ise) |
| `GET` | `/me/leave-balances` | Kendi izin bakiyeleri | Auth |
| `GET` | `/me/documents` | Kendi belgeleri | Auth |
| `GET` | `/me/notifications` | Bildirimler | Auth |
| `PATCH` | `/me/notifications/{id}/read` | Bildirimi okundu işaretle | Auth |
| `PATCH` | `/me/notifications/read-all` | Tümünü okundu işaretle | Auth |
| `GET` | `/me/notifications/stream` | SSE bildirim akışı | Auth |

### 15.3 Personel Modülü

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/personnel/employees` | Çalışan listesi (filtrelenebilir, sayfalı) | `personnel:employee:read` |
| `GET` | `/personnel/employees/{id}` | Çalışan detayı | `personnel:employee:read` |
| `POST` | `/personnel/employees` | Yeni çalışan oluştur | `personnel:employee:create` |
| `PUT` | `/personnel/employees/{id}` | Çalışan bilgilerini güncelle | `personnel:employee:update` |
| `DELETE` | `/personnel/employees/{id}` | Çalışanı sil (soft delete) | `personnel:employee:delete` |
| `GET` | `/personnel/employees/{id}/documents` | Çalışanın belgeleri | `personnel:document:read` |
| `POST` | `/personnel/employees/{id}/documents` | Çalışana belge yükle | `personnel:document:create` |
| `DELETE` | `/personnel/employees/{id}/documents/{doc_id}` | Belge sil | `personnel:document:delete` |
| `GET` | `/personnel/employees/{id}/job-history` | Terfi/nakil geçmişi | `personnel:employee:read` |
| `POST` | `/personnel/employees/{id}/job-history` | Terfi/nakil/zam kaydı | `personnel:employee:update` |
| `GET` | `/personnel/employees/{id}/contracts` | Sözleşmeler | `personnel:contract:read` |
| `POST` | `/personnel/employees/{id}/contracts` | Yeni sözleşme | `personnel:contract:create` |
| `POST` | `/personnel/employees/import` | Toplu Excel import | `personnel:employee:create` |
| `GET` | `/personnel/employees/export` | Excel export | `personnel:employee:read` |

### 15.4 İzin Modülü

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/types` | İzin türleri listesi | Auth |
| `POST` | `/leave/types` | Yeni izin türü tanımla | `leave:type:create` |
| `PUT` | `/leave/types/{id}` | İzin türü güncelle | `leave:type:update` |
| `GET` | `/leave/requests` | İzin talepleri (filtrelenebilir) | `leave:request:read` |
| `GET` | `/leave/requests/{id}` | İzin talebi detayı | `leave:request:read` |
| `POST` | `/leave/requests` | İK tarafından izin talebi oluştur | `leave:request:create` |
| `PATCH` | `/leave/requests/{id}/approve` | İzin talebini onayla | `leave:request:approve` |
| `PATCH` | `/leave/requests/{id}/reject` | İzin talebini reddet | `leave:request:approve` |
| `GET` | `/leave/balances` | Tüm çalışanların izin bakiyeleri | `leave:balance:read` |
| `GET` | `/leave/balances/{employee_id}` | Çalışanın izin bakiyeleri | `leave:balance:read` |
| `POST` | `/leave/balances/recalculate` | İzin bakiyelerini yeniden hesapla | `leave:balance:update` |
| `GET` | `/leave/calendar` | İzin takvimi (departman/ekip) | `leave:request:read` |

### 15.5 Organizasyon Modülü

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/organization/departments` | Departman listesi (ağaç yapısı) | Auth |
| `POST` | `/organization/departments` | Yeni departman | `organization:department:create` |
| `PUT` | `/organization/departments/{id}` | Departman güncelle | `organization:department:update` |
| `DELETE` | `/organization/departments/{id}` | Departman sil | `organization:department:delete` |
| `GET` | `/organization/positions` | Pozisyon listesi | Auth |
| `POST` | `/organization/positions` | Yeni pozisyon | `organization:position:create` |
| `PUT` | `/organization/positions/{id}` | Pozisyon güncelle | `organization:position:update` |
| `GET` | `/organization/chart` | Organizasyon şeması (hiyerarşik) | Auth |

### 15.6 Bildirim Modülü

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/notifications` | Bildirim listesi (sayfalı) | Auth |
| `GET` | `/notifications/unread-count` | Okunmamış bildirim sayısı | Auth |
| `PATCH` | `/notifications/{id}/read` | Okundu işaretle | Auth |
| `PATCH` | `/notifications/read-all` | Tümünü okundu işaretle | Auth |
| `GET` | `/notifications/stream` | SSE bildirim akışı | Auth |

### 15.7 Dosya Modülü

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/documents/upload` | Dosya yükle | Auth |
| `GET` | `/documents/{id}/download` | Dosya indir (signed URL) | Auth |
| `DELETE` | `/documents/{id}` | Dosya sil | Auth (yetki kontrolü) |

### 15.8 Platform Yönetimi

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/platform/tenants` | Firma listesi | `platform:tenant:read` |
| `POST` | `/platform/tenants` | Yeni firma oluştur | `platform:tenant:create` |
| `PUT` | `/platform/tenants/{id}` | Firma güncelle | `platform:tenant:update` |
| `GET` | `/platform/tenants/{id}/branches` | Şube listesi | `platform:tenant:read` |
| `POST` | `/platform/tenants/{id}/branches` | Yeni şube | `platform:branch:create` |

### 15.9 Sistem

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/health` | Sistem sağlık kontrolü | Public |
| `GET` | `/system/cities` | Şehir listesi | Auth |
| `GET` | `/system/districts?city_id=34` | İlçe listesi | Auth |
| `GET` | `/system/currencies` | Para birimleri | Auth |
| `GET` | `/system/public-holidays?year=2026` | Resmi tatiller | Auth |

---

## 16. Örnek İstek/Response Akışları

### 16.1 İzin Talebi Oluşturma (Çalışan)

**Request:**

```
POST /api/v1/me/leaves
Authorization: Bearer eyJhbG...
Content-Type: application/json
```

```json
{
  "leave_type_id": 1,
  "start_date": "2026-04-14",
  "end_date": "2026-04-18",
  "reason": "Aile ziyareti"
}
```

**Response (201 Created):**

```json
{
  "success": true,
  "data": {
    "id": 234,
    "employee": {
      "id": 42,
      "full_name": "Ahmet Yılmaz"
    },
    "leave_type": {
      "id": 1,
      "name": "Yıllık Ücretli İzin"
    },
    "start_date": "2026-04-14",
    "end_date": "2026-04-18",
    "total_days": 5.0,
    "reason": "Aile ziyareti",
    "status": "pending",
    "created_at": "2026-04-09T14:30:00Z"
  }
}
```

### 16.2 İzin Onaylama (Yönetici)

**Request:**

```
PATCH /api/v1/leave/requests/234/approve
Authorization: Bearer eyJhbG...
Content-Type: application/json
```

```json
{
  "comment": "Onaylandı, iyi tatiller."
}
```

**Response (200 OK):**

```json
{
  "success": true,
  "data": {
    "id": 234,
    "status": "approved",
    "approved_by": {
      "id": 10,
      "full_name": "Mehmet Demir"
    },
    "approved_at": "2026-04-09T15:00:00Z"
  }
}
```

### 16.3 Yetersiz İzin Bakiyesi Hatası

```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_LEAVE_BALANCE",
    "message": "Yeterli izin bakiyeniz bulunmamaktadır.",
    "details": {
      "requested_days": 5.0,
      "remaining_days": 3.0,
      "leave_type": "Yıllık Ücretli İzin"
    }
  }
}
```

**HTTP Status:** `422 Unprocessable Entity`

---

## 17. CORS Politikası

| Ortam | İzin Verilen Origin'ler |
|-------|------------------------|
| Local | `http://localhost:3000`, `http://localhost:8000` |
| Staging | `https://staging.ikplatform.com` |
| Production | `https://ikplatform.com`, `https://*.ikplatform.com` |

**İzin verilen header'lar:** `Authorization`, `Content-Type`, `X-Request-ID`  
**İzin verilen method'lar:** `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`

---

## 18. Request ID ve İzlenebilirlik

Her istek bir `X-Request-ID` header'ı taşır:

- İstemci gönderirse kullanılır, göndermezse sunucu UUID üretir.
- Response'ta `X-Request-ID` header'ı ile döner.
- Loglar, Sentry hataları ve audit kayıtlarında bu ID ile ilişkilendirilir.
- Hata durumunda destek ekibine bu ID iletilir.

```
Request:  X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
Response: X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

---

## 19. Faz 3 İçin Not

Aşağıdaki modüllerin endpoint detayları ilgili modül dokümanlarında tanımlanacaktır:

| Modül | Doküman | Beklenen Endpoint Grupları |
|-------|---------|---------------------------|
| Bordro & Maaş | 14-modul-bordro-maas.md | Bordro hesaplama, PDF, banka dosyası, maaş simülasyonu |
| Performans | 13-modul-performans-yonetimi.md | OKR, KPI, değerlendirme, 360° feedback |
| İşe Alım (ATS) | 11-modul-ise-alim-ats.md | İlan, başvuru, aday takip, mülakat, teklif |
| Eğitim | 15-modul-egitim-gelisim.md | Eğitim kaydı, katılım, sertifika |
| Vardiya & Mesai | 16-modul-vardiya-mesai.md | Vardiya planlama, puantaj, PDKS |
| Raporlama | 18-modul-raporlama-analitik.md | Dashboard, rapor üretimi, metrikler |
| Entegrasyon | 09-entegrasyon-haritasi.md | SGK, banka, muhasebe, SMS, e-posta |

Bu endpoint'ler tanımlanırken bu dokümandaki URL yapısı, response formatı, hata kodları ve yetki kurallarına uyulacaktır.

---

## 20. Sonuç

API tasarımı aşağıdaki temeller üzerine kurulmuştur:

- **Tutarlı URL yapısı:** `/api/v1/{module}/{resource}`, kebab-case, çoğul isimler
- **Standart response formatı:** `{ success, data, pagination }` ve `{ success, error: { code, message, details } }`
- **Anlamlı HTTP status kodları:** 2xx başarı, 4xx istemci hatası, 5xx sunucu hatası
- **Sayfalama + filtreleme + sıralama:** Query string bazlı, tutarlı
- **Rate limiting:** Endpoint grubuna göre farklı limitler
- **Yetki modeli:** `{module}:{resource}:{action}` formatı
- **MVP odaklı endpoint listesi:** Auth + Personel + İzin + Self-Servis + Organizasyon + Bildirim

Bir sonraki adımda [09-entegrasyon-haritasi.md](09-entegrasyon-haritasi.md) dokümanında SGK, e-Devlet, banka, muhasebe, SMS, e-posta ve PDKS entegrasyonları detaylandırılacaktır.
