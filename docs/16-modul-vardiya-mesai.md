# 16 — Modül: Vardiya & Mesai Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Vardiya şablonları, çalışma takvimi, puantaj, fazla mesai, resmi tatil ve hafta sonu çalışma, PDKS entegrasyonu, devam istisnaları  
> **Faz:** Faz 2 — İzin ve Bordro modüllerinden sonra devreye alınır  
> **Referans:** 04-gereksinim-analizi.md, 09-entegrasyon-haritasi.md, 12-modul-izin-devamsizlik.md, 14-modul-bordro-maas.md

---

## 1. Modül Özeti

Vardiya & Mesai Yönetimi modülü; çalışanların planlı çalışma düzenlerini, fiili giriş-çıkış verilerini ve bunlardan türeyen puantaj ile fazla mesai hesaplarını yönetir. Modül özellikle saha, operasyon, üretim ve destek ekiplerinde vardiyalı çalışma düzeni için kritik rol oynar.

### 1.1 Kapsam

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| Vardiya şablonu tanımı | Karmaşık üretim optimizasyonu |
| Haftalık/aylık çalışma planı | Biometrik cihaz firmware yönetimi |
| Giriş-çıkış kayıtları | Turnike donanım yönetimi |
| Fazla mesai ve vardiya farkı | Tam zamanlı rota planlama |
| PDKS entegrasyonu | — |

### 1.2 Temel Akış

```
Vardiya planı hazırlandı
    ▼
Çalışanlara atandı
    ▼
PDKS veya manuel giriş-çıkış verisi işlendi
    ▼
Sapmalar ve mesailer hesaplandı
    ▼
Bordroya referans puantaj üretildi
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|----------------|-------------------|-----------------|
| **Operasyon Yöneticisi** | Vardiya planlayıcı | Günlük / haftalık | Vardiya atama, plan değişikliği, açık vardiya takibi |
| **Ayşe (İK / Bordro Uzmanı)** | Puantaj doğrulayıcı | Aylık yoğun | Puantaj onayı, mesai onayı, bordro aktarımı |
| **Mehmet (Dept. Yöneticisi)** | Mesai onaylayıcı | Haftalık | Ekibinin mesai taleplerini onaylama, puantaj kontrolü |
| **Zeynep (Çalışan)** | Son kullanıcı | Günlük / haftalık | Kendi takvimini görme, mesai talebi, giriş-çıkış |
| **Hakan (Genel Müdür)** | Dashboard tüketici | Aylık | Devam analitiği, mesai maliyet raporu |

### 2.2 Operasyon Yöneticisi — Vardiya Planlama Yolculuğu

```
PLANLAMA               ATAMA                    TAKİP
   │                      │                        │
   ▼                      ▼                        ▼
Gelecek hafta/ay       Çalışanlara vardiya      Giriş-çıkış verilerini
planını oluştur        atamalarını yap           izle
   │                      │                        │
   ├─ Şablonlardan seç   ├─ Sürükle-bırak veya  ├─ Geç gelen/eksik
   ├─ İzinli olanları    │  toplu atama           │  kayıtları gör
   │  kontrol et         ├─ Çakışma kontrolü     ├─ Mesai taleplerini
   └─ Kapasite planla    └─ Bildirim gönder        │  onayla
                                                   └─ Puantaj raporunu
                                                      kontrol et
```

### 2.3 Çalışan — Vardiya ve Mesai Yolculuğu

```
TAKVİM                  GİRİŞ-ÇIKIŞ             MESAİ TALEBİ
   │                       │                        │
   ▼                       ▼                        ▼
Kendi vardiya          PDKS / mobil              Fazla mesai
takvimimi gör          giriş-çıkış               talebi oluştur
   │                    kayıtlarım                   │
   ├─ Bu hafta plan     ├─ Anlık giriş-çıkış    ├─ Tarih ve saat
   ├─ Değişiklikler     ├─ Eksik kayıt varsa     ├─ Gerekçe
   └─ Bildirimler       │  uyarı görür          └─ Yönetici onayına
                        └─ Puantaj özetim            gönder
