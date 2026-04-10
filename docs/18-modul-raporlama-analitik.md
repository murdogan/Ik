# 18 — Modül: Raporlama & Analitik

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Dashboard tasarımı, İK metrikleri, özel rapor oluşturma, export, filtreleme, veri erişim modeli, analitik cache ve snapshot yapısı  
> **Faz:** Faz 2 — Tüm operasyonel modüllerin üstüne oturan analitik katman  
> **Referans:** 06-sistem-mimarisi.md, 08-api-tasarimi.md, 10-17 arası modül dokümanları

---

## 1. Modül Özeti

Raporlama & Analitik modülü, operasyonel İK verilerini karar destek görünümüne dönüştürür. Amaç yönetici ve İK ekiplerinin personel, izin, performans, eğitim, devamsızlık, işe alım ve maliyet verilerini filtrelenebilir dashboard ve export altyapısı üzerinden izlemesini sağlamaktır.

### 1.1 Analitik Katman Prensipleri

| Prensip | Açıklama |
|---------|----------|
| Snapshot yaklaşımı | Dönemsel raporlar değişmez özet tablolar üzerinden yürür |
| Yetkili görünüm | Rapor verisi rol ve hiyerarşiye göre filtrelenir |
| Export güvenliği | Hassas rapor export'ları audit log'a yazılır |
| Performans | Sık kullanılan dashboard'lar Redis ve pre-aggregation ile hızlandırılır |

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|----------------|-------------------|-----------------|
| **Hakan (Genel Müdür / C-Level)** | Executive dashboard tüketici | Haftalık | Turnover, headcount, maliyet KPI'ları |
| **Ayşe (İK Uzmanı)** | Operasyonel raporcu | Günlük / haftalık | İzin, devamsızlık, bordro raporları, özel rapor |
| **Mehmet (Dept. Yöneticisi)** | Departman raporcu | Haftalık | Ekip performansı, izin durumu, mesai raporu |
| **Süper Admin** | Rapor yöneticisi | Nadiren | Dashboard yapılandırma, veri erişim politikaları |

### 2.2 Genel Müdür — KPI Takibi Yolculuğu

```
GİRİŞ               DASHBOARD              DETAY / EXPORT
   │                    │                       │
   ▼                    ▼                       ▼
Executive dashboard  KPI kartlarını gözden   Trend grafiğine tıkla
sayfasını aç         geçir                   → detay rapor aç
   │                    │                       │
   ├─ Headcount trend   ├─ Kırmızı alarm varsa ├─ Departman bazında
   ├─ Turnover oranı    │  kartı tıkla         │  drill-down
   ├─ Maliyet trendi    ├─ Tarih aralığı       └─ PDF export al
   └─ Performans özeti  │  değiştir                ve yönetime gönder
                        └─ Karşılaştırmalı
                           (YoY / MoM)
```

### 2.3 İK Uzmanı — Özel Rapor Oluşturma Yolculuğu

```
İHTİYAÇ              OLUŞTURMA              PAYLAŞIM
   │                    │                       │
   ▼                    ▼                       ▼
"Departman bazında   Rapor oluşturucuyu aç   Raporu kaydet ve
izin kullanım oranı    │                     zamanla
istiyorum"           ├─ Sütunları seç        ├─ Kaydet (saved reports)
                     ├─ Filtreleri belirle    ├─ Excel export
                     ├─ Gruplama tanımla      ├─ Zamanlanmış gönderim
                     └─ Önizle                └─ Link ile paylaş
```

---

## 3. Fonksiyonel Gereksinimler

### 3.1 Dashboard Yönetimi

#### FR-RPT-01: Hazır Dashboard Kartları

**Kart Tipleri:**

| Tip | Açıklama | Örnek |
|-----|----------|-------|
| `kpi_card` | Tekil metrik + trend | Turnover Rate: 8.2% ↑ |
| `bar_chart` | Kategorik karşılaştırma | Departman bazında headcount |
| `line_chart` | Zaman serisi | Aylık işe alım trendi |
| `pie_chart` | Oran dağılımı | Cinsiyet dağılımı |
| `heatmap` | Yoğunluk matrisi | İzin kullanımı (ay × dept.) |
| `table` | Tablo görünümü | En yüksek turnover departmanlar |
| `gauge` | Hedef/gerçekleşme | Eğitim tamamlama oranı (%) |

