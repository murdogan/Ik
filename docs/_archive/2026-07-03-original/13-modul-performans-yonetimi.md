# 13 — Modül: Performans Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Hedef belirleme (OKR/KPI), değerlendirme dönemleri, öz değerlendirme, yönetici değerlendirmesi, 360 derece geri bildirim, yetkinlik matrisi, kalibrasyon, performans gelişim planı (PIP), performans raporları  
> **Faz:** Faz 2 — MVP sonrası ilk genişleme paketinde yer alır; Personel Yönetimi, Organizasyon Şeması, Self-Servis Portal ve Bildirim altyapısına bağımlıdır  
> **Referans:** 04-gereksinim-analizi.md, 07-veritabani-tasarimi.md (genel tablolar ve audit yaklaşımı), 08-api-tasarimi.md (yetki modeli ve REST standartları), 10-modul-personel-yonetimi.md, 17-modul-organizasyon-semasi.md, 19-modul-self-servis-portal.md

---

## 1. Modül Özeti

Performans Yönetimi modülü; çalışan hedeflerinin tanımlanması, dönemsel performans değerlendirmelerinin yürütülmesi, çok kaynaklı geri bildirim toplanması ve gelişim aksiyonlarının takip edilmesini sağlar. Amaç yalnızca puan üretmek değil; şirket hedefleri ile bireysel hedefleri hizalamak, yönetsel kararları veri ile desteklemek ve çalışan gelişimini sistematik hale getirmektir.

Modül, Türkiye'deki orta ve büyük ölçekli işletmelerde sık görülen hibrit performans modelini destekler: yıllık veya çeyreklik hedef takibi, dönem sonu değerlendirme, gerektiğinde 360 geri bildirim ve sonuçlara bağlı gelişim planı. İlk sürümde ücret/prim kararı otomatik verilmez; bu veri karar destek amacıyla sunulur.

### 1.1 Modül Kapsamı

| Kapsam İçi | Kapsam Dışı |
|------------|-------------|
| Şirket, departman ve çalışan seviyesinde hedef setleri | Maaş artışı ve prim hesaplama otomasyonu (14-modul-bordro-maas.md) |
| OKR ve KPI tabanlı hedef tanımlama | İşe alım aday performans skoru (11-modul-ise-alim-ats.md) |
| Dönem oluşturma ve değerlendirme takvimi | LMS içerik sunumu ve eğitim içeriği barındırma (15-modul-egitim-gelisim.md) |
| Öz değerlendirme ve yönetici değerlendirmesi | Gerçek zamanlı üretkenlik izleme / çalışan gözetimi |
| 360 derece geri bildirim kampanyaları | Bordroya otomatik zam/bonus yansıtma |
| Yetkinlik matrisi ve rol bazlı yetkinlik profilleri | Psikometrik test motoru |
| Kalibrasyon toplantısı için performans dağılım görünümü | Hukuki disiplin sürecini otomatik başlatma |
| Performans gelişim planı (PIP) takibi | Serbest metin AI koçluğu |
| Performans dashboard ve raporları | — |

### 1.2 Faz Planındaki Rolü

```
Faz 1 (MVP):      Personel + İzin + Self-Servis
Faz 2 Genişleme:  Performans + Eğitim + Organizasyon + Raporlama

Performans Yönetimi:
  - Personel verisini kullanır
  - Organizasyon yapısına göre hedef dağıtır
  - Self-Servis üzerinden çalışan katılımını sağlar
  - Bildirim sistemi ile değerlendirme akışını çalıştırır
```

### 1.3 İlişkili Modüller

```
                    ┌──────────────┐
                    │   Personel   │ çalışan kartı, unvan,
                    │   Modülü     │ işe giriş, yönetici
                    └──────┬───────┘
                           │
                           │
┌──────────────┐    ┌──────┴────────┐    ┌──────────────┐
│ Notification │◀───│  Performans   │───▶│ Self-Servis  │
│   Modülü     │    │   Yönetimi    │    │    Portal    │
└──────────────┘    └──────┬────────┘    └──────────────┘
 değerlendirme açılışı,     │               öz değerlendirme,
 hatırlatma, sonuç bildirimi│               hedef takibi
                            │
                  ┌─────────┼─────────┐
                  │         │         │
            ┌─────┴───┐ ┌───┴─────┐ ┌─┴──────────┐
            │Organ.   │ │ Eğitim  │ │ Raporlama  │
            │Modülü   │ │ Modülü  │ │  Modülü    │
            └─────────┘ └─────────┘ └────────────┘
             hiyerarşi,     gelişim      dashboard,
             kademe, rol    aksiyonları  kıyaslama
```

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Modüldeki Rolü | Kullanım Sıklığı | Kritik İşlemler |
|---------|----------------|------------------|-----------------|
| **Zeynep (Çalışan)** | Hedef sahibi ve öz değerlendirici | Haftalık kısa, dönem sonunda yoğun | Hedef ilerlemesi güncelleme, öz değerlendirme, geri bildirim isteme |
| **Mehmet (Departman Yöneticisi)** | Hedef atayan ve birincil değerlendirici | Haftalık | Hedef onayı, değerlendirme yazma, 1:1 notları, PIP başlatma |
| **Ayşe (İK Müdürü)** | Süreç sahibi ve kalibrasyon yöneticisi | Günlük / dönemsel yoğun | Dönem açma, şablon tanımlama, kampanya izleme, kalibrasyon |
| **Hakan (Genel Müdür)** | Sonuç tüketici / üst düzey onay | Aylık / çeyreklik | Organizasyon performans görünümü, düşük performans kümeleri |

### 2.2 Çalışan — Hedef ve Öz Değerlendirme Yolculuğu

```
PLANLAMA              DÖNEM İÇİ              DEĞERLENDİRME            SONUÇ
   │                      │                        │                      │
   ▼                      ▼                        ▼                      ▼
Şirket hedefleri     Hedef ilerlemesini       Öz değerlendirme        Sonuç kartını
açıldı               günceller                doldurur                görür
   │                      │                        │                      │
   ├─ Kendi hedeflerini   ├─ Kanıt / not ekler    ├─ Puan verir         ├─ Güçlü yönler
   │  oluşturur           ├─ Risk işaretler       ├─ Yorum yazar        ├─ Gelişim alanları
   ▼                      ▼                        ▼                      └─ Gelişim planı
Yönetici onayına      Dönem ortası check-in     Yönetici değerlendirmesi
gönderir              için hazırlık yapar       sonrası sonuç kesinleşir
```

