# 07 — Veritabanı Tasarımı

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** Veritabanı konvansiyonları, multi-tenant yapısı, çekirdek tablolar, MVP modül tabloları, indeksleme stratejisi, migration yaklaşımı  
> **Referans:** 04-gereksinim-analizi.md, 05-teknoloji-secimi.md, 06-sistem-mimarisi.md

---

## 1. Amaç

Bu doküman, veritabanının genel kurallarını, çekirdek tablolarını ve MVP kapsamındaki modül tablolarını tanımlar.

**Kapsam sınırı:** Bordro, performans, eğitim, vardiya, işe alım gibi modüllerin detaylı tablo tasarımları Faz 3'teki ilgili modül dokümanlarında yapılacaktır. Bu doküman, tüm modüllerin uyacağı kuralları ve ortak altyapıyı belirler.

---

## 2. Veritabanı Konvansiyonları

### 2.1 Adlandırma Kuralları

| Kural | Format | Örnek |
|-------|--------|-------|
| Tablo adı | `{modül}_{çoğul_isim}` snake_case | `personnel_employees`, `leave_requests` |
| Kolon adı | snake_case | `first_name`, `created_at`, `is_active` |
| Primary key | `id` (BigInteger, autoincrement) | `id` |
| Foreign key | `{ilişkili_tablo_tekil}_id` | `employee_id`, `department_id` |
| Tenant referansı | `tenant_id` | Her tenant-scoped tabloda zorunlu |
| Boolean kolon | `is_` veya `has_` öneki | `is_active`, `has_mfa_enabled` |
| Tarih kolonu | `_at` veya `_date` soneki | `created_at`, `start_date` |
| Enum kolon | Kısa açıklayıcı isim | `status`, `type`, `gender` |
| Index adı | `ix_{tablo}_{kolon(lar)}` | `ix_personnel_employees_tenant_id` |
| Unique constraint | `uq_{tablo}_{kolon(lar)}` | `uq_auth_users_email_tenant_id` |

### 2.2 Ortak Kolonlar

Her tenant-scoped tablo aşağıdaki kolonları içerir:

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BigInteger, PK | Otomatik artan benzersiz tanımlayıcı |
| `tenant_id` | BigInteger, FK, NOT NULL | Verinin ait olduğu firma |
| `created_at` | TIMESTAMPTZ, NOT NULL | Kayıt oluşturulma zamanı (DB default: `now()`) |
| `updated_at` | TIMESTAMPTZ, NOT NULL | Son güncelleme zamanı (DB default: `now()`, auto-update) |
| `created_by` | BigInteger, FK, nullable | Kaydı oluşturan kullanıcı |
| `updated_by` | BigInteger, FK, nullable | Kaydı güncelleyen kullanıcı |

### 2.3 Soft Delete Politikası

Personel verileri yasal saklama yükümlülüğü taşıdığından, silme işlemi fiziksel olarak yapılmaz:

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `is_deleted` | Boolean, default: false | Soft delete bayrağı |
| `deleted_at` | TIMESTAMPTZ, nullable | Silinme zamanı |
| `deleted_by` | BigInteger, FK, nullable | Silme işlemini yapan kullanıcı |

- Tüm sorgularda `WHERE is_deleted = false` filtresi varsayılan olarak uygulanır (SQLAlchemy global filter).
- KVKK kapsamında belirli süreler sonunda kalıcı silme işlemi ayrı bir süreçle yönetilir.
- Fiziksel silme yalnızca KVKK veri silme talebi veya yasal saklama süresi dolduğunda gerçekleşir.

### 2.4 Veri Tipleri Tercihleri

| İhtiyaç | PostgreSQL Tipi | Gerekçe |
|---------|----------------|---------|
| ID'ler | `BIGINT` | Uzun vadede INT taşmasını önler |
| Para/maaş | `NUMERIC(15,2)` | Float hassasiyet kaybı riskini önler |
| Tarih + saat | `TIMESTAMPTZ` | Timezone-aware, UTC saklama |
| Sadece tarih | `DATE` | İzin başlangıç/bitiş, doğum tarihi |
| Kısa metin | `VARCHAR(n)` | Ad, soyad, e-posta gibi sınırlı alanlar |
| Uzun metin | `TEXT` | Açıklama, not, adres |
| Yapılandırılmamış veri | `JSONB` | Esnek metadata, ayarlar, ek alanlar |
| Enum değerler | `VARCHAR` + uygulama katmanı enum | DB enum migration zorluğu yaratır |
| TC Kimlik No | `VARCHAR(11)` | Sabit uzunluk, şifreli saklama |
| Telefon | `VARCHAR(20)` | Uluslararası format desteği |
| E-posta | `VARCHAR(255)` | RFC 5321 |

