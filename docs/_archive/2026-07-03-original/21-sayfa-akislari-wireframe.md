# 21 — Sayfa Akışları & Wireframe Rehberi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Ana kullanıcı akışları, temel ekran kümeleri, navigasyon modeli, modüller arası geçişler, wireframe öncelik listesi  
> **Faz:** Faz 4

---

## 1. Bilgi Mimarisi

### 1.1 Ana Navigasyon Haritası

```
┌────────────────────────────────────────────────────────────────┐
│                          App Shell                              │
├────────────┬───────────────────────────────────────────────────┤
│            │                                                    │
│  SIDEBAR   │               İÇERİK ALANI                        │
│            │                                                    │
│  🏠 Dashboard │                                                │
│  👥 Personel  │  ┌─────────────────────────────────────┐       │
│  🏖 İzin      │  │  Breadcrumb: Dashboard > İzin > ...  │       │
│  📋 İşe Alım  │  ├─────────────────────────────────────┤       │
│  ⭐ Performans│  │                                     │       │
│  📚 Eğitim    │  │          Sayfa İçeriği               │       │
│  💰 Bordro    │  │                                     │       │
│  🕐 Vardiya   │  │                                     │       │
│  🏢 Organizas.│  │                                     │       │
│  📊 Raporlar  │  │                                     │       │
│  ⚙️ Ayarlar   │  └─────────────────────────────────────┘       │
│              │                                                  │
│  ─────────   │    ÜST BAR:                                      │
│  👤 Profilim  │    [Arama] [🔔 Bildirim] [👤 Profil/Çıkış]     │
│              │                                                  │
└────────────┴────────────────────────────────────────────────────┘
```

### 1.2 Navigasyon Detayları