**Hedef Süreler:**

| Adım | Hedef | Manuel / Geleneksel |
|------|-------|----------------------|
| Hedef oluşturma | < 15 dakika / çalışan | 1-2 toplantı + Excel |
| Öz değerlendirme tamamlama | < 20 dakika | 1-2 saat, dağınık form |
| Yönetici değerlendirme | < 30 dakika / çalışan | 2-3 saat, manuel derleme |
| Kalibrasyon hazırlığı | < 1 iş günü | 3-5 iş günü |

### 2.3 Yönetici — Değerlendirme ve Kalibrasyon Yolculuğu

```
BİLDİRİM                 İNCELEME                KARAR
   │                        │                      │
   ▼                        ▼                      ▼
"Dönem kapanıyor"      Çalışanın hedefleri     Puan / yorum /
hatırlatması gelir      ve öz değerlendirmesi   gelişim önerisi girilir
   │                     incelenir                 │
   ▼                        │                      ├── Gerekirse PIP
Takım listesi açılır      ├─ Geçmiş dönemle kıyas  │   başlatılır
   │                       ├─ Yetkinlik puanı      └── Kalibrasyona gönder
   ▼                       └─ 360 geri bildirim
Taslak değerlendirme       katkıları
oluşturulur
```

### 2.4 İK — Dönem Yönetimi Yolculuğu

```
TASARIM                 YÜRÜTME                 KAPANIŞ
   │                      │                        │
   ▼                      ▼                        ▼
Değerlendirme dönemi   Katılım oranı izlenir   Kalibrasyon toplantısı
oluşturulur            gecikenlere hatırlatma  yapılır
   │                      │                        │
   ├─ Şablon seçilir      ├─ Kilit ekipler takip   ├─ Son skorlar yayınlanır
   ├─ Yetkinlik seti      ├─ Eskalasyon            ├─ Rapor paylaşılır
   └─ Takvim belirlenir   └─ Kampanya sağlığı      └─ Gelişim planları açılır
```

---

## 3. Fonksiyonel Gereksinimler — Detay

### 3.1 Hedef Kataloğu ve Hedef Atama

#### FR-PERF-01: Hedef Çerçevesi Tanımlama

**Açıklama:** İK veya yetkili yönetici; şirket, departman ve bireysel seviyede hedef çerçeveleri oluşturabilmeli, hedef tiplerini ve ağırlıklarını tanımlayabilmelidir.

**Hedef Tipleri:**

| Kod | Hedef Tipi | Açıklama | Ölçüm Şekli |
|-----|------------|----------|-------------|
| `okr_objective` | OKR Objective | Nitel hedef başlığı | Bağlı key result'larla ölçülür |
| `okr_key_result` | OKR Key Result | Sonuç odaklı alt hedef | Sayısal / yüzde |
| `kpi` | KPI | Sürekli izlenen metrik | Sayı, oran, para |
| `behavioral` | Davranışsal hedef | Yetkinlik / davranış odaklı | Skor veya rubric |
| `project` | Proje hedefi | Belirli proje teslimatı | Tamamlanma / milestone |

**Hedef Konfigürasyonu:**

| Özellik | Açıklama |
|---------|----------|
| Hedef seviyesi | Şirket, departman, ekip, bireysel |
| Ağırlık | Toplam skora etkisi (%) |
| Ölçüm tipi | Sayı, yüzde, evet/hayır, rubric |
| Başlangıç değeri | Opsiyonel baseline |
| Hedef değer | Beklenen sonuç |
| Stretch hedef | İsteğe bağlı iddialı hedef |
| Görünürlük | Sadece çalışan-yönetici, ekip, tüm şirket |
| Zorunluluk | Dönem kapanışı için zorunlu mu |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-01 | Bir performans döneminde bir çalışana atanan aktif hedeflerin toplam ağırlığı `%100` olmalıdır |
| IK-PRF-02 | Şirket veya departman hedefleri bireysel hedefe bağlanabilir; zincir en fazla 3 seviye olabilir |
| IK-PRF-03 | `okr_objective` tipi hedef doğrudan puanlanmaz; puan bağlı key result'lardan türetilir |
| IK-PRF-04 | Kapanmış dönemin hedefleri düzenlenemez; yalnızca yorum eklenebilir |
| IK-PRF-05 | Aynı çalışan için aynı dönemde aynı isimle iki aktif bireysel hedef oluşturulamaz |

---

#### FR-PERF-02: Performans Dönemi ve Takvimi Yönetimi

**Açıklama:** İK, şirket bazında performans dönemleri oluşturabilmeli; planlama, öz değerlendirme, yönetici değerlendirmesi, kalibrasyon ve yayın aşamalarını tarih bazlı yönetebilmelidir.

**Desteklenen Dönem Modelleri:**

| Model | Açıklama | Kullanım |
|-------|----------|----------|
| **Yıllık** | Yılda 1 kez tam değerlendirme | Kurumsal şirketler |
| **6 aylık** | Yılda 2 kez performans çevrimi | Orta ölçekli şirketler |
| **Çeyreklik** | Hızlı OKR döngüsü | Teknoloji / ürün ekipleri |
| **Özel dönem** | Proje veya adaptasyon bazlı dönem | Deneme süresi, reorganizasyon |

**Dönem Aşamaları:**

```
Taslak → Hedef Planlama → Dönem İçi Check-in → Öz Değerlendirme
     → Yönetici Değerlendirmesi → Kalibrasyon → Sonuç Yayını → Arşiv
```

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-06 | Tenant içinde aynı tarihlerde aynı çalışan kitlesini kapsayan iki aktif performans dönemi açılamaz |
| IK-PRF-07 | Dönem aşamaları geri alınabilir, ancak yayımlanmış sonuçlar yeni revizyon olmadan değiştirilemez |
| IK-PRF-08 | Öz değerlendirme aşaması kapanmadan yönetici değerlendirmesi açılmaz; İK isterse force-open yapabilir |
| IK-PRF-09 | Her aşama başlangıcında ilgili kullanıcılara bildirim gönderilir |
| IK-PRF-10 | Deneme süresi değerlendirmesi ayrı şablonla yönetilir; ana yıllık skora otomatik eklenmez |

