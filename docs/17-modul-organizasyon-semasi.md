# 17 — Modül: Organizasyon Şeması & Pozisyon Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Şirket hiyerarşisi, departman yapısı, pozisyon katalogları, kadro planlama, raporlama ilişkileri, vekalet ve yönetici zinciri  
> **Faz:** Faz 2 — Personel ve Performans modüllerinin kurumsal hiyerarşi temelini oluşturur  
> **Referans:** 10-modul-personel-yonetimi.md, 13-modul-performans-yonetimi.md, 19-modul-self-servis-portal.md

---

## 1. Modül Özeti

Organizasyon Şeması modülü; şirketin fonksiyon, departman, takım ve pozisyon yapısını tekil doğruluk kaynağı olarak yönetir. Amaç yalnızca görsel organigram üretmek değil; yetki, onay, raporlama ve planlama süreçlerinin hiyerarşik altyapısını sağlamaktır.

### 1.1 Kapsam

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| Şirket, birim, departman ve ekip tanımları | Fiziksel ofis yerleşim planı |
| Pozisyon kataloğu ve pozisyon seviyeleri | Tam workforce planning optimizasyonu |
| Yönetici-çalışan raporlama ilişkileri | Maaş bandı hesap motoru |
| Vekalet ve geçici raporlama zinciri | — |
| Kadro durumları: dolu, açık, planlanan | — |

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|----------------|-------------------|-----------------|
| **Süper Admin** | Kök yapı yöneticisi | Nadiren (kurulum) | Şirket ağacı inşası, pozisyon sınıfları tanımlama |
| **Ayşe (İK Uzmanı)** | Organizasyon yöneticisi | Haftalık | Birim/pozisyon CRUD, kadro planlama, vekalet tanımı |
| **Mehmet (Dept. Yöneticisi)** | Hiyerarşi tüketicisi | İhtiyaç anında | Takımını görür, reorganizasyon talebi bildirir |
| **Zeynep (Çalışan)** | Organigram okuyucu | İhtiyaç anında | Şirket rehberi, kime rapor verdiğini görme |
| **Hakan (Genel Müdür)** | Stratejik planlayıcı | Aylık / çeyreklik | Kadro durumu, reorganizasyon onayı |

### 2.2 İK Uzmanı — Yapı Değişikliği Yolculuğu

```
TALEP                  PLANLAMA                UYGULAMA
   │                      │                        │
   ▼                      ▼                        ▼
Yeni departman veya    Organizasyon ağacında    Değişikliği yayınla
pozisyon talebi geldi  değişikliği planla       ve bildirimleri gönder
   │                      │                        │
   ├─ Üst yönetim onayı  ├─ Hangi birimin altı?  ├─ Efektif tarih
   ├─ Kadro planı güncelle├─ Yönetici ata         ├─ İlgili çalışanlar
   └─ Maliyet merkezi bel.├─ Pozisyonları tanımla  │  haberdar edilir
                          └─ Kadro aç             └─ Onay zincirleri
                                                      güncellenir
```

### 2.3 Çalışan — Organizasyon Keşfi Yolculuğu

```
SORU                   ARAMA                   SONUÇ
   │                      │                       │
   ▼                      ▼                       ▼
"Kime rapor veriyorum?" Organigram veya        Yönetici zinciri,
"X departman kim?"      şirket rehberinde       iletişim bilgileri
                        arama                    
```

---

## 3. Fonksiyonel Gereksinimler

### 3.1 Organizasyon Ağacı Yönetimi

#### FR-ORG-01: Çok Seviyeli Organizasyon Ağacı

**Düğüm Tipleri:**

| Tip | Açıklama | Örnek |
|-----|----------|-------|
| `company` | Kök düğüm (tenant = 1 company) | ABC Teknoloji A.Ş. |
| `division` | Ana bölüm | Teknoloji, İş Geliştirme |
| `department` | Departman | Yazılım Geliştirme, İnsan Kaynakları |
| `team` | Alt ekip | Backend Takımı, Mobil Takımı |
| `virtual` | Matris / proje ekibi | Ürün Lansman Ekibi |

**Düğüm Özellikleri:**

