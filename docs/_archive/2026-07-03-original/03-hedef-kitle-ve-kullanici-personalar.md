# 03 — Hedef Kitle ve Kullanıcı Personaları

> **Hazırlanma Tarihi:** 7 Nisan 2026  
> **Kapsam:** Kullanıcı segmentleri, persona tanımları, kullanıcı hikayeleri (user stories), kullanım senaryoları

---

## 1. Hedef Kitle Segmentasyonu

### 1.1 İşletme Ölçeğine Göre Segmentler

| Segment | Çalışan Sayısı | Pazar Potansiyeli (TR) | Öncelik | Satış Döngüsü |
|---------|---------------|----------------------|---------|---------------|
| **Mikro İşletme** | 1-9 | ~3.000.000+ firma | Düşük | Self-servis |
| **Küçük İşletme** | 10-49 | ~250.000 firma | ✅ Öncelik 1 | Self-servis / kısa demo |
| **Orta Ölçek** | 50-249 | ~40.000 firma | ✅ Öncelik 1 | Demo + deneme |
| **Büyük Orta** | 250-499 | ~5.000 firma | ✅ Öncelik 2 | Teklif bazlı |
| **Kurumsal** | 500+ | ~2.000 firma | Öncelik 3 | Teklif + POC |

### 1.2 Sektöre Göre Öncelikli Hedefler

| Sektör | Neden Öncelikli | Kritik Modüller |
|--------|----------------|-----------------|
| **Perakende & Mağazacılık** | Çok şubeli, yüksek çalışan sirkülasyonu, vardiya yoğun | Vardiya, PDKS, İzin, Bordro |
| **Üretim & Fabrika** | Vardiya zorunluluğu, SGK bildirge yoğunluğu | Vardiya, Bordro, PDKS, İSG |
| **Teknoloji & Yazılım** | Dijitalleşmeye açık, performans odaklı | Performans (OKR), İşe Alım, Eğitim |
| **Hizmet Sektörü (Otel, Restoran)** | Mevsimsel iş gücü, yüksek ciro | Vardiya, İzin, Bordro, ATS |
| **Sağlık** | Regülasyon yoğun, vardiya kritik | Vardiya, Bordro, Eğitim (sertifika) |
| **Lojistik & Kargo** | Saha çalışanları, mobil ihtiyaç yüksek | Mobil Self-Servis, Vardiya, PDKS |
| **Eğitim** | Sezonsal yapı, sözleşme çeşitliliği | Personel, İzin, Bordro |

### 1.3 Dijital Olgunluk Düzeyine Göre

| Düzey | Profil | Yaklaşım |
|-------|--------|---------|
| **Düzey 0 — Manuel** | Excel + kağıt, İK yazılımı yok | "Sıfırdan dijitalleşme" mesajı; basit, ücretsiz başlangıç |
| **Düzey 1 — Temel Dijital** | Basit bir İK aracı var ama yetersiz | "Daha fazlasını yapın" mesajı; geçiş kolaylığı |
| **Düzey 2 — Gelişmiş** | Mevcut İK yazılımı var, memnun değil | "Daha iyi alternatif" mesajı; veri göçü desteği |
| **Düzey 3 — Kurumsal** | SAP/Oracle var, yüksek maliyet | "Aynı güç, uygun fiyat" mesajı; modül bazlı geçiş |

---

## 2. Kullanıcı Rolleri

Sistemde 5 ana kullanıcı rolü bulunacaktır:

```
┌─────────────────────────────────────────────────────────┐
│                    SİSTEM YÖNETİCİSİ                    │
│              (IT Admin / Süper Admin)                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│   │  İK Müdürü / │  │  Departman   │  │   Çalışan    │ │
│   │  İK Uzmanı   │  │  Yöneticisi  │  │  (Self-Srv)  │ │
│   └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│   ┌──────────────────────────────────────────────────┐  │
│   │              ÜST YÖNETİM (C-Level)              │  │
│   │         (Dashboard & Raporlar — Salt Okunur)      │  │
│   └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

| Rol | Erişim | Kullanım Sıklığı |
|-----|--------|-----------------|
| **İK Müdürü / İK Uzmanı** | Tüm İK modülleri, raporlama, ayarlar | Günlük — 4-8 saat |
| **Departman Yöneticisi** | Kendi ekibi: izin onay, performans, vardiya | Günlük — 30-60 dk |
| **Çalışan** | Self-servis: izin talebi, bordro görüntüleme, profil | Haftalık — 10-20 dk |
| **Üst Yönetim (C-Level)** | Dashboard, raporlar, İK metrikleri | Haftalık/aylık — 15-30 dk |
| **Sistem Yöneticisi** | Kullanıcı yönetimi, entegrasyonlar, konfigürasyon | Gerektiğinde — değişken |

---

## 3. Persona Tanımları

### 3.1 Persona: Ayşe — İK Müdürü

```
┌─────────────────────────────────────────┐
│  👤 AYŞE KAYA                           │
│  İnsan Kaynakları Müdürü               │
│  38 yaş | Kadın | İstanbul             │
└─────────────────────────────────────────┘
```

| Alan | Detay |
|------|-------|
| **Şirket** | Orta ölçekli üretim firması, 180 çalışan, 3 şube |
| **Eğitim** | İşletme lisans, İK yüksek lisans |
| **Deneyim** | 12 yıl İK, 5 yılı yönetici pozisyonunda |
| **Ekip** | 2 İK uzmanı, 1 bordro sorumlusu |
| **Teknoloji** | Orta düzey; Excel kullanıyor, İK yazılımı deneyimi var |
| **Cihaz** | İş'te masaüstü, hareket halinde telefon |

**Günlük Rutini:**
1. Sabah: İzin taleplerini onaylama, devamsızlık kontrolü
2. Öğle: İşe alım süreçleri, mülakat değerlendirme
3. Öğleden sonra: Bordro hazırlığı, SGK bildirge kontrolü
4. Akşama doğru: Raporlama, performans takibi

**Acıları (Pain Points):**
- Excel'de bordro hesaplamak saatler sürüyor ve hata riski yüksek
- SGK bildirgesini ayrı bir sistemden yapmak zorunda kalıyor
- İzin bakiyeleri karmaşık, özellikle kıdem bazlı izin hesapları
- Performans değerlendirmesi kağıt üzerinde, takip zorlaşıyor
- 3 şube arasında veri tutarsızlığı oluyor
- Mevzuat değişikliklerini takip etmek zor (AGİ, vergi dilimleri)

**Hedefleri:**
- Tüm İK süreçlerini tek platformda yönetmek
- Bordro hatalarını sıfırlamak
- SGK/e-Devlet işlemlerini otomatikleştirmek
- Yönetim için anlamlı raporlar üretmek
- Stratejik İK'ya zaman ayırabilmek

**Başarı Kriteri:**
> "Ayda 3 gün bordro hazırlığından, 2 gün SGK bildirgelerinden kurtulursam, o zaman gerçek İK işlerime odaklanabilirim."

---

### 3.2 Persona: Mehmet — Departman Yöneticisi

```
┌─────────────────────────────────────────┐
│  👤 MEHMET DEMİR                        │
│  Üretim Müdürü                          │
│  45 yaş | Erkek | Kocaeli              │
└─────────────────────────────────────────┘
```

| Alan | Detay |
|------|-------|
| **Şirket** | Aynı üretim firması, 180 çalışan |
| **Sorumluluk** | 60 kişilik üretim ekibi, 3 vardiya |
| **Eğitim** | Makine mühendisliği |
| **Teknoloji** | Düşük-orta; telefon kullanıyor ama yazılıma mesafeli |
| **Cihaz** | Çoğunlukla telefon, nadiren masaüstü |

**Günlük Rutini:**
1. Sabah: Vardiya kontrolü, devamsızlık raporu
2. Gün içi: İzin talepleri WhatsApp'tan geliyor, kağıda not alıyor
3. Ay sonu: Puantaj tablosunu Excel'e giriyor

**Acıları:**
- İzin talepleri WhatsApp, telefon, yüz yüze — her yerden geliyor
- Vardiya değişikliği kaos yaratıyor
- Kim neredeydi, kim izinliydi — takip zor
- Performans değerlendirmesi için "o formu doldur" deniyor ama zaman yok
- Fazla mesai hesapları tutarsız

**Hedefleri:**
- İzin taleplerini telefondan tek tuşla onaylamak
- Vardiya planını kolay oluşturabilmek
- Ekibinin devamsızlık durumunu anlık görebilmek
- Performans notlarını hızlıca girebilmek

**Başarı Kriteri:**
> "Telefonumdan 10 saniyede izin onaylayabiliyorsam ve vardiya planı 5 dakikada çıkıyorsa, bu iş tamam."

---

### 3.3 Persona: Zeynep — Çalışan

```
┌─────────────────────────────────────────┐
│  👤 ZEYNEP YILDIZ                       │
│  Kalite Kontrol Uzmanı                  │
│  28 yaş | Kadın | Kocaeli              │
└─────────────────────────────────────────┘
```

| Alan | Detay |
|------|-------|
| **Şirket** | Aynı üretim firması, vardiyalı çalışıyor |
| **Eğitim** | Endüstri mühendisliği |
| **Teknoloji** | Yüksek; dijital araçlara aşina, her şeyi telefondan yapmak istiyor |
| **Cihaz** | Neredeyse sadece telefon |

**Günlük İK İhtiyaçları:**
- İzin talebi oluşturmak
- Kalan izin bakiyesini görmek
- Maaş bordrosunu görüntülemek
- Vardiya programını kontrol etmek
- Eğitim ve gelişim fırsatlarını keşfetmek

**Acıları:**
- İzin almak için İK'ya e-posta atıp geri dönüş beklemek zorunda
- Maaş bordrosunu görmek için İK'yı aramak gerekiyor
- Gelecek haftaki vardiyası ne, bilemiyor — WhatsApp grubundan bakıyor
- Hangi eğitime katılabileceğini öğrenmek zor
- Şirkette ne tür kariyer fırsatları var, görünür değil

**Hedefleri:**
- Tüm İK işlemlerini telefondan halletmek
- İzin talebini 3 tıkla oluşturmak
- Maaş bordrosunu istediği zaman görmek
- Vardiya programını haftalık bildirimle almak

**Başarı Kriteri:**
> "İzin isteyeceksem telefona 3 kez dokununca olsun. Bordromu merak ettiğimde hemen göreyim. O kadar."

---

### 3.4 Persona: Hakan — Şirket Sahibi / Genel Müdür

```
┌─────────────────────────────────────────┐
│  👤 HAKAN ÖZTÜRKoğlu                   │
│  Kurucu Ortak & Genel Müdür            │
│  52 yaş | Erkek | İstanbul             │
└─────────────────────────────────────────┘
```

| Alan | Detay |
|------|-------|
| **Şirket** | Perakende zinciri, 5 mağaza, 120 çalışan |
| **Eğitim** | İşletme |
| **Teknoloji** | Düşük; sonuçlara bakar, detayla uğraşmaz |
| **Cihaz** | Tablet + telefon |

**İK ile İlişkisi:**
- Ayda 1-2 kez İK'dan rapor ister
- Maliyet odaklı düşünür
- "Kaç kişi işe giriş/çıkış yaptı bu ay?" sorusu her toplantıda
- Fazla mesai maliyetlerini takip etmek istiyor

**Acıları:**
- İK'dan gelen raporlar Excel tablosu — anlayamıyor
- Şirketin toplam İK maliyetini bir bakışta göremiyor
- Fazla mesai maliyetinin hangi departmanda yoğunlaştığını bilmiyor
- İşten ayrılma oranı yükseliyor ama nedenini anlayamıyor
- "SGK cezası yedik" haberleri stres yaratıyor

**Hedefleri:**
- Tek ekranda şirketin İK özetini görmek (headcount, maliyet, devamsızlık, ciro)
- Trendleri grafiklerle izlemek
- Maliyet optimizasyonu için veri bazlı karar almak
- SGK/yasal uyumlulukta sıfır hata

**Başarı Kriteri:**
> "Tabletimi açtığımda şirketimin İK sağlığını bir bakışta anlayabilmeliyim. Detaya inmek istediğimde tek tıkla inebilmeliyim."

---

### 3.5 Persona: Emre — KOBİ Sahibi (Mikro/Küçük)

```
┌─────────────────────────────────────────┐
│  👤 EMRE ARSLAN                         │
│  Yazılım Şirketi Kurucusu              │
│  34 yaş | Erkek | Ankara               │
└─────────────────────────────────────────┘
```

| Alan | Detay |
|------|-------|
| **Şirket** | Yazılım ajansı, 22 çalışan |
| **Eğitim** | Bilgisayar mühendisliği |
| **Teknoloji** | Çok yüksek; her şeyi dijital istiyor |
| **Cihaz** | Laptop + telefon |
| **Mevcut Durum** | İK yok, kendisi yönetiyor, muhasebeci bordro yapıyor |

**Acıları:**
- İK işleri için ayrı bir kişi tutamıyor (maliyet)
- İzinleri Slack'te takip ediyor, bazen kaçırıyor
- Bordroyu muhasebeciye her ay Excel gönderiyor
- Performans değerlendirme yok — hissi olarak değerlendiriyor
- OKR kullanmak istiyor ama araç yok
- İşe alım LinkedIn + tanıdık üzerinden, süreç yok

**Hedefleri:**
- İK'yı "sıfır İK personeli" ile yönetebilmek
- Ücretsiz veya çok düşük maliyetli başlangıç
- Slack/Teams entegrasyonu
- Modern, API-first bir aracı kolayca entegre etmek

**Başarı Kriteri:**
> "10 dakikada kurulup çalışan, ücretsiz başlayabileceğim, büyüdükçe modül ekleyebileceğim bir şey lazım. Ucube Excel tablolarından kurtulmalıyım."

---

### 3.6 Persona: Fatma — İK Uzmanı (İşe Alım Odaklı)

```
┌─────────────────────────────────────────┐
│  👤 FATMA ŞAHİN                         │
│  İşe Alım Uzmanı                       │
│  30 yaş | Kadın | İstanbul             │
└─────────────────────────────────────────┘
```

| Alan | Detay |
|------|-------|
| **Şirket** | Teknoloji firması, 300 çalışan, yılda 60+ pozisyon |
| **Sorumluluk** | İlan yönetimi, aday tarama, mülakat koordinasyonu, teklif süreci |
| **Teknoloji** | Yüksek; ATS deneyimi var (Kariyer.net arka ofis) |

**Acıları:**
- Farklı platformlardan gelen başvuruları tek yerde toplayamıyor
- CV'leri manuel taramak saatler sürüyor
- Mülakat notları e-posta/WhatsApp'ta dağınık
- Aday deneyimi ölçülemiyor — tekliflerin kabul oranı düşük
- Onboarding süreci kopuk, ilk gün kaotik

**Hedefleri:**
- Tüm başvuruları tek panelde görmek
- AI ile CV ön eleme
- Mülakat takvimini aday ile otomatik paylaşmak
- Onboarding checklist'i dijitalleştirmek
- İşe alım metriklerini raporlamak (time-to-hire, cost-per-hire)

**Başarı Kriteri:**
> "Bir pozisyonu açıyorum, başvurular otomatik sıralanıyor, mülakat planlama tek tık, aday 'çok profesyonel bir süreçti' diyor — işte o zaman mutluyum."

---

## 4. Kullanıcı Hikayeleri (User Stories)

### 4.1 Personel Yönetimi

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-P01 | İK Uzmanı | Yeni çalışan kaydını tüm özlük bilgileriyle birlikte oluşturabilmeliyim | Must |
| US-P02 | İK Uzmanı | Çalışan listesini departman, pozisyon, işe giriş tarihine göre filtreleyebilmeliyim | Must |
| US-P03 | İK Uzmanı | Çalışanın iş sözleşmesi, kimlik, diploma gibi belgelerini dijital ortamda saklayabilmeliyim | Must |
| US-P04 | Çalışan | Kendi profil bilgilerimi (adres, telefon, acil durum kişisi) güncelleyebilmeliyim | Must |
| US-P05 | İK Uzmanı | İşten çıkış sürecini (kıdem/ihbar hesabı, çıkış mülakatı) yönetebilmeliyim | Must |
| US-P06 | İK Uzmanı | Toplu çalışan verilerini Excel'den içe aktarabilmeliyim | Must |
| US-P07 | Yönetici | Ekibimdeki çalışanların temel bilgilerini ve organizasyon yapısını görebilmeliyim | Should |

### 4.2 İzin & Devamsızlık

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-İ01 | Çalışan | Mobil uygulama üzerinden izin talebi oluşturabilmeliyim | Must |
| US-İ02 | Yönetici | Gelen izin taleplerini mobilde tek tuşla onaylayabilmeliyim | Must |
| US-İ03 | Çalışan | Kalan izin bakiyemi (yıllık, mazeret, hastalık) anlık görebilmeliyim | Must |
| US-İ04 | İK Uzmanı | İzin türlerini ve kotalarını kıdeme göre otomatik tanımlayabilmeliyim | Must |
| US-İ05 | Yönetici | Ekibimin izin takvimini görebilmeliyim (çakışma kontrolü) | Should |
| US-İ06 | İK Uzmanı | Devamsızlık raporlarını departman bazında alabilmeliyim | Should |
| US-İ07 | Sistem | Resmi tatilleri otomatik takvime eklemeli ve izin bakiyelerinden düşmemelidir | Must |

### 4.3 Bordro & Maaş

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-B01 | İK Uzmanı | Aylık bordroyu SGK primleri, gelir vergisi, damga vergisi dahil otomatik hesaplatabilmeliyim | Must |
| US-B02 | İK Uzmanı | Fazla mesai, prim, ikramiye gibi ek ödemeleri bordro hesabına dahil edebilmeliyim | Must |
| US-B03 | Çalışan | Aylık maaş bordromu mobil uygulama üzerinden görüntüleyebilmeliyim | Must |
| US-B04 | İK Uzmanı | Mevzuat değişikliklerinde (vergi dilimi, SGK tavan, AGİ) sistemi tek tuşla güncelleyebilmeliyim | Must |
| US-B05 | İK Uzmanı | SGK bildirgesi (APHB) verilerini otomatik dışa aktarabilmeliyim | Should |
| US-B06 | Üst Yönetim | Toplam personel maliyetini departman bazında görebilmeliyim | Should |
| US-B07 | İK Uzmanı | Maaş simülasyonu yapabilmeliyim (zam senaryoları, maliyet etkisi) | Could |

### 4.4 Performans Yönetimi

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-PF01 | İK Uzmanı | Dönemsel performans değerlendirme sürecini başlatıp yönetebilmeliyim | Must |
| US-PF02 | Yönetici | Ekip üyelerime hedef (OKR/KPI) belirleyebilmeliyim | Must |
| US-PF03 | Çalışan | Kendi hedeflerimi ve ilerleme durumumu görebilmeliyim | Must |
| US-PF04 | İK Uzmanı | 360° feedback süreci oluşturabilmeliyim | Should |
| US-PF05 | Yönetici | Ekibimin yetkinlik matrisini görebilmeliyim | Should |
| US-PF06 | Üst Yönetim | Şirket geneli performans dağılımını dashboard'da görebilmeliyim | Should |

### 4.5 İşe Alım (ATS)

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-A01 | İK Uzmanı | İş ilanı oluşturup birden fazla kanala yayınlayabilmeliyim | Must |
| US-A02 | İK Uzmanı | Tüm kanallardan gelen başvuruları tek panelde görebilmeliyim | Must |
| US-A03 | İK Uzmanı | Adayları aşamalar arasında (başvuru → ön eleme → mülakat → teklif) sürükleyerek taşıyabilmeliyim | Must |
| US-A04 | Yönetici | Mülakat değerlendirme formunu doldurup not bırakabilmeliyim | Should |
| US-A05 | İK Uzmanı | Aday havuzu oluşturup gelecekteki pozisyonlar için saklayabilmeliyim | Should |
| US-A06 | İK Uzmanı | İşe alım metriklerini (time-to-hire, kaynak analizi) raporlayabilmeliyim | Could |

### 4.6 Vardiya & Mesai

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-V01 | İK Uzmanı | Vardiya şablonları tanımlayabilmeliyim (sabah/akşam/gece) | Must |
| US-V02 | Yönetici | Haftalık/aylık vardiya planını oluşturabilmeliyim | Must |
| US-V03 | Çalışan | Kendi vardiya programımı mobilde görebilmeliyim | Must |
| US-V04 | Sistem | Fazla mesai saatlerini otomatik hesaplayabilmelidir | Must |
| US-V05 | İK Uzmanı | PDKS cihazlarından giriş/çıkış verilerini alabilmeliyim | Should |
| US-V06 | Yönetici | Vardiya çakışması uyarısı alabilmeliyim | Should |

### 4.7 Eğitim & Gelişim

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-E01 | İK Uzmanı | Eğitim planı oluşturup çalışanlara atayabilmeliyim | Must |
| US-E02 | Çalışan | Bana atanan eğitimleri ve sertifikalarımı görebilmeliyim | Must |
| US-E03 | İK Uzmanı | Sertifika geçerlilik tarihlerini takip edip süre dolmadan uyarı alabilmeliyim | Should |
| US-E04 | Çalışan | Eğitim kataloğundan kendi gelişim alanıma uygun eğitim talep edebilmeliyim | Could |

### 4.8 Raporlama & Analitik

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-R01 | Üst Yönetim | Ana dashboard'da headcount, maliyet, devamsızlık, ciro oranını görebilmeliyim | Must |
| US-R02 | İK Uzmanı | Hazır rapor şablonlarını kullanabilmeliyim (departman bazlı, dönemsel) | Must |
| US-R03 | İK Uzmanı | Özel rapor oluşturup filtreleme yapabilmeliyim | Should |
| US-R04 | Üst Yönetim | İK metriklerini geçmiş dönemle karşılaştırabilmeliyim (trend analizi) | Should |
| US-R05 | İK Uzmanı | Raporları PDF/Excel olarak dışa aktarabilmeliyim | Must |

### 4.9 Self-Servis Portal

| ID | Kullanıcı | Hikaye | Öncelik |
|----|-----------|--------|---------|
| US-S01 | Çalışan | Şirket duyurularını mobilde görebilmeliyim | Must |
| US-S02 | Çalışan | Doğum günü ve iş yıl dönümü bildirimlerini alabilmeliyim | Should |
| US-S03 | Çalışan | Şirket rehberinden iş arkadaşlarımın iletişim bilgisine ulaşabilmeliyim | Should |
| US-S04 | Çalışan | Avans, masraf, fazla mesai gibi talepler oluşturabilmeliyim | Must |
| US-S05 | Yönetici | Ekibimle ilgili tüm talepleri tek panelden yönetebilmeliyim | Must |

---

## 5. Kullanıcı Yolculuk Haritaları (User Journey)

### 5.1 Çalışan İzin Talebi Yolculuğu

```
İHTİYAÇ          EYLEM               SİSTEM              SONUÇ
  │                 │                    │                   │
  ▼                 ▼                    ▼                   ▼
