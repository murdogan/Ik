# 14 — Modül: Bordro & Maaş Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Maaş hesaplama, ücret bileşenleri, yasal kesintiler, fazla mesai, prim/ikramiye, bordro kapanışı, bordro export, banka ödeme dosyası, SGK ve vergi uyum verileri  
> **Faz:** Faz 2 — İzin, Personel ve Organizasyon modülleri oturduktan sonra devreye alınır  
> **Referans:** 04-gereksinim-analizi.md, 07-veritabani-tasarimi.md, 08-api-tasarimi.md, 09-entegrasyon-haritasi.md, 10-modul-personel-yonetimi.md, 12-modul-izin-devamsizlik.md, 16-modul-vardiya-mesai.md

---

## 1. Modül Özeti

Bordro & Maaş Yönetimi modülü; çalışan ücretlerinin dönemsel olarak hesaplanması, yasal kesintilerin uygulanması, yan hak ve ek ödemelerin işlenmesi, bordro kapanışı ve ödeme çıktılarının üretilmesini sağlar. Modülün ana amacı, Türkiye mevzuatına uyumlu, denetlenebilir ve tenant bazında yapılandırılabilir bir bordro süreci sunmaktır.

İlk sürümde odak Türkiye bordro mevzuatı olacaktır. Çok ülke bordro desteği kapsam dışıdır. Performans ve vardiya verileri bordroya referans veri sağlar; nihai hesaplama bordro modülünde yapılır.

### 1.1 Kapsam

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| Ücret tipi ve maaş bileşenleri | Muhasebe ERP içinde tam yevmiye oluşumu |
| Brüt-net hesaplama | Uluslararası bordro mevzuatı |
| SGK, gelir vergisi, damga vergisi kesintileri | Banka mutabakatının tam otomasyonu |
| Fazla mesai ve ek kazanç yansıtma | Avans kredi skorlama |
| Prim, ikramiye ve ek ödeme kalemleri | Çalışan harcama yönetimi |
| Bordro taslak, onay ve kapanış akışı | — |
| PDF bordro pusulası üretimi | — |
| Banka ödeme dosyası | — |

### 1.2 İlişkili Modüller

```
Personel  ──▶ ücret tipi, medeni hal, SGK bilgileri
İzin      ──▶ ücretsiz izin, raporlu gün, devamsızlık etkisi
Vardiya   ──▶ fazla mesai, gece vardiyası, puantaj
Performans──▶ prim/bonus referans verisi
Entegrasyon──▶ banka, muhasebe, e-beyanname adaptörleri
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|----------------|-------------------|-----------------|
| **Ayşe (Bordro Uzmanı)** | Operasyon sahibi | Aylık yoğun (ayın 20-30'u) | Puantaj kontrolü, bordro hesaplama, kapanış, banka export |
| **Mehmet (İK Müdürü)** | Onaylayıcı | Aylık 2-3 gün | Taslak bordroyu gözden geçirme, toplu onay, revizyon kararı |
| **Emre (Finans Sorumlusu)** | Ödeme çıktı tüketicisi | Aylık 1-2 gün | Banka ödeme dosyası indirme, toplam maliyet kontrolü, muhasebe export |
| **Zeynep (Çalışan)** | Son kullanıcı | Aylık 1 kez | Bordro pusulası görüntüleme, geçmiş ay karşılaştırma |
| **Hakan (Genel Müdür)** | Dashboard tüketici | Aylık/çeyreklik | Toplam personel maliyeti, departman kıyası |

### 2.2 Bordro Uzmanı — Aylık Bordro Çevrimi Yolculuğu

```
HAZIRLIK (Ayın 20-25)       HESAPLAMA (Ayın 25-28)       KAPANIŞ (Ayın 28-30)
   │                            │                            │
   ▼                            ▼                            ▼
Puantaj verisi              Bordro hesaplamasını          Finans onayı
toplandı/doğrulandı         çalıştır                      alındı
   │                            │                            │
   ├─ Vardiya modülünden       ├─ Brüt-net kontrol          ├─ Bordroyu kapat
   │  puantaj import            ├─ Sapma raporu incele        ├─ PDF pusulalar üret
   ├─ İzin modülünden          ├─ Manuel düzeltme             ├─ Banka dosyası oluştur
   │  ücretsiz izin             │  (gerekirse)                ├─ Muhasebe export al
   ├─ Ek ödeme/prim            └─ Taslak onaya gönder        └─ Çalışanlara bildirim
   │  kalemleri işle                                              gönder
   └─ Devamsızlık etkisi
      kontrol et
```

**Hedef Süreler:**

| Adım | Hedef | Manuel / Geleneksel |
|------|-------|----------------------|
| Puantaj toplama | < 1 iş günü (otomatik import) | 3-5 iş günü |
| Bordro hesaplama çalıştırma | < 5 dakika (500 çalışan) | 2-3 iş günü (Excel) |
| Taslak kontrol | < 1 iş günü | 2 iş günü |
| Kapanış + çıktı üretme | < 30 dakika | Yarım gün |

### 2.3 Çalışan — Bordro Pusulası Görüntüleme Yolculuğu

```
BİLDİRİM               GÖRÜNTÜLEME              SORGULAMA
   │                       │                        │
   ▼                       ▼                        ▼
"Bordro pusulanız       Pusulayı aç:             Fark var mı?
hazır" bildirimi        ├─ Brüt maaş              ├─ Geçmiş ayla kıyas
   │                    ├─ Kesintiler              ├─ PDF indir
   ▼                    ├─ Net ücret               └─ İK'ya soru
Self-servis →           ├─ Fazla mesai                 (destek talebi)
Belgelerim →            └─ Ek ödemeler
Bordro kartı
```

### 2.4 Finans — Ödeme ve Maliyet Kontrol Yolculuğu

```
ONAYBEKLİYOR            KONTROL                  ÖDEME
   │                       │                        │
   ▼                       ▼                        ▼
Bordro taslağı          Toplam tutarı             Banka ödeme dosyasını
İK'dan onay geldi       bütçeyle karşılaştır      indir
   │                       │                        │
   ▼                    ├─ Departman kırılımı     ├─ IBAN kontrolü
