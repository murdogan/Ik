# 31 — Lansman & Geçiş Planı

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Pilot geçiş, veri migrasyonu, kullanıcı eğitimi, destek modeli, aşamalı canlıya geçiş ve başarı kriterleri  
> **Faz:** Faz 7

---

## 1. Lansman Yaklaşımı

Canlıya geçiş tek seferde büyük patlama yaklaşımıyla değil, kontrollü pilot ve aşamalı yayılım modeliyle yapılmalıdır. Önce sınırlı tenant veya tek şirket içindeki belirli ekiplerle geçiş yapılır; geri bildirimler sonrası genişleme sağlanır.

---

## 2. Geçiş Aşamaları

| Aşama | Süre | Açıklama | Çıktı |
|-------|------|----------|-------|
| 1. Hazırlık | 2 hafta | Veri eşleme, kullanıcı listeleri, rol matrisi, eğitim materyali | Migration planı, eğitim takvimi |
| 2. Veri Migrasyonu | 1-2 hafta | Mevcut sistemden veri aktarımı, doğrulama | Doğrulanmış veri seti |
| 3. UAT | 1 hafta | İK ekibi ve kilit kullanıcılarla kabul testi | Onaylı UAT raporu |
| 4. Pilot | 2-4 hafta | Seçili birim/departmanda sınırlı canlı kullanım | Pilot raporu, feedback listesi |
| 5. Stabilizasyon | 1-2 hafta | Hata düzeltme, süreç optimizasyonu, performans iyileştirme | Stabil sistem |
| 6. Genişleme | 2-4 hafta | Kademeli olarak diğer departman / tenant'ları dahil etme | %100 kullanıcı geçişi |
| 7. Tam Canlı | — | Eski sistem devreden çıkarılır | Go-live onayı |

### 2.1 Geçiş Zaman Çizelgesi

```
Hafta:  1    2    3    4    5    6    7    8    9   10   11   12
       ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
Hazırlık ████
Migration    ████
UAT              ██
Pilot            ██████████
Stabilize                  ████
Genişleme                      ████████
Tam Canlı                              ████
Hypercare                              ████████████
       ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
                  UAT ▲  Pilot ▲      Go-Live ▲
```

---

## 3. Veri Migrasyonu

### 3.1 Migrasyon Veri Haritası

| Kaynak Veri | Hedef Modül | Hedef Tablo | Migrasyon Yöntemi | Öncelik |
|-------------|-------------|-------------|--------------------| --------|
| Personel kayıtları | Personel | employees | CSV/Excel import | P1 |
| Departman / birim yapısı | Organizasyon | org_units | CSV import | P1 |
| Yönetici hiyerarşisi | Organizasyon | org_reporting_lines | CSV import | P1 |
| İzin bakiyeleri (yıllık) | İzin | leave_balances | Açılış bakiyesi import | P1 |
| İzin geçmişi (opsiyonel) | İzin | leave_requests | CSV import | P2 |
| Pozisyon tanımları | Organizasyon | org_positions | CSV import | P1 |
| Belgeler (özlük dosyaları) | Personel | Dosya sistemi (MinIO) | Toplu upload | P2 |
| Bordro geçmişi (opsiyonel) | Bordro | payroll_periods | CSV import | P3 |
| Eğitim kayıtları | Eğitim | enrollments | CSV import | P3 |

### 3.2 Migrasyon Adımları

```
1. Kaynak Veri Analizi
   ├── Kaynak format tespiti (Excel, CSV, eski DB)
   ├── Alan eşleme dokümanı hazırlama
   └── Veri kalitesi raporu (eksik, tutarsız, duplike)
       │
       ▼
2. Veri Temizleme
   ├── Duplike kayıt birleştirme
   ├── Eksik alan tamamlama (ör. TCKN, departman)
   └── Format standardizasyonu (tarih, telefon)
       │
       ▼
3. Test Migrasyonu (Staging)
   ├── python manage.py migrate_import --source=data.csv --dry-run
   ├── Doğrulama kontrolleri (kayıt sayısı, anahtar alanlar)
   └── İK ekibi ile örneklem doğrulama
       │
       ▼
4. Canlı Migrasyon
   ├── Bakım penceresi (mesai dışı)
   ├── python manage.py migrate_import --source=data.csv --confirm
   ├── Otomatik doğrulama script'i
   └── İK onayı
```

### 3.3 Migrasyon Management Command'ları

