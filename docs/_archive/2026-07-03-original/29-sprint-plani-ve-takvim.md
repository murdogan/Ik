# 29 — Sprint Planı & Takvim

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Faz bazlı teslim planı, sprint yapısı, milestone'lar, MVP ve sonraki sürüm kırılımı, ekip ritmi ve bağımlılık yönetimi  
> **Faz:** Faz 7

---

## 1. Planlama Varsayımları

| Parametre | Değer |
|-----------|-------|
| Sprint süresi | 2 hafta (10 iş günü) |
| Ekip büyüklüğü | 5-6 kişi (2 backend, 2 frontend, 1 full-stack/DevOps, 1 QA) |
| Sprint velocity (hedef) | 40-50 story point / sprint |
| Story point ölçeği | Fibonacci (1, 2, 3, 5, 8, 13) |
| Buffer | Her sprint'te %15 buffer (teknik borç, bug fix) |
| Faz 1-2 durumu | Analiz ve mimari dokümanları tamamlanmış |
| Geliştirme başlangıcı | Sprint 1 = Proje iskeleti |

---

## 2. Yüksek Seviye Takvim ve Faz Planı

### 2.1 Faz Detay Tablosu

| Faz | Sprint | Süre | Modüller | Çıktı |
|-----|--------|------|----------|-------|
| **Faz 1 — Temel Altyapı** | S1-S2 | 4 hafta | Auth, Tenant, DB altyapı | Çalışan proje iskeleti |
| **Faz 2 — MVP Core** | S3-S8 | 12 hafta | Personel, İzin, Self-servis | **MVP Release** |
| **Faz 3 — İK Operasyon** | S9-S13 | 10 hafta | İşe Alım, Performans, Organizasyon | İK genişletme |
| **Faz 4 — Gelişmiş Modüller** | S14-S18 | 10 hafta | Eğitim, Raporlama, Bordro, Vardiya | Tam platform |
| **Faz 5 — Güvenlik & Uyum** | S19-S20 | 4 hafta | KVKK, güvenlik sertleştirme, yetki | Uyumluluk |
| **Faz 6 — DevOps & QA** | S21-S22 | 4 hafta | CI/CD, monitoring, performans testi | Prod hazırlık |
| **Faz 7 — Lansman** | S23-S24 | 4 hafta | Pilot, geçiş, eğitim, go-live | **Canlıya Geçiş** |

**Toplam:** ~48 hafta (~12 ay)

### 2.2 Gantt Zaman Çizelgesi

```
Ay:   1     2     3     4     5     6     7     8     9    10    11    12
     ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
Faz1 ████
Faz2      ████████████████
Faz3                        ██████████████
Faz4                                      ██████████████
Faz5                                                    ████
Faz6                                                        ████
Faz7                                                            ████
     ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
          MVP ▲                                               Go-Live ▲
```

---

## 3. Sprint Detay Planı

### Faz 1 — Temel Altyapı (S1-S2)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S1** | Proje iskeleti (Django + Next.js + Docker Compose) | 8 | — |
| | PostgreSQL, Redis, MinIO kurulumu | 5 | — |
| | Tenant modeli ve multi-tenancy altyapısı | 8 | DB |
| | JWT auth + refresh token mekanizması | 8 | — |
| | CI pipeline (lint + test + build) | 5 | — |
| | **S1 Toplam** | **34** | |
| **S2** | MFA (TOTP) entegrasyonu | 5 | Auth |
| | RBAC temel yapısı (roller, izinler, scope) | 8 | Auth |
| | Audit log altyapısı | 5 | — |
| | Bildirim altyapısı (e-posta, in-app şablonları) | 5 | — |
| | Dosya yükleme servisi (MinIO, ClamAV) | 5 | MinIO |
| | Seed data ve developer onboarding dokümantasyonu | 3 | — |
| | **S2 Toplam** | **31** | |

### Faz 2 — MVP Core (S3-S8)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S3** | Personel modülü — çalışan CRUD + listeleme | 8 | Tenant, RBAC |
| | Çalışan profil detay sayfası | 5 | Personel |
| | Departman ve pozisyon yönetimi | 5 | — |
| | **S3 Toplam** | **18** | |
| **S4** | Personel — toplu import (Excel) | 5 | Personel |
| | Personel — belge yönetimi ve arşiv | 5 | Dosya servisi |
| | Personel — arama ve filtreleme (tam metin) | 5 | Personel |
| | İzin modülü — izin tipleri ve politika tanımlama | 5 | — |
| | **S4 Toplam** | **20** | |
| **S5** | İzin — talep oluşturma ve bakiye hesaplama | 8 | İzin tipleri |
| | İzin — onay iş akışı (tek/çok kademeli) | 8 | RBAC, Bildirim |
| | İzin — takvim görünümü | 5 | İzin |
| | **S5 Toplam** | **21** | |
| **S6** | Self-servis portal — çalışan dashboard | 8 | Personel, İzin |
| | Self-servis — profil görüntüleme ve değişiklik talebi | 5 | Personel |
| | Self-servis — görev kutusu (pending onaylar) | 5 | İzin |
| | Duyuru sistemi | 3 | — |
| | **S6 Toplam** | **21** | |
| **S7** | Bildirim sistemi (e-posta + in-app + push) | 8 | Celery |
| | Temel raporlar (izin özeti, personel sayıları) | 5 | Raporlama |
| | Güvenlik sertleştirme (rate limit, CORS, headers) | 5 | — |
| | **S7 Toplam** | **18** | |
| **S8** | MVP bug fix ve polish | 8 | Tüm MVP modülleri |
| | UAT senaryoları çalıştırma | 5 | QA |
| | Performans testi (temel yük) | 5 | DevOps |
| | MVP pilot hazırlık ve eğitim materyali | 3 | — |
| | **S8 Toplam** | **21** | |