---

#### FR-PERF-03: Öz Değerlendirme ve Kanıt Girişi

**Açıklama:** Çalışanlar kendi hedef ilerlemelerini, dönemdeki çıktıları, öğrenimleri ve zorlukları belgeleyerek öz değerlendirme formunu doldurabilmelidir.

**Öz Değerlendirme Formu Bölümleri:**

| Bölüm | Açıklama |
|-------|----------|
| Hedef bazlı ilerleme | Her hedef için gerçekleşen değer ve kısa açıklama |
| Başarı örnekleri | Somut çıktı / proje / teslim listesi |
| Karşılaşılan engeller | Bağımlılık, kapasite, süreç sorunu |
| Destek ihtiyacı | Yönetici veya şirketten beklenen destek |
| Gelişim alanı | Çalışanın kendisinin belirttiği gelişim ihtiyacı |
| Genel öz skor | Dönem genel öz puanı |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-11 | Öz değerlendirme yalnızca aktif ve atandığı dönem içinde yapılabilir |
| IK-PRF-12 | Zorunlu hedefler için ilerleme veya yorum girilmeden form tamamlanamaz |
| IK-PRF-13 | Çalışan gönderdiği öz değerlendirmeyi aşama kapanana kadar düzenleyebilir |
| IK-PRF-14 | Dosya ve bağlantı kanıtı eklenebilir; dosyalar MinIO üzerinde signed URL ile saklanır |
| IK-PRF-15 | Öz skor nihai skor yerine geçmez; yalnızca karşılaştırmalı görünümde kullanılır |

---

#### FR-PERF-04: Yönetici Değerlendirmesi

**Açıklama:** Doğrudan yönetici, çalışan hedeflerini ve yetkinliklerini değerlendirerek nihai yönetici skorunu ve metinsel yorumları girebilmelidir.

**Değerlendirme Bileşenleri:**

| Bileşen | Açıklama | Varsayılan Ağırlık |
|---------|----------|--------------------|
| Hedef skoru | OKR/KPI gerçekleşme düzeyi | %60 |
| Yetkinlik skoru | Rol bazlı yetkinlik seviyesi | %25 |
| Davranış / değer uyumu | Şirket değerlerine uyum | %15 |

**Puanlama Ölçekleri:**

| Ölçek | Açıklama |
|-------|----------|
| `1-5` | En yaygın likert tipi |
| `1-10` | Daha ayrıntılı puanlama |
| `A-E` | Harf bazlı sınıflama |
| `custom` | Tenant tanımlı etiketli ölçek |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-16 | Yönetici yalnızca doğrudan veya dolaylı olarak yetkili olduğu çalışanları değerlendirebilir |
| IK-PRF-17 | Her değerlendirme için metinsel özet alanı zorunludur |
| IK-PRF-18 | Yöneticinin verdiği skor, kalibrasyon öncesi `manager_proposed_score` olarak saklanır |
| IK-PRF-19 | Çalışanın dönemde yönetici değişimi varsa İK ana değerlendiriciyi belirler; önceki yönetici katkı yorumu bırakabilir |
| IK-PRF-20 | Düşük performans eşik altında ise sistem PIP önerisi gösterir |

---

#### FR-PERF-05: 360 Derece Geri Bildirim Kampanyası

**Açıklama:** Belirli dönemlerde veya belirli gruplar için çoklu değerlendirici (peer, matrix manager, bağlı çalışan, iç müşteri) geri bildirim kampanyası başlatılabilmelidir.

**Değerlendirici Kaynakları:**

| Kaynak | Açıklama |
|--------|----------|
| Yönetici | Doğrudan amir |
| Peer | Aynı ekipten veya projeden iş arkadaşı |
| Matrix manager | Noktalı çizgi yönetici |
| Report | Yönetici için bağlı çalışan değerlendirmesi |
| Stakeholder | İç müşteri / proje paydaşı |

**Kampanya Parametreleri:**

| Parametre | Açıklama |
|-----------|----------|
| Anonimlik | Anonim / isimli / hibrit |
| Min. değerlendirici sayısı | Sonuç görünmesi için asgari sayı |
| Yetkinlik seti | Hangi sorular ve rubric |
| Son teslim tarihi | Kampanya kapanış tarihi |
| Hatırlatma sıklığı | 3 günde bir, haftalık vb. |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-21 | Anonim kampanyada min. 3 yanıt olmadan bireysel geri bildirim detayı görüntülenmez |
| IK-PRF-22 | Bir kullanıcı aynı kampanyada aynı kişi için aynı rol üzerinden yalnızca bir kez yanıt verebilir |
| IK-PRF-23 | 360 geri bildirim varsayılan olarak nihai skora otomatik yansımaz; tenant ayarı ile ağırlık verilebilir |
| IK-PRF-24 | Anonim kampanyada serbest metin yorumlar PII filtresinden geçirilecek uyarı akışına tabi tutulur |
| IK-PRF-25 | Kampanya kapanınca yanıtlar kilitlenir; İK dışında düzenlenemez |

---

#### FR-PERF-06: Yetkinlik Matrisi ve Rol Profili

**Açıklama:** Her pozisyon veya rol ailesi için beklenen yetkinlikler ve hedeflenen seviye tanımlanabilmeli; çalışan değerlendirmesi bu matrise göre yapılabilmelidir.

**Yetkinlik Boyutları:**

| Boyut | Örnekler |
|-------|----------|
| Teknik | Domain bilgisi, araç kullanımı, kalite |
| Davranışsal | İletişim, takım çalışması, sorumluluk |
| Liderlik | Delegasyon, karar alma, koçluk |
| Fonksiyonel | Bordro bilgisi, işe alım uzmanlığı, raporlama |

**Seviye Modeli:**

| Seviye | Açıklama |
|--------|----------|
| 1 | Başlangıç |
| 2 | Temel uygulama |
| 3 | Beklenen seviye / bağımsız |
| 4 | Güçlü / mentorluk verebilir |
| 5 | Uzman / stratejik katkı |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-26 | Her unvan ailesi için bir varsayılan yetkinlik şablonu bulunabilir |
| IK-PRF-27 | Yetkinlik beklentisi organizasyon seviyesine göre override edilebilir |
| IK-PRF-28 | Dönem açıldıktan sonra kullanılan yetkinlik şablonu snapshot olarak saklanır |
| IK-PRF-29 | Nihai skor hesaplanırken eksik yetkinlik puanları varsa sistem uyarı verir |
| IK-PRF-30 | Gelişim planı önerileri yetkinlik açığına bağlanabilir |