Toplam maliyet          ├─ Geçen ayla fark       ├─ Bankaya yükle
raporu incele           └─ Onay ver               └─ Mutabakat

---

## 3. Fonksiyonel Gereksinimler

### 3.1 Ücret Yapısı ve Maaş Bileşenleri

#### FR-BRD-01: Ücret Modeli Tanımlama

**Açıklama:** Çalışan bazında aylık, günlük, saatlik veya vardiya tabanlı ücret modeli tanımlanabilmeli.

**Ücret Modelleri:**

| Model | Açıklama | Hesaplama Temeli |
|-------|----------|-----------------|
| `monthly` | Aylık sabit maaş | Brüt aylık tutar |
| `daily` | Günlük ücret | Brüt günlük × çalışılan gün |
| `hourly` | Saatlik ücret | Brüt saatlik × çalışılan saat |
| `shift_based` | Vardiya bazlı | Vardiya ücreti × vardiya sayısı |

#### FR-BRD-02: Kazanç/Kesinti Bileşenleri

**Açıklama:** Sabit kazanç, değişken kazanç, yan hak ve kesinti kalemleri tenant bazında tanımlanabilmeli.

**Varsayılan Bileşen Tipleri:**

| Kod | Bileşen | Tip | SGK Matrahı | Vergi Matrahı |
|-----|---------|-----|-------------|---------------|
| `base_salary` | Temel maaş | Sabit kazanç | Evet | Evet |
| `overtime_pay` | Fazla mesai ücreti | Değişken kazanç | Evet | Evet |
| `holiday_overtime` | Tatil mesai ücreti | Değişken kazanç | Evet | Evet |
| `night_shift_diff` | Gece vardiya farkı | Değişken kazanç | Evet | Evet |
| `bonus` | Prim / ikramiye | Tek seferlik | Evet | Evet |
| `food_allowance` | Yemek yardımı | Yan hak | Kısmi (limit üzeri) | Kısmi |
| `transport_allowance` | Ulaşım yardımı | Yan hak | Kısmi (limit üzeri) | Kısmi |
| `child_allowance` | Çocuk yardımı | Yan hak | Hayır (limit dahili) | Hayır |
| `sgk_employee` | SGK işçi payı | Yasal kesinti | — | — |
| `unemployment_employee` | İşsizlik sigortası işçi payı | Yasal kesinti | — | — |
| `income_tax` | Gelir vergisi | Yasal kesinti | — | — |
| `stamp_tax` | Damga vergisi | Yasal kesinti | — | — |
| `union_fee` | Sendika aidatı | Diğer kesinti | Hayır | Evet (matrahtan indirilir) |
| `advance_deduction` | Avans kesintisi | Diğer kesinti | Hayır | Hayır |
| `execution_deduction` | İcra kesintisi | Diğer kesinti | Hayır | Hayır |

#### FR-BRD-03: Bileşen Konfigürasyonu

| Özellik | Açıklama |
|---------|----------|
| SGK matrahına dahil mi | Bileşen SGK matrahını artırır mı |
| Gelir vergisi matrahına dahil mi | Bileşen kümülatif vergi matrahına girer mi |
| İstisna limiti | Yemek/yol gibi kalemlerde aylık istisna tutarı (tenant ayarı) |
| Tekrar tipi | Sabit (her ay), tek seferlik, dönemsel |
| Hesaplama formülü | Sabit tutar, yüzde, saat × birim fiyat |

### 3.2 Bordro Hesaplama Motoru

#### FR-BRD-04: Brüt-Net Hesaplama Formülleri

**Ana Hesaplama Akışı:**

```
Brüt Ücret (aylık + ek kazançlar)
    │
    ├─ (−) SGK İşçi Payı    = SGK Matrahı × %14
    ├─ (−) İşsizlik İşçi    = SGK Matrahı × %1
    │       ─────────────────────────────────────
    │       Gelir Vergisi Matrahı = Brüt − SGK İşçi − İşsizlik İşçi
    │
    ├─ (−) Gelir Vergisi     = Kümülatif matrah dilimine göre
    ├─ (−) Damga Vergisi     = Brüt × ‰7,59
    │       ─────────────────────────────────────
    │       Net Ücret = Brüt − Toplam Kesinti
    │
    └─ İşveren Maliyeti:
        ├─ (+) SGK İşveren Payı  = SGK Matrahı × %15,5 (5 puan indirimli: %20,5 − %5)
        ├─ (+) İşsizlik İşveren  = SGK Matrahı × %2
        └─ Toplam İşveren Maliyeti = Brüt + SGK İşveren + İşsizlik İşveren
```

**Gelir Vergisi Dilimleri (2026 — snapshot olarak saklanır):**

| Dilim | Matrah Aralığı (TL) | Oran |
|-------|---------------------|------|
| 1. dilim | 0 – 110.000 | %15 |
| 2. dilim | 110.001 – 230.000 | %20 |
| 3. dilim | 230.001 – 580.000 | %27 |
| 4. dilim | 580.001 – 3.000.000 | %35 |
| 5. dilim | 3.000.001 + | %40 |

> **Not:** Dilim değerleri her yıl değişir. Sistem `payroll_tax_parameters` tablosundan dönem snapshot'ını okur.

**Kümülatif Vergi Hesaplama Algoritması:**

```
kümülatif_matrah_önceki = SUM(gelir_vergisi_matrahı) önceki aylar
kümülatif_matrah_bu_ay  = kümülatif_matrah_önceki + bu_ay_matrah

bu_ay_vergi = vergi_hesapla(kümülatif_matrah_bu_ay) − vergi_hesapla(kümülatif_matrah_önceki)

vergi_hesapla(matrah):
    vergi = 0
    for dilim in dilimler:
        if matrah <= dilim.alt_sınır:
            break
        vergilendirilebilir = min(matrah, dilim.üst_sınır) − dilim.alt_sınır
        vergi += vergilendirilebilir × dilim.oran
    return vergi
```

**SGK Tavan ve Taban Kontrolü:**

