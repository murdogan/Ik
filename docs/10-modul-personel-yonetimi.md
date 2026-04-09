# 10 — Modül: Personel Yönetimi

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** Çalışan kayıtları, özlük dosyaları, iş sözleşmeleri, işe giriş/çıkış süreçleri, zimmet yönetimi, belge yönetimi, terfi/nakil  
> **Faz:** MVP (Faz 1) — Personel Yönetimi, İzin ve Self-Servis Portal ile birlikte ilk çıkışta yer alır  
> **Referans:** 04-gereksinim-analizi.md (FR-PER-01 – FR-PER-15), 06-sistem-mimarisi.md, 07-veritabani-tasarimi.md, 08-api-tasarimi.md

---

## 1. Modül Özeti

Personel Yönetimi modülü, İK Yönetim Sistemi'nin **temel taşıdır**. Çalışana ait tüm demografik, kurumsal ve yasal verilerin oluşturulması, güncellenmesi, saklanması ve raporlanmasından sorumludur. Diğer tüm modüller (İzin, Bordro, Performans, Vardiya, Eğitim) personel verisi üzerinden çalışır.

### 1.1 Modül Kapsamı

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| Çalışan kaydı oluşturma (CRUD) | Bordro hesaplama (14-modul-bordro-maas.md) |
| Özlük bilgileri yönetimi | İzin talep/onay akışı (12-modul-izin-devamsizlik.md) |
| İş sözleşmesi yönetimi | Performans değerlendirme (13-modul-performans-yonetimi.md) |
| Belge (doküman) yönetimi | Vardiya planlama (16-modul-vardiya-mesai.md) |
| İşe giriş süreci (onboarding) | İş ilanı ve aday takibi (11-modul-ise-alim-ats.md) |
| İşten çıkış süreci (offboarding) | Detaylı organizasyon şeması yönetimi (17-modul-organizasyon-semasi.md) |
| Terfi, nakil, görev değişikliği | Eğitim planları (15-modul-egitim-gelisim.md) |
| Zimmet yönetimi | — |
| Toplu veri içe/dışa aktarma | — |
| Çoklu şirket/şube desteği | — |
| Engelli çalışan takibi | — |
| Çalışan arama ve filtreleme | — |

### 1.2 MVP'deki Rolü

Personel Yönetimi, MVP'de **İzin Yönetimi** ve **Self-Servis Portal** ile birlikte ilk üç modülden biridir:

```
MVP Kapsamı:
┌────────────────────────────────────────────────┐
│  Personel Yönetimi  ←  Temel veri kaynağı      │
│  İzin Yönetimi      ←  Personel'e bağımlı      │
│  Self-Servis Portal ←  Personel'e bağımlı      │
│  Auth + Bildirim    ←  Altyapı modülleri        │
└────────────────────────────────────────────────┘
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|---------------|-------------------|-----------------|
| **Ayşe (İK Müdürü)** | Ana kullanıcı | Günlük 4-8 saat | Çalışan CRUD, sözleşme, onboarding, offboarding, raporlama |
| **Mehmet (Dept. Yöneticisi)** | Ekip verisi tüketici | Günlük 15-30 dk | Ekip listesi görüntüleme, organizasyon yapısı |
| **Zeynep (Çalışan)** | Self-servis kullanıcı | Haftalık 5-10 dk | Profil güncelleme, belge görüntüleme |
| **Hakan (Genel Müdür)** | Dashboard tüketici | Ayda 2-3 kez | Headcount raporu, departman dağılımı |
| **Emre (KOBİ Sahibi)** | Hem İK hem yönetici | Haftalık 30-60 dk | Çalışan ekleme, toplu import, genel bakış |

### 2.2 İK Uzmanı — Yeni Çalışan Ekleme Yolculuğu

```
HAZIRLIK              VERİ GİRİŞİ              TAKİP
   │                      │                       │
   ▼                      ▼                       ▼
İşe alım sürecinden  → Çalışan formunu doldur → Onboarding checklist
aday kabul edildi       │                         başlat
   │                    ├─ Kişisel bilgiler        │
   ▼                    ├─ İletişim bilgileri      ├─ IT: E-posta hesabı
Evrakları topla         ├─ Departman / Pozisyon    ├─ IT: Laptop teslimi
   │                    ├─ Maaş bilgisi            ├─ İK: SGK bildirimi
   ▼                    ├─ Sözleşme türü           ├─ İK: İmza evrakları
SGK işe giriş           └─ Banka hesabı            ├─ Yönetici: Tanışma
bildirimi hazırla                                   └─ Eğitim: Oryantasyon
   │                      │                       │
   ▼                      ▼                       ▼
Belgeler sisteme      → Kullanıcı hesabı       → Çalışan
yüklenir                otomatik oluşur          aktif durumda
```

**Hedef Süreler:**

| Adım | Hedef | Mevcut (Manuel) |
|------|-------|-----------------|
| Çalışan kaydı oluşturma | < 5 dakika | 30-60 dakika |
| Belge yükleme | < 2 dakika | 10-15 dakika (fotokopi + dosyalama) |
| Onboarding checklist başlatma | Otomatik | Yok (takip edilmiyor) |
| SGK giriş verisi hazırlama | Otomatik | 15-20 dakika |
| Toplu çalışan import (Excel) | < 3 dakika (100 çalışan) | 1-2 gün |

### 2.3 İK Uzmanı — İşten Çıkış Yolculuğu

```
KARAR                SÜREÇ                     KAPANIŞ
  │                    │                          │
  ▼                    ▼                          ▼
Çıkış kararı      → Offboarding checklist     → Çalışan durumu
alındı               başlat                      "terminated" olur
  │                    │                          │
  ▼                    ├─ Kıdem/ihbar hesabı      ├─ SGK çıkış bildirimi
Çıkış türü seçilir    ├─ Çıkış mülakatı          │  verisi üretilir
(istifa/fesih/        ├─ Zimmet iade kontrolü     │
 karşılıklı/emekli)   ├─ İzin bakiyesi kapatma   ├─ Kullanıcı hesabı
  │                    ├─ Son bordro hazırlığı    │  devre dışı olur
  ▼                    └─ Bilgi transferi         │
Gerekçe kaydedilir                                └─ Arşiv'e alınır
```

**Hedef Süreler:**

| Adım | Hedef | Mevcut (Manuel) |
|------|-------|-----------------|
| Kıdem/ihbar ön hesaplama | Otomatik (< 3 saniye) | 30-60 dakika (Excel) |
| SGK çıkış verisi üretimi | Otomatik | 15-20 dakika |
| Zimmet iade kontrolü | Dijital checklist (< 5 dakika) | Kağıt bazlı, 1 saat |
| Tüm offboarding süreci | < 30 dakika | 1-2 gün |

### 2.4 Çalışan — Self-Servis Profil Güncelleme Yolculuğu

```
İHTİYAÇ             EYLEM                    SONUÇ
  │                    │                        │
  ▼                    ▼                        ▼
Adres değişti    →  Mobil'den profili aç  →  Değişiklik kaydedildi
  │                    │                        │
  ▼                    ▼                        ▼