| Özellik | Açıklama |
|---------|----------|
| Kod | Benzersiz birim kodu (ör. DEP-SW-001) |
| Adı | Birim adı |
| Üst birim | parent_id (ağaç ilişkisi) |
| Yönetici | Birimin yöneticisi (employees FK) |
| Maliyet merkezi | Muhasebe entegrasyonu kodu |
| Efektif tarih | Birimin geçerlilik başlangıcı |
| Bitiş tarihi | NULL = aktif; dolu ise geçmişe alınmış |
| Sıra (sort_order) | Aynı seviyede görsel sıralama |

#### FR-ORG-02: Departman / Ekip Detayları

Her birim için atanabilecek ek bilgiler:

| Özellik | Açıklama |
|---------|----------|
| Yönetici | Birimin birincil yöneticisi |
| Maliyet merkezi kodu | Finansal raporlama bağlantısı |
| Lokasyon | Birimin fiziksel/sanal çalışma yeri |
| Açıklama | Birimin misyonu/kapsamı |

### 3.2 Pozisyon Yönetimi

#### FR-ORG-03: Pozisyon Kataloğu

| Özellik | Açıklama |
|---------|----------|
| Pozisyon kodu | Benzersiz (ör. POS-SWE-001) |
| Unvan | "Kıdemli Yazılım Mühendisi" |
| Rol ailesi (job_family) | Engineering, Finance, HR, Sales vs. |
| Kademe (grade) | Junior, Mid, Senior, Lead, Manager, Director, VP, C-Level |
| Bağlı birim | Hangi org_unit altında |
| Min/Max headcount | Kadro planlama sınırları |
| Maaş bandı referansı | (Bordro modülü ile ilişki, opsiyonel) |
| Yetkinlikler | Pozisyona beklenen yetkinlik listesi |

#### FR-ORG-04: Kadro Durumu Takibi

| Kadro Durumu | Açıklama |
|--------------|----------|
| `filled` | Aktif çalışan atanmış |
| `open` | Açık pozisyon, ilan verilebilir (İşe Alım modülüne bağlantı) |
| `planned` | Gelecek dönem planlanmış |
| `frozen` | Dondurulmuş (bütçe kısıtı) |
| `retired` | Pozisyon kapatılmış |

### 3.3 Raporlama İlişkileri

#### FR-ORG-05: Çoklu Raporlama Zinciri

| İlişki Tipi | Açıklama |
|-------------|----------|
| `direct` | Birincil (doğrudan) yönetici — performans, izin onayı |
| `dotted` | Matris (noktalı çizgi) — proje bazlı |
| `delegation` | Geçici vekalet — tarih aralığı ile |

#### FR-ORG-06: Vekalet Yönetimi

**Durum Makinesi:**

```
                 ┌──────────┐
   Oluşturuldu → │ scheduled │
                 └────┬─────┘
        efektif tarih geldi
                 ┌────▼─────┐
                 │  active   │
                 └────┬─────┘
          bitiş tarihi doldu / iptal
                 ┌────▼─────┐
                 │  ended    │
                 └──────────┘
```

### 3.4 İş Kuralları

| Kural | Açıklama |
|-------|----------|
| IK-ORG-01 | Bir organizasyon düğümü kendi alt düğümüne bağlanamaz; döngü engellenir (CTE ile kontrol) |
| IK-ORG-02 | Aktif çalışanı olan pozisyon doğrudan silinemez; önce `retired` yapılmalı |
| IK-ORG-03 | Vekalet ilişkisi bitiş tarihinden sonra otomatik `ended` olur |
| IK-ORG-04 | Yetki ve onay akışları için geçerli yönetici zinciri her gün cache'lenir |
| IK-ORG-05 | Aynı anda bir pozisyon için birden fazla aktif vekalet olamaz |
| IK-ORG-06 | Organizasyon değişiklikleri efektif tarih ile planlanabilir; geçmişe yürümez |
| IK-ORG-07 | Birim silindiğinde alt birimleri üst birime taşınır (cascading reassign) |

---

## 4. Veritabanı Tasarımı

### 4.1 org_units

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | Multi-tenant |
| `parent_id` | UUID FK → org_units NULL | Üst birim (kök için NULL) |
| `code` | VARCHAR(30) UNIQUE | Birim kodu (ör. DEP-SW-001) |
| `name` | VARCHAR(150) | Birim adı |
| `unit_type` | ENUM | `company`, `division`, `department`, `team`, `virtual` |
| `manager_id` | UUID FK → employees NULL | Birim yöneticisi |
| `cost_center` | VARCHAR(30) NULL | Maliyet merkezi kodu |
| `location` | VARCHAR(200) NULL | Fiziksel/sanal lokasyon |
| `description` | TEXT NULL | Birim açıklaması |
| `sort_order` | SMALLINT DEFAULT 0 | Aynı seviyede sıralama |
| `effective_date` | DATE | Geçerlilik başlangıcı |
| `end_date` | DATE NULL | NULL = aktif |
| `is_active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

```sql
CREATE INDEX ix_org_units_parent ON org_units (tenant_id, parent_id);
CREATE INDEX ix_org_units_manager ON org_units (tenant_id, manager_id);