---

## 3. Multi-Tenant Yapısı

### 3.1 Tenant Nedir?

Bu sistemde **tenant**, İK yazılımını kullanan her bir firmadır:

```
┌─────────────────────────────────────────────────┐
│            Tek PostgreSQL Veritabanı             │
│                                                  │
│   Tenant 1          Tenant 2          Tenant 3   │
│   ABC Holding       XYZ Teknoloji     DEF Loji   │
│   500 çalışan       80 çalışan        200 çalışan│
│   tenant_id = 1     tenant_id = 2     tenant_id=3│
│                                                  │
│   Her tabloda tenant_id kolonu var                │
│   Her sorgu otomatik tenant_id filtresi taşır     │
└─────────────────────────────────────────────────┘
```

### 3.2 Tenant İzolasyon Katmanları

**Katman 1 — Uygulama (birincil):**

```python
# core/middleware.py — Her istekte tenant context set edilir
class TenantMiddleware:
    async def __call__(self, request, call_next):
        # JWT'den tenant_id çıkarılır
        tenant_id = get_tenant_from_token(request)
        # Request context'e yazılır
        request.state.tenant_id = tenant_id
        return await call_next(request)

# shared/base_model.py — SQLAlchemy global filter
class TenantQuery(Query):
    def filter_by_tenant(self):
        tenant_id = get_current_tenant_id()
        return self.filter(self.column_descriptions[0]['entity'].tenant_id == tenant_id)
```

**Katman 2 — Veritabanı (kritik tablolar):**

Bordro, özlük ve audit log tablolarında ek güvence olarak PostgreSQL Row Level Security uygulanır:

```sql
-- Bordro tablosunda RLS
ALTER TABLE payroll_payslips ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON payroll_payslips
    USING (tenant_id = current_setting('app.current_tenant_id')::BIGINT);
```

### 3.3 Tenant-Scoped vs Global Tablolar

| Tip | Açıklama | Örnekler |
|-----|----------|----------|
| **Tenant-scoped** | `tenant_id` kolonu var, her firma kendi verisini görür | `personnel_employees`, `leave_requests`, `auth_users` |
| **Global** | Tüm sistemde ortaktır, tenant'a bağlı değildir | `sys_countries`, `sys_cities`, `sys_currencies`, `sys_public_holidays` |
| **Platform** | SaaS platform yönetimi | `platform_tenants`, `platform_subscriptions`, `platform_plans` |

---

## 4. Çekirdek Tablolar

Bu tablolar modüllerden bağımsızdır ve tüm sistemin temelini oluşturur.

### 4.1 Platform Tabloları (Global)

#### `platform_tenants` — Firmaları (Müşteriler)

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | Tenant ID |
| `name` | VARCHAR(255) | NOT NULL | Firma adı |
| `tax_number` | VARCHAR(11) | UNIQUE, nullable | Vergi numarası |
| `trade_name` | VARCHAR(255) | nullable | Ticaret unvanı |
| `domain` | VARCHAR(100) | UNIQUE, nullable | Alt alan adı (abc.ikplatform.com) |
| `logo_url` | VARCHAR(500) | nullable | Firma logosu |
| `address` | TEXT | nullable | Adres |
| `city` | VARCHAR(100) | nullable | Şehir |
| `phone` | VARCHAR(20) | nullable | Telefon |
| `email` | VARCHAR(255) | nullable | İletişim e-postası |
| `subscription_plan` | VARCHAR(50) | NOT NULL, default: 'trial' | Abonelik planı |
| `subscription_status` | VARCHAR(20) | NOT NULL, default: 'active' | active, suspended, cancelled |
| `employee_limit` | INTEGER | NOT NULL | Maksimum çalışan sayısı |
| `settings` | JSONB | default: '{}' | Firma bazlı ayarlar (izin politikası, çalışma saati vs.) |
| `is_active` | BOOLEAN | NOT NULL, default: true | Firma aktif mi |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### `platform_tenant_branches` — Şubeler

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK → platform_tenants | Firma |
| `name` | VARCHAR(255) | NOT NULL | Şube adı |
| `code` | VARCHAR(50) | nullable | Şube kodu |
| `city` | VARCHAR(100) | nullable | Şehir |
| `address` | TEXT | nullable | Adres |
| `is_headquarters` | BOOLEAN | default: false | Merkez şube mi |
| `is_active` | BOOLEAN | default: true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

**Index:** `ix_tenant_branches_tenant_id`

---

### 4.2 Kimlik & Yetkilendirme Tabloları