| Parametre | Değer (2026 — örnek) | Açıklama |
|-----------|----------------------|----------|
| SGK Taban | Brüt asgari ücret | Aylık SGK priminin hesaplandığı minimum matrah |
| SGK Tavan | Brüt asgari ücret × 7,5 | SGK prim kesintisinin üst limiti |
| Asgari ücret (brüt) | Mevzuat parametresinden okunur | Yıllık güncellenir |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-BRD-06 | SGK matrahı taban altına düşemez; ücretsiz izin günü düşüldükten sonra bile taban kontrol edilir |
| IK-BRD-07 | SGK matrahı tavanı aşarsa prim tavandan kesilir |
| IK-BRD-08 | Kümülatif vergi matrahı dönem başından itibaren hesaplanır; çalışanın işe giriş ayı baz alınır |
| IK-BRD-09 | Asgari geçim indirimi (AGİ) kaldırılmış olup; güncel mevzuata göre asgari ücret istisnası uygulanır |
| IK-BRD-10 | Engelli çalışanlarda vergi indirimi derecesine göre uygulanır |

#### FR-BRD-05: Ücretsiz İzin ve Devamsızlık Etkisi

**Gün Eksiltme Hesaplama:**

```
Çalışılan gün sayısı = Aydaki iş günü − ücretsiz izin günleri − mazeretsiz devamsızlık günleri
Orantılı brüt = (Brüt aylık / Aydaki iş günü) × Çalışılan gün sayısı
```

**Raporlu (SGK) Hastalık İzni:**

```
SGK ödemeli günler → Brütden düşülür
İlk 2 gün SGK ödemez → İşveren politikasına göre ücretli veya ücretsiz (tenant ayarı)
3. günden itibaren → SGK geçici iş göremezlik ödeneği (bordro dışı)
```

#### FR-BRD-06: Fazla Mesai Hesaplama

**Mesai Katsayıları (4857 İş Kanunu Md. 41-47):**

| Mesai Türü | Katsayı | Açıklama |
|------------|---------|----------|
| Normal fazla mesai | ×1,5 | Haftalık 45 saat üzeri |
| Hafta sonu mesaisi | ×1,5 | Cumartesi çalışması (firma politikasına göre) |
| Ulusal bayram / genel tatil | ×2,0 | Resmi tatil günü çalışması |
| Gece vardiya farkı | +%10 | 20:00 – 06:00 arası çalışma |

**Hesaplama:**

```
Saatlik brüt = Aylık brüt / 225 (aylık çalışma saati: 7,5 saat × 30 gün)
Fazla mesai ücreti = Saatlik brüt × katsayı × mesai saati
```

#### FR-BRD-07: Prim ve İkramiye İşleme

| Tip | Açıklama | SGK/Vergi |
|-----|----------|-----------|
| Performans primi | Performans modülünden referans | SGK + Vergi matrahına dahil |
| Satış primi | Değişken kazanç | SGK + Vergi matrahına dahil |
| Bayram ikramiyesi | Tek seferlik ödeme | SGK + Vergi matrahına dahil |
| Kıdem tazminatı | İşten ayrılışta | Gelir vergisinden istisna, damga vergisine tabi |

### 3.3 Kapanış ve Onay Akışı

#### FR-BRD-08: Bordro Durum Makinesi

```
draft ──────▶ calculated ──────▶ approved ──────▶ closed
  │               │                  │               │
  │               │                  │               └── revision ──▶ draft
  │               │                  └── rejected ──▶ draft
  │               └── error ──▶ draft (düzeltme sonrası)
  └── İlk oluşturulma
```

**Durum Geçiş Kuralları:**

| Geçiş | Koşul | Yetki |
|--------|-------|-------|
| draft → calculated | Hesaplama job'ı başarıyla tamamlandı | `payroll:calculate` |
| calculated → approved | İK onay verdi | `payroll:approve` |
| approved → closed | Finans onayı ve kapanış | `payroll:close` |
| closed → revision | Revizyon açma (gerekçe zorunlu) | `payroll:revise` |
| revision → draft | Revizyon düzeltmeleri yapıldı | `payroll:update` |

#### FR-BRD-09: Revizyon Akışı

| Kural | Açıklama |
|-------|----------|
| IK-BRD-11 | Revizyon açıldığında önceki kapanış snapshot'ı korunur |
| IK-BRD-12 | Revizyon gerekçesi zorunludur ve audit log'a yazılır |
| IK-BRD-13 | Revizyon yalnızca bir önceki dönem için açılabilir; daha eski dönemler kilitlidir |
| IK-BRD-14 | Revizyon sırasında eski ve yeni tutarlar karşılaştırmalı gösterilir |

### 3.4 Çıktılar ve Entegrasyon

#### FR-BRD-11: PDF Bordro Pusulası

**Pusulada Yer Alacak Bilgiler:**

| Bölüm | İçerik |
|-------|--------|
| Başlık | Şirket adı, dönem, çalışan adı, sicil no |
| Kazançlar | Temel maaş, fazla mesai, prim, yan haklar (kalem kalem) |
| Kesintiler | SGK işçi, işsizlik işçi, gelir vergisi, damga vergisi, diğer |
| Özet | Brüt toplam, toplam kesinti, net ücret |
| Kümülatif | Yılbaşından itibaren kümülatif brüt ve vergi matrahı |

#### FR-BRD-12: Banka Ödeme Dosyası

**Desteklenen Formatlar:**

| Format | Banka | Açıklama |
|--------|-------|----------|
| EFT/Havale XML | Genel | Standart banka EFT formatı |
| Özel banka formatı | Tenant ayarına göre | Banka spesifik CSV/TXT |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-BRD-15 | IBAN doğrulaması geçmeyen çalışan ödeme dosyasına dahil edilmez; uyarı listesine eklenir |
| IK-BRD-16 | Banka dosyası yalnızca `closed` statüsündeki bordrolardan üretilir |
| IK-BRD-17 | Her banka export dosyası hash ile imzalanır ve MinIO'da saklanır |

### 3.5 Genel İş Kuralları

