# 12 — Modül: İzin & Devamsızlık Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** İzin türleri tanımlama, yıllık kota hesaplama, talep/onay akışları, bakiye yönetimi, izin takvimi, yıl sonu devir, yarım/saatlik izin, devamsızlık takibi, resmi tatil yönetimi  
> **Faz:** MVP (Faz 1) — Personel Yönetimi, Self-Servis Portal ile birlikte ilk çıkışta yer alır  
> **Referans:** 04-gereksinim-analizi.md (FR-IZN-01 – FR-IZN-13), 07-veritabani-tasarimi.md (Bölüm 5.2), 08-api-tasarimi.md (Bölüm 15.4), 10-modul-personel-yonetimi.md

---

## 1. Modül Özeti

İzin & Devamsızlık Yönetimi modülü, çalışanların tüm izin süreçlerini (talep oluşturma, onay akışı, bakiye takibi, takvim görünümü) ve devamsızlık kayıtlarını dijitalleştirir. **MVP'nin üç temel modülünden biridir**; Personel Yönetimi modülüne doğrudan bağımlıdır ve Self-Servis Portal'ın en yoğun kullanılan özelliğini sağlar.

Türkiye İş Kanunu'na (4857 sayılı Kanun) tam uyumlu kota hesaplama, çok seviyeli onay akışı, mobil öncelikli deneyim ve otomatik devir mekanizmaları içerir.

### 1.1 Modül Kapsamı

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| İzin türleri tanımlama ve yönetimi | Bordro/maaş izin ücreti hesaplama (14-modul-bordro-maas.md) |
| Kıdeme göre otomatik yıllık kota hesaplama | Vardiya bazlı devamsızlık analizi (16-modul-vardiya-mesai.md) |
| İzin talebi oluşturma (tam gün, yarım gün, saatlik) | Performans değerlendirmede devam skoru (13-modul-performans-yonetimi.md) |
| Çok seviyeli onay akışı | PDKS cihaz doğrulama (16-modul-vardiya-mesai.md) |
| İzin bakiyesi hesaplama ve anlık görüntüleme | Fazla mesai hakkı doğumu (16-modul-vardiya-mesai.md) |
| Ekip/departman izin takvimi | — |
| Resmi tatil takvimi (Türkiye + özel tatiller) | — |
| Yıl sonu izin devri (carry-over) yönetimi | — |
| Devamsızlık kayıt ve takibi | — |
| Toplu idari izin tanımlama | — |
| İzin iptal ve tarih değişikliği | — |
| Mobil izin talebi ve onay | — |

### 1.2 MVP'deki Rolü

```
MVP Kapsamı:
┌────────────────────────────────────────────────────────┐
│  Personel Yönetimi  ←  Çalışan verisi kaynağı          │
│  İzin Yönetimi      ←  Personel'e bağımlı (çalışan     │
│                         oluşturulunca bakiye açılır)    │
│  Self-Servis Portal ←  İzin talebinin ana giriş noktası│
│  Auth + Bildirim    ←  Onay bildirimleri                │
└────────────────────────────────────────────────────────┘
```

### 1.3 İlişkili Modüller

```
                    ┌──────────────┐
                    │   Personel   │ Çalışan verisi, kıdem hesabı,
                    │   Modülü     │ işe giriş tarihi, departman
                    └──────┬───────┘
                           │
┌──────────────┐    ┌──────┴───────┐    ┌──────────────┐
│ Notification │◀───│    İzin &    │───▶│  Self-Servis │
│   Modülü     │    │ Devamsızlık  │    │    Portal    │
└──────────────┘    └──────┬───────┘    └──────────────┘
  onay/red, push            │              çalışan talep
  SMS/e-posta               │              ve bakiye görünümü
                    ┌───────┼────────┐
                    │       │        │
              ┌─────┴──┐  ┌─┴────┐  ┌┴──────────┐
              │ Bordro  │  │Organ.│  │  Vardiya  │
              │ Modülü  │  │Modülü│  │  Modülü   │
              └─────────┘  └──────┘  └───────────┘
              kullanılmayan  dept/      devam
              izin ücreti   yönetici   kaydı
              (offboarding) hiyerarşi
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|---------------|-------------------|-----------------|
| **Zeynep (Çalışan)** | Ana talep oluşturucu | Ayda 1-3 kez | İzin talebi, bakiye görüntüleme, talep iptali |
| **Mehmet (Dept. Yöneticisi)** | Birincil onaylayıcı | Haftada 2-5 kez | İzin onay/red, ekip takvimi görüntüleme |
| **Ayşe (İK Müdürü)** | Yönetici & ikincil onaylayıcı | Günlük 15-30 dk | İzin türü tanımlama, bakiye düzeltme, devamsızlık raporu, toplu izin |
| **Emre (KOBİ Sahibi)** | Hem yönetici hem İK | Haftada 2-4 kez | Onay/red, politika tanımlama, raporlama |
| **Hakan (Genel Müdür)** | Dashboard tüketici | Ayda 1-2 kez | İzin yoğunluğu raporu, devamsızlık oranı |

### 2.2 Çalışan — İzin Talebi Yolculuğu

```
İHTİYAÇ               TALEP                   ONAY                    SONUÇ
   │                    │                        │                        │
   ▼                    ▼                        ▼                        ▼
İzin almak         Mobil / web'den          Yöneticiye              Onaylandı veya
istiyor            izin talebi aç           push bildirimi          reddedildi:
   │                    │                    gönderildi                   │
   ▼                    ├─ İzin türü seç         │                    ├── Onay: bakiye
Bakiyesini             ├─ Tarih(ler) gir      Yönetici:              │    güncellendi,
kontrol eder           ├─ Yarım gün?         ├── Ekip takvimini       │    bildirim geldi
   │                   ├─ Açıklama (opsiyonel)│   kontrol eder       │
   ▼                   ├─ Rapor yükle         ├── Onaylar (1 tık) → │── Red: gerekçe
Bakiye yeterliyse      │  (hastalık ise)      └── veya reddeder         ve bildirim
devam eder             └─ Gönder                  (gerekçe ile)          geldi
```

**Hedef Süreler:**

| Adım | Hedef | Mevcut (Manuel) |
|------|-------|-----------------|
| İzin talebi oluşturma | < 1 dakika (mobil) | 5-15 dakika (kağıt / e-posta) |
| Yönetici onay süresi | < 4 saat (iş saati) | 1-3 gün |
| Bakiye görüntüleme | Anlık | İK'ya sormak gerekiyor |
| Yıl sonu bakiye hesaplama | Otomatik | Yarım gün İK çalışması |

### 2.3 Departman Yöneticisi — Onay Yolculuğu

```
BİLDİRİM               İNCELEME                KARAR
   │                       │                      │
   ▼                       ▼                      ▼
Push bildirim:         Ekip takvimini         Onayla / Reddet
"Zeynep izin           incele:                (gerekçe ile)
talep etti"               │                      │
   │                    ├─ Çakışm var mı?         │
   ▼                    ├─ Proje kritik mi?    ├── Onay → Bildirim
Mobil / web'den         └─ Kapasite yeterli?  └── Red → Gerekçe zorunlu
talebi gör
```

**Yönetici Karar Kriterleri:**

| Kriter | Değerlendirme |
|--------|---------------|
| Ekip izin çakışması | Aynı günde ekibin % kaçı izinli? |
| Bakiye yeterliliği | Sistem otomatik kontrol eder |
| Özel proje dönemi | Yönetici manuel değerlendirme |
| İzin türü uygunluğu | Hastalık raporlu mu? |

### 2.4 İK Müdürü — Devamsızlık Takip Yolculuğu

```
TESPİT                 KAYIT                   TAKİP
   │                    │                        │
   ▼                    ▼                        ▼
Çalışan gelmiyor   → Devamsızlık kaydı       → 3. devamsızlıkta
ve bildirim yok      oluştur:                   uyarı şablonu
   │                    ├─ Tarih                 │
   ▼                    ├─ Mazeret var mı?        ▼