```

---

## 3. Fonksiyonel Gereksinimler

### 3.1 Vardiya Şablon Yönetimi

#### FR-SHF-01: Vardiya Şablonu Tanımlama

**Açıklama:** Vardiya şablonunda başlangıç, bitiş, mola, lokasyon ve vardiya tipi tanımlanabilmeli.

**Vardiya Tipleri:**

| Tip | Açıklama | Mola | Gece Farkı |
|-----|----------|------|------------|
| `morning` | Sabah vardiyası (ör. 08:00-16:00) | 1 saat | Hayır |
| `afternoon` | Öğleden sonra (ör. 16:00-00:00) | 1 saat | Kısmi |
| `night` | Gece vardiyası (ör. 00:00-08:00) | 1 saat | Evet (+%10) |
| `split` | Bölünmüş (ör. 08:00-12:00 + 17:00-21:00) | Arası tatil | Kısmi |
| `flexible` | Esnek çalışma (çekirdek saat tanımlı) | Tenant ayarı | — |
| `office` | Standart ofis (ör. 09:00-18:00) | 1 saat | Hayır |

**Şablon Konfigürasyonu:**

| Özellik | Açıklama |
|---------|----------|
| Başlangıç saati | HH:MM |
| Bitiş saati | HH:MM |
| Mola süresi (dakika) | Planlanan mola |
| Net çalışma süresi | Otomatik hesaplanan |
| Tolerans (dakika) | Geç gelme/erken çıkış toleransı |
| Lokasyon | Fiziksel adres veya şube |
| Renk kodu | Takvimde gösterilecek renk |

#### FR-SHF-02: Vardiya Planı Oluşturma

**Plan Tipleri:**

| Tip | Açıklama |
|-----|----------|
| Tekil atama | Belirli bir gün için tekil vardiya |
| Haftalık tekrar | Her hafta aynı düzende tekrar eden |
| Rotasyon | A-B-C vardiyaları arası dönüşümlü |
| Aylık plan | Tüm ayın planı toplu olarak |

#### FR-SHF-03: Giriş-Çıkış Kayıtları ve PDKS Entegrasyonu

**Veri Kaynakları:**

| Kaynak | Açıklama | Öncelik |
|--------|----------|---------|
| PDKS cihaz | Kart, parmak izi, yüz tanıma | Birincil (tenant ayarı) |
| Mobil check-in | GPS doğrulama ile | İkincil |
| Manuel kayıt | İK veya yönetici girişi | Düzeltme amaçlı |
| API import | Dış sistem entegrasyonu | Toplu import |

**PDKS Entegrasyon Protokolleri:**

| Protokol | Açıklama |
|----------|----------|
| REST API pull | Cihaz yazılımından zamanlanmış çekme |
| Webhook push | Cihaz anlık bildirim gönderir |
| Dosya import | CSV/XML dosya yükleme (batch) |

#### FR-SHF-04: Sapma ve Fazla Mesai Hesaplama

**Hesaplama Kuralları:**

```
Geç gelme = Fiili giriş − Planlı başlangıç (tolerans düşülür)
Erken çıkış = Planlı bitiş − Fiili çıkış (tolerans düşülür)
Eksik çalışma = Planlı net süre − Fiili net süre
Fazla mesai = Fiili çalışma − Planlı çalışma (pozitif ise)
```

**Mesai Katsayıları (14-modul-bordro-maas.md ile uyumlu):**

| Durum | Katsayı | Açıklama |
|-------|---------|----------|
| Normal fazla mesai | ×1,5 | Haftalık 45 saat üzeri |
| Hafta sonu | ×1,5 | Tenant ayarına göre |
| Resmi tatil | ×2,0 | Resmi tatil günü çalışma |
| Gece vardiya farkı | +%10 | 20:00-06:00 arası |

#### FR-SHF-05: Mesai Onay Akışı

```
Sistem mesai tespit etti
    │
    ▼
Otomatik fazla mesai kaydı oluşturuldu
    │
    ▼
Yönetici onayına gönderildi
    │
    ├── ONAYLADI → Bordroya aktarılır
    └── REDDETTİ → Kayıt pasif, gerekçe zorunlu