---

#### FR-PERF-07: Kalibrasyon ve Nihai Sonuç Yayını

**Açıklama:** İK ve üst yöneticiler, yönetici öneri skorlarını ekipler arası tutarlılık için kalibre edebilmeli; gerekçeli değişikliklerle nihai skor ve performans kategorisini yayınlayabilmelidir.

**Kalibrasyon Görünümleri:**

| Görünüm | Açıklama |
|---------|----------|
| 9-box grid | Performans x potansiyel matrisi |
| Dağılım grafiği | Takım / departman skor dağılımı |
| Kıyas tablosu | Aynı unvan veya kademe için sıralama |
| Outlier listesi | Çok yüksek / çok düşük skor adayları |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-31 | Kalibrasyon değişikliği gerekçe girmeden kaydedilemez |
| IK-PRF-32 | Nihai skor yayınlandıktan sonra çalışan sonucu görüntüleyebilir |
| IK-PRF-33 | Forced distribution zorunlu değildir; tenant ayarı ile açılabilir |
| IK-PRF-34 | Kalibrasyon geçmişi audit log'da önceki ve yeni değerle tutulur |
| IK-PRF-35 | Sonuç açıklama tarihi gelmeden sonuçlar çalışanla paylaşılmaz |

---

#### FR-PERF-08: Performans Gelişim Planı (PIP)

**Açıklama:** Düşük performans veya kritik gelişim ihtiyacı görülen çalışanlar için belirli süreli, ölçülebilir gelişim planı oluşturulabilmeli ve takip edilebilmelidir.

**PIP Alanları:**

| Alan | Açıklama |
|------|----------|
| Başlangıç / bitiş tarihi | Plan süresi |
| Gelişim hedefleri | Somut ve ölçülebilir aksiyonlar |
| Başarı kriterleri | Planın başarılı sayılma koşulları |
| Gözden geçirme noktaları | Haftalık / iki haftalık check-in |
| Sorumlu taraf | Yönetici, çalışan, İK |
| Sonuç | Başarılı, uzatıldı, başarısız |

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-36 | PIP yalnızca yetkili yönetici veya İK tarafından başlatılabilir |
| IK-PRF-37 | Aktif bir PIP varken aynı çalışan için ikinci aktif PIP açılamaz |
| IK-PRF-38 | PIP gözden geçirme notları çalışan tarafından görülebilirlik ayarına sahiptir |
| IK-PRF-39 | PIP sonucu iş akdine ilişkin otomatik karar üretmez; yalnızca kayıt ve takip amacı taşır |
| IK-PRF-40 | Başarısız sonuç İK dashboard'unda kırmızı risk olarak işaretlenir |

---

#### FR-PERF-09: 1:1 Notları ve Check-in Takibi

**Açıklama:** Yönetici ve çalışan arasındaki dönem içi check-in görüşmeleri, kısa aksiyon notları ve ilerleme kayıtlarıyla takip edilebilmelidir.

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-41 | 1:1 notları varsayılan olarak çalışan ve yöneticisi arasında paylaşılır |
| IK-PRF-42 | Yönetici belirli notu "özel" işaretlerse yalnızca kendisi ve İK görebilir |
| IK-PRF-43 | Check-in tarihi geçmiş ancak tamamlanmamış kayıtlar dashboard'da gecikmiş görünür |
| IK-PRF-44 | Dönem başına önerilen minimum check-in sayısı tenant ayarıdır |

---

#### FR-PERF-10: Raporlama ve Organizasyon Görünürlüğü

**Açıklama:** İK ve üst yönetim; ekip, departman, kademe ve dönem bazında performans sonuçlarını raporlayabilmelidir.

**İş Kuralları:**

| Kural | Açıklama |
|-------|----------|
| IK-PRF-45 | Yönetici yalnızca yetkili olduğu hiyerarşi için toplu rapor görebilir |
| IK-PRF-46 | 360 anonim veriler bireysel kimliği açığa çıkaracak detay seviyesinde export edilemez |
| IK-PRF-47 | Sonuçlar dönem snapshot'ı olarak saklanır; geçmiş dönem raporları değişmez |
| IK-PRF-48 | Performans sonuçları, ücret ve terfi kararları için referans veri olarak işaretlenebilir ancak doğrudan karar motoru değildir |

---

## 4. Veritabanı Tasarımı

### 4.1 Tablo İlişkisi

```
performance_cycles ────────────── performance_goal_templates
        │                                 │
        ├───────────── performance_goals ─┘
        │                    │
        │                    ├── performance_goal_updates
        │                    └── performance_goal_links
        │
        ├── performance_reviews ───── performance_review_scores
        │               │
        │               ├── performance_feedback_requests
        │               ├── performance_feedback_responses
        │               └── performance_checkins
        │
        └── performance_pips

competency_frameworks ───── competency_items ───── performance_review_scores
```

### 4.2 Ana Tablolar

