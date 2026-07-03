# 11 — Modül: İşe Alım & Aday Takip Sistemi (ATS)

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** İş ilanı yönetimi, başvuru toplama, aday takibi (kanban), mülakat planlama, değerlendirme & skor kartı, teklif süreci, aday havuzu, kariyer sayfası, işe alım metrikleri  
> **Faz:** Faz 3 (Growth) — Personel + İzin + Self-Servis (MVP) sonrasında  
> **Referans:** 04-gereksinim-analizi.md (FR-ATS-01 – FR-ATS-12), 07-veritabani-tasarimi.md (Bölüm 12), 08-api-tasarimi.md, 09-entegrasyon-haritasi.md (Bölüm 4.10)

---

## 1. Modül Özeti

İşe Alım & Aday Takip (ATS) modülü, açık pozisyonların yönetiminden adayın işe başlamasına kadar olan tüm süreci dijitalleştirir. Fatma (İşe Alım Uzmanı) personası için birincil modüldür; Ayşe (İK Müdürü) ve Mehmet (Departman Yöneticisi) için ikincil tüketici konumundadır.

### 1.1 Modül Kapsamı

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| İş ilanı oluşturma ve yönetimi | Bordro hesaplama (14-modul-bordro-maas.md) |
| Çoklu kanal yayınlama (kariyer sayfası, çerçeve entegrasyon) | Onboarding checklist (10-modul-personel-yonetimi.md) |
| Başvuru toplama (form, CV yükleme, e-posta) | Performans değerlendirme (13-modul-performans-yonetimi.md) |
| Kanban aday takibi (pipeline) | Çalışan özlük dosyaları (10-modul-personel-yonetimi.md) |
| Aday puanlama / skor kartı | Eğitim yönetimi (15-modul-egitim-gelisim.md) |
| Mülakat planlama ve değerlendirme | — |
| Teklif mektubu oluşturma | — |
| Aday havuzu | — |
| Aday iletişim geçmişi | — |
| KVKK aday rızası yönetimi | — |
| İşe alım raporları ve metrikleri | — |
| Gömülebilir kariyer sayfası | — |

### 1.2 İşe Alım Pipeline Genel Görünümü

```
İlan           Başvuru         Ön Eleme       Mülakat        Değerlendirme   Teklif         Sonuç
Oluştur        Topla           Yap            Planla         Puanla          Gönder         Belirle

┌──────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐   ┌──────────┐   ┌──────────┐
│ İlan │───▶│Başvurular │───▶│ Ön Eleme │───▶│ Mülakat  │───▶│Değerlend.│──▶│  Teklif  │──▶│İşe Alındı│
│Yayınla│   │  Gelir   │    │ Filtrele │    │  Yap     │    │ Puanla   │   │  Yap     │   │  veya    │
└──────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘   └──────────┘   │Reddedildi│
                                                                                          └──────────┘
```

### 1.3 İlişkili Modüller

```
                    ┌──────────────┐
                    │ Organization │ Departman, pozisyon bilgisi
                    │   Modülü     │
                    └──────┬───────┘
                           │
┌──────────────┐    ┌──────┴───────┐    ┌──────────────┐
│ Notification │◀───│   İşe Alım   │───▶│   Personel   │
│   Modülü     │    │   (ATS)      │    │   Modülü     │
└──────────────┘    └──────┬───────┘    └──────────────┘
  e-posta, SMS,            │              aday → çalışan dönüşümü
  push bildirim     ┌──────┼───────┐
                    │      │       │
              ┌─────┴──┐ ┌┴─────┐ ┌┴──────────┐
              │Takvim  │ │MinIO │ │ Auth      │
              │Entegr. │ │(CV)  │ │ Modülü    │
              └────────┘ └──────┘ └───────────┘
              mülakat     dosya     yetki
              planlama    saklama   kontrolü
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|---------------|-------------------|-----------------|
| **Fatma (İşe Alım Uzmanı)** | Ana kullanıcı | Günlük 6-8 saat | İlan oluşturma, aday takibi, mülakat koordinasyonu, teklif |
| **Ayşe (İK Müdürü)** | Onaylayıcı / raporlama | Günlük 30-60 dk | İlan onayı, teklif onayı, metrik takibi |
| **Mehmet (Dept. Yöneticisi)** | Mülakat yapıcı / değerlendirici | Haftalık 1-2 saat | Mülakat, skor kartı doldurma, aday değerlendirme |
| **Emre (KOBİ Sahibi)** | Hem İK hem yönetici | Aylık birkaç kez | İlan oluşturma, aday değerlendirme |
| **Hakan (Genel Müdür)** | Dashboard tüketici | Aylık 1-2 kez | İşe alım metrikleri, headcount raporları |

### 2.2 İşe Alım Uzmanı — Tam İşe Alım Yolculuğu

```
HAZIRLIK              YAYINLAMA            TOPLAMA               TAKİP
   │                      │                    │                     │
   ▼                      ▼                    ▼                     ▼
Yöneticiden         → İlan oluştur        → Başvurular gelir   → Kanban'da
açık pozisyon         │                      │                    aday takibi
talebi gelir          ├─ Başlık/Açıklama     ├─ Kariyer sayfası    │
   │                  ├─ Gereksinimler       ├─ E-posta             ├─ Ön eleme
   ▼                  ├─ Departman/Pozisyon   ├─ Manuel giriş       ├─ Mülakat planlama
İlan ihtiyaçları      ├─ Çalışma türü       └─ (Faz 3+: Platform)  ├─ Değerlendirme
belirlenir            ├─ Maaş aralığı                               ├─ Teklif gönderme
   │                  └─ Son başvuru tarihi                         └─ İşe alım / Red
   ▼                      │                                            │
İş tanımı hazırlanır  → Kariyer sayfasında                          ▼
                        yayınla                                   Kabul edilirse
                                                                 → Personel modülüne
                                                                   çalışan olarak aktar
```

**Hedef Süreler:**

| Adım | Hedef | Mevcut (Manuel) |
|------|-------|-----------------|
| İlan oluşturma | < 10 dakika | 30-60 dakika (farklı platformlarda ayrı ayrı) |
| CV ön eleme (50 aday) | < 15 dakika | 2-3 saat (manuel tarama) |
| Mülakat planlama (5 aday) | < 5 dakika | 30-60 dakika (e-posta/telefon koordinasyonu) |
| Teklif mektubu oluşturma | < 3 dakika | 30 dakika (template düzenleme) |
| Aday → çalışan dönüşümü | < 2 dakika | 30-60 dakika (yeniden veri girişi) |
| İşe alım süreci (uçtan uca) | 15-30 gün | 30-60 gün |

### 2.3 Departman Yöneticisi — Mülakat & Değerlendirme Yolculuğu

```
BİLDİRİM             MÜLAKAT              DEĞERLENDİRME
   │                    │                      │
   ▼                    ▼                      ▼
Mülakat davetiyesi  → Aday profilini       → Skor kartını doldur
e-posta'da gelir      incele (CV, notlar)     │
   │                    │                      ├─ Teknik yetkinlik
   ▼                    ▼                      ├─ İletişim becerisi
Takvimde uygu       → Mülakat yap            ├─ Kültür uyumu
saatleri kontrol      (yüz yüze / online)     ├─ Motivasyon
   │                    │                      └─ Genel not / yorum
   ▼                    ▼                      │
Uygunluğu onayla    → Not al                → İşe alım uzmanına
                                               geri bildirim gider
```

### 2.4 Aday — Başvuru Deneyimi

```
KEŞFETME              BAŞVURU               TAKİP
   │                    │                      │
   ▼                    ▼                      ▼
Kariyer sayfasında  → Formu doldur         → E-posta ile
ilanı görür           │                      durum güncellemesi
   │                  ├─ Kişisel bilgiler     │
   ▼                  ├─ CV yükle (PDF)       ├─ "Başvurunuz alındı"
İlan detayını okur    ├─ Ön yazı              ├─ "Mülakata davetlisiniz"
   │                  ├─ KVKK onayı           ├─ "Değerlendirme sürecinde"
   ▼                  └─ Gönder               └─ "Teklif / Red"
Başvur butonuna
tıklar
```

**Aday Deneyimi Hedefleri:**

| Metrik | Hedef |
|--------|-------|
| Başvuru formu tamamlama süresi | < 5 dakika |
| Kariyer sayfası yüklenme süresi | < 2 saniye |
| İlk geri bildirim süresi | < 48 saat (otomatik e-posta) |
| Mülakat davetiyesi sonrası onay | Tek tık ile takvime ekleme |

---

## 3. Fonksiyonel Gereksinimler — Detay

### 3.1 İş İlanı Yönetimi

#### FR-ATS-01: İş İlanı Oluşturma

**Açıklama:** İK uzmanı, açık bir pozisyon için iş ilanı oluşturabilmeli, düzenleyebilmeli ve yayınlayabilmelidir.

**İlan Durumları:**

```
draft → published → closed → archived
  │         │          │
  │         │          └─ Pozisyon dolduruldu veya iptal
  │         └─ Son başvuru tarihi geçti (otomatik) veya manuel kapatma
  └─ Henüz yayınlanmadı (taslak)
