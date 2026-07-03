# 15 — Modül: Eğitim & Gelişim Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Eğitim kataloğu, zorunlu eğitimler, eğitim planları, katılım takibi, sertifika yönetimi, gelişim planları, kariyer yol haritası bağlantıları  
> **Faz:** Faz 2 — Performans ve Organizasyon modüllerini destekleyen gelişim katmanı  
> **Referans:** 04-gereksinim-analizi.md, 10-modul-personel-yonetimi.md, 13-modul-performans-yonetimi.md, 17-modul-organizasyon-semasi.md

---

## 1. Modül Özeti

Eğitim & Gelişim modülü; çalışanların zorunlu ve isteğe bağlı eğitimlerini planlamayı, eğitim katılımını izlemeyi, sertifikaları saklamayı ve performans çıktılarıyla ilişkili gelişim planlarını yönetmeyi sağlar. Modül bir LMS yerine kurumsal eğitim orkestrasyonu katmanı olarak tasarlanır.

### 1.1 Kapsam

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| Eğitim kataloğu | Video hosting / tam LMS oynatıcı |
| Sınıf içi ve online eğitim kaydı | SCORM motoru ilk sürümde |
| Sertifika geçerlilik takibi | Üçüncü parti içerik üretimi |
| Gelişim planı aksiyonları | Ücret/terfi kararı otomasyonu |
| Kariyer patikası ile eğitim eşleştirme | — |

### 1.2 Temel Akış

```
Eğitim ihtiyacı oluştu
    ▼
Katalogdan eğitim seçildi veya yeni eğitim açıldı
    ▼
Katılımcılar atandı
    ▼
Katılım / tamamlama izlendi
    ▼
Sertifika ve gelişim çıktısı kaydedildi
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|----------------|-------------------|-----------------|
| **Ayşe (İK Gelişim Uzmanı)** | Eğitim yöneticisi | Günlük | Katalog yönetimi, toplu atama, uyum raporu takibi, sertifika kontrolü |
| **Mehmet (Dept. Yöneticisi)** | Gelişim planı sahibi | Haftalık | Ekibine eğitim önerme/atama, ilerleme izleme, performans bağlantılı gelişim |
| **Zeynep (Çalışan)** | Katılımcı | Aylık 2-4 kez | Atanan eğitimleri görme, tamamlama, sertifika erişimi, gelişim planı takibi |
| **Hakan (Genel Müdür)** | Dashboard tüketici | Çeyreklik | Uyum eğitim oranları, gelişim yatırım özeti |

### 2.2 İK Gelişim Uzmanı — Eğitim Planlama Yolculuğu

```
İHTİYAÇ TESPİTİ           PLANLAMA                 TAKİP
   │                         │                        │
   ▼                         ▼                        ▼
Performans sonuçları     Kataloğa eğitim ekle     Katılım oranını
ve uyum gereksinimleri   veya mevcut seç           izle
incelendi                    │                        │
   │                    ├─ Hedef kitle belirle     ├─ Tamamlamayanları
   ├─ Yetkinlik açıkları├─ Tarih / format ayarla   │  hatırlat
   ├─ Zorunlu mevzuat   ├─ Ön koşul tanımla       ├─ Sertifika yenileme
   │  eğitimleri        └─ Toplu ata                │  takibi
   └─ Onboarding                                   └─ Rapor çek
      eğitimleri
```

### 2.3 Çalışan — Eğitim Tamamlama Yolculuğu

```
BİLDİRİM               KATILIM                  TAMAMLAMA
   │                       │                        │
   ▼                       ▼                        ▼
"Yeni eğitiminiz       Eğitim detayını          Eğitimi tamamla:
atandı" bildirimi      incele:                  ├─ Sınıf: katılım
   │                    ├─ Format (online/sınıf)│    onayı (İK)
   ▼                    ├─ Süre, ön koşul       ├─ Online: link
Self-servis →           ├─ Son tarih             │    üzerinden
Eğitimlerim →           └─ Başla / kayıt ol     └─ Sertifika yükle
Detay kartı                                          veya otomatik
                                                     oluştur
```

### 2.4 Yönetici — Ekip Gelişim Yolculuğu

```
PERFORMANS SONUCU       GELİŞİM PLANI            TAKİP
   │                       │                        │
   ▼                       ▼                        ▼