| Kural | Açıklama |
|-------|----------|
| IK-BRD-01 | Aynı çalışan için aynı bordro döneminde tek aktif bordro kaydı olabilir |
| IK-BRD-02 | Kapanmış bordro doğrudan silinemez |
| IK-BRD-03 | Hesaplamada kullanılan mevzuat parametreleri dönem snapshot'ı olarak saklanır |
| IK-BRD-04 | Negatif net ücret oluşursa sistem hata veya manuel inceleme uyarısı üretir |
| IK-BRD-05 | Banka IBAN doğrulaması geçmeyen çalışan ödeme dosyasına dahil edilmez |

---

## 4. Veritabanı Tasarımı

### 4.1 Tablo İlişkisi

```
payroll_periods ────────── payroll_runs
        │                       │
        └── payroll_items ──────┘
                │
                ├── payroll_item_components
                │
                └── payroll_adjustments

payroll_bank_exports ──── payroll_periods
payroll_tax_parameters (mevzuat snapshot)
payroll_component_definitions (tenant bazlı bileşen tanımları)
```

### 4.2 Tablo Detayları

#### `payroll_periods` — Bordro Dönemleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `year` | SMALLINT | Bordro yılı |
| `month` | SMALLINT | Bordro ayı (1-12) |
| `status` | VARCHAR(20) | `draft`, `calculated`, `approved`, `closed`, `revision` |
| `work_days` | SMALLINT | Aydaki iş günü sayısı |
| `closed_at` | TIMESTAMPTZ, nullable | Kapanış zamanı |
| `closed_by` | BIGINT, FK, nullable | Kapanışı yapan kullanıcı |
| `revision_reason` | TEXT, nullable | Revizyon gerekçesi |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `payroll_runs` — Hesaplama Çalıştırmaları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `period_id` | BIGINT, FK | |
| `run_number` | SMALLINT | Kaçıncı hesaplama (revizyon sayacı) |
| `status` | VARCHAR(20) | `running`, `completed`, `failed` |
| `total_employees` | INTEGER | Hesaplanan çalışan sayısı |
| `total_gross` | NUMERIC(15,2) | Toplam brüt |
| `total_net` | NUMERIC(15,2) | Toplam net |
| `total_employer_cost` | NUMERIC(15,2) | Toplam işveren maliyeti |
| `error_count` | INTEGER, default: 0 | Hatalı hesaplama sayısı |
| `started_at` | TIMESTAMPTZ | |
| `completed_at` | TIMESTAMPTZ, nullable | |
| `created_by` | BIGINT, FK | |

#### `payroll_items` — Çalışan Bazlı Bordro Satırları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `period_id` | BIGINT, FK | |
| `run_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `wage_type` | VARCHAR(20) | `monthly`, `daily`, `hourly`, `shift_based` |
| `work_days` | NUMERIC(5,1) | Çalışılan gün |
| `unpaid_leave_days` | NUMERIC(5,1) | Ücretsiz izin günleri |
| `absence_days` | NUMERIC(5,1) | Devamsızlık günleri |
| `overtime_hours` | NUMERIC(6,1) | Fazla mesai saati |
| `gross_amount` | NUMERIC(12,2) | Brüt ücret |
| `sgk_employee` | NUMERIC(12,2) | SGK işçi payı |
| `unemployment_employee` | NUMERIC(12,2) | İşsizlik işçi payı |
| `income_tax_base` | NUMERIC(12,2) | Gelir vergisi matrahı |
| `cumulative_tax_base` | NUMERIC(15,2) | Kümülatif vergi matrahı |
| `income_tax` | NUMERIC(12,2) | Gelir vergisi |
| `stamp_tax` | NUMERIC(12,2) | Damga vergisi |
| `min_wage_exemption` | NUMERIC(12,2) | Asgari ücret istisnası |
| `other_deductions` | NUMERIC(12,2) | Diğer kesintiler toplamı |
| `total_deductions` | NUMERIC(12,2) | Toplam kesinti |
| `net_amount` | NUMERIC(12,2) | Net ücret |
| `sgk_employer` | NUMERIC(12,2) | SGK işveren payı |
| `unemployment_employer` | NUMERIC(12,2) | İşsizlik işveren payı |
| `total_employer_cost` | NUMERIC(15,2) | Toplam işveren maliyeti |
| `status` | VARCHAR(20) | `draft`, `approved`, `closed`, `error` |
| `error_message` | TEXT, nullable | Hesaplama hatası açıklaması |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `payroll_item_components` — Kazanç/Kesinti Kalemleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `payroll_item_id` | BIGINT, FK | |
| `component_code` | VARCHAR(50) | `base_salary`, `overtime_pay`, `sgk_employee` vb. |
| `component_type` | VARCHAR(20) | `earning`, `deduction`, `employer_cost` |
| `description` | VARCHAR(200) | Bileşen açıklaması |
| `amount` | NUMERIC(12,2) | Tutar (kazanç: pozitif, kesinti: negatif) |
| `quantity` | NUMERIC(8,2), nullable | Saat, gün, adet |
| `rate` | NUMERIC(12,4), nullable | Birim fiyat veya oran |
| `is_sgk_base` | BOOLEAN | SGK matrahına dahil mi |
| `is_tax_base` | BOOLEAN | Vergi matrahına dahil mi |

#### `payroll_adjustments` — Manuel Düzeltmeler

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `payroll_item_id` | BIGINT, FK | |
| `field_name` | VARCHAR(50) | Düzeltilen alan |
| `old_value` | NUMERIC(12,2) | Önceki değer |
| `new_value` | NUMERIC(12,2) | Yeni değer |
| `reason` | TEXT | Düzeltme gerekçesi |
| `created_by` | BIGINT, FK | |
| `created_at` | TIMESTAMPTZ | |

#### `payroll_tax_parameters` — Mevzuat Parametre Snapshot'ları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `year` | SMALLINT | Geçerli yıl |
| `half` | SMALLINT | 1 veya 2 (yarı yıl) |
| `min_wage_gross` | NUMERIC(12,2) | Brüt asgari ücret |
| `sgk_employee_rate` | NUMERIC(5,4) | SGK işçi oranı |
| `sgk_employer_rate` | NUMERIC(5,4) | SGK işveren oranı |
| `sgk_employer_discount` | NUMERIC(5,4) | 5 puan teşvik indirimi |
| `unemployment_employee_rate` | NUMERIC(5,4) | İşsizlik işçi oranı |
| `unemployment_employer_rate` | NUMERIC(5,4) | İşsizlik işveren oranı |
| `sgk_ceiling_multiplier` | NUMERIC(4,2) | SGK tavan çarpanı (7,5) |
| `stamp_tax_rate` | NUMERIC(8,6) | Damga vergisi oranı |
| `tax_brackets` | JSONB | Gelir vergisi dilimleri |
| `food_exemption_daily` | NUMERIC(8,2) | Günlük yemek istisnası |
| `transport_exemption_monthly` | NUMERIC(8,2) | Aylık ulaşım istisnası |
| `is_active` | BOOLEAN | |
| `created_by` | BIGINT, FK | |
| `created_at` | TIMESTAMPTZ | |

#### `payroll_bank_exports` — Banka Ödeme Dosyaları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `period_id` | BIGINT, FK | |
| `file_name` | VARCHAR(255) | Dosya adı |
| `file_url` | TEXT | MinIO signed URL |
| `file_hash` | VARCHAR(64) | SHA-256 hash |
| `total_amount` | NUMERIC(15,2) | Toplam ödeme tutarı |
| `employee_count` | INTEGER | Dahil edilen çalışan sayısı |
| `excluded_count` | INTEGER | IBAN hatası nedeniyle çıkarılan |
| `format` | VARCHAR(30) | `eft_xml`, `bank_csv`, `custom` |
| `created_by` | BIGINT, FK | |
| `created_at` | TIMESTAMPTZ | |

### 4.3 İndeksler

```sql
CREATE INDEX ix_payroll_items_period_employee ON payroll_items (tenant_id, period_id, employee_id);
CREATE INDEX ix_payroll_items_status ON payroll_items (tenant_id, status);
CREATE INDEX ix_payroll_runs_period_status ON payroll_runs (tenant_id, period_id, status);
CREATE INDEX ix_payroll_components_item ON payroll_item_components (payroll_item_id);
CREATE INDEX ix_payroll_tax_params_active ON payroll_tax_parameters (tenant_id, year, half) WHERE is_active = true;
CREATE INDEX ix_payroll_adjustments_item ON payroll_adjustments (payroll_item_id);
CREATE UNIQUE INDEX uq_payroll_items_period_emp ON payroll_items (tenant_id, period_id, employee_id) WHERE status != 'error';
```

---

## 5. API Endpoint Detayları

Tüm bordro endpoint'leri `/api/v1/payroll` prefix'i altındadır.

### 5.1 Dönem Yönetimi

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/payroll/periods` | Bordro dönemleri listesi | `payroll:read` |
| `POST` | `/payroll/periods` | Yeni dönem oluştur | `payroll:create` |
| `GET` | `/payroll/periods/{id}` | Dönem detayı | `payroll:read` |
| `POST` | `/payroll/periods/{id}/calculate` | Bordro hesapla (async job) | `payroll:calculate` |
| `POST` | `/payroll/periods/{id}/approve` | Bordroyu onayla | `payroll:approve` |
| `POST` | `/payroll/periods/{id}/close` | Bordro kapat | `payroll:close` |
| `POST` | `/payroll/periods/{id}/revise` | Revizyon aç (gerekçe zorunlu) | `payroll:revise` |

