# İnsan Kaynakları Yönetim Sistemi — Yol Haritası

> **Hedef Kitle:** Tüm ölçeklerdeki işletmeler (modüler yapı)  
> **Platform:** Web (Full Responsive) + Mobil Uyumlu  
> **Mobil Kapsam:** Tüm modüller responsive; izin, bildirim, vardiya, performans ve personel bilgileri mobilde öncelikli  

---

## Faz 1 — Analiz & Araştırma

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 1 | `01-piyasa-arastirmasi.md` | Türkiye ve global İK yazılım pazarı, trendler, pazar büyüklüğü |
| 2 | `02-rakip-analizi.md` | Yerli ve yabancı rakiplerin özellik karşılaştırması (SAP SuccessFactors, Workday, Kolay İK, Pürlen, Bordro+, vb.) |
| 3 | `03-hedef-kitle-ve-kullanici-personalar.md` | Kullanıcı segmentleri, persona tanımları, kullanıcı hikayeleri |
| 4 | `04-gereksinim-analizi.md` | Fonksiyonel ve fonksiyonel olmayan gereksinimler, MoSCoW önceliklendirme |

## Faz 2 — Teknoloji & Mimari Kararlar

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 5 | `05-teknoloji-secimi.md` | Frontend, backend, veritabanı, altyapı teknoloji stack'i karşılaştırması ve seçimi |
| 6 | `06-sistem-mimarisi.md` | Genel mimari diyagram, servis yapısı (monolith / microservice), katman mimarisi |
| 7 | `07-veritabani-tasarimi.md` | ER diyagramları, tablo yapıları, ilişkiler, indeksleme stratejisi |
| 8 | `08-api-tasarimi.md` | REST/GraphQL API tasarım prensipleri, endpoint listesi, versiyonlama |
| 9 | `09-entegrasyon-haritasi.md` | 3. parti entegrasyonlar (SGK, e-Devlet, banka, e-posta, SMS, LDAP/AD, muhasebe yazılımları) |

## Faz 3 — Modül Dökümanları

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 10 | `10-modul-personel-yonetimi.md` | Çalışan kayıtları, özlük dosyaları, iş sözleşmeleri, işe giriş/çıkış süreçleri |
| 11 | `11-modul-ise-alim-ats.md` | İlan yönetimi, başvuru takibi, mülakat planlama, teklif süreci, aday havuzu |
| 12 | `12-modul-izin-devamsizlik.md` | İzin türleri, talep/onay akışları, kota yönetimi, devamsızlık takibi |
| 13 | `13-modul-performans-yonetimi.md` | Hedef belirleme (OKR/KPI), değerlendirme dönemleri, 360° feedback, yetkinlik matrisi |
| 14 | `14-modul-bordro-maas.md` | Maaş hesaplama, yasal kesintiler (SGK, gelir vergisi, damga), AGİ, fazla mesai, prim, ikramiye |
| 15 | `15-modul-egitim-gelisim.md` | Eğitim planları, online/offline eğitim takibi, sertifika yönetimi, kariyer yol haritası |
| 16 | `16-modul-vardiya-mesai.md` | Vardiya tanımlama, çalışma takvimi, fazla mesai hesaplama, PDKS entegrasyonu |
| 17 | `17-modul-organizasyon-semasi.md` | Şirket hiyerarşisi, departman yapısı, pozisyon yönetimi, kadro planlaması |
| 18 | `18-modul-raporlama-analitik.md` | Dashboard tasarımı, İK metrikleri, özel rapor oluşturma, veri görselleştirme |
| 19 | `19-modul-self-servis-portal.md` | Çalışan portalı, yönetici portalı, talep yönetimi, duyuru sistemi |

## Faz 4 — UI/UX & Tasarım

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 20 | `20-tasarim-rehberi.md` | Renk paleti, tipografi, ikon seti, bileşen kütüphanesi (design system) |
| 21 | `21-sayfa-akislari-wireframe.md` | Ekran listesi, kullanıcı akışları, wireframe referansları |
| 22 | `22-mobil-tasarim-stratejisi.md` | Responsive breakpoint'ler, mobil öncelikli özellikler, PWA/native karar analizi |

## Faz 5 — Güvenlik, Uyumluluk & Yetkilendirme

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 23 | `23-kvkk-gdpr-uyumluluk.md` | Kişisel veri koruma, açık rıza yönetimi, veri saklama/silme politikaları |
| 24 | `24-guvenlik-politikalari.md` | Kimlik doğrulama (SSO, MFA), şifreleme, güvenlik açığı yönetimi, OWASP |
| 25 | `25-yetkilendirme-rol-yonetimi.md` | Rol bazlı erişim kontrolü (RBAC), izin matrisi, multi-tenant yetkilendirme |

## Faz 6 — DevOps, Test & Deployment

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 26 | `26-altyapi-ve-deployment.md` | Sunucu mimarisi, container (Docker/K8s), cloud/on-premise seçenekleri |
| 27 | `27-ci-cd-pipeline.md` | Build, test, deploy otomasyonu, ortam yönetimi (dev/staging/prod) |
| 28 | `28-test-stratejisi.md` | Birim test, entegrasyon test, E2E test, performans test, test coverage hedefleri |

## Faz 7 — Proje Yönetimi & Lansman

| # | Dosya Adı | Açıklama |
|---|-----------|----------|
| 29 | `29-sprint-plani-ve-takvim.md` | Sprint bazlı geliştirme planı, milestone'lar, MVP kapsamı, fazlara ayırma |
| 30 | `30-maliyet-analizi.md` | Geliştirme maliyeti, altyapı maliyeti, lisanslama, insan kaynağı planlaması |
| 31 | `31-lansman-ve-gecis-plani.md` | Veri göçü, kullanıcı eğitimi, pilot uygulama, aşamalı geçiş stratejisi |

---

## Çalışma Sırası

```
Faz 1 ──► Faz 2 ──► Faz 3 ──► Faz 4 ──► Faz 5 ──► Faz 6 ──► Faz 7
Analiz    Mimari    Modüller   Tasarım   Güvenlik  DevOps    Lansman
```

- **Faz 1-2** tamamlanmadan Faz 3'e geçilmez (teknoloji kararları modül tasarımını etkiler).
- **Faz 3 ve Faz 4** paralel yürütülebilir.
- **Faz 5** tüm modüllerle iç içe geçecek, ama ayrı dokümante edilecek.
- **MVP Hedefi:** Personel Yönetimi + İzin + Self-Servis Portal ile ilk çıkış.

---

> **Toplam:** 31 adet detaylı MD dosyası  
> **İlk adım:** `01-piyasa-arastirmasi.md` ile başlayacağız.