Çalışanın yetkinlik     Gelişim aksiyonu         İlerlemeyi izle:
açığını gör              oluştur:                 ├─ Tamamlanan eğitimler
   │                    ├─ Eğitim öner           ├─ Sertifika durumu
   ▼                    ├─ Mentorluk ata         └─ 1:1'de değerlendir
Önerilen eğitimleri     ├─ Proje deneyimi
incele ve ata           └─ Son tarih belirle
```

---

## 3. Fonksiyonel Gereksinimler

### 3.1 Eğitim Kataloğu Yönetimi

#### FR-EDU-01: Eğitim Tanımlama

**Açıklama:** Eğitim kataloğunda eğitim türü, süre, format, hedef kitle ve ön koşullar tanımlanabilmeli.

**Eğitim Formatları:**

| Format | Açıklama | Tamamlama |
|--------|----------|-----------|
| `classroom` | Sınıf içi / fiziksel | Katılım onayı (İK / eğitmen) |
| `online_live` | Canlı online (webinar) | Katılım onayı |
| `online_self` | Kendi hızında online | Link üzerinden, tamamlama takibi |
| `external` | Harici kurum eğitimi | Manuel sertifika yükleme |
| `blended` | Karma (online + sınıf) | Her bileşen ayrı takip |
| `on_the_job` | İş başı eğitim | Yönetici onayı |

**Eğitim Konfigürasyonu:**

| Özellik | Açıklama |
|---------|----------|
| Kategori | Teknik, yönetsel, uyum, kişisel gelişim, onboarding |
| Süre | Saat/gün cinsinden |
| Ön koşul | Başka bir eğitimin tamamlanmış olması |
| Hedef kitle | Rol, kademe, departman, lokasyon bazında |
| Zorunluluk | Zorunlu / isteğe bağlı / önerilen |
| Tekrar sıklığı | Tek seferlik, yıllık, 2 yılda bir |
| Kapasite | Sınıf içi eğitimler için max kişi |
| Harici link | Online eğitimler için URL |
| Sertifika şablonu | Otomatik sertifika üretimi aktif mi |

#### FR-EDU-02: Zorunlu Eğitim Ataması

**Otomatik Atama Kuralları:**

| Tetikleyici | Aksiyon |
|-------------|---------|
| Yeni çalışan (onboarding) | Rol bazlı zorunlu eğitim paketi atanır |
| Rol değişikliği / terfi | Yeni rolün zorunlu eğitimleri atanır |
| Sertifika süresi dolumu | Yenileme eğitimi otomatik atanır |
| Mevzuat güncellemesi | İK toplu atama yapar |

#### FR-EDU-03: Katılım Takibi

**Durum Makinesi:**

```
assigned ──▶ in_progress ──▶ completed
    │             │              │
    │             └── failed     └── (sertifika oluşur)
    │
    └── expired (son tarih geçti)
```

#### FR-EDU-04: Sertifika Yönetimi

| Alan | Açıklama |
|------|----------|
| Sertifika adı | Eğitim adından otomatik veya özel |
| Düzenleme tarihi | Tamamlama tarihi |
| Geçerlilik süresi | Son tarih (nullable — süresiz) |
| Belge dosyası | MinIO'da saklanan PDF/resim |
| Kaynak | Sistem üretimi / harici yükleme |

#### FR-EDU-05: Performans Bağlantılı Gelişim Önerisi

```
Performans modülü → yetkinlik açığı → eğitim önerisi