### 5.2 Bordro Kalemleri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/payroll/periods/{id}/items` | Dönemdeki tüm bordro satırları | `payroll:read` |
| `GET` | `/payroll/items/{id}` | Tek çalışan bordro detayı | `payroll:read` |
| `GET` | `/payroll/items/{id}/components` | Kazanç/kesinti kalemleri | `payroll:read` |
| `PATCH` | `/payroll/items/{id}` | Manuel düzeltme (gerekçe zorunlu) | `payroll:update` |
| `GET` | `/payroll/items/{id}/adjustments` | Düzeltme geçmişi | `payroll:read` |

### 5.3 Çıktılar

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/payroll/periods/{id}/generate-slips` | PDF pusulalar üret (async) | `payroll:export` |
| `POST` | `/payroll/periods/{id}/bank-export` | Banka dosyası oluştur | `payroll:export` |
| `GET` | `/payroll/bank-exports/{id}/download` | Banka dosyasını indir | `payroll:export` |
| `POST` | `/payroll/periods/{id}/accounting-export` | Muhasebe export | `payroll:export` |

### 5.4 Raporlama

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/payroll/reports/cost-summary` | Toplam maliyet raporu | `payroll:report:read` |
| `GET` | `/payroll/reports/comparison` | Dönem karşılaştırma | `payroll:report:read` |
| `GET` | `/payroll/reports/deduction-breakdown` | Kesinti dağılımı | `payroll:report:read` |
| `GET` | `/payroll/reports/overtime-cost` | Fazla mesai maliyet raporu | `payroll:report:read` |

### 5.5 Mevzuat Parametreleri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/payroll/tax-parameters` | Aktif parametre seti | `payroll:config:read` |
| `POST` | `/payroll/tax-parameters` | Yeni parametre yılı/dönemi ekle | `payroll:config:create` |
| `PATCH` | `/payroll/tax-parameters/{id}` | Parametre güncelle | `payroll:config:update` |

### 5.6 Self-Servis Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/payroll/slips` | Kendi bordrolarım (lista) | Auth |
| `GET` | `/me/payroll/slips/{period_id}` | Belirli dönem pusulası | Auth |
| `GET` | `/me/payroll/slips/{period_id}/pdf` | PDF indir | Auth |

### 5.7 Örnek Request / Response

#### POST `/api/v1/payroll/periods/{id}/calculate`

**Request Body:**

```json
{
  "employee_scope": "all",
  "include_overtime": true,
  "include_adjustments": true
}
```

**Response (202 Accepted):**