```

| Durum | Kod | Açıklama |
|-------|-----|----------|
| Taslak | `draft` | Oluşturuldu, henüz yayınlanmadı |
| Yayında | `published` | Kariyer sayfasında görünür, başvuru alabilir |
| Kapalı | `closed` | Başvuru almıyor ama veriler korunuyor |
| Arşivlenmiş | `archived` | Geçmiş kayıt, raporlarda görünür |

**İlan Alanları:**

| Alan | Tip | Zorunlu | Açıklama |
|------|-----|---------|----------|
| Başlık | VARCHAR(255) | Evet | İlan başlığı, ör: "Kıdemli Python Geliştirici" |
| Slug | VARCHAR(255) | Otomatik | URL-friendly slug: `kidemli-python-gelistirici-2026-04` |
| Departman | FK | Evet | Hangi departman için |
| Pozisyon | FK | Evet | Hangi pozisyon |
| Şube / Lokasyon | FK | Evet | Çalışılacak yer |
| Çalışma türü | ENUM | Evet | `full_time`, `part_time`, `intern`, `contract` |
| Çalışma modeli | ENUM | Evet | `office`, `remote`, `hybrid` |
| Deneyim seviyesi | ENUM | Hayır | `junior`, `mid`, `senior`, `lead`, `manager` |
| İş tanımı | TEXT (rich) | Evet | Markdown/HTML destekli detaylı açıklama |
| Gereksinimler | TEXT (rich) | Evet | Aranan nitelikler |
| Tercih edilen | TEXT (rich) | Hayır | Tercih edilen nitelikler |
| Maaş aralığı (min) | NUMERIC | Hayır | Gösterilsin mi seçeneği ile |
| Maaş aralığı (max) | NUMERIC | Hayır | |
| Maaş gösterilsin mi | BOOLEAN | Evet | Kariyernet gibi gizlenebilir |
| Alınacak kişi sayısı | SMALLINT | Evet | Pozisyon adedi |
| Son başvuru tarihi | DATE | Hayır | Geçince ilan otomatik kapanır |
| Etiketler | VARCHAR[] | Hayır | Arama ve gruplama için: `python`, `remote`, `acil` |
| İlan sorumlusu | FK | Evet | İK uzmanı (ilanı yöneten kişi) |
| Onaylayan | FK | Hayır | Yönetici veya İK müdürü |
| Yayın kanalları | JSONB | Hayır | Hangi kanallara yayınlanacağı |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-ILN-01 | İlan oluşturulduğunda varsayılan durum `draft`'tır |
| IK-ILN-02 | İlan yayınlanabilmesi için başlık, departman, pozisyon, çalışma türü, iş tanımı ve gereksinimler zorunludur |
| IK-ILN-03 | Slug otomatik üretilir (başlık + tarih), benzersiz olmalıdır (tenant içinde) |
| IK-ILN-04 | Son başvuru tarihi geçen ilanlar günlük Celery cron ile otomatik `closed` yapılır |
| IK-ILN-05 | Kapatılan ilanlara yeni başvuru kabul edilmez |
| IK-ILN-06 | İlan silinmez, `archived` olarak saklanır (soft delete) |
| IK-ILN-07 | İlan yayınlandığında ilan sorumlusuna bildirim, kapandığında özet rapor gönderilir |
| IK-ILN-08 | Maaş aralığı girilmişse `show_salary = false` ile gizlenebilir (aday göremez ama İK kullanabilir) |
| IK-ILN-09 | Bir ilanın kopyası oluşturulabilir (benzer pozisyon için hızlı ilan) |

---

#### FR-ATS-02: Çoklu Kanal Yayınlama

**Açıklama:** Oluşturulan ilan birden fazla kanala yayınlanabilmelidir.

**Yayın Kanalları:**

| Kanal | Faz | Yöntem | Açıklama |
|-------|-----|--------|----------|
| Kariyer sayfası (dahili) | Faz 3 (MVP ATS) | Otomatik | Sistem içi gömülebilir kariyer sayfası |
| Manuel ilan paylaşımı | Faz 3 | Link kopyalama | İlan linkini LinkedIn, social media'da paylaşma |
| Kariyer.net API | Faz 3+ | Adaptör | İlan otomatik yayın + başvuru çekme |
| LinkedIn API | Faz 3+ | Adaptör | İlan otomatik yayın |
| Indeed API | Faz 4 | Adaptör | İlan otomatik yayın |

**Adaptör Mimarisi (09-entegrasyon-haritasi.md referansı):**

```python
# apps/api/integrations/job_board_adapter.py

class JobBoardAdapter(ABC):
    """İş ilanı platformu adaptör arayüzü."""

    @abstractmethod
    async def publish_job(self, job: JobPostingDTO) -> ExternalJobId: ...

    @abstractmethod
    async def update_job(self, external_id: str, job: JobPostingDTO) -> None: ...

    @abstractmethod
    async def close_job(self, external_id: str) -> None: ...

    @abstractmethod
    async def fetch_applications(self, external_id: str) -> list[ExternalApplication]: ...


class KariyerNetAdapter(JobBoardAdapter):
    """Kariyer.net API entegrasyonu."""
    ...

class LinkedInAdapter(JobBoardAdapter):
    """LinkedIn Jobs API entegrasyonu."""
    ...
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-KNL-01 | Dahili kariyer sayfası yayını Faz 3'te varsayılan ve zorunlu kanaldır |
| IK-KNL-02 | Dış platform entegrasyonları opsiyoneldir ve ayrı konfigüre edilir |
| IK-KNL-03 | Dış platformlara ilan yayınlama tenant ayarlarında aktif edilmelidir |
| IK-KNL-04 | İlan kapatıldığında dış platformlardaki ilan da otomatik kapatılır (adaptör çağrısı) |
| IK-KNL-05 | Dış platformdan çekilen başvurular `ats_applications.source` alanında kaynak ile işaretlenir |

---

### 3.2 Başvuru Toplama

#### FR-ATS-03: Başvuru Toplama

**Açıklama:** Adaylar çeşitli kanallardan başvurabilmelidir.

**Başvuru Kanalları:**

| Kanal | Yöntem | Faz |
|-------|--------|-----|
| Kariyer sayfası formu | Online form + CV yükleme | Faz 3 |
| Doğrudan link | İlan sayfası paylaşım linki | Faz 3 |
| Manuel giriş | İK uzmanı elle aday kaydı oluşturur | Faz 3 |
| E-posta (forward) | İK'ya gelen CV'yi sisteme ekleme | Faz 3 |
| Kariyer.net | API ile otomatik çekme | Faz 3+ |
| LinkedIn | API ile otomatik çekme | Faz 3+ |

**Başvuru Formu Alanları:**

| Alan | Tip | Zorunlu | Açıklama |
|------|-----|---------|----------|
| Ad | VARCHAR(100) | Evet | |
| Soyad | VARCHAR(100) | Evet | |
| E-posta | VARCHAR(255) | Evet | Benzersizlik kontrolü (ilan bazında) |
| Telefon | VARCHAR(20) | Evet | |
| CV dosyası | Dosya | Evet | PDF, DOCX (max 5 MB) |
| Ön yazı / Motivasyon | TEXT | Hayır | Adayın motivasyon metni |
| LinkedIn profili | URL | Hayır | |
| Beklenen maaş | NUMERIC | Hayır | |
| En erken başlangıç | DATE | Hayır | Ne zaman başlayabilir |
| Bilgi kaynağı | ENUM | Hayır | İlanı nereden gördü: `career_page`, `linkedin`, `referral`, `other` |
| KVKK onayı | BOOLEAN | Evet | Açık rıza metni onayı |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-BŞV-01 | KVKK onayı verilmeden başvuru kabul edilmez |
| IK-BŞV-02 | Aynı aday aynı ilana yalnızca bir kez başvurabilir (e-posta benzersizlik) |
| IK-BŞV-03 | Aynı aday farklı ilanlara başvurabilir |
| IK-BŞV-04 | CV dosyası MinIO'da `{tenant_id}/ats/applications/{application_id}/` yoluna kaydedilir |
| IK-BŞV-05 | Başvuru alındığında adaya otomatik onay e-postası gönderilir (Celery) |
| IK-BŞV-06 | Başvuru alındığında ilan sorumlusuna bildirim gönderilir |
| IK-BŞV-07 | Başvuru kaynağı (`source`) otomatik belirlenir veya form'da seçilir |
| IK-BŞV-08 | Kapalı ilanlara başvuru kabul edilmez (API 422 döner) |
| IK-BŞV-09 | CV dosyası yalnızca PDF ve DOCX formatında, maksimum 5 MB kabul edilir |

---

### 3.3 Kanban Aday Takibi (Pipeline)

#### FR-ATS-04: Kanban Aday Takibi

**Açıklama:** Adaylar görsel bir kanban panosunda aşamalar arasında takip edilmelidir.

**Varsayılan Pipeline Aşamaları:**

| Sıra | Aşama | Kod | Açıklama | Otomatik İşlem |
|------|-------|-----|----------|----------------|
| 1 | Yeni Başvuru | `applied` | Başvuru henüz incelenmedi | Otomatik onay e-postası |
| 2 | Ön Eleme | `screening` | CV inceleniyor, ön değerlendirme | — |
| 3 | Telefon Görüşmesi | `phone_screen` | İlk telefon mülakatı | — |
| 4 | Mülakat | `interview` | Yüz yüze / video mülakat | Takvim daveti gönderimi |
| 5 | Değerlendirme | `evaluation` | Son değerlendirme, referans kontrolü | — |
| 6 | Teklif | `offer` | Teklif gönderildi, yanıt bekleniyor | Teklif e-postası |
| 7 | İşe Alındı | `hired` | Teklif kabul edildi | Personel modülüne transfer |
| 8 | Reddedildi | `rejected` | Aday reddedildi (herhangi bir aşamada) | Red e-postası |
| 9 | Çekildi | `withdrawn` | Aday kendi çekildi | — |

**Pipeline Özelleştirme:**

| Özellik | Açıklama |
|---------|----------|
| Aşama ekleme | Tenant bazlı ek aşamalar eklenebilir (ör: "Teknik Test", "Case Study") |
| Aşama sırası | Sıralama değiştirilebilir |
| Zorunlu aşamalar | Bazı aşamalar atlanamaz (konfigüre edilebilir) |
| Aşama silme | Aday olan aşama silinemez |

**Kanban Görünümü:**