Eşleştirme: competency_item.code ↔ learning_course.target_competencies (JSONB)
```

#### FR-EDU-06: Kariyer Patikası Eğitim Paketi

| Alan | Açıklama |
|------|----------|
| Mevcut pozisyon | Çalışanın güncel rolü |
| Hedef pozisyon | Kariyer yolundaki bir üst rol |
| Gerekli eğitimler | Hedef pozisyon için tanımlı eğitim listesi |
| Tamamlanan | Zaten bitirdiği eğitimler |
| Eksik | Henüz tamamlanmamış eğitimler |

### 3.2 Gelişim Planı Yönetimi

#### FR-EDU-07: Gelişim Planı Oluşturma

**Gelişim Aksiyonu Tipleri:**

| Tip | Açıklama |
|-----|----------|
| Eğitim | Katalogdan veya harici eğitim |
| Mentorluk | Mentor atama ve görüşme takibi |
| Proje deneyimi | İş başı öğrenme / stretch assignment |
| Okuma / araştırma | Kendi kendine çalışma |
| Sertifikasyon | Dış sertifikasyon programı |

### 3.3 İş Kuralları

| Kural | Açıklama |
|-------|----------|
| IK-EDU-01 | Aynı çalışan için aynı aktif eğitim ataması mükerrer açılamaz |
| IK-EDU-02 | Süresi dolan zorunlu sertifika dashboard'da risk olarak görünür |
| IK-EDU-03 | Zorunlu eğitim tamamlanmadan belirli süreçler için uyarı üretilebilir (ör. performans değerlendirme) |
| IK-EDU-04 | Harici eğitim kayıtları manuel sertifika yüklemesiyle işlenebilir |
| IK-EDU-05 | Ön koşul eğitimi tamamlanmadan bağımlı eğitim atanabilir ancak başlatılamaz |
| IK-EDU-06 | Sınıf içi eğitim kapasitesi dolduğunda bekleme listesi oluşturulur |
| IK-EDU-07 | Eğitim iptal edildiğinde tüm atanmış katılımcılara bildirim gider |
| IK-EDU-08 | Gelişim planı aksiyonları performans dönemine bağlanabilir; dönem kapanışında ilerleme raporu oluşur |

---

## 4. Veritabanı Tasarımı

### 4.1 Tablo İlişkisi

```
learning_courses ──────── learning_sessions
        │                       │
        └── learning_assignments ┘
                │
                └── learning_certificates

learning_development_plans ──── learning_development_actions
        │
        └── performance_reviews (bağlantılı dönem)