#### `performance_cycles` — Değerlendirme Dönemleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `name` | VARCHAR(120) | `2026 Yıllık Performans`, `2026 Q2 OKR` |
| `cycle_type` | VARCHAR(20) | `annual`, `semiannual`, `quarterly`, `custom` |
| `status` | VARCHAR(20) | `draft`, `planning`, `self_review`, `manager_review`, `calibration`, `published`, `archived` |
| `start_date` | DATE | |
| `end_date` | DATE | |
| `self_review_deadline` | DATE, nullable | |
| `manager_review_deadline` | DATE, nullable | |
| `publish_at` | TIMESTAMPTZ, nullable | |
| `created_by` | BIGINT, FK | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `performance_goals` — Çalışan Hedefleri

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `cycle_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `parent_goal_id` | BIGINT, nullable | Objective → Key result ilişkisi |
| `linked_goal_id` | BIGINT, nullable | Şirket/departman hedefine bağ |
| `goal_type` | VARCHAR(30) | |
| `title` | VARCHAR(200) | |
| `description` | TEXT, nullable | |
| `weight` | NUMERIC(5,2) | |
| `measurement_type` | VARCHAR(20) | `number`, `percentage`, `currency`, `rubric`, `boolean` |
| `start_value` | NUMERIC(12,2), nullable | |
| `target_value` | NUMERIC(12,2), nullable | |
| `current_value` | NUMERIC(12,2), nullable | |
| `visibility` | VARCHAR(20) | `private`, `team`, `company` |
| `status` | VARCHAR(20) | `draft`, `active`, `completed`, `cancelled` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `performance_reviews` — Değerlendirme Kaydı

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `cycle_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | Değerlendirilen kişi |
| `manager_id` | BIGINT, FK | Birincil değerlendirici |
| `self_score` | NUMERIC(5,2), nullable | |
| `manager_proposed_score` | NUMERIC(5,2), nullable | |
| `calibrated_score` | NUMERIC(5,2), nullable | |
| `final_score` | NUMERIC(5,2), nullable | |
| `performance_label` | VARCHAR(30), nullable | `high`, `solid`, `developing`, `critical` |
| `self_summary` | TEXT, nullable | |
| `manager_summary` | TEXT, nullable | |
| `calibration_note` | TEXT, nullable | |
| `published_at` | TIMESTAMPTZ, nullable | |
| `status` | VARCHAR(20) | `not_started`, `self_submitted`, `manager_submitted`, `calibrated`, `published` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `performance_review_scores` — Hedef / Yetkinlik Bazlı Puanlar

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `review_id` | BIGINT, FK | |
| `score_type` | VARCHAR(20) | `goal`, `competency`, `value_alignment`, `feedback` |
| `reference_id` | BIGINT, nullable | Hedef veya yetkinlik öğesi |
| `reviewer_type` | VARCHAR(20) | `self`, `manager`, `peer`, `hr` |
| `score` | NUMERIC(5,2) | |
| `comment` | TEXT, nullable | |
| `created_at` | TIMESTAMPTZ | |

#### `performance_feedback_requests` — 360 Talep Kayıtları

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `cycle_id` | BIGINT, FK | |
| `review_id` | BIGINT, FK | |
| `subject_employee_id` | BIGINT, FK | Geri bildirimi alınan |
| `reviewer_employee_id` | BIGINT, FK | Geri bildirim veren |
| `reviewer_role` | VARCHAR(20) | `peer`, `manager`, `report`, `stakeholder` |
| `is_anonymous` | BOOLEAN | |
| `status` | VARCHAR(20) | `pending`, `submitted`, `expired`, `declined` |
| `requested_at` | TIMESTAMPTZ | |
| `submitted_at` | TIMESTAMPTZ, nullable | |

#### `performance_pips` — Gelişim Planı

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | BIGINT, PK | |
| `tenant_id` | BIGINT, FK | |
| `employee_id` | BIGINT, FK | |
| `cycle_id` | BIGINT, FK, nullable | İlgili dönem |
| `owner_manager_id` | BIGINT, FK | |
| `status` | VARCHAR(20) | `draft`, `active`, `successful`, `extended`, `unsuccessful`, `cancelled` |
| `start_date` | DATE | |
| `end_date` | DATE | |
| `goal_summary` | TEXT | |
| `success_criteria` | TEXT | |
| `final_note` | TEXT, nullable | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### 4.3 İndeksler

```sql
CREATE INDEX ix_perf_cycles_tenant_status ON performance_cycles (tenant_id, status);
CREATE INDEX ix_perf_goals_employee_cycle ON performance_goals (tenant_id, employee_id, cycle_id);
CREATE INDEX ix_perf_reviews_employee_cycle ON performance_reviews (tenant_id, employee_id, cycle_id);
CREATE INDEX ix_perf_feedback_pending ON performance_feedback_requests (tenant_id, status, requested_at)
    WHERE status IN ('pending', 'expired');
CREATE INDEX ix_perf_pips_employee_status ON performance_pips (tenant_id, employee_id, status);
```

---

## 5. API Endpoint Detayları

Tüm performans endpoint'leri `/api/v1/performance` prefix'i altındadır.

### 5.1 Dönem ve Şablon Yönetimi

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/performance/cycles` | Performans dönemleri listesi | `performance:cycle:read` |
| `POST` | `/performance/cycles` | Yeni dönem oluştur | `performance:cycle:create` |
| `PATCH` | `/performance/cycles/{id}` | Dönem güncelle | `performance:cycle:update` |
| `PATCH` | `/performance/cycles/{id}/transition` | Aşama geçişi yap | `performance:cycle:update` |
| `GET` | `/performance/templates/goals` | Hedef şablonları | `performance:template:read` |
| `POST` | `/performance/templates/goals` | Hedef şablonu oluştur | `performance:template:create` |

### 5.2 Hedef Yönetimi

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/performance/goals` | Hedef listesi | `performance:goal:read` |
| `POST` | `/performance/goals` | Hedef oluştur | `performance:goal:create` |
| `PATCH` | `/performance/goals/{id}` | Hedef güncelle | `performance:goal:update` |
| `POST` | `/performance/goals/{id}/progress` | İlerleme güncellemesi ekle | `performance:goal:update` |
| `POST` | `/performance/goals/{id}/submit` | Yönetici onayına gönder | `performance:goal:update` |

### 5.3 Değerlendirme Süreci

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/performance/reviews` | Değerlendirme kayıtları | `performance:review:read` |
| `GET` | `/performance/reviews/{id}` | Detay görüntüle | `performance:review:read` |
| `PATCH` | `/performance/reviews/{id}/self-review` | Öz değerlendirme gönder | Auth |
| `PATCH` | `/performance/reviews/{id}/manager-review` | Yönetici değerlendirmesi gönder | `performance:review:write` |
| `PATCH` | `/performance/reviews/{id}/calibrate` | Kalibrasyon kaydet | `performance:review:calibrate` |
| `PATCH` | `/performance/reviews/{id}/publish` | Sonucu yayınla | `performance:review:publish` |

### 5.4 360 Feedback

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `POST` | `/performance/feedback/campaigns` | 360 kampanyası başlat | `performance:feedback:create` |
| `GET` | `/performance/feedback/requests` | Bekleyen geri bildirim talepleri | Auth |
| `POST` | `/performance/feedback/requests/{id}/submit` | Geri bildirim yanıtı gönder | Auth |
| `GET` | `/performance/feedback/reviews/{review_id}` | Toplu geri bildirim özeti | `performance:feedback:read` |

### 5.5 PIP ve Check-in

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/performance/pips` | PIP listesi | `performance:pip:read` |
| `POST` | `/performance/pips` | Yeni PIP oluştur | `performance:pip:create` |
| `PATCH` | `/performance/pips/{id}` | PIP güncelle | `performance:pip:update` |
| `POST` | `/performance/pips/{id}/checkins` | PIP check-in notu ekle | `performance:pip:update` |
| `POST` | `/performance/checkins` | Dönem içi 1:1 kaydı ekle | `performance:checkin:create` |