İzin almak    ─→  Mobil uygulamayı  ─→  İzin bakiyesini  ─→  Talep
istiyorum         açıyor                gösterir              oluşturuldu
                    │                    │                   │
                    ▼                    ▼                   ▼
              Tarih seçiyor     ─→  Çakışma kontrolü  ─→  Yöneticiye
              İzin türü seçiyor     yapar                   bildirim
                                                            gider
                                         │                   │
                                         ▼                   ▼
                                    Yönetici onaylar  ─→  Çalışana
                                    veya reddeder         bildirim
                                                            │
                                                            ▼
                                                      Bakiye güncellenir
                                                      Takvim güncellenir
```

**Hedef Süreler:**
- Talep oluşturma: **< 30 saniye**
- Yönetici onayı: **< 1 dakika** (mobil bildirim ile)
- Toplam süreç: **< 5 dakika**

### 5.2 İK Uzmanı Aylık Bordro Yolculuğu

```
AY SONU         VERİ TOPLAMA          HESAPLAMA           ÇIKTI
  │                 │                    │                   │
  ▼                 ▼                    ▼                   ▼
Bordro          Puantaj verileri   ─→  Otomatik brüt/net ─→  Bordro
hazırla         otomatik çekilir       hesaplama              PDF
                    │                    │                   │
                    ▼                    ▼                   ▼
              İzin/devamsızlık  ─→  SGK prim kesintisi ─→  SGK
              verileri çekilir      Gelir vergisi          bildirge
                    │               Damga vergisi          verisi
                    ▼                    │                   │
              Ek ödemeler       ─→  Kontrol & onay    ─→  Banka
              girilir (prim,         ekranı                 dosyası
              fazla mesai)              │                   │
                                        ▼                   ▼
                                   İK Müdürü onaylar ─→  Çalışanlara
                                                         bildirim