learning_course_prerequisites (ön koşul ilişkisi)
learning_career_paths ──── learning_career_path_courses
```

### 4.2 Tablo Detayları

#### `learning_courses` — Eğitim Kataloğu

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `code` | VARCHAR(50) | Eğitim kodu (tenant içinde benzersiz) |
| `title` | VARCHAR(200) | Eğitim başlığı |
| `description` | TEXT, nullable | Detaylı açıklama |
| `category` | VARCHAR(30) | `technical`, `managerial`, `compliance`, `personal_dev`, `onboarding` |
| `format` | VARCHAR(20) | `classroom`, `online_live`, `online_self`, `external`, `blended`, `on_the_job` |
| `duration_hours` | NUMERIC(5,1) | Toplam süre (saat) |
| `capacity` | SMALLINT, nullable | Sınıf içi max kişi |
| `is_mandatory` | BOOLEAN, default: false | Zorunlu mu |
| `recurrence` | VARCHAR(20), nullable | `once`, `yearly`, `biennial` |
| `target_roles` | JSONB, nullable | Hedef rol kodları |
| `target_departments` | JSONB, nullable | Hedef departman ID'leri |
| `target_competencies` | JSONB, nullable | İlişkili yetkinlik kodları |
| `external_url` | TEXT, nullable | Online eğitim linki |
| `certificate_template` | VARCHAR(50), nullable | Otomatik sertifika şablonu |
| `is_active` | BOOLEAN, default: true | |
| `created_by` | BIGINT, FK | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `learning_assignments` — Eğitim Atamaları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `course_id` | BIGINT, FK | |
| `session_id` | BIGINT, FK, nullable | Sınıf içi oturum |
| `employee_id` | BIGINT, FK | |
| `assigned_by` | BIGINT, FK | Atayanyan (İK / yönetici / sistem) |
| `assignment_reason` | VARCHAR(30) | `onboarding`, `mandatory`, `development`, `manager_request`, `self_request` |
| `status` | VARCHAR(20) | `assigned`, `in_progress`, `completed`, `failed`, `expired`, `cancelled` |
| `due_date` | DATE, nullable | Son tamamlama tarihi |
| `started_at` | TIMESTAMPTZ, nullable | |
| `completed_at` | TIMESTAMPTZ, nullable | |
| `score` | NUMERIC(5,2), nullable | Sınav/değerlendirme puanı |
| `development_plan_id` | BIGINT, FK, nullable | Bağlı gelişim planı |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `learning_sessions` — Eğitim Oturumları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `course_id` | BIGINT, FK | |
| `title` | VARCHAR(200) | Oturum başlığı |
| `session_date` | DATE | |
| `start_time` | TIME | |
| `end_time` | TIME | |
| `location` | VARCHAR(200), nullable | Fiziksel veya online link |
| `instructor` | VARCHAR(100), nullable | Eğitmen adı |
| `capacity` | SMALLINT | |
| `enrolled_count` | SMALLINT, default: 0 | |
| `status` | VARCHAR(20) | `planned`, `open`, `full`, `completed`, `cancelled` |
| `created_at` | TIMESTAMPTZ | |

#### `learning_certificates` — Sertifika Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `course_id` | BIGINT, FK, nullable | Sistem eğitimi ise |
| `assignment_id` | BIGINT, FK, nullable | |
| `certificate_name` | VARCHAR(200) | |
| `issuer` | VARCHAR(200), nullable | Veren kurum |
| `issue_date` | DATE | |
| `expiry_date` | DATE, nullable | Son geçerlilik (null = süresiz) |
| `file_url` | TEXT, nullable | MinIO signed URL |
| `source` | VARCHAR(20) | `system_generated`, `external_upload` |
| `is_active` | BOOLEAN, default: true | |
| `created_at` | TIMESTAMPTZ | |

#### `learning_development_plans` — Gelişim Planları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `cycle_id` | BIGINT, FK, nullable | Bağlı performans dönemi |
| `title` | VARCHAR(200) | |
| `status` | VARCHAR(20) | `draft`, `active`, `completed`, `cancelled` |
| `created_by` | BIGINT, FK | Yönetici veya İK |
| `start_date` | DATE | |
| `target_date` | DATE | |
| `completion_note` | TEXT, nullable | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `learning_development_actions` — Gelişim Aksiyonları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `plan_id` | BIGINT, FK | |
| `action_type` | VARCHAR(20) | `training`, `mentoring`, `project`, `reading`, `certification` |
| `title` | VARCHAR(200) | |
| `description` | TEXT, nullable | |
| `assignment_id` | BIGINT, FK, nullable | Eğitim tipinde bağlı atama |
| `status` | VARCHAR(20) | `not_started`, `in_progress`, `completed`, `cancelled` |
| `due_date` | DATE, nullable | |
| `completed_at` | TIMESTAMPTZ, nullable | |

### 4.3 İndeksler

```sql
CREATE INDEX ix_learning_assignments_employee_status ON learning_assignments (tenant_id, employee_id, status);
CREATE INDEX ix_learning_assignments_course ON learning_assignments (tenant_id, course_id, status);
CREATE INDEX ix_learning_certificates_expiry ON learning_certificates (tenant_id, expiry_date) WHERE is_active = true;
CREATE INDEX ix_learning_certificates_employee ON learning_certificates (tenant_id, employee_id);
CREATE INDEX ix_learning_dev_plans_employee ON learning_development_plans (tenant_id, employee_id, status);
CREATE UNIQUE INDEX uq_learning_assignments_active ON learning_assignments (tenant_id, course_id, employee_id) WHERE status IN ('assigned', 'in_progress');
```

---

## 5. API Endpoint Detayları

Tüm eğitim endpoint'leri `/api/v1/learning` prefix'i altındadır.

### 5.1 Eğitim Kataloğu

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/learning/courses` | Eğitim kataloğu listesi | `learning:read` |
| `POST` | `/learning/courses` | Eğitim oluştur | `learning:create` |
| `PATCH` | `/learning/courses/{id}` | Eğitim güncelle | `learning:update` |
| `GET` | `/learning/courses/{id}` | Eğitim detayı | `learning:read` |