### 5.6 Self-Servis Endpoint'leri

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/performance/goals` | Kendi hedeflerim | Auth |
| `GET` | `/me/performance/reviews/current` | Aktif dönem değerlendirmem | Auth |
| `PATCH` | `/me/performance/reviews/{id}/self-review` | Öz değerlendirme tamamla | Auth |
| `GET` | `/me/performance/feedback-requests` | Benden istenen geri bildirimler | Auth |
| `GET` | `/me/performance/development-plan` | Kendi gelişim planım / PIP | Auth |

### 5.7 Örnek Request / Response

#### POST `/api/v1/performance/goals`

**Request Body:**

```json
{
  "cycle_id": 12,
  "employee_id": 451,
  "goal_type": "kpi",
  "title": "İşe alım süresini kısalt",
  "description": "Açık pozisyonlarda ortalama işe alım süresini 42 günden 30 güne düşür",
  "weight": 25,
  "measurement_type": "number",
  "start_value": 42,
  "target_value": 30,
  "visibility": "team"
}
```

**Response (201 Created):**

```json
{
  "success": true,
  "data": {
    "id": 981,
    "cycle_id": 12,
    "employee_id": 451,
    "title": "İşe alım süresini kısalt",
    "weight": 25,
    "status": "draft",
    "linked_goal": null,
    "created_at": "2026-04-10T09:30:00Z"
  }
}
```

**Olası Hata Kodları:**

| HTTP | Kod | Açıklama |
|------|-----|----------|
| 400 | `VALIDATION_ERROR` | Eksik alan, yanlış ölçüm tipi veya ağırlık hatası |
| 409 | `GOAL_WEIGHT_EXCEEDED` | Toplam ağırlık %100'ü aşıyor |
| 409 | `CYCLE_NOT_EDITABLE` | Dönem düzenlemeye kapalı |
| 403 | `PERMISSION_DENIED` | Yetkisiz kullanıcı |
| 404 | `PERFORMANCE_CYCLE_NOT_FOUND` | Dönem bulunamadı |

---

## 6. Ekran Tasarımı Rehberi

### 6.1 Ekran Listesi

| # | Ekran | Platform | Rol | Öncelik |
|---|-------|----------|-----|---------|
| 1 | Hedeflerim Dashboard | Web + Mobil | Çalışan | Must |
| 2 | Hedef Oluştur / Düzenle | Web | Çalışan, Yönetici | Must |
| 3 | Öz Değerlendirme Formu | Web + Mobil | Çalışan | Must |
| 4 | Takım Değerlendirme Paneli | Web | Yönetici | Must |
| 5 | 360 Geri Bildirim Formu | Web + Mobil | Tüm roller | Should |
| 6 | Kalibrasyon Paneli | Web | İK, Üst Yönetici | Must |
| 7 | Yetkinlik Matrisi Yönetimi | Web | İK | Must |
| 8 | PIP ve Gelişim Takip Ekranı | Web | Yönetici, İK | Should |
| 9 | Performans Raporları | Web | İK, C-Level | Must |

### 6.2 Hedeflerim Dashboard

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ Self-Servis / Performans                                  │
├──────────────────────────────────────────────────────────────┤
│  2026 Q2 Performans Dönemi                                  │
│  Durum: Hedef Planlama açık     Son gün: 30 Nisan           │
│                                                              │
│  Genel İlerleme                                              │
│  ████████████░░░░░░  %62                                      │
│                                                              │
│  Hedeflerim                                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ KPI · İşe alım süresini 30 güne indir    %25         │  │
│  │ Mevcut: 34 gün  → Hedef: 30 gün          %75 ilerleme│  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Davranışsal · Yönetici iletişimini güçlendir %15      │  │
│  │ Son check-in: 8 gün önce                              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│ [ Hedef Ekle ] [ Öz Değerlendirmeyi Aç ]                     │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 Yönetici Değerlendirme Paneli

```
┌──────────────────────────────────────────────────────────────┐
│ ◀ Yönetici Paneli / Takım Değerlendirmeleri                 │
├──────────────────────────────────────────────────────────────┤
│ Dönem: 2026 İlk Yarı  ·  Öz değerlendirmesi tamamlayan: 8/10│
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 👤 Zeynep Kaya        İK Uzmanı                        │   │
│ │ Öz skor: 4.4 / 5      Geçen dönem: 4.1                │   │
│ │ Hedef tamamlanma: %87  360 yanıt: 5                   │   │
│ │ [ Değerlendir ] [ 1:1 Notları ] [ Geçmiş ]            │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ 👤 Can Demir         Bordro Uzmanı                     │   │
│ │ Öz skor: Bekleniyor   Son tarih: bugün                │   │
│ │ [ Hatırlatma Gönder ]                                 │   │
│ └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 6.4 Kalibrasyon Ekranı

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◀ İK Paneli / Kalibrasyon                                           │
├──────────────────────────────────────────────────────────────────────┤
│ Filtreler: [Departman ▼] [Kademe ▼] [Yönetici ▼]                    │
│                                                                      │
│ 9-Box Grid                          Skor Dağılımı                    │
│ ┌──────────────────────┐           ┌──────────────────────────────┐  │
│ │  ◉  ◉                │           │ 5.0 | ██                    │  │
│ │     ◉◉◉              │           │ 4.0 | ███████               │  │
│ │       ◉              │           │ 3.0 | ████                  │  │
│ └──────────────────────┘           └──────────────────────────────┘  │
│                                                                      │
│ Outlier'lar                                                          │
│ Zeynep Kaya   4.8 → 4.5   Gerekçe: takım normunun üzerinde           │
│ [ Kalibrasyon Notu Zorunlu ]                                         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 7. Raporlama

### 7.1 Performans Raporları