```

**Hedef Süreler:**
- Veri toplama: **Otomatik** (önceden 2 gün)
- Hesaplama: **< 5 dakika** (önceden 2-3 gün)
- Kontrol & onay: **< 1 saat**
- Toplam: **< 2 saat** (önceden 3-5 iş günü)

---

## 6. Erişim Platformu Tercihleri

| Persona | Web (Desktop) | Mobil (Uygulama) | Tablet | Birincil |
|---------|-------------|-----------------|--------|---------|
| İK Müdürü (Ayşe) | %70 | %25 | %5 | Web |
| Yönetici (Mehmet) | %20 | %75 | %5 | **Mobil** |
| Çalışan (Zeynep) | %10 | %85 | %5 | **Mobil** |
| Üst Yönetim (Hakan) | %20 | %30 | %50 | **Tablet** |
| KOBİ Sahibi (Emre) | %50 | %45 | %5 | Web + Mobil |
| İşe Alım (Fatma) | %80 | %15 | %5 | Web |

> **Sonuç:** Çalışanlar ve yöneticiler ağırlıklı olarak **mobil** kullanıcı. İK uzmanları **web** odaklı. Tüm modüller **responsive** olmalı, mobilde izin/onay/bildirim/vardiya/bordro görüntüleme tam fonksiyonel olmalı.

---

## 7. Persona Bazlı Modül Öncelik Matrisi

| Modül | Ayşe (İK) | Mehmet (Yön.) | Zeynep (Çalışan) | Hakan (C-Level) | Emre (KOBİ) | Fatma (ATS) |
|-------|-----------|-------------|-----------------|----------------|------------|------------|
| Personel | ★★★ | ★ | ★★ | ★ | ★★★ | ★ |
| İzin | ★★★ | ★★★ | ★★★ | ★ | ★★ | ★ |
| Bordro | ★★★ | ★ | ★★ | ★★ | ★★★ | ★ |
| Performans | ★★ | ★★★ | ★★ | ★★ | ★★ | ★ |
| İşe Alım | ★★ | ★ | ★ | ★ | ★ | ★★★ |
| Vardiya | ★★ | ★★★ | ★★ | ★ | ★ | ★ |
| Eğitim | ★★ | ★ | ★★ | ★ | ★ | ★ |
| Org. Şeması | ★★ | ★ | ★ | ★★ | ★ | ★ |
| Raporlama | ★★★ | ★ | ★ | ★★★ | ★★ | ★★ |
| Self-Servis | ★ | ★★ | ★★★ | ★ | ★ | ★ |

*(★★★ = Kritik, ★★ = Önemli, ★ = İkincil)*

---

## 8. Sonuç

### MVP İçin Minimum Persona Kapsamı

MVP aşamasında minimum 3 persona tatmin edilmeli:

1. **Ayşe (İK Müdürü)** — Birincil kullanıcı, her gün kullanacak
2. **Zeynep (Çalışan)** — En kalabalık kullanıcı grubu, mobil odaklı
3. **Mehmet (Yönetici)** — Onay mekanizması için kritik, mobil odaklı

### MVP Modül-Persona Eşleşmesi

```
MVP = Personel + İzin + Self-Servis Portal
    → Ayşe: Çalışan kaydı + izin yönetimi ✅
    → Zeynep: İzin talebi + bakiye görüntüleme + profil ✅
    → Mehmet: İzin onaylama + ekip görüntüleme ✅
```

---

> **Sonraki Adım:** [04-gereksinim-analizi.md](04-gereksinim-analizi.md) — Fonksiyonel ve fonksiyonel olmayan gereksinimler, MoSCoW önceliklendirme