### 5.2 Oturum Yönetimi

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/learning/courses/{id}/sessions` | Oturum oluştur | `learning:create` |
| `GET` | `/learning/sessions` | Oturum listesi | `learning:read` |
| `PATCH` | `/learning/sessions/{id}` | Oturum güncelle | `learning:update` |

### 5.3 Atamalar

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/learning/assignments` | Eğitim ata (tekil/toplu) | `learning:assign` |
| `GET` | `/learning/assignments` | Atama listesi (filtreli) | `learning:read` |
| `PATCH` | `/learning/assignments/{id}` | Durum güncelle | `learning:update` |
| `POST` | `/learning/assignments/{id}/complete` | Tamamlama onayla | `learning:update` |

### 5.4 Sertifikalar

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/learning/certificates` | Sertifika listesi | `learning:read` |
| `POST` | `/learning/certificates` | Harici sertifika yükle | `learning:create` |
| `GET` | `/learning/certificates/expiring` | Süresi dolacak sertifikalar | `learning:read` |

### 5.5 Gelişim Planları

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/learning/development-plans` | Plan listesi | `learning:read` |
| `POST` | `/learning/development-plans` | Plan oluştur | `learning:create` |
| `POST` | `/learning/development-plans/{id}/actions` | Aksiyon ekle | `learning:update` |
| `PATCH` | `/learning/development-plans/{id}/actions/{aid}` | Aksiyon güncelle | `learning:update` |

### 5.6 Self-Servis Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/learning` | Kendi eğitim listesi | Auth |
| `GET` | `/me/learning/assignments` | Atanmış eğitimlerim | Auth |
| `GET` | `/me/learning/certificates` | Sertifikalarım | Auth |
| `POST` | `/me/learning/certificates` | Harici sertifika yükle | Auth |
| `GET` | `/me/learning/development-plan` | Gelişim planım | Auth |
| `GET` | `/me/learning/career-path` | Kariyer yolu ve eğitim önerileri | Auth |

### 5.7 Örnek Request / Response

#### POST `/api/v1/learning/assignments`

**Request Body:**

```json
{
  "course_id": 15,
  "employee_ids": [451, 452, 460],
  "assignment_reason": "mandatory",
  "due_date": "2026-06-30",
  "development_plan_id": null
}
```

**Response (201 Created):**

```json
{
  "success": true,
  "data": {
    "created_count": 3,
    "skipped_count": 0,
    "assignments": [
      { "id": 301, "employee_id": 451, "status": "assigned", "due_date": "2026-06-30" },
      { "id": 302, "employee_id": 452, "status": "assigned", "due_date": "2026-06-30" },
      { "id": 303, "employee_id": 460, "status": "assigned", "due_date": "2026-06-30" }
    ]
  }
}
```

**Olası Hata Kodları:**

| HTTP | Kod | Açıklama |
|------|-----|----------|
| 400 | `VALIDATION_ERROR` | Eksik alan veya geçersiz parametre |
| 409 | `DUPLICATE_ASSIGNMENT` | Çalışanın zaten aktif ataması var |
| 409 | `SESSION_FULL` | Oturum kapasitesi dolu |
| 422 | `PREREQUISITE_NOT_MET` | Ön koşul eğitimi tamamlanmamış |
| 404 | `COURSE_NOT_FOUND` | Eğitim bulunamadı |

---

## 6. Ekranlar ve Raporlar

### 6.1 Ekran Listesi

| # | Ekran | Platform | Rol | Öncelik |
|---|-------|----------|-----|---------|
| 1 | Eğitim kataloğu | Web + Mobil | Tüm roller | Must |
| 2 | Eğitim detay kartı | Web + Mobil | Tüm roller | Must |
| 3 | Eğitim atama paneli | Web | İK | Must |
| 4 | Eğitimlerim / atamalarım | Web + Mobil | Çalışan | Must |
| 5 | Sertifika takip ekranı | Web | İK, Çalışan | Must |
| 6 | Gelişim planı ekranı | Web + Mobil | Çalışan, Yönetici | Must |
| 7 | Kariyer patikası ve öneriler | Web | Çalışan | Should |
| 8 | Uyum eğitim raporu | Web | İK, C-Level | Must |
| 9 | Eğitim tamamlama analitiği | Web | İK | Should |

### 6.2 Ana Raporlar

