# 22 — Mobil Tasarım Stratejisi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Mobil öncelikli kullanım senaryoları, responsive strateji, PWA ve native karar çerçevesi, push bildirimleri, offline yaklaşımı  
> **Faz:** Faz 4

---

## 1. Mobil Strateji Özeti

Mobil deneyim, masaüstü arayüzün küçültülmüş versiyonu olarak değil; çalışan ve yönetici günlük ihtiyaçlarının hızlı çözüldüğü ayrı bir öncelik katmanı olarak ele alınır. MVP ve Faz 2 boyunca mobilde en kritik işlemler izin, onay, bildirim, vardiya görünümü ve performans görevleridir.

---

## 2. Mobilde Öncelikli Senaryolar

| Öncelik | Senaryo | Kullanıcı | Kullanım Sıklığı |
|---------|---------|-----------|-------------------|
| 1 | İzin talebi oluşturma ve durum takibi | Çalışan | Haftalık |
| 2 | Yönetici onayı / reddi | Yönetici | Günlük |
| 3 | Vardiya takvimi ve puantaj görüntüleme | Çalışan | Günlük |
| 4 | Giriş-çıkış (mobil check-in) | Çalışan | Günlük (2×) |
| 5 | Duyuru ve bildirim okuma | Herkes | Günlük |
| 6 | Performans öz değerlendirme görevleri | Çalışan | Dönemsel |
| 7 | Bordro pusulası görüntüleme / indirme | Çalışan | Aylık |
| 8 | Profil görüntüleme ve acil durum bilgisi güncelleme | Çalışan | Nadiren |

### 2.1 Mobil Ekran Akışları

#### İzin Talebi (Mobil)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│Dashboard │───▶│İzin Kart │───▶│Talep Form│───▶│ Başarılı │
│          │    │          │    │(Bottom   │    │          │
│[İzin Tal]│    │Bakiye:12 │    │ Sheet)   │    │"Gönder-  │
│          │    │[Talep Et]│    │Tip, Tarih│    │ ildi ✓"  │
│          │    │          │    │Vekil     │    │          │
│          │    │          │    │[Gönder]  │    │[Takip Et]│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