| # | Rapor | Açıklama | Filtreler | Format |
|---|-------|----------|-----------|--------|
| 1 | Performans Sonuç Dağılımı | Ekip / departman bazında skor dağılımı | Dönem, departman, kademe | Grafik + tablo |
| 2 | Hedef Gerçekleşme Raporu | Hedef bazında gerçekleşme oranı | Dönem, hedef tipi, yönetici | Tablo + Excel |
| 3 | Yetkinlik Açığı Raporu | Rol beklentisi ile çalışan seviyesi farkı | Kademe, rol ailesi | Isı haritası |
| 4 | 360 Katılım Raporu | Kampanya yanıt oranları | Kampanya, departman | Tablo |
| 5 | Düşük Performans / PIP Raporu | Riskli çalışan listesi ve plan durumları | Dönem, yönetici | Liste |
| 6 | Yönetici Tutarlılık Raporu | Yönetici bazlı skor verme eğilimleri | Yönetici, dönem | Boxplot / tablo |
| 7 | Gelişim Planı İlerleme Raporu | Yetkinlik gelişim aksiyonlarının durumu | Plan sahibi, tarih | Tablo |

### 7.2 Dashboard Kartları

| Kart | Formül |
|------|--------|
| Ortalama performans skoru | `published reviews total / published review count` |
| Yüksek performans oranı | `high performer sayısı / toplam yayınlanan sonuç` |
| Hedef gerçekleşme oranı | `tamamlanan hedef ağırlığı / toplam hedef ağırlığı` |
| 360 katılım oranı | `yanıtlanan talep / toplam gönderilen talep` |
| PIP başarı oranı | `successful PIP / kapanan PIP` |

---

## 8. İş Akışları ve Otomasyon

### 8.1 Otomatik Tetiklenen İşlemler

| Tetikleyici | İşlem | Yöntem |
|-------------|-------|--------|
| Yeni performans dönemi açıldı | Dahil çalışanlar için review kayıtları oluştur | Senkron + bulk insert |
| Aşama değişti | İlgili kullanıcılara bildirim gönder | Celery |
| Öz değerlendirme gönderildi | Yöneticiye görev bildirimi | Celery |
| Son teslim tarihi yaklaştı | Geciken kullanıcılara hatırlatma | Celery beat |
| Kalibrasyon tamamlandı | Sonuçların yayın zamanı planlanır | Celery scheduled task |
| PIP oluşturuldu | Yöneticinin check-in görevleri oluşturulur | Senkron |

### 8.2 Celery Beat Görevleri

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `send_performance_deadline_reminders` | Günlük 09:00 | Son 3 gün kalan aşamalar için hatırlatma |
| `escalate_overdue_manager_reviews` | Günlük 10:00 | Geciken yönetici değerlendirmelerini İK'ya eskale et |
| `publish_scheduled_performance_results` | Saatlik | Yayın tarihi gelen sonuçları görünür yap |
| `refresh_performance_dashboards` | Günlük 02:00 | Özet metrik cache'lerini yenile |
| `close_expired_feedback_requests` | Günlük 01:00 | Süresi dolan 360 taleplerini kapat |

### 8.3 Bildirim Şablonları

| Şablon | Tetikleyici | Alıcı | İçerik |
|--------|-------------|-------|--------|
| `performance_cycle_opened` | Dönem planlama başladı | Çalışan | "Yeni performans dönemi açıldı, hedeflerinizi tamamlayın." |
| `self_review_due` | Öz değerlendirme son 3 gün | Çalışan | "Öz değerlendirmeniz için son 3 gün." |
| `manager_review_pending` | Yönetici görevi | Yönetici | "Takımınızdan 4 değerlendirme bekliyor." |
| `feedback_request_sent` | 360 talebi açıldı | Değerlendirici | "Zeynep Kaya için geri bildirim istendi." |
| `performance_result_published` | Sonuç yayınlandı | Çalışan | "Performans dönemi sonucunuz yayınlandı." |
| `pip_checkin_due` | PIP ara görüşme tarihi | Yönetici, çalışan | "Bu hafta PIP gözden geçirme toplantınız var." |

---

## 9. Güvenlik ve KVKK

### 9.1 Hassas Veri Sınıflandırması

| Veri | Hassasiyet | Saklama | Erişim Kontrolü |
|------|-----------|---------|-----------------|
| Hedef başlıkları | Düşük-Orta | Düz metin | İlgili çalışan, yönetici, İK |
| Değerlendirme yorumları | Orta-Yüksek | Düz metin | Yetkili kişi, İK |
| 360 anonim yanıtlar | Yüksek | Düz metin + maskeleme | Toplu görünüm, kimliksiz |
| PIP kayıtları | Yüksek | Düz metin | İK + ilgili yönetici + çalışan |
| Eklenen kanıt dokümanları | Orta | MinIO | Signed URL + rol kontrolü |

### 9.2 KVKK Gereksinimleri

| Gereksinim | Uygulama |
|------------|----------|
| Amaçla sınırlılık | Performans verisi yalnızca değerlendirme, gelişim ve yönetsel raporlama amacıyla işlenir |
| Erişim sınırı | Yönetici sadece yetkili olduğu organizasyon ağacını görebilir |
| Anonim geri bildirim koruması | Min. yanıt eşiği ve toplu gösterim zorunluluğu |
| Saklama süresi | Değerlendirme kayıtları iş ilişkisi + şirket politikası süresince saklanır; silme politikası KVKK dokümanına bağlanır |
| Audit trail | Sonuç, kalibrasyon ve PIP değişiklikleri silinemez audit kayıtlarıyla tutulur |

### 9.3 Rol Bazlı Erişim Matrisi

| İzin | Süper Admin | İK Yöneticisi | Dept. Yöneticisi | Çalışan |
|------|------------|--------------|------------------|---------|
| `performance:cycle:create` | ✅ | ✅ | ❌ | ❌ |
| `performance:goal:create` | ✅ | ✅ | ✅ (ekibi/kendisi) | ✅ (kendi) |
| `performance:review:read` | ✅ | ✅ | Ekibi | Kendi |
| `performance:review:write` | ✅ | ✅ | Ekibi | ❌ |
| `performance:review:calibrate` | ✅ | ✅ | Opsiyonel | ❌ |
| `performance:feedback:create` | ✅ | ✅ | ✅ | ❌ |
| `performance:pip:create` | ✅ | ✅ | ✅ | ❌ |
| `performance:report:read` | ✅ | ✅ | Ekibi | ❌ |