| # | Rapor | Açıklama | Filtreler | Format |
|---|-------|----------|-----------|--------|
| 1 | Zorunlu eğitim tamamlama oranı | Uyum eğitimlerinde kalan açık | Departman, rol, eğitim | Grafik + tablo |
| 2 | Sertifika yenileme raporu | Süresi dolan/dolacak sertifikalar | Tarih aralığı, eğitim | Risk listesi |
| 3 | Eğitim katılım raporu | Oturum ve kişi bazında katılım | Dönem, format | Tablo |
| 4 | Gelişim planı ilerleme raporu | Plan bazında tamamlanma oranı | Departman, yönetici | Tablo + grafik |
| 5 | Eğitim yatırım özeti | Verilen eğitim saat/kişi ve maliyet | Dönem, departman | Dashboard kartı |

### 6.3 Dashboard Kartları

| Kart | Formül |
|------|--------|
| Zorunlu eğitim uyum oranı | `completed mandatory / total mandatory × 100` |
| Yaklaşan sertifika yenilemeleri | `COUNT(*) WHERE expiry_date BETWEEN now AND now + 30 gün` |
| Ortalama eğitim saati / çalışan | `SUM(duration_hours × completed) / active_employee_count` |
| Geciken eğitim atamaları | `COUNT(*) WHERE status = 'assigned' AND due_date < now` |

---

## 7. İş Akışları ve Otomasyon

### 7.1 Celery Beat Görevleri

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `check_certificate_expiry` | Günlük 08:00 | 30, 14, 7 gün kalan sertifikalar için hatırlatma |
| `expire_overdue_assignments` | Günlük 01:00 | Son tarihi geçen atamaları `expired` yap |
| `auto_assign_onboarding` | Çalışan oluşturulduğunda | Rol bazlı zorunlu eğitim paketi ata |
| `auto_assign_role_change` | Rol değişikliğinde | Yeni rolün zorunlu eğitimlerini ata |
| `send_assignment_reminders` | Haftalık pazartesi 09:00 | Tamamlanmamış atamaları hatırlat |
| `refresh_learning_dashboards` | Günlük 03:00 | Uyum ve tamamlama metriklerini yenile |

### 7.2 Bildirim Şablonları

| Şablon | Tetikleyici | Alıcı | İçerik |
|--------|-------------|-------|--------|
| `learning_assigned` | Eğitim atandı | Çalışan | "Yeni eğitiminiz atandı: [eğitim adı]. Son tarih: [tarih]." |
| `learning_due_reminder` | Son tarih yaklaşıyor | Çalışan | "[eğitim adı] eğitiminizin son tarihi [tarih]. Lütfen tamamlayın." |
| `learning_completed` | Eğitim tamamlandı | Çalışan, Yönetici | "[çalışan] [eğitim adı] eğitimini tamamladı." |
| `certificate_expiring` | Sertifika 30 gün kala | Çalışan, İK | "[sertifika adı] sertifikanızın geçerlilik süresi [tarih] tarihinde dolacak." |
| `certificate_expired` | Sertifika süresi doldu | İK, Yönetici | "[çalışan]'ın [sertifika] sertifikası süresi doldu. Risk kaydı oluşturuldu." |
| `session_reminder` | Oturum 1 gün kala | Katılımcılar | "[eğitim adı] sınıf içi oturumu yarın [saat]'de [lokasyon]'da." |
| `assignment_expired` | Atama süresi doldu | Çalışan, Yönetici | "[eğitim adı] eğitiminizin süresi doldu." |

---

## 8. Güvenlik ve KVKK

### 8.1 Hassas Veri Sınıflandırması

| Veri | Hassasiyet | Erişim Kontrolü |
|------|-----------|-----------------|
| Eğitim geçmişi | Orta | Çalışan kendisi, yönetici ekibi, İK tümü |
| Sertifika belgeleri | Orta | MinIO signed URL + rol kontrolü |
| Gelişim planı notları | Orta-Yüksek | Çalışan, yönetici, İK |
| Performans bağlantılı gelişim | Yüksek | Yetkili kişiler |

### 8.2 Rol Bazlı Erişim Matrisi

