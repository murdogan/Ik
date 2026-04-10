# 23 — KVKK & GDPR Uyumluluk

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Kişisel veri işleme envanteri, açık rıza, aydınlatma, veri minimizasyonu, saklama/silme politikası, veri sahibi hakları, yurtdışı aktarım ve kayıt süreçleri  
> **Faz:** Faz 5

---

## 1. Amaç

Bu doküman, İnsan Kaynakları Yönetim Sistemi içinde işlenen kişisel verilerin KVKK ve gerekli durumlarda GDPR ilkelerine uygun biçimde yönetilmesi için temel kuralları tanımlar.

---

## 2. Veri Kategorileri ve İşleme Envanteri

### 2.1 Veri Kategorileri

| Kategori | Örnek Veri | Hassasiyet | İşleme Amacı |
|----------|------------|------------|--------------|
| Kimlik verisi | Ad, soyad, TCKN, doğum tarihi, cinsiyet | Yüksek | Personel yönetimi, yasal yükümlülük |
| İletişim verisi | E-posta, telefon, adres | Orta | İş iletişimi, bildirim |
| Özlük verisi | İşe giriş tarihi, unvan, departman, sözleşme tipi | Orta | Personel yönetimi, raporlama |
| Finansal veri | Maaş, IBAN, bordro, SGK primi | Yüksek | Bordro işleme, yasal bildirim |
| Özel nitelikli veri | Sağlık raporu, engellilik bilgisi, kan grubu | Çok yüksek | İzin yönetimi, İSG yükümlülüğü |
| Performans verisi | Değerlendirme skorları, yorumlar, hedefler | Yüksek | Performans yönetimi, kariyer planlama |
| Biyometrik veri | Parmak izi hash, yüz tanıma template | Çok yüksek | PDKS giriş-çıkış (açık rıza zorunlu) |
| Lokasyon verisi | GPS koordinatları (mobil check-in) | Yüksek | Devam takibi (açık rıza zorunlu) |
| Eğitim verisi | Sertifikalar, eğitim geçmişi | Orta | Gelişim yönetimi |
| Aday verisi | CV, mülakat notları, referanslar | Yüksek | İşe alım süreci |

### 2.2 Modül Bazlı İşleme Envanteri

| Modül | İşlenen Veriler | Hukuki Dayanak (KVKK) | GDPR Karşılığı |
|-------|-----------------|------------------------|----------------|
| 10 – Personel | Kimlik, iletişim, özlük | Md. 5/2-c (sözleşme), Md. 5/2-ç (yasal) | Art. 6(1)(b), 6(1)(c) |
| 11 – İşe Alım | Aday verileri, CV | Md. 5/2-c (sözleşme öncesi), açık rıza | Art. 6(1)(b), 6(1)(a) |
| 12 – İzin | İzin tarihleri, sağlık raporu | Md. 5/2-ç (yasal), Md. 6/3 (sağlık) | Art. 6(1)(c), 9(2)(b) |
| 13 – Performans | Puanlar, hedefler, yorumlar | Md. 5/2-f (meşru menfaat) | Art. 6(1)(f) |
| 14 – Bordro | Finansal veriler, SGK | Md. 5/2-ç (yasal yükümlülük) | Art. 6(1)(c) |
| 15 – Eğitim | Eğitim geçmişi, sertifikalar | Md. 5/2-f (meşru menfaat) | Art. 6(1)(f) |
| 16 – Vardiya | Giriş-çıkış, biyometri, GPS | Md. 5/2-c + açık rıza (biyometri) | Art. 6(1)(b), 9(2)(a) |
| 18 – Raporlama | Anonim/aggrege veriler | Md. 28/1 (anonimleştirme) | Recital 26 |

---

## 3. Uyum İlkeleri

| İlke | KVKK Maddesi | Uygulama |
|------|-------------|----------|
| Hukuka uygunluk | Md. 4/2-a | Her veri işleme faaliyeti için hukuki dayanak belirlenir |
| Veri minimizasyonu | Md. 4/2-ç | Gerekli olmayan alanlar toplanmaz; form'da opsiyonel işaretlenir |
| Amaçla sınırlılık | Md. 4/2-c | Her veri alanı spesifik iş amacı ile eşlenir |
| Doğruluk güncelleme | Md. 4/2-d | Çalışan profil değişikliği self-servis ile mümkün |
| Saklama süresi | Md. 4/2-e | Modül bazlı retention kuralları; süre dolunca otomatik anonimleştirme |
| Şeffaflık | Md. 10 | Aydınlatma metni ve işleme amacı her form'da görünür |
| Hak kullanımı | Md. 11 | Erişim, düzeltme, silme, taşıma talepleri izlenir ve cevaplanır |
| Veri sorumlusu kaydı | Md. 16 | VERBİS'e kayıt zorunluluğu |

---

## 4. Saklama ve Silme Politikası