---

## 10. Modüller Arası Bağımlılıklar

### 10.1 Performans Modülünün Sunduğu Servisler

```python
class PerformanceService:
    """Diğer modüllerin kullandığı performans servisleri."""

    async def get_employee_latest_score(self, employee_id: int) -> Decimal | None
    """Son yayınlanan performans skorunu döner."""

    async def get_goal_completion_summary(self, employee_id: int, cycle_id: int) -> dict
    """Self-servis ve raporlama için hedef gerçekleşme özetini üretir."""

    async def get_competency_gap_summary(self, employee_id: int) -> list[dict]
    """Eğitim ve gelişim modülü için yetkinlik açığı döner."""

    async def has_active_pip(self, employee_id: int) -> bool
    """İK risk görünümü ve yönetici ekranları için aktif PIP kontrolü."""
```

### 10.2 Performans Modülünün Kullandığı Servisler

| Modül | Servis | Kullanım |
|-------|--------|----------|
| **Personnel** | `PersonnelService.get_employee()` | Çalışan kartı, unvan, yönetici bilgisi |
| **Organization** | `OrganizationService.get_hierarchy()` | Yetki kapsamı ve kalibrasyon grupları |
| **Notification** | `NotificationService.send()` | Hatırlatma, sonuç, geri bildirim bildirimi |
| **Self-Servis** | Kimlik ve çalışan deneyimi | Öz değerlendirme ve görüntüleme |
| **Education & Development** | `LearningService.create_development_plan()` | Yetkinlik açığı sonrası eğitim önerisi |

### 10.3 Bağımlılık Diyagramı

```
┌──────────────────┐        ┌────────────────────┐        ┌──────────────────┐
│    Personel      │───────▶│   Performans       │───────▶│ Eğitim & Gelişim │
│    Modülü        │        │    Yönetimi        │        │    Modülü        │
└──────────────────┘        └─────────┬──────────┘        └──────────────────┘
                                      │
                        ┌─────────────┼─────────────┐
                        │             │             │
                  ┌─────┴────┐  ┌─────┴──────┐  ┌───┴─────────┐
                  │ Organiz. │  │ Bildirim   │  │ Self-Servis │
                  │ Modülü   │  │ Modülü     │  │   Portal    │
                  └──────────┘  └────────────┘  └─────────────┘
```

---

## 11. Performans Gereksinimleri

| Senaryo | Hedef | Yöntem |
|---------|-------|--------|
| Çalışanın kendi hedef dashboard'u | < 120ms | Redis cache + özet sorgu |
| Takım değerlendirme listesi (50 kişi) | < 250ms | Sayfalama + ön hesaplanmış review status |
| Kalibrasyon görünümü (500 çalışan) | < 2 saniye | Materialized summary + Redis |
| 360 kampanya yanıt listesi | < 150ms | İndeksli durum sorgusu |
| Rapor export (1.000 çalışan) | < 30 saniye | Async export job + signed URL |

---

## 12. Test Senaryoları

### 12.1 Birim Test

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Hedef ağırlıkları toplamı | `%100` değilse hata |
| 2 | Objective puanı | Bağlı key result ortalamasından türetilir |
| 3 | Yetkinlik gap hesabı | Beklenen seviye - mevcut seviye doğru bulunur |
| 4 | Nihai skor hesaplama | Ağırlıklı ortalama doğru hesaplanır |
| 5 | Anonim 360 görünürlüğü | 3'ten az yanıt varsa detay gizli |
| 6 | PIP tekil aktif kontrolü | İkinci aktif plan engellenir |

### 12.2 Entegrasyon Test

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Dönem aç → review kayıtları oluştu | Hedef kitlesi için review satırları yaratıldı |
| 2 | Öz değerlendirme gönder → yönetici görevi açıldı | Bildirim gönderildi, status güncellendi |
| 3 | Yönetici değerlendirme → kalibrasyon kuyruğu | `manager_submitted` durumu oluştu |
| 4 | 360 talebi gönder → yanıt geldi | Talep `submitted` oldu, review özetine işlendi |
| 5 | Sonuç yayınla → çalışan görüntüledi | `published_at` dolu ve self-servis erişimi açık |
| 6 | PIP oluştur → check-in hatırlatması | Görev ve bildirim üretildi |

### 12.3 E2E Test

| # | Test | Adımlar |
|---|------|---------|
| 1 | Tam performans çevrimi | Dönem aç → çalışan hedef gir → yönetici onayla → öz değerlendirme → yönetici değerlendirme → kalibrasyon → yayın |
| 2 | 360 kampanya | Kampanya aç → değerlendirici seç → yanıtla → anonim özet görüntüle |
| 3 | Düşük performans ve PIP | Düşük skor → PIP öner → plan aç → check-in ekle → sonucu kapat |

---

## 13. Kısıtlamalar ve Varsayımlar

### 13.1 Kısıtlamalar

| # | Kısıt | Etki | Çözüm |
|---|-------|------|-------|
| K1 | Her şirket tek performans modeli kullanmayabilir | Farklı kurallar gerektirir | Tenant bazlı ağırlık, ölçek ve dönem konfigürasyonu |
| K2 | 360 anonimlik küçük ekiplerde kimlik sızıntısı riski taşır | Gizlilik zedelenebilir | Min. yanıt eşiği ve toplu gösterim |
| K3 | Performans skorları hukuki / ücret kararlarında hassas kullanılır | Yorum kalitesi kritik | Audit log + kalibrasyon + insan onayı |
| K4 | Çok sık dönem açılması kullanım yorgunluğu yaratabilir | Katılım düşer | Hatırlatma ve sade form tasarımı |

### 13.2 Varsayımlar

| # | Varsayım | Risk |
|---|----------|------|
| V1 | Çalışan-yönetici ilişkisi Personel ve Organizasyon modüllerinde günceldir | Orta |
| V2 | Şirketler performans sonucunu doğrudan bordroya bağlamadan önce manuel karar verir | Düşük |
| V3 | Yetkinlik şablonları rol ailesi bazında tanımlanabilir | Düşük |
| V4 | Mobil kullanım öz değerlendirme ve geri bildirim için yeterli; kalibrasyon web ağırlıklı kalır | Düşük |