#### `auth_users` — Kullanıcılar

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK → platform_tenants | |
| `email` | VARCHAR(255) | NOT NULL | Giriş e-postası |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt hash |
| `is_active` | BOOLEAN | default: true | Hesap aktif mi |
| `is_email_verified` | BOOLEAN | default: false | E-posta doğrulandı mı |
| `has_mfa_enabled` | BOOLEAN | default: false | MFA aktif mi |
| `mfa_secret` | VARCHAR(255) | nullable | TOTP secret (şifreli) |
| `failed_login_attempts` | INTEGER | default: 0 | Başarısız giriş sayısı |
| `locked_until` | TIMESTAMPTZ | nullable | Hesap kilitleme süresi |
| `last_login_at` | TIMESTAMPTZ | nullable | Son giriş zamanı |
| `last_login_ip` | VARCHAR(45) | nullable | Son giriş IP |
| `password_changed_at` | TIMESTAMPTZ | nullable | Son şifre değişikliği |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |
| `is_deleted` | BOOLEAN | default: false | |
| `deleted_at` | TIMESTAMPTZ | nullable | |

**Unique:** `uq_auth_users_email_tenant_id (email, tenant_id)`  
**Index:** `ix_auth_users_tenant_id`, `ix_auth_users_email`

#### `auth_roles` — Roller

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK, nullable | NULL ise sistem rolü, doluysa firma özel rolü |
| `name` | VARCHAR(100) | NOT NULL | Rol adı |
| `code` | VARCHAR(50) | NOT NULL | Teknik kod: `super_admin`, `hr_manager`, `employee` |
| `description` | TEXT | nullable | Açıklama |
| `is_system` | BOOLEAN | default: false | Sistem tarafından oluşturulmuş (silinemez) |
| `is_active` | BOOLEAN | default: true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Varsayılan sistem rolleri:**

| Kod | Açıklama |
|-----|----------|
| `super_admin` | Platform yöneticisi |
| `tenant_admin` | Firma süper admini |
| `hr_manager` | İK yöneticisi |
| `dept_manager` | Departman yöneticisi |
| `employee` | Çalışan |
| `c_level` | Üst düzey yönetici |

#### `auth_permissions` — İzinler (Yetkiler)

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `module` | VARCHAR(50) | NOT NULL | Modül adı: `personnel`, `leave`, `payroll` |
| `action` | VARCHAR(50) | NOT NULL | İşlem: `create`, `read`, `update`, `delete`, `approve` |
| `resource` | VARCHAR(100) | NOT NULL | Kaynak: `employee`, `leave_request`, `payslip` |
| `description` | TEXT | nullable | |

**Unique:** `uq_auth_permissions_module_action_resource`

#### `auth_role_permissions` — Rol-İzin Eşleşmesi

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `role_id` | BIGINT | FK → auth_roles, PK | |
| `permission_id` | BIGINT | FK → auth_permissions, PK | |

#### `auth_user_roles` — Kullanıcı-Rol Eşleşmesi

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `user_id` | BIGINT | FK → auth_users, PK | |
| `role_id` | BIGINT | FK → auth_roles, PK | |
| `assigned_at` | TIMESTAMPTZ | NOT NULL | Rol atanma zamanı |
| `assigned_by` | BIGINT | FK → auth_users, nullable | Rolü atayan kullanıcı |

#### `auth_refresh_tokens` — Refresh Token'lar

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `user_id` | BIGINT | FK → auth_users | |
| `token_hash` | VARCHAR(255) | NOT NULL, UNIQUE | Token hash (plain saklanmaz) |
| `device_info` | VARCHAR(255) | nullable | Cihaz bilgisi |
| `ip_address` | VARCHAR(45) | nullable | |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `is_revoked` | BOOLEAN | default: false | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Index:** `ix_auth_refresh_tokens_user_id`, `ix_auth_refresh_tokens_token_hash`

---

### 4.3 Audit Log

#### `audit_logs` — Denetim Kaydı

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK → platform_tenants | |
| `user_id` | BIGINT | FK → auth_users, nullable | Sistem işlemleri için null olabilir |
| `action` | VARCHAR(20) | NOT NULL | `CREATE`, `UPDATE`, `DELETE`, `LOGIN`, `LOGOUT`, `APPROVE`, `REJECT` |
| `module` | VARCHAR(50) | NOT NULL | Modül adı |
| `table_name` | VARCHAR(100) | NOT NULL | Etkilenen tablo |
| `record_id` | BIGINT | nullable | Etkilenen kayıt ID |
| `old_values` | JSONB | nullable | Önceki değerler |
| `new_values` | JSONB | nullable | Yeni değerler |
| `ip_address` | VARCHAR(45) | nullable | İstek kaynağı |
| `user_agent` | VARCHAR(500) | nullable | Tarayıcı/uygulama bilgisi |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Index:** `ix_audit_logs_tenant_id_created_at`, `ix_audit_logs_user_id`, `ix_audit_logs_table_name_record_id`