-- Döngü kontrolü için recursive CTE
-- Uygulama katmanında INSERT/UPDATE trigger ile çağrılır
```

### 4.2 org_positions

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `org_unit_id` | UUID FK → org_units | Bağlı birim |
| `code` | VARCHAR(30) UNIQUE | Pozisyon kodu (ör. POS-SWE-001) |
| `title` | VARCHAR(150) | Unvan |
| `job_family` | VARCHAR(50) | Rol ailesi (Engineering, HR, Finance…) |
| `grade` | VARCHAR(30) | Kademe (Junior, Mid, Senior, Lead…) |
| `min_headcount` | SMALLINT DEFAULT 1 | Minimum kadro |
| `max_headcount` | SMALLINT DEFAULT 1 | Maksimum kadro |
| `current_headcount` | SMALLINT DEFAULT 0 | Önbellek: mevcut doluluk |
| `status` | ENUM DEFAULT 'open' | `filled`, `open`, `planned`, `frozen`, `retired` |
| `salary_band_ref` | VARCHAR(30) NULL | Bordro maaş bandı referansı |
| `required_competencies` | JSONB NULL | `["Python","Proje Yönetimi"]` |
| `description` | TEXT NULL | Pozisyon tanımı |
| `is_active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### 4.3 org_reporting_lines

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `employee_id` | UUID FK → employees | Raporlayan çalışan |
| `manager_id` | UUID FK → employees | Yönetici |
| `line_type` | ENUM | `direct`, `dotted` |
| `effective_date` | DATE | |
| `end_date` | DATE NULL | NULL = aktif |
| `created_at` | TIMESTAMPTZ | |

```sql
ALTER TABLE org_reporting_lines
  ADD CONSTRAINT uq_reporting_direct
  UNIQUE (tenant_id, employee_id, line_type, effective_date)
  WHERE line_type = 'direct';
```

### 4.4 org_delegations

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `delegator_id` | UUID FK → employees | Vekalet veren |
| `delegate_id` | UUID FK → employees | Vekalet alan |
| `scope` | ENUM | `full` (tüm yetkiler), `approval_only`, `custom` |
| `scope_permissions` | JSONB NULL | Custom scope detayı |
| `start_date` | DATE | Vekalet başlangıcı |
| `end_date` | DATE | Vekalet bitişi |
| `status` | ENUM DEFAULT 'scheduled' | `scheduled`, `active`, `ended`, `cancelled` |
| `reason` | TEXT NULL | Vekalet nedeni (izin, iş seyahati) |
| `created_by` | UUID FK → users | |
| `created_at` | TIMESTAMPTZ | |

### 4.5 org_headcount_plans

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `position_id` | UUID FK → org_positions | |
| `plan_year` | SMALLINT | Planlama yılı |
| `plan_quarter` | SMALLINT NULL | 1-4 veya NULL (yıllık) |
| `planned_headcount` | SMALLINT | Planlanan kadro sayısı |
| `budget_status` | ENUM | `approved`, `pending`, `rejected` |
| `notes` | TEXT NULL | |
| `created_at` | TIMESTAMPTZ | |

---

## 5. API Endpoint Detayları

### 5.1 Organizasyon Birimleri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/organization/units` | Ağaç listesi (flat veya nested) | `organization:read` |
| `GET` | `/organization/units/{id}` | Birim detayı | `organization:read` |
| `POST` | `/organization/units` | Birim oluştur | `organization:create` |
| `PUT` | `/organization/units/{id}` | Birim güncelle | `organization:update` |
| `PATCH` | `/organization/units/{id}/move` | Birim taşı (parent değiştir) | `organization:update` |
| `DELETE` | `/organization/units/{id}` | Birim pasife al | `organization:delete` |

**GET /organization/units?format=tree — Yanıt:**