```

#### FR-SHF-06: İzin-Vardiya Çakışma Kontrolü

| Durum | Aksiyon |
|-------|---------|
| İzinli güne vardiya atama | Uyarı göster, yönetici override edebilir |
| Vardiyalı güne izin talebi | Vardiya bilgisi izin formunda gösterilir |
| Devamsız çalışan | Devamsızlık kaydı vardiya baz alınarak oluşturulur |

### 3.2 İş Kuralları

| Kural | Açıklama |
|-------|----------|
| IK-SHF-01 | Aynı çalışan aynı zaman aralığında iki vardiyaya atanamaz |
| IK-SHF-02 | Onaysız fazla mesai bordroya varsayılan olarak aktarılmaz |
| IK-SHF-03 | PDKS verisi ile manuel düzeltme arasında kaynak önceliği tenant ayarıdır |
| IK-SHF-04 | Gece vardiyası tanımı (başlangıç/bitiş saat) tenant bazında yapılandırılabilir |
| IK-SHF-05 | İki vardiya arası minimum dinlenme süresi 11 saattir (İş Kanunu); ihlal uyarı üretir |
| IK-SHF-06 | Haftalık 45 saat aşımında sistem otomatik fazla mesai kaydı oluşturur |
| IK-SHF-07 | PDKS verisi gelmezse çalışanın o günü "eksik kayıt" olarak işaretlenir |
| IK-SHF-08 | Puantaj verileri bordro dönem kapanışına kadar düzeltilebilir; kapanış sonrası kilitlenir |
| IK-SHF-09 | Geç gelme toleransı (ör. 5-15 dk) tenant ayarı olarak belirlenir |

---

## 4. Veritabanı Tasarımı

### 4.1 shift_templates

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | Multi-tenant |
| `name` | VARCHAR(100) | Şablon adı (ör. "Sabah 08-16") |
| `code` | VARCHAR(20) UNIQUE | Kısa kod (ör. "SBH-08") |
| `shift_type` | ENUM | `morning`, `afternoon`, `night`, `split`, `flexible`, `office` |
| `start_time` | TIME | Vardiya başlangıç saati |
| `end_time` | TIME | Vardiya bitiş saati |
| `break_minutes` | SMALLINT | Mola süresi (dakika) |
| `net_work_minutes` | SMALLINT | Otomatik: (bitiş-başlangıç) − mola |
| `late_tolerance_min` | SMALLINT DEFAULT 5 | Geç gelme toleransı (dk) |
| `early_leave_tolerance_min` | SMALLINT DEFAULT 5 | Erken çıkış toleransı |
| `color_hex` | VARCHAR(7) | Takvim rengi (ör. #FF9800) |
| `location` | VARCHAR(200) | Varsayılan çalışma lokasyonu |
| `is_night_shift` | BOOLEAN DEFAULT FALSE | Gece vardiyası mı |
| `night_premium_pct` | DECIMAL(5,2) DEFAULT 10.00 | Gece zammı yüzdesi |
| `is_active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### 4.2 shift_plans

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `name` | VARCHAR(100) | Plan adı (ör. "Ocak 2025 Üretim") |
| `plan_type` | ENUM | `single`, `weekly_repeat`, `rotation`, `monthly` |
| `department_id` | UUID FK → departments NULL | Departman bazlı plan |
| `start_date` | DATE | Plan başlangıç |
| `end_date` | DATE | Plan bitiş |
| `status` | ENUM | `draft`, `published`, `archived` |
| `created_by` | UUID FK → users | Oluşturan |
| `published_at` | TIMESTAMPTZ | Yayınlanma zamanı |
| `created_at` | TIMESTAMPTZ | |

### 4.3 shift_assignments

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `plan_id` | UUID FK → shift_plans NULL | Bağlı plan |
| `employee_id` | UUID FK → employees | Atanan çalışan |
| `template_id` | UUID FK → shift_templates | Kullanılan şablon |
| `shift_date` | DATE | Vardiya tarihi |
| `actual_start` | TIME NULL | Fiili başlangıç (varsa) |
| `actual_end` | TIME NULL | Fiili bitiş (varsa) |
| `status` | ENUM DEFAULT 'assigned' | `assigned`, `completed`, `absent`, `cancelled` |
| `notes` | TEXT NULL | Yönetici notu |
| `created_at` | TIMESTAMPTZ | |

**Kısıtlamalar:**

```sql
ALTER TABLE shift_assignments
  ADD CONSTRAINT uq_shift_per_employee_date
  UNIQUE (tenant_id, employee_id, shift_date);

CREATE INDEX ix_shift_assignments_lookup
  ON shift_assignments (tenant_id, employee_id, shift_date);
CREATE INDEX ix_shift_assignments_plan
  ON shift_assignments (plan_id, shift_date);
```

### 4.4 attendance_logs

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `employee_id` | UUID FK → employees | |
| `event_time` | TIMESTAMPTZ | Giriş veya çıkış zamanı |
| `event_type` | ENUM | `clock_in`, `clock_out`, `break_start`, `break_end` |
| `source` | ENUM | `pdks_device`, `mobile_checkin`, `manual`, `api_import` |
| `device_id` | VARCHAR(50) NULL | PDKS cihaz kimliği |
| `latitude` | DECIMAL(10,7) NULL | Mobil check-in GPS |
| `longitude` | DECIMAL(10,7) NULL | Mobil check-in GPS |
| `ip_address` | INET NULL | Kaynak IP |
| `is_corrected` | BOOLEAN DEFAULT FALSE | Manuel düzeltme mi |
| `corrected_by` | UUID FK → users NULL | Düzelten kişi |
| `correction_reason` | TEXT NULL | Düzeltme nedeni |
| `raw_payload` | JSONB NULL | PDKS cihaz ham verisi |
| `created_at` | TIMESTAMPTZ | |