```json
{
  "success": true,
  "data": {
    "run_id": 45,
    "period_id": 12,
    "status": "running",
    "total_employees": 247,
    "started_at": "2026-04-25T14:30:00Z",
    "message": "Bordro hesaplama başlatıldı."
  }
}
```

#### GET `/api/v1/me/payroll/slips/12`

**Response (200 OK):**

```json
{
  "success": true,
  "data": {
    "period": { "year": 2026, "month": 3, "label": "Mart 2026" },
    "employee": { "id": 451, "name": "Zeynep Kaya", "title": "İK Uzmanı" },
    "earnings": [
      { "code": "base_salary", "description": "Temel Maaş", "amount": 35000.00 },
      { "code": "food_allowance", "description": "Yemek Yardımı", "amount": 1500.00 },
      { "code": "overtime_pay", "description": "Fazla Mesai (12 saat)", "amount": 2800.00 }
    ],
    "deductions": [
      { "code": "sgk_employee", "description": "SGK İşçi Payı (%14)", "amount": -5383.00 },
      { "code": "unemployment_employee", "description": "İşsizlik Sigortası (%1)", "amount": -384.50 },
      { "code": "income_tax", "description": "Gelir Vergisi", "amount": -4684.88 },
      { "code": "stamp_tax", "description": "Damga Vergisi", "amount": -298.33 }
    ],
    "summary": {
      "gross_amount": 39300.00,
      "total_deductions": 10750.71,
      "net_amount": 28549.29,
      "cumulative_tax_base": 103425.00
    },
    "pdf_url": "/api/v1/me/payroll/slips/12/pdf"
  }
}
```

**Olası Hata Kodları:**

| HTTP | Kod | Açıklama |
|------|-----|----------|
| 400 | `VALIDATION_ERROR` | Eksik veya geçersiz parametre |
| 409 | `PERIOD_ALREADY_CALCULATED` | Dönem zaten hesaplanmış |
| 409 | `PERIOD_NOT_CLOSEABLE` | Hesaplanmamış veya onaysız bordro kapatılamaz |
| 422 | `NEGATIVE_NET_AMOUNT` | Negatif net ücret oluştu (manuel inceleme gerekli) |
| 422 | `MISSING_TAX_PARAMETERS` | Dönem için mevzuat parametresi tanımlı değil |
| 422 | `MISSING_IBAN` | Çalışanın IBAN bilgisi eksik |
| 404 | `PAYROLL_PERIOD_NOT_FOUND` | Dönem bulunamadı |

---

## 6. Ekranlar ve Raporlar

### 6.1 Ekran Listesi

| # | Ekran | Platform | Rol | Öncelik |
|---|-------|----------|-----|---------|
| 1 | Bordro dönem listesi | Web | İK, Bordro | Must |
| 2 | Taslak bordro inceleme (tablo) | Web | İK, Bordro | Must |
| 3 | Bordro detay kartı (çalışan bazlı) | Web | İK, Bordro | Must |
| 4 | Çalışan bordro pusulası | Web + Mobil | Çalışan | Must |
| 5 | Banka ödeme export ekranı | Web | Finans | Must |
| 6 | Maliyet dashboard | Web | İK, Finans, C-Level | Must |
| 7 | Mevzuat parametre yönetimi | Web | Süper Admin | Must |
| 8 | Sapma ve uyarı ekranı | Web | Bordro | Should |
| 9 | Dönem karşılaştırma | Web | İK, Finans | Should |

### 6.2 Bordro Dönem İnceleme Ekranı

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◀ Bordro / Mart 2026                       Durum: Taslak            │
├──────────────────────────────────────────────────────────────────────┤
│ Özet: 247 çalışan · Toplam Brüt: 8.925.300 ₺ · Net: 6.148.200 ₺   │
│       İşveren Maliyeti: 10.650.800 ₺ · Hata: 2 çalışan             │
│                                                                      │
│ ┌─────────┬───────────┬──────────┬──────────┬──────────┬──────────┐ │
│ │ Çalışan │ Brüt      │ SGK+İşsz │ Gelir V. │ Net      │ Durum   │ │
│ ├─────────┼───────────┼──────────┼──────────┼──────────┼──────────┤ │
│ │ Z.Kaya  │ 39.300    │ 5.767    │ 4.684    │ 28.549   │ ✅ OK    │ │
│ │ A.Demir │ 28.500    │ 4.182    │ 2.876    │ 21.144   │ ✅ OK    │ │
│ │ M.Çelik │ 45.200    │ 6.633    │ 6.120    │ 32.104   │ ⚠️ Sapma │ │
│ │ E.Yılmaz│ 22.000    │ 3.228    │ 1.350    │ ---      │ ❌ Hata  │ │
│ └─────────┴───────────┴──────────┴──────────┴──────────┴──────────┘ │
│                                                                      │
│ [Yeniden Hesapla] [Sapmaları Göster] [Onayla] [Excel Export]         │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.3 Çalışan Bordro Pusulası

```
┌──────────────────────────────────────────────┐
│  ABC Teknoloji A.Ş.                          │
│  BORDRO PUSULASI — Mart 2026                 │
│  ──────────────────────────────              │
│  Zeynep Kaya · İK Uzmanı · Sicil: 1042      │
│                                              │
│  KAZANÇLAR                                   │
│  Temel Maaş .................. 35.000,00 ₺   │
│  Yemek Yardımı ...............  1.500,00 ₺   │
│  Fazla Mesai (12 sa) ........  2.800,00 ₺   │
│  ────────────────────────────                │
│  BRÜT TOPLAM ................. 39.300,00 ₺   │
│                                              │
│  KESİNTİLER                                  │
│  SGK İşçi Payı (%14) ........  5.383,00 ₺   │
│  İşsizlik Sig. (%1) .........    384,50 ₺   │
│  Gelir Vergisi ...............  4.684,88 ₺   │
│  Damga Vergisi ...............    298,33 ₺   │
│  ────────────────────────────                │
│  TOPLAM KESİNTİ ............. 10.750,71 ₺   │
│                                              │
│  NET ÜCRET ................... 28.549,29 ₺   │
│  ────────────────────────────                │
│  Küm. Vergi Matrahı: 103.425 ₺              │
│                                              │
│  [PDF İndir] [Geçmiş Aylar]                 │
└──────────────────────────────────────────────┘
```