Acil durum       →  Güncelleme yap       →  İK'ya bildirim gitti
kişisi değişti       (kısıtlı alanlar)       (audit log oluştu)
```

**Çalışanın Güncelleyebileceği Alanlar:**

| Alan | Çalışan Güncelleyebilir | İK Onayı Gerekir |
|------|------------------------|-------------------|
| Telefon numarası | ✅ | Hayır |
| Adres | ✅ | Hayır |
| Acil durum kişisi | ✅ | Hayır |
| Kişisel e-posta | ✅ | Hayır |
| Profil fotoğrafı | ✅ | Hayır |
| Kan grubu | ✅ | Hayır |
| Medeni durum | ✅ | Evet (bordro etkisi — AGİ) |
| Banka hesabı (IBAN) | ✅ | Evet (güvenlik) |
| İsim değişikliği | ❌ | İK tarafından yapılır |
| Departman/Pozisyon | ❌ | İK tarafından yapılır |
| Maaş | ❌ | İK tarafından yapılır |

---

## 3. Fonksiyonel Gereksinimler — Detay

### 3.1 Çalışan Kaydı Yönetimi (CRUD)

#### FR-PER-01: Çalışan Kaydı Oluşturma

**Açıklama:** İK uzmanı, yeni çalışan kaydını tüm özlük bilgileriyle birlikte oluşturabilmelidir.

**Zorunlu Alanlar:**

| Alan Grubu | Alanlar | Not |
|------------|---------|-----|
| **Kimlik** | TC kimlik no, ad, soyad, doğum tarihi, cinsiyet | TC kimlik şifreli saklanır |
| **İletişim** | Telefon, iş e-postası | E-posta benzersiz (tenant içinde) |
| **Kurumsal** | Sicil no, departman, pozisyon, şube, yönetici | Sicil no benzersiz (tenant içinde) |
| **İstihdam** | İşe giriş tarihi, çalışma türü, sözleşme türü | |
| **Mali** | Brüt maaş, para birimi | Yetki kontrolü uygulanır |

**Opsiyonel Alanlar:**

| Alan Grubu | Alanlar |
|------------|---------|
| Kişisel | Medeni durum, uyruk, kan grubu, askerlik durumu, eğitim seviyesi |
| Adres | Adres, il, ilçe |
| Acil Durum | Acil durum kişisi adı, telefon, yakınlık derecesi |
| Mali | IBAN, SGK sicil no |
| Engelli | Engel durumu, engel oranı |
| Diğer | Profil fotoğrafı, notlar, ek metadata (JSONB) |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PER-01 | TC kimlik no 11 haneli olmalı ve Luhn algoritması ile doğrulanmalıdır |
| IK-PER-02 | Sicil numarası tenant içinde benzersiz olmalıdır |
| IK-PER-03 | İş e-postası tenant içinde benzersiz olmalıdır |
| IK-PER-04 | İşe giriş tarihi gelecek tarih olabilir (planlı işe alım), ancak 1 yıldan fazla ilerisi olamaz |
| IK-PER-05 | Brüt maaş 0'dan büyük olmalıdır |
| IK-PER-06 | Brüt maaş alanı yalnızca `personnel:salary:read` yetkisine sahip kullanıcılara gösterilir |
| IK-PER-07 | Çalışan oluşturulduğunda otomatik olarak `auth_users` tablosunda kullanıcı hesabı oluşturulur ve hoş geldin e-postası gönderilir |
| IK-PER-08 | Çalışan kaydı oluşturulduğunda tenant'ın `employee_limit` kotası kontrol edilir; aşıldıysa hata döner |
| IK-PER-09 | Çalışan durumu varsayılan olarak `active` atanır |
| IK-PER-10 | Tüm oluşturma işlemi tek transaction'da çalışır (çalışan + kullanıcı hesabı + ilk sözleşme) |

**Kabul Kriterleri:**

- [x] TC kimlik, ad, soyad, telefon, departman, pozisyon, işe giriş tarihi zorunlu girilebilmeli
- [x] Sicil no otomatik atanabilmeli veya manuel girilebilmeli
- [x] Kayıt sonrası otomatik kullanıcı hesabı oluşmalı
- [x] Hoş geldin e-postası arka planda (Celery) gönderilmeli
- [x] Çalışan kotası kontrol edilmeli
- [x] Audit log kaydı oluşmalı

---

#### FR-PER-02: Çalışan Profili Düzenleme

**Açıklama:** İK uzmanı tüm alanları, çalışan ise yalnızca kısıtlı alanları güncelleyebilmelidir.

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PER-11 | Çalışan kendi profilinde yalnızca izin verilen alanları güncelleyebilir (bkz. Bölüm 2.4 tablosu) |
| IK-PER-12 | Medeni durum ve IBAN değişikliği İK onayı gerektirir (bordro etkisi) |
| IK-PER-13 | Departman/pozisyon değişikliği yapıldığında `personnel_job_history` kaydı otomatik oluşmalıdır |
| IK-PER-14 | Maaş değişikliğinde eski ve yeni maaş `personnel_job_history` tablosuna yazılmalıdır |
| IK-PER-15 | Tüm alan değişiklikleri `audit_logs` tablosuna old_values / new_values ile kaydedilmelidir |

---

#### FR-PER-08: Çalışan Arama ve Filtreleme

**Açıklama:** İK uzmanı çalışan listesini çeşitli kriterlere göre filtreleyebilmeli, metin araması yapabilmelidir.

**Filtre Kriterleri:**

| Filtre | Parametre | Tip | Örnek |
|--------|-----------|-----|-------|
| Durum | `status` | Çoklu seçim | `active`, `on_leave`, `suspended`, `terminated` |
| Departman | `department_id` | Tekli / çoklu | `3` veya `3,5,7` |
| Pozisyon | `position_id` | Tekli / çoklu | `12` |
| Şube | `branch_id` | Tekli / çoklu | `1,2` |
| Çalışma türü | `employment_type` | Tekli / çoklu | `full_time`, `part_time`, `intern`, `contract` |
| Sözleşme türü | `contract_type` | Tekli / çoklu | `indefinite`, `fixed_term` |
| İşe giriş tarihi | `hire_date_from`, `hire_date_to` | Tarih aralığı | `2024-01-01` |
| Yönetici | `manager_id` | Tekli | `42` |
| Cinsiyet | `gender` | Tekli | `male`, `female` |
| Metin arama | `search` | Metin | `ahmet yılmaz` veya `S001` |

**Arama Davranışı:**

- `search` parametresi ad, soyad, sicil numarası ve iş e-postası üzerinde arama yapar
- PostgreSQL `pg_trgm` ile fuzzy matching desteklenir (yazım hataları tolere edilir)
- Full-text search vektörü ile Türkçe karakter desteği sağlanır
- Minimum 2 karakter girilmelidir

**Performans Hedefi:**

| Senaryo | Hedef |
|---------|-------|
| Filtrelenmiş liste (1.000 çalışan DB'de) | < 100ms |
| Metin arama (10.000 çalışan DB'de) | < 300ms |
| Sayfalı liste (100.000 çalışan DB'de) | < 200ms |

---

### 3.2 Belge Yönetimi

#### FR-PER-04: Dijital Belge Yönetimi

**Açıklama:** Çalışana ait belgeler (kimlik fotokopisi, diploma, sağlık raporu, sözleşme vb.) dijital ortamda saklanabilmelidir.

**Belge Türleri:**

| Kod | Belge Türü | Zorunlu mu | Geçerlilik Takibi |
|-----|-----------|------------|-------------------|
| `id_card` | Nüfus cüzdanı / kimlik kartı kopyası | Evet | Hayır |
| `diploma` | Diploma / mezuniyet belgesi | Hayır | Hayır |
| `health_report` | Sağlık raporu / işe giriş muayenesi | Evet | Evet (yıllık) |
| `criminal_record` | Adli sicil kaydı | Firma politikasına göre | Evet (6 ay) |
| `contract` | İş sözleşmesi | Otomatik | Hayır |
| `sgk_registration` | SGK işe giriş bildirimi | Otomatik | Hayır |
| `photo` | Vesikalık fotoğraf | Hayır | Hayır |
| `certificate` | Sertifika / eğitim belgesi | Hayır | Evet |
| `military_document` | Askerlik durum belgesi | Erkek çalışanlarda | Hayır |
| `residence_permit` | İkamet / çalışma izni (yabancı) | Yabancı uyruklu | Evet |
| `other` | Diğer | Hayır | Hayır |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-DOC-01 | Dosya boyutu maksimum 10 MB olmalıdır |
| IK-DOC-02 | İzin verilen dosya formatları: PDF, DOCX, XLSX, JPEG, PNG |
| IK-DOC-03 | Dosya adı sanitize edilir: özel karakterler temizlenir, UUID prefix eklenir |
| IK-DOC-04 | Dosyalar MinIO'da `{tenant_id}/employees/{employee_id}/documents/` yoluna kaydedilir |
| IK-DOC-05 | Dosyalara erişim signed URL ile sağlanır, doğrudan MinIO erişimi yoktur |
| IK-DOC-06 | Geçerlilik tarihi olan belgeler için süresi dolmadan 30 gün önce İK'ya uyarı bildirimi gönderilir |
| IK-DOC-07 | Belge silme işlemi soft delete'tir; KVKK saklama süresi boyunca fiziksel dosya korunur |
| IK-DOC-08 | Çalışan kendi belgelerini görüntüleyebilir ancak yalnızca İK ekleyip silebilir |

**Belge Süresi Dolum Uyarı Akışı:**

```
Günlük Celery Job (cronjob — her gün 09:00)
    │
    ▼
personnel_documents tablosunda
expiry_date yaklaşan kayıtları sorgula
    │
    ├── 30 gün kala  → İK'ya e-posta + in-app bildirim
    ├── 7 gün kala   → İK'ya e-posta + push bildirim
    └── Süresi dolmuş → İK'ya acil uyarı + dashboard'da kırmızı badge
```

---

### 3.3 İş Sözleşmesi Yönetimi

#### FR-PER-05: İş Sözleşmesi Yönetimi

**Açıklama:** Çalışanın iş sözleşmeleri tanımlanabilmeli, takip edilebilmelidir.

**Sözleşme Türleri:**

| Kod | Tür | Açıklama | Bitiş Tarihi |
|-----|-----|----------|--------------|
| `indefinite` | Belirsiz süreli | Süresiz iş sözleşmesi | Yok |
| `fixed_term` | Belirli süreli | Bitiş tarihi belirtilen sözleşme | Zorunlu |
| `part_time` | Kısmi zamanlı | Haftalık çalışma saati < 45 | Opsiyonel |
| `intern` | Stajyer | Staj sözleşmesi | Zorunlu |
| `seasonal` | Mevsimlik | Belirli dönemde çalışma | Zorunlu |
| `trial` | Deneme süreli | Deneme süresi olan sözleşme | Deneme bitiş tarihi zorunlu |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-SÖZ-01 | Bir çalışanın yalnızca 1 aktif sözleşmesi olabilir |
| IK-SÖZ-02 | Yeni sözleşme oluşturulduğunda önceki sözleşmenin durumu `expired` olarak güncellenir |
| IK-SÖZ-03 | Belirli süreli sözleşmelerde bitiş tarihi zorunludur |
| IK-SÖZ-04 | Belirli süreli sözleşme bitimine 30 gün kala İK'ya hatırlatma bildirimi gönderilir |
| IK-SÖZ-05 | Sözleşme PDF'i oluşturulabilir (şablon bazlı, WeasyPrint ile) |
| IK-SÖZ-06 | Deneme süresi bitiş tarihi sözleşme başlangıcından itibaren en fazla 2 ay sonra olabilir (4857 İş Kanunu Md. 15) |
| IK-SÖZ-07 | Sözleşme oluşturulduğunda `personnel_employees.base_salary` alanı otomatik güncellenir |
| IK-SÖZ-08 | Maaş değişikliği olan sözleşmelerde `personnel_job_history` kaydı oluşur |

**Sözleşme Süresi Dolum Uyarı Akışı:**

```
Günlük Celery Job
    │
    ▼