**Dashboard Şablonları:**

| Dashboard | Hedef Kitle | Kartlar |
|-----------|-------------|---------|
| Executive | C-Level | Headcount, Turnover, Total Cost, Perf. Avg. |
| İK Operasyon | İK Ekibi | İzin, Devamsızlık, İşe Alım, Bordro Durum |
| Departman | Yöneticiler | Ekip headcount, izin, performans |
| Eğitim | İK / L&D | Tamamlama oranı, sertifika durumu |

#### FR-RPT-02: Özel Rapor Oluşturucu

**Rapor Builder Bileşenleri:**

| Bileşen | Açıklama |
|---------|----------|
| Veri kaynağı seçimi | Hangi modül verileri (Personel, İzin, Bordro…) |
| Sütun seçici | Mevcut alanlardan sütun seçimi (drag-drop) |
| Filtre paneli | Departman, tarih, durum vb. filtreler |
| Gruplama | Group by alan(lar)ı |
| Sıralama | Birincil/ikincil sıralama |
| Görselleştirme tipi | Tablo, bar, line, pie seçimi |
| Formüller (opsiyonel) | COUNT, SUM, AVG, yüzde hesaplama |

#### FR-RPT-03: Görselleştirme ve Grafik Desteği

Desteklenen chart kütüphanesi: **Apache ECharts** (veya tenant tercihi)

| Grafik | Kullanım Alanı |
|--------|----------------|
| Bar / Grouped Bar | Departman, pozisyon karşılaştırma |
| Line / Area | Zaman serileri (headcount, maliyet trendi) |
| Pie / Donut | Oran dağılımları |
| Heatmap | İzin, devamsızlık yoğunlukları |
| Scatter | İki metriğin korelasyonu (ör. kıdem vs. performans) |
| Gauge | Hedef gerçekleşme yüzdeleri |

#### FR-RPT-04: Export ve Çıktı Formatları

| Format | Açıklama | Uygulama |
|--------|----------|----------|
| Excel (.xlsx) | Formatlı çalışma kitabı | openpyxl veya xlsxwriter |
| CSV | Ham veri | Standart CSV |
| PDF | Raporlama formatında | WeasyPrint veya reportlab |
| JSON | API tüketimi | Standart JSON |

**Asenkron Export Akışı:**

```
Kullanıcı export iste → Celery task oluştur → Arka planda üret
     │                                              │
     └── Job durumu: pending → processing → done / failed
                                                    │
                                              İndirme linki
                                              (imzalı, süreli URL)
```

#### FR-RPT-05: Zamanlanmış Rapor Gönderimi

| Özellik | Açıklama |
|---------|----------|
| Frekans | Günlük, haftalık, aylık, çeyreklik |
| Alıcılar | E-posta listesi (sistem içi kullanıcılar) |
| Format | Excel veya PDF |
| Koşullu gönderim | "Verisi yoksa gönderme" seçeneği |
| Zaman dilimi | Tenant timezone'una göre |

### 3.2 Temel İK Metrikleri (KPI Kataloğu)

| Metrik | Formül | Kaynak Modül |
|--------|--------|--------------|
| Headcount | Aktif çalışan sayısı | Personel |
| Turnover Rate | (Dönemde ayrılan / Dönem başı headcount) × 100 | Personel |
| Average Tenure | Ortalama kıdem (yıl) | Personel |
| Absenteeism Rate | (Devamsızlık günü / Toplam çalışma günü) × 100 | İzin |
| Leave Utilization | (Kullanılan izin / Toplam hak edilen) × 100 | İzin |
| Time-to-Hire | Talep açılma → işe başlama (gün ortalaması) | İşe Alım |
| Offer Acceptance Rate | (Kabul edilen teklifler / Toplam teklifler) × 100 | İşe Alım |
| Avg. Performance Score | Dönem ortalama performans puanı | Performans |
| Training Completion | (Tamamlanan atama / Toplam atama) × 100 | Eğitim |
| Overtime Cost Ratio | Fazla mesai maliyeti / Toplam bordro maliyeti | Bordro |
| Cost per Employee | Toplam bordro / Headcount | Bordro |
| Gender Diversity | Kadın/Erkek oranı | Personel |

### 3.3 İş Kuralları