```
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│ Yeni (12)  │ │Ön Eleme(8) │ │ Mülakat(3) │ │Değerlen.(2)│ │ Teklif (1) │ │ İşe Al.(1) │
├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤
│┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────────┐│
││ Ahmet Y. ││ ││ Elif K.  ││ ││ Can D.   ││ ││ Seda T.  ││ ││ Mert K.  ││ ││ Deniz B. ││
││ ★★★★☆   ││ ││ ★★★☆☆   ││ ││ ★★★★★   ││ ││ ★★★★☆   ││ ││ ★★★★★   ││ ││ ★★★★★   ││
││ 2 gün    ││ ││ 5 gün    ││ ││ 1 gün    ││ ││ 3 gün    ││ ││ 7 gün    ││ ││ ✓ Kabul  ││
│└──────────┘│ │└──────────┘│ │└──────────┘│ │└──────────┘│ │└──────────┘│ │└──────────┘│
│┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │            │ │            │
││ Fatma S. ││ ││ Burak M. ││ ││ Aylin T. ││ ││ Oğuz H.  ││ │            │ │            │
││ ★★★☆☆   ││ ││ ★★★★☆   ││ ││ ★★★★☆   ││ ││ ★★★☆☆   ││ │            │ │            │
││ 1 gün    ││ ││ 3 gün    ││ ││ 2 gün    ││ ││ 1 gün    ││ │            │ │            │
│└──────────┘│ │└──────────┘│ │└──────────┘│ │└──────────┘│ │            │ │            │
│    ...     │ │    ...     │ │┌──────────┐│ │            │ │            │ │            │
│            │ │            │ ││ Zehra A. ││ │            │ │            │ │            │
│            │ │            │ ││ ★★★★★   ││ │            │ │            │ │            │
│            │ │            │ ││ yeni     ││ │            │ │            │ │            │
│            │ │            │ │└──────────┘│ │            │ │            │ │            │
└────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-KNB-01 | Aday kartları sürükle-bırak ile aşamalar arası taşınır |
| IK-KNB-02 | Aşama değişikliğinde `ats_stage_history` kaydı oluşur (tarih, değiştiren, gerekçe) |
| IK-KNB-03 | `rejected` ve `withdrawn` aşamalarına herhangi bir aşamadan geçilebilir |
| IK-KNB-04 | `hired` aşamasına geçişte "Personel modülüne aktar" aksiyonu tetiklenir |
| IK-KNB-05 | Her aşamada adayın kaç gün beklediği hesaplanır ve gösterilir |
| IK-KNB-06 | Aşama geçişinde opsiyonel not ekleme imkanı sağlanır |
| IK-KNB-07 | Reddedilen adaylar aday havuzuna otomatik atanır (KVKK onayı varsa) |
| IK-KNB-08 | Kanban'da filtre: pozisyon, puan, giriş tarihi, kaynak |

---

### 3.4 Aday Puanlama ve Skor Kartı

#### FR-ATS-05: Aday Puanlama / Derecelendirme

**Açıklama:** Mülakatçılar ve İK uzmanları her aşamada adayı puanlayabilmelidir.

**Skor Kartı Yapısı:**

#### `ats_scorecard_templates` — Skor Kartı Şablonları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `name` | VARCHAR(200) | Şablon adı: "Teknik Mülakat", "Kültür Uyumu" |
| `description` | TEXT | |
| `criteria` | JSONB | Değerlendirme kriterleri listesi |
| `is_default` | BOOLEAN | Varsayılan şablon mu |
| `created_at` | TIMESTAMPTZ | |

**Örnek Skor Kartı Kriterleri (JSONB):**

```json
{
  "criteria": [
    {
      "key": "technical_skills",
      "label": "Teknik Yetkinlik",
      "description": "Gerekli teknik becerilere sahiplik",
      "weight": 30,
      "max_score": 5
    },
    {
      "key": "communication",
      "label": "İletişim Becerisi",
      "description": "Kendini ifade etme, dinleme, sunum",
      "weight": 20,
      "max_score": 5
    },
    {
      "key": "culture_fit",
      "label": "Kültür Uyumu",
      "description": "Şirket kültürü ve değerleriyle uyum",
      "weight": 20,
      "max_score": 5
    },
    {
      "key": "motivation",
      "label": "Motivasyon",
      "description": "Pozisyona ve şirkete ilgi/istek",
      "weight": 15,
      "max_score": 5
    },
    {
      "key": "experience",
      "label": "Deneyim",
      "description": "İlgili iş deneyimi ve başarılar",
      "weight": 15,
      "max_score": 5
    }
  ]
}
```

#### `ats_evaluations` — Değerlendirme Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `application_id` | BIGINT, FK | Hangi başvuru |
| `evaluator_id` | BIGINT, FK → auth_users | Değerlendirmeyi yapan kişi |
| `stage` | VARCHAR(30) | Hangi aşamada yapıldı |
| `scorecard_template_id` | BIGINT, FK, nullable | Kullanılan skor kartı şablonu |
| `scores` | JSONB | Her kriter için verilen puanlar |
| `weighted_score` | NUMERIC(5,2) | Ağırlıklı ortalama puan (hesaplanan) |
| `recommendation` | VARCHAR(20) | `strong_yes`, `yes`, `neutral`, `no`, `strong_no` |
| `notes` | TEXT | Açık metin değerlendirme notu |
| `is_private` | BOOLEAN, default: false | Yalnızca İK'nın görebildiği not |
| `created_at` | TIMESTAMPTZ | |

**Örnek Score JSONB:**

```json
{
  "technical_skills": 4,
  "communication": 5,
  "culture_fit": 3,
  "motivation": 4,
  "experience": 3
}
```

**Ağırlıklı Puan Hesaplaması:**

```
weighted_score = Σ (puan / max_puan × ağırlık) 

Örnek: (4/5 × 30) + (5/5 × 20) + (3/5 × 20) + (4/5 × 15) + (3/5 × 15)
     = 24 + 20 + 12 + 12 + 9 = 77 / 100
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-SKR-01 | Bir başvuruya birden fazla kişi değerlendirme yapabilir |
| IK-SKR-02 | Her değerlendiricinin puanı bağımsız saklanır |
| IK-SKR-03 | Aday kartında tüm değerlendirmelerin ortalaması gösterilir |
| IK-SKR-04 | Skor kartı şablonları tenant bazlı özelleştirilebilir |
| IK-SKR-05 | Özel not (`is_private = true`) yalnızca İK yetkilileri tarafından görülebilir |
| IK-SKR-06 | Değerlendirme gönderildikten sonra düzenlenemez (immutable) |
| IK-SKR-07 | Değerlendirme yapılmadan adayın sonraki aşamaya geçmesi mümkündür ancak uyarı verilir |
| IK-SKR-08 | Skor kartı doldurulduğunda İK uzmanına bildirim gönderilir |

---

### 3.5 Mülakat Planlama

#### FR-ATS-06: Mülakat Planlama

**Açıklama:** Mülakatlar takvim üzerinden planlanabilmeli, katılımcılara otomatik davet gönderilmelidir.

#### `ats_interviews` — Mülakat Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `application_id` | BIGINT, FK | Hangi başvuru |
| `interview_type` | VARCHAR(30) | `phone`, `video`, `onsite`, `panel`, `technical_test`, `case_study` |
| `title` | VARCHAR(255) | Mülakat başlığı: "1. Tur Teknik Mülakat" |
| `scheduled_at` | TIMESTAMPTZ | Planlanan tarih ve saat |
| `duration_minutes` | SMALLINT | Süre (dakika, varsayılan: 60) |
| `location` | VARCHAR(500), nullable | Fiziksel lokasyon veya video link |
| `meeting_link` | VARCHAR(500), nullable | Google Meet / Zoom / Teams linki |
| `status` | VARCHAR(20) | `scheduled`, `confirmed`, `completed`, `cancelled`, `no_show` |
| `notes` | TEXT, nullable | İç not |
| `candidate_notified` | BOOLEAN, default: false | Adaya bildirim gönderildi mi |
| `candidate_confirmed` | BOOLEAN, default: false | Aday onayladı mı |
| `created_by` | BIGINT, FK | Mülakatı planlayan |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `ats_interview_participants` — Mülakat Katılımcıları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `interview_id` | BIGINT, FK | |
| `user_id` | BIGINT, FK → auth_users | Mülakatçı |
| `role` | VARCHAR(30) | `interviewer`, `observer`, `note_taker` |
| `is_required` | BOOLEAN, default: true | Zorunlu katılımcı mı |
| `response` | VARCHAR(20), nullable | `accepted`, `declined`, `tentative` |

**Mülakat Türleri:**

| Tür | Kod | Açıklama |
|-----|-----|----------|
| Telefon Görüşmesi | `phone` | İlk ön görüşme |
| Video Mülakat | `video` | Online mülakat (Zoom/Meet/Teams) |
| Yüz Yüze | `onsite` | Ofiste mülakat |
| Panel | `panel` | Birden fazla mülakatçı ile |
| Teknik Test | `technical_test` | Kodlama testi, sınav |
| Vaka Çalışması | `case_study` | Case study sunumu |

**Mülakat Planlama Akışı:**

```
İK Uzmanı mülakat planlar
    │
    ├── Aday seçer
    ├── Mülakat türü ve tarihi belirler
    ├── Mülakatçıları ekler
    └── Lokasyon veya link girer
        │
        ▼
    Sistem otomatik:
    ├── Mülakatçılara takvim daveti gönderir (e-posta)
    ├── Adaya mülakat davetiyesi gönderir (e-posta + SMS)
    └── Mülakata 1 gün kala hatırlatma planlar (Celery)
        │
        ▼
    Mülakat sonrası:
    ├── Mülakatçılar skor kartı doldurur
    └── İK uzmanı aday aşamasını günceller
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-MLK-01 | Mülakat planlandığında adaya ve tüm katılımcılara e-posta davetiyesi gönderilir |
| IK-MLK-02 | Mülakata 24 saat kala adaya hatırlatma SMS'i gönderilir |
| IK-MLK-03 | Mülakata 1 saat kala mülakatçılara push bildirim gönderilir |
| IK-MLK-04 | Mülakat iptal edildiğinde tüm taraflara iptal bildirimi gönderilir |
| IK-MLK-05 | Bir başvuru için birden fazla mülakat planlanabilir (turlar: 1. tur, 2. tur) |
| IK-MLK-06 | Geçmiş tarihe mülakat planlanamaz |
| IK-MLK-07 | Aday `no_show` durumunda İK'ya otomatik bildirim gönderilir |
| IK-MLK-08 | Mülakat takvimi Google Calendar / Outlook ile senkronize edilebilir (Faz 3+ — takvim entegrasyonu) |

---

### 3.6 Teklif Süreci

#### FR-ATS-07: Teklif Mektubu Oluşturma

**Açıklama:** Adaya resmi iş teklifi gönderilebilmeli; teklif şablon bazlı PDF olarak oluşturulabilmelidir.

#### `ats_offers` — Teklif Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `application_id` | BIGINT, FK | Hangi başvuru |
| `offered_position_id` | BIGINT, FK | Teklif edilen pozisyon |
| `offered_department_id` | BIGINT, FK | Teklif edilen departman |
| `offered_salary` | NUMERIC(15,2) | Teklif edilen brüt maaş |
| `currency` | VARCHAR(3), default: 'TRY' | Para birimi |
| `employment_type` | VARCHAR(30) | `full_time`, `part_time`, vb. |
| `contract_type` | VARCHAR(30) | `indefinite`, `fixed_term` |
| `proposed_start_date` | DATE | Önerilen başlangıç tarihi |
| `benefits` | JSONB, nullable | Ek yan haklar |
| `offer_letter_url` | VARCHAR(500), nullable | Oluşturulan PDF'in MinIO URL'i |
| `status` | VARCHAR(20) | `draft`, `sent`, `accepted`, `rejected`, `expired`, `withdrawn` |
| `sent_at` | TIMESTAMPTZ, nullable | Adaya gönderilme zamanı |
| `responded_at` | TIMESTAMPTZ, nullable | Adayın yanıt zamanı |
| `expiry_date` | DATE, nullable | Teklifin geçerlilik süresi |
| `rejection_reason` | TEXT, nullable | Red gerekçesi |
| `approved_by` | BIGINT, FK, nullable | Teklifi onaylayan (İK müdürü / yönetici) |
| `created_by` | BIGINT, FK | Teklifi oluşturan |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Teklif Durumları:**

```
draft → sent → accepted → (personel modülüne transfer)
  │       │        │
  │       ├── rejected (aday reddetti)
  │       ├── expired (süre doldu)
  │       └── withdrawn (firma geri çekti)
  │
  └── İptal (hiç gönderilmedi)
