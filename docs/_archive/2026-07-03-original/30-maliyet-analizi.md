# 30 — Maliyet Analizi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Geliştirme maliyeti, altyapı maliyeti, lisans/servis maliyetleri, insan kaynağı ihtiyacı ve maliyet riskleri  
> **Faz:** Faz 7

---

## 1. Maliyet Kategorileri

| Kategori | İçerik | Oran (tahmini) |
|----------|--------|----------------|
| İnsan kaynağı | Yazılım geliştirme, ürün, tasarım, QA, DevOps | %65-70 |
| Altyapı | Sunucu, veritabanı, storage, CDN, izleme | %15-20 |
| 3. parti servisler | E-posta, SMS, push, hata takibi, CI/CD | %5-8 |
| Uyum ve güvenlik | Pentest, KVKK danışmanlık, sertifikasyon | %3-5 |
| Eğitim ve lansman | Kullanıcı eğitimi, veri göçü, pilot | %3-5 |

---

## 2. Ekip Yapısı ve İnsan Kaynağı Maliyeti

### 2.1 Ekip Kadrosu

| Rol | Adet | Dahil Olduğu Fazlar | Aylık Maliyet (TL, brüt) | Not |
|-----|------|---------------------|---------------------------|-----|
| Kıdemli Backend Geliştirici | 2 | Faz 1-7 (12 ay) | 80.000 – 120.000 | Django/FastAPI, full-time |
| Kıdemli Frontend Geliştirici | 2 | Faz 1-7 (12 ay) | 75.000 – 110.000 | Next.js/React, full-time |
| Mobil Geliştirici (Flutter) | 1 | Faz 4-7 (6 ay) | 70.000 – 100.000 | Part-time → full-time |
| UI/UX Tasarımcı | 1 | Faz 1-4 (8 ay) | 55.000 – 80.000 | İlk 4 faz full, sonra part-time |
| QA Mühendisi | 1 | Faz 2-7 (10 ay) | 55.000 – 80.000 | E2E + performans test |
| DevOps / Altyapı | 1 | Faz 1-7 (12 ay) | 75.000 – 110.000 | Part-time ilk 6 ay, full sonra |
| Ürün Yöneticisi / Analist | 1 | Faz 1-7 (12 ay) | 65.000 – 95.000 | Full-time |
| Proje Yöneticisi | 0.5 | Faz 1-7 (12 ay) | 35.000 – 50.000 | Part-time |

### 2.2 İnsan Kaynağı Maliyet Özeti

| Dönem | Aktif Kişi | Aylık Toplam (TL) | Süre | Dönem Toplamı (TL) |
|-------|------------|--------------------| -----|---------------------|
| Faz 1-2 (Ay 1-4) | 7-8 | 500.000 – 750.000 | 4 ay | 2.000.000 – 3.000.000 |
| Faz 3-4 (Ay 5-9) | 8-9 | 580.000 – 850.000 | 5 ay | 2.900.000 – 4.250.000 |
| Faz 5-7 (Ay 10-12) | 7-8 | 500.000 – 750.000 | 3 ay | 1.500.000 – 2.250.000 |
| **12 Ay Toplam** | | | | **6.400.000 – 9.500.000** |

> **Not:** Maliyet aralıkları İstanbul piyasa koşullarına göre (2026 Q1-Q2) tahmin edilmiştir. Uzaktan çalışma modelinde %10-15 düşüş mümkün.

---

## 3. Altyapı Maliyetleri

### 3.1 Geliştirme ve Staging Ortamı

| Kalem | Spesifikasyon | Aylık Maliyet (USD) |
|-------|---------------|---------------------|
| Dev sunucu (VM/VPS) | 4 vCPU, 8 GB RAM | $40 – $60 |
| Staging sunucu (VM) | 4 vCPU, 8 GB RAM | $40 – $60 |
| Dev/Staging DB | PostgreSQL (shared) | dahil |
| Object storage (dev) | 50 GB | $2 – $5 |
| **Dev+Staging Toplam** | | **$80 – $125/ay** |

### 3.2 Production Ortamı