| Kural | Açıklama |
|-------|----------|
| IK-RPT-01 | Yönetici yalnızca yetkili organizasyon alt ağacı verilerini görür |
| IK-RPT-02 | Örneklem < 5 kişi olan gruplamalarda kişisel veri maskelenir (k-anonymity) |
| IK-RPT-03 | Export edilen her hassas rapor kullanıcı, zaman ve filtre bilgisiyle loglanır |
| IK-RPT-04 | Zamanlanmış rapor linkleri imzalı ve süreli (max 72 saat) |
| IK-RPT-05 | Dashboard cache 15 dk'da bir yenilenir; manuel refresh butonu mevcut |
| IK-RPT-06 | Özel rapor sorgusu max 60 saniye sonra timeout olur |

---

## 4. Veri Mimarisi

### 4.1 Katmanlı Yapı

| Katman | Açıklama | Teknoloji |
|--------|----------|-----------|
| Operasyonel tablolar | Kaynak modül verisi (OLTP) | PostgreSQL |
| Summary tablolar | Günlük/aylık özetler (Celery batch) | PostgreSQL |
| Materialized Views | Ağır sorgular için hızlandırma | PostgreSQL REFRESH CONCURRENTLY |
| Cache | Dashboard kart cache'leri | Redis (TTL: 15 dk) |
| Export depolama | Üretilen dosyalar | S3/MinIO (imzalı URL) |

### 4.2 Summary Tabloları (Detay)

#### analytics_headcount_daily

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `snapshot_date` | DATE | Hangi günün snapshot'ı |
| `department_id` | UUID FK → org_units | |
| `total_active` | INTEGER | Aktif çalışan sayısı |
| `total_new_hires` | INTEGER | O ay işe alınanlar |
| `total_terminations` | INTEGER | O ay ayrılanlar |
| `gender_male` | INTEGER | Erkek sayısı |
| `gender_female` | INTEGER | Kadın sayısı |
| `avg_tenure_months` | DECIMAL(6,1) | Ortalama kıdem (ay) |
| `created_at` | TIMESTAMPTZ | |

#### analytics_leave_monthly

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `period_month` | DATE | Dönem (ayın ilk günü) |
| `department_id` | UUID FK → org_units | |
| `leave_type` | VARCHAR(30) | İzin tipi |
| `total_days_used` | DECIMAL(8,1) | Kullanılan toplam gün |
| `total_employees` | INTEGER | İzin kullanan çalışan sayısı |
| `absenteeism_rate` | DECIMAL(5,2) | Devamsızlık oranı (%) |

#### analytics_performance_cycle_summary

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `cycle_id` | UUID FK → performance_cycles | |
| `department_id` | UUID FK → org_units | |
| `avg_score` | DECIMAL(4,2) | Ortalama puan |
| `score_distribution` | JSONB | `{"1": 2, "2": 5, "3": 15, "4": 8, "5": 3}` |
| `completion_rate` | DECIMAL(5,2) | Değerlendirme tamamlanma % |
| `pip_count` | INTEGER | PIP'e alınan çalışan sayısı |

#### analytics_payroll_monthly_cost

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `period_month` | DATE | |
| `department_id` | UUID FK → org_units | |
| `total_gross` | DECIMAL(15,2) | Toplam brüt maliyet |
| `total_net` | DECIMAL(15,2) | Toplam net ödeme |
| `total_employer_cost` | DECIMAL(15,2) | İşveren maliyeti |
| `overtime_cost` | DECIMAL(15,2) | Fazla mesai maliyeti |
| `headcount` | INTEGER | Dönem çalışan sayısı |
| `cost_per_employee` | DECIMAL(12,2) | Kişi başı maliyet |