personnel_contracts tablosunda
end_date yaklaşan aktif sözleşmeleri sorgula
    │
    ├── 30 gün kala → İK'ya bildirim: "Sözleşme yakında bitiyor"
    ├── 7 gün kala  → İK'ya acil hatırlatma
    └── Bitiş günü  → İK'ya: "Sözleşme bugün sona erdi, yenilenmeli veya sonlandırılmalı"
```

---

### 3.4 İşe Giriş Süreci (Onboarding)

#### FR-PER-06: Onboarding Yönetimi

**Açıklama:** Yeni çalışan sisteme kaydedildiğinde otomatik başlayan, görev bazlı bir onboarding checklist sistemi.

**Onboarding Checklist Yapısı:**

#### `personnel_onboarding_templates` — Onboarding Şablonları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `name` | VARCHAR(200) | Şablon adı: "Standart Onboarding", "Stajyer Onboarding" |
| `description` | TEXT | Açıklama |
| `employment_type` | VARCHAR(30), nullable | Uygulanacak çalışma türü (null = hepsi) |
| `is_active` | BOOLEAN, default: true | |
| `created_at` | TIMESTAMPTZ | |

#### `personnel_onboarding_template_items` — Şablon Görevleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `template_id` | BIGINT, FK | Hangi şablona ait |
| `title` | VARCHAR(255) | Görev başlığı |
| `description` | TEXT | Detaylı açıklama |
| `assigned_role` | VARCHAR(50) | Sorumlu rol: `hr`, `it`, `manager`, `employee` |
| `due_days` | SMALLINT | İşe girişten kaç gün sonra tamamlanmalı |
| `is_required` | BOOLEAN, default: true | Zorunlu mu |
| `sort_order` | SMALLINT | Sıralama |

#### `personnel_onboarding_tasks` — Çalışan Bazlı Görevler

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | Hangi çalışan |
| `template_item_id` | BIGINT, FK | Kaynak şablon görevi |
| `title` | VARCHAR(255) | Görev başlığı |
| `description` | TEXT | |
| `assigned_to` | BIGINT, FK → auth_users | Sorumlu kişi |
| `due_date` | DATE | Tamamlanması gereken tarih |
| `status` | VARCHAR(20) | `pending`, `in_progress`, `completed`, `skipped` |
| `completed_at` | TIMESTAMPTZ | |
| `completed_by` | BIGINT, FK | |
| `notes` | TEXT | |
| `created_at` | TIMESTAMPTZ | |

**Varsayılan Onboarding Görevleri:**

| # | Görev | Sorumlu | Süre |
|---|-------|---------|------|
| 1 | İK: SGK işe giriş bildirimi hazırlama | İK | 1 gün |
| 2 | İK: İş sözleşmesi imzalatma | İK | 1 gün |
| 3 | İK: Özlük belgelerini toplama ve sisteme yükleme | İK | 3 gün |
| 4 | İT: Kurumsal e-posta hesabı oluşturma | IT | 1 gün |
| 5 | İT: Bilgisayar / ekipman teslimi | IT | 1 gün |
| 6 | İT: Sistem erişim yetkilerini tanımlama | IT | 1 gün |
| 7 | Yönetici: Ekiple tanıştırma | Yönetici | 1 gün |
| 8 | Yönetici: Görev tanımını paylaşma | Yönetici | 3 gün |
| 9 | Çalışan: Profil bilgilerini tamamlama | Çalışan | 3 gün |
| 10 | Çalışan: Acil durum kişisini girme | Çalışan | 3 gün |
| 11 | İK: İSG oryantasyon eğitimi | İK | 7 gün |
| 12 | İK: KVKK aydınlatma metni onayı | İK | 1 gün |

**Onboarding Süreci Akışı:**

```
Yeni Çalışan Kaydı Oluşturulur
    │
    ▼
Çalışma türüne uygun onboarding şablonu seçilir
    │
    ▼
Şablon görevleri kişiselleştirilip personnel_onboarding_tasks'a kopyalanır
    │
    ▼
Her görev için assigned_to belirlenir ve due_date hesaplanır
    │
    ▼
İlgili kişilere bildirim gönderilir (e-posta + push)
    │
    ▼
Görevler tamamlandıkça checked işaretlenir
    │
    ▼
Tüm zorunlu görevler tamamlandığında
    │
    ▼
Onboarding tamamlandı bildirimi → İK'ya rapor
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-ONB-01 | Çalışan oluşturulduğunda onboarding otomatik başlar |
| IK-ONB-02 | Checklist görevleri farklı kişilere atanabilir (İK, IT, yönetici, çalışan) |
| IK-ONB-03 | Süresi dolan görevler için otomatik hatırlatma gönderilir |
| IK-ONB-04 | Onboarding ilerlemesi dashboard'da yüzde olarak gösterilir |
| IK-ONB-05 | Zorunlu görevler tamamlanmadan onboarding kapatılamaz |
| IK-ONB-06 | Şablonlar tenant bazlı özelleştirilebilir |

---

### 3.5 İşten Çıkış Süreci (Offboarding)

#### FR-PER-07: Offboarding Yönetimi

**Açıklama:** Çalışan işten ayrıldığında tüm sürecin dijital olarak yönetilmesi.

**İşten Çıkış Türleri:**

| Kod | Tür | Açıklama | Kıdem Hakkı | İhbar Hakkı |
|-----|-----|----------|-------------|-------------|
| `resignation` | İstifa | Çalışan kendi isteğiyle ayrılır | Hayır* | Hayır |
| `termination` | İşveren feshi | İşveren tarafından iş akdi sonlandırma | Evet | Evet |
| `mutual` | İkale (karşılıklı) | Karşılıklı anlaşma ile ayrılma | Anlaşmaya bağlı | Anlaşmaya bağlı |
| `retirement` | Emeklilik | SGK emeklilik hakkı | Evet | Hayır |
| `military` | Askerlik | Zorunlu askerlik nedeniyle | Evet | Hayır |
| `death` | Vefat | Çalışanın vefatı | Evet (mirasçılara) | Hayır |
| `contract_end` | Sözleşme sonu | Belirli süreli sözleşme bitimi | Hayır | Hayır |
| `disciplinary` | Disiplin feshi | 25. madde kapsamında haklı fesih | Hayır | Hayır |

> *İstifada bile 1 yıl+ çalışmışsa bazı koşullarda kıdem hakkı doğabilir.

**Offboarding Tabloları:**

#### `personnel_offboarding` — İşten Çıkış Kaydı

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | Çıkış yapan çalışan |
| `termination_type` | VARCHAR(30) | Çıkış türü (yukarıdaki kodlardan) |
| `termination_date` | DATE | Son çalışma günü |
| `notice_date` | DATE, nullable | Bildirim tarihi |
| `reason` | TEXT | Çıkış gerekçesi |
| `severance_eligible` | BOOLEAN | Kıdem tazminatı hakkı var mı |
| `severance_amount` | NUMERIC(15,2), nullable | Kıdem tazminatı ön hesaplaması |
| `notice_pay_eligible` | BOOLEAN | İhbar tazminatı hakkı var mı |
| `notice_pay_amount` | NUMERIC(15,2), nullable | İhbar tazminatı ön hesaplaması |
| `remaining_leave_days` | NUMERIC(5,1), nullable | Kullanılmamış izin günü |
| `leave_pay_amount` | NUMERIC(15,2), nullable | İzin ücreti hesabı |
| `exit_interview_notes` | TEXT, nullable | Çıkış mülakatı notları |
| `exit_interview_completed` | BOOLEAN, default: false | Çıkış mülakatı yapıldı mı |
| `status` | VARCHAR(20) | `in_progress`, `completed`, `cancelled` |
| `initiated_by` | BIGINT, FK | Süreci başlatan İK kullanıcısı |
| `completed_at` | TIMESTAMPTZ, nullable | Süreç tamamlanma zamanı |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `personnel_offboarding_tasks` — Çıkış Görevleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `offboarding_id` | BIGINT, FK | Hangi offboarding sürecine ait |
| `title` | VARCHAR(255) | Görev başlığı |
| `assigned_to` | BIGINT, FK | Sorumlu kişi |
| `status` | VARCHAR(20) | `pending`, `completed`, `skipped` |
| `completed_at` | TIMESTAMPTZ | |
| `notes` | TEXT | |

**Varsayılan Offboarding Görevleri:**

| # | Görev | Sorumlu |
|---|-------|---------|
| 1 | İK: Kıdem/ihbar tazminatı hesaplama | İK |
| 2 | İK: SGK işten çıkış bildirimi hazırlama | İK |
| 3 | İK: Çıkış mülakatı yapma | İK |
| 4 | İK: Son bordro hazırlığı | İK |
| 5 | İK: Kullanılmamış izin bakiyesi hesabı | İK |
| 6 | İK: İbraname hazırlama ve imzalatma | İK |
| 7 | İT: E-posta hesabı kapatma | IT |
| 8 | İT: Sistem erişim yetkilerini kaldırma | IT |
| 9 | İT: Zimmet iade kontrolü (laptop, telefon, kart) | IT |
| 10 | Yönetici: Bilgi ve iş transferi | Yönetici |
| 11 | Muhasebe: Final ödeme işlemleri | Muhasebe |

**Kıdem Tazminatı Ön Hesaplama Formülü:**