```

**Teklif Mektubu PDF Şablonu:**

```
┌───────────────────────────────────────────────────┐
│                    FİRMA LOGOSU                    │
│                                                   │
│  Tarih: 15 Nisan 2026                             │
│                                                   │
│  Sayın Ahmet Yılmaz,                              │
│                                                   │
│  [Firma Adı] bünyesinde [Pozisyon] pozisyonunda   │
│  görev almanız için teklifimizi iletmekten         │
│  memnuniyet duyarız.                              │
│                                                   │
│  Pozisyon: Kıdemli Python Geliştirici              │
│  Departman: Yazılım Geliştirme                    │
│  Çalışma Türü: Tam Zamanlı                        │
│  Brüt Maaş: ₺48.000 / ay                         │
│  Başlangıç Tarihi: 1 Mayıs 2026                  │
│  Yan Haklar: Özel sağlık sigortası, yemek kartı   │
│                                                   │
│  Bu teklif 7 gün geçerlidir.                      │
│                                                   │
│  Saygılarımızla,                                  │
│  [İK Müdürü Adı]                                  │
│  [Firma Adı]                                      │
└───────────────────────────────────────────────────┘
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-TKL-01 | Teklif oluşturmak için İK müdürü veya yetkili onayı gerekebilir (tenant ayarlarına göre) |
| IK-TKL-02 | Teklif gönderildiğinde adaya e-posta ile PDF teklif mektubu iletilir |
| IK-TKL-03 | Teklif süresi dolduğunda otomatik `expired` olur (Celery job) |
| IK-TKL-04 | Kabul edilen teklifte aday otomatik olarak `hired` aşamasına geçer |
| IK-TKL-05 | Aynı başvuru için aynı anda yalnızca bir aktif teklif olabilir |
| IK-TKL-06 | Teklif PDF'i WeasyPrint ile şablon bazlı oluşturulur |
| IK-TKL-07 | Teklif PDF'i MinIO'da `{tenant_id}/ats/offers/{offer_id}/` yoluna kaydedilir |
| IK-TKL-08 | Maaş alanı yalnızca `recruitment:offer:salary` yetkisine sahip kullanıcılara görünür |

---

### 3.7 Aday Havuzu

#### FR-ATS-08: Aday Havuzu

**Açıklama:** Reddedilen veya bekleyen adaylar gelecekteki pozisyonlar için havuzda saklanabilmelidir.

**Aday Havuzu Yapısı:**

| Özellik | Açıklama |
|---------|----------|
| Otomatik ekleme | Aday reddedildiğinde veya çekildiğinde KVKK onayı varsa havuza otomatik eklenir |
| Manuel ekleme | İK uzmanı herhangi bir adayı havuza ekleyebilir |
| Etiketleme | Adaylar yetkinlik, deneyim, pozisyon gibi etiketlerle kategorize edilir |
| Arama | Havuzda yetkinlik, pozisyon, konum, etiket bazlı arama yapılabilir |
| Yeniden başvuru | Havuzdaki aday yeni bir ilana hızlıca atanabilir (mevcut verileri korunarak) |
| Süre sınırı | KVKK gereği aday verisi belirli süre sonra silinir (varsayılan: 2 yıl) |

#### `ats_talent_pool` — Aday Havuzu Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `candidate_id` | BIGINT, FK | Aday |
| `tags` | VARCHAR[], nullable | Etiketler: `["python", "senior", "remote"]` |
| `source_application_id` | BIGINT, FK, nullable | Havuza eklenme kaynağı olan başvuru |
| `notes` | TEXT, nullable | İK notu |
| `added_by` | BIGINT, FK | Ekleyen kişi |
| `kvkk_consent_expiry` | DATE | KVKK onayı geçerlilik süresi |
| `status` | VARCHAR(20) | `active`, `contacted`, `expired`, `removed` |
| `created_at` | TIMESTAMPTZ | |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-HVZ-01 | Aday havuzuna ekleme, KVKK açık rızası olan adaylar için yapılabilir |
| IK-HVZ-02 | KVKK onay süresi dolduğunda aday havuzundan otomatik çıkarılır (veri silinir veya anonimleştirilir) |
| IK-HVZ-03 | Havuzdaki aday yeni bir ilana atandığında mevcut CV ve notları korunur |
| IK-HVZ-04 | Etiketlerle aday aranabilir ve filtrelenebilir |
| IK-HVZ-05 | Aday, kendi verisinin silinmesini talep edebilir (KVKK hakkı) |
| IK-HVZ-06 | Günlük Celery job ile KVKK süresi dolan aday havuzu kayıtları temizlenir |

---

### 3.8 Aday İletişim Geçmişi

#### FR-ATS-10: Aday İletişim Geçmişi

**Açıklama:** Aday ile yapılan tüm iletişim kronolojik olarak takip edilmelidir.

#### `ats_communications` — İletişim Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `application_id` | BIGINT, FK | Hangi başvuru |
| `type` | VARCHAR(20) | `email`, `phone`, `sms`, `note`, `system` |
| `direction` | VARCHAR(10) | `outbound`, `inbound`, `internal` |
| `subject` | VARCHAR(255), nullable | E-posta konusu |
| `content` | TEXT | İçerik (e-posta metni, telefon notu, sistem notu) |
| `sent_by` | BIGINT, FK, nullable | Gönderen (İK kullanıcısı) |
| `sent_at` | TIMESTAMPTZ | |
| `is_auto` | BOOLEAN, default: false | Otomatik gönderim mi (ör: onay e-postası) |

**İletişim Türleri:**

| Tür | Açıklama | Örnek |
|-----|----------|-------|
| `email` | E-posta iletişimi | Başvuru onayı, mülakat daveti, teklif |
| `phone` | Telefon görüşmesi notu | "Aday ile telefonda görüşüldü, müsaitliği..." |
| `sms` | SMS gönderimi | Mülakat hatırlatma |
| `note` | İç not (aday göremez) | "Referans kontrolü yapıldı, olumlu" |
| `system` | Sistem tarafından oluşturulan | "Aday 'Mülakat' aşamasına taşındı" |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-ILT-01 | Otomatik gönderilen tüm e-postalar iletişim geçmişine kaydedilir |
| IK-ILT-02 | İK uzmanı manuel not / telefon notu ekleyebilir |
| IK-ILT-03 | İletişim geçmişi kronolojik sırada gösterilir (en yeni üstte) |
| IK-ILT-04 | İç notlar (`internal`) adaya görünmez |
| IK-ILT-05 | İletişim kayıtları silinemez (audit trail) |

---

### 3.9 Kariyer Sayfası (Gömülebilir)

#### FR-ATS-11: Kariyer Sayfası

**Açıklama:** Şirketin web sitesine gömülebilir bir kariyer sayfası sunulmalıdır.

**Kariyer Sayfası Özellikleri:**

| Özellik | Açıklama |
|---------|----------|
| Gömülebilir widget | `<iframe>` veya JavaScript embed kodu ile şirket sitesine entegre |
| Standalone sayfa | `careers.{tenant-slug}.ikplatform.com` benzeri alt alan |
| İlan listesi | Aktif ilanlar filtrelenebilir (departman, lokasyon, çalışma türü) |
| İlan detayı | İş tanımı, gereksinimler, başvuru formu |
| Responsive | Mobil uyumlu |
| Tema özelleştirme | Firma renkleri, logo, özel CSS |
| SEO uyumlu | Meta tags, Open Graph, structured data (JobPosting schema) |
| Dil desteği | Türkçe (varsayılan), İngilizce |

**Embed Kodu Örneği:**

```html
<!-- Kariyer Sayfası Embed -->
<div id="ik-careers-widget"></div>
<script src="https://cdn.ikplatform.com/careers.js" 
        data-tenant="firma-slug" 
        data-theme="light"
        data-lang="tr">
</script>
```

**Kariyer Sayfası Endpoint'leri (Public — Auth Gerekmez):**

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/public/careers/{tenant_slug}/jobs` | Aktif ilan listesi |
| `GET` | `/public/careers/{tenant_slug}/jobs/{slug}` | İlan detayı |
| `POST` | `/public/careers/{tenant_slug}/jobs/{slug}/apply` | Başvuru gönder |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-KRY-01 | Kariyer sayfası public endpoint'tir, auth gerektirmez |
| IK-KRY-02 | Yalnızca `published` durumundaki ilanlar gösterilir |
| IK-KRY-03 | Rate limiting: IP başına 10 başvuru/saat |
| IK-KRY-04 | Başvuru formunda CAPTCHA (hCaptcha) entegrasyonu ile bot koruması |
| IK-KRY-05 | Embed widget'ı CORS politikası ile sınırlandırılır (tenant whitelist) |
| IK-KRY-06 | SEO için `JobPosting` JSON-LD schema oluşturulur |

---

### 3.10 KVKK Aday Rızası Yönetimi

#### FR-ATS-12: KVKK Aday Rızası

**Açıklama:** Başvuru sırasında adaydan açık rıza alınmalı, saklama süreleri yönetilmelidir.

**KVKK Gereksinimleri:**

| Gereksinim | Uygulama |
|------------|----------|
| **Aydınlatma metni** | Başvuru formunda KVKK aydınlatma metni gösterilir ve onay alınır |
| **Açık rıza** | "Kişisel verilerimin işlenmesini kabul ediyorum" checkbox'ı |
| **Aday havuzu rızası** | Ek checkbox: "Verilerimin gelecek pozisyonlar için saklanmasını kabul ediyorum" |
| **Saklama süresi** | Varsayılan: 2 yıl (tenant ayarlarından değiştirilebilir) |
| **Silme hakkı** | Aday e-posta ile veri silme talebi yapabilir |
| **Veri taşınabilirliği** | Adayın verisi JSON/CSV olarak dışa aktarılabilir |
| **Rıza kaydı** | Rıza tarihi, IP adresi, onaylanan metin versiyonu kaydedilir |

#### `ats_consent_records` — Rıza Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `candidate_id` | BIGINT, FK | |
| `consent_type` | VARCHAR(30) | `application_data`, `talent_pool`, `marketing` |
| `consent_text_version` | VARCHAR(20) | Onaylanan metin versiyonu: "v1.2" |
| `is_granted` | BOOLEAN | Onay verildi mi |
| `granted_at` | TIMESTAMPTZ | Onay zamanı |
| `ip_address` | INET | Onay veren IP |
| `user_agent` | TEXT | Tarayıcı bilgisi |
| `revoked_at` | TIMESTAMPTZ, nullable | Rıza geri çekilme zamanı |
| `expiry_date` | DATE | Rıza geçerlilik tarihi |

**Otomatik Temizlik (Celery Beat):**

```
Haftalık Celery Job (her Pazar 02:00)
    │
    ▼