#### report_definitions

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `name` | VARCHAR(150) | Rapor adı |
| `description` | TEXT NULL | |
| `data_source` | ENUM | `employees`, `leaves`, `performance`, `payroll`, `recruitment`, `training` |
| `columns` | JSONB | Seçili sütunlar `[{"field":"name","label":"Ad"}]` |
| `filters` | JSONB | Filtre koşulları |
| `group_by` | JSONB NULL | Gruplama alanları |
| `sort_by` | JSONB NULL | Sıralama |
| `chart_type` | VARCHAR(20) NULL | Görselleştirme tipi |
| `is_scheduled` | BOOLEAN DEFAULT FALSE | Zamanlanmış mı |
| `schedule_cron` | VARCHAR(50) NULL | Cron ifadesi |
| `schedule_recipients` | JSONB NULL | E-posta alıcıları |
| `schedule_format` | ENUM NULL | `excel`, `pdf` |
| `created_by` | UUID FK → users | |
| `is_shared` | BOOLEAN DEFAULT FALSE | Diğer kullanıcılar görebilir mi |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### report_export_jobs

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `report_id` | UUID FK → report_definitions NULL | Özel rapor ise |
| `dashboard_code` | VARCHAR(50) NULL | Dashboard export ise |
| `format` | ENUM | `excel`, `csv`, `pdf`, `json` |
| `status` | ENUM DEFAULT 'pending' | `pending`, `processing`, `done`, `failed` |
| `file_path` | VARCHAR(500) NULL | S3/MinIO dosya yolu |
| `download_url` | TEXT NULL | İmzalı indirme URL'i |
| `url_expires_at` | TIMESTAMPTZ NULL | Link geçerlilik süresi |
| `row_count` | INTEGER NULL | Toplam satır |
| `file_size_bytes` | BIGINT NULL | Dosya boyutu |
| `filters_applied` | JSONB | Uygulanan filtreler (audit) |
| `requested_by` | UUID FK → users | |
| `started_at` | TIMESTAMPTZ NULL | |
| `completed_at` | TIMESTAMPTZ NULL | |
| `error_message` | TEXT NULL | Hata durumunda |
| `created_at` | TIMESTAMPTZ | |

---

## 5. API Endpoint Detayları

### 5.1 Dashboard Endpoints

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/reports/dashboards` | Dashboard listesi | `report:read` |
| `GET` | `/reports/dashboards/{code}` | Dashboard kart verileri | `report:read` |
| `GET` | `/reports/dashboards/{code}/cards/{cardId}` | Tekil kart verisi | `report:read` |
| `POST` | `/reports/dashboards/{code}/refresh` | Cache yenile | `report:read` |

**GET /reports/dashboards/executive — Yanıt:**

```json
{
  "code": "executive",
  "title": "Executive Dashboard",
  "last_refreshed": "2025-02-03T10:15:00Z",
  "cards": [
    {
      "id": "headcount",
      "type": "kpi_card",
      "title": "Toplam Çalışan",
      "value": 342,
      "previous_value": 338,
      "change_pct": 1.18,
      "trend": "up",
      "period": "2025-02"
    },
    {
      "id": "turnover",
      "type": "kpi_card",
      "title": "Turnover Oranı",
      "value": 8.2,
      "unit": "%",
      "previous_value": 7.5,
      "change_pct": 9.33,
      "trend": "up",
      "alert": true,
      "alert_threshold": 8.0
    },
    {
      "id": "dept_headcount",
      "type": "bar_chart",
      "title": "Departman Bazında Headcount",
      "data": {
        "labels": ["Yazılım", "İK", "Finans", "Satış"],
        "values": [85, 24, 32, 56]
      }
    }
  ]
}
```

### 5.2 Özel Rapor Endpoints

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/reports/custom` | Kayıtlı raporlarım | `report:read` |
| `POST` | `/reports/custom` | Özel rapor tanımla | `report:create` |
| `PUT` | `/reports/custom/{id}` | Rapor güncelle | `report:create` |
| `DELETE` | `/reports/custom/{id}` | Rapor sil | `report:create` |
| `POST` | `/reports/custom/{id}/run` | Raporu çalıştır (senkron) | `report:read` |
| `POST` | `/reports/custom/{id}/preview` | Önizleme (ilk 50 satır) | `report:read` |

**POST /reports/custom — İstek:**

```json
{
  "name": "Departman Bazında İzin Kullanımı",
  "data_source": "leaves",
  "columns": [
    { "field": "department_name", "label": "Departman" },
    { "field": "leave_type", "label": "İzin Tipi" },
    { "field": "total_days", "label": "Toplam Gün", "aggregate": "SUM" },
    { "field": "employee_count", "label": "Kişi Sayısı", "aggregate": "COUNT_DISTINCT" }
  ],
  "filters": [
    { "field": "period", "op": "between", "value": ["2025-01-01", "2025-03-31"] },
    { "field": "status", "op": "eq", "value": "approved" }
  ],
  "group_by": ["department_name", "leave_type"],
  "sort_by": [{ "field": "total_days", "dir": "desc" }],
  "chart_type": "bar_chart"
}
```