### 4.1 Modül Bazlı Saklama Süreleri

| Veri Türü | Minimum Saklama | Maksimum Saklama | Yasal Dayanak | Süre Sonrası |
|-----------|-----------------|------------------|---------------|--------------|
| Özlük dosyaları | İş ilişkisi + 10 yıl | 15 yıl | İş Kanunu Md. 32, Borçlar K. Md. 146 | Anonimleştirme |
| Bordro kayıtları | 5 yıl | 10 yıl | VUK Md. 253, SGK Md. 93 | Arşiv → silme |
| SGK bildirgeleri | 10 yıl | 10 yıl | 5510 sayılı K. Md. 93 | Silme |
| İzin kayıtları | İş ilişkisi + 5 yıl | 10 yıl | İş Kanunu | Anonimleştirme |
| Sağlık raporları | İş ilişkisi süresi | İlişki + 2 yıl | KVKK Md. 6 | Silme (zorunlu) |
| Performans kayıtları | İş ilişkisi süresi | İlişki + 5 yıl | Meşru menfaat | Anonimleştirme |
| Aday verileri (red) | 6 ay | 2 yıl | İŞKUR mevzuatı | Silme |
| Biyometrik hash | İş ilişkisi süresi | İlişki bittikten 30 gün | KVKK Md. 6 | Silme (zorunlu) |
| GPS lokasyon logları | 30 gün | 90 gün | Meşru menfaat | Silme |
| Audit logları | 2 yıl | 5 yıl | ISO 27001, KVKK | Arşiv |
| Eğitim sertifikaları | İş ilişkisi süresi | İlişki + 5 yıl | İSG mevzuatı | Anonimleştirme |

### 4.2 Otomatik Veri Yaşam Döngüsü

```
Veri oluşturuldu → Aktif saklama → Saklama süresi doldu
         │                              │
         ▼                              ▼
    İş ilişkisi              ┌─────────────────┐
    devam ediyor             │ Retention Engine │
                             │ (Celery daily)   │
                             └────────┬────────┘
                                      │
                              ┌───────┼───────┐
                              ▼       ▼       ▼
                          Anonimleş  Silme   Arşive
                          -tirme            taşıma
```

---

## 5. Açık Rıza ve Aydınlatma

### 5.1 Açık Rıza Gerektiren İşlemler

| İşlem | Açıklama | Rıza Tipi |
|-------|----------|-----------|
| Biyometrik PDKS | Parmak izi / yüz tanıma ile giriş-çıkış | Açık, ayrı form |
| GPS check-in | Mobil uygulamada konum kaydetme | Açık, ayrı form |
| Fotoğraf kullanımı | Profil fotoğrafının organizasyon şemasında gösterimi | Açık |
| Sağlık verisi işleme | Rapor yükleme, engellilik bilgisi | KVKK Md. 6, açık rıza |
| Aday havuzu saklama | Red edilen adayın verisini gelecek ilanlar için saklama | Açık |

### 5.2 Rıza Kaydı Yapısı

| Alan | Açıklama |
|------|----------|
| Rıza tipi | Belirli, açık, bilgilendirici |
| Veriliş zamanı | Zaman damgası (TIMESTAMPTZ) |
| Versiyon | Aydınlatma metni versiyonu |
| IP / cihaz | Rızanın verildiği ortam |
| Geri çekme | Her an geri çekilebilir; geri çekme zaman damgası |

### 5.3 Aydınlatma Metinleri

| Metin | Gösterim Yeri |
|-------|---------------|
| İşe alım aydınlatma | Başvuru formu öncesi |
| Çalışan aydınlatma | Onboarding sihirbazı (ilk adım) |
| Biyometrik aydınlatma | PDKS aktivasyon ekranı |
| GPS aydınlatma | Mobil check-in ilk kullanım |
| Çerez aydınlatma | Web portal footer |

---

## 6. Veri Sahibi Hakları (KVKK Md. 11)

| Hak | Açıklama | SLA |
|-----|----------|-----|
| Bilgi alma | Veriler hakkında bilgi talep etme | 30 gün |
| Erişim | Kendi verilerine erişim | 30 gün |
| Düzeltme | Eksik/hatalı veri düzeltme | 30 gün |
| Silme / yok etme | Koşullar sağlanırsa silme | 30 gün |
| Aktarım (taşınabilirlik) | Verilerini yapılandırılmış formatta alma | 30 gün |
| İtiraz | Olumsuz sonuç doğuran işleme itiraz | 30 gün |
| Otomatik karar itiraz | Otomatik profilleme sonucuna itiraz | 30 gün |

### 6.1 Hak Kullanımı Teknik Akış