**Not:** Audit log tablosu çok hızlı büyüyeceğinden, ileride `created_at` üzerinden aylık partitioning uygulanacaktır.

---

### 4.4 Bildirim Tabloları

#### `notif_templates` — Bildirim Şablonları

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK, nullable | NULL ise sistem şablonu |
| `code` | VARCHAR(100) | NOT NULL | `leave_approved`, `payslip_ready`, `birthday_reminder` |
| `channel` | VARCHAR(20) | NOT NULL | `email`, `sms`, `push`, `in_app` |
| `subject` | VARCHAR(255) | nullable | E-posta konusu (şablonlu) |
| `body_template` | TEXT | NOT NULL | İçerik şablonu (Jinja2) |
| `is_active` | BOOLEAN | default: true | |

#### `notif_logs` — Gönderilmiş Bildirimler

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `user_id` | BIGINT | FK → auth_users | Alıcı |
| `template_code` | VARCHAR(100) | NOT NULL | Şablon kodu |
| `channel` | VARCHAR(20) | NOT NULL | Gönderim kanalı |
| `title` | VARCHAR(255) | nullable | Bildirim başlığı |
| `body` | TEXT | nullable | Bildirim içeriği |
| `data` | JSONB | nullable | Ek veri (deep link, parametre) |
| `is_read` | BOOLEAN | default: false | Okundu mu |
| `read_at` | TIMESTAMPTZ | nullable | Okunma zamanı |
| `sent_at` | TIMESTAMPTZ | NOT NULL | Gönderilme zamanı |
| `status` | VARCHAR(20) | NOT NULL | `sent`, `delivered`, `failed` |
| `error_message` | TEXT | nullable | Hata varsa detay |

**Index:** `ix_notif_logs_tenant_id_user_id`, `ix_notif_logs_user_id_is_read`

---

### 4.5 Sistem Referans Tabloları (Global)

#### `sys_countries` — Ülkeler

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | SMALLINT, PK | |
| `code` | VARCHAR(3) | ISO 3166-1 alpha-3 |
| `name` | VARCHAR(100) | Ülke adı (TR) |

#### `sys_cities` — Şehirler

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | SMALLINT, PK | |
| `country_id` | SMALLINT, FK | |
| `plate_code` | VARCHAR(2) | Plaka kodu (TR) |
| `name` | VARCHAR(100) | Şehir adı |

#### `sys_districts` — İlçeler

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | INTEGER, PK | |
| `city_id` | SMALLINT, FK | |
| `name` | VARCHAR(100) | İlçe adı |

#### `sys_currencies` — Para Birimleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | SMALLINT, PK | |
| `code` | VARCHAR(3) | ISO 4217: TRY, USD, EUR |
| `name` | VARCHAR(50) | Para birimi adı |
| `symbol` | VARCHAR(5) | ₺, $, € |

#### `sys_public_holidays` — Resmi Tatiller

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | INTEGER, PK | |
| `country_code` | VARCHAR(3) | Ülke kodu |
| `date` | DATE | Tatil tarihi |
| `name` | VARCHAR(200) | Tatil adı |
| `year` | SMALLINT | Yıl |

---

## 5. MVP Modül Tabloları

MVP kapsamı: **Personel Yönetimi + İzin + Self-Servis Portal**

### 5.1 Personel Modülü