### 5.3 Export Endpoints

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/reports/export` | Export job başlat | `report:export` |
| `GET` | `/reports/export/jobs` | Export job listesi | `report:export` |
| `GET` | `/reports/export/jobs/{id}` | Job durumu | `report:export` |
| `GET` | `/reports/export/jobs/{id}/download` | Dosya indir (imzalı URL) | `report:export` |

### 5.4 Zamanlanmış Rapor Endpoints

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/reports/custom/{id}/schedule` | Zamanlama ayarla | `report:schedule` |
| `DELETE` | `/reports/custom/{id}/schedule` | Zamanlama iptal | `report:schedule` |
| `GET` | `/reports/schedules` | Tüm zamanlanmış raporlar | `report:schedule` |

---

## 6. Ekranlar ve Raporlar

### 6.1 Executive Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  Executive Dashboard               Şubat 2025     [⟲ Yenile]   │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ 📊 Headcount    │ 📉 Turnover     │ 💰 Toplam Maliyet          │
│    342          │    8.2%  ⚠️     │    ₺4.2M                   │
│    ↑ +4 (MoM)   │    ↑ +0.7%      │    ↑ +3.1%                 │
├─────────────────┴─────────────────┴─────────────────────────────┤
│  Departman Headcount               │  Aylık Turnover Trendi     │
│  ▓▓▓▓▓▓▓▓▓▓▓▓░░ Yazılım (85)     │  ─────────╱──              │
│  ▓▓▓▓▓▓▓▓░░░░░░ Satış (56)       │           Ort: 7.5%        │
│  ▓▓▓▓▓░░░░░░░░░ Finans (32)      │  ──────────  hedef: 8%     │
│  ▓▓▓░░░░░░░░░░░ İK (24)          │                             │
├─────────────────────────────────────────────────────────────────┤
│  Performans Skor Dağılımı          │  Eğitim Tamamlama          │
│  ⭐1:2 ⭐2:5 ⭐3:15 ⭐4:8 ⭐5:3   │  ▓▓▓▓▓▓▓▓░░ 78%           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Özel Rapor Oluşturucu