| İzin | Süper Admin | İK Yöneticisi | Dept. Yöneticisi | Çalışan |
|------|------------|--------------|------------------|---------|
| `learning:create` | ✅ | ✅ | ❌ | ❌ |
| `learning:assign` | ✅ | ✅ | ✅ (ekibi) | ❌ |
| `learning:update` | ✅ | ✅ | ✅ (ekibi) | ❌ |
| `learning:read` | ✅ | ✅ | Ekibi | Kendi |
| Kendi eğitimleri | — | — | — | ✅ |
| Harici sertifika yükleme | — | — | — | ✅ |

---

## 9. Modüller Arası Bağımlılıklar

### 9.1 Eğitim Modülünün Sunduğu Servisler

```python
class LearningService:
    """Diğer modüllerin kullandığı eğitim servisleri."""

    async def get_employee_training_summary(self, employee_id: int) -> dict
    """Tamamlanan/devam eden eğitim sayısı ve saat toplamı."""

    async def get_mandatory_compliance_status(self, employee_id: int) -> list[dict]
    """Zorunlu eğitim uyum durumu (risk dashboard için)."""

    async def create_development_action(self, plan_id: int, action: dict) -> int
    """Performans modülünden gelişim aksiyonu oluşturma."""

    async def get_expiring_certificates(self, days_ahead: int = 30) -> list[dict]
    """Yaklaşan sertifika yenilemeleri."""
```

### 9.2 Kullandığı Servisler

| Modül | Servis | Kullanım |
|-------|--------|----------|
| **Personnel** | `PersonnelService.get_employee()` | Çalışan bilgisi, rol, departman |
| **Organization** | `OrganizationService.get_role_family()` | Rol bazlı eğitim eşleştirme |
| **Performance** | `PerformanceService.get_competency_gap_summary()` | Yetkinlik açığından eğitim önerisi |
| **Notification** | `NotificationService.send()` | Tüm bildirimler |
| **Self-Service** | Portal katmanı | Çalışan deneyimi |

---

## 10. Performans Gereksinimleri

| Senaryo | Hedef | Yöntem |
|---------|-------|--------|
| Eğitim kataloğu listeleme | < 150ms | Sayfalama + indeks |
| Toplu atama (500 kişi) | < 10 saniye | Bulk insert |
| Sertifika yenileme taraması | < 5 saniye | İndeksli tarih sorgusu |
| Gelişim planı dashboard | < 200ms | Pre-aggregation |
| Uyum raporu (tüm şirket) | < 3 saniye | Summary tablo + cache |

---

## 11. Test Senaryoları

### 11.1 Birim Test

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Mükerrer aktif atama | Engellenir (409) |
| 2 | Ön koşul kontrolü | Ön koşul eksik ise başlatılamaz |
| 3 | Sertifika geçerlilik hesabı | Son tarih doğru belirlenir |
| 4 | Kapasite kontrolü | Dolu oturum ataması engellenir |
| 5 | Onboarding otomatik atama | Yeni çalışana zorunlu eğitimler atanır |

### 11.2 Entegrasyon Test

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Performans → gelişim önerisi | Yetkinlik açığına göre eğitim önerisi gelir |
| 2 | Eğitim tamamlama → sertifika | Otomatik sertifika oluşur |
| 3 | Sertifika süre dolumu → bildirim | Hatırlatma gönderilir |
| 4 | Rol değişikliği → otomatik atama | Yeni rolün eğitimleri atanır |

### 11.3 E2E Test

| # | Test | Adımlar |
|---|------|---------|
| 1 | Tam eğitim çevrimi | Katalog → atama → katılım → tamamlama → sertifika |
| 2 | Gelişim planı akışı | Performans sonucu → plan oluştur → aksiyon ekle → eğitim ata → tamamla |
| 3 | Uyum senaryosu | Zorunlu eğitim ata → sertifika süresi dol → yenileme |

---

## 12. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | İlk sürümde tam LMS özellikleri bulunmaz; içerik link veya harici sağlayıcı ile açılır |
| K2 | SCORM entegrasyonu ilk sürümde kapsam dışı; sonraki fazda değerlendirilir |
| K3 | Eğitim maliyet takibi (bütçe) ilk sürümde basit düzeyde; detaylı bütçeleme kapsam dışı |
| V1 | Eğitim sonuçları performans kararına girdi sağlar ancak tek başına belirleyici değildir |
| V2 | Harici eğitim platformlarıyla API entegrasyonu gelecek fazda değerlendirilir |