#### `personnel_employees` — Çalışanlar

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `user_id` | BIGINT | FK → auth_users, UNIQUE | Kullanıcı hesabı ilişkisi |
| `employee_number` | VARCHAR(20) | NOT NULL | Sicil numarası |
| `first_name` | VARCHAR(100) | NOT NULL | |
| `last_name` | VARCHAR(100) | NOT NULL | |
| `tc_identity_no` | VARCHAR(11) | nullable | Şifreli saklanır |
| `birth_date` | DATE | nullable | |
| `gender` | VARCHAR(10) | nullable | `male`, `female`, `other` |
| `marital_status` | VARCHAR(20) | nullable | `single`, `married`, `divorced`, `widowed` |
| `nationality` | VARCHAR(3) | nullable | Ülke kodu |
| `phone` | VARCHAR(20) | nullable | |
| `personal_email` | VARCHAR(255) | nullable | Kişisel e-posta |
| `work_email` | VARCHAR(255) | nullable | İş e-postası |
| `photo_url` | VARCHAR(500) | nullable | Profil fotoğrafı (MinIO) |
| `blood_type` | VARCHAR(5) | nullable | Kan grubu |
| `military_status` | VARCHAR(20) | nullable | Askerlik durumu |
| `disability_status` | BOOLEAN | default: false | Engel durumu |
| `disability_degree` | INTEGER | nullable | Engel yüzdesi |
| `education_level` | VARCHAR(30) | nullable | Eğitim seviyesi |
| `address` | TEXT | nullable | |
| `city_id` | INTEGER | FK → sys_cities, nullable | |
| `district_id` | INTEGER | FK → sys_districts, nullable | |
| `emergency_contact_name` | VARCHAR(200) | nullable | Acil durum kişisi |
| `emergency_contact_phone` | VARCHAR(20) | nullable | |
| `emergency_contact_relation` | VARCHAR(50) | nullable | Yakınlık derecesi |
| `department_id` | BIGINT | FK → org_departments, nullable | |
| `position_id` | BIGINT | FK → org_positions, nullable | |
| `branch_id` | BIGINT | FK → platform_tenant_branches, nullable | |
| `manager_id` | BIGINT | FK → personnel_employees, nullable | Bağlı olduğu yönetici |
| `hire_date` | DATE | NOT NULL | İşe giriş tarihi |
| `termination_date` | DATE | nullable | İşten çıkış tarihi |
| `termination_reason` | VARCHAR(50) | nullable | Çıkış nedeni |
| `employment_type` | VARCHAR(30) | NOT NULL | `full_time`, `part_time`, `intern`, `contract` |
| `contract_type` | VARCHAR(30) | NOT NULL | `indefinite`, `fixed_term` |
| `work_type` | VARCHAR(20) | nullable | `office`, `remote`, `hybrid` |
| `base_salary` | NUMERIC(15,2) | nullable | Brüt maaş |
| `currency` | VARCHAR(3) | default: 'TRY' | |
| `iban` | VARCHAR(34) | nullable | Banka IBAN |
| `sgk_no` | VARCHAR(20) | nullable | SGK sicil numarası |
| `status` | VARCHAR(20) | NOT NULL, default: 'active' | `active`, `on_leave`, `suspended`, `terminated` |
| `notes` | TEXT | nullable | İK notu |
| `metadata` | JSONB | default: '{}' | Ek alanlar |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |
| `created_by` | BIGINT | FK, nullable | |
| `updated_by` | BIGINT | FK, nullable | |
| `is_deleted` | BOOLEAN | default: false | |
| `deleted_at` | TIMESTAMPTZ | nullable | |

**Index:**  
- `ix_personnel_employees_tenant_id`  
- `ix_personnel_employees_department_id`  
- `ix_personnel_employees_manager_id`  
- `ix_personnel_employees_status`  
- `uq_personnel_employees_tenant_employee_no (tenant_id, employee_number)`

#### `org_departments` — Departmanlar

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `name` | VARCHAR(200) | NOT NULL | Departman adı |
| `code` | VARCHAR(50) | nullable | Departman kodu |
| `parent_id` | BIGINT | FK → org_departments, nullable | Üst departman (hiyerarşi) |
| `manager_id` | BIGINT | FK → personnel_employees, nullable | Departman yöneticisi |
| `is_active` | BOOLEAN | default: true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### `org_positions` — Pozisyonlar

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `name` | VARCHAR(200) | NOT NULL | Pozisyon adı |
| `code` | VARCHAR(50) | nullable | Pozisyon kodu |
| `department_id` | BIGINT | FK → org_departments, nullable | Bağlı departman |
| `is_active` | BOOLEAN | default: true | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### `personnel_contracts` — İş Sözleşmeleri

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `employee_id` | BIGINT | FK → personnel_employees | |
| `contract_type` | VARCHAR(30) | NOT NULL | `indefinite`, `fixed_term`, `part_time`, `intern` |
| `start_date` | DATE | NOT NULL | Sözleşme başlangıcı |
| `end_date` | DATE | nullable | Belirli süreli ise bitiş |
| `base_salary` | NUMERIC(15,2) | NOT NULL | Brüt maaş |
| `currency` | VARCHAR(3) | default: 'TRY' | |
| `weekly_hours` | NUMERIC(4,1) | default: 45 | Haftalık çalışma saati |
| `probation_end_date` | DATE | nullable | Deneme süresi bitiş |
| `document_url` | VARCHAR(500) | nullable | Sözleşme dosyası (MinIO) |
| `status` | VARCHAR(20) | NOT NULL | `active`, `expired`, `terminated` |
| `notes` | TEXT | nullable | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