**🎯 MVP Release — Sprint 8 sonunda**

### Faz 3 — İK Operasyon (S9-S13)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S9** | İşe alım — ilan yönetimi ve aday havuzu | 8 | Personel |
| | İşe alım — başvuru formu ve parsing | 5 | — |
| | **S9 Toplam** | **13** | |
| **S10** | İşe alım — aday pipeline (Kanban) | 8 | ATS |
| | İşe alım — mülakat planlama ve değerlendirme | 5 | ATS |
| | İşe alım — teklif ve onboarding entegrasyonu | 5 | ATS, Personel |
| | **S10 Toplam** | **18** | |
| **S11** | Performans — dönem ve hedef tanımlama | 8 | Personel |
| | Performans — değerlendirme formları | 5 | Performans |
| | **S11 Toplam** | **13** | |
| **S12** | Performans — 360° değerlendirme ve kalibrasyon | 8 | Performans |
| | Organizasyon şeması — birim ve pozisyon yönetimi | 5 | Personel |
| | Organizasyon — interaktif organigram | 5 | Org |
| | **S12 Toplam** | **18** | |
| **S13** | Organizasyon — vekalet ve delegasyon | 5 | Org, RBAC |
| | Organizasyon — kadro planlama | 5 | Org |
| | Faz 3 entegrasyon testleri ve bug fix | 5 | Tümü |
| | **S13 Toplam** | **15** | |

### Faz 4 — Gelişmiş Modüller (S14-S18)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S14** | Eğitim — kurs yönetimi ve katalog | 8 | — |
| | Eğitim — kayıt ve tamamlama takibi | 5 | Eğitim |
| | **S14 Toplam** | **13** | |
| **S15** | Eğitim — gelişim planları ve sertifika yönetimi | 5 | Eğitim |
| | Raporlama — dashboard builder | 8 | Raporlama altyapı |
| | Raporlama — zamanlanmış rapor ve export | 5 | Celery |
| | **S15 Toplam** | **18** | |
| **S16** | Bordro — maaş hesaplama motoru (brüt→net) | 13 | Personel, İzin |
| | Bordro — SGK ve vergi bildirgeleri | 8 | Bordro |
| | **S16 Toplam** | **21** | |
| **S17** | Bordro — bordro slip PDF ve onay akışı | 5 | Bordro |
| | Vardiya — şablon ve plan yönetimi | 8 | Personel |
| | Vardiya — PDKS entegrasyonu | 5 | Vardiya |
| | **S17 Toplam** | **18** | |
| **S18** | Vardiya — mesai hesaplama ve onay | 5 | Vardiya |
| | Faz 4 entegrasyon testleri | 5 | Tümü |
| | Bordro UAT (muhasebeci doğrulaması) | 5 | Bordro |
| | **S18 Toplam** | **15** | |

### Faz 5 — Güvenlik & Uyum (S19-S20)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S19** | KVKK uyum — açık rıza yönetimi ve aydınlatma | 8 | Auth |
| | KVKK — veri sahibi hak kullanımı portali | 5 | Self-servis |
| | KVKK — saklama süresi motoru (otomatik silme/anonimleştirme) | 8 | Celery |
| | **S19 Toplam** | **21** | |
| **S20** | Güvenlik sertleştirme (OWASP checklist) | 8 | — |
| | Penetrasyon testi ve düzeltmeleri | 8 | — |
| | VERBİS veri envanteri export | 3 | KVKK |
| | **S20 Toplam** | **19** | |

### Faz 6 — DevOps & QA (S21-S22)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S21** | CI/CD production pipeline (GitHub Actions) | 8 | — |
| | Monitoring stack (Prometheus + Grafana + Loki) | 8 | Altyapı |
| | Alarm kuralları ve on-call setup | 5 | Monitoring |
| | **S21 Toplam** | **21** | |
| **S22** | Yük testi ve performans optimizasyonu | 8 | Tümü |
| | Yedekleme ve felaket kurtarma testi | 5 | DB |
| | Full regression E2E suite | 8 | QA |
| | **S22 Toplam** | **21** | |