```
Kıdem Tazminatı = Yıl × Son Brüt Maaş (tavan kontrolü ile)

Kıdem Yılı = (Çıkış Tarihi - İşe Giriş Tarihi) / 365
Tavan = Devlet tarafından belirlenen kıdem tazminatı tavanı (6 ayda bir güncellenir)

Eğer Son Brüt Maaş > Tavan ise → Tavan uygulanır
Yıl kesiri orantılı hesaplanır (ör: 3 yıl 4 ay = 3.33 yıl)
```

**İhbar Tazminatı Süreleri (4857 İş Kanunu Md. 17):**

| Kıdem | İhbar Süresi | İhbar Tazminatı |
|-------|-------------|-----------------|
| 0-6 ay | 2 hafta | 2 haftalık brüt ücret |
| 6-18 ay | 4 hafta | 4 haftalık brüt ücret |
| 18-36 ay | 6 hafta | 6 haftalık brüt ücret |
| 36+ ay | 8 hafta | 8 haftalık brüt ücret |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-OFF-01 | Çıkış süreci başlatıldığında çalışan durumu `terminated` olmaz; süreç tamamlanınca durumu değişir |
| IK-OFF-02 | Kıdem/ihbar tutarları ön hesaplamadır ve bilgilendirme amaçlıdır; kesin hesap bordro modülünde yapılır |
| IK-OFF-03 | Tüm zorunlu görevler tamamlanmadan offboarding kapatılamaz |
| IK-OFF-04 | Çıkış tamamlandığında çalışanın kullanıcı hesabı otomatik devre dışı olur (`auth_users.is_active = false`) |
| IK-OFF-05 | Çıkış tamamlandığında çalışan kaydı soft delete olmaz, `status = terminated` olarak kalır (yasal saklama) |
| IK-OFF-06 | SGK çıkış bildirimi için gerekli veriler otomatik hazırlanır |
| IK-OFF-07 | Kullanılmamış izin bakiyesi otomatik hesaplanır ve çıkış sürecine yansır |

---

### 3.6 Terfi, Nakil ve Görev Değişikliği

#### FR-PER-11: Terfi/Nakil/Görev Değişikliği Kaydı

**Açıklama:** Çalışanın departman, pozisyon, unvan, maaş veya yönetici değişikliklerinin tarihçe ile takip edilmesi.

**Değişiklik Türleri:**

| Kod | Tür | Açıklama |
|-----|-----|----------|
| `promotion` | Terfi | Üst pozisyona atama |
| `transfer` | Nakil | Farklı departman/şubeye geçiş |
| `title_change` | Unvan değişikliği | Pozisyon adı veya seviye değişikliği |
| `salary_change` | Maaş değişikliği | Zam, ayarlama, ücret güncellemesi |
| `manager_change` | Yönetici değişikliği | Raporlama hattı değişikliği |
| `branch_transfer` | Şube transferi | Farklı fiziksel lokasyona geçiş |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-DEG-01 | Her değişiklik `personnel_job_history` tablosuna eski ve yeni değerleriyle kaydedilir |
| IK-DEG-02 | Geçerlilik tarihi (effective_date) gelecek tarih olabilir |
| IK-DEG-03 | Geçerlilik tarihinde çalışanın ilgili alanları otomatik güncellenir (Celery scheduled job) |
| IK-DEG-04 | Maaş değişikliğinde yalnızca `personnel:salary:update` yetkisine sahip kullanıcılar işlem yapabilir |
| IK-DEG-05 | Departman değişikliğinde çalışanın bağlı olduğu yönetici otomatik güncellenebilir (opsiyonel) |
| IK-DEG-06 | Geçmiş değişiklik kayıtları silinemez (audit trail) |

**Tarihçe Görüntüleme:**

```
Çalışan Profili → "Kariyer Geçmişi" sekmesi

Tarih        Değişiklik       Eski                Yeni
─────────────────────────────────────────────────────────
2026-04-01   Terfi           Jr. Developer       Mid Developer
                              Yazılım Dept.       Yazılım Dept.
                              ₺35.000             ₺48.000

2025-07-15   Nakil           Destek Dept.        Yazılım Dept.
                              Destek Uzmanı       Jr. Developer

2024-03-15   İşe Giriş       —                   Destek Dept.
                              —                   Destek Uzmanı
                              —                   ₺28.000
```

---

### 3.7 Zimmet Yönetimi

#### FR-PER-12: Zimmet Yönetimi

**Açıklama:** Çalışana teslim edilen şirket varlıklarının (laptop, telefon, araç, kart vb.) takibi.

#### `personnel_assets` — Zimmet Tanımları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `category` | VARCHAR(50) | `laptop`, `phone`, `vehicle`, `key`, `card`, `furniture`, `other` |
| `name` | VARCHAR(255) | Varlık adı |
| `serial_number` | VARCHAR(100), nullable | Seri numarası |
| `description` | TEXT, nullable | Açıklama |
| `purchase_date` | DATE, nullable | Satın alma tarihi |
| `purchase_cost` | NUMERIC(15,2), nullable | Satın alma bedeli |
| `status` | VARCHAR(20) | `available`, `assigned`, `maintenance`, `retired` |
| `created_at` | TIMESTAMPTZ | |

#### `personnel_asset_assignments` — Zimmet Atamaları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `asset_id` | BIGINT, FK | Hangi varlık |
| `employee_id` | BIGINT, FK | Hangi çalışan |
| `assigned_date` | DATE | Teslim tarihi |
| `assigned_by` | BIGINT, FK | Teslim eden |
| `return_date` | DATE, nullable | İade tarihi |
| `return_condition` | VARCHAR(50), nullable | `good`, `damaged`, `lost` |
| `returned_to` | BIGINT, FK, nullable | İade alan |
| `notes` | TEXT, nullable | |
| `status` | VARCHAR(20) | `active`, `returned`, `lost` |
| `created_at` | TIMESTAMPTZ | |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-ZMT-01 | Bir varlık aynı anda yalnızca bir çalışana atanabilir |
| IK-ZMT-02 | Offboarding sürecinde çalışanın tüm aktif zimmetleri listelenir |
| IK-ZMT-03 | İade edilmemiş zimmetler offboarding tamamlanmasını engeller (uyarı verir) |
| IK-ZMT-04 | Zimmet geçmişi (hangi çalışan ne zaman kullandı) takip edilir |
| IK-ZMT-05 | Çalışan self-servis portalından kendi zimmet listesini görebilir |

---

### 3.8 Toplu Veri İçe Aktarma (Excel Import)

#### FR-PER-03: Toplu Veri İçe Aktarma

**Açıklama:** İK uzmanı çok sayıda çalışan verisini Excel/CSV dosyasından toplu olarak sisteme aktarabilmelidir.

**İmport Akışı:**

```
İK Uzmanı Excel Dosyası Yükler
    │
    ▼
Sistem şablon uyumluluğunu kontrol eder
    │
    ├── Format hatası → Hata raporu döner (satır bazlı)
    │
    ▼
Celery arka plan görevi başladı
    │
    ├── Satır satır validasyon:
    │   ├── TC kimlik doğrulama
    │   ├── E-posta benzersizlik kontrolü
    │   ├── Sicil no benzersizlik kontrolü
    │   ├── Departman/Pozisyon varlık kontrolü
    │   └── Veri tipi / format kontrolü
    │
    ├── Hatalı satırlar → Hata raporu (Excel)
    │
    ▼
Geçerli satırlar toplu insert edilir
    │
    ▼
Sonuç raporu İK'ya bildirilir:
    "150 çalışan başarıyla eklendi, 3 satırda hata bulundu"
```

**Excel Şablon Alanları:**

| Kolon | Zorunlu | Format | Örnek |
|-------|---------|--------|-------|
| Sicil No | Evet | Metin | S001 |
| TC Kimlik No | Evet | 11 haneli rakam | 12345678901 |
| Ad | Evet | Metin | Ahmet |
| Soyad | Evet | Metin | Yılmaz |
| Doğum Tarihi | Hayır | GG.AA.YYYY | 15.03.1990 |
| Cinsiyet | Hayır | Erkek / Kadın | Erkek |
| Telefon | Hayır | Metin | 05551234567 |
| İş E-postası | Evet | E-posta | ahmet@firma.com |
| Departman | Evet | Metin (mevcut departman adı) | Yazılım Geliştirme |
| Pozisyon | Evet | Metin (mevcut pozisyon adı) | Kıdemli Geliştirici |
| İşe Giriş Tarihi | Evet | GG.AA.YYYY | 01.04.2026 |
| Çalışma Türü | Evet | full_time / part_time / intern / contract | full_time |
| Sözleşme Türü | Evet | indefinite / fixed_term | indefinite |
| Brüt Maaş | Hayır | Sayı | 45000 |
| IBAN | Hayır | Metin | TR320006100519786457841326 |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-IMP-01 | Maksimum 1.000 satır / dosya |
| IK-IMP-02 | Dosya boyutu maksimum 5 MB |
| IK-IMP-03 | Desteklenen formatlar: .xlsx, .csv |
| IK-IMP-04 | Import sırasında mevcut çalışanlar güncellenmez, sadece yeni kayıt oluşturulur |
| IK-IMP-05 | Hatalı satırlar başarılı satırları engellemez (kısmi import) |
| IK-IMP-06 | Import sonuçları rapor olarak indirilir (başarılı/hatalı satırlar) |
| IK-IMP-07 | Import işlemi Celery'de arka planda çalışır, tamamlandığında bildirim gönderilir |
| IK-IMP-08 | Şablon dosyası `/api/v1/personnel/employees/import-template` endpoint'inden indirilir |

---

### 3.9 Veri Dışa Aktarma (Export)