#### `personnel_documents` — Çalışan Belgeleri

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `employee_id` | BIGINT | FK → personnel_employees | |
| `document_type` | VARCHAR(50) | NOT NULL | `id_card`, `diploma`, `health_report`, `contract`, `other` |
| `title` | VARCHAR(255) | NOT NULL | Belge başlığı |
| `file_url` | VARCHAR(500) | NOT NULL | MinIO dosya yolu |
| `file_size` | INTEGER | nullable | Boyut (byte) |
| `mime_type` | VARCHAR(100) | nullable | Dosya tipi |
| `expiry_date` | DATE | nullable | Geçerlilik tarihi (sertifika, sağlık raporu) |
| `uploaded_by` | BIGINT | FK → auth_users | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

#### `personnel_job_history` — Terfi/Nakil Geçmişi

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `employee_id` | BIGINT | FK → personnel_employees | |
| `change_type` | VARCHAR(30) | NOT NULL | `promotion`, `transfer`, `title_change`, `salary_change` |
| `old_department_id` | BIGINT | nullable | Önceki departman |
| `new_department_id` | BIGINT | nullable | Yeni departman |
| `old_position_id` | BIGINT | nullable | Önceki pozisyon |
| `new_position_id` | BIGINT | nullable | Yeni pozisyon |
| `old_salary` | NUMERIC(15,2) | nullable | Önceki maaş |
| `new_salary` | NUMERIC(15,2) | nullable | Yeni maaş |
| `old_manager_id` | BIGINT | nullable | Önceki yönetici |
| `new_manager_id` | BIGINT | nullable | Yeni yönetici |
| `effective_date` | DATE | NOT NULL | Geçerlilik tarihi |
| `reason` | TEXT | nullable | Değişiklik nedeni |
| `approved_by` | BIGINT | FK → auth_users, nullable | Onaylayan |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

---

### 5.2 İzin Modülü