PDKS / vardiya         ├─ Mazeretli mi?       Raporda kümülatif
verisinden tespit      └─ Açıklama             devamsızlık görünür
```

---

## 3. Fonksiyonel Gereksinimler — Detay

### 3.1 İzin Türleri Yönetimi

#### FR-IZN-01: İzin Türleri Tanımlama

**Açıklama:** İK yöneticisi sistem genelinde geçerli izin türlerini tanımlayabilmeli, özelliklerini konfigüre edebilmelidir.

**Varsayılan İzin Türleri:**

| Kod | İzin Türü | Ücretli | Belge Zorunlu | Yasal Dayanak | Yıllık Limit |
|-----|-----------|---------|---------------|---------------|--------------|
| `annual` | Yıllık Ücretli İzin | Evet | Hayır | 4857 Md. 53 | Kıdeme göre (oto) |
| `sick_reported` | Hastalık İzni (Raporlu) | Hayır (SGK öder) | Evet (rapor) | İş Kanunu | Sınırsız |
| `sick_unreported` | Raporsuz Hastalık İzni | Evet | Hayır | Firma politikası | 5 gün (örnek) |
| `marriage` | Evlilik İzni | Evet | Hayır | 4857 Md. 74 | 3 gün |
| `bereavement` | Ölüm İzni | Evet | Hayır | 4857 Md. 74 | 3 gün |
| `maternity` | Doğum/Analık İzni | Hayır (SGK öder) | Evet | 4857 Md. 74 | 16 hafta |
| `paternity` | Babalık İzni | Evet | Hayır | 4857 Md. 74 | 5 gün |
| `unpaid` | Ücretsiz İzin | Hayır | Hayır | 4857 Md. 56 | Anlaşmaya bağlı |
| `administrative` | İdari İzin | Evet | Hayır | İşveren kararı | — |
| `military_reserve` | Askerlik Tatbikat | Evet | Evet | 1111 Md. 43 | 90 gün/yıl |
| `exam` | Sınav İzni | Evet | Evet | Firma politikası | 2 gün/sınav |

**İzin Türü Konfigürasyonu:**

| Özellik | Açıklama |
|---------|----------|
| Yarım gün izin | İzin türü için AM/PM seçimi aktif edilebilir |
| Saatlik izin | Saat bazlı alınabilir mi (ör. doktor randevusu için 2 saat) |
| Belge zorunluluğu | Talep içinde belge yüklenmesi zorunlu mu |
| Kota tipi | Otomatik kıdem hesabı mı, sabit gün mü, sınırsız mı |
| Bakiye etkisi | Bakiyeyi düşür / sadece kayıt / bilgisel |
| Takvim rengi | Ekip takviminde gösterilecek hex renk |
| Ücretlilik | Bordro modülü için referans |
| Onay akışı | Direkt yönetici onayı mı, İK da onaylasın mı |
| Transfer edilebilir | Yıl sonu devredilsin mi |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVT-01 | `annual` kodu sistem genelinde rezerve edilmiştir; silinemez, devre dışı bırakılabilir |
| IK-LVT-02 | Bir izin türü, aktif talebi veya bakiyesi olan çalışan varken silinemez; `is_active = false` yapılır |
| IK-LVT-03 | Tenant başına en fazla 30 aktif izin türü tanımlanabilir |
| IK-LVT-04 | `code` alanı tenant içinde benzersiz olmalıdır |
| IK-LVT-05 | `allows_hourly = true` ise `allows_half_day` da otomatik true kabul edilir |

---

#### FR-IZN-02: Kıdeme Göre Otomatik Yıllık Kota Hesaplama

**Açıklama:** 4857 sayılı İş Kanunu'na uygun olarak çalışanın kıdemine göre yıllık ücretli izin hakkı otomatik hesaplanmalıdır.

**Yasal Kota Tablosu (4857 İş Kanunu Md. 53):**

| Kıdem | Yıllık İzin Hakkı | Not |
|-------|------------------|-----|
| 1 yıldan 5 yıla kadar (1 yıl dahil) | **14 iş günü** | Minimum |
| 5 yıldan 15 yıla kadar (5 yıl dahil) | **20 iş günü** | |
| 15 yıl ve üzeri | **26 iş günü** | |
| 18 yaş altı veya 50 yaş üstü | **20 iş günü** (minimum) | Yaşa göre artabilir |

> **Önemli:** İlk yıl tamamlanmadan izin hakkı doğmaz. 1 yıllık süre dolduğunda hak doğar.

**Kıdem Hesaplama Algoritması:**

```
Kıdem (yıl) = (Hesaplama tarihi − İşe giriş tarihi) / 365.25

Kıdem ≥ 1 yıl  → İzin hakkı doğmuştur
Kıdem < 1 yıl  → İzin hakkı yok (bazı firmalar orantılı vermek ister: opsiyonel)

Yıllık kota = yasal tablodan kıdeme göre seçim

Orantılı hesaplama (opsiyonel - 1. yıl için):
  Hak = (Kıdem yıl içi gün sayısı / 365) × kıdem kotası
```

**Hesaplama Tetikleyicileri:**

| Tetikleyici | Açıklama |
|-------------|----------|
| Yeni çalışan oluşturuldu | İşe giriş 1 yıl tamamlandığında kota oluşturulur (Celery scheduled job) |
| Yıl başı (1 Ocak) | Tüm aktif çalışanların o yılki kotası hesaplanır ve `leave_balances` güncellenir |
| Manuel yeniden hesaplama | İK'dan endpoint çağrısıyla; kıdem değişikliği veya hata düzeltmesinde |
| Çalışan işe giriş tarihi değiştirildi | Bakiye yeniden hesaplanır |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVK-01 | Kota hesaplamasında resmi tatiller iş günü sayısından çıkarılır |
| IK-LVK-02 | İlk yılını doldurmayan çalışana `annual` tipi bakiye oluşturulmaz (orantılı hak opsiyoneldir — tenant ayarı) |
| IK-LVK-03 | Mevcut yılda kıdem sınırı geçen çalışanın kotası o yıl içinde güncellenir (5. veya 15. yılını dolduran) |
| IK-LVK-04 | 18 yaş altı veya 50 yaş üstü çalışanlar için yasal minimum 20 gün uygulanır |
| IK-LVK-05 | Kota hesaplaması iş kanununa uygun olsun/olmasın tenant seviyesinde özelleştirilebilir (yukarıya yuvarlama serbesttir, aşağıya yuvarlama hata verir) |
| IK-LVK-06 | Mevcut yılda kullanılan izinler kota değiştirilse bile geri alınmaz |

---

#### FR-IZN-03: İzin Talebi Oluşturma

**Açıklama:** Çalışan veya İK, belirli türde ve tarih aralığında izin talebi oluşturabilmelidir.

**İzin Talebi Akışı:**

```
Talep Oluştur
    │
    ├── Çalışan (Self-Servis / Mobil)
    └── İK (yönetim paneli — çalışan adına)
            │
            ▼
Sistem validasyon kontrolleri:
    ├── Bakiye yeterli mi? (annual için)
    ├── Tarihler geçerli mi? (başlangıç ≤ bitiş)
    ├── Geçmiş tarih mi? (opsiyonel kural)
    ├── Aynı dönemde aktif talep var mı?
    ├── Resmi tatile denk mi? (uyarı verilir)
    └── Belge zorunlu mu? (hastalık vb.)
            │
            ▼
Validasyon geçtiyse:
    ├── Talep `pending` durumuyla kaydedilir
    ├── `leave_balances.pending_days` güncellenir
    └── Onay akışı başlatılır
```

**İzin Süresi Hesaplama:**

```
Toplam gün = (Bitiş tarihi − Başlangıç tarihi + 1)
           − (Aralıktaki haftasonu günleri)
           − (Aralıktaki resmi tatil günleri)

Yarım gün durumunda: +0.5 gün eklenir / çıkarılır
Saatlik durumda: toplam saat / günlük çalışma saati
```

**Yarım Gün İzin Modeli:**

| Seçim | Açıklama | Gün Değeri |
|-------|----------|------------|
| `am` (sabah yarısı) | Sabah biter, öğleden sonra gelir | 0.5 |
| `pm` (öğleden sonra yarısı) | Sabah gelir, öğleden sonra başlar | 0.5 |
| Tam gün | Serbest gün | 1.0 |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVR-01 | Bakiyesi yetersiz çalışan izin talebi oluşturamaz (ücretli izin türleri için); sıfır veya negatif bakiye hata döner |
| IK-LVR-02 | Başlangıç tarihi bitiş tarihinden ileri olamaz |
| IK-LVR-03 | Aynı çalışan aynı tarihte üst üste gelen iki aktif talebi olamaz: `LEAVE_OVERLAP` hatası |
| IK-LVR-04 | Onay bekleyen talep süresince `pending_days` bakiyeye yansır (düşülmüş gibi görünür) |
| IK-LVR-05 | Hastalık izni (raporlu) için belge yükleme zorunludur; belge yoksa talep `pending` durumda kalır, 3 iş günü içinde yüklenmezse otomatik İK uyarısı |
| IK-LVR-06 | Çalışan gelecek 6 ayı için talep oluşturabilir; daha uzun vadeli talepler İK onayıyla aktif edilir |
| IK-LVR-07 | Resmi tatile denk gelen günler otomatik izin süresinden düşülür; bilgilendirme mesajı gösterilir |
| IK-LVR-08 | Saat bazlı izin yalnızca `allows_hourly = true` olan türlerde oluşturulabilir |
| IK-LVR-09 | İzin talebi oluşturulduğunda talebin olduğu tüm onaylayıcılara bildirim gönderilir |

---

#### FR-IZN-04: Çok Seviyeli Onay Akışı

**Açıklama:** İzin talepleri, tenant konfigürasyonuna göre bir veya çok aşamalı onay sürecinden geçmelidir.

**Onay Modelleri:**

| Model | Açıklama | Kullanım |
|-------|----------|----------|
| **Direkt onay** | Yönetici → Onay/Red | Küçük firmalar, kısa izinler |
| **İki aşamalı** | Yönetici → İK → Onay/Red | Standart model |
| **Otomatik onay** | Belirli türler otomatik onaylanır | Evlilik, ölüm vb. |
| **Sadece bilgilendirme** | Talep kaydedilir, bildirim gider ama onay gerekmez | Ücretsiz izin kaydı |

**Onay Akış Diyagramı:**

```
Çalışan Talep Oluşturdu
    │
    ▼
[Adım 1] Doğrudan Yönetici
    │
    ├── ONAYLADI ──────────────────────────────────────────┐
    │                                                      │
    ├── REDDETTİ → Çalışana red bildirimi                  │
    │              Talep `rejected` olur                   │
    │                                                      ▼
    └── (İK onayı konfigüre edilmişse)              [Adım 2] İK Yöneticisi
                                                          │
                                                    ├── ONAYLADI → Talep `approved`
                                                    │              Bakiye güncellendi
                                                    │              Çalışana bildirim
                                                    │
                                                    └── REDDETTİ → Çalışana red bildirimi
                                                                   Talep `rejected` olur