```
Çalışan portal'dan hak kullanımı talebi oluşturur
    │
    ▼
Sistem talep kaydı açar (data_subject_requests tablosu)
    │
    ▼
İK / DPO dashboard'unda görev oluşur
    │
    ▼
Talep incelenir → kimlik doğrulama
    │
    ├── Onay → İşlem yapılır (erişim raporu, düzeltme, silme)
    └── Red → Gerekçeli cevap (yasal saklama zorunluluğu vb.)
    │
    ▼
Sonuç çalışana bildirilir; tüm süreç loglanır
```

### 6.2 data_subject_requests Tablosu

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `employee_id` | UUID FK | Talep eden |
| `request_type` | ENUM | `access`, `rectification`, `erasure`, `portability`, `objection` |
| `description` | TEXT | Talep detayı |
| `status` | ENUM | `pending`, `in_review`, `completed`, `rejected` |
| `assigned_to` | UUID FK → users NULL | İK/DPO |
| `response` | TEXT NULL | Cevap metni |
| `completed_at` | TIMESTAMPTZ NULL | |
| `sla_deadline` | DATE | Yasal süre (30 gün) |
| `created_at` | TIMESTAMPTZ | |

---

## 7. VERBİS Kaydı ve Veri Sorumlusu

| Konu | Uygulama |
|------|----------|
| VERBİS kaydı | Tenant (veri sorumlusu) kendi kaydından sorumlu |
| Veri envanteri | Sistem modül bazlı veri envanterini otomatik üretebilir |
| İrtibat kişisi | Tenant ayarlarında DPO / irtibat kişisi tanımlanır |
| İmha politikası | Veri imha planı tenant bazında yapılandırılır |

---

## 8. Yurtdışı Veri Aktarımı

| Durum | Kontrol |
|-------|---------|
| Veri Türkiye'de barındırılır | Varsayılan; ek işlem gerektirmez |
| Yurtdışı bulut sağlayıcı (EU) | KVKK Kurul kararı + yeterli koruma kontrolü |
| Yurtdışı bulut sağlayıcı (ABD vb.) | Açık rıza veya taahhütname gereklidir |
| 3. taraf entegrasyonlar | Veri işleyen sözleşmesi + güvenlik değerlendirmesi zorunlu |

---

## 9. Teknik ve Operasyonel Kontroller

| Kontrol | Açıklama | Detay |
|---------|----------|-------|
| Şifreleme (transit) | TLS 1.3 zorunlu | Tüm API ve web trafiği |
| Şifreleme (at-rest) | AES-256 | Hassas alanlar (TCKN, IBAN, sağlık verisi) |
| Maskeleme | Dinamik veri maskeleme | TCKN: ****1234, IBAN: TR** **** **XX XX |
| RBAC | Rol bazlı erişim kontrolü | Modül ve alan bazında |
| Tenant izolasyonu | Her tenant kendi verisini görür | Row-level security |
| Audit log | Tüm veri erişim ve değişiklikleri | Kim, ne zaman, ne yaptı |
| Export kontrolü | Hassas veri export'unda audit + onay | PDF/Excel çıktılarında log |
| Anonimleştirme | Geri dönüşümsüz veri anonimleştirme | K-anonymity (k ≥ 5) |
| Pseudonymization | Geri dönüşümlü takma ad | Test ortamlarında gerçek veri yerine |
| Veri lokalizasyonu | Türkiye içinde barındırma | AWS Istanbul / Azure Türkiye |

---

## 10. Celery Zamanlanmış Görevler

| Görev | Cron | Açıklama |
|-------|------|----------|
| `check_retention_policies` | Her gün 02:00 | Saklama süresi dolan verileri tespit eder ve işlem kuyruğuna ekler |
| `execute_data_deletion` | Her gün 03:00 | Onaylanmış silme/anonimleştirme işlemlerini uygular |
| `check_consent_expiry` | Her gün 04:00 | Süresi dolan rızaları tespit eder ve bildirim gönderir |
| `generate_data_inventory` | Her ayın 1'i | Modül bazlı veri envanteri raporunu üretir |
| `sla_deadline_reminder` | Her gün 09:00 | Yaklaşan SLA süresi olan hak kullanım taleplerini hatırlatır |

---

## 11. Test Senaryoları

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Erişim talebi oluşturma | Talep kaydı açılır, SLA süresi hesaplanır |
| 2 | Silme talebi (yasal saklama süresi aktif) | Sistem reddeder, gerekçe gösterir |
| 3 | Saklama süresi dolan veri | Anonimleştirme/silme görevi çalışır |
| 4 | Açık rıza geri çekme | İlgili veri işleme durdurulur |
| 5 | Anonimleştirilmiş veriye erişim | Bireysel kimlik tespit edilemez |
| 6 | Hassas veri export'u | Audit log kaydı oluşur |
| 7 | Tenant izolasyonu | Farklı tenant verisi görüntülenemez |
| 8 | Maskeleme doğrulama | TCKN ve IBAN yetkisiz kullanıcıda maskelenmiş |