ats_consent_records tablosunda expiry_date geçmiş kayıtları bul
    │
    ▼
İlişkili aday verilerini:
    ├── Aktif başvurusu yok → Anonimleştir veya sil
    ├── Aktif başvurusu var → Atla (süreç devam ediyor)
    └── Aday havuzunda → Havuzdan çıkar
    │
    ▼
Silme/anonimleştirme logunu kaydet
```

---

## 4. Veritabanı Tasarımı

### 4.1 Tablo Listesi

07-veritabani-tasarimi.md'deki konvansiyonlara (Bölüm 2) ve multi-tenant kurallarına (Bölüm 3) uyumludur.

```
ats_candidates ───────────────── ats_talent_pool
    │                                
    └── ats_applications ─────── ats_evaluations
            │                        
            ├── ats_interviews ── ats_interview_participants
            │                    
            ├── ats_offers       
            │                    
            ├── ats_communications
            │                    
            └── ats_stage_history
                                 
ats_jobs (ilanlar)               
    │                            
    └── ats_job_channels         
                                 
ats_pipeline_stages (özelleştirilebilir aşamalar)
                                 
ats_scorecard_templates          
                                 
ats_consent_records              
```

### 4.2 Ana Tablolar

#### `ats_candidates` — Aday Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `first_name` | VARCHAR(100) | |
| `last_name` | VARCHAR(100) | |
| `email` | VARCHAR(255) | Benzersiz (tenant içinde) |
| `phone` | VARCHAR(20), nullable | |
| `linkedin_url` | VARCHAR(500), nullable | |
| `resume_url` | VARCHAR(500), nullable | MinIO'daki son CV URL'i |
| `source` | VARCHAR(30), nullable | İlk başvuru kaynağı |
| `tags` | VARCHAR[], nullable | Etiketler |
| `metadata` | JSONB, nullable | Ek bilgiler |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

> **Not:** Aday (`ats_candidates`) ve başvuru (`ats_applications`) ayrı tablolardır. Bir aday birden fazla ilana başvurabilir.

#### `ats_jobs` — İş İlanları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `title` | VARCHAR(255) | İlan başlığı |
| `slug` | VARCHAR(255) | URL-friendly benzersiz slug |
| `department_id` | BIGINT, FK | |
| `position_id` | BIGINT, FK | |
| `branch_id` | BIGINT, FK, nullable | |
| `hiring_manager_id` | BIGINT, FK, nullable | Pozisyon yöneticisi |
| `recruiter_id` | BIGINT, FK | İlan sorumlusu (İK uzmanı) |
| `employment_type` | VARCHAR(30) | `full_time`, `part_time`, `intern`, `contract` |
| `work_model` | VARCHAR(20) | `office`, `remote`, `hybrid` |
| `experience_level` | VARCHAR(20), nullable | `junior`, `mid`, `senior`, `lead`, `manager` |
| `description` | TEXT | İş tanımı (Markdown) |
| `requirements` | TEXT | Aranan nitelikler (Markdown) |
| `preferred` | TEXT, nullable | Tercih edilen (Markdown) |
| `salary_min` | NUMERIC(15,2), nullable | Maaş aralığı alt |
| `salary_max` | NUMERIC(15,2), nullable | Maaş aralığı üst |
| `currency` | VARCHAR(3), default: 'TRY' | |
| `show_salary` | BOOLEAN, default: false | Adaya maaş gösterilsin mi |
| `headcount` | SMALLINT, default: 1 | Alınacak kişi sayısı |
| `deadline` | DATE, nullable | Son başvuru tarihi |
| `tags` | VARCHAR[], nullable | Etiketler |
| `status` | VARCHAR(20) | `draft`, `published`, `closed`, `archived` |
| `published_at` | TIMESTAMPTZ, nullable | Yayınlanma zamanı |
| `closed_at` | TIMESTAMPTZ, nullable | Kapanma zamanı |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `is_deleted` | BOOLEAN, default: false | Soft delete |

**İndeksler:**

```sql
-- İlan arama ve filtreleme
CREATE INDEX ix_ats_jobs_tenant_status ON ats_jobs (tenant_id, status);
CREATE INDEX ix_ats_jobs_slug ON ats_jobs (tenant_id, slug) WHERE is_deleted = false;
CREATE INDEX ix_ats_jobs_dept ON ats_jobs (tenant_id, department_id, status);
CREATE INDEX ix_ats_jobs_deadline ON ats_jobs (deadline) WHERE status = 'published';

-- İlan full-text search
ALTER TABLE ats_jobs ADD COLUMN search_vector TSVECTOR
GENERATED ALWAYS AS (
    to_tsvector('turkish', coalesce(title, '') || ' ' || coalesce(description, ''))
) STORED;
CREATE INDEX ix_ats_jobs_search ON ats_jobs USING GIN (search_vector);
```

#### `ats_applications` — Başvurular

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `job_id` | BIGINT, FK | Hangi ilan |
| `candidate_id` | BIGINT, FK | Hangi aday |
| `current_stage` | VARCHAR(30) | Mevcut pipeline aşaması |
| `source` | VARCHAR(30) | `career_page`, `linkedin`, `kariyer_net`, `referral`, `email`, `manual` |
| `resume_url` | VARCHAR(500), nullable | Başvuru anındaki CV (MinIO) |
| `cover_letter` | TEXT, nullable | Ön yazı |
| `expected_salary` | NUMERIC(15,2), nullable | Beklenen maaş |
| `available_from` | DATE, nullable | En erken başlangıç tarihi |
| `overall_score` | NUMERIC(5,2), nullable | Tüm değerlendirmelerin ortalaması |
| `is_in_talent_pool` | BOOLEAN, default: false | Aday havuzuna eklendi mi |
| `rejection_reason` | TEXT, nullable | Red gerekçesi |
| `hired_employee_id` | BIGINT, FK, nullable | İşe alındıysa oluşturulan çalışan kaydı |
| `applied_at` | TIMESTAMPTZ | Başvuru zamanı |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**İndeksler:**

```sql
CREATE INDEX ix_ats_applications_tenant_job ON ats_applications (tenant_id, job_id);
CREATE INDEX ix_ats_applications_candidate ON ats_applications (tenant_id, candidate_id);
CREATE INDEX ix_ats_applications_stage ON ats_applications (tenant_id, current_stage);
CREATE UNIQUE INDEX uq_ats_applications_job_candidate 
    ON ats_applications (tenant_id, job_id, candidate_id); -- Aynı ilana tek başvuru
```

#### `ats_stage_history` — Aşama Geçmişi

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `application_id` | BIGINT, FK | |
| `from_stage` | VARCHAR(30), nullable | Önceki aşama (ilk giriş için null) |
| `to_stage` | VARCHAR(30) | Yeni aşama |
| `changed_by` | BIGINT, FK | Değişikliği yapan |
| `notes` | TEXT, nullable | Aşama değişikliği notu |
| `created_at` | TIMESTAMPTZ | |

#### `ats_pipeline_stages` — Özelleştirilebilir Pipeline Aşamaları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `code` | VARCHAR(30) | Aşama kodu |
| `name` | VARCHAR(100) | Görüntülenen isim |
| `color` | VARCHAR(7), nullable | Hex renk kodu |
| `sort_order` | SMALLINT | Sıralama |
| `is_system` | BOOLEAN, default: false | Sistem aşaması mı (silinemez) |
| `is_terminal` | BOOLEAN, default: false | Son aşama mı (`hired`, `rejected`, `withdrawn`) |
| `is_active` | BOOLEAN, default: true | |

---

## 5. API Endpoint Detayları

Tüm ATS endpoint'leri `/api/v1/recruitment` prefix'i altındadır (08-api-tasarimi.md, Bölüm 7).

### 5.1 İlan Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/recruitment/jobs` | İlan listesi (filtre + sayfalama) | `recruitment:job:read` |
| `POST` | `/recruitment/jobs` | Yeni ilan oluştur | `recruitment:job:create` |
| `GET` | `/recruitment/jobs/{id}` | İlan detayı | `recruitment:job:read` |
| `PUT` | `/recruitment/jobs/{id}` | İlan güncelle | `recruitment:job:update` |
| `PATCH` | `/recruitment/jobs/{id}/publish` | İlan yayınla | `recruitment:job:update` |
| `PATCH` | `/recruitment/jobs/{id}/close` | İlan kapat | `recruitment:job:update` |
| `POST` | `/recruitment/jobs/{id}/duplicate` | İlan kopyala | `recruitment:job:create` |
| `GET` | `/recruitment/jobs/{id}/stats` | İlan istatistikleri (başvuru sayıları, aşama dağılımı) | `recruitment:job:read` |

### 5.2 Başvuru / Aday Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/recruitment/jobs/{id}/applications` | İlana yapılan başvurular (kanban view) | `recruitment:application:read` |
| `POST` | `/recruitment/jobs/{id}/applications` | Manuel başvuru ekleme | `recruitment:application:create` |
| `GET` | `/recruitment/applications/{id}` | Başvuru detayı (aday bilgisi + geçmiş) | `recruitment:application:read` |
| `PATCH` | `/recruitment/applications/{id}/stage` | Aşama değiştir | `recruitment:application:update` |
| `PATCH` | `/recruitment/applications/{id}/reject` | Adayı reddet | `recruitment:application:update` |
| `POST` | `/recruitment/applications/{id}/convert` | Adayı çalışana dönüştür (personel modülüne) | `recruitment:application:convert` |
| `GET` | `/recruitment/candidates` | Aday listesi (tüm adaylar) | `recruitment:candidate:read` |
| `GET` | `/recruitment/candidates/{id}` | Aday detayı (tüm başvuruları dahil) | `recruitment:candidate:read` |