| Kalem | Spesifikasyon | Aylık Maliyet (USD) |
|-------|---------------|---------------------|
| App sunucu(lar) | 2× (4 vCPU, 8 GB RAM) | $160 – $240 |
| PostgreSQL (managed HA) | 4 vCPU, 16 GB RAM, 200 GB SSD | $200 – $400 |
| Redis (managed Sentinel) | 3× 2 GB | $60 – $120 |
| MinIO / Object Storage | 500 GB (başlangıç) | $15 – $30 |
| CDN / WAF | CloudFlare Pro | $25 |
| Monitoring (Grafana Cloud veya self-hosted) | Self-hosted | $0 – $50 |
| Log yönetimi (Loki / ELK) | Self-hosted | $0 – $50 |
| Yedekleme storage | 1 TB (cross-region) | $25 – $50 |
| SSL sertifika | Let's Encrypt veya managed | $0 – $10 |
| Domain | 1 domain + wildcard | $15/yıl |
| **Production Toplam** | | **$485 – $975/ay** |

### 3.3 Ölçekleme Maliyet Projeksiyonu

| Kullanıcı Sayısı | Tenant | Ek Altyapı İhtiyacı | Tahmini Aylık (USD) |
|-------------------|--------|----------------------|---------------------|
| 100-500 | 1-3 | Başlangıç konfigürasyonu | $485 – $700 |
| 500-2.000 | 3-10 | +1 app replika, DB scale-up | $700 – $1.200 |
| 2.000-5.000 | 10-25 | Read replica, Redis cluster | $1.200 – $2.000 |
| 5.000-10.000 | 25-50 | Kubernetes geçişi, auto-scale | $2.000 – $4.000 |

---

## 4. 3. Parti Servis Maliyetleri

| Servis | Sağlayıcı | Fiyat Modeli | Aylık Tahmini (USD) |
|--------|-----------|-------------|---------------------|
| E-posta (transactional) | Amazon SES / Resend | $0.10 / 1000 e-posta | $10 – $50 |
| SMS | NetGSM / İleti Merkezi | ₺0.15-0.25 / SMS | ₺500 – ₺2.000 |
| Push notification | Firebase (FCM) | Ücretsiz (1M/ay) | $0 |
| Hata takibi | Sentry (self-hosted) | Self-hosted | $0 |
| CI/CD | GitHub Actions | 3.000 dk/ay (ücretsiz) → $40/ay | $0 – $40 |
| Container registry | GitHub Packages | 500 MB ücretsiz → $0.25/GB | $0 – $10 |
| Kod kalitesi | Codecov | Ücretsiz (public) → $10/ay | $0 – $10 |
| Güvenlik tarama | Snyk (ücretsiz tier) | 200 test/ay ücretsiz | $0 – $50 |
| **Toplam** | | | **$20 – $200/ay** |

---

## 5. Uyum ve Güvenlik Maliyetleri

| Kalem | Sıklık | Tahmini Maliyet |
|-------|--------|-----------------|
| Penetrasyon testi (dış firma) | 6 aylık | ₺50.000 – ₺150.000 / test |
| KVKK danışmanlık | Proje başında + yıllık | ₺30.000 – ₺80.000/yıl |
| VERBİS kayıt desteği | Bir kerelik | ₺10.000 – ₺20.000 |
| SSL / sertifika yönetimi | Yıllık | $0 – $200/yıl |
| Güvenlik eğitimi | Yıllık | ₺10.000 – ₺30.000 |
| **Yıllık Toplam** | | **₺150.000 – ₺430.000** |

---

## 6. Lansman ve Eğitim Maliyetleri

| Kalem | Tahmini Maliyet |
|-------|-----------------|
| Pilot kurulum ve veri migrasyonu | ₺50.000 – ₺100.000 |
| Admin eğitimi (İK ekibi) | ₺20.000 – ₺40.000 |
| Çalışan eğitimi (video + dokümantasyon) | ₺30.000 – ₺60.000 |
| Kullanıcı kılavuzları ve help center | ₺15.000 – ₺30.000 |
| **Toplam** | **₺115.000 – ₺230.000** |

---

## 7. Toplam Proje Maliyet Özeti (12 Ay)

| Kalem | Minimum (TL) | Maksimum (TL) |
|-------|:------------:|:-------------:|
| İnsan kaynağı (geliştirme) | 6.400.000 | 9.500.000 |
| Altyapı (12 ay) | 200.000 | 420.000 |
| 3. parti servisler (12 ay) | 8.000 | 80.000 |
| Uyum ve güvenlik | 150.000 | 430.000 |
| Lansman ve eğitim | 115.000 | 230.000 |
| **TOPLAM** | **6.873.000** | **10.660.000** |

> **Yaklaşık USD karşılığı:** $180.000 – $280.000 (1 USD ≈ 38 TL tahmini)