#### Yönetici Onay (Mobil)

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│Push Bild.│───▶│Onay Det. │───▶│ Sonuç    │
│          │    │(Bottom   │    │          │
│"Ali izin │    │ Sheet)   │    │"Onaylan- │
│ talep et"│    │          │    │ dı ✓"    │
│[Aç]      │    │Detaylar  │    │          │
│          │    │Bakiye OK │    │          │
│          │    │[Onayla]  │    │          │
│          │    │[Reddet]  │    │          │
└──────────┘    └──────────┘    └──────────┘
```

#### Mobil Check-in (GPS)

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│Dashboard │───▶│Check-in  │───▶│ Onay     │
│          │    │Buton     │    │          │
│[Giriş    │    │          │    │"Giriş    │
│ Yap]     │    │📍 GPS do-│    │kaydedild"│
│          │    │ğrulanıyor│    │07:58     │
│          │    │[Onayla]  │    │          │
└──────────┘    └──────────┘    └──────────┘
```

---

## 3. PWA ve Native Karar Çerçevesi

| Kriter | PWA | Native / Flutter |
|--------|-----|------------------|
| Hızlı dağıtım | Güçlü | Orta |
| Push bildirim | Sınırlı / platform bağımlı | Güçlü |
| Offline veri | Temel | Güçlü |
| Cihaz entegrasyonu | Sınırlı | Güçlü |
| UX akıcılığı | İyi | Çok iyi |

**Karar:** Web ile birlikte Flutter mobil uygulama hedeflenir. Web responsive deneyim zorunlu kalır; çalışan işlemleri mobil uygulamada optimize edilir.

---

## 4. Responsive Prensipleri

| Kural | Açıklama |
|-------|----------|
| MOB-01 | Kritik işlem kartları fold üstünde görünür |
| MOB-02 | Büyük veri tabloları mobilde kart görünümüne dönüşür |
| MOB-03 | Tek elle kullanım için ana aksiyonlar alt bölgede konumlanır |
| MOB-04 | Dosya yükleme akışları kamera ve dosya seçici ile uyumlu tasarlanır |
| MOB-05 | Minimum dokunma hedefi 44×44px |
| MOB-06 | Swipe gesture'ları: sola kaydır → red, sağa kaydır → onayla (onay kartları) |
| MOB-07 | Pull-to-refresh tüm liste ekranlarında aktif |
| MOB-08 | Bottom sheet modal tercih edilir; full-screen modal yalnızca formlar için |

### 4.1 Gesture Desteği

| Gesture | Kullanım Alanı | Aksiyon |
|---------|----------------|---------|
| Swipe right | Onay kartı | Hızlı onayla |
| Swipe left | Onay kartı | Reddet / detay aç |
| Pull down | Liste ekranları | Yenile |
| Long press | Takvim günü | Hızlı izin talebi |
| Pinch zoom | Organizasyon şeması | Yakınlaştır/uzaklaştır |
| Double tap | Dashboard kart | Kart detay aç |

### 4.2 Mobil Navigasyon

```
┌──────────────────────────┐
│  ┌──────────────────────┐│
│  │   Sayfa İçeriği       ││
│  │                      ││
│  │   (Tam ekran)        ││
│  │                      ││
│  │                      ││
│  └──────────────────────┘│
│                          │
│  ─────────────────────── │
│  ┌────┬────┬────┬────┬──┐│
│  │ 🏠 │ 🏖 │ ➕ │ ✏️ │ 👤││
│  │Ana │İzin│Hızlı│Gör│Pro││
│  │Syf │    │İşlm│ev │fil││
│  └────┴────┴────┴────┴──┘│
│                          │
│  Ortadaki ➕ FAB butonu:  │
│  → İzin talebi           │
│  → Mesai talebi           │
│  → Check-in               │
└──────────────────────────┘
```

---

## 5. Bildirim ve Offline Stratejisi

### 5.1 Push Bildirim Stratejisi

| Bildirim Kategorisi | Öncelik | Ses/Titreşim | Gruplanma |
|---------------------|---------|--------------|-----------|
| İzin onay sonucu | Yüksek | Varsayılan | Hayır |
| Yönetici onay talebi | Yüksek | Varsayılan | İşlem bazlı |
| Vardiya değişikliği | Yüksek | Varsayılan | Hayır |
| Performans görevi | Orta | Sessiz | Hayır |
| Duyuru | Düşük | Sessiz | Günlük özet |
| Bordro pusulası hazır | Orta | Sessiz | Hayır |

**Bildirim Davranışı:**

| Özellik | Uygulama |
|---------|----------|
| Deep linking | Bildirime tıklama → ilgili sayfaya direkt yönlendirme |
| Badge count | Ana ekranda okunmamış görev/bildirim sayısı |
| Bildirim kanalları (Android) | İzin, Performans, Duyuru ayrı kanallar |
| Sessiz saatler | Tenant ayarı: varsayılan 22:00-07:00 arası sessiz |

### 5.2 Offline ve Senkronizasyon Stratejisi

| Senaryo | Offline Davranış | Senkronizasyon |
|---------|------------------|----------------|
| İzin talebi | Taslak (draft) olarak yerel kaydet | Bağlantı geldiğinde otomatik gönder |
| Check-in | Yerel kaydet + GPS snapshot | İlk bağlantıda senkronize |
| Takvim görüntüleme | Önbellekten göster | Arka planda güncelle |
| Duyuru okuma | Önbellekten göster | Otomatik güncelle |
| Onay işlemi | Offline'da yapılamaz; uyarı göster | — |
| Form doldurma | Taslak yerel kaydet | Otomatik senkronize |

**Senkronizasyon Göstergesi:**

```
┌──────────────────────────┐
│  ⚠️ Çevrimdışı moddasınız│
│  Son güncelleme: 14:30   │
│  [Yenile]                │
└──────────────────────────┘
```

**Veri Önbellek Stratejisi:**

| Veri | Cache Süresi | Strateji |
|------|--------------|----------|
| Dashboard kartları | 15 dakika | Stale-while-revalidate |
| Takvim verileri | 1 saat | Cache-first, background update |
| Profil bilgileri | 24 saat | Cache-first |
| Duyurular | 30 dakika | Network-first, fallback to cache |

---

## 6. Flutter Mobil Uygulama Mimarisi

### 6.1 Mimari Yaklaşım

| Katman | Teknoloji/Yaklaşım |
|--------|---------------------|
| State Management | Riverpod veya BLoC |
| API İletişimi | Dio + Retrofit |
| Yerel Depolama | Hive veya drift (SQLite) |
| Push Bildirim | Firebase Cloud Messaging (FCM) |
| GPS | geolocator paketi |
| Biyometrik Auth | local_auth paketi |
| Deep Linking | go_router |

### 6.2 Ekran Listesi (Mobil)

| # | Ekran | Öncelik |
|---|-------|---------|
| 1 | Login / SSO / biyometrik giriş | P1 |
| 2 | Çalışan dashboard | P1 |
| 3 | İzin talebi formu (bottom sheet) | P1 |
| 4 | İzin listesi / takip | P1 |
| 5 | Yönetici onay listesi | P1 |
| 6 | Bildirim merkezi | P1 |
| 7 | Vardiya takvimi | P2 |
| 8 | Mobil check-in (GPS) | P2 |
| 9 | Bordro pusulası görüntüleme | P2 |
| 10 | Performans hedef/değerlendirme | P2 |
| 11 | Profil ekranı | P2 |
| 12 | Duyurular listesi | P3 |
| 13 | Şirket rehberi / organigram | P3 |
| 14 | Eğitim atamalarım | P3 |

---

## 7. Mobil Başarı Metrikleri

| Metrik | Hedef |
|--------|-------|
| İzin talebi tamamlama süresi | < 60 saniye |
| Yönetici onay süresi (bildirimden) | < 30 saniye |
| Mobil check-in süresi | < 10 saniye |
| Uygulama cold start | < 3 saniye |
| Mobil crash-free oranı | > %99.5 |
| Push tıklama oranı (CTR) | > %35 |
| Offline → online senkronizasyon başarısı | > %99 |
| App Store puanı hedefi | > 4.5 |

---

## 8. Test Stratejisi (Mobil)

| Test Tipi | Araç | Kapsam |
|-----------|------|--------|
| Widget testi | Flutter test | Tüm bileşenler |
| Entegrasyon testi | Integration test | Kritik akışlar (izin, onay) |
| E2E | Appium / Patrol | Gerçek cihazda tam akış |
| Performans | Flutter DevTools | FPS, memory, startup time |
| Erişilebilirlik | TalkBack / VoiceOver testi | Tüm P1 ekranlar |

---

## 9. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | iOS minimum versiyon: 15.0; Android minimum API: 26 (Android 8.0) |
| K2 | GPS doğrulama yalnızca mobil check-in için kullanılır; tenant bazında devre dışı bırakılabilir |
| K3 | Offline modda yalnızca okuma ve taslak kaydetme desteklenir; onay işlemleri çevrimiçi gerektirir |
| V1 | Flutter single codebase ile iOS + Android desteklenir |
| V2 | FCM ile push bildirim altyapısı kullanılır |
| V3 | Biyometrik kimlik doğrulama opsiyoneldir; tenant ayarı ile açılır |