```
┌─────────────────────────────────────────────────────────────────┐
│  Rapor Oluşturucu             [Önizle] [Kaydet] [Export] [Zamanla]│
├────────────────────────┬────────────────────────────────────────┤
│  Veri Kaynağı:         │  Sütunlar:                             │
│  [○ Personel]          │  ┌────────────┐  ┌──────────┐         │
│  [● İzin]              │  │ Departman  │→ │ İzin Tipi│→ ...    │
│  [○ Bordro]            │  └────────────┘  └──────────┘         │
│  [○ Performans]        │                                        │
│                        │  Filtreler:                             │
│  Gruplama:             │  Dönem: [2025-Q1]                      │
│  [Departman] [İzin Tipi]│  Durum: [Onaylı]                      │
│                        │                                        │
│  Grafik: [Bar Chart ▼] │  Sıralama: [Toplam Gün ↓]             │
├────────────────────────┴────────────────────────────────────────┤
│  Önizleme (ilk 50 satır):                                      │
│  ┌────────────┬──────────┬──────────┬──────────┐               │
│  │ Departman  │ İzin Tipi│ Top. Gün │ Kişi     │               │
│  ├────────────┼──────────┼──────────┼──────────┤               │
│  │ Yazılım    │ Yıllık   │ 45.0     │ 12       │               │
│  │ Yazılım    │ Hastalık │ 8.0      │ 5        │               │
│  │ Satış      │ Yıllık   │ 38.0     │ 10       │               │
│  └────────────┴──────────┴──────────┴──────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Export Merkezi

```
┌─────────────────────────────────────────────────────────────────┐
│  Export Merkezi                                                 │
├─────┬──────────────────────┬────────┬────────┬────────┬────────┤
│ #   │ Rapor                │ Format │ Satır  │ Durum  │ İşlem  │
├─────┼──────────────────────┼────────┼────────┼────────┼────────┤
│ 1   │ İzin Kullanımı Q1   │ Excel  │ 1,245  │ ✅ Hazır│ [İndir]│
│ 2   │ Bordro Ocak 2025    │ PDF    │ 342    │ ⏳ Üret.│  —     │
│ 3   │ Turnover Raporu      │ CSV    │  —     │ ❌ Hata│ [Tekrar]│
└─────┴──────────────────────┴────────┴────────┴────────┴────────┘
```

---

## 7. Celery Beat / Zamanlanmış Görevler

| Görev | Cron | Açıklama |
|-------|------|----------|
| `refresh_headcount_daily` | Her gün 02:00 | analytics_headcount_daily snapshot'ını günceller |
| `refresh_leave_monthly` | Her ayın 1'i 03:00 | Önceki ayın izin özetini hesaplar |
| `refresh_payroll_monthly` | Her ayın 1'i 04:00 | Önceki ayın bordro maliyet özetini hesaplar |
| `refresh_materialized_views` | Her gün 05:00 | REFRESH MATERIALIZED VIEW CONCURRENTLY |
| `process_scheduled_reports` | Her gün 07:00 | Zamanlanmış raporları üretir ve e-posta gönderir |
| `cleanup_expired_exports` | Her gün 01:00 | 7 günden eski export dosyalarını siler |
| `warm_dashboard_cache` | Her 15 dk | Sık kullanılan dashboard'ların Redis cache'ini yeniler |

---

## 8. Bildirim Şablonları

| Bildirim | Kanal | Alıcı | Tetikleyici |
|----------|-------|-------|-------------|
| Zamanlanmış rapor hazır | E-posta | Rapor alıcıları | Rapor üretildiğinde |
| Export tamamlandı | Push | İsteyen kullanıcı | Export job bittiğinde |
| Export başarısız | Push + E-posta | İsteyen kullanıcı | Export hata aldığında |
| KPI alarm eşiği aşıldı | Push + E-posta | İK + Yönetim | Turnover, devamsızlık vb. eşik aşımı |
| Dashboard veri uyarısı | E-posta | Admin | Veri kaynağında tutarsızlık tespit edildiğinde |

---

## 9. Güvenlik ve Uyumluluk

### 9.1 Veri Erişim Modeli

| Katman | Uygulama |
|--------|----------|
| Satır seviyesi filtreleme | Rapor sorguları `org_unit_id IN (kullanıcının yetkili birimleri)` ile filtrelenir |
| Sütun seviyesi | Hassas alanlar (maaş, TC Kimlik) yalnızca belirli rollere açık |
| k-anonymity | < 5 kişilik gruplarda bireysel veri maskelenir |
| Export audit | Her export: kullanıcı, filtreler, satır sayısı, format loglanır |

### 9.2 Rol-Erişim Matrisi

| Yetki | Süper Admin | İK Uzmanı | Dept. Yöneticisi | Çalışan |
|-------|:-----------:|:---------:|:----------------:|:-------:|
| Executive dashboard | ✅ | ✅ | ❌ | ❌ |
| İK operasyon dashboard | ✅ | ✅ | ❌ | ❌ |
| Departman dashboard | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| Özel rapor oluştur | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| Bordro raporu | ✅ | ✅ (bordro yetkili) | ❌ | ❌ |
| Export | ✅ | ✅ | ✅ (kendi dept.) | ❌ |
| Zamanlanmış rapor | ✅ | ✅ | ❌ | ❌ |
| Rapor tanımı yönetimi | ✅ | ✅ | ❌ | ❌ |

### 9.3 Audit Trail

| Olay | Loglanan Veri |
|------|---------------|
| Rapor görüntüleme | Kullanıcı, dashboard/rapor ID, filtreler, zaman |
| Export başlatma | Kullanıcı, rapor ID, format, filtreler, satır sayısı |
| Export indirme | Kullanıcı, dosya boyutu, indirme zamanı |
| KPI alarm tetiklenmesi | Metrik, eşik, gerçekleşen değer, etkilenen birimler |

---

## 10. Bağımlılıklar

| Modül | Kullanım |
|-------|----------|
| 10 – Personel | Headcount, turnover, demografi verileri |
| 11 – İşe Alım | Time-to-hire, kaynak performansı |
| 12 – İzin | İzin kullanım, devamsızlık verileri |
| 13 – Performans | Skor dağılımı, hedef gerçekleşme |
| 14 – Bordro | Maliyet, maaş, mesai verileri |
| 15 – Eğitim | Tamamlama oranı, sertifika durumu |
| 16 – Vardiya | Puantaj, mesai verileri |
| 17 – Organizasyon | Birim hiyerarşisi (filtreleme) |

---

## 11. Modüller Arası Servis Arayüzü

```python
class ReportingService:
    """Raporlama modülü servis arayüzü."""
    
    def get_dashboard_data(
        self, dashboard_code: str, filters: dict | None = None
    ) -> DashboardDTO:
        """Dashboard kart verilerini döner. Self-Servis modülü tarafından kullanılır."""
        ...
    
    def run_custom_report(
        self, report_id: UUID, filters: dict | None = None
    ) -> ReportResultDTO:
        """Özel raporu çalıştırır; senkron sonuç döner (max 10K satır)."""
        ...
    
    def start_export_job(
        self, report_id: UUID, format: str, filters: dict | None = None
    ) -> ExportJobDTO:
        """Asenkron export başlatır; job ID döner."""
        ...
    
    def get_kpi_value(
        self, metric_code: str, filters: dict | None = None
    ) -> KPIValueDTO:
        """Tekil metrik değeri döner. Dashboard kartları tarafından kullanılır."""
        ...