### 5.3 Mülakat Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/recruitment/applications/{id}/interviews` | Mülakat planla | `recruitment:interview:create` |
| `GET` | `/recruitment/applications/{id}/interviews` | Başvurunun mülakatları | `recruitment:interview:read` |
| `PUT` | `/recruitment/interviews/{id}` | Mülakat güncelle | `recruitment:interview:update` |
| `PATCH` | `/recruitment/interviews/{id}/cancel` | Mülakat iptal et | `recruitment:interview:update` |
| `GET` | `/recruitment/interviews/upcoming` | Yaklaşan mülakatlar (takvim) | `recruitment:interview:read` |

### 5.4 Değerlendirme Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/recruitment/applications/{id}/evaluations` | Değerlendirme / skor kartı gönder | `recruitment:evaluation:create` |
| `GET` | `/recruitment/applications/{id}/evaluations` | Başvurunun değerlendirmeleri | `recruitment:evaluation:read` |
| `GET` | `/recruitment/scorecard-templates` | Skor kartı şablonları | `recruitment:scorecard:read` |
| `POST` | `/recruitment/scorecard-templates` | Skor kartı şablonu oluştur | `recruitment:scorecard:manage` |

### 5.5 Teklif Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/recruitment/applications/{id}/offers` | Teklif oluştur | `recruitment:offer:create` |
| `GET` | `/recruitment/applications/{id}/offers` | Başvurunun teklifleri | `recruitment:offer:read` |
| `PATCH` | `/recruitment/offers/{id}/send` | Teklifi gönder | `recruitment:offer:send` |
| `PATCH` | `/recruitment/offers/{id}/accept` | Teklifi kabul et (İK tarafından) | `recruitment:offer:update` |
| `PATCH` | `/recruitment/offers/{id}/reject` | Teklifi reddet | `recruitment:offer:update` |
| `PATCH` | `/recruitment/offers/{id}/withdraw` | Teklifi geri çek | `recruitment:offer:update` |
| `GET` | `/recruitment/offers/{id}/pdf` | Teklif PDF'ini indir | `recruitment:offer:read` |

### 5.6 Aday Havuzu Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/recruitment/talent-pool` | Aday havuzu listesi (filtre + arama) | `recruitment:talent_pool:read` |
| `POST` | `/recruitment/talent-pool` | Havuza aday ekle | `recruitment:talent_pool:manage` |
| `DELETE` | `/recruitment/talent-pool/{id}` | Havuzdan kaldır | `recruitment:talent_pool:manage` |

### 5.7 İletişim Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/recruitment/applications/{id}/communications` | İletişim geçmişi | `recruitment:communication:read` |
| `POST` | `/recruitment/applications/{id}/communications` | Not / e-posta kaydı ekle | `recruitment:communication:create` |

### 5.8 Rapor Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/recruitment/reports/pipeline-summary` | Pipeline özet raporu | `recruitment:report:read` |
| `GET` | `/recruitment/reports/time-to-hire` | Time-to-hire raporu | `recruitment:report:read` |
| `GET` | `/recruitment/reports/source-analysis` | Kaynak analizi raporu | `recruitment:report:read` |
| `GET` | `/recruitment/reports/recruiter-performance` | İşe alım uzmanı performansı | `recruitment:report:read` |

---

## 6. Aday → Çalışan Dönüşüm Akışı

Teklif kabul edildikten sonra adayın personel modülüne aktarımı:

```
Teklif Kabul Edildi (ats_offers.status = 'accepted')
    │
    ▼
İK Uzmanı "Çalışana Dönüştür" butonuna tıklar
    │
    ▼
Dönüşüm formu açılır (aday verileri ön doldurulmuş):
    ├── Ad / Soyad (adaydan)
    ├── E-posta (adaydan)
    ├── Telefon (adaydan)
    ├── Departman / Pozisyon (tekliften)
    ├── Maaş (tekliften)
    ├── İşe başlama tarihi (tekliften)
    ├── Çalışma türü / Sözleşme türü (tekliften)
    └── + Eksik alanlar (TC kimlik, sicil no, IBAN vb.)
        │
        ▼
    İK eksik alanları doldurur ve kaydeder
        │
        ▼
    Sistem:
    ├── personnel_employees kaydı oluşturur
    ├── ats_applications.hired_employee_id güncellenir
    ├── ats_applications.current_stage = 'hired' olur
    ├── İlan headcount 1 azalır; 0'a düştüyse ilan otomatik kapanır
    ├── Personel onboarding checklist başlatılır
    └── Aday CV'si çalışan belgeleri arasına kopyalanır
```

**POST `/api/v1/recruitment/applications/{id}/convert`**

**Request Body:**

```json
{
  "tc_identity_no": "12345678901",
  "employee_number": "S042",
  "hire_date": "2026-05-01",
  "base_salary": 48000.00,
  "department_id": 3,
  "position_id": 12,
  "branch_id": 1,
  "employment_type": "full_time",
  "contract_type": "indefinite"
}
```

**Response (201 Created):**

```json
{
  "success": true,
  "data": {
    "employee_id": 42,
    "employee_number": "S042",
    "full_name": "Ahmet Yılmaz",
    "message": "Aday başarıyla çalışana dönüştürüldü."
  }
}
```

---

## 7. Ekran Tasarımı Rehberi

### 7.1 Ekran Listesi

| # | Ekran | Platform | Rol | Öncelik |
|---|-------|----------|-----|---------|
| 1 | İlan Listesi | Web | İK | Must |
| 2 | İlan Oluşturma / Düzenleme | Web | İK | Must |
| 3 | İlan Detayı + Pipeline Kanban | Web | İK | Must |
| 4 | Aday Profili (başvuru detayı) | Web | İK, Yönetici | Must |
| 5 | Mülakat Planlama Modal | Web | İK | Should |
| 6 | Mülakat Takvimi | Web | İK, Yönetici | Should |
| 7 | Skor Kartı Formu | Web + Mobil | İK, Yönetici | Must |
| 8 | Teklif Oluşturma Formu | Web | İK | Should |
| 9 | Aday Havuzu | Web | İK | Should |
| 10 | İşe Alım Dashboard | Web | İK, C-Level | Should |
| 11 | Kariyer Sayfası (public) | Web (responsive) | Aday | Must |
| 12 | Başvuru Formu (public) | Web (responsive) | Aday | Must |

### 7.2 İlan Listesi Ekranı

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ İK Paneli  /  İşe Alım  /  İlanlar                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ [🔍 İlan ara...       ]  [Durum ▼] [Dept. ▼]  [+ Yeni İlan] │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 🟢 Kıdemli Python Geliştirici                          │   │
│ │ Yazılım Geliştirme · İstanbul · Tam Zamanlı · Remote   │   │
│ │ 📊 45 başvuru · 3 mülakat · 1 teklif                   │   │
│ │ 📅 Yayın: 01.04.2026 · Son: 30.04.2026                │   │
│ │ 👤 Sorumlu: Fatma Şahin                                │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 🟢 UI/UX Tasarımcı                                     │   │
│ │ Ürün · İstanbul · Tam Zamanlı · Hibrit                 │   │
│ │ 📊 28 başvuru · 5 mülakat · 0 teklif                   │   │
│ │ 📅 Yayın: 05.04.2026 · Son: 25.04.2026                │   │
│ │ 👤 Sorumlu: Fatma Şahin                                │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ ⚫ Satış Müdürü                        [TASLAK]        │   │
│ │ Satış · Ankara · Tam Zamanlı · Ofis                    │   │
│ │ 📊 — başvuru                                           │   │
│ │ 📅 Oluşturuldu: 08.04.2026                             │   │
│ │ 👤 Sorumlu: Fatma Şahin                                │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ Gösterilen: 3 / 12 ilan                    ◀ 1 2 ... ▶      │
└──────────────────────────────────────────────────────────────┘
```

### 7.3 Kanban Pipeline Ekranı

```
┌──────────────────────────────────────────────────────────────────┐
│ ◀ İlanlar / Kıdemli Python Geliştirici          [Düzenle] [⋮]  │
├──────────────────────────────────────────────────────────────────┤
│ 📊 45 Başvuru · ⏱ Ort. Süre: 18 gün · 🎯 Dönüşüm: %2.2       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│ │Yeni (25) │ │ Ön E.(12)│ │Mülakat(5)│ │Değerl.(2)│ │Teklif 1│ │
│ ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤ ├────────┤ │
│ │┌────────┐│ │┌────────┐│ │┌────────┐│ │┌────────┐│ │┌──────┐│ │
│ ││A. Yılmaz│ ││E. Kaya ││ ││C. Demir││ ││S. Tekin││ ││M.Kara││ │
│ ││★★★★☆  ││ ││★★★☆☆  ││ ││★★★★★  ││ ││★★★★☆  ││ ││★★★★★ ││ │
│ ││2 gün   ││ ││3 gün   ││ ││1 gün   ││ ││2 gün   ││ ││Bekle.││ │
│ │└────────┘│ │└────────┘│ │└────────┘│ │└────────┘│ │└──────┘│ │
│ │┌────────┐│ │┌────────┐│ │┌────────┐│ │┌────────┐│ │        │ │
│ ││F. Sarı ││ ││B. Mutlu││ ││A. Tunç ││ ││O. Hasan││ │        │ │
│ ││yeni    ││ ││★★★★☆  ││ ││★★★★☆  ││ ││★★★☆☆  ││ │        │ │
│ │└────────┘│ │└────────┘│ │└────────┘│ │└────────┘│ │        │ │
│ │   ...    │ │   ...    │ │   ...    │ │          │ │        │ │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │
│                                                                  │
│  Reddedilen: 8 · Çekilen: 2                                     │
└──────────────────────────────────────────────────────────────────┘
```

### 7.4 Aday Profili (Detay)

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ Pipeline  /  Ahmet Yılmaz                                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐  Ahmet Yılmaz                 Aşama: Mülakat   │
│  │         │  ahmet.yilmaz@email.com       ★★★★☆ (4.2/5)    │
│  │  📷     │  +90 555 123 45 67                              │
│  │         │  LinkedIn: /in/ahmetyilmaz                      │
│  └─────────┘  Başvuru: 01.04.2026 (8 gün önce)              │
│               Kaynak: Kariyer Sayfası                        │
│                                                              │
│ ┌─────────┬───────────┬───────────┬────────────┬───────────┐ │
│ │   CV    │Değerlend. │ Mülakatlar│  İletişim  │ Geçmiş    │ │
│ └─────────┴───────────┴───────────┴────────────┴───────────┘ │
│                                                              │
│ Aksiyonlar:                                                  │
│ [📅 Mülakat Planla] [⭐ Değerlendir] [➡ Aşama Değiştir]     │
│ [📧 E-posta Gönder] [❌ Reddet] [💼 Teklif Oluştur]         │
│                                                              │
│ ─── CV İçeriği ─────────────────────────────────              │
│ ┌──────────────────────────────────────────────┐             │
│ │  📄 ahmet_yilmaz_cv.pdf                      │             │
│ │  [Görüntüle] [İndir]                        │             │
│ └──────────────────────────────────────────────┘             │
│                                                              │
│ ─── Aşama Geçmişi ─────────────────────────────              │
│ 01.04 Yeni Başvuru (Fatma S.)                                │
│ 03.04 → Ön Eleme (Fatma S.) "CV uygun, devam"               │
│ 05.04 → Mülakat (Fatma S.) "Teknik mülakat planlandı"       │
└──────────────────────────────────────────────────────────────┘
```