### 6.4 Ana Raporlar

| # | Rapor | Açıklama | Filtreler | Format |
|---|-------|----------|-----------|--------|
| 1 | Bordro maliyet özeti | Departman/şirket bazında toplam brüt, net, işveren maliyeti | Dönem, departman, lokasyon | Grafik + tablo |
| 2 | Fazla mesai maliyet raporu | Fazla mesai kaynaklı ek maliyet | Dönem, departman | Tablo + Excel |
| 3 | Kesinti dağılım raporu | Vergi, SGK, diğer kesinti kırılımı | Dönem | Pasta grafik + tablo |
| 4 | Dönem karşılaştırma | Seçili iki dönemin fark analizi | Dönem 1, Dönem 2 | Tablo |
| 5 | Maliyet trend raporu | 12 aylık maliyet trendi | Yıl, departman | Çizgi grafik |
| 6 | Çalışan maliyet kartı | Birey bazında yıllık toplam maliyet | Çalışan | Kart + grafik |

### 6.5 Dashboard Kartları

| Kart | Formül |
|------|--------|
| Aylık toplam işveren maliyeti | `SUM(total_employer_cost) WHERE period = current` |
| Ortalama net ücret | `AVG(net_amount)` |
| Fazla mesai maliyet oranı | `SUM(overtime_pay) / SUM(gross_amount) × 100` |
| Dönemsel maliyet değişimi | `(Bu ay toplam − geçen ay toplam) / geçen ay toplam × 100` |
| SGK prim toplam | `SUM(sgk_employee + sgk_employer + unemployment_employee + unemployment_employer)` |

---

## 7. İş Akışları ve Otomasyon

### 7.1 Celery Beat Görevleri

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `remind_payroll_deadline` | Ayın 20'si, 09:00 | Bordro uzmanına "Puantaj toplama zamanı" hatırlatması |
| `check_missing_timesheet` | Ayın 22'si, 10:00 | Puantaj verisi eksik çalışanları listele ve uyar |
| `notify_payroll_calculated` | Hesaplama tamamlandığında | İK'ya "Taslak bordro hazır" bildirimi |
| `generate_payroll_slips_batch` | Kapanış sonrası | Tüm çalışanlar için PDF pusulalar üret (async batch) |
| `notify_payslip_ready` | PDF üretim tamamlandığında | Çalışanlara "Bordro pusulanız hazır" push/e-posta |
| `refresh_payroll_dashboards` | Günlük 03:00 | Maliyet özet cache'lerini yenile |

### 7.2 Bildirim Şablonları

| Şablon | Tetikleyici | Alıcı | İçerik |
|--------|-------------|-------|--------|
| `payroll_deadline_reminder` | Ayın 20'si | Bordro uzmanı | "Bordro hazırlık süreci başlıyor. Puantaj verilerini kontrol edin." |
| `payroll_draft_ready` | Hesaplama tamamlandı | İK Yöneticisi | "Mart 2026 bordro taslağı hazır. İnceleme ve onay bekleniyor." |
| `payroll_approved` | İK onayı verildi | Finans | "Mart 2026 bordrosu onaylandı. Banka ödeme dosyası hazırlanabilir." |
| `payroll_closed` | Kapanış yapıldı | İK, Finans | "Mart 2026 bordrosu kapatıldı." |
| `payslip_ready` | PDF üretildi | Çalışan | "Mart 2026 bordro pusulanız hazır. Self-servis portalından görüntüleyebilirsiniz." |
| `payroll_error` | Hesaplama hatası | Bordro uzmanı | "2 çalışanın bordro hesaplamasında hata oluştu. İnceleme gerekiyor." |
| `payroll_revision_opened` | Revizyon açıldı | İK, Finans | "Mart 2026 bordrosunda revizyon açıldı. Gerekçe: [gerekçe]" |

---

## 8. Güvenlik ve KVKK

### 8.1 Hassas Veri Sınıflandırması

| Veri | Hassasiyet | Saklama | Erişim Kontrolü |
|------|-----------|---------|-----------------|
| Maaş tutarları | Çok yüksek | Şifreli kolon (opsiyonel) | Bordro yetkisi + çalışan kendisi |
| SGK/vergi bilgileri | Yüksek | Düz metin (DB şifreli bağlantı) | Bordro yetkisi |
| IBAN bilgileri | Yüksek | Maskelenmiş gösterim | Bordro + Finans |
| PDF pusulalar | Yüksek | MinIO signed URL | Çalışan kendisi + İK |
| Banka ödeme dosyaları | Çok yüksek | MinIO + hash imza | Finans yetkisi |

### 8.2 KVKK Gereksinimleri

| Gereksinim | Uygulama |
|------------|----------|
| Amaçla sınırlılık | Bordro verisi yalnızca ücret hesaplama ve yasal raporlama amacıyla işlenir |
| Saklama süresi | Bordro kayıtları 10 yıl boyunca arşivlenir (İş Kanunu + SGK mevzuatı) |
| Erişim kaydı | Bordro detay görüntüleme ve export aksiyonları audit log'a yazılır |
| Veri minimizasyonu | Çalışan self-servis'te yalnızca kendi pusula bilgisini görür |
| Export güvenliği | Toplu bordro ve banka dosyası export'ları imzalı URL + kullanıcı bilgisiyle loglanır |

### 8.3 Rol Bazlı Erişim Matrisi

| İzin | Süper Admin | İK Yöneticisi | Bordro Uzmanı | Finans | Dept. Yöneticisi | Çalışan |
|------|------------|--------------|--------------|--------|-----------------|---------|
| `payroll:read` | ✅ | ✅ | ✅ | ✅ (özet) | ❌ | ❌ |
| `payroll:create` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `payroll:calculate` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `payroll:update` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `payroll:approve` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `payroll:close` | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| `payroll:revise` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `payroll:export` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `payroll:config:*` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Kendi pusulası | — | — | — | — | — | ✅ |

---

## 9. Modüller Arası Bağımlılıklar