```sql
CREATE INDEX ix_attendance_logs_lookup
  ON attendance_logs (tenant_id, employee_id, event_time);
CREATE INDEX ix_attendance_logs_source
  ON attendance_logs (tenant_id, source, event_time);
```

### 4.5 timesheet_summaries

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `employee_id` | UUID FK → employees | |
| `assignment_id` | UUID FK → shift_assignments NULL | İlişkili vardiya |
| `summary_date` | DATE | Puantaj tarihi |
| `planned_minutes` | SMALLINT | Planlı çalışma süresi |
| `actual_minutes` | SMALLINT | Fiili çalışma süresi |
| `break_minutes` | SMALLINT | Fiili mola süresi |
| `late_minutes` | SMALLINT DEFAULT 0 | Geç gelme (tolerans düşülmüş) |
| `early_leave_minutes` | SMALLINT DEFAULT 0 | Erken çıkış (tolerans düşülmüş) |
| `overtime_minutes` | SMALLINT DEFAULT 0 | Fazla mesai dakikası |
| `overtime_type` | ENUM NULL | `normal`, `weekend`, `holiday`, `night` |
| `status` | ENUM DEFAULT 'pending' | `pending`, `approved`, `locked` |
| `approved_by` | UUID FK → users NULL | |
| `approved_at` | TIMESTAMPTZ NULL | |
| `locked_at` | TIMESTAMPTZ NULL | Bordro kapanışında kilitlenme |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

```sql
ALTER TABLE timesheet_summaries
  ADD CONSTRAINT uq_timesheet_per_day
  UNIQUE (tenant_id, employee_id, summary_date);
```

### 4.6 overtime_requests

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `employee_id` | UUID FK → employees | |
| `timesheet_id` | UUID FK → timesheet_summaries NULL | İlişkili puantaj |
| `request_date` | DATE | Mesai tarihi |
| `requested_minutes` | SMALLINT | Talep edilen süre |
| `approved_minutes` | SMALLINT NULL | Onaylanan süre |
| `overtime_type` | ENUM | `normal`, `weekend`, `holiday` |
| `multiplier` | DECIMAL(3,2) | Katsayı (1.50, 2.00) |
| `reason` | TEXT | Mesai gerekçesi |
| `status` | ENUM DEFAULT 'pending' | `pending`, `approved`, `rejected` |
| `decided_by` | UUID FK → users NULL | |
| `decided_at` | TIMESTAMPTZ NULL | |
| `rejection_reason` | TEXT NULL | Red gerekçesi (zorunlu) |
| `payroll_exported` | BOOLEAN DEFAULT FALSE | Bordroya aktarıldı mı |
| `created_at` | TIMESTAMPTZ | |

---

## 5. API Endpoint Detayları

### 5.1 Vardiya Şablonları

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/shifts/templates` | Şablon listesi | `shift:read` |
| `POST` | `/shifts/templates` | Şablon oluştur | `shift:create` |
| `PUT` | `/shifts/templates/{id}` | Şablon güncelle | `shift:create` |
| `DELETE` | `/shifts/templates/{id}` | Şablon pasif et | `shift:delete` |

**POST /shifts/templates — İstek:**

```json
{
  "name": "Sabah Vardiyası 08-16",
  "code": "SBH-08",
  "shift_type": "morning",
  "start_time": "08:00",
  "end_time": "16:00",
  "break_minutes": 60,
  "late_tolerance_min": 10,
  "early_leave_tolerance_min": 5,
  "color_hex": "#FF9800",
  "location": "Fabrika A Binası",
  "is_night_shift": false
}
```

**Yanıt (201):**

```json
{
  "id": "tpl-uuid",
  "name": "Sabah Vardiyası 08-16",
  "code": "SBH-08",
  "net_work_minutes": 420,
  "created_at": "2025-01-15T10:00:00Z"
}
```

### 5.2 Vardiya Planları

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/shifts/plans` | Plan listesi | `shift:read` |
| `POST` | `/shifts/plans` | Plan oluştur | `shift:plan:create` |
| `PATCH` | `/shifts/plans/{id}/publish` | Planı yayınla | `shift:plan:create` |