### 7.5 Kariyer Sayfası (Public — Aday Görünümü)

```
┌──────────────────────────────────────────────────────────────┐
│                    🏢 FİRMA ADI                               │
│                    Kariyer Fırsatları                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ [🔍 Pozisyon ara...     ] [Departman ▼] [Lokasyon ▼]         │
│                           [Çalışma Türü ▼]                   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ Kıdemli Python Geliştirici                              │   │
│ │ Yazılım Geliştirme · İstanbul · Tam Zamanlı · Remote   │   │
│ │ Son Başvuru: 30.04.2026                                │   │
│ │                                        [Başvur →]      │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ UI/UX Tasarımcı                                         │   │
│ │ Ürün · İstanbul · Tam Zamanlı · Hibrit                 │   │
│ │ Son Başvuru: 25.04.2026                                │   │
│ │                                        [Başvur →]      │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ 2 açık pozisyon                                              │
│                                                              │
│ ─────────────────────────────────────────────────────────    │
│ © 2026 Firma Adı · KVKK Aydınlatma Metni                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. Raporlama ve Metrikler

### 8.1 İşe Alım Raporları

| # | Rapor | Açıklama | Filtreler | Format |
|---|-------|----------|-----------|--------|
| 1 | Pipeline Özet Raporu | Her aşamadaki aday sayısı (ilan bazlı) | İlan, tarih | Dashboard + Excel |
| 2 | Time-to-Hire | İş ilanı açılıştan işe alıma geçen süre | İlan, departman, tarih | Ortalama/median grafik |
| 3 | Time-to-Fill | İlan yayınından pozisyon doldurulmasına geçen süre | İlan, departman | Trend çizgi grafik |
| 4 | Kaynak Analizi (Source) | Hangi kanaldan kaç başvuru geldi, dönüşüm oranı | Tarih, ilan | Pasta + çubuk grafik |
| 5 | Dönüşüm Hunisi | Aşama bazlı dönüşüm oranları | İlan, tarih | Funnel grafik |
| 6 | Recruiter Performansı | İşe alım uzmanı bazlı ilan/başvuru/işe alım sayıları | Recruiter, tarih | Tablo |
| 7 | Red Nedenleri Analizi | Neden/aşama bazlı red dağılımı | İlan, tarih | Pasta grafik |
| 8 | Aday Havuzu Raporu | Havuzdaki aday sayısı, yetkinlik dağılımı | Etiket, tarih | Tablo + Excel |
| 9 | Teklif Kabul Oranı (Offer Acceptance Rate) | Gönderilen tekliflerin kabul/ret oranı | Tarih, departman | Yüzde |
| 10 | Cost-per-Hire | Pozisyon başına işe alım maliyeti | İlan, departman | Tablo |

### 8.2 Dashboard Kartları (İşe Alım Bölümü)

```
┌────────────────────────────────────────────────────────────┐
│                    İŞE ALIM DASHBOARD                      │
├────────────┬────────────┬────────────┬────────────────────  │
│  Açık      │  Bu Ay     │  Ort.      │  Teklif              │
│  İlan      │  Başvuru   │  Time-to   │  Kabul               │
│  ┌──────┐  │  ┌──────┐  │  -Hire     │  Oranı               │
│  │  5   │  │  │  73  │  │  ┌──────┐  │  ┌──────┐            │
│  └──────┘  │  └──────┘  │  │ 22gün│  │  │ %75  │            │
│            │  ↑ %15     │  └──────┘  │  └──────┘            │
├────────────┴────────────┴────────────┴────────────────────  │
│                                                            │
│ Dönüşüm Hunisi             │ Kaynak Dağılımı              │
│ ┌─────────────────────┐    │ ┌──────────────────┐          │
│ │ ████████████ 73 Baş.│    │ │ Kariyer Say. 42% │          │
│ │ █████████  45 Ön El.│    │ │ LinkedIn     28% │          │
│ │ ██████    18 Mülakat│    │ │ Referans     18% │          │
│ │ ████       8 Değerl.│    │ │ Kariyer.net  12% │          │
│ │ ██         3 Teklif │    │ └──────────────────┘          │
│ │ █          2 İşeAlım│    │                               │
│ └─────────────────────┘    │ Time-to-Hire Trendi (6 ay)    │
│ Dönüşüm: %2.7             │ ┌──────────────────┐          │
│                            │ │  \    /\          │          │
│                            │ │   \  /  \___     │          │
│                            │ │    \/        \   │          │
│                            │ └──────────────────┘          │
└────────────────────────────────────────────────────────────┘
```

### 8.3 Rapor Metrikleri ve Hesaplama

| Metrik | Formül |
|--------|--------|
| **Time-to-Hire** | `hired` aşamasına geçiş tarihi − başvuru tarihi (gün) |
| **Time-to-Fill** | İlan kapanış tarihi − ilan yayın tarihi (gün) |
| **Offer Acceptance Rate** | (Kabul edilen teklif / Gönderilen teklif) × 100 |
| **Dönüşüm Oranı** | (Hired aday / Toplam başvuru) × 100 |
| **Aşama Dönüşümü** | (Sonraki aşamaya geçen / Mevcut aşama toplam) × 100 |
| **Source Effectiveness** | (Kaynak X'ten hired / Kaynak X'ten başvuru) × 100 |
| **Cost-per-Hire** | (İş ilanı maliyeti + işe alım uzmanı zamanı) / İşe alınan kişi sayısı |
| **Pipeline Velocity** | Ortalama aşama geçiş süresi (gün) |

---

## 9. İş Akışları ve Otomasyon

### 9.1 Otomatik Tetiklenen İşlemler

| Tetikleyici | İşlem | Yöntem |
|-------------|-------|--------|
| Başvuru alındı | Adaya onay e-postası | Celery |
| Başvuru alındı | İlan sorumlusuna bildirim | Push + in-app |
| Aşama değişti | `ats_stage_history` kaydı | Senkron |
| Aşama `interview` oldu | Mülakat planlama hatırlatması İK'ya | In-app bildirim |
| Mülakat planlandı | Adaya e-posta + SMS davetiye | Celery |
| Mülakat planlandı | Mülakatçılara takvim daveti | Celery |
| Mülakata 24 saat kala | Adaya SMS hatırlatma | Celery beat |
| Mülakata 1 saat kala | Mülakatçılara push bildirim | Celery beat |
| Skor kartı dolduruldu | İK uzmanına bildirim | Push + in-app |
| Teklif gönderildi | Adaya e-posta (PDF ek) | Celery |
| Teklif kabul edildi | İK'ya bildirim + `hired` aşamasına geçiş | Senkron + push |
| Teklif süresi doldu | Otomatik `expired`, İK'ya uyarı | Celery beat |
| Aday `hired` oldu | İlan headcount kontrolü (0 ise kapat) | Senkron |
| İlan son başvuru geçti | İlan otomatik `closed` | Celery beat (günlük) |
| KVKK rıza süresi doldu | Aday verisini anonimleştir / sil | Celery beat (haftalık) |

### 9.2 Celery Beat (Zamanlanmış Görevler)

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `close_expired_jobs` | Günlük 00:00 | Son başvuru tarihi geçen ilanları kapat |
| `remind_upcoming_interviews` | Günlük 08:00 | Yarınki mülakatlar için hatırlatma gönder |
| `expire_offers` | Günlük 09:00 | Süresi dolan teklifleri `expired` yap |
| `check_stale_applications` | Haftalık Pazartesi | 14+ gün aynı aşamada kalan başvuruları İK'ya bildir |
| `cleanup_expired_consent` | Haftalık Pazar 02:00 | KVKK rıza süresi dolan aday verilerini temizle |
| `calculate_recruitment_metrics` | Günlük 01:00 | Dashboard metriklerini hesapla ve cache'e yaz |

### 9.3 E-posta Şablonları

| Şablon | Tetikleyici | Alıcı | İçerik |
|--------|-------------|-------|--------|
| `application_received` | Başvuru alındı | Aday | "Başvurunuz alınmıştır. Sürecinizi takip edin." |
| `interview_invitation` | Mülakat planlandı | Aday | "Mülakata davetlisiniz. Tarih: ..., Yer/Link: ..." |
| `interview_reminder` | Mülakata 24 saat kala | Aday | "Yarın mülakatınız var. Detaylar: ..." |
| `offer_letter` | Teklif gönderildi | Aday | "Size iş teklifimizi sunuyoruz. (PDF ekte)" |
| `application_rejected` | Aday reddedildi | Aday | "Başvurunuz değerlendirilmiş olup..." |
| `application_hired` | Aday işe alındı | Aday | "Teklifiniz kabul edilmiştir. Başlangıç tarihiniz: ..." |

---

## 10. Güvenlik ve KVKK

### 10.1 Hassas Veri Sınıflandırması

| Veri | Hassasiyet | Erişim Kontrolü |
|------|-----------|-----------------|
| Aday CV dosyası | Yüksek | `recruitment:application:read` + signed URL |
| Aday e-posta/telefon | Orta | `recruitment:candidate:read` |
| Teklif maaşı | Yüksek | `recruitment:offer:salary` |
| Değerlendirme notları (private) | Orta | `recruitment:evaluation:read` (yalnızca İK) |
| KVKK rıza kayıtları | Çok Yüksek | Sistem (silinmez) |

### 10.2 Rol Bazlı Erişim Matrisi (ATS Modülü)

| İzin | Süper Admin | İK Yöneticisi | İşe Alım Uzmanı | Dept. Yöneticisi | Çalışan |
|------|------------|--------------|------------------|-----------------|---------|
| `recruitment:job:create` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `recruitment:job:read` | ✅ | ✅ | ✅ | Kendi departmanı | ❌ |
| `recruitment:job:update` | ✅ | ✅ | Kendi ilanları | ❌ | ❌ |
| `recruitment:application:read` | ✅ | ✅ | Kendi ilanları | Kendi departmanı | ❌ |
| `recruitment:application:update` | ✅ | ✅ | Kendi ilanları | ❌ | ❌ |
| `recruitment:application:convert` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `recruitment:interview:create` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `recruitment:evaluation:create` | ✅ | ✅ | ✅ | ✅ (atandıysa) | ❌ |
| `recruitment:evaluation:read` | ✅ | ✅ | Kendi ilanları | Kendi değerlend. | ❌ |
| `recruitment:offer:create` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `recruitment:offer:send` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `recruitment:offer:salary` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `recruitment:talent_pool:manage` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `recruitment:report:read` | ✅ | ✅ | ✅ | ❌ | ❌ |

### 10.3 Public Endpoint Güvenliği (Kariyer Sayfası)

| Güvenlik Katmanı | Uygulama |
|-----------------|----------|
| Rate limiting | IP başına 10 başvuru/saat, 100 sayfa görüntüleme/dakika |
| CAPTCHA | hCaptcha başvuru formunda zorunlu |
| CORS | Tenant whitelist'e göre izin verilen origin'ler |
| Dosya doğrulama | MIME type kontrolü, dosya boyutu limiti, antivirüs tarama |
| Input sanitization | XSS koruması, HTML strip, SQL injection koruması |
| KVKK | Başvuru alınamaz rıza onayı olmadan |

---

## 11. Modüller Arası Bağımlılıklar

### 11.1 ATS Modülünün Sunduğu Servisler

```python
class RecruitmentService:
    """Diğer modüllerin kullanabileceği işe alım servisleri."""

    async def get_open_positions_count(self, tenant_id: int) -> int
    async def get_active_applications_count(self, tenant_id: int) -> int
    async def get_job_by_id(self, job_id: int) -> Job
    async def get_recruitment_metrics(self, tenant_id: int, period: DateRange) -> RecruitmentMetrics
