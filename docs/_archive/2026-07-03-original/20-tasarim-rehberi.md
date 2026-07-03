# 20 — Tasarım Rehberi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Tasarım prensipleri, renk sistemi, tipografi, spacing, ikonografi, durum renkleri, bileşen kütüphanesi yaklaşımı, erişilebilirlik ve responsive temel kararları  
> **Faz:** Faz 4

---

## 1. Tasarım İlkeleri

| İlke | Açıklama |
|------|----------|
| Açıklık | İK işlemleri karmaşık olabilir; arayüz daima bir sonraki adımı net göstermeli |
| Güven | Bordro, izin ve performans gibi hassas veriler için kurumsal ve güvenilir görsel dil korunmalı |
| Hız | Sık kullanılan akışlar minimum adımda tamamlanmalı |
| Tutarlılık | Web ve mobilde ortak bileşen dili kullanılmalı |
| Erişilebilirlik | WCAG AA seviyesine yakın kontrast ve odak görünürlüğü sağlanmalı |

---

## 2. Görsel Yön

Ürün görsel dili kurumsal fakat steril olmayan bir çizgide konumlanır. Ana yaklaşım; açık zemin, güçlü bilgi hiyerarşisi, belirgin kart yapıları, statü renklerinde netlik ve yönetici ekranlarında yoğun veri için dengeli tablo/kart karmasıdır.

### 2.1 Renk Sistemi

#### Light Mode (Varsayılan)

| Token | Değer | Kullanım |
|-------|-------|----------|
| `--color-primary` | `#0F4C81` | Ana aksiyon, link, aktif durum |
| `--color-primary-strong` | `#0A365B` | Hover, vurgulu başlık |
| `--color-primary-light` | `#E8F0FE` | Seçili satır, aktif kart zemin |
| `--color-accent` | `#E3A008` | Uyarı, ikincil vurgu |
| `--color-accent-light` | `#FFF8E1` | Uyarı kart zemini |
| `--color-success` | `#1F8A5B` | Başarılı durum |
| `--color-success-light` | `#E6F5ED` | Başarı kart zemini |
| `--color-danger` | `#C2412D` | Hata, iptal, kritik risk |
| `--color-danger-light` | `#FDECEB` | Hata kart zemini |
| `--color-info` | `#2563EB` | Bilgilendirme |
| `--color-info-light` | `#EFF6FF` | Bilgi kart zemini |
| `--color-bg` | `#F6F8FB` | Sayfa zemini |
| `--color-surface` | `#FFFFFF` | Kart ve panel yüzeyi |
| `--color-border` | `#D9E1EC` | Ayraç ve input border |
| `--color-text` | `#1B2430` | Ana metin |
| `--color-text-muted` | `#627184` | İkincil metin |
| `--color-text-disabled` | `#A0AEC0` | Devre dışı metin |

#### Dark Mode

| Token | Değer | Kullanım |
|-------|-------|----------|
| `--color-bg` | `#0F1419` | Sayfa zemini |
| `--color-surface` | `#1A2332` | Kart yüzeyi |
| `--color-surface-elevated` | `#243044` | Modal, dropdown |
| `--color-border` | `#2D3F56` | Ayraçlar |
| `--color-text` | `#E2E8F0` | Ana metin |
| `--color-text-muted` | `#8B9DB5` | İkincil metin |
| `--color-primary` | `#4A9FE5` | Daha açık primary (kontrast) |
| `--color-success` | `#34D399` | Daha açık başarı rengi |
| `--color-danger` | `#F87171` | Daha açık hata rengi |

**Geçiş:** `prefers-color-scheme` media query ve kullanıcı tercihi (localStorage). Tenant ayarı dark mode'u kapatabilir.

### 2.2 Tipografi

| Katman | Stil |
|--------|------|
| Başlık | `Manrope` veya `Plus Jakarta Sans`, 600-700 |
| Gövde | `Source Sans 3`, 400-600 |
| Sayısal veri | `IBM Plex Sans` veya tablo içinde tabular numerals |

### 2.3 Spacing ve Radius

| Token | Değer |
|-------|-------|
| `space-1` | 4px |
| `space-2` | 8px |
| `space-3` | 12px |
| `space-4` | 16px |
| `space-6` | 24px |
| `space-8` | 32px |
| `radius-sm` | 8px |
| `radius-md` | 12px |
| `radius-lg` | 18px |

---

## 3. Bileşen Kütüphanesi Yaklaşımı