#### `leave_types` — İzin Türleri

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `name` | VARCHAR(100) | NOT NULL | İzin adı: Yıllık ücretli, mazeret, hastalık vs. |
| `code` | VARCHAR(30) | NOT NULL | `annual`, `sick`, `marriage`, `bereavement`, `maternity`, `unpaid`, `administrative` |
| `is_paid` | BOOLEAN | NOT NULL | Ücretli mi |
| `is_document_required` | BOOLEAN | default: false | Belge (rapor) zorunlu mu |
| `max_days_per_year` | INTEGER | nullable | Yıllık maksimum gün (null = sınırsız) |
| `allows_half_day` | BOOLEAN | default: true | Yarım gün izin verilebilir mi |
| `allows_hourly` | BOOLEAN | default: false | Saatlik izin verilebilir mi |
| `is_auto_calculated` | BOOLEAN | default: false | Kıdeme göre otomatik mı |
| `color` | VARCHAR(7) | nullable | Takvimde gösterim rengi (#hex) |
| `is_active` | BOOLEAN | default: true | |
| `sort_order` | SMALLINT | default: 0 | Sıralama |
| `created_at` | TIMESTAMPTZ | NOT NULL | |

**Unique:** `uq_leave_types_tenant_code (tenant_id, code)`

#### `leave_balances` — İzin Bakiyeleri

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `employee_id` | BIGINT | FK → personnel_employees | |
| `leave_type_id` | BIGINT | FK → leave_types | |
| `year` | SMALLINT | NOT NULL | Yıl |
| `total_days` | NUMERIC(5,1) | NOT NULL | Toplam hak |
| `used_days` | NUMERIC(5,1) | default: 0 | Kullanılan |
| `pending_days` | NUMERIC(5,1) | default: 0 | Onay bekleyen |
| `carried_over_days` | NUMERIC(5,1) | default: 0 | Önceki yıldan devir |
| `remaining_days` | NUMERIC(5,1) | GENERATED | `total_days + carried_over_days - used_days - pending_days` |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

**Unique:** `uq_leave_balances_emp_type_year (tenant_id, employee_id, leave_type_id, year)`

#### `leave_requests` — İzin Talepleri

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `tenant_id` | BIGINT | FK | |
| `employee_id` | BIGINT | FK → personnel_employees | Talep eden |
| `leave_type_id` | BIGINT | FK → leave_types | İzin türü |
| `start_date` | DATE | NOT NULL | Başlangıç |
| `end_date` | DATE | NOT NULL | Bitiş |
| `start_half` | VARCHAR(5) | nullable | `am`, `pm` (yarım gün ise) |
| `end_half` | VARCHAR(5) | nullable | `am`, `pm` |
| `total_days` | NUMERIC(5,1) | NOT NULL | Toplam gün (yarım gün dahil) |
| `reason` | TEXT | nullable | Açıklama |
| `document_url` | VARCHAR(500) | nullable | Ek belge (rapor vs.) |
| `status` | VARCHAR(20) | NOT NULL, default: 'pending' | `pending`, `approved`, `rejected`, `cancelled` |
| `approved_by` | BIGINT | FK → auth_users, nullable | Onaylayan |
| `approved_at` | TIMESTAMPTZ | nullable | Onay zamanı |
| `rejection_reason` | TEXT | nullable | Red gerekçesi |
| `cancelled_at` | TIMESTAMPTZ | nullable | İptal zamanı |
| `cancellation_reason` | TEXT | nullable | İptal gerekçesi |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

**Index:**  
- `ix_leave_requests_tenant_employee (tenant_id, employee_id)`  
- `ix_leave_requests_status`  
- `ix_leave_requests_dates (start_date, end_date)` — takvim sorguları için

#### `leave_approval_flows` — Onay Adımları

| Kolon | Tip | Kısıtlama | Açıklama |
|-------|-----|-----------|----------|
| `id` | BIGINT | PK | |
| `leave_request_id` | BIGINT | FK → leave_requests | |
| `step_order` | SMALLINT | NOT NULL | Onay sırası (1, 2, 3...) |
| `approver_id` | BIGINT | FK → auth_users | Onaylayıcı |
| `status` | VARCHAR(20) | NOT NULL, default: 'pending' | `pending`, `approved`, `rejected` |
| `comment` | TEXT | nullable | Onaylayıcı notu |
| `acted_at` | TIMESTAMPTZ | nullable | İşlem zamanı |

---

## 6. Tablo İlişki Özeti

```
platform_tenants
    │
    ├── platform_tenant_branches
    ├── auth_users ─── auth_user_roles ─── auth_roles ─── auth_role_permissions ─── auth_permissions
    │       │
    │       └── auth_refresh_tokens
    │
    ├── personnel_employees
    │       │
    │       ├── personnel_contracts
    │       ├── personnel_documents
    │       ├── personnel_job_history
    │       │
    │       ├── leave_balances ─── leave_types
    │       └── leave_requests ─── leave_approval_flows
    │
    ├── org_departments (self-referencing: parent_id)
    ├── org_positions
    │
    ├── audit_logs
    ├── notif_logs ─── notif_templates
    │
    └── [Faz 3 modülleri: payroll_*, shift_*, recruitment_*, training_*, performance_*]

Global:
    sys_countries ─── sys_cities ─── sys_districts
    sys_currencies
    sys_public_holidays
```

---

## 7. İndeksleme Stratejisi

### 7.1 Genel Kurallar

| Kural | Açıklama |
|-------|----------|
| Her FK otomatik indexlenir | Join performansı için |
| `tenant_id` her tenant-scoped tabloda indexlenir | Partition key gibi davranır |
| Sık sorgulanan filtreler composite index alır | `(tenant_id, status)`, `(tenant_id, employee_id)` |
| Arama alanları GIN index alır | `first_name`, `last_name` üzerinde `pg_trgm` |
| Tarih aralığı sorguları BRIN index alır | `created_at`, `start_date` gibi kronolojik kolonlar |
| JSONB alanlar GIN index alır | `settings`, `metadata` sorgulama için |

### 7.2 Çalışan Arama İndeksi

```sql
-- Trigram index ile fuzzy arama desteği
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX ix_personnel_employees_name_trgm 
ON personnel_employees 
USING GIN ((first_name || ' ' || last_name) gin_trgm_ops);

-- Full-text search vektörü
ALTER TABLE personnel_employees 
ADD COLUMN search_vector TSVECTOR 
GENERATED ALWAYS AS (
    to_tsvector('turkish', coalesce(first_name, '') || ' ' || coalesce(last_name, '') || ' ' || coalesce(employee_number, ''))
) STORED;

CREATE INDEX ix_personnel_employees_search ON personnel_employees USING GIN (search_vector);
```

---

## 8. Migration Stratejisi

### 8.1 Alembic Kullanımı

| Kural | Açıklama |
|-------|----------|
| Her şema değişikliği migration dosyası olmalı | Manuel SQL ile tablo değişikliği yapılmaz |
| Migration dosyaları sıralı ve açıklayıcı isimlendirilir | `001_create_auth_tables.py`, `002_create_personnel_tables.py` |
| Her migration hem `upgrade` hem `downgrade` içerir | Geri alınabilirlik şart |
| Migration'lar CI/CD'de otomatik çalışır | Deploy öncesi migration, sonra uygulama |
| Prod'da migration öncesi yedek alınır | Kritik değişikliklerde zorunlu |

### 8.2 Seed Data

Aşağıdaki veriler ilk kurulumda otomatik oluşturulur:

- Varsayılan sistem rolleri (super_admin, tenant_admin, hr_manager, dept_manager, employee, c_level)
- Varsayılan izin türleri (yıllık, mazeret, hastalık, evlilik, doğum, vefat, ücretsiz, idari)
- Türkiye il ve ilçe listesi
- Resmi tatil takvimi (güncel yıl)
- Para birimleri (TRY, USD, EUR)
- Varsayılan bildirim şablonları

---

## 9. Performans Hedefleri

| Metrik | Hedef | Yöntem |
|--------|-------|--------|
| Çalışan listesi (sayfalı) | < 100ms | Composite index + pagination |
| Çalışan arama | < 300ms | pg_trgm + full-text search |
| İzin bakiyesi sorgusu | < 50ms | Materialized computed column |
| İzin takvimi (departman, 1 ay) | < 200ms | Date range index |
| Dashboard sayaçları | < 200ms | Redis cache (60s TTL) |
| Audit log sorgusu | < 500ms | Time-based partitioning + index |

---

## 10. Güvenlik Kuralları

| Kural | Uygulama |
|-------|----------|
| TC Kimlik No şifreli saklanır | Kolon bazlı AES-256 şifreleme (uygulama katmanı) |
| IBAN şifreli saklanır | Kolon bazlı şifreleme |
| Şifreler hash'lenir | bcrypt, asla düz metin saklanmaz |
| Refresh token hash'lenir | SHA-256 hash |
| Audit log değiştirilemez | INSERT-only tablo, UPDATE/DELETE engellenir |
| DB bağlantısı şifreli | SSL/TLS zorunlu |
| DB kullanıcı yetkileri ayrılır | App user (CRUD), migration user (DDL), read-only user (raporlama) |

---

## 11. Yedekleme Stratejisi

| Yedek Türü | Sıklık | Saklama Süresi |
|------------|--------|----------------|
| Full backup (pg_dump) | Günlük | 30 gün |
| WAL arşivleme (PITR) | Sürekli | 7 gün |
| Aylık full backup | Ayda 1 | 12 ay |

---

## 12. Faz 3 İçin Not

Aşağıdaki modüllerin tablo tasarımları ilgili modül dokümanlarında yapılacaktır:

| Modül | Doküman | Beklenen Tablolar |
|-------|---------|-------------------|
| Bordro & Maaş | 14-modul-bordro-maas.md | `payroll_payslips`, `payroll_parameters`, `payroll_deductions`, `payroll_items` |
| Performans | 13-modul-performans-yonetimi.md | `perf_periods`, `perf_goals`, `perf_evaluations`, `perf_feedbacks` |
| İşe Alım (ATS) | 11-modul-ise-alim-ats.md | `ats_jobs`, `ats_applications`, `ats_candidates`, `ats_interviews` |
| Eğitim | 15-modul-egitim-gelisim.md | `training_courses`, `training_enrollments`, `training_certificates` |
| Vardiya & Mesai | 16-modul-vardiya-mesai.md | `shift_templates`, `shift_assignments`, `shift_attendance` |
| Organizasyon (detay) | 17-modul-organizasyon-semasi.md | `org_hierarchy`, `org_headcount_plans` |

Bu tablolar oluşturulurken bu dokümandaki konvansiyonlara (bölüm 2), ortak kolon yapısına ve multi-tenant kurallarına (bölüm 3) uyulacaktır.

---

## 13. Sonuç

Veritabanı tasarımı aşağıdaki temeller üzerine kurulmuştur:

- **Tek PostgreSQL veritabanı**, tüm modüller aynı DB'de
- **Multi-tenant:** `tenant_id` ile firma izolasyonu, uygulama + RLS katmanı
- **Tutarlı konvansiyonlar:** Adlandırma, veri tipleri, ortak kolonlar tüm tablolarda aynı
- **MVP odaklı detay:** Personel + İzin tabloları tam detaylı, diğerleri Faz 3'e
- **Performans:** İndeksleme stratejisi, full-text search, cache hedefleri belirli
- **Güvenlik:** Kolon bazlı şifreleme, audit log, DB kullanıcı ayrımı

Bir sonraki adımda [08-api-tasarimi.md](08-api-tasarimi.md) dokümanında API endpoint yapısı, versiyonlama, hata formatı ve MVP endpoint listesi detaylandırılacaktır.