### Faz 7 — Lansman (S23-S24)

| Sprint | User Story / Task | SP | Bağımlılık |
|--------|-------------------|----|------------|
| **S23** | Pilot tenant kurulumu ve veri migrasyonu | 8 | Tümü |
| | Kullanıcı eğitimleri (admin, İK, çalışan) | 5 | — |
| | Pilot dönem izleme ve feedback | 5 | — |
| | **S23 Toplam** | **18** | |
| **S24** | Pilot feedback düzeltmeleri | 8 | S23 |
| | Go-live checklist ve son kontroller | 5 | — |
| | Canlıya geçiş ve hypercare (ilk hafta) | 5 | — |
| | **S24 Toplam** | **18** | |

---

## 4. Milestone'lar

| Milestone | Sprint | Tarih (Ay ~) | Çıktı | Kabul Kriteri |
|-----------|--------|--------------|-------|---------------|
| **M1** — Tech Foundation | S2 sonu | Ay 1 | Çalışan iskelet, auth, CI | Login + RBAC çalışıyor |
| **M2** — Personel Ready | S4 sonu | Ay 2 | Personel CRUD, import, belgeler | 100 çalışan import edilebiliyor |
| **M3** — MVP Release 🎯 | S8 sonu | Ay 4 | Personel + İzin + Self-servis | UAT geçti, pilot hazır |
| **M4** — İK Operasyon | S13 sonu | Ay 6.5 | ATS + Performans + Organizasyon | E2E testler geçiyor |
| **M5** — Tam Platform | S18 sonu | Ay 9 | Eğitim + Raporlama + Bordro + Vardiya | Bordro hesaplama doğru |
| **M6** — Uyumluluk | S20 sonu | Ay 10 | KVKK, güvenlik sertleştirme | Pentest raporunda kritik yok |
| **M7** — Go-Live 🚀 | S24 sonu | Ay 12 | Canlı sistem | SLA karşılanıyor, 0 P1 bug |

---

## 5. Bağımlılık Haritası

```
Auth/Tenant ──┐
              ├──→ Personel ──┬──→ İzin ──────┬──→ Self-servis (MVP)
RBAC ─────────┘              │               │
                             ├──→ İşe Alım   ├──→ Raporlama
                             ├──→ Performans │
                             ├──→ Organizasyon│
                             ├──→ Eğitim     │
                             ├──→ Bordro ────┤
                             └──→ Vardiya ───┘
Celery/Bildirim ────────────────────────────→ Tüm modüller
Dosya Servisi ──────────────────────────────→ Personel, İşe Alım, Eğitim
```

---

## 6. Risk ve Buffer Planı

| Risk | Olasılık | Etki | Mitigation | Sprint Buffer |
|------|----------|------|------------|---------------|
| Bordro hesaplama karmaşıklığı | Yüksek | Yüksek | Muhasebeci erken dahil, parametrized test | +1 sprint (S18) |
| PDKS entegrasyon gecikmesi | Orta | Orta | Mock PDKS ile geliştirme, gerçek entegrasyon sonra | +0.5 sprint |
| Performans sorunları (büyük veri) | Orta | Yüksek | Erken yük testi (S8), index optimizasyonu | S7'de erken test |
| KVKK yasal değişiklik | Düşük | Orta | Esnek veri politika motoru | — |
| Ekip ayrılması | Düşük | Yüksek | Çapraz eğitim, dokümantasyon | %15 sprint buffer |

---

## 7. Sprint Ritüelleri

| Ritüel | Sıklık | Süre | Katılımcılar |
|--------|--------|------|--------------|
| Sprint Planning | 2 haftada 1 (sprint başı) | 2 saat | Tüm ekip + PO |
| Daily Standup | Her iş günü | 15 dk | Geliştirme ekibi |
| Backlog Refinement | Haftalık (Çarşamba) | 1 saat | Geliştirme ekibi + PO |
| Sprint Demo / Review | Sprint sonu (Cuma) | 1 saat | Tüm ekip + stakeholder |
| Retrospective | Sprint sonu | 45 dk | Geliştirme ekibi |
| Tech Sync | Haftalık | 30 dk | Backend + Frontend lead |

---

## 8. Velocity Takibi

| Metrik | Hedef | Alarm |
|--------|-------|-------|
| Sprint velocity | 40-50 SP | < 30 SP üst üste 2 sprint |
| Sprint tamamlanma | ≥ %85 planned stories | < %70 → scope review |
| Bug oranı | ≤ 2 P1/P2 bug per sprint | > 5 → kalite odaklı sprint |
| Tech debt oranı | ≤ %15 sprint capacity | > %25 → tech debt sprint |