```

---

## 12. Performans Gereksinimleri

| Metrik | Hedef |
|--------|-------|
| Dashboard kart yükleme (cache hit) | < 200 ms (p95) |
| Dashboard kart yükleme (cache miss) | < 2 saniye (p95) |
| Özel rapor çalıştırma (< 10K satır) | < 5 saniye |
| Özel rapor çalıştırma (> 10K satır) | Asenkron; max 60 saniye timeout |
| Export üretimi (Excel, 50K satır) | < 30 saniye (asenkron) |
| Materialized view refresh | < 5 dakika (off-peak) |
| KPI hesaplama (cache miss) | < 1 saniye |

---

## 13. Test Senaryoları

### 13.1 Birim Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| UT-01 | Headcount KPI hesaplama | Aktif çalışan sayısı doğru |
| UT-02 | Turnover formülü | (Ayrılan / Dönem başı) × 100 doğru |
| UT-03 | k-anonymity maskeleme (< 5 kişi) | Kişisel veriler maskelenir |
| UT-04 | Filtre uygulama (departman + tarih) | Doğru alt küme döner |
| UT-05 | Sütun yetki kontrolü (maaş alanı) | Yetkisiz kullanıcı maaş sütununu göremez |
| UT-06 | Export URL imza doğrulama | Süresi geçmiş URL 403 döner |

### 13.2 Entegrasyon Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| IT-01 | Headcount snapshot → dashboard KPI | Günlük batch sonrası dashboard verisi tutarlı |
| IT-02 | Asenkron export → S3 depolama | Dosya oluşturulur, imzalı URL çalışır |
| IT-03 | Zamanlanmış rapor → e-posta gönderimi | Rapor üretilir, alıcılara mail gider |
| IT-04 | Rol filtresi → departman kısıtı | Yönetici sadece kendi departman verisini görür |
| IT-05 | Materialized view refresh → cache invalidate | Refresh sonrası cache tutarlı |

### 13.3 E2E / Performans Testler

| # | Senaryo | Adımlar |
|---|---------|---------|
| E2E-01 | Dashboard tam akış | Login → Executive dashboard → KPI kontrol → Drill-down → Export |
| E2E-02 | Özel rapor oluştur → zamanla | Rapor tanımla → Önizle → Kaydet → Zamanlama ayarla → E-posta doğrula |
| E2E-03 | Büyük veri export | 50K satırlık raporu Excel export et → İndirme linkini doğrula |
| PERF-01 | Dashboard cache performansı | 100 eşzamanlı dashboard isteği, p95 < 200ms |

---

## 14. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | Gerçek zamanlı streaming analitik desteklenmez; veriler batch/near-real-time |
| K2 | Özel rapor sorgusu max 60 saniye; karmaşık sorgular asenkron'a yönlendirilir |
| K3 | k-anonymity eşiği (5) tenant bazında yapılandırılabilir |
| V1 | Tüm summary tablolar her gece yeniden hesaplanır; gün içi anlık değildir |
| V2 | Chart rendering frontend tarafında yapılır (ECharts); API sadece veri döner |
| V3 | Export dosyaları 7 gün sonra otomatik silinir |