```

**Onaylayıcı Belirleme:**

| Durum | Onaylayıcı |
|-------|-----------|
| Çalışanın yöneticisi tanımlı | Doğrudan yönetici (personnel_employees.manager_id) |
| Yönetici tanımlı değil | İK yöneticisi birinci onaylayıcı olur |
| Yönetici de izindeyse | Yöneticinin yöneticisi veya İK devralır (tenant ayarı) |
| Çalışan yönetici ise | İK birinci onaylayıcı olur |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVA-01 | Onaylayıcı kendi talebini onaylayamaz; sistem otomatik olarak bir üst onaylayıcıya yönlendirir |
| IK-LVA-02 | Onay adımları sıralıdır; birinci adım tamamlanmadan ikinci başlamaz |
| IK-LVA-03 | Her onaylayıcı onay/red kararını gerekçe ile verebilir |
| IK-LVA-04 | Red gerekçesi çalışana bildirimde gösterilir |
| IK-LVA-05 | Tüm adımlar onaylandığında talep `approved`; bakiye kesinleşir (`used_days` artar, `pending_days` azalır) |
| IK-LVA-06 | Yönetici 3 iş günü içinde yanıt vermezse İK'ya eskalasyon bildirimi gider (Celery beat) |
| IK-LVA-07 | İzinli yöneticinin taleplerini genişletilmiş yetkili devralır (vekil ataması — 19-modul-self-servis-portal.md kapsamında) |
| IK-LVA-08 | Otomatik onaylanacak izin türleri açıldığında `leave_approval_flows` kaydı oluşmaz; talep direkt `approved` olur |

---

#### FR-IZN-05: İzin Bakiyesi Görüntüleme

**Açıklama:** Çalışan ve yöneticiler anlık izin bakiyelerini, geçmiş kullanımlarını ve bekleyen talepleri görebilmelidir.

**Bakiye Kartı (UI):**

```
┌──────────────────────────────────────────────┐
│  YILLIK ÜCRETLİ İZİN — 2026                 │
│                                              │
│  Toplam Hak:      20 gün   (kıdem: 6 yıl)   │
│  Geçen Yıldan:   +2 gün   (devir)           │
│  ─────────────────────────                   │
│  Kullanılan:      5 gün                      │
│  Onay Bekleyen:   3 gün                      │
│  ─────────────────────────                   │
│  Kalan Bakiye:   14 gün   ████████████░░     │
└──────────────────────────────────────────────┘
```

**Bakiye Formülü:**

```
remaining_days = total_days + carried_over_days - used_days - pending_days
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVB-01 | `remaining_days` PostgreSQL GENERATED ALWAYS kolonudur; manuel güncellenemez |
| IK-LVB-02 | İK, hata düzeltmesi için bakiye manuel ayarlayabilir (`leave:balance:update` yetkisi); her ayarlama audit log'a yazılır |
| IK-LVB-03 | Çalışan yalnızca kendi bakiyesini görebilir; yönetici ekibinin bakiyesini görür; İK hepsini görür |
| IK-LVB-04 | Negatif bakiyeye izin verilip verilmeyeceği tenant bazlı konfigürasyonla belirlenir |
| IK-LVB-05 | Bakiye geçmişi (her tahakkuk ve düşüm) `leave_balance_transactions` tablosunda loglanır |

---

#### FR-IZN-06: Ekip / Departman İzin Takvimi

**Açıklama:** Yöneticiler ve çalışanlar takvim görünümünde ekip izinlerini, resmi tatilleri ve hafta sonlarını görebilmelidir.

**Takvim Görünümü:**

```
┌──────────────────────────────────────────────────────────────────────┐
│              NİSAN 2026 — Yazılım Geliştirme Departmanı              │
├────────┬────────┬────────┬────────┬────────┬────────┬────────────────┤
│  Pzt   │  Sal   │  Çar   │  Per   │  Cum   │  Ctsi  │  Paz           │
├────────┼────────┼────────┼────────┼────────┼────────┼────────────────┤
│   6    │   7    │   8    │   9    │  10    │        │                │
│ Ahmet ─│ Ahmet ─│        │        │        │        │                │
│ (yıllık│ (yıllık│        │        │        │        │                │
├────────┼────────┼────────┼────────┼────────┼────────┼────────────────┤
│  13    │  14    │  15    │  16    │  17    │        │                │
│        │ Elif ─ │ Elif ─ │ Elif ─ │ 🎉 MİLLİ│        │                │
│        │ (yıllık│ (yıllık│ (yıllık│EGEM.   │        │                │
├────────┼────────┼────────┼────────┼────────┼────────┼────────────────┤
│  20    │  21    │  22    │  23    │  24    │        │                │
│ Can ──→│ Can ──→│ Can ──→│        │  🎉 PAZAR│        │                │
│(hastalık(hastalık(hastalık│       │ BAYRAMII│        │                │
└────────┴────────┴────────┴────────┴────────┴────────┴────────────────┘

 ■ Yıllık İzin   ■ Hastalık   🎉 Resmi Tatil   ░ Onay Bekleyen
```

**Takvim Özellikleri:**

| Özellik | Açıklama |
|---------|----------|
| Görünüm modları | Aylık, haftalık, günlük |
| Filtreler | Departman, çalışan, izin türü |
| Çakışma uyarısı | Aynı günde birden fazla çalışan izinliyse renk koyulaşır |
| Kapasite göstergesi | Belirli günde ekibin yüzde kaçı izinli (ısı haritası) |
| Resmi tatiller | Kırmızı/sarı şerit ile gösterilir |
| Bekleyen talepler | Çizgili gösterim |
| Mobil | Kaydırmalı haftalık görünüm |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVC-01 | Çalışan yalnızca onaylanan (ve opsiyonel olarak bekleyen) kendi izinlerini ve ekip onaylı izinlerini görebilir |
| IK-LVC-02 | Yönetici kendi departmanındaki tüm izinleri görebilir |
| IK-LVC-03 | Takvim verileri Redis'te 5 dakika cache'lenir |
| IK-LVC-04 | Çok departmandaki çalışanlar için ekip filtresi yönetici grubu bazında çalışır |

---

#### FR-IZN-07: Yıl Sonu İzin Devri (Carry-Over)

**Açıklama:** Her yıl sonunda kalan izin bakiyeleri belirlenen politikaya göre devredilmeli veya sıfırlanmalıdır.

**Devir Politika Seçenekleri:**

| Politika | Açıklama | Örnek |
|---------|----------|-------|
| **Tam devir** | Kalan bakiyenin tamamı sonraki yıla aktarılır | 5 gün kaldı → 5 gün devir |
| **Üst limitli devir** | Belirli günden fazlası devredilmez | Maks 5 gün devir; 8 kalan → 5 devir |
| **Orantılı devir** | Kalan bakiyenin belirli oranı devredilir | %50 devir; 8 kalan → 4 devir |
| **Sıfırlama** | Kalan bakiye devredilmez, sıfırlanır | 5 gün kaldı → 0 devir |
| **Vade süreli devir** | Devreden bakiye X ay içinde kullanılmazsa düşer | 3 ay içinde kullanılmazsa düşer |

**Devir İşlem Akışı (Celery Beat — 31 Aralık gece yarısı):**

```
Yıl Sonu Celery Job (31 Aralık 23:59 veya 1 Ocak 00:01)
    │
    ▼
Tüm aktif kiracılar için döngü:
    │
    ├── Tenant izin devir politikası okunur
    │
    ├── Her çalışan için:
    │   ├── Mevcut yıl `leave_balances` okunur (annual türü)
    │   ├── remaining_days hesaplanır
    │   ├── Politikaya göre carried_over_days hesaplanır
    │   ├── Yeni yıl için `leave_balances` kaydı oluşturulur:
    │   │   ├── total_days = kıdeme göre yeni yılın kotası
    │   │   └── carried_over_days = hesaplanan devir
    │   └── `leave_balance_transactions` log kaydı
    │
    └── İK'ya devir özet raporu e-posta ile gönderilir
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVD-01 | Devir politikası yalnızca `annual` tipi izine uygulanır; diğer türler yıl başında sıfırlanır |
| IK-LVD-02 | Devir işlemi idempotent olmalıdır; tekrar çalıştırılırsa mevcut yıl bakiyesini çiftlemez |
| IK-LVD-03 | Vade süreli devirde son kullanma tarihi geçen günler Celery job ile otomatik düşülür ve loglenir |
| IK-LVD-04 | İK, bireysel çalışan için devir gün sayısını manuel ayarlayabilir (audit log zorunlu) |
| IK-LVD-05 | Yeni yıl kotası hesaplandıktan sonra çalışana "İzin hakları güncellendi" bildirimi gönderilir |

---

#### FR-IZN-08: Yarım Gün ve Saatlik İzin

**Açıklama:** İzin türüne göre tam gün dışında yarım gün (AM/PM) veya saat aralığı belirterek izin talep edilebilmelidir.

**Yarım Gün Seçenekleri:**

| Seçim | Gün Etkisi | Açıklama |
|-------|-----------|----------|
| Tüm gün | 1.0 gün | Standart |
| Sabah yarısı (AM) | 0.5 gün | Sabah başlar, öğle biter |
| Öğleden sonra yarısı (PM) | 0.5 gün | Öğle başlar, akşam biter |

**Saatlik İzin:**

| Alan | Açıklama |
|------|----------|
| Başlangıç saati | HH:MM formatında |
| Bitiş saati | HH:MM formatında |
| Süre (otomatik) | Bitiş − Başlangıç |
| Gün etkisi | Toplam saat / Günlük çalışma saati (8 saat) |

**Örnek Saatlik Hesaplama:**

```
Doktor randevusu — 3 saatlik izin:
  Gün etkisi = 3 / 8 = 0.375 gün