```json
{
  "id": "root-uuid",
  "name": "ABC Teknoloji A.Ş.",
  "unit_type": "company",
  "manager": { "id": "emp-ceo", "full_name": "Hakan Demir" },
  "children": [
    {
      "id": "div-tech",
      "name": "Teknoloji",
      "unit_type": "division",
      "manager": { "id": "emp-cto", "full_name": "Can Kaya" },
      "children": [
        {
          "id": "dep-sw",
          "name": "Yazılım Geliştirme",
          "unit_type": "department",
          "children": []
        }
      ]
    }
  ]
}
```

**POST /organization/units — İstek:**

```json
{
  "parent_id": "div-tech",
  "code": "DEP-DATA-001",
  "name": "Veri Mühendisliği",
  "unit_type": "department",
  "manager_id": "emp-123",
  "cost_center": "CC-DATA",
  "effective_date": "2025-04-01"
}
```

### 5.2 Pozisyonlar

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/organization/positions` | Pozisyon listesi (filtre) | `organization:read` |
| `POST` | `/organization/positions` | Pozisyon oluştur | `organization:create` |
| `PUT` | `/organization/positions/{id}` | Pozisyon güncelle | `organization:update` |
| `PATCH` | `/organization/positions/{id}/status` | Durum değiştir | `organization:update` |

**GET /organization/positions?status=open — Yanıt:**

```json
{
  "items": [
    {
      "id": "pos-uuid",
      "code": "POS-SWE-003",
      "title": "Kıdemli Backend Geliştirici",
      "org_unit": { "id": "dep-sw", "name": "Yazılım Geliştirme" },
      "grade": "Senior",
      "job_family": "Engineering",
      "status": "open",
      "min_headcount": 1,
      "max_headcount": 2,
      "current_headcount": 0
    }
  ],
  "total": 1
}
```

### 5.3 Raporlama İlişkileri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/organization/reporting-lines/{employeeId}` | Yönetici zinciri | `organization:read` |
| `POST` | `/organization/reporting-lines` | İlişki oluştur | `organization:update` |
| `DELETE` | `/organization/reporting-lines/{id}` | İlişki sonlandır | `organization:update` |

### 5.4 Vekalet

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/organization/delegations` | Vekalet oluştur | `organization:delegate` |
| `GET` | `/organization/delegations` | Aktif vekaletler | `organization:read` |
| `PATCH` | `/organization/delegations/{id}/cancel` | Vekalet iptal | `organization:delegate` |

### 5.5 Self-Servis

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/organization/tree` | Kendi bulunduğum ağaç | Auth |
| `GET` | `/me/organization/manager-chain` | Yönetici zincirim | Auth |
| `GET` | `/me/organization/team` | Aynı birim çalışma arkadaşlarım | Auth |

---

## 6. Ekranlar ve Raporlar

### 6.1 İnteraktif Organigram