### 5.3 Vardiya Atamaları

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/shifts/assignments` | Tekil atama | `shift:assign` |
| `POST` | `/shifts/assignments/bulk` | Toplu atama | `shift:assign` |
| `GET` | `/shifts/assignments` | Atama listesi (filtre) | `shift:read` |
| `DELETE` | `/shifts/assignments/{id}` | Atama iptal | `shift:assign` |

**POST /shifts/assignments/bulk — İstek:**

```json
{
  "plan_id": "plan-uuid",
  "assignments": [
    { "employee_id": "emp-001", "template_id": "tpl-uuid", "shift_date": "2025-02-03" },
    { "employee_id": "emp-001", "template_id": "tpl-uuid", "shift_date": "2025-02-04" },
    { "employee_id": "emp-002", "template_id": "tpl-uuid", "shift_date": "2025-02-03" }
  ]
}
```

**Yanıt (201):**

```json
{
  "created": 3,
  "conflicts": [],
  "warnings": [
    { "employee_id": "emp-002", "date": "2025-02-03", "message": "Çalışanın bu tarihte onaylı izni var" }
  ]
}
```

### 5.4 Giriş-Çıkış Kayıtları

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/shifts/attendance/clock` | Giriş/çıkış kaydı | Auth |
| `POST` | `/shifts/attendance/import` | PDKS toplu import | `shift:attendance:import` |
| `GET` | `/shifts/attendance` | Kayıt listesi (filtre) | `shift:attendance:read` |
| `PATCH` | `/shifts/attendance/{id}/correct` | Manuel düzeltme | `shift:attendance:correct` |

**POST /shifts/attendance/clock — İstek (Mobil Check-in):**

```json
{
  "event_type": "clock_in",
  "latitude": 41.0082,
  "longitude": 28.9784
}
```

**POST /shifts/attendance/import — İstek (PDKS Batch):**

```json
{
  "source": "pdks_device",
  "device_id": "PDKS-A1-001",
  "records": [
    { "employee_code": "EMP001", "event_time": "2025-02-03T07:58:00+03:00", "event_type": "clock_in" },
    { "employee_code": "EMP001", "event_time": "2025-02-03T16:02:00+03:00", "event_type": "clock_out" }
  ]
}
```