Bakiye düşümü: 0.375 gün (0.5'e yuvarlama — tenant ayarı opsiyonel)
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVH-01 | Yarım gün izin yalnızca izin türünün `allows_half_day = true` olduğu durumlarda seçilebilir |
| IK-LVH-02 | Saatlik izin yalnızca `allows_hourly = true` olan türlerde oluşturulabilir |
| IK-LVH-03 | Saatlik izinde bitiş saati başlangıç saatinden ileri olmalıdır |
| IK-LVH-04 | Aynı gün sabah AM + öğleden sonra PM talep = tam gün izin; çakışma kontrolü bunu engeller |
| IK-LVH-05 | Saatlik bakiye yuvarlama stratejisi tenant ayarında belirlenir (0.1'e veya 0.5'e) |

---

#### FR-IZN-09: Resmi Tatil Takvimi

**Açıklama:** Türkiye resmi tatilleri ve şirkete özel tatil günleri sistemde tanımlı olmalı; izin süreleri hesaplanırken tatil günleri otomatik düşülmelidir.

**Türkiye Resmi Tatilleri:**

| Tarih | Tatil | Gün Sayısı |
|-------|-------|-----------|
| 1 Ocak | Yılbaşı | 1 gün |
| 23 Nisan | Ulusal Egemenlik ve Çocuk Bayramı | 1 gün |
| 1 Mayıs | Emek ve Dayanışma Günü | 1 gün |
| 19 Mayıs | Atatürk'ü Anma, Gençlik ve Spor Bayramı | 1 gün |
| 15 Temmuz | Demokrasi ve Millî Birlik Günü | 1 gün |
| 30 Ağustos | Zafer Bayramı | 1 gün |
| 29 Ekim | Cumhuriyet Bayramı | 1 gün |
| Ramazan Bayramı | Dini tatil (Hicri takvim) | 3,5 gün |
| Kurban Bayramı | Dini tatil (Hicri takvim) | 4,5 gün |

**Tatil Yönetim Özellikleri:**

| Özellik | Açıklama |
|---------|----------|
| Otomatik yıllık yükleme | Sabit Gregoryen tarihli tatiller her yıl otomatik oluşturulur |
| Hicri takvim | Ramazan ve Kurban tatilleri yıllık Diyanet takvimi baz alınarak İK tarafından eklenir |
| Özel tatil | Şirkete özel tatil/idari izin günü tanımlanabilir |
| Bölgesel tatil | Şube bazlı (İstanbul, Ankara vb.) özel tatil desteği |
| Yarım gün tatil | Bayram arife günleri için 0.5 olarak işaretlenebilir |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVT2-01 | Resmi tatil günlerine denk gelen izin günleri hesaplamaya dahil edilmez; otomatik düşülür |
| IK-LVT2-02 | Hicri takvim tatilleri İK müdürü tarafından yıllık olarak sisteme eklenir |
| IK-LVT2-03 | Resmi tatil çalışma günü olarak işlenmişse (İK tarafından iptal edilmişse) izin hesaplamaya dahil edilir |
| IK-LVT2-04 | Şirket özel tatil günleri çalışanın bağlı olduğu şubeye göre uygulanır |
| IK-LVT2-05 | Tatil günü kütüphanesi her yıl 1 Kasım'dan sonra günlük kontrol ile İK'ya hatırlatma gönderilir |

---

#### FR-IZN-10: Devamsızlık Takibi

**Açıklama:** İzin talebi olmadan işe gelmeyen çalışanların devamsızlık kaydı oluşturulabilmeli, kümülatif takip yapılabilmelidir.

**Devamsızlık Türleri:**

| Kod | Tür | Açıklama | Ücret Etkisi |
|-----|-----|----------|--------------|
| `excused` | Mazeretli | Sonradan gerekçe sunuldu | Firma politikasına göre |
| `unexcused` | Mazeretsiz | Hiçbir gerekçe yok | Ücret kesintisi |
| `late` | Geç gelme | Mesai saatinden sonra | Opsiyonel — firma politikası |
| `early_leave` | Erken çıkış | İzinsiz erken ayrılma | Opsiyonel |

**Devamsızlık Kaydı Akışı:**

```
Çalışan işe gelmedi
    │
    ├── PDKS / Vardiya verisi → Otomatik tespit (16 no'lu modül entegrasyonu)
    └── İK manuel kayıt → Devamsızlık formu
            │
            ▼
Devamsızlık kaydı oluşturuldu
    │
    ▼
Yöneticiye bildirim
    │
    ▼
İK uyarı mekanizması:
    ├── 1. mazeretsiz devamsızlık → Yazılı uyarı (şablon e-posta)
    ├── 3. mazeretsiz devamsızlık → İK müdürüne eskalasyon bildirimi
    └── 5+ mazeretsiz devamsızlık → Disiplin süreci uyarısı
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVX-01 | Devamsızlık kaydı geriye dönük en fazla 30 gün için oluşturulabilir |
| IK-LVX-02 | Mazeretsiz devamsızlık sonradan mazeretli yapılabilir (İK onayıyla); audit log kaydı oluşur |
| IK-LVX-03 | Devamsızlık, çalışanın yıllık izin hakkından otomatik düşülmez; ancak ücret kesintisi bordro modülüne bilgi olarak iletilir |
| IK-LVX-04 | Kümülatif devamsızlık sayacı takvim yılı bazında tutulur |
| IK-LVX-05 | Devamsızlık kaydının olduğu günlerde çalışanın izin talebi varsa çakışma uyarısı verilir |

---

#### FR-IZN-11: Mobil İzin Talebi ve Onayı

**Açıklama:** Çalışan mobil cihazdan izin talebi oluşturabilmeli; yönetici mobil üzerinden tek tuş onayla/reddet işlemini yapabilmelidir.

**Mobil Deneyim Özellikleri:**

| Özellik | Açıklama |
|---------|----------|
| Hızlı talep | 3 adımda (türü seç, tarihi gir, gönder) |
| Push bildirimi | Yöneticiye talep, çalışana onay/red push gelir |
| Tek tuş onay | Yönetici push bildiriminden direkt onayla/reddet |
| Bakiye widget | Ana ekranda kalan izin bakiyesi kartı |
| Takvim | Kaydırmalı haftalık takvim, ekip izinleri |

**Mobile-First Ekranlar:**

```
┌─────────────────────────┐    ┌─────────────────────────┐
│ ◀  İzin Talebi          │    │ ◀  Yönetici Onayı        │
├─────────────────────────┤    ├─────────────────────────┤
│                         │    │                         │
│ İzin Türü               │    │ 👤 Zeynep Kaya           │
│ [Yıllık Ücretli ▼]      │    │ Yıllık İzin Talebi       │
│                         │    │ 21 – 25 Nisan 2026       │
│ Başlangıç Tarihi        │    │ 5 iş günü                │
│ [  21 Nisan 2026  ]     │    │                         │
│                         │    │ Bakiye: 14/20 gün        │
│ Bitiş Tarihi            │    │ Çakışma: Yok             │
│ [  25 Nisan 2026  ]     │    │                         │
│                         │    │ "Yıllık tatil için"      │
│ Süre: 5 iş günü         │    │                         │
│ Kalan bakiye:           │    │ [  ONAYLA  ] [  REDDET  ]│
│ 14 → 9 gün olacak      │    │                         │
│                         │    │ Red gerekçesi:          │
│ Açıklama (opsiyonel)    │    │ [___________________]   │
│ [Yıllık tatil için ]    │    │                         │
│                         │    │                         │
│ [   TALEP OLUŞTUR   ]   │    │                         │
└─────────────────────────┘    └─────────────────────────┘
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVM-01 | Push bildiriminde "Onayla" ve "Reddet" aksiyonu doğrudan bildirimden yapılabilir (iOS/Android notification action) |
| IK-LVM-02 | Mobil red işleminde gerekçe girişi zorunludur |
| IK-LVM-03 | Çevrimdışı talep taslak olarak saklanır, çevrimiçi olunca gönderilir |

---

#### FR-IZN-12: Toplu İdari İzin Tanımlama

**Açıklama:** İK yöneticisi belirli bir departman, şube veya tüm şirkete idari izin günü ekleyebilmelidir (ör. fabrika bakım hafta kapanışı).

**Toplu İzin Tanımlama Parametreleri:**

| Alan | Açıklama |
|------|----------|
| Hedef kitle | Tüm şirket / Şube(ler) / Departman(lar) / Pozisyon grubu |
| Tarih aralığı | Tek gün veya dönem |
| İzin türü | Genellikle `administrative` |
| Açıklama | "Fabrika bakım kapanışı", "Yılbaşı uzun hafta sonu" |
| Onay gerekli mi | Toplu idari izinde onay akışı gerekmez; direkt `approved` olur |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVT3-01 | Toplu idari izin `leave:bulk:create` yetkisi gerektirir |
| IK-LVT3-02 | Toplu izin mevcut bireysel izinlerle çakışmaz; ayrı kayıt oluşturulur, kullanıcıya bildirim gider |
| IK-LVT3-03 | Toplu idari izin bakiyeyi düşürmez (ücretli, işverenin verdiği); `is_employer_granted = true` işaretlenir |
| IK-LVT3-04 | İptal edildiğinde etkilenen tüm çalışanlara bildirim gönderilir |

---

#### FR-IZN-13: İzin İptali ve Değişikliği

**Açıklama:** Onay bekleyen veya onaylanmış izin talepleri belirli kurallara uygun şekilde iptal edilebilmeli ya da tarihleri değiştirilebilmelidir.

**İptal / Değişiklik Seneryoları:**

| Durum | İzin Veren | Kural |
|-------|-----------|-------|
| `pending` iptali | Çalışan kendisi | Onay akışı atlanır; anında iptal |
| `approved` iptali — henüz başlamadı | Çalışan | Yönetici onayı gerekir |
| `approved` iptali — devam eden | Çalışan veya İK | İK onayı gerekir; kullanılan günler düşülür |
| Tarih değişikliği | Çalışan | Mevcut talep iptal, yeni talep açılır; onay akışı tekrar başlar |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-LVI-01 | Başlamış izin başlangıç tarihi değiştirilemez; yalnızca bitiş tarihi kısaltılabilir |
| IK-LVI-02 | İptal edildiğinde `pending_days` veya `used_days` ilgili kısım geri eklenir |
| IK-LVI-03 | İzin kullanılmış dönemler geri alınamaz (geçmiş günler için kısmi iptal: sadece gelecekteki günler iade edilir) |
| IK-LVI-04 | 3 günden uzun süreli onaylanmış izinlerin iptali İK'ya bildirim gönderir |
| IK-LVI-05 | İptal gerekçesi zorunludur |

---

## 4. Veritabanı Tasarımı

### 4.1 Tablo İlişkisi

07-veritabani-tasarimi.md Bölüm 5.2'deki tablolara ek detaylar aşağıdadır.

```
leave_types ──────────────────── leave_balances
     │                                 │
     └── leave_requests ───────────────┘
              │
              ├── leave_approval_flows
              │
              └── leave_balance_transactions (log)

leave_absences (devamsızlık kayıtları)
     │
     └── personnel_employees (çalışan)

public_holidays (resmi tatiller)
     │
     └── tenant_id (şirkete özel tatiller dahil)
```

### 4.2 Ek Tablolar

#### `leave_balance_transactions` — Bakiye İşlem Geçmişi

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `leave_type_id` | BIGINT, FK | |
| `year` | SMALLINT | |
| `transaction_type` | VARCHAR(30) | `accrual`, `used`, `reversed`, `carry_over`, `adjustment`, `expire` |
| `days` | NUMERIC(5,1) | Pozitif: ekleme, Negatif: düşüm |
| `reference_id` | BIGINT, nullable | İlgili leave_request.id veya carry-over job id |
| `note` | TEXT, nullable | Düzeltme notları |
| `created_by` | BIGINT, FK → auth_users | İşlemi yapan (sistem = 0) |
| `created_at` | TIMESTAMPTZ | |

#### `leave_absences` — Devamsızlık Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `absence_date` | DATE | Devamsızlık günü |
| `absence_type` | VARCHAR(20) | `unexcused`, `excused`, `late`, `early_leave` |
| `duration_hours` | NUMERIC(4,1), nullable | Geç gelme / erken çıkış için saat |
| `reason` | TEXT, nullable | Mazeret açıklaması |
| `is_excused` | BOOLEAN, default: false | Sonradan mazeret kabul edildi mi |
| `excused_by` | BIGINT, FK, nullable | Mazereti kabul eden |
| `excused_at` | TIMESTAMPTZ, nullable | Kabul zamanı |
| `created_by` | BIGINT, FK | Kaydı oluşturan (İK veya sistem) |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**İndeksler:**

```sql
CREATE INDEX ix_leave_absences_tenant_emp ON leave_absences (tenant_id, employee_id);
CREATE INDEX ix_leave_absences_date ON leave_absences (tenant_id, absence_date);
```

#### `public_holidays` — Resmi Tatil Takvimi

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK, nullable | null = tüm tenantlar için geçerli (sistem geneli) |
| `branch_id` | BIGINT, FK, nullable | null = tüm şubeler |
| `name` | VARCHAR(100) | Tatil adı |
| `holiday_date` | DATE | Tatil tarihi |
| `duration` | NUMERIC(3,1), default: 1.0 | Tatil gün sayısı (0.5 = arife yarım günü) |
| `is_recurring` | BOOLEAN, default: true | Her yıl tekrar eden mi (Gregori takvim) |
| `year` | SMALLINT, nullable | Tekrar etmiyorsa hangi yılın tatili |
| `is_active` | BOOLEAN, default: true | |

**İndeksler:**

```sql
CREATE INDEX ix_public_holidays_date ON public_holidays (holiday_date, tenant_id);
CREATE INDEX ix_public_holidays_year ON public_holidays (year, tenant_id);
```

#### `leave_policy_settings` — İzin Politika Ayarları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK, UNIQUE | Tenant başına tek kayıt |
| `carryover_policy` | VARCHAR(20) | `full`, `capped`, `percentage`, `none` |
| `carryover_max_days` | NUMERIC(5,1), nullable | `capped` politikasında maksimum devir günü |
| `carryover_percentage` | SMALLINT, nullable | `percentage` politikasında devir yüzdesi |
| `carryover_expiry_months` | SMALLINT, nullable | Devreden bakiye kaç ay içinde kullanılmalı |
| `allow_negative_balance` | BOOLEAN, default: false | Negatif bakiyeye izin verilsin mi |
| `proportional_first_year` | BOOLEAN, default: false | İlk yılda orantılı kota verilsin mi |
| `approval_model` | VARCHAR(20) | `manager_only`, `manager_then_hr`, `auto` |
| `escalation_days` | SMALLINT, default: 3 | Kaç iş günü yanıt gelmezse eskalasyon |
| `hourly_rounding` | VARCHAR(10) | `none`, `half`, `full` — saatlik bakiye yuvarlama |
| `work_hours_per_day` | NUMERIC(4,1), default: 8.0 | Saatlik izin hesabı için referans |

### 4.3 Mevcut Tablolara Ek İndeksler

```sql
-- leave_requests için ek sorgular
CREATE INDEX ix_leave_requests_dates ON leave_requests (tenant_id, start_date, end_date);
CREATE INDEX ix_leave_requests_status_emp ON leave_requests (tenant_id, employee_id, status)
    WHERE status IN ('pending', 'approved');

-- leave_balances cache sorgusu
CREATE INDEX ix_leave_balances_emp_year ON leave_balances (tenant_id, employee_id, year);

-- leave_approval_flows eskalasyon sorgusu
CREATE INDEX ix_leave_approval_flows_pending ON leave_approval_flows (status, acted_at)
    WHERE status = 'pending';
```

---

## 5. API Endpoint Detayları

Tüm izin endpoint'leri `/api/v1/leave` prefix'i altındadır (08-api-tasarimi.md, Bölüm 15.4).

### 5.1 İzin Türleri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/types` | İzin türleri listesi | Auth |
| `POST` | `/leave/types` | Yeni izin türü oluştur | `leave:type:create` |
| `PUT` | `/leave/types/{id}` | İzin türü güncelle | `leave:type:update` |
| `PATCH` | `/leave/types/{id}/deactivate` | İzin türünü devre dışı bırak | `leave:type:update` |

### 5.2 İzin Talepleri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/requests` | İzin talepleri listesi (filtrelenebilir) | `leave:request:read` |
| `POST` | `/leave/requests` | İK adına izin talebi oluştur | `leave:request:create` |
| `GET` | `/leave/requests/{id}` | İzin talebi detayı | `leave:request:read` |
| `PATCH` | `/leave/requests/{id}/approve` | Talebi onayla | `leave:request:approve` |
| `PATCH` | `/leave/requests/{id}/reject` | Talebi reddet (gerekçe zorunlu) | `leave:request:approve` |
| `PATCH` | `/leave/requests/{id}/cancel` | Talebi iptal et | `leave:request:cancel` |
| `GET` | `/leave/requests/pending` | Onay bekleyen talepler (yönetici görünümü) | `leave:request:approve` |

### 5.3 Bakiye Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/balances` | Tüm çalışan bakiyeleri | `leave:balance:read` |
| `GET` | `/leave/balances/{employee_id}` | Çalışana ait bakiye dökümü | `leave:balance:read` |
| `POST` | `/leave/balances/recalculate` | Bakiyeleri yeniden hesapla | `leave:balance:update` |
| `PATCH` | `/leave/balances/{id}/adjust` | Manuel bakiye düzeltmesi (İK) | `leave:balance:update` |
| `GET` | `/leave/balances/{employee_id}/transactions` | Bakiye işlem geçmişi | `leave:balance:read` |

### 5.4 Takvim ve Raporlama

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/calendar` | Departman/ekip izin takvimi | `leave:request:read` |
| `GET` | `/leave/calendar/export` | Takvim iCal veya Excel export | `leave:request:read` |
| `GET` | `/leave/reports/summary` | Dözel izin özet raporu | `leave:report:read` |
| `GET` | `/leave/reports/absence` | Devamsızlık raporu | `leave:report:read` |
| `GET` | `/leave/reports/remaining` | Kalan bakiye raporu | `leave:report:read` |

### 5.5 Devamsızlık

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/absences` | Devamsızlık listesi (filtreli) | `leave:absence:read` |
| `POST` | `/leave/absences` | Devamsızlık kaydı oluştur | `leave:absence:create` |
| `PATCH` | `/leave/absences/{id}/excuse` | Devamsızlığı mazerete çevir | `leave:absence:update` |
| `GET` | `/leave/absences/{employee_id}` | Çalışanın devamsızlık geçmişi | `leave:absence:read` |

### 5.6 Resmi Tatiller ve Politika

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/leave/holidays` | Yıllık tatil listesi | Auth |
| `POST` | `/leave/holidays` | Özel tatil tanımla | `leave:holiday:create` |
| `DELETE` | `/leave/holidays/{id}` | Tatil sil | `leave:holiday:create` |
| `GET` | `/leave/policy` | Tenant izin politikası | `leave:policy:read` |
| `PUT` | `/leave/policy` | Tenant izin politikası güncelle | `leave:policy:update` |

### 5.7 Self-Servis Endpoint'leri (çalışan kendi talebi)

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/leaves` | Kendi izin talepleri | Auth |
| `POST` | `/me/leaves` | Yeni izin talebi oluştur | Auth |
| `DELETE` | `/me/leaves/{id}` | Bekleyen talebi iptal et | Auth |
| `GET` | `/me/leave-balances` | Kendi bakiyeleri | Auth |
| `GET` | `/me/leave-calendar` | Kendi ve ekip takvimi | Auth |

### 5.8 Örnek Request / Response

#### POST `/api/v1/me/leaves` — İzin Talebi Oluşturma

**Request Body:**

```json
{
  "leave_type_id": 1,
  "start_date": "2026-04-21",
  "end_date": "2026-04-25",
  "start_half": null,
  "end_half": null,
  "reason": "Yıllık tatil planı",
  "document_url": null
}
```

**Response (201 Created):**

```json
{
  "success": true,
  "data": {
    "id": 123,
    "leave_type": {
      "id": 1,
      "name": "Yıllık Ücretli İzin",
      "code": "annual"
    },
    "start_date": "2026-04-21",
    "end_date": "2026-04-25",
    "total_days": 5.0,
    "status": "pending",
    "balance_before": 14.0,
    "balance_after_approval": 9.0,
    "approval_steps": [
      {
        "step_order": 1,
        "approver": "Mehmet Demir",
        "status": "pending"
      }
    ],
    "created_at": "2026-04-10T10:30:00Z"
  }
}
```

**Olası Hata Kodları:**

| HTTP | Kod | Açıklama |
|------|-----|----------|
| 400 | `VALIDATION_ERROR` | Eksik alan veya geçersiz tarih formatı |
| 409 | `LEAVE_OVERLAP` | Aynı dönemde aktif talep mevcut |
| 422 | `INSUFFICIENT_LEAVE_BALANCE` | Bakiye yetersiz |
| 422 | `LEAVE_TYPE_NOT_ALLOWED` | İzin türü yarım gün / saat desteği yok |
| 422 | `APPROVAL_NOT_ALLOWED` | Kendi talebini onaylama girişimi |
| 404 | `LEAVE_TYPE_NOT_FOUND` | Belirtilen izin türü bulunamadı |

---

## 6. Ekran Tasarımı Rehberi

### 6.1 Ekran Listesi

| # | Ekran | Platform | Rol | Öncelik |
|---|-------|----------|-----|---------|
| 1 | İzin Talebi Oluşturma | Web + Mobil | Çalışan | Must |
| 2 | Kendi İzin Talepleri Listesi | Web + Mobil | Çalışan | Must |
| 3 | İzin Bakiyesi Kartı | Web + Mobil | Çalışan | Must |
| 4 | Ekip / Departman Takvimi | Web + Mobil | Yönetici, Çalışan | Must |
| 5 | Onay Bekleyen Talepler | Web + Mobil | Yönetici | Must |
| 6 | İzin Yönetim Paneli (İK) | Web | İK | Must |
| 7 | İzin Türleri Tanımı | Web | İK | Must |
| 8 | Bakiye Yönetimi | Web | İK | Must |
| 9 | Devamsızlık Kayıt ve Liste | Web | İK, Yönetici | Must |
| 10 | İzin Raporları | Web | İK, C-Level | Must |
| 11 | Politika Ayarları | Web | İK, Süper Admin | Must |
| 12 | Toplu İzin Tanımlama | Web | İK | Should |
| 13 | Resmi Tatil Takvimi Yönetimi | Web | İK | Must |

### 6.2 İzin Talebi Oluşturma (Web)

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ Profilim  /  İzin Talebi Oluştur                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ İzin Türü                                                    │
│ ┌─────────────────────────────────────────────────────────┐  │
│ │ ○ Yıllık Ücretli İzin    (Kalan: 14 gün)                │  │
│ │ ○ Raporsuz Hastalık       (Kalan: 3 gün)                │  │
│ │ ○ Evlilik İzni            (Kalan: 3 gün)                │  │
│ │ ○ Ücretsiz İzin                                         │  │
│ │ ○ Diğer...                                              │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ Tarih Aralığı                                                │
│ [  21 Nisan 2026  ] ──── [  25 Nisan 2026  ]                │
│                                                              │
│ Süre: 5 iş günü  ⚠️ 23 Nisan Resmi Tatil — otomatik hariç  │
│                                                              │
│ Yarım Gün?  ○ Hayır  ○ Sabah  ○ Öğleden Sonra               │
│                                                              │
│ Açıklama (opsiyonel)                                         │
│ [____________________________________________________]       │
│                                                              │
│ Belge Yükle (raporlu hastalık için zorunlu)                  │
│ [📎 Dosya Seç]                                               │
│                                                              │
│ Bakiye Önizleme:                                             │
│ ┌─────────────────────────────────────────────────────────┐  │
│ │ Mevcut: 14 gün    │   Kullanılacak: 5 gün               │  │
│ │ Onay sonrası kalan: 9 gün                               │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│               [ TALEP OLUŞTUR ]   [ İptal ]                  │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 Yönetici Onay Paneli (Web)

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ İK Paneli  /  İzin Onaylarım                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Onay Bekleyen: 3 talep                          [Tümünü Gör]│
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 👤 Zeynep Kaya      ← Yıllık Ücretli İzin             │   │
│ │ 21 – 25 Nisan 2026 (5 gün) · Talep: 2 saat önce       │   │
│ │ Bakiye: 14/20 gün ✅ Çakışma yok                       │   │
│ │ "Yıllık tatil planı"                                   │   │
│ │                              [ ONAYLA ] [ REDDET ]     │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 👤 Can Demir        ← Raporsuz Hastalık İzni           │   │
│ │ 10 Nisan 2026 (1 gün) · Talep: 1 gün önce             │   │
│ │ Bakiye: 5/5 gün ✅ Çakışma yok                         │   │
│ │                                                        │   │
│ │                              [ ONAYLA ] [ REDDET ]     │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 👤 Ahmet Yılmaz     ← Yıllık Ücretli İzin             │   │
│ │ 4 – 8 Mayıs 2026 (5 gün) · Talep: 3 gün önce          │   │
│ │ Bakiye: 20/20 gün ✅                                    │   │
│ │ ⚠️ Aynı dönem: Elif Kaya da izin talep etti (beklemede)│   │
│ │                                                        │   │
│ │                              [ ONAYLA ] [ REDDET ]     │   │
│ └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 6.4 İK İzin Yönetim Paneli

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ İK Paneli  /  İzin Yönetimi                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ [İzin Talepleri] [Bakiyeler] [Devamsızlık] [Takvim]         │
│ [İzin Türleri] [Politika] [Raporlar]                        │
│                                                              │
│ ──── İzin Talepleri ────────────────────────────────────      │
│ Filtreler: [Durum ▼] [Departman ▼] [Tarih Aralığı ▼]        │
│                                                              │
│ ┌──────────┬─────────────────┬──────┬──────────┬──────────┐  │
│ │ Çalışan  │ İzin Türü       │ Süre │ Durum    │ Onaylayıcı│ │
│ ├──────────┼─────────────────┼──────┼──────────┼──────────┤  │
│ │ Zeynep K.│ Yıllık Ücretli  │ 5 gün│ ⏳ Bekl. │ M. Demir │  │
│ ├──────────┼─────────────────┼──────┼──────────┼──────────┤  │
│ │ Can D.   │ Raporsuz Hast.  │ 1 gün│ ✅ Onaylı │ M. Demir │  │
│ ├──────────┼─────────────────┼──────┼──────────┼──────────┤  │
│ │ Ahmet Y. │ Yıllık Ücretli  │ 5 gün│ ❌ Reddld │ M. Demir │  │
│ └──────────┴─────────────────┴──────┴──────────┴──────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 6.5 Mobil — Bakiye ve Hızlı Talep

```
┌─────────────────────────┐
│ ◀  İzin           + Yeni│
├─────────────────────────┤
│                         │
│ ┌─────────────────────┐ │
│ │ Yıllık İzin — 2026  │ │
│ │ ████████████░░░     │ │
│ │ 14 / 20 gün kaldı   │ │
│ └─────────────────────┘ │
│                         │
│ Son Taleplerim          │
│ ──────────────────────  │
│ ✅ 21-25 Nis · 5 gün    │
│    Onaybekleniyor       │
│                         │
│ ✅ 10 Mar · 1 gün       │
│    Onaylandı            │
│                         │
│ ❌ 15 Şub · 3 gün       │
│    Reddedildi           │
│    "Proje teslim dönemi"│
│                         │
│                         │
│ [  + YENİ İZİN TALEP  ] │
└─────────────────────────┘
```

---

## 7. Raporlama

### 7.1 İzin ve Devamsızlık Raporları

| # | Rapor | Açıklama | Filtreler | Format |
|---|-------|----------|-----------|--------|
| 1 | İzin Bakiye Raporu | Çalışan bazlı kalan izin günleri | Departman, şube, yıl | Tablo + Excel |
| 2 | İzin Kullanım Raporu | Dönem içinde kullanılan izin günleri | Tarih, departman, izin türü | Tablo + grafik |
| 3 | Devamsızlık Raporu | Kümülatif mazeretsiz devamsızlık | Tarih aralığı, çalışan | Liste |
| 4 | İzin Yoğunluk Raporu | Departman / aylık izin yoğunluğu haritası | Departman, ay | Isı haritası |
| 5 | Onay Süresi Raporu | Ortalama talep-onay süresi (yönetici bazlı) | Yönetici, tarih | Tablo |
| 6 | Yıll Sonu Devir Raporu | Devredilen / sıfırlanan izin günleri | Yıl, departman | Tablo + Excel |
| 7 | SGK Sicil Uyum Raporu | İzin türleri ve SGK bildirim eşleştirmesi | Tarih, çalışan | Tablo |
| 8 | Eskalasyon Raporu | Zamanında onaylanmayan talepler | Tarih, yönetici | Liste |

### 7.2 Dashboard Kartları

```
┌────────────────────────────────────────────────────────────┐
│                      İZİN DASHBOARD                        │
├────────────┬────────────┬────────────┬────────────────────  │
│  Bu Hafta  │  Bu Ay     │  Ortalama  │  Onay Bekleme        │
│  İzinli    │  Kullanım  │  Bakiye    │  Süresi              │
│  Çalışan   │            │            │                     │
│  ┌──────┐  │  ┌──────┐  │  ┌──────┐  │  ┌──────┐           │
│  │  8   │  │  │ 47 gün│  │  │12 gün│  │  │ 6 sa │           │
│  └──────┘  │  └──────┘  │  └──────┘  │  └──────┘           │
│  %5 ekip   │  ↑ %20     │            │                     │
├────────────┴────────────┴────────────┴────────────────────  │
│                                                            │
│ Aylık İzin Kullanımı      │ Devamsızlık Trendi             │
│ ┌─────────────────────┐   │ ┌──────────────────┐           │
│ │ ████ Yıllık      35 │   │ │  2 |              │           │
│ │ ██ Hastalık      12 │   │ │  1 |  * * *  *    │           │
│ │ █ Evlilik         3 │   │ │  0 |___________   │           │
│ │ █ Diğer           5 │   │ │  Oca Şub Mar Nis  │           │
│ └─────────────────────┘   └──────────────────┘             │
└────────────────────────────────────────────────────────────┘
```

### 7.3 Rapor Metrikleri ve Hesaplama

| Metrik | Formül |
|--------|--------|
| **Ortalama Bakiye** | Toplam kalan gün / Aktif çalışan sayısı |
| **İzin Kullanım Oranı** | (Kullanılan gün / Toplam hak) × 100 |
| **Devamsızlık Oranı** | (Mazeretsiz devamsızlık günü / Toplam çalışma günü) × 100 |
| **Ortalama Onay Süresi** | Σ (approved_at − created_at) / Onaylanan talep sayısı |
| **İzin Yoğunluğu** | (İzinli çalışan / Toplam çalışan) × 100 (günlük) |
| **Devir Etkinliği** | (Kullanılan devir izni / Toplam devreden izin) × 100 |

---

## 8. İş Akışları ve Otomasyon

### 8.1 Otomatik Tetiklenen İşlemler

| Tetikleyici | İşlem | Yöntem |
|-------------|-------|--------|
| Çalışan oluşturuldu | İzin bakiyesi ilk kaydını oluştur (annual — işe giriş yılı kota) | Senkron (PersonnelService çağrısı) |
| İzin talebi oluşturuldu | Onaylayıcılara push + e-posta bildirimi | Celery (async) |
| İzin talebi onaylandı / reddedildi | Çalışana push + e-posta | Celery |
| İzin talebi onaylandı | `leave_balances.used_days` güncelle, `pending_days` azalt | Senkron |
| İzin talebi reddedildi | `leave_balances.pending_days` iade et | Senkron |
| İzin talebi iptal edildi | `leave_balances.used_days` veya `pending_days` iade et | Senkron |
| Çalışan offboarding | Kalan bakiye gün sayısını offboarding kaydına yaz | Senkron (LeaveService.get_remaining_balance()) |

### 8.2 Celery Beat (Zamanlanmış Görevler)

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `calculate_annual_leave_entitlements` | 1 Ocak 00:01 | Tüm aktif çalışanların yeni yıl kotasını hesapla ve `leave_balances` oluştur |
| `process_carryover` | 1 Ocak 00:05 | Yıl sonu devir politikasına göre devreden bakiyeleri aktar |
| `check_first_year_anniversary` | Günlük 09:00 | İşe girişi tam 1 yıl dolanlara ilk kotayı aç |
| `escalate_pending_approvals` | Günlük 09:00 | X iş günü yanıtsız kalan talepleri yöneticinin yöneticisine eskalasyon |
| `expire_carryover_balances` | Günlük 09:00 | Vadesi dolan devir bakiyelerini düş |
| `send_holiday_reminder` | 1 Kasım 09:00 | Bir sonraki yılın tatil takvimini güncelleme İK hatırlatması |
| `cleanup_absence_alerts` | Günlük 09:00 | Üst sınırı geçen devamsızlıklar için İK uyarısı |
| `recalculate_pending_days` | Günlük 01:00 | Onay bekleyip sonuçlanmayan taleplerin bakiye tutarlılık kontrolü |

### 8.3 E-posta / Bildirim Şablonları

| Şablon | Tetikleyici | Alıcı | İçerik |
|--------|-------------|-------|--------|
| `leave_request_submitted` | Talep oluşturuldu | Onaylayıcı | "Zeynep Kaya 5 günlük izin talep etti. [Onayla/Reddet]" |
| `leave_request_approved` | Talep onaylandı | Çalışan | "İzin talebiniz onaylandı. 21–25 Nisan 2026" |
| `leave_request_rejected` | Talep reddedildi | Çalışan | "İzin talebiniz reddedildi. Gerekçe: [...]" |
| `leave_request_cancelled` | Talep iptal edildi | Onaylayıcı | "Zeynep Kaya'nın talebi iptal edildi" |
| `leave_approval_escalated` | Eskalasyon | Üst yönetici | "Mehmet Demir 3 günlük izin talebini yanıtlamadı" |
| `leave_balance_updated` | Yıl başı | Çalışan | "2026 izin haklarınız güncellendi: 20 gün + 2 devir" |
| `absence_recorded` | Devamsızlık kaydı | Yönetici | "Can Demir bugün işe gelmedi" |
| `absence_threshold_alert` | 3. mazeretsiz devamsızlık | İK | "Can Demir bu yıl 3. kez mazeretsiz devamsız" |

---

## 9. Güvenlik ve KVKK

### 9.1 Hassas Veri Sınıflandırması

| Veri | Hassasiyet | Saklama | Erişim Kontrolü |
|------|-----------|---------|-----------------|
| İzin türü | Düşük | Düz metin | Auth |
| Talep tarihleri | Düşük | Düz metin | Auth (çalışan kendi + yönetici ekip) |
| Hastalık belgesi (PDF/JPEG) | Orta-Yüksek | MinIO (signed URL) | `leave:request:read` + çalışan kendi |
| İzin gerekçesi | Orta | Düz metin | Auth (çalışan kendi + yönetici + İK) |
| Devamsızlık gerekçesi | Orta | Düz metin | `leave:absence:read` |
| Bakiye bilgisi | Düşük | Düz metin | Çalışan kendi + `leave:balance:read` |

### 9.2 KVKK Gereksinimleri

| Gereksinim | Uygulama |
|------------|----------|
| Hastalık belgesi saklama | MinIO'da saklı, signed URL ile erişim; çalışan ayrıldıktan 5 yıl saklanır |
| Devamsızlık verisi | Türk Ticaret Kanunu saklama süresi (10 yıl) kapsamında |
| İzin onay kayıtları | Audit trail zorunlu; silinemez |
| Çalışan hakları | Self-servis portal üzerinden kendi verilerini görüntüleme ve döküm |

### 9.3 Rol Bazlı Erişim Matrisi

| İzin | Süper Admin | İK Yöneticisi | Dept. Yöneticisi | Çalışan |
|------|------------|--------------|-----------------|---------|
| `leave:type:create` | ✅ | ✅ | ❌ | ❌ |
| `leave:request:read` | ✅ | ✅ | Kendi ekibi | Kendi talepleri |
| `leave:request:create` | ✅ | ✅ (adına) | ❌ | Kendi (Auth) |
| `leave:request:approve` | ✅ | ✅ | Kendi ekibi | ❌ |
| `leave:request:cancel` | ✅ | ✅ | ❌ | Kendi pending |
| `leave:balance:read` | ✅ | ✅ | Kendi ekibi | Kendi bakiyesi |
| `leave:balance:update` | ✅ | ✅ | ❌ | ❌ |
| `leave:absence:create` | ✅ | ✅ | ✅ (kendi ekibi) | ❌ |
| `leave:absence:read` | ✅ | ✅ | Kendi ekibi | ❌ |
| `leave:absence:update` | ✅ | ✅ | ❌ | ❌ |
| `leave:holiday:create` | ✅ | ✅ | ❌ | ❌ |
| `leave:policy:update` | ✅ | ✅ | ❌ | ❌ |
| `leave:bulk:create` | ✅ | ✅ | ❌ | ❌ |
| `leave:report:read` | ✅ | ✅ | Kendi ekibi | ❌ |

---

## 10. Modüller Arası Bağımlılıklar

### 10.1 İzin Modülünün Sunduğu Servisler

```python
class LeaveService:
    """Diğer modüllerin kullandığı izin servisleri."""

    async def create_initial_balances(self, employee_id: int, hire_date: date) -> None
    """Çalışan oluşturulunca çağrılır — 1 yıl dolduğunda kota açmak için job planlar."""

    async def get_remaining_balance(self, employee_id: int, leave_type_code: str, year: int) -> Decimal
    """Offboarding'de kullanılmamış izin ücreti hesabı için."""

    async def get_leave_summary(self, employee_id: int, year: int) -> LeaveSummary
    """Performans ve self-servis dashboard'u için özet bakiye."""

    async def is_employee_on_leave(self, employee_id: int, check_date: date) -> bool
    """Vardiya modülünün devam kontrolü için."""

    async def get_employee_leaves_in_range(self, employee_id: int, start: date, end: date) -> list[LeaveRequest]
    """Bordro modülünün maaş hesabı için."""
```

### 10.2 İzin Modülünün Kullandığı Servisler

| Modül | Servis | Kullanım |
|-------|--------|----------|
| **Personnel** | `PersonnelService.get_employee()` | Çalışan verisi, kıdem hesabı |
| **Personnel** | `PersonnelService.get_employee_hire_date()` | Kıdem hesaplama |
| **Personnel** | `PersonnelService.get_employee_manager()` | Onay akışı için yönetici belirleme |
| **Organization** | `OrganizationService.get_department_employees()` | Ekip takvimi |
| **Notification** | `NotificationService.send()` | Talep, onay, red bildirimleri |

### 10.3 Bağımlılık Diyagramı

```
┌──────────────────┐           ┌────────────────────┐
│    Personel      │──────────▶│  İzin & Devamsızlık │
│  Modülü          │  kıdem,   │      Modülü         │
│ (çalışan kaydı)  │  yönetici │                     │
└──────────────────┘           └──────────┬──────────┘
                                          │
                         ┌────────────────┼───────────────────┐
                         │                │                   │
                   ┌─────┴──┐     ┌───────┴────┐    ┌────────┴──┐
                   │ Bordro  │     │Self-Servis │    │ Vardiya   │
                   │ Modülü  │     │  Portal    │    │  Modülü   │
                   └─────────┘     └────────────┘    └───────────┘
                   izinli gün,      talep & bakiye    devam takibi
                   kullanılmayan    görüntüleme        (PDKS entegr)
                   izin ücreti
```

---

## 11. Performans Gereksinimleri

| Senaryo | Hedef | Yöntem |
|---------|-------|--------|
| İzin bakiyesi görüntüleme | < 50ms | Redis cache (60s TTL) + generated kolon |
| İzin talebi listeleme (sayfalı) | < 100ms | Composite index + pagination |
| Ekip takvimi (1 aylık, 50 çalışan) | < 200ms | Redis cache (5dk TTL) |
| Onay akışı tetikleme | < 300ms | Senkron DB + Celery async bildirim |
| Yıl sonu devir işlemi (1.000 çalışan) | < 2 dakika | Celery batch |
| Bakiye yeniden hesaplama (100 çalışan) | < 5 saniye | Celery + bulk update |
| İzin raporu (500 çalışan, 1 yıl veri) | < 3 saniye | Aggregate query + Redis cache |

---

## 12. Test Senaryoları

### 12.1 Birim Test

| # | Test | Beklenen Sonuç |
|---|------|---------------|
| 1 | Kıdem hesaplama (3 yıl kullanıcı) | 14 gün kota |
| 2 | Kıdem hesaplama (6 yıl kullanıcı) | 20 gün kota |
| 3 | Kıdem hesaplama (16 yıl kullanıcı) | 26 gün kota |
| 4 | İzin süresi hesaplama (Pazartesi–Cuma) | 5 gün (haftasonu hariç) |
| 5 | Resmi tatil içeren izin süresi | Tatil günleri düşülmüş |
| 6 | Yarım gün + tam gün toplam | 1.5 gün |
| 7 | Saatlik izin gün hesabı (3 saat / 8 saat) | 0.375 gün |
| 8 | Bakiye formülü (20 + 2 devir − 5 kullanılan − 3 bekleyen) | 14 gün |
| 9 | Devir hesaplama (8 gün kalan, max 5 devir) | 5 gün devir |
| 10 | Çakışma kontrolü (aynı dönem + pending talep) | `LEAVE_OVERLAP` hatası |

### 12.2 Entegrasyon Test

| # | Test | Beklenen Sonuç |
|---|------|---------------|
| 1 | Çalışan oluştur → İzin bakiyesi var mı | `leave_balances` kaydı oluştu (1. yıl dolunca) |
| 2 | İzin talebi oluştur → Onaylayıcıya bildirim | Push + e-posta gönderildi |
| 3 | Talep onayla → Bakiye güncellendi mi | `used_days` arttı, `pending_days` azaldı |
| 4 | Talep reddet → Bakiye iade edildi mi | `pending_days` sıfırlandı |
| 5 | Offboarding → Kalan bakiye hesaplandı mı | `LeaveService.get_remaining_balance()` doğru döner |
| 6 | Yıl sonu devir job → Bakiye yeni yıla aktarıldı mı | `carried_over_days` doğru |
| 7 | Tenant A talebi → Tenant B'den erişilemez | 403 veya boş liste |
| 8 | Çalışan kendi talebini self-servisten onayla girişimi | 422 `APPROVAL_NOT_ALLOWED` |

### 12.3 E2E Test

| # | Test | Adımlar |
|---|------|---------|
| 1 | Tam izin akışı (mobil) | Login (çalışan) → İzin Talebi → Türü seç → Tarih gir → Gönder → Yönetici push → Onayla → Bakiye güncellendi |
| 2 | Multi-level onay akışı | İzin talebi → Yönetici onaylar → İK'ya bildirim → İK onaylar → Talep approved |
| 3 | İzin iptali | Onaylı izin → Henüz başlamadı → Çalışan iptal talebi → Yönetici onaylar → Bakiye iade |
| 4 | Devamsızlık takibi | İK devamsızlık kaydı → Yöneticiye bildirim → 3. devamsızlıkta eskalasyon |
| 5 | Yıl sonu akışı | 31 Aralık → Celery job → Yeni yıl bakiyeleri oluştu → Devir günleri aktarıldı → Çalışanlara bildirim |

---

## 13. Kısıtlamalar ve Varsayımlar

### 13.1 Kısıtlamalar

| # | Kısıt | Etki | Çözüm |
|---|-------|------|-------|
| K1 | Hicri takvim tatilleri yıllık İK girişi gerektiriyor | Ramazan/Kurban tatilleri her yıl manuel eklenmeli | Diyanet İşleri takvimi referansıyla yıllık İK görevi |
| K2 | Yabancı uyruklu çalışanlar için farklı yasal izin kuralları uygulanabilir | İlk sürümde Türkiye İş Kanunu standart | Tenant bazlı özel kural motoru Faz 3+ |
| K3 | PDKS entegrasyonu devamsızlık otomasyonu için gerekli | İlk sürümde devamsızlık manuel kaydedilir | 16-modul-vardiya-mesai.md kapsamında Faz 2 |
| K4 | Kıdem tazminatına etkili devamsızlık hesabı bordro bağlantısı gerektirir | Devamsızlık kaydı bilgisel, bordro doğrulama bordro modülünde | Bordro modülü entegrasyonu Faz 2 |

### 13.2 Varsayımlar

| # | Varsayım | Risk |
|---|---------|------|
| V1 | Çalışma haftası Pazartesi–Cuma (5 gün, 8 saat/gün) | Küçük — tenant ayarından düzenlenebilir |
| V2 | Türkiye İş Kanunu (4857) kıdem tablosu geçerli | Küçük — özel politika tenant bazlı üzerine yazılabilir |
| V3 | Yönetici hiyerarşisi `personnel_employees.manager_id` ile tanımlıdır | Küçük — personel modülüne bağımlılık |
| V4 | İzin bakiyesi negatife düşemez (varsayılan) | Orta — tenant bazlı negatif bakiye konfigürasyonu ile aşılabilir |
| V5 | İlk yıl çalışanına orantılı izin verilmez (yasal minimum) | Düşük — tenant ayarında `proportional_first_year` ile değiştirilebilir |

---

## 14. Gelecek İyileştirmeler (Roadmap)

| Faz | İyileştirme | Açıklama |
|-----|-------------|----------|
| Faz 2 | PDKS entegrasyonu ile otomatik devamsızlık tespiti | Kart okuyucu / biyometrik veri ile devamsızlık otomatik kaydı |
| Faz 2 | Bölgesel çalışma saati takvimi | Farklı şubeler için farklı çalışma saati ve hafta sonu tanımı |
| Faz 3 | Esnek çalışma süresi izin modeli (TOIL) | Fazla mesai karşılığı izin hakkı |
| Faz 3 | İzin planlaması — AI öneri | Ekip yoğunluğuna göre "şu tarihlerden birini seçin" önerisi |
| Faz 3 | Sağlık sigortası sistemi entegrasyonu | Raporlu izinlerin sigorta sistemine otomatik bildirimi |
| Faz 3 | SGK e-bildirge entegrasyonu | Analık/babalık izni SGK'ya otomatik bildirim |
| Faz 4 | Uzun dönem izin planlama (sabbatical) | 1 ay veya üzeri izin planlaması ve kademeli hakediş |
| Faz 4 | İzin satın alma / satma politikası | Çalışanın ek izin satın alması veya kullanmadığını nakde çevirmesi |

---

## 15. Sonuç

İzin & Devamsızlık Yönetimi modülü, MVP'nin en kritik üç modülünden biridir ve çalışanların günlük en sık kullandığı özellikleri sunar. Bu doküman aşağıdaki temel kararları detaylandırmıştır:

- **Türk İş Kanunu uyumu:** 4857 sayılı Kanun kıdem tablosu otomatik kota hesaplama, yasal minimumlar ve tazminat hesaplaması için temel referans
- **Çok seviyeli onay:** Tenant bazlı konfigüre edilebilir onay modeli (yönetici, yönetici + İK, otomatik)
- **Anlık bakiye:** GENERATED ALWAYS kolon ile bakiye tutarlılığı garantisi; Redis cache ile < 50ms görüntüleme
- **Mobil öncelik:** Çalışan ve yönetici için native push bildirimi, tek tuş onay, 3 adımlı talep oluşturma
- **Otomasyon:** Yıl başı kota hesaplama, birinci yıl dönümü açma, eskalasyon, devir — tümü Celery beat ile
- **Resmi tatil entegrasyonu:** Türkiye Gregoryen tatilleri otomatik, Hicri tatiller İK girişi; izin süresinden otomatik düşme
- **Devamsızlık yönetimi:** Mazeretli/mazeretsiz ayrımı, kümülatif uyarı mekanizması, bordro modülüne bilgi akışı
- **KVKK uyum:** Hastalık belgeleri için MinIO + signed URL, audit log zorunluluğu, saklama süresi yönetimi
- **Modüler entegrasyon:** `LeaveService` arayüzü ile Personel, Bordro, Vardiya modüllerine servis sunumu

---

> **Sonraki Adım:** [13-modul-performans-yonetimi.md](13-modul-performans-yonetimi.md) — Hedef belirleme (OKR/KPI), değerlendirme dönemleri, 360° feedback, yetkinlik matrisi