```
┌─────────────────────────────────────────────────────────────────┐
│  Organizasyon Şeması           [Ağaç] [Liste] [Arama]  [Filtre]│
│                                                                 │
│                    ┌──────────────┐                              │
│                    │  ABC Tekno.  │                              │
│                    │  Hakan Demir │                              │
│                    │  CEO         │                              │
│                    └──────┬───────┘                              │
│              ┌────────────┼────────────┐                        │
│        ┌─────▼─────┐ ┌───▼────┐ ┌─────▼──────┐                 │
│        │ Teknoloji │ │  İK    │ │ İş Gelişt. │                 │
│        │ Can Kaya  │ │ Ayşe Y.│ │ Fatma K.   │                 │
│        │ CTO       │ │ HRD    │ │ VP         │                 │
│        └─────┬─────┘ └────────┘ └────────────┘                 │
│        ┌─────┼──────┐                                           │
│   ┌────▼───┐ ┌──▼──┐                                           │
│   │Yazılım │ │Veri │   Tıklayınca: birim detayı, kadro durumu  │
│   │12/15   │ │3/5  │   açılır (dolu/açık kadro sayısı)         │
│   └────────┘ └─────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Pozisyon Kataloğu

```
┌─────────────────────────────────────────────────────────────────┐
│  Pozisyon Kataloğu               [+ Yeni Pozisyon]     [Filtre]│
├──────────┬─────────────────────┬─────────┬──────┬──────┬───────┤
│ Kod      │ Unvan               │ Birim   │Kademe│Durum │Doluluk│
├──────────┼─────────────────────┼─────────┼──────┼──────┼───────┤
│ POS-001  │ Sr. Backend Dev.    │ Yazılım │Senior│ Dolu │ 2/2   │
│ POS-002  │ Jr. Frontend Dev.   │ Yazılım │Junior│ Açık │ 0/1   │
│ POS-003  │ Data Engineer       │ Veri    │ Mid  │ Plan.│ 0/2   │
│ POS-004  │ İK Uzmanı           │ İK      │ Mid  │ Dolu │ 1/1   │
└──────────┴─────────────────────┴─────────┴──────┴──────┴───────┘
```

### 6.3 Kadro Plan Raporu

| Rapor | Açıklama | Çıktı |
|-------|----------|-------|
| Kadro doluluk özeti | Departman bazında dolu/açık/planlanan | Grafik + tablo |
| Yönetici span-of-control | Her yöneticinin doğrudan raporlayan sayısı | Tablo |
| Pozisyon dağılımı | Job family / grade bazında headcount | Pivot tablo |
| Vekalet takip raporu | Aktif ve yaklaşan vekaletler | Liste |
| Organizasyon değişiklik geçmişi | Birim/pozisyon oluşturma/kapatma log'u | Zaman çizelgesi |

---

## 7. Celery Beat / Zamanlanmış Görevler

| Görev | Cron | Açıklama |
|-------|------|----------|
| `refresh_manager_chain_cache` | Her gün 01:00 | Tüm çalışanlar için yönetici zincirini Redis cache'e yazar |
| `auto_end_expired_delegations` | Her gün 00:15 | Bitiş tarihi geçmiş vekaletleri `ended` yapar |
| `sync_position_headcounts` | Her gün 02:00 | current_headcount alanını aktif atamalardan yeniden hesaplar |
| `notify_upcoming_delegations` | Her gün 09:00 | Yarın başlayacak vekaletler hakkında bildirim gönderir |

---

## 8. Bildirim Şablonları

| Bildirim | Kanal | Alıcı | Tetikleyici |
|----------|-------|-------|-------------|
| Vekalet atandı | Push + E-posta | Vekalet alan + veren | Vekalet oluşturulduğunda |
| Vekalet başladı | Push | Vekalet alan | Efektif tarih geldiğinde |
| Vekalet sona erdi | Push | Vekalet alan + veren | Bitiş tarihi dolduğunda |
| Organizasyon değişikliği | E-posta | Etkilenen çalışanlar | Birim taşıma/kapatma yapıldığında |
| Yeni pozisyon açıldı | E-posta | İşe alım ekibi | Pozisyon `open` yapıldığında |
| Kadro planı onaylandı | E-posta | İK + dept. yöneticisi | Headcount plan onayı |

---

## 9. Güvenlik ve Uyumluluk

### 9.1 Rol-Erişim Matrisi

| Yetki | Süper Admin | İK Uzmanı | Dept. Yöneticisi | Çalışan |
|-------|:-----------:|:---------:|:----------------:|:-------:|
| Birim CRUD | ✅ | ✅ | ❌ | ❌ |
| Birim görüntüle | ✅ | ✅ | ✅ | ✅ (organigram) |
| Pozisyon CRUD | ✅ | ✅ | ❌ | ❌ |
| Kadro planı yönetimi | ✅ | ✅ | ⚠️ (talep) | ❌ |
| Raporlama ilişkisi tanımla | ✅ | ✅ | ❌ | ❌ |
| Vekalet oluştur | ✅ | ✅ | ✅ (kendi ekibi) | ❌ |
| Yönetici zinciri görüntüle | ✅ | ✅ | ✅ (kendi ekibi) | ✅ (kendi) |
| Kadro raporu | ✅ | ✅ | ✅ (kendi dept.) | ❌ |

### 9.2 Audit Trail

| Olay | Loglanan Veri |
|------|---------------|
| Birim oluşturma/güncelleme/silme | Eski/yeni değerler, kullanıcı, zaman |
| Pozisyon durum değişikliği | Eski/yeni status, kullanıcı |
| Raporlama ilişkisi değişikliği | Eski/yeni yönetici, efektif tarih |
| Vekalet işlemleri | Oluşturma/iptal, ilgili taraflar |
| Birim taşıma (parent değişikliği) | Eski/yeni parent, etkilenen alt düğümler |

---

## 10. Bağımlılıklar

| Modül | Kullanım |
|-------|----------|
| 10 – Personel | Çalışan-pozisyon eşleşmesi, department_id ilişkisi |
| 11 – İşe Alım | Açık pozisyon bilgisi, talep oluşturma |
| 12 – İzin | Onay zinciri için yönetici hiyerarşisi |
| 13 – Performans | Değerlendirici hiyerarşisi, matris raporlama |
| 19 – Self-Servis | Şirket rehberi ve organizasyon kartı |
| 25 – Yetkilendirme | Rol-temelli erişim, departman scope filtreleme |

---

## 11. Modüller Arası Servis Arayüzü

```python
class OrganizationService:
    """Organizasyon modülü servis arayüzü."""
    
    def get_org_tree(
        self, tenant_id: UUID, root_unit_id: UUID | None = None
    ) -> OrgTreeDTO:
        """Tüm modüller tarafından çağrılabilir; organizasyon ağacı."""
        ...
    
    def get_manager_chain(
        self, employee_id: UUID
    ) -> list[EmployeeSummaryDTO]:
        """İzin/Performans modülleri; onay zinciri için yönetici listesi."""
        ...
    
    def get_direct_reports(
        self, manager_id: UUID
    ) -> list[EmployeeSummaryDTO]:
        """Yöneticinin doğrudan raporlayan çalışanları."""
        ...
    
    def get_active_delegation(
        self, employee_id: UUID, target_date: date | None = None
    ) -> DelegationDTO | None:
        """Aktif vekalet varsa döner; onay motorları tarafından çağrılır."""
        ...
    
    def get_open_positions(
        self, org_unit_id: UUID | None = None
    ) -> list[PositionDTO]:
        """İşe alım modülü tarafından çağrılır; açık pozisyon listesi."""
        ...