```

### 11.2 ATS Modülünün Kullandığı Servisler

| Modül | Servis | Kullanım |
|-------|--------|----------|
| **Personnel** | `PersonnelService.create_employee()` | Aday → çalışan dönüşümü |
| **Personnel** | `PersonnelService.get_employee_count()` | Headcount kontrolü |
| **Organization** | `OrganizationService.get_department()` | İlan departman doğrulama |
| **Organization** | `OrganizationService.get_position()` | İlan pozisyon doğrulama |
| **Auth** | `AuthService.get_user()` | Mülakatçı / recruiter bilgisi |
| **Notification** | `NotificationService.send()` | E-posta, SMS, push bildirimler |
| **Notification** | `NotificationService.send_email_template()` | Şablon bazlı e-posta |

---

## 12. Performans Gereksinimleri

| Senaryo | Hedef | Yöntem |
|---------|-------|--------|
| İlan listesi (sayfalı, 100 ilan) | < 100ms | Composite index, pagination |
| Kanban pipeline view (200 başvuru) | < 200ms | Stage index, eager loading |
| Aday arama (10.000 aday, fuzzy) | < 300ms | pg_trgm + full-text search |
| Kariyer sayfası (public, CDN) | < 500ms | Cache (Redis 5dk TTL) + CDN |
| Başvuru formu submit | < 2s | Async dosya yükleme + Celery |
| Dashboard metrikleri | < 200ms | Pre-calculated + Redis cache |
| Teklif PDF oluşturma | < 5s | WeasyPrint, Celery |

---

## 13. Test Senaryoları

### 13.1 Birim Test

| # | Test | Beklenen Sonuç |
|---|------|---------------|
| 1 | İlan slug üretimi (Türkçe başlık) | Geçerli URL-friendly slug |
| 2 | Ağırlıklı skor hesaplama | Doğru weighted_score |
| 3 | İhbar süresi kontrol (son başvuru geçmiş) | İlan kapatılır |
| 4 | Teklif süresi dolum kontrolü | Teklif expired olur |
| 5 | KVKK rıza süresi kontrolü | Süresi dolan aday verileri temizlenir |
| 6 | Aynı ilana ikinci başvuru kontrolü | Conflict hatası |
| 7 | Aşama geçiş validasyonu | History kaydı oluşur |

### 13.2 Entegrasyon Test

| # | Test | Beklenen Sonuç |
|---|------|---------------|
| 1 | Başvuru oluştur → aday kaydı oluşur mu | `ats_candidates` + `ats_applications` kaydı var |
| 2 | Aday `hired` → personel kaydı oluşur mu | `personnel_employees` kaydı, onboarding başladı |
| 3 | Mülakat planla → bildirimler gönderildi mi | E-posta + SMS gönderim logu var |
| 4 | Teklif gönder → PDF oluşturuldu mu | MinIO'da dosya var |
| 5 | İlan kapat → kariyer sayfasında görünmez mi | Public endpoint boş döner |
| 6 | KVKK süresi dol → aday verisi temizlendi mi | Aday verileri anonimleştirilmiş |
| 7 | Tenant A ilanı → Tenant B'den erişilemez | 403 veya boş liste döner |

### 13.3 E2E Test

| # | Test | Adımlar |
|---|------|---------|
| 1 | Tam işe alım akışı | İlan oluştur → Yayınla → Başvuru al → Ön eleme → Mülakat planla → Değerlendir → Teklif gönder → Kabul → Çalışana dönüştür |
| 2 | Kariyer sayfası başvuru | Public sayfayı aç → İlan listesi → Detay → Formu doldur → CV yükle → KVKK onayla → Gönder → Onay e-postası |
| 3 | Mülakat değerlendirme (yönetici) | Login (yönetici) → Mülakatlar → Aday profili → Skor kartı doldur → Gönder |
| 4 | Aday havuzu kullanımı | Aday reddet → Havuza eklendi → Yeni ilan oluştur → Havuzdan aday ekle → Pipeline'da başvurusu var |
| 5 | Teklif red ve yeniden teklif | Teklif gönder → Aday reddeder → Yeni teklif oluştur → Gönder → Kabul |

---

## 14. Kısıtlamalar ve Varsayımlar

### 14.1 Kısıtlamalar

| # | Kısıt | Etki | Çözüm |
|---|-------|------|-------|
| K1 | Kariyer.net / LinkedIn API partnership gerektirebilir | İlk sürümde dış platform entegrasyonu yapılamayabilir | Kariyer sayfası + link paylaşımı ile başlangıç |
| K2 | AI CV ayrıştırma karmaşık Türkçe NLP gerektirir | İlk sürümde manuel CV inceleme | Faz 4'te Türkçe NLP entegrasyonu |
| K3 | Video mülakat entegrasyonu dış servis bağımlılığı | Zoom/Meet/Teams native entegrasyon yok | Meeting link alanı ile yönlendirme |
| K4 | E-imza yasal gereksinimler | Teklif e-imzası ilk sürümde yok | PDF indirip ıslak imza, Faz 4'te e-imza |

### 14.2 Varsayımlar

| # | Varsayım | Risk |
|---|---------|------|
| V1 | Her ilan için en az bir sorumlu (recruiter) atanacaktır | Düşük |
| V2 | Adaylar benzersiz e-posta adresi kullanacaktır | Düşük |
| V3 | İlk sürümde dış platform entegrasyonu yapılmayacaktır | Düşük |
| V4 | Mülakat takvimi Google Calendar / Outlook ile senkronize edilecektir (Faz 3+) | Orta |
| V5 | Ortalama ilan başına 30-50 başvuru beklenecektir | Düşük |

---

## 15. Gelecek İyileştirmeler (Roadmap)

| Faz | İyileştirme | Açıklama |
|-----|-------------|----------|
| Faz 3+ | Kariyer.net / LinkedIn API entegrasyonu | İlan otomatik yayın + başvuru çekme |
| Faz 3+ | Google Calendar / Outlook entegrasyonu | Mülakat takvim senkronizasyonu |
| Faz 4 | AI CV ayrıştırma (Türkçe NLP) | CV'den otomatik yetkinlik çıkarma ve adayları sıralama |
| Faz 4 | AI aday eşleştirme | İlan gereksinimleri ile aday yetkinliklerini otomatik eşleştirme |
| Faz 4 | Video mülakat platformu | Asenkron video mülakat kayıt ve değerlendirme |
| Faz 4 | Dijital imza entegrasyonu | Teklif mektuplarının dijital olarak imzalanması |
| Faz 4 | Referans kontrol sistemi | Otomatik referans sorma ve takip |
| Faz 4 | Employer branding araçları | Gelişmiş kariyer sayfası, şirket kültürü içeriği |
| Faz 4 | Predictive analytics | Time-to-hire tahmini, aday başarı skoru |

---

## 16. Sonuç

İşe Alım & Aday Takip (ATS) modülü, şirketlerin açık pozisyon süreçlerini uçtan uca dijitalleştirmesini sağlar. Bu doküman aşağıdaki temel kararları detaylandırmıştır:

- **Kanban pipeline:** Görsel, sürükle-bırak aday takibi ile aşamalar arası geçiş
- **Skor kartı sistemi:** Ağırlıklı değerlendirme kriterleri, çoklu değerlendirici desteği
- **Mülakat planlama:** Takvim entegrasyonu, otomatik davet ve hatırlatmalar
- **Teklif yönetimi:** Şablon bazlı PDF teklif mektubu, onay akışı, süre takibi
- **Aday havuzu:** KVKK uyumlu aday saklama, etiketleme, yeniden kullanım
- **Kariyer sayfası:** Gömülebilir, SEO uyumlu, responsive, CAPTCHA korumalı
- **KVKK tam uyum:** Açık rıza, saklama süresi, otomatik temizlik, veri taşınabilirliği
- **Aday → çalışan dönüşümü:** Tek tık ile personel modülüne veri aktarımı
- **İşe alım metrikleri:** Time-to-hire, kaynak analizi, dönüşüm hunisi, teklif kabul oranı
- **Otomasyon:** 15+ otomatik tetik, 6 zamanlanmış görev, 6 e-posta şablonu

---

> **Sonraki Adım:** [12-modul-izin-devamsizlik.md](12-modul-izin-devamsizlik.md) — İzin türleri, talep/onay akışları, kota yönetimi, devamsızlık takibi