### 5.5 Puantaj Yönetimi

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/shifts/timesheets` | Puantaj listesi | `shift:timesheet:read` |
| `GET` | `/shifts/timesheets/summary` | Dönem özet rapor | `shift:timesheet:read` |
| `PATCH` | `/shifts/timesheets/{id}/approve` | Puantaj onayı | `shift:timesheet:approve` |
| `POST` | `/shifts/timesheets/lock` | Dönem kilitle (bordro) | `shift:timesheet:lock` |

**GET /shifts/timesheets — Yanıt:**

```json
{
  "items": [
    {
      "id": "ts-uuid",
      "employee": { "id": "emp-001", "full_name": "Ali Yılmaz" },
      "summary_date": "2025-02-03",
      "planned_minutes": 420,
      "actual_minutes": 450,
      "late_minutes": 0,
      "overtime_minutes": 30,
      "overtime_type": "normal",
      "status": "pending"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

### 5.6 Fazla Mesai Talepleri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/shifts/overtime-requests` | Mesai talebi oluştur | Auth |
| `GET` | `/shifts/overtime-requests` | Talep listesi | `shift:overtime:read` |
| `PATCH` | `/shifts/overtime-requests/{id}/decide` | Onayla/reddet | `shift:overtime:approve` |
| `POST` | `/shifts/overtime-requests/export-payroll` | Bordroya aktar | `shift:overtime:export` |

### 5.7 Self-Servis

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/shifts` | Kendi vardiya takvimim | Auth |
| `GET` | `/me/shifts/timesheets` | Kendi puantajım | Auth |
| `GET` | `/me/shifts/overtime-requests` | Kendi mesai taleplerim | Auth |
| `POST` | `/me/shifts/attendance/clock` | Giriş-çıkış kaydet | Auth |

---

## 6. Ekranlar ve Raporlar

### 6.1 Aylık Vardiya Planlama Ekranı

```
┌─────────────────────────────────────────────────────────────────┐
│  Vardiya Planı: Ocak 2025 — Üretim Departmanı    [Yayınla]     │
├─────────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┤
│ Çalışan │ Pzt  │ Sal  │ Çar  │ Per  │ Cum  │ Cmt  │ Paz  │ Saat │
├─────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│ Ali Y.  │ SBH  │ SBH  │ SBH  │ SBH  │ SBH  │  —   │  —   │  40h │
│ Ayşe K. │ ÖSN  │ ÖSN  │ ÖSN  │ ÖSN  │ ÖSN  │  —   │  —   │  40h │
│ Mehmet  │ GCE  │ GCE  │  —   │  —   │ GCE  │ GCE  │ GCE  │  40h │
│ Zeynep  │ İZN  │ İZN  │ SBH  │ SBH  │ SBH  │  —   │  —   │  24h │
└─────────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
  [SBH] 08-16  [ÖSN] 16-00  [GCE] 00-08  [İZN] İzinli  [—] Boş
  
  Sürükle-bırak ile şablon ata | Sağ tık → Günü boşalt
```

### 6.2 Günlük Puantaj Ekranı

```
┌─────────────────────────────────────────────────────────────────┐
│  Puantaj — 3 Şubat 2025                [Tümünü Onayla] [Filtre]│
├─────────┬────────┬────────┬────────┬──────┬──────┬─────────────┤
│ Çalışan │ Plan   │ Giriş  │ Çıkış  │ Geç  │ Mesai│ Durum       │
├─────────┼────────┼────────┼────────┼──────┼──────┼─────────────┤
│ Ali Y.  │ 08-16  │ 07:58  │ 16:32  │  —   │ 30dk │ ⏳ Onay bek.│
│ Ayşe K. │ 08-16  │ 08:12  │ 16:00  │  2dk │  —   │ ✅ Normal   │
│ Mehmet  │ 08-16  │  —     │  —     │  —   │  —   │ ⚠️ Eksik    │
│ Zeynep  │ İzinli │  —     │  —     │  —   │  —   │ 🏖 İzinli   │
└─────────┴────────┴────────┴────────┴──────┴──────┴─────────────┘
```

### 6.3 Mesai Onay Paneli

```
┌─────────────────────────────────────────────────────────────────┐
│  Fazla Mesai Onay Paneli                      3 kayıt bekliyor │
├─────────┬──────────┬───────┬──────┬──────────┬─────────────────┤
│ Çalışan │ Tarih    │ Süre  │ Tip  │ Gerekçe  │ İşlem           │
├─────────┼──────────┼───────┼──────┼──────────┼─────────────────┤
│ Ali Y.  │ 03.02.25 │ 30 dk │ Norm │ Sipariş  │ [Onayla] [Red]  │
│ Fatma S.│ 03.02.25 │ 2 sa  │ Tatil│ Acil bak │ [Onayla] [Red]  │
│ Emre D. │ 01.02.25 │ 45 dk │ Norm │ Vardiya  │ [Onayla] [Red]  │
└─────────┴──────────┴───────┴──────┴──────────┴─────────────────┘
```

### 6.4 PDKS Entegrasyon Monitör

```
┌─────────────────────────────────────────────────────────────────┐
│  PDKS Cihaz Durumu                               Son 24 saat   │
├──────────────┬──────────┬─────────┬──────────┬─────────────────┤
│ Cihaz        │ Lokasyon │ Son Sinyal │ Kayıt  │ Durum          │
├──────────────┼──────────┼──────────┼──────────┼─────────────────┤
│ PDKS-A1-001  │ Giriş A  │ 5 dk önce│ 142     │ 🟢 Aktif       │
│ PDKS-A1-002  │ Giriş B  │ 3 dk önce│ 98      │ 🟢 Aktif       │
│ PDKS-B1-001  │ Arka Giriş│ 2 sa önce│ 0      │ 🔴 Bağlantı yok│
└──────────────┴──────────┴──────────┴──────────┴─────────────────┘
```

### 6.5 Devam Analitiği Raporu

| Rapor | Açıklama | Çıktı |
|-------|----------|-------|
| Geç gelme trendi | Departman/çalışan bazında geç gelme oranı | Grafik + tablo |
| Devamsızlık oranı | Departman bazında devamsızlık yüzdesi | Grafik |
| Mesai maliyet raporu | Dönem bazında mesai saatleri ve tahmini maliyet | PDF/Excel |
| Vardiya doluluk analizi | Şablon bazında kapasite kullanım oranı | Grafik |
| PDKS sapma raporu | Eksik kayıt, anormallik listesi | Tablo |

---

## 7. Celery Beat / Zamanlanmış Görevler

| Görev | Cron | Açıklama |
|-------|------|----------|
| `calculate_daily_timesheets` | Her gün 02:00 | Önceki günün giriş-çıkış verilerinden puantaj satırı oluşturur |
| `detect_attendance_anomalies` | Her gün 03:00 | Eksik giriş/çıkış, çift giriş gibi sapmaları tespit eder |
| `pull_pdks_records` | Her 15 dk | PDKS cihazlarından yeni kayıtları çeker (REST API pull yöntemi) |
| `auto_create_overtime_records` | Her gün 04:00 | 45 saat/hafta aşımı olan çalışanlara otomatik mesai kaydı oluşturur |
| `lock_timesheets_for_payroll` | Ay sonu + 5. iş günü | Bordro dönemindeki puantajları kilitler |
| `send_missing_record_alerts` | Her gün 10:00 | Eksik giriş-çıkış kaydı olan çalışanlara bildirim gönderir |

---

## 8. Bildirim Şablonları

| Bildirim | Kanal | Alıcı | Tetikleyici |
|----------|-------|-------|-------------|
| Vardiya atandı | Push + E-posta | Çalışan | Yeni vardiya ataması yapıldığında |
| Vardiya değişikliği | Push + E-posta | Çalışan | Mevcut atama güncellendiğinde |
| Mesai talebi oluştu | Push | Yönetici | Çalışan mesai talebi gönderdiğinde |
| Mesai onaylandı/reddedildi | Push + E-posta | Çalışan | Yönetici karar verdiğinde |
| Eksik giriş-çıkış kaydı | Push | Çalışan + İK | Günlük sapma kontrolünde |
| Puantaj onayı bekleniyor | E-posta | Yönetici | Ay sonunda onaylanmamış puantaj varsa |
| PDKS bağlantı sorunu | E-posta | IT admin | Cihaz 1 saatten fazla sinyal göndermezse |

---

## 9. Güvenlik ve Uyumluluk

### 9.1 KVKK / GDPR

| Konu | Uygulama |
|------|----------|
| Lokasyon verisi (GPS) | Açık rıza ile toplanır; mobil check-in opsiyonel |
| Biyometrik PDKS | Açık rıza formu zorunlu; veri hash olarak saklanır |
| Puantaj verileri | Minimum 5 yıl saklama (İş Kanunu); sonra anonimleştirme |
| Erişim kısıtı | Çalışan yalnızca kendi verilerini görür |
| Maskeleme | Cihaz ham verileri (raw_payload) sadece admin erişimli |

### 9.2 Rol-Erişim Matrisi

| Yetki | Süper Admin | İK Uzmanı | Dept. Yöneticisi | Çalışan |
|-------|:-----------:|:---------:|:----------------:|:-------:|
| Şablon CRUD | ✅ | ✅ | ❌ | ❌ |
| Plan oluştur/yayınla | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| Vardiya atama | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| Puantaj görüntüle | ✅ | ✅ | ✅ (kendi dept.) | ✅ (kendi) |
| Puantaj onayla | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| Puantaj kilitle | ✅ | ✅ | ❌ | ❌ |
| Mesai talep et | ❌ | ❌ | ❌ | ✅ |
| Mesai onayla | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| PDKS import | ✅ | ✅ | ❌ | ❌ |
| Giriş-çıkış düzelt | ✅ | ✅ | ⚠️ (talep ile) | ❌ |
| Raporlar | ✅ | ✅ | ✅ (kendi dept.) | ❌ |

### 9.3 Audit Trail

| Olay | Loglanan Veri |
|------|---------------|
| Manuel puantaj düzeltme | Eski/yeni değer, düzelten kullanıcı, zaman, gerekçe |
| Mesai onay/red | Karar veren, zaman, nedenler |
| Puantaj kilitleme | Kilitleyen kullanıcı, dönem |
| PDKS import | Import zamanı, kayıt sayısı, eşleşme oranı |
| Vardiya plan yayınlama | Yayınlayan, etkilenen çalışan sayısı |

---

## 10. Bağımlılıklar

| Modül | Kullanım |
|-------|----------|
| 10 – Personel | Çalışan bilgileri, departman, pozisyon |
| 12 – İzin | Vardiya-izin çakışması, devam kontrolü |
| 14 – Bordro | Fazla mesai ve puantaj verileri aktarımı |
| 09 – Entegrasyon | PDKS cihaz, dış zaman sistemleri |

---

## 11. Modüller Arası Servis Arayüzü

```python
class ShiftService:
    """Vardiya & Mesai modülü servis arayüzü."""
    
    def get_timesheet_summary(
        self, employee_id: UUID, period_start: date, period_end: date
    ) -> list[TimesheetSummaryDTO]:
        """Bordro modülü tarafından çağrılır; dönem puantaj özeti."""
        ...
    
    def get_approved_overtime(
        self, employee_id: UUID, period_start: date, period_end: date
    ) -> list[OvertimeDTO]:
        """Bordro modülü tarafından çağrılır; onaylı mesai kayıtları."""
        ...
    
    def check_shift_conflict(
        self, employee_id: UUID, start_date: date, end_date: date
    ) -> list[ConflictDTO]:
        """İzin modülü tarafından çağrılır; izin-vardiya çakışma kontrolü."""
        ...
    
    def get_attendance_for_date(
        self, employee_id: UUID, target_date: date
    ) -> AttendanceSummaryDTO | None:
        """Devamsızlık modülü tarafından çağrılır; gün bazında giriş-çıkış."""
        ...
    
    def import_pdks_records(
        self, device_id: str, records: list[PDKSRecordDTO]
    ) -> ImportResultDTO:
        """Entegrasyon modülü tarafından çağrılır; PDKS toplu import."""
        ...
```

---

## 12. Performans Gereksinimleri

| Metrik | Hedef |
|--------|-------|
| Puantaj hesaplama (günlük batch, 1000 çalışan) | < 120 saniye |
| PDKS kayıt import (1000 kayıt) | < 10 saniye |
| Vardiya takvimi yükleme | < 500 ms (p95) |
| Toplu vardiya atama (100 satır) | < 3 saniye |
| Puantaj listesi sorgulama | < 300 ms (p95) |

---

## 13. Test Senaryoları

### 13.1 Birim Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| UT-01 | Çakışan vardiya ataması | `ShiftConflictError`; ikinci atama reddedilir |
| UT-02 | Puantaj hesaplama — zamanında giriş-çıkış | Geç=0, erken=0, mesai=0 |
| UT-03 | Puantaj hesaplama — 30 dk geç gelme (10 dk tolerans) | Geç=20 dk |
| UT-04 | Fazla mesai hesaplama — 30 dk fazla çalışma | overtime_minutes=30, type=normal |
| UT-05 | Gece vardiyası fark hesaplama | %10 premium doğru uygulanır |
| UT-06 | İzinli güne vardiya atama | Uyarı döner ama kayıt oluşturulabilir |
| UT-07 | Tolerans sınırında giriş | Tam tolerans dakikasında → geç=0 |
| UT-08 | Eksik giriş-çıkış tespiti | Sadece clock_in var → "eksik kayıt" |
| UT-09 | İki vardiya arası 11 saat kuralı | < 11 saat arayla atama → uyarı |

### 13.2 Entegrasyon Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| IT-01 | PDKS CSV import → attendance_logs | Kayıtlar doğru çalışanla eşleşir |
| IT-02 | Puantaj onayı → bordro export | Onaylı mesai verileri PayrollService'e aktarılır |
| IT-03 | İzin oluşturma → vardiya çakışma kontrolü | İzin modülünden ShiftService.check_shift_conflict çağrılır |
| IT-04 | Plan yayınlama → bildirim gönderimi | Atanan tüm çalışanlara bildirim iletilir |
| IT-05 | Puantaj kilitleme → düzenleme engeli | Kilitli kayıtta güncelleme 403 döner |

### 13.3 Uçtan Uca (E2E) Testler

| # | Senaryo | Adımlar |
|---|---------|---------|
| E2E-01 | Tam vardiya döngüsü | Şablon oluştur → Plan yap → Ata → PDKS import → Puantaj hesapla → Onayla → Bordroya aktar |
| E2E-02 | Mesai onay akışı | Çalışan fazla çalışır → Sistem mesai kaydı oluşturur → Yönetici onaylar → Bordro export |
| E2E-03 | PDKS kesintisi senaryosu | Cihaz bağlantı kesilir → Alert üretilir → Manuel kayıt girilir → Puantaj düzeltilir |

---

## 14. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | Cihaz entegrasyon formatları tenant bazında değişebilir; adaptör katmanı gerekir |
| K2 | Biyometrik veri (parmak izi, yüz) cihaz tarafında saklanır; sisteme sadece zaman damgası gelir |
| K3 | GPS doğrulaması yalnızca mobil check-in'de kullanılır; doğruluk yarıçapı tenant ayarı |
| V1 | Günlük çalışma saati ve mola kuralları tenant ayarından belirlenir |
| V2 | Resmi tatil takvimi 09-entegrasyon-haritasi aracılığıyla yıllık güncellenir |
| V3 | PDKS cihazları REST API veya dosya export destekler (minimum bir yöntem) |