**Açıklama:** Çalışan listesi Excel veya CSV olarak dışa aktarılabilmelidir.

**Export Özellikleri:**

| Özellik | Açıklama |
|---------|----------|
| Filtrelenmiş export | Mevcut liste filtresiyle eşleşen çalışanlar export edilir |
| Alan seçimi | İK kullanıcısı hangi alanların export edileceğini seçebilir |
| Format | .xlsx veya .csv |
| Hassas veri maskeleme | TC kimlik, IBAN, maaş gibi alanlar yetki kontrolüne tabidir; yetkisiz ise maskelenir |
| Büyük veri | 10.000+ kayıtta export Celery'de çalışır, hazır olduğunda bildirim gelir |

---

### 3.10 Engelli Çalışan Takibi

#### FR-PER-14: Engelli Çalışan Takibi

**Açıklama:** Engelli çalışanların takibi ve yasal kontenjan hesaplaması.

**Yasal Kontenjan (4857 İş Kanunu Md. 30):**

| Çalışan Sayısı | Engelli Kontenjanı | Oran |
|---------------|-------------------|------|
| 50'den az | Zorunlu değil | — |
| 50 ve üzeri | Çalışan sayısının %3'ü | %3 |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-ENG-01 | Engelli çalışanların engel durumu ve oranı kaydedilir |
| IK-ENG-02 | Dashboard'da yasal kontenjan durumu gösterilir (dolu/boş kadro) |
| IK-ENG-03 | Kontenjan altına düşüldüğünde İK'ya uyarı verilir |
| IK-ENG-04 | Engel durumu değişikliği audit log ile takip edilir |
| IK-ENG-05 | Engelli çalışan raporu SGK teşvik hesabı için kullanılır (bordro modülü referansı) |

---

### 3.11 Çoklu Şirket ve Şube Desteği

#### FR-PER-15: Çoklu Şirket / Şube Yönetimi

**Açıklama:** Tek hesapta birden fazla şirket veya şube yönetilebilmelidir.

**Hiyerarşi:**