| Komut | Açıklama |
|-------|----------|
| `python manage.py import_employees --file=data.xlsx` | Toplu personel import |
| `python manage.py import_org_structure --file=org.csv` | Departman ve hiyerarşi |
| `python manage.py import_leave_balances --file=balances.csv --year=2026` | İzin açılış bakiyeleri |
| `python manage.py import_documents --dir=/uploads/` | Toplu belge yükleme |
| `python manage.py validate_migration --report` | Migrasyon doğrulama raporu |

### 3.4 Doğrulama Kontrolleri

| Kontrol | Beklenen |
|---------|----------|
| Kayıt sayısı eşleşmesi | Kaynak kayıt = hedef kayıt |
| TCKN benzersizliği | Duplike yok |
| Departman-çalışan ilişkisi | Tüm çalışanlar bir departmana bağlı |
| Yönetici zinciri | Kırık (orphan) referans yok |
| İzin bakiye kontrolü | Negatif bakiye yok (istisna: avans izin) |
| E-posta benzersizliği | Duplike e-posta yok |

### 3.5 Rollback Planı

| Durum | Aksiyon |
|-------|---------|
| Migrasyon sırasında hata | Transaction rollback, kaynak veriye dönüş |
| Migrasyon sonrası veri hatası | Düzeltme script'i veya tekrar import |
| Go-live sonrası kritik hata | Eski sisteme geçici dönüş (paralel çalışma dönemi) |

---

## 4. Go-Live Checklist

| # | Kontrol | Sorumlu | Durum |
|---|---------|---------|-------|
| 1 | Tüm veri migrasyonu tamamlandı ve doğrulandı | DevOps + İK | ☐ |
| 2 | UAT onayı alındı (İK imzası) | Ürün + İK | ☐ |
| 3 | Kullanıcı hesapları oluşturuldu (e-posta davetleri) | DevOps | ☐ |
| 4 | Rol atamaları yapıldı (admin, İK, yönetici, çalışan) | İK + Admin | ☐ |
| 5 | SSL sertifikası aktif, domain yapılandırması tamam | DevOps | ☐ |
| 6 | Monitoring ve alarm kuralları aktif | DevOps | ☐ |
| 7 | Yedekleme planı test edildi | DevOps | ☐ |
| 8 | E-posta / SMS bildirimleri test edildi | QA | ☐ |
| 9 | KVKK aydınlatma metinleri yüklendi | DPO / İK | ☐ |
| 10 | Performans testi geçti (SLA karşılandı) | QA + DevOps | ☐ |
| 11 | Penetrasyon testi raporu — kritik/yüksek bulgu yok | Güvenlik | ☐ |
| 12 | Rollback planı dokümante edildi | DevOps | ☐ |
| 13 | Destek ekibi hazır, iletişim kanalları açık | Destek | ☐ |
| 14 | Eğitimler tamamlandı (admin + İK + çalışan) | Ürün | ☐ |
| 15 | Eski sistem paralel çalışma planı hazır | İK + DevOps | ☐ |

---

## 5. Eğitim Planı

### 5.1 Eğitim Programı

| Hedef Kitle | İçerik | Format | Süre | Zamanlama |
|-------------|--------|--------|------|-----------|
| Süper Admin / IT | Tenant yapılandırma, rol yönetimi, monitoring | Yüz yüze / online | 4 saat | Go-live -2 hafta |
| İK Yöneticisi | Personel yönetimi, izin politikaları, raporlama | Workshop | 1 gün | Go-live -1 hafta |
| İK Uzmanı | Günlük operasyonlar, bordro, işe alım | Workshop | 1 gün | Go-live -1 hafta |
| Departman Yöneticisi | Onay akışları, ekip görünümü, performans | Online | 2 saat | Go-live -1 hafta |
| Çalışanlar | Self-servis, izin talebi, profil, bildirimler | Video + kılavuz | 30 dk | Go-live haftası |

### 5.2 Eğitim Materyalleri

| Materyal | Format | Dil |
|----------|--------|-----|
| Admin kılavuzu | PDF + online help center | TR |
| İK operasyon kılavuzu | PDF + video (5-10 dk bölümler) | TR |
| Çalışan hızlı başlangıç | İnteraktif walkthrough (in-app) | TR |
| Sık sorulan sorular (SSS) | Help center makalesi | TR |
| Video eğitim serisi | 10-15 kısa video (ekran kaydı) | TR |

---

## 6. Destek Modeli

### 6.1 Hypercare Dönemi (İlk 4 Hafta)