---

## 8. Aylık İşletme Maliyeti (Go-Live Sonrası)

| Kalem | Aylık (TL) |
|-------|------------|
| Altyapı (prod + monitoring) | 20.000 – 40.000 |
| 3. parti servisler | 1.500 – 8.000 |
| DevOps / bakım (1 kişi part-time) | 35.000 – 55.000 |
| Destek (1 kişi) | 30.000 – 45.000 |
| Güvenlik (amortisman) | 12.000 – 35.000 |
| **Aylık Toplam** | **98.500 – 183.000** |
| **Yıllık İşletme** | **1.182.000 – 2.196.000** |

---

## 9. ROI ve Geri Dönüş Analizi

### 9.1 Mevcut Manuel Süreç Maliyeti (Yıllık Tasarruf Potansiyeli)

| Alan | Manuel Süre | Otomatik Süre | Tasarruf | Yıllık TL Karşılığı |
|------|-------------|---------------|----------|---------------------|
| İzin yönetimi | 4 saat/hafta × İK | 0.5 saat/hafta | %87 | ~50.000 |
| Bordro hazırlama | 5 gün/ay | 1 gün/ay | %80 | ~120.000 |
| Personel dosyası yönetimi | 3 saat/hafta | 0.5 saat/hafta | %83 | ~40.000 |
| Performans takibi | 2 hafta/yıl (İK) | 2 gün/yıl | %80 | ~30.000 |
| Raporlama | 1 gün/hafta | Otomatik | %95 | ~80.000 |
| İşe alım süreci | 1 hafta / pozisyon | 2 gün / pozisyon | %60 | ~60.000 |
| **Yıllık Toplam Tasarruf** | | | | **~380.000** |

### 9.2 Ek Faydalar (Dolaylı)

| Fayda | Tahmini Yıllık Değer |
|-------|---------------------|
| Hata azalması (bordro, SGK) | ₺50.000 – ₺150.000 |
| Çalışan memnuniyeti → düşük işten ayrılma | ₺100.000 – ₺300.000 |
| KVKK uyum (ceza riski azaltma) | ₺200.000+ (potansiyel ceza) |
| Karar hızı (anlık raporlama) | Ölçülemez |

### 9.3 Geri Dönüş Süresi (Payback Period)

| Senaryo | Yıllık Tasarruf | Proje Maliyeti | Payback |
|---------|-----------------|----------------|---------|
| Muhafazakâr (500 çalışan) | ₺500.000 | ₺8.000.000 | ~16 ay |
| Orta (1.000 çalışan) | ₺900.000 | ₺8.000.000 | ~9 ay |
| İyimser (2.000+ çalışan, çok tenant) | ₺1.500.000+ | ₺8.000.000 | ~5 ay |

---

## 10. Maliyet Riskleri ve Mitigation

| Risk | Olasılık | Etki | Mitigation |
|------|----------|------|------------|
| Bordro mevzuat karmaşıklığı | Yüksek | +%15-20 geliştirme süresi | Erken muhasebeci dahil, parametrize kurallar |
| Entegrasyon sayısı artışı | Orta | +%10 bakım maliyeti | Adaptör pattern, sınırlı MVP entegrasyon |
| Döviz kuru dalgalanması (altyapı) | Orta | Altyapı maliyeti artışı | 6 aylık peşin ödeme, reserved instance |
| Ekip dönüşümü | Düşük | +%20 süre | Çapraz eğitim, dokümantasyon |
| Özelleştirme talep yığılması | Orta | Kapsam kayması | MVP disiplini, change request prosedürü |

---

## 11. SaaS Fiyatlandırma Modeli (Çok Tenantlı Senaryo)

| Plan | Çalışan Sayısı | Aylık Fiyat / Çalışan | Özellikler |
|------|----------------|------------------------|------------|
| Starter | 1-50 | ₺25 / çalışan | Personel, İzin, Self-servis |
| Professional | 51-500 | ₺20 / çalışan | + Performans, İşe Alım, Eğitim |
| Enterprise | 500+ | ₺15 / çalışan | + Bordro, Vardiya, API, SLA |
| Kurumsal (on-premise) | Özel | Proje bazlı | Tam lisans + kurulum |

**Break-even hesabı (SaaS modeli):**
- Aylık işletme: ₺150.000
- Ortalama çalışan başı gelir: ₺20
- Break-even: 7.500 aktif çalışan (birden çok tenant toplam)