### 9.1 Bordro Modülünün Sunduğu Servisler

```python
class PayrollService:
    """Diğer modüllerin kullandığı bordro servisleri."""

    async def get_employee_last_net(self, employee_id: int) -> Decimal | None
    """Son kapanmış dönemdeki net ücreti döner."""

    async def get_period_cost_summary(self, period_id: int) -> dict
    """Raporlama modülü için dönem maliyet özetini üretir."""

    async def get_employee_annual_cost(self, employee_id: int, year: int) -> Decimal
    """Yıllık toplam işveren maliyetini döner."""

    async def is_period_closed(self, period_id: int) -> bool
    """Entegrasyon modülü için dönem kapanış kontrolü."""
```

### 9.2 Bordro Modülünün Kullandığı Servisler

| Modül | Servis | Kullanım |
|-------|--------|----------|
| **Personnel** | `PersonnelService.get_employee_payroll_data()` | Ücret tipi, brüt maaş, medeni hal, SGK no, IBAN, engelli derecesi |
| **Leave** | `LeaveService.get_unpaid_leave_days()` | Dönemdeki ücretsiz izin günleri |
| **Leave** | `LeaveService.get_sick_leave_days()` | Raporlu hastalık günleri |
| **Shift** | `ShiftService.get_overtime_summary()` | Onaylı fazla mesai saat dökümü |
| **Shift** | `ShiftService.get_timesheet_summary()` | Puantaj (çalışılan gün/saat) |
| **Performance** | `PerformanceService.get_bonus_eligible()` | Prim hak eden çalışan listesi (referans) |
| **Notification** | `NotificationService.send()` | Tüm bildirimler |
| **Integration** | `IntegrationService.export_bank_file()` | Banka format adaptörü |

### 9.3 Bağımlılık Diyagramı

```
┌──────────────┐  ┌──────────┐  ┌──────────┐
│  Personel    │  │   İzin   │  │ Vardiya  │
│  Modülü      │  │  Modülü  │  │  Modülü  │
└──────┬───────┘  └────┬─────┘  └────┬─────┘
       │               │             │
       └───────────────┼─────────────┘
                       │
                ┌──────┴────────┐
                │    Bordro     │
                │   Modülü      │
                └──────┬────────┘
                       │
           ┌───────────┼───────────┐
           │           │           │
     ┌─────┴────┐ ┌────┴─────┐ ┌──┴──────────┐
     │Performans│ │Bildirim  │ │Entegrasyon  │
     │(referans)│ │  Modülü  │ │  Modülü     │
     └──────────┘ └──────────┘ └─────────────┘
```

---

## 10. Performans Gereksinimleri

| Senaryo | Hedef | Yöntem |
|---------|-------|--------|
| Bordro hesaplama (500 çalışan) | < 5 dakika | Bulk insert + paralel batch hesaplama |
| Tek çalışan pusulası görüntüleme | < 200ms | İndeksli sorgu |
| Bordro dönem listesi | < 150ms | Sayfalama + cache |
| PDF pusulası üretme (500 adet) | < 10 dakika | Async Celery worker, paralel PDF üretimi |
| Banka export dosyası üretme | < 30 saniye | Tek batch sorgu + dosya üretimi |
| Maliyet dashboard | < 2 saniye | Pre-aggregation + Redis cache |

---

## 11. Test Senaryoları

### 11.1 Birim Test

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Standart aylık maaş brüt-net hesaplama | Tüm kesintiler doğru, net tutarı doğru |
| 2 | SGK tavan aşımı | Prim tavandan kesilir |
| 3 | Kümülatif vergi dilimi geçişi | İkinci dilim oranı doğru uygulanır |
| 4 | Ücretsiz izinli ay (10 gün) | Orantılı brüt doğru hesaplanır |
| 5 | Fazla mesai (normal + tatil) | Katsayılar doğru uygulanır |
| 6 | Negatif net ücret | Hata üretilir, status `error` olur |
| 7 | Asgari ücret istisnası | İstisna tutarı doğru uygulanır |
| 8 | Engelli vergi indirimi | Derece bazlı indirim doğru |
| 9 | SGK taban kontrolü | Taban altına düşmez |

### 11.2 Entegrasyon Test

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | İzin modülü → ücretsiz izin verisi | Bordro gün eksiltmesine doğru yansır |
| 2 | Vardiya → fazla mesai verisi | Onaylı mesai saatleri bordroya aktarılır |
| 3 | Hesaplama → PDF üretimi | Tüm çalışanlar için pusulalar oluşur |
| 4 | Kapanış → banka export | Geçerli formatta dosya üretilir |
| 5 | Revizyon açma → yeniden hesaplama | Eski snapshot korunur, yeni hesaplama doğru |

### 11.3 E2E Test

| # | Test | Adımlar |
|---|------|---------|
| 1 | Tam bordro çevrimi | Puantaj → hesaplama → kontrol → onay → kapanış → export |
| 2 | Revizyon senaryosu | Kapalı bordro → revizyon aç → düzeltme → yeniden kapanış |
| 3 | Çalışan pusulası görüntüleme | Giriş → self-servis → bordro → PDF indir |

---

## 12. Kısıtlamalar ve Varsayımlar

| # | Varsayım / Kısıt | Not |
|---|------------------|-----|
| K1 | İlk sürüm yalnızca Türkiye mevzuatını destekler | Çok ülke desteği sonraki faz |
| K2 | Mevzuat parametreleri dönemsel olarak admin tarafından güncellenir | Otomatik mevzuat feed'i kapsam dışı |
| K3 | Muhasebe yevmiye entegrasyonu export düzeyindedir | Tam ERP entegrasyonu kapsam dışı |
| K4 | Banka mutabakatı otomatik değildir | Ödeme dosyası üretilir, mutabakat harici |
| V1 | Puantaj verisi vardiya modülünden veya manuel import ile gelir | Hibrit destek |
| V2 | SGK e-beyanname doğrudan gönderilmez; export dosyası üretilir | İlk sürüm |
| V3 | Bordro hesaplama saatler dışında çalıştırılması önerilir | Performans