| Parametre | Değer |
|-----------|-------|
| Süre | Go-live sonrası 4 hafta |
| Destek saatleri | 08:00 – 20:00 (haftaiçi) |
| Yanıt SLA | P1: 30 dk, P2: 2 saat, P3: 4 saat |
| Destek kanalları | Slack kanalı + e-posta + in-app ticket |
| Destek ekibi | 2 kişi (1 teknik + 1 fonksiyonel) |
| Günlük rapor | Açık ticket sayısı, çözüm oranı, kullanım istatistikleri |

### 6.2 Normal Destek (Hypercare Sonrası)

| Parametre | Değer |
|-----------|-------|
| Destek saatleri | 09:00 – 18:00 (haftaiçi) |
| Yanıt SLA | P1: 1 saat, P2: 4 saat, P3: 1 iş günü |
| Destek kanalları | E-posta + in-app ticket |
| Destek ekibi | 1 kişi (part-time teknik + İK süper kullanıcı) |

### 6.3 Severity Tanımları

| Seviye | Tanım | Örnek |
|--------|-------|-------|
| P1 — Kritik | Sistem erişilemez veya veri kaybı riski | Login yapılamıyor, bordro hatası |
| P2 — Yüksek | Önemli fonksiyon çalışmıyor, workaround yok | İzin onay butonu hata veriyor |
| P3 — Orta | Fonksiyon çalışıyor ama sorunlu | Rapor yavaş yükleniyor |
| P4 — Düşük | Kozmetik veya öneri | Renk sorunu, metin değişikliği |

---

## 7. Paralel Çalışma Stratejisi

| Aşama | Eski Sistem | Yeni Sistem | Süre |
|-------|-------------|-------------|------|
| Pilot | Aktif (ana) | Test + pilot birimler | 2-4 hafta |
| Geçiş | Salt okunur (referans) | Aktif (yeni kayıtlar) | 2 hafta |
| Tam canlı | Kapatıldı (arşiv) | Tek kaynak (SoR) | — |

> **Önemli:** Paralel çalışma döneminde veri girişi SADECE tek sistemde yapılır. Çift veri girişi kabul edilmez.

---

## 8. Başarı Kriterleri ve KPI'lar

### 8.1 Lansman Başarı KPI'ları

| KPI | Hedef | Ölçüm Periyodu |
|-----|-------|-----------------|
| Aktif kullanım oranı | > %75 (ilk ay), > %90 (3. ay) | Aylık |
| İzin taleplerinin sistem üzerinden açılma oranı | > %90 (ilk ay) | Aylık |
| Kritik hata (P1) | 0 (ilk ay) | Sürekli |
| Destek talebi çözüm süresi | < 1 iş günü (ortalama) | Haftalık |
| Sistem uptime | ≥ %99.5 | Aylık |
| Kullanıcı memnuniyeti (NPS) | ≥ 7/10 | İlk ay sonu anket |
| Veri doğruluğu | %100 (migrasyon sonrası doğrulama) | Go-live + 1 hafta |
| Eğitim tamamlama oranı | > %90 (İK), > %80 (çalışan) | Go-live öncesi |

### 8.2 3 Aylık Değerlendirme

| KPI | Hedef |
|-----|-------|
| Tüm İK süreçleri dijitale taşındı | %100 |
| Eski sistem tamamen devreden çıktı | ✅ |
| İK ekip verimliliği artışı | ≥ %30 |
| Çalışan self-servis kullanım oranı | > %85 |
| Aylık aktif kullanıcı | > %90 kayıtlı kullanıcı |

---

## 9. İletişim Planı

| Zaman | Hedef Kitle | Kanal | Mesaj |
|-------|-------------|-------|-------|
| Go-live -4 hafta | Tüm şirket | E-posta + duyuru | Yeni İK sistemi geliyor, takvim paylaşımı |
| Go-live -2 hafta | Yöneticiler | Workshop daveti | Eğitim programı detayları |
| Go-live -1 hafta | Tüm çalışanlar | E-posta + poster | Hesap oluşturma bilgisi, hızlı başlangıç kılavuzu |
| Go-live günü | Tüm şirket | E-posta + in-app | Sistem açıldı, destek kanalları |
| Go-live +1 hafta | Tüm şirket | E-posta | İlk hafta özeti, SSS, destek hatırlatması |
| Go-live +1 ay | Yönetim | Rapor | Kullanım istatistikleri, geri bildirim özeti |