| Bileşen | Açıklama |
|---------|----------|
| App shell | Sol menü + üst bar + içerik alanı |
| Kartlar | Dashboard, özet, liste kartları |
| Data table | Filtre, sıralama, kolon seçimi, export |
| Form alanları | Text, select, date, file upload, stepper |
| Statü bileşenleri | Badge, alert, timeline, progress bar |
| Akış bileşenleri | Onay adımı, görev kartı, activity feed |

### 3.1 Durum Tasarımı

| Durum | Görsel Yaklaşım |
|-------|-----------------|
| Başarılı | Yeşil badge + hafif yeşil yüzey (`--color-success-light`) |
| Beklemede | Sarı/amber badge + saat ikonu (`--color-accent-light`) |
| Reddedildi / kritik | Kırmızı badge + net uyarı alanı (`--color-danger-light`) |
| Bilgilendirme | Mavi tonlu çağrı kartı (`--color-info-light`) |
| Devre dışı | Gri badge + soluk metin (`--color-text-disabled`) |
| Devam ediyor | Primary badge + animasyonlu progress |

### 3.2 İkon Kütüphanesi

| Kategori | Kütüphane/Yaklaşım |
|----------|---------------------|
| Genel UI | [Lucide Icons](https://lucide.dev/) (MIT, tree-shakeable) |
| Modül ikonu | Özel SVG set (HR spesifik: izin, bordro, performans) |
| Bayrak | `flag-icons` paketi (ülke seçimi için) |
| Dosya tipi | MIME tip bazlı ikon eşlemesi |

**İkon Boyutları:**

| Token | Boyut | Kullanım |
|-------|-------|----------|
| `icon-xs` | 14px | Tablo içi, badge yanı |
| `icon-sm` | 18px | Form alanı, inline |
| `icon-md` | 22px | Buton, menü |
| `icon-lg` | 28px | Kart başlığı |
| `icon-xl` | 40px | Empty state, hero |

### 3.3 Animasyon ve Geçişler

| Animasyon | Detay | Süre |
|-----------|-------|------|
| Sayfa geçişi | Fade-in + slide-up | 200ms ease-out |
| Modal açılış | Fade + scale (0.95→1) | 150ms ease-out |
| Dropdown | Fade + slide-down | 150ms ease-out |
| Toast notification | Slide-in sağdan | 300ms ease-out |
| Skeleton loader | Shimmer efekti | Sürekli (veri gelene kadar) |
| Buton hover | Background-color transition | 100ms |
| Tab değişimi | Crossfade | 200ms |

**Prefers-reduced-motion:** `motion-safe:` prefix; azaltılmış hareket modu desteklenir.

### 3.4 Empty States (Boş Durumlar)

| Durum | Görsel Yaklaşım |
|-------|-----------------|
| İlk kullanım (onboarding) | İllüstrasyon + açıklama + CTA buton |
| Arama sonuç yok | Arama ikonu + "Sonuç bulunamadı" + filtre temizle |
| Veri yok | Hafif gri ikon + "Henüz kayıt yok" + oluşturma linki |
| Hata durumu | Hata ikonu + teknik olmayan mesaj + tekrar dene butonu |
| İzinsiz erişim | Kilit ikonu + "Bu alana erişim yetkiniz yok" |

```
┌─────────────────────────────────────────┐
│                                         │
│         🗂️  (Açık tonu ikon)            │
│                                         │
│     Henüz izin talebi oluşturmadınız    │
│                                         │
│     İlk izin talebinizi oluşturmak      │
│     için aşağıdaki butonu kullanın.     │
│                                         │
│         [+ İzin Talep Et]               │
│                                         │
└─────────────────────────────────────────┘
```

---

## 4. Responsive Temeller

| Breakpoint | Token | Kullanım |
|------------|-------|----------|
| `0-639px` | `mobile` | Mobil tek kolon, bottom nav, tam genişlik kartlar |
| `640-1023px` | `tablet` | Tablet / dar laptop, hibrit iki kolon, sidebar collapse |
| `1024-1439px` | `desktop` | Standart desktop, sidebar açık, 2-3 kolon grid |
| `1440px+` | `wide` | Geniş dashboard, 3-4 kolon, yoğun veri tabloları |

### 4.1 Layout Grid

| Breakpoint | Kolon | Gutter | Margin |
|------------|-------|--------|--------|
| Mobile | 4 | 16px | 16px |
| Tablet | 8 | 20px | 24px |
| Desktop | 12 | 24px | 32px |
| Wide | 12 | 24px | 48px |

### 4.2 Responsive Davranışlar

| Bileşen | Mobile | Tablet | Desktop |
|---------|--------|--------|---------|
| Sidebar menü | Bottom tab bar | Hamburger ile collapse | Her zaman açık |
| Data table | Kart görünümüne dönüşür | Yatay scroll + sabitlenmiş ilk kolon | Tam tablo |
| Dashboard kartları | Tek kolon, dikey stack | 2 kolon grid | 3-4 kolon grid |
| Modal/Dialog | Full-screen bottom sheet | Merkez modal (60% genişlik) | Merkez modal (40% genişlik) |
| Form alanları | Tam genişlik | 2 kolon form | 2-3 kolon form |
| Takvim görünümü | Gün/liste | Hafta | Ay |

---

## 5. Erişilebilirlik Gereksinimleri

| Kural | Hedef | Açıklama |
|-------|-------|----------|
| ERS-01 | WCAG 2.1 AA | Metin-kontrast en az 4.5:1 (normal metin), 3:1 (büyük metin) |
| ERS-02 | Odak göstergesi | Tüm interaktif öğelerde 2px solid primary focus ring |
| ERS-03 | Hata iletimi | Form hata mesajları yalnızca renkle değil ikon + metinle belirtilir |
| ERS-04 | Tablo erişimi | Tablolar mobilde kart görünümüne dönüşebilir; `aria-label` mevcut |
| ERS-05 | Klavye navigasyonu | Tab sırası mantıklı; escape ile modal kapanır; enter ile submit |
| ERS-06 | Screen reader | Tüm form elemanlarında `label`, görsellerde `alt`, dinamik içerikte `aria-live` |
| ERS-07 | Renk bağımsızlığı | Durum bilgisi yalnızca renkle değil ikon veya metin ile de iletilir |
| ERS-08 | Dokunma hedefi | Mobilde minimum 44×44px dokunma alanı |
| ERS-09 | Metin boyutlandırma | `rem` birim kullanımı; tarayıcı font-size ayarına saygı |

### 5.1 Erişilebilirlik Test Araçları

| Araç | Kullanım |
|------|----------|
| axe DevTools | Otomatik erişilebilirlik taraması (CI/CD entegre) |
| Lighthouse | Genel erişilebilirlik puanı (hedef: 90+) |
| NVDA / VoiceOver | Manuel screen reader testi |
| Contrast checker | Renk kontrastı doğrulaması |

---

## 6. Tasarım Token Yönetimi

| Konu | Uygulama |
|------|----------|
| Token formatı | CSS Custom Properties (`:root` seviyesi) |
| Dark mode geçişi | `[data-theme="dark"]` selector ile override |
| Tenant özelleştirme | Tenant renkleri runtime'da CSS variable override |
| Bileşen kütüphanesi | Tailwind CSS utility classes + custom component layer |
| Figma ↔ Kod senkronu | Figma tokens plugin → JSON → CSS variables build pipeline |

---

## 7. Tasarım Sisteminde Öncelikli Sayfalar

| # | Sayfa | Modül | Öncelik |
|---|-------|-------|---------|
| 1 | Self-servis ana sayfa (çalışan + yönetici) | Portal | Yüksek |
| 2 | İzin talebi akışı (form + takvim) | İzin | Yüksek |
| 3 | Personel kartı (profil detay) | Personel | Yüksek |
| 4 | Yönetici onay paneli | Portal | Yüksek |
| 5 | Aylık vardiya planlama (sürükle-bırak) | Vardiya | Yüksek |
| 6 | Performans değerlendirme formu | Performans | Yüksek |
| 7 | Bordro pusulası ve bordro operasyon | Bordro | Orta |
| 8 | Executive dashboard | Raporlama | Orta |
| 9 | Organizasyon şeması (interaktif) | Organizasyon | Orta |
| 10 | İşe alım pipeline (Kanban) | İşe Alım | Orta |
| 11 | Eğitim kataloğu ve atama | Eğitim | Düşük |
| 12 | Özel rapor oluşturucu | Raporlama | Düşük |

---

## 8. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | Dark mode Faz 4'te devreye alınır; light mode MVP'de varsayılan |
| K2 | Tenant renk özelleştirmesi primary ve accent ile sınırlı |
| V1 | Tüm ikon ve illüstrasyonlar SVG formatında, tree-shakeable |
| V2 | Bileşen kütüphanesi Storybook ile belgelenir |
| V3 | RTL (sağdan sola) yazı desteği kapsam dışıdır |