```

---

## 12. Performans Gereksinimleri

| Metrik | Hedef |
|--------|-------|
| Organizasyon ağacı yükleme (1000 düğüm) | < 500 ms (p95) |
| Yönetici zinciri sorgusu (10 seviye) | < 100 ms (cache) |
| Pozisyon arama (filtreleme) | < 300 ms (p95) |
| Vekalet durum güncelleme (batch) | < 5 saniye |
| Organigram render (frontend, 500 düğüm) | < 2 saniye ilk yükleme |

---

## 13. Test Senaryoları

### 13.1 Birim Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| UT-01 | Döngüsel hiyerarşi oluşturma denemesi | `CircularReferenceError` |
| UT-02 | Aktif çalışanı olan pozisyonu silme | 400 Bad Request; önce retire edilmeli |
| UT-03 | Kök birimi silme denemesi | 400 Bad Request; company düğümü silinemez |
| UT-04 | Aynı parent altında aynı code ile birim oluşturma | Unique constraint ihlali |
| UT-05 | Vekalet çakışması (aynı delegator, overlapping tarih) | `DelegationConflictError` |
| UT-06 | Headcount sınırı aşımı | Uyarı: max_headcount aşıldı |

### 13.2 Entegrasyon Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| IT-01 | Birim silme → alt birimlerin üst birime taşınması | Alt birimler parent_id güncellenir |
| IT-02 | Yönetici zinciri cache refresh | Redis'teki zincir güncel veriye eşit |
| IT-03 | Vekalet başlangıcı → yetki delegasyonu | Vekil, orijinal yöneticinin onay yetkilerini alır |
| IT-04 | Pozisyon `open` → İşe alım modülüne bildirim | İşe alım modülü açık pozisyonu görür |

### 13.3 E2E Testler

| # | Senaryo | Adımlar |
|---|---------|---------|
| E2E-01 | Reorganizasyon | Yeni departman oluştur → Pozisyon aç → Çalışan ata → Raporlama ilişkisi kur → Organigram'da doğrula |
| E2E-02 | Vekalet döngüsü | Vekalet oluştur → Başlangıç tarihi gel → Onay talebi vekile git → Vekalet bitişi → Yetki geri dön |
| E2E-03 | Kadro planlama | Headcount plan oluştur → Onay → Pozisyon aç → İşe alım ile eşle |

---

## 14. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | Organizasyon ağacı maksimum 10 seviye derinliğe sahip olabilir (performans) |
| K2 | Virtual (matris) birimler resmi organizasyon hiyerarşisinde görünmez; ayrı filtre gerektirir |
| V1 | Her tenant'ın tek bir kök (company) düğümü vardır |
| V2 | Yönetici zinciri cache her gece yenilenir; acil değişikliklerde cache invalidate edilir |
| V3 | Maliyet merkezi kodları ERP/muhasebe sisteminden alınır |