```
Tenant (Firma)
    │
    ├── Şube 1 (Merkez — İstanbul)
    │   ├── Departman A
    │   │   ├── Çalışan 1
    │   │   └── Çalışan 2
    │   └── Departman B
    │       └── Çalışan 3
    │
    ├── Şube 2 (Ankara)
    │   └── Departman C
    │       ├── Çalışan 4
    │       └── Çalışan 5
    │
    └── Şube 3 (İzmir Fabrika)
        └── Departman D
            └── Çalışan 6
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-ŞUB-01 | Her çalışan bir şubeye atanmalıdır |
| IK-ŞUB-02 | Departman yöneticisi yalnızca kendi şubesindeki çalışanları görür (opsiyonel — ayarlanabilir) |
| IK-ŞUB-03 | İK yöneticisi tüm şubelerdeki çalışanları görebilir |
| IK-ŞUB-04 | Raporlar şube bazlı filtrelenebilir |
| IK-ŞUB-05 | Şubeler arası nakil `personnel_job_history` ile takip edilir |

---

## 4. API Endpoint Detayları

### 4.1 Çalışan CRUD Endpoint'leri

Temel endpoint listesi [08-api-tasarimi.md](08-api-tasarimi.md) bölüm 15.3'te tanımlanmıştır. Bu bölüm ek detayları içerir.

#### POST `/api/v1/personnel/employees` — Çalışan Oluşturma

**Request Body:**

```json
{
  "employee_number": "S001",
  "first_name": "Ahmet",
  "last_name": "Yılmaz",
  "tc_identity_no": "12345678901",
  "birth_date": "1990-03-15",
  "gender": "male",
  "marital_status": "married",
  "phone": "+905551234567",
  "work_email": "ahmet.yilmaz@firma.com",
  "department_id": 3,
  "position_id": 12,
  "branch_id": 1,
  "manager_id": 15,
  "hire_date": "2026-04-15",
  "employment_type": "full_time",
  "contract_type": "indefinite",
  "work_type": "office",
  "base_salary": 45000.00,
  "currency": "TRY",
  "address": "Kadıköy, İstanbul",
  "city_id": 34,
  "emergency_contact_name": "Fatma Yılmaz",
  "emergency_contact_phone": "+905559876543",
  "emergency_contact_relation": "Eş"
}
```

**Response (201 Created):**

```json
{
  "success": true,
  "data": {
    "id": 42,
    "employee_number": "S001",
    "first_name": "Ahmet",
    "last_name": "Yılmaz",
    "full_name": "Ahmet Yılmaz",
    "department": {
      "id": 3,
      "name": "Yazılım Geliştirme"
    },
    "position": {
      "id": 12,
      "name": "Kıdemli Geliştirici"
    },
    "branch": {
      "id": 1,
      "name": "İstanbul Merkez"
    },
    "manager": {
      "id": 15,
      "full_name": "Mehmet Demir"
    },
    "hire_date": "2026-04-15",
    "employment_type": "full_time",
    "status": "active",
    "photo_url": null,
    "created_at": "2026-04-09T14:30:00Z"
  }
}
```

**Olası Hata Kodları:**

| HTTP | Kod | Açıklama |
|------|-----|----------|
| 400 | `VALIDATION_ERROR` | Eksik zorunlu alan veya geçersiz format |
| 400 | `INVALID_TC_IDENTITY` | TC kimlik no doğrulanamadı |
| 409 | `EMPLOYEE_NUMBER_EXISTS` | Sicil numarası zaten kullanılıyor |
| 409 | `EMAIL_ALREADY_EXISTS` | İş e-postası zaten kullanılıyor |
| 422 | `EMPLOYEE_LIMIT_EXCEEDED` | Tenant çalışan kotası doldu |
| 404 | `DEPARTMENT_NOT_FOUND` | Belirtilen departman bulunamadı |
| 404 | `POSITION_NOT_FOUND` | Belirtilen pozisyon bulunamadı |

---

#### GET `/api/v1/personnel/employees` — Çalışan Listesi

**Query Parameters:**

```
GET /api/v1/personnel/employees?status=active&department_id=3&search=ahmet&sort=-hire_date&page=1&size=20
```

**Response alanları (liste görünümünde):**

```json
{
  "success": true,
  "data": [
    {
      "id": 42,
      "employee_number": "S001",
      "first_name": "Ahmet",
      "last_name": "Yılmaz",
      "full_name": "Ahmet Yılmaz",
      "photo_url": "https://...",
      "department": { "id": 3, "name": "Yazılım Geliştirme" },
      "position": { "id": 12, "name": "Kıdemli Geliştirici" },
      "branch": { "id": 1, "name": "İstanbul Merkez" },
      "hire_date": "2024-03-15",
      "employment_type": "full_time",
      "status": "active",
      "work_type": "office"
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

> **Not:** Liste görünümünde maaş, TC kimlik gibi hassas alanlar döndürülmez. Detay endpoint'inde yetki kontrolü ile döner.

---

#### GET `/api/v1/personnel/employees/{id}` — Çalışan Detayı

**Response:** Tüm alanları içerir. Hassas alanlar (maaş, TC kimlik, IBAN) yetki kontrolüne tabidir:

- `personnel:salary:read` yetkisi yoksa `base_salary` alanı `null` döner
- `personnel:sensitive:read` yetkisi yoksa `tc_identity_no` maskelenir (`***-****-901`)
- `personnel:sensitive:read` yetkisi yoksa `iban` maskelenir (`TR32 **** **** **** **** 1326`)

---

### 4.2 Onboarding Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/personnel/onboarding/templates` | Onboarding şablon listesi | `personnel:onboarding:read` |
| `POST` | `/personnel/onboarding/templates` | Yeni şablon oluştur | `personnel:onboarding:manage` |
| `PUT` | `/personnel/onboarding/templates/{id}` | Şablon güncelle | `personnel:onboarding:manage` |
| `GET` | `/personnel/employees/{id}/onboarding` | Çalışanın onboarding durumu | `personnel:onboarding:read` |
| `PATCH` | `/personnel/onboarding/tasks/{task_id}/complete` | Görevi tamamla | Auth (atanan kişi veya İK) |
| `PATCH` | `/personnel/onboarding/tasks/{task_id}/skip` | Görevi atla | `personnel:onboarding:manage` |
| `GET` | `/personnel/onboarding/dashboard` | Onboarding genel durumu | `personnel:onboarding:read` |

### 4.3 Offboarding Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/personnel/employees/{id}/offboarding` | Çıkış sürecini başlat | `personnel:offboarding:create` |
| `GET` | `/personnel/employees/{id}/offboarding` | Çıkış süreci durumu | `personnel:offboarding:read` |
| `PATCH` | `/personnel/offboarding/{id}` | Çıkış bilgilerini güncelle | `personnel:offboarding:update` |
| `PATCH` | `/personnel/offboarding/{id}/complete` | Çıkış sürecini tamamla | `personnel:offboarding:update` |
| `PATCH` | `/personnel/offboarding/tasks/{task_id}/complete` | Görevi tamamla | Auth (atanan kişi veya İK) |
| `GET` | `/personnel/offboarding/{id}/severance-preview` | Kıdem/ihbar ön hesaplama | `personnel:offboarding:read` |

### 4.4 Zimmet Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/personnel/assets` | Varlık listesi | `personnel:asset:read` |
| `POST` | `/personnel/assets` | Yeni varlık | `personnel:asset:create` |
| `PUT` | `/personnel/assets/{id}` | Varlık güncelle | `personnel:asset:update` |
| `POST` | `/personnel/assets/{id}/assign` | Çalışana ata | `personnel:asset:assign` |
| `PATCH` | `/personnel/assets/{id}/return` | İade al | `personnel:asset:assign` |
| `GET` | `/personnel/employees/{id}/assets` | Çalışanın zimmetleri | `personnel:asset:read` |

### 4.5 Import/Export Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/personnel/employees/import-template` | Excel şablon dosyasını indir | `personnel:employee:create` |
| `POST` | `/personnel/employees/import` | Excel dosyasıyla toplu import | `personnel:employee:create` |
| `GET` | `/personnel/employees/import/{job_id}/status` | Import iş durumu | `personnel:employee:create` |
| `GET` | `/personnel/employees/export` | Filtrelenmiş çalışan listesini dışa aktar | `personnel:employee:read` |

---

## 5. Ekran Tasarımı Rehberi

### 5.1 Ekran Listesi

| # | Ekran | Platform | Rol | Öncelik |
|---|-------|----------|-----|---------|
| 1 | Çalışan Listesi | Web + Mobil | İK, Yönetici | Must |
| 2 | Çalışan Ekleme Formu | Web | İK | Must |
| 3 | Çalışan Detay / Profil | Web + Mobil | İK, Yönetici, Çalışan | Must |
| 4 | Çalışan Düzenleme Formu | Web | İK | Must |
| 5 | Onboarding Dashboard | Web | İK | Must |
| 6 | Onboarding Checklist | Web + Mobil | İK, IT, Yönetici | Must |
| 7 | Offboarding Süreci | Web | İK | Must |
| 8 | Belge Yönetimi (çalışan altında) | Web | İK | Must |
| 9 | Sözleşme Yönetimi (çalışan altında) | Web | İK | Must |
| 10 | Kariyer Geçmişi (çalışan altında) | Web | İK | Must |
| 11 | Zimmet Yönetimi | Web | İK, IT | Should |
| 12 | Toplu Import Ekranı | Web | İK | Must |
| 13 | Kendi Profilim (Self-Servis) | Web + Mobil | Çalışan | Must |
| 14 | Organizasyon Şeması (temel) | Web | Tüm roller | Should |
| 15 | Personel Raporları | Web | İK, C-Level | Must |

### 5.2 Çalışan Listesi Ekranı (Web)

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ İK Paneli  /  Personel Yönetimi  /  Çalışan Listesi       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ [🔍 Çalışan ara...        ]  [Filtreler ▼]  [+ Yeni Çalışan]│
│                              [📥 İçe Aktar] [📤 Dışa Aktar] │
│                                                              │
│ Aktif filtreler: Departman: Yazılım | Durum: Aktif     [x]   │
│                                                              │
│ ┌────┬──────────┬───────────────┬──────────────┬──────┬─────┐│
│ │ □  │ Çalışan  │ Departman     │ Pozisyon     │Tarih │ ... ││
│ ├────┼──────────┼───────────────┼──────────────┼──────┼─────┤│
│ │ □  │ 👤 Ahmet │ Yazılım       │ Sr.Developer │04/24 │ ⋮   ││
│ │    │ Yılmaz   │ Geliştirme    │              │      │     ││
│ ├────┼──────────┼───────────────┼──────────────┼──────┼─────┤│
│ │ □  │ 👤 Elif  │ Yazılım       │ Jr.Developer │01/25 │ ⋮   ││
│ │    │ Kaya     │ Geliştirme    │              │      │     ││
│ ├────┼──────────┼───────────────┼──────────────┼──────┼─────┤│
│ │ □  │ 👤 Can   │ Yazılım       │ QA Engineer  │06/25 │ ⋮   ││
│ │    │ Demir    │ Geliştirme    │              │      │     ││
│ └────┴──────────┴───────────────┴──────────────┴──────┴─────┘│
│                                                              │
│ Toplam: 156 çalışan                     ◀ 1 2 3 ... 8 ▶     │
└──────────────────────────────────────────────────────────────┘
```

**Özellikler:**
- Toplu seçim (checkbox) ile toplu işlem yapabilme (toplu durum değişikliği, dışa aktarım)
- Kolon sıralaması (tıklayarak ASC/DESC)
- Satıra tıklayınca detay sayfasına yönlendirme
- ⋮ menü: Düzenle, Belge Ekle, Onboarding Görüntüle, İşten Çıkış Başlat
- Responsive: Mobilde kart görünümüne dönüşür

### 5.3 Çalışan Detay Ekranı (Web)

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ Çalışan Listesi  /  Ahmet Yılmaz                [Düzenle] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐  Ahmet Yılmaz                     Durum: 🟢    │
│  │         │  Kıdemli Yazılım Geliştirici        Aktif       │
│  │  📷     │  Yazılım Geliştirme Departmanı                  │
│  │         │  İstanbul Merkez Şubesi                         │
│  └─────────┘  İşe Giriş: 15 Mart 2024 (2 yıl 1 ay)         │
│                                                              │
│ ┌─────────┬───────────┬───────────┬──────────┬───────────┐   │
│ │ Kişisel │ Kurumsal  │ Belgeler  │ Sözleşme │ Geçmiş    │   │
│ │ Bilgiler│ Bilgiler  │           │          │           │   │
│ └─────────┴───────────┴───────────┴──────────┴───────────┘   │
│                                                              │
│ Sekme İçeriği (seçili sekmeye göre değişir)                  │
│ ─────────────────────────────────────────────                │
│                                                              │
│ Kişisel Bilgiler:                                            │
│ ┌────────────────┬─────────────────────┐                     │
│ │ TC Kimlik      │ ***-****-901        │                     │
│ │ Doğum Tarihi   │ 15 Mart 1990 (36)   │                     │
│ │ Cinsiyet       │ Erkek               │                     │
│ │ Medeni Durum   │ Evli                │                     │
│ │ Kan Grubu      │ A Rh+               │                     │
│ │ Telefon        │ +90 555 123 45 67   │                     │
│ │ Kişisel E-posta│ ahmet@gmail.com     │                     │
│ │ Adres          │ Kadıköy, İstanbul   │                     │
│ ├────────────────┼─────────────────────┤                     │
│ │ Acil Durum     │ Fatma Yılmaz (Eş)   │                     │
│ │ Kişisi         │ +90 555 987 65 43   │                     │
│ └────────────────┴─────────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
```

**Sekmeler:**

| Sekme | İçerik |
|-------|--------|
| Kişisel Bilgiler | Demografik, iletişim, acil durum |
| Kurumsal Bilgiler | Departman, pozisyon, yönetici, maaş, çalışma türü |
| Belgeler | Yüklü belgeler listesi, yeni belge ekleme |
| Sözleşmeler | Aktif ve geçmiş sözleşmeler |
| Kariyer Geçmişi | Terfi, nakil, maaş değişiklikleri kronolojisi |
| Zimmetler | Çalışana atanan varlıklar |
| Onboarding | Onboarding checklist ve ilerleme durumu |

### 5.4 Mobil Ekranlar

**Çalışan Listesi (Mobil — Kart Görünümü):**

```
┌─────────────────────────┐
│ ◀  Personel       🔍 ≡  │
├─────────────────────────┤
│                         │
│ ┌─────────────────────┐ │
│ │ 👤 Ahmet Yılmaz     │ │
│ │ Sr. Developer       │ │
│ │ Yazılım Geliştirme  │ │
│ │ 🟢 Aktif             │ │
│ └─────────────────────┘ │
│                         │
│ ┌─────────────────────┐ │
│ │ 👤 Elif Kaya        │ │
│ │ Jr. Developer       │ │
│ │ Yazılım Geliştirme  │ │
│ │ 🟢 Aktif             │ │
│ └─────────────────────┘ │
│                         │
│ ┌─────────────────────┐ │
│ │ 👤 Can Demir        │ │
│ │ QA Engineer         │ │
│ │ Yazılım Geliştirme  │ │
│ │ 🟡 İzinde            │ │
│ └─────────────────────┘ │
│                         │
└─────────────────────────┘
```

**Çalışan Profil (Mobil):**

```
┌─────────────────────────┐
│ ◀  Ahmet Yılmaz    ✏️   │
├─────────────────────────┤
│         ┌─────┐         │
│         │ 📷  │         │
│         └─────┘         │
│    Ahmet Yılmaz         │
│    Sr. Developer        │
│    🟢 Aktif              │
│                         │
│ ┌─────────────────────┐ │
│ │ 📧 ahmet@firma.com  │ │
│ │ 📱 +90 555 123 4567 │ │
│ │ 🏢 Yazılım Geliştirme│ │
│ │ 📍 İstanbul Merkez   │ │
│ │ 📅 15.03.2024        │ │
│ └─────────────────────┘ │
│                         │
│ [Belgeler] [Zimmetler]  │
│ [Sözleşme] [Geçmiş]    │
│                         │
└─────────────────────────┘
```

---

## 6. Raporlama

### 6.1 Personel Modülü Raporları

| # | Rapor | Açıklama | Filtreler | Format |
|---|-------|----------|-----------|--------|
| 1 | Headcount Raporu | Toplam çalışan sayısı, departman dağılımı | Tarih, şube, departman | Dashboard + Excel |
| 2 | Cinsiyet Dağılımı | Kadın/Erkek oranı departman bazlı | Şube, departman | Pasta grafik + Excel |
| 3 | Yaş Dağılımı | Yaş gruplarına göre çalışan sayısı | Şube, departman | Histogram + Excel |
| 4 | Kıdem Dağılımı | Kıdem yılına göre çalışan dağılımı | Şube, departman | Çubuk grafik + Excel |
| 5 | İşe Giriş Raporu | Dönemsel işe alınan çalışan listesi | Tarih aralığı, departman | Liste + Excel |
| 6 | İşten Çıkış Raporu | Dönemsel ayrılan çalışan listesi ve nedenleri | Tarih aralığı, çıkış türü | Liste + Excel |
| 7 | Personel Devir Oranı (Turnover) | Aylık/yıllık turnover | Tarih, departman | Trend çizgi grafik |
| 8 | Sözleşme Bitiş Raporu | Yaklaşan sözleşme sonları | Tarih aralığı | Liste |
| 9 | Belge Süresi Dolum Raporu | Süresi yaklaşan/dolan belgeler | Tarih aralığı, belge türü | Liste |
| 10 | Engelli Kontenjan Raporu | Yasal kontenjan durumu | Şube | Özet tablo |
| 11 | Departman Bazlı Maliyet Raporu | Departman başına personel maliyeti | Departman, şube | Tablo + grafik |
| 12 | Onboarding Durum Raporu | Devam eden onboarding süreçleri | Durum | Liste |
| 13 | Zimmet Raporu | Tüm şirket varlıkları ve atamaları | Kategori, durum | Liste + Excel |

### 6.2 Dashboard Kartları (Personel Bölümü)

```
┌────────────────────────────────────────────────────────────┐
│                    PERSONEL DASHBOARD                       │
├────────────┬────────────┬────────────┬────────────────────  │
│  Toplam    │  Bu Ay     │  Bu Ay     │  Devam Eden         │
│  Çalışan   │  İşe Giren │  Ayrılan   │  Onboarding         │
│  ┌──────┐  │  ┌──────┐  │  ┌──────┐  │  ┌──────┐           │
│  │ 156  │  │  │  5   │  │  │  2   │  │  │  3   │           │
│  └──────┘  │  └──────┘  │  └──────┘  │  └──────┘           │
│  ↑ %3      │            │            │                     │
├────────────┴────────────┴────────────┴────────────────────  │
│                                                            │
│ Departman Dağılımı          │ Cinsiyet Dağılımı            │
│ ┌─────────────────────┐    │ ┌──────────────────┐          │
│ │ ████████████ Yazılım 45  │ │  ◉ Erkek    58%  │          │
│ │ ████████  Satış     32   │ │  ◉ Kadın    42%  │          │
│ │ ██████  Üretim      28   │ └──────────────────┘          │
│ │ ████  İK            12   │                               │
│ │ ███  Finans          9   │ Turnover Trendi (12 ay)       │
│ │ ██  Diğer           30   │ ┌──────────────────┐          │
│ └─────────────────────┘    │ │   /\    /\       │          │
│                            │ │  /  \  /  \___   │          │
│                            │ │ /    \/        \  │          │
│                            │ └──────────────────┘          │
└────────────────────────────────────────────────────────────┘
```

### 6.3 Rapor Metrikleri ve Hesaplama

| Metrik | Formül |
|--------|--------|
| **Headcount** | `status = active` olan çalışan sayısı |
| **Turnover Oranı (Aylık)** | (Ayda ayrılan çalışan / Ay başı headcount) × 100 |
| **Turnover Oranı (Yıllık)** | (Yılda ayrılan çalışan / Ortalama headcount) × 100 |
| **Ortalama Kıdem** | Tüm aktif çalışanların kıdem yılı ortalaması |
| **Ortalama Yaş** | Tüm aktif çalışanların yaş ortalaması |
| **Engelli Oranı** | (Engelli çalışan / Toplam çalışan) × 100 |
| **Onboarding Tamamlanma** | (Tamamlanan görev / Toplam görev) × 100 |

---

## 7. İş Akışları ve Otomasyon

### 7.1 Otomatik Tetiklenen İşlemler

| Tetikleyici | İşlem | Yöntem |
|-------------|-------|--------|
| Çalışan oluşturuldu | Kullanıcı hesabı oluştur + hoş geldin e-postası gönder | Senkron (transaction) + Celery (e-posta) |
| Çalışan oluşturuldu | Onboarding checklist başlat | Senkron |
| Çalışan oluşturuldu | Varsayılan izin bakiyelerini oluştur | Senkron (izin modülü service çağrısı) |
| Departman/pozisyon değişti | Job history kaydı oluştur | Senkron |
| Maaş değişti | Job history kaydı oluştur | Senkron |
| Offboarding tamamlandı | Kullanıcı hesabını devre dışı bırak | Senkron |
| Offboarding tamamlandı | Çalışan durumunu `terminated` yap | Senkron |
| Sözleşme bitimine 30 gün | İK'ya hatırlatma bildirimi | Celery beat (günlük cron) |
| Belge süresine 30 gün | İK'ya hatırlatma bildirimi | Celery beat (günlük cron) |
| Onboarding görevi süresi doldu | Sorumluya hatırlatma | Celery beat (günlük cron) |
| Profil güncellendi (çalışan tarafından) | Audit log kaydı + İK bildirimi (IBAN/medeni durum değişikliği) | Senkron |

### 7.2 Celery Beat (Zamanlanmış Görevler)

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `check_contract_expiry` | Günlük 09:00 | Süresi yaklaşan sözleşmeleri kontrol et |
| `check_document_expiry` | Günlük 09:00 | Süresi yaklaşan belgeleri kontrol et |
| `check_onboarding_overdue` | Günlük 09:00 | Süresi geçen onboarding görevlerini bildir |
| `check_probation_expiry` | Günlük 09:00 | Deneme süresi biten çalışanları bildir |
| `recalculate_disability_quota` | Haftalık Pazartesi | Engelli kontenjan durumunu güncelle |

---

## 8. Güvenlik ve KVKK

### 8.1 Hassas Veri Sınıflandırması

| Veri | Hassasiyet | Saklama | Erişim Kontrolü |
|------|-----------|---------|-----------------|
| TC Kimlik No | Çok Yüksek | AES-256 şifreli kolon | `personnel:sensitive:read` |
| IBAN | Yüksek | AES-256 şifreli kolon | `personnel:sensitive:read` |
| Brüt Maaş | Yüksek | Düz metin (yetki kontrolü) | `personnel:salary:read` |
| Adres | Orta | Düz metin | Auth (ilgili roller) |
| Telefon | Orta | Düz metin | Auth (ilgili roller) |
| Profil fotoğrafı | Düşük | MinIO (signed URL) | Auth |
| Departman/Pozisyon | Düşük | Düz metin | Auth |
| Ad/Soyad | Düşük | Düz metin | Auth |

### 8.2 KVKK Uyum Gereksinimleri

| Gereksinim | Uygulama |
|------------|----------|
| **Aydınlatma metni** | Çalışan ilk girişinde KVKK aydınlatma metnini onaylar |
| **Açık rıza** | Zorunlu olmayan verilerin (fotoğraf, kan grubu vb.) toplanması için rıza alınır |
| **Veri minimizasyonu** | Zorunlu olmayan alanlar opsiyoneldir |
| **Erişim hakkı** | Çalışan self-servis portalından kendi verilerini görebilir |
| **Düzeltme hakkı** | Çalışan self-servis üzerinden düzeltme talep edebilir |
| **Unutulma hakkı** | Yasal saklama süresi dolduktan sonra fiziksel silme mekanizması |
| **Veri taşınabilirliği** | Çalışan verilerinin standart formatta (JSON/CSV) dışa aktarımı |
| **Saklama süreleri** | İş hukuku: 10 yıl, SGK: 10 yıl, vergi: 5 yıl — süre dolduktan sonra anonim veya silme |
| **Veri erişim logu** | Kim, ne zaman, hangi çalışan verisine erişti — audit_logs |
| **Üçüncü taraf paylaşım** | SGK, banka gibi paylaşımlar loglenir |

### 8.3 Rol Bazlı Erişim Matrisi (Personel Modülü)

| İzin | Süper Admin | İK Yöneticisi | Dept. Yöneticisi | Çalışan | C-Level |
|------|------------|--------------|-----------------|---------|---------|
| `personnel:employee:create` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:employee:read` | ✅ | ✅ | Kendi ekibi | Kendi profili | ✅ (salt okunur) |
| `personnel:employee:update` | ✅ | ✅ | ❌ | Kısıtlı alanlar | ❌ |
| `personnel:employee:delete` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:salary:read` | ✅ | ✅ | ❌ | Kendi maaşı | ❌ |
| `personnel:salary:update` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:sensitive:read` | ✅ | ✅ | ❌ | Kendi verisi | ❌ |
| `personnel:document:create` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:document:read` | ✅ | ✅ | ❌ | Kendi belgeleri | ❌ |
| `personnel:contract:read` | ✅ | ✅ | ❌ | Kendi sözleşmesi | ❌ |
| `personnel:onboarding:manage` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:onboarding:read` | ✅ | ✅ | Kendi ekibi | Kendi | ❌ |
| `personnel:offboarding:create` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:asset:assign` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `personnel:asset:read` | ✅ | ✅ | Kendi ekibi | Kendi zimmetleri | ❌ |

---

## 9. Modüller Arası Bağımlılıklar

### 9.1 Personel Modülünün Sunduğu Servisler

Personel modülü, diğer modüllerin temel veri kaynağıdır. `PersonnelService` sınıfı aşağıdaki fonksiyonları diğer modüllere sunar:

```python
class PersonnelService:
    """Diğer modüllerin kullandığı personel servisleri."""

    async def get_employee(self, employee_id: int) -> Employee
    async def get_employee_by_user_id(self, user_id: int) -> Employee
    async def get_employees_by_department(self, department_id: int) -> list[Employee]
    async def get_employees_by_manager(self, manager_id: int) -> list[Employee]
    async def get_employee_manager(self, employee_id: int) -> Employee | None
    async def get_active_employee_count(self, tenant_id: int) -> int
    async def get_employee_hire_date(self, employee_id: int) -> date
    async def get_employee_salary(self, employee_id: int) -> Decimal
    async def is_employee_active(self, employee_id: int) -> bool
    async def update_employee_status(self, employee_id: int, status: str) -> None
```

### 9.2 Personel Modülünün Kullandığı Servisler

| Modül | Servis | Kullanım |
|-------|--------|----------|
| **Auth** | `AuthService.create_user()` | Çalışan oluşturulunca kullanıcı hesabı oluşturma |
| **Auth** | `AuthService.deactivate_user()` | Offboarding tamamlanınca hesap devre dışı bırakma |
| **Leave** | `LeaveService.create_initial_balances()` | Çalışan oluşturulunca izin bakiyesi oluşturma |
| **Leave** | `LeaveService.get_remaining_balance()` | Offboarding'de kullanılmamış izin hesabı |
| **Notification** | `NotificationService.send()` | Onboarding görevleri, belge süreleri, hatırlatmalar |
| **Organization** | `OrganizationService.get_department()` | Departman bilgisi doğrulama |

### 9.3 Bağımlılık Diyagramı

```
                    ┌──────────────┐
                    │     Auth     │
                    │   Modülü     │
                    └──────┬───────┘
                           │ kullanıcı hesap yönetimi
                           │
┌──────────────┐    ┌──────┴───────┐    ┌──────────────┐
│ Organization │◀───│   Personel   │───▶│    Leave      │
│   Modülü     │    │   Modülü     │    │   Modülü     │
└──────────────┘    └──────┬───────┘    └──────────────┘
  dept, pozisyon           │
                    ┌──────┼───────┐
                    │      │       │
              ┌─────┴──┐ ┌┴─────┐ ┌┴──────────┐
              │Bildirim│ │Bordro│ │Performans │
              │Modülü  │ │Modülü│ │  Modülü   │
              └────────┘ └──────┘ └───────────┘
                           ▲          ▲
                           │          │
                    çalışan verisi çeker
```

---

## 10. Performans Gereksinimleri

| Senaryo | Hedef | Yöntem |
|---------|-------|--------|
| Çalışan listesi (20 kayıt/sayfa, 10.000 çalışan DB'de) | < 100ms | Composite index, pagination |
| Çalışan arama (fuzzy, 10.000 kayıt) | < 300ms | pg_trgm + full-text search |
| Çalışan detayı (join'ler dahil) | < 150ms | Eager loading, index |
| Excel import (500 satır) | < 30 saniye | Celery, batch insert |
| Excel export (5.000 çalışan) | < 10 saniye | Celery, streaming |
| Onboarding dashboard | < 200ms | Cache (Redis, 60s TTL) |
| Kıdem/ihbar ön hesaplama | < 100ms | In-memory hesaplama |

---

## 11. Test Senaryoları

### 11.1 Birim Test

| # | Test | Beklenen Sonuç |
|---|------|---------------|
| 1 | TC kimlik doğrulama (geçerli) | True |
| 2 | TC kimlik doğrulama (geçersiz) | False |
| 3 | Kıdem tazminatı hesaplama (3 yıl 4 ay, 45.000 TL) | Doğru tutar |
| 4 | İhbar süresi hesaplama (2 yıl kıdem) | 6 hafta |
| 5 | Deneme süresi bitiş tarihi hesaplama | İşe giriş + 2 ay |
| 6 | Sicil numarası benzersizlik kontrolü | Conflict hatası |
| 7 | Engelli kontenjan hesaplama (55 çalışan) | Min 2 engelli |
| 8 | İzin verilen profil alanları kontrolü (çalışan rolü) | Kısıtlı alanlar |

### 11.2 Entegrasyon Test

| # | Test | Beklenen Sonuç |
|---|------|---------------|
| 1 | Çalışan oluştur → Kullanıcı hesabı oluşur mu | Auth modülünde kullanıcı kaydı var |
| 2 | Çalışan oluştur → İzin bakiyesi oluşur mu | Leave modülünde yıllık bakiye kaydı var |
| 3 | Çalışan oluştur → Onboarding checklist oluşur mu | Onboarding görevleri listelenebilir |
| 4 | Offboarding tamamla → Kullanıcı hesabı devre dışı mı | `auth_users.is_active = false` |
| 5 | Departman değişikliği → Job history kaydı oluşur mu | `personnel_job_history` kaydı var |
| 6 | Excel import → Toplu çalışan oluşur mu | DB'de doğru sayıda kayıt var |
| 7 | Tenant A çalışanı → Tenant B'den erişilemez | 403 veya boş liste döner |

### 11.3 E2E Test

| # | Test | Adımlar |
|---|------|---------|
| 1 | Yeni çalışan ekleme akışı | Login → Personel → Yeni Çalışan → Form doldur → Kaydet → Liste'de görünür → Onboarding başladı |
| 2 | Profil güncelleme (çalışan) | Login (çalışan) → Profilim → Telefon güncelle → Kaydet → Yeni numara görünür |
| 3 | İşten çıkış akışı | Login → Personel → Çalışan seç → İşten Çıkış Başlat → Checklist tamamla → Çalışan terminated |
| 4 | Toplu import | Login → İçe Aktar → Şablon indir → Doldur → Yükle → Sonuç raporu → Çalışanlar listede |
| 5 | Belge yükleme | Login → Çalışan detay → Belgeler → Dosya yükle → Listede görünür → İndirilir |

---

## 12. Kısıtlamalar ve Varsayımlar

### 12.1 Kısıtlamalar

| # | Kısıt | Etki | Çözüm |
|---|-------|------|-------|
| K1 | TC kimlik doğrulama harici servis gerektiriyor | İlk sürümde basit format kontrolü | Nüfus müd. SOAP servisi Faz 3'te |
| K2 | SGK işe giriş/çıkış doğrudan API ile yapılamıyor | Dosya export ile çözüm | SGK formatında dosya üretimi |
| K3 | Profil fotoğrafı boyutu mobilde sorun olabilir | Fotoğraf optimizasyonu | Otomatik resize + sıkıştırma (max 500KB) |
| K4 | Farklı sektörlerde farklı zorunlu belgeler var | Belge şablonu herkese uymayabilir | Tenant bazlı belge türü konfigürasyonu |

### 12.2 Varsayımlar

| # | Varsayım | Risk |
|---|---------|------|
| V1 | Her çalışanın benzersiz iş e-postası var | Düşük |
| V2 | Türk vatandaşlarının TC kimlik numarası 11 haneli | Düşük |
| V3 | Her firma en az bir departman ve pozisyon tanımlamış | Düşük |
| V4 | Yabancı uyruklu çalışan oranı düşük | Düşük |
| V5 | İşe giriş bildirimi SGK'ya manuel yapılacak (dosya export) | Orta |

---

## 13. Gelecek İyileştirmeler (Roadmap)

| Faz | İyileştirme | Açıklama |
|-----|-------------|----------|
| Faz 2 | e-Devlet TC doğrulama | KPS SOAP servisi ile online doğrulama |
| Faz 2 | SGK otomatik dosya üretimi | APHB, işe giriş/çıkış XML dosyaları |
| Faz 3 | AI destekli özgeçmiş ayrıştırma | CV'den otomatik çalışan kaydı oluşturma |
| Faz 3 | Dijital imza entegrasyonu | Sözleşmelerin dijital olarak imzalanması |
| Faz 3 | Çalışan self-servis talepleri | İsim/soyisim değişikliği talebi, belge talebi |
| Faz 4 | Tahminsel işten ayrılma analizi | ML ile işten ayrılma riski tahmini |
| Faz 4 | Blockchain sertifika doğrulama | Diploma ve sertifika doğrulama |
| Faz 4 | Gelişmiş organizasyon planlaması | Kadro planlama, headcount bütçeleme |

---

## 14. Sonuç

Personel Yönetimi modülü, İK Yönetim Sistemi'nin en temel ve en geniş kapsamlı modülüdür. Bu doküman aşağıdaki temel kararları detaylandırmıştır:

- **Kapsamlı çalışan kaydı:** 40+ alan ile Türk iş hukuku ve İK ihtiyaçlarına tam uyum
- **Dijital onboarding/offboarding:** Checklist tabanlı, otomatik tetiklenen, takip edilebilir süreçler
- **Belge ve sözleşme yönetimi:** MinIO tabanlı güvenli depolama, süre takibi, otomatik hatırlatma
- **Terfi ve kariyer geçmişi:** Kronolojik değişiklik kaydı, audit trail
- **Zimmet takibi:** Varlık ataması, iade kontrolü, offboarding entegrasyonu
- **Toplu operasyonlar:** Excel import/export, şablon desteği, arka plan işleme
- **Güvenlik ve KVKK:** Kolon bazlı şifreleme, hassas veri maskeleme, rol bazlı erişim, audit log
- **Modüller arası entegrasyon:** Auth, Leave, Notification, Bordro modülleri ile doğrudan servis çağrısı
- **Mobil öncelik:** Çalışan profili, belge görüntüleme, onboarding görevleri mobilde tam fonksiyonel
- **Otomasyon:** 10+ otomatik tetiklenen işlem ve 5 zamanlanmış görev

---

> **Sonraki Adım:** [11-modul-ise-alim-ats.md](11-modul-ise-alim-ats.md) — İlan yönetimi, başvuru takibi, mülakat planlama, teklif süreci, aday havuzu