| Bölüm | Alt Sayfalar | Erişim |
|-------|--------------|--------|
| Dashboard | Çalışan dashboard, yönetici dashboard, İK dashboard, executive dashboard | Rol bazlı |
| Personel | Liste, kart/detay, belge yönetimi, özlük, onboarding sihirbazı | İK + Admin |
| İzin | Taleplerim/listesi, takım takvimi, bakiyeler, politikalar | Herkes (scope'lu) |
| İşe Alım | İlanlar, aday havuzu, pipeline (Kanban), mülakat takvimi, teklifler | İK + Hiring mgr |
| Performans | Hedefler, değerlendirmeler, kalibrasyon, PIP takibi | Herkes (scope'lu) |
| Eğitim | Katalog, atamalarım, sertifikalar, gelişim planı | Herkes (scope'lu) |
| Bordro | Dönemler, bordro hesaplama, puslalar, export, SGK | İK Bordro |
| Vardiya | Şablonlar, plan, puantaj, mesai onayları, PDKS | Operasyon + İK |
| Organizasyon | Organigram, pozisyonlar, kadro planı, vekaletler | İK + Admin |
| Raporlar | Executive dashboard, İK dashboard, özel rapor, export merkezi | Rol bazlı |
| Ayarlar | Roller/yetkiler, entegrasyonlar, politika setleri, tenant ayarları | Admin |

### 1.3 Mobil Bottom Navigation

```
┌───────────────────────────────────────────────┐
│                                               │
│              Sayfa İçeriği (Tam ekran)         │
│                                               │
├──────┬──────┬──────┬──────┬──────────────────┤
│  🏠  │  🏖  │  ✏️  │  🔔  │      👤          │
│ Ana  │ İzin │Görev │Bildir│    Profil        │
│Sayfa │      │lerim │imler │                  │
└──────┴──────┴──────┴──────┴──────────────────┘
```

Mobilde "Daha fazla" menüsü → hamburger ile tüm modüllere erişim.

---

## 2. Kritik Kullanıcı Akışları

### 2.1 Çalışan — İzin Talebi Akışı

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│Dashboard │───▶│İzin Kartı│───▶│Talep Form│───▶│Önizleme &│───▶│  Başarılı │
│          │    │"Bakiye:12"│    │          │    │Validasyon│    │          │
│[İzin Tal]│    │[Talep Et]│    │Tip: Yıllık│   │          │    │"Talebiniz│
│          │    │          │    │Tarih: ... │    │Bakiye ✓  │    │ gönderil-│
│          │    │          │    │Vekil: ... │    │Çakışma ✓ │    │ di"      │
│          │    │          │    │[Gönder]  │    │[Onayla]  │    │[Takip Et]│
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                      │                                │
                                      ▼                                ▼
                                 Hata varsa:                    ┌──────────┐
                                 "Yetersiz                      │  Detay & │
                                  bakiye"                       │Durum Tak.│
                                  inline uyarı                  │[İptal Et]│
                                                                └──────────┘
```

### 2.2 Yönetici — Onay Kutusu Akışı

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│Yönetici  │───▶│Bekleyen  │───▶│Görev Det.│───▶│Sonuç &   │
│Dashboard │    │Görevlerim│    │Panel     │    │Feed      │
│          │    │          │    │          │    │          │
│"3 onay   │    │İzin: Ali │    │Ali Yılmaz│    │✅ Onay-  │
│ bekliyor"│    │İzin: Fatma│   │3 gün yıl.│   │landı     │
│[Gör]     │    │Mesai: Em.│    │10-12 Şub │    │Bildirim  │
│          │    │          │    │Bakiye: OK│    │gönderildi│
│          │    │[Detay]   │    │          │    │          │
│          │    │[Toplu On]│    │[Onayla]  │    │[Geri Dön]│
│          │    │          │    │[Reddet]  │    │          │
│          │    │          │    │[Yorum]   │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 2.3 İK — Çalışan Kayıt Akışı (Sihirbaz)

```
Adım 1/5          Adım 2/5          Adım 3/5          Adım 4/5          Adım 5/5
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│KİMLİK    │───▶│İŞ BİLGİ  │───▶│ORGANİZAS.│───▶│BELGELER  │───▶│ÖZET &    │
│          │    │          │    │& ÜCRET   │    │          │    │KAYIT     │
│Ad, Soyad │    │İşe Giriş │    │Departman │    │Kimlik    │    │Tüm bilgi │
│TC Kimlik  │    │Pozisyon  │    │Yönetici  │    │Sözleşme  │    │Doğrulama │
│Doğum Tar.│    │Sözleşme  │    │Brüt Maaş │    │Fotoğraf  │    │          │
│Cinsiyet  │    │Çalışma T.│    │Erişim Rol│    │Diğer...  │    │[Kaydet]  │
│İletişim  │    │          │    │          │    │          │    │          │
│          │    │          │    │          │    │          │    │          │
│ [İleri →]│    │ [İleri →]│    │ [İleri →]│    │ [İleri →]│    │          │
│          │    │[← Geri]  │    │[← Geri]  │    │[← Geri]  │    │[← Geri]  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘  
    ●               ●               ●               ●               ●
  Progress bar: ════════════════════════════[████████████░░░░]═══════════
```

### 2.4 Performans — Dönemden Sonuca Akışı

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│Dönem     │───▶│Hedef     │───▶│Öz Değer- │───▶│Yönetici  │───▶│Kalibras- │───▶│Sonuç     │
│Açılışı   │    │Tanımlama │    │lendirme  │    │Değerlend.│    │yon       │    │Yayını    │
│          │    │          │    │          │    │          │    │          │    │          │
│ İK admin │    │ Çalışan  │    │ Çalışan  │    │ Yönetici │    │ İK+Üst Y.│    │ Çalışan  │
│ dönem    │    │ hedefler │    │ form dol-│    │ form dol-│    │ puan     │    │ sonucu   │
│ ayarları │    │ oluşturur│    │ durur    │    │ durur    │    │ normaliz.│    │ görebilir│
│          │    │ yönetici │    │          │    │          │    │          │    │          │
│          │    │ onaylar  │    │          │    │          │    │          │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 2.5 İşe Alım — Pipeline Akışı

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│Talep     │───▶│İlan      │───▶│Pipeline  │───▶│Teklif &  │
│Oluştur   │    │Yayınla   │    │(Kanban)  │    │Onboarding│
│          │    │          │    │          │    │          │
│Pozisyon  │    │İlan met. │    │Başvuru → │    │Teklif    │
│Min. krit.│    │Kanal seç │    │Ön Eleme→ │    │dokümanı  │
│Bütçe     │    │Yayınla   │    │Mülakat → │    │İmza      │
│Onay      │    │          │    │Teklif →  │    │Personel  │
│          │    │          │    │Red/Kabul │    │kaydı     │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 2.6 Bordro — Aylık Dönem Akışı

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│Dönem Aç  │───▶│Verileri  │───▶│Bordro    │───▶│İnceleme &│───▶│Banka &   │
│          │    │Topla     │    │Hesapla   │    │Onay      │    │Kapanış   │
│          │    │          │    │          │    │          │    │          │
│Ay seç    │    │Puantaj   │    │Hesapla   │    │Karşılaşt.│    │Banka exp.│
│Kontrol l.│    │Mesai     │    │butonu    │    │Hata kont.│    │SGK bild. │
│          │    │Ek ödemeler│   │Toplu     │    │Onay      │    │Pusulalar │
│          │    │Kesintiler│    │hesaplama │    │          │    │Dönem klt.│
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

---

## 3. Wireframe Öncelik Matrisi

| Öncelik | Sayfa | Modül | Neden | Faz |
|---------|-------|-------|-------|-----|
| P1 | Self-servis dashboard (çalışan + yönetici) | Portal | Tüm kullanıcıların giriş noktası | MVP |
| P1 | İzin talep formu + bakiye kart | İzin | MVP kritik akış | MVP |
| P1 | Personel detay kartı (profil) | Personel | Ana veri yüzeyi | MVP |
| P1 | Yönetici onay paneli | Portal | Günlük operasyon akışı | MVP |
| P1 | Bordro dönem yönetimi | Bordro | Hassas operasyon alanı | MVP |
| P1 | Login / SSO / MFA ekranı | Auth | İlk dokunma noktası | MVP |
| P2 | Performans değerlendirme formu | Performans | Faz 2 kritik ekran | Faz 2 |
| P2 | İşe alım pipeline (Kanban) | İşe Alım | ATS ana ekranı | Faz 2 |
| P2 | Vardiya planlama (sürükle-bırak) | Vardiya | Operasyonel planlama | Faz 2 |
| P2 | Organizasyon şeması (interaktif) | Organizasyon | Hiyerarşi görselleştirme | Faz 2 |
| P3 | Executive dashboard | Raporlama | Yönetim KPI'ları | Faz 3 |
| P3 | Özel rapor oluşturucu | Raporlama | Analitik esneklik | Faz 3 |
| P3 | Eğitim kataloğu ve atama | Eğitim | L&D akışları | Faz 3 |

---

## 4. Wireframe Standartları ve Notları

### 4.1 Genel Kurallar

| Alan | Kural |
|------|-------|
| Dashboard | Kart + görev + duyuru kombinasyonu; 3-4 kolon grid (desktop), tek kolon (mobil) |
| Veri yoğun ekranlar | Filtre çubuğu sabit (sticky), sayfalama + sayfa başına kayıt seçeneği |
| Formlar | 5-7 alanı geçen formlar stepper ile bölünmeli; mobilde tek kolon |
| Mobil alt nav | Yalnızca sık kullanılan 4-5 alan gösterilmeli |
| Loading state | İçerik yerleşimi koruyan skeleton loader (shimmer) |
| Error state | Inline hata mesajı + açıklayıcı metin + tekrar dene butonu |
| Empty state | İllüstrasyon + açıklama + CTA (bkz. 20-tasarim-rehberi.md §3.4) |

### 4.2 Modüller Arası Geçiş Haritası

```
Portal Dashboard ──────────────────────────────────────┐
    │                                                    │
    ├── İzin kartı ─────────────────── İzin modülü       │
    ├── Bordro pusulası ────────────── Bordro modülü     │
    ├── Performans görevi ──────────── Performans modülü │
    ├── Eğitim kartı ──────────────── Eğitim modülü     │
    ├── Vardiya takvimi ────────────── Vardiya modülü    │
    ├── Şirket rehberi ─────────────── Organizasyon mod. │
    └── Raporlar ───────────────────── Raporlama modülü  │
                                                         │
Yönetici Dashboard ──────────────────────────────────────┤
    ├── Onay kutusu ────────────────── İlgili modüle yön.│
    ├── Takım takvimi ─────────────── İzin + Vardiya     │
    └── Ekip performansı ──────────── Performans modülü  │
```

### 4.3 Breadcrumb Yapısı

```
Ana Sayfa > İzin > Yeni Talep
Ana Sayfa > Personel > Ali Yılmaz > Belgeleri
Ana Sayfa > Performans > 2025 Q1 > Hedefler
Ana Sayfa > Bordro > Ocak 2025 > Hesaplama
Ana Sayfa > Raporlar > Özel Rapor > Düzenle
```

---

## 5. Detay Wireframe: Self-Servis Dashboard (P1)

### 5.1 Çalışan Görünümü (Desktop)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [☰]  İK Portal          [🔍 Ara...]         [🔔 3]  [👤 Zeynep ▾]   │
├──────────┬──────────────────────────────────────────────────────────────┤
│          │                                                              │
│ 🏠 Ana   │  Merhaba, Zeynep                            3 Şubat 2025   │
│ 🏖 İzin  │  ─────────────────────────────────────────────────────────  │
│ ⭐ Perf. │                                                              │
│ 📚 Eğitim│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│ 🕐 Vardiya│ │📋 Görevler  │ │🏖 İzin      │ │🕐 Bu Hafta          │   │
│ 💰 Bordro│  │  2 bekleyen │ │  Yıllık: 12 │ │  Pzt-Cum 08:00-16:00│   │
│ 📄 Belge │  │  [Görüntüle]│ │  [Talep Et] │ │  [Takvim]           │   │
│ 📢 Duyuru│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│          │                                                              │
│          │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│          │  │💰 Bordro    │ │📚 Eğitim    │ │⭐ Performans        │   │
│          │  │  Ocak: Net  │ │  İSG eğitimi│ │  Hedef ilerlemesi   │   │
│          │  │  ₺28.500    │ │  15 Şubat   │ │  ████████░░ 75%     │   │
│          │  │  [İndir]    │ │  [Detay]    │ │  [Hedeflerim]       │   │
│          │  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│          │                                                              │
│          │  📢 Duyurular                                       [Tümü] │
│          │  ─────────────────────────────────────────────────────────  │
│          │  ⭐ Yeni Yan Haklar Paketi          2 saat önce   [Oku]    │
│          │  ○  Ofis Taşınma Bilgisi            1 gün önce    [Oku]    │
│          │                                                              │
└──────────┴──────────────────────────────────────────────────────────────┘
```

### 5.2 Çalışan Görünümü (Mobil)

```
┌──────────────────────┐
│  İK Portal    🔔 3 👤│
├──────────────────────┤
│                      │
│  Merhaba, Zeynep     │
│                      │
│  ┌──────────────────┐│
│  │📋 2 Görev Bekliy.││
│  │[Görüntüle →]     ││
│  └──────────────────┘│
│                      │
│  ┌──────────────────┐│
│  │🏖 İzin Bakiyem   ││
│  │  Yıllık: 12 gün  ││
│  │  [İzin Talep Et] ││
│  └──────────────────┘│
│                      │
│  ┌──────────────────┐│
│  │🕐 Bugün Vardiyam ││
│  │  08:00-16:00     ││
│  └──────────────────┘│
│                      │
│  ┌──────────────────┐│
│  │💰 Son Bordro     ││
│  │  Ocak — ₺28.500  ││
│  │  [İndir]         ││
│  └──────────────────┘│
│                      │
│  📢 Yeni Yan Haklar │
│     Paketi [Oku →]   │
│                      │
├──────┬──────┬──────┬─┤
│ 🏠   │ 🏖   │ ✏️   │🔔│
│Ana   │İzin  │Görev │Bil│
└──────┴──────┴──────┴─┘
```

---

## 6. Detay Wireframe: İzin Talep Formu (P1)

```
┌────────────────────────────────────────────────────┐
│  İzin Talebi                          [× Kapat]   │
├────────────────────────────────────────────────────┤
│                                                    │
│  İzin Tipi: [Yıllık İzin          ▾]              │
│                                                    │
│  Başlangıç:  [📅 10.02.2025]  ○ Tam gün          │
│  Bitiş:      [📅 12.02.2025]  ○ Yarım gün (öğle) │
│                                                    │
│  Süre: 3 gün    Kalan bakiye: 12 gün              │
│                                                    │
│  Vekil: [Mehmet Kaya             ▾]               │
│                                                    │
│  Açıklama:                                         │
│  ┌──────────────────────────────────────┐          │
│  │ (opsiyonel)                          │          │
│  └──────────────────────────────────────┘          │
│                                                    │
│  Ek Dosya: [📎 Dosya Seç]                         │
│                                                    │
│  ⚠️ Takım takvimi: Aynı tarihte 1 kişi izinli    │
│                                                    │
│         [İptal]              [Talebi Gönder]       │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## 7. Detay Wireframe: Yönetici Onay Paneli (P1)

```
┌────────────────────────────────────────────────────────────────┐
│  Onay Bekleyenler                          Toplam: 4 işlem    │
├──────────────────────────────────────┬─────────────────────────┤
│                                      │                         │
│  ┌────────────────────────────────┐  │  DETAY PANELİ           │
│  │ 🏖 Ali Yılmaz — İzin Talebi   │◀─│  ───────────────────    │
│  │   3 gün yıllık, 10-12 Şubat   │  │  Ali Yılmaz              │
│  │   ⏱ 2 saat önce               │  │  Yazılım Geliştirme     │
│  └────────────────────────────────┘  │                         │
│  ┌────────────────────────────────┐  │  Talep: 3 gün yıllık   │
│  │ 🏖 Fatma S. — İzin Talebi     │  │  Tarih: 10-12 Şubat    │
│  │   1 gün hastalık, 3 Şubat     │  │  Bakiye: 14 gün ✅      │
│  │   ⏱ 5 saat önce               │  │  Vekil: Mehmet Kaya    │
│  └────────────────────────────────┘  │  Çakışma: Yok ✅        │
│  ┌────────────────────────────────┐  │                         │
│  │ 🕐 Emre D. — Mesai Onayı      │  │  Yorum:                 │
│  │   45 dk normal mesai           │  │  ┌───────────────────┐  │
│  │   ⏱ 1 gün önce                │  │  │ (opsiyonel)       │  │
│  └────────────────────────────────┘  │  └───────────────────┘  │
│  ┌────────────────────────────────┐  │                         │
│  │ ⭐ Zeynep A. — Performans     │  │  [Reddet]  [Onayla ✓]  │
│  │   Hedef onayı bekliyor        │  │                         │
│  │   ⏱ 3 gün önce                │  │                         │
│  └────────────────────────────────┘  │                         │
│                                      │                         │
│  [Tümünü Onayla]                     │                         │
├──────────────────────────────────────┴─────────────────────────┤
│  Geçmiş onaylar (son 30 gün)                          [Tümü]  │
└────────────────────────────────────────────────────────────────┘
```

---

## 8. Çıktılar ve Teslimatlar

| # | Çıktı | Araç/Format | Hedef |
|---|-------|-------------|-------|
| 1 | Düşük sadakat wireframe seti | Figma | Tüm P1 sayfaları |
| 2 | Tıklanabilir prototip akışları | Figma Prototype | İzin talebi, onay, personel kayıt |
| 3 | Responsive breakpoint varyasyonları | Figma | Her P1 sayfa için mobile + desktop |
| 4 | Geliştirici handoff bileşen haritası | Figma Dev Mode | Spacing, renk, tipografi ölçüleri |
| 5 | Kullanıcı akış diyagramları | Mermaid / draw.io | Tüm §2 akışları |
| 6 | Erişilebilirlik kontrol listesi | Doküman | Her sayfa için a11y checklist |
