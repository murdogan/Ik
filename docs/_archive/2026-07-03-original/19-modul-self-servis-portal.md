# 19 — Modül: Self-Servis Portal

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Çalışan portalı, yönetici portalı, talep yönetimi, duyurular, profil işlemleri, görevlerim, bildirim merkezi, mobil öncelikli deneyim  
> **Faz:** MVP'de çekirdek bileşen; sonraki modüllerin kullanıcıya açılan yüzüdür  
> **Referans:** 10-modul-personel-yonetimi.md, 12-modul-izin-devamsizlik.md, 13-modul-performans-yonetimi.md, 17-modul-organizasyon-semasi.md

---

## 1. Modül Özeti

Self-Servis Portal; çalışanların ve yöneticilerin günlük İK işlemlerini merkezi bir deneyim üzerinden yapmasını sağlar. Portal, tüm operasyonel modüllerin kullanıcı katmanı olarak çalışır ve web ile mobil uyumlu responsive deneyim sunar.

### 1.1 Temel Yetkinlikler

| Alan | Açıklama |
|------|----------|
| Profilim | Kişisel bilgiler, iletişim, özlük verileri |
| Taleplerim | İzin, belge, bilgi güncelleme, masraf benzeri talepler |
| Görevlerim | Onay bekleyen işlemler, performans görevleri |
| Duyurular | Şirket haberleri ve politika duyuruları |
| Belgelerim | Bordro, sertifika, sözleşme, ek dosyalar |

---

## 2. İlişkili Personalar ve Kullanıcı Yolculukları

### 2.1 Persona-Modül İlişkisi

| Persona | Portal Görünümü | Kullanım Sıklığı | Kritik İşlemler |
|---------|-----------------|-------------------|-----------------|
| **Zeynep (Çalışan)** | Kişisel dashboard | Günlük | İzin talebi, profil, bordro pusulası, görevler |
| **Mehmet (Dept. Yöneticisi)** | Ekip dashboard'u | Günlük | Onay kutusu, takım takvimi, ekip özeti |
| **Ayşe (İK Uzmanı)** | İK operasyon kısa yolları | Günlük | Genişletilmiş fonksiyonlar, duyuru yönetimi |
| **Hakan (Genel Müdür)** | Executive özet | Haftalık | KPI kartları, onay bekleyenler |

### 2.2 Çalışan — Günlük Portal Yolculuğu

```
GİRİŞ                 DASHBOARD              İŞLEM
   │                      │                       │
   ▼                      ▼                       ▼
Login (SSO/MFA)       Kişisel dashboard       Hızlı işlem yap
   │                   açılır                     │
   ├─ Bildirimler →    ├─ Bekleyen görevler    ├─ İzin talebi oluştur
   │  badge sayısı     ├─ Kalan izin bakiyesi  ├─ Bordro pusulası indir
   └─ Duyuru kartı     ├─ Yaklaşan eğitimler  ├─ Profil güncelleme talebi
                       ├─ Bu hafta vardiyam     ├─ Belge talebi
                       └─ Son duyurular        └─ Bildirim tercihlerini
                                                    ayarla
```

### 2.3 Yönetici — Ekip Yönetimi Yolculuğu

```
GİRİŞ                 ONAY KUTUSU            EKİP TAKİBİ
   │                      │                       │
   ▼                      ▼                       ▼
Yönetici dashboard     Bekleyen onayları      Ekibini izle
açılır                 gör ve işle                │
   │                      │                   ├─ Takım takvimi
   ├─ 3 izin onayı    ├─ İzin talebi onayla  │  (kim nerede)
   ├─ 1 mesai onayı   ├─ Mesai talebi onayla ├─ Performans özeti
   └─ Performans       ├─ Belge talebi onayla ├─ İzin bakiye durumu
      görevleri        └─ Toplu onayla        └─ Devamsızlık uyarıları
```

---

## 3. Fonksiyonel Gereksinimler

### 3.1 Kişiselleştirilmiş Dashboard

#### FR-SSP-01: Rol Bazlı Dashboard

**Çalışan Dashboard Kartları:**

| Kart | Veri Kaynağı | Öncelik |
|------|--------------|---------|
| Bekleyen görevlerim | Tüm modüller (birleşik) | Yüksek |
| İzin bakiyem | İzin modülü | Yüksek |
| Bu hafta vardiyam | Vardiya modülü | Yüksek |
| Son bordro pusulam | Bordro modülü | Orta |
| Yaklaşan eğitimler | Eğitim modülü | Orta |
| Performans hedefleri | Performans modülü | Orta |
| Son duyurular | Portal duyuru sistemi | Düşük |
| Doğum günleri | Personel modülü | Düşük |

**Yönetici Dashboard Ek Kartları:**

| Kart | Veri Kaynağı |
|------|--------------|
| Onay bekleyenler (badge) | Tüm onay modülleri |
| Ekip takım takvimi | İzin + Vardiya |
| Ekip performans özeti | Performans modülü |
| Departman headcount | Organizasyon modülü |

#### FR-SSP-02: Birleşik Görev Kutusu

**Görev Tipleri ve Kaynakları:**

| Görev Tipi | Kaynak Modül | Örnek |
|------------|--------------|-------|
| `leave_approval` | İzin | "Ali Yılmaz 3 gün yıllık izin talep etti" |
| `overtime_approval` | Vardiya | "Mehmet Kaya 2 saat mesai onayı bekliyor" |
| `performance_review` | Performans | "Öz değerlendirmenizi tamamlayın" |
| `document_request` | Personel | "Zeynep belge talebi gönderi" |
| `training_assignment` | Eğitim | "İSG eğitimi son tarih: 15 Şubat" |
| `profile_change` | Portal | "Profil güncelleme talebi onay bekliyor" |

**Önceliklendirme:** Son tarih yakınlığı → Görev tipi öncelik ağırlığı → Oluşturulma tarihi

### 3.2 Profil Yönetimi

#### FR-SSP-03: Profil Görüntüleme ve Güncelleme

**Alan Kategorileri:**

| Kategori | Alanlar | Düzenleme |
|----------|---------|-----------|
| Kişisel | Ad, soyad, doğum tarihi, fotoğraf | Salt okunur (talep ile) |
| İletişim | Telefon, e-posta, adres | Doğrudan düzenlenebilir (self) |
| İş bilgileri | Pozisyon, departman, işe giriş | Salt okunur |
| Acil durum | Acil durum kişisi, telefon | Doğrudan düzenlenebilir |
| Banka | IBAN, banka adı | Salt okunur (talep ile) |
| Belgeler | TC kimlik, ehliyet, sertifikalar | Yükleme (İK onayı) |

**Profil Değişiklik Talebi Akışı:**

```
Çalışan düzenleme iste → Değişiklik talebi oluşturuldu (eski ↔ yeni)
        │
        ▼
İK onay kutusuna düştü → İK onayladı → Profil güncellendi
                       → İK reddetti → Çalışana bildirim + gerekçe
```

### 3.3 Duyuru Sistemi

#### FR-SSP-04: Segmentli Duyurular

| Özellik | Açıklama |
|---------|----------|
| Hedef kitle | Tüm şirket, departman, pozisyon, lokasyon veya bireysel |
| Öncelik | Normal, önemli, acil |
| Yayın zamanı | Anlık veya zamanlanmış |
| Son geçerlilik | Otomatik kaldırma tarihi |
| Pin | Sabitlenmiş duyuru (her zaman üstte) |
| Okunma takibi | Okunma oranı İK'ya raporlanır |
| Ek dosya | PDF, görsel eklenebilir |

### 3.4 Belge Kasası

#### FR-SSP-05: Belgelerim

| Belge Tipi | Kaynak | İndirme |
|------------|--------|---------|
| Bordro pusulası | Bordro modülü (otomatik) | PDF |
| İş sözleşmesi | Personel modülü | PDF |
| Sertifikalar | Eğitim modülü | PDF |
| SGK dökümleri | Bordro modülü | PDF |
| Kendi yüklediğim belgeler | Self-servis | Çeşitli |

### 3.5 Bildirim Merkezi

#### FR-SSP-06: Bildirim Yönetimi

**Bildirim Kanalları:**

| Kanal | Açıklama |
|-------|----------|
| Uygulama içi (in-app) | Portal ve mobilde gerçek zamanlı (WebSocket) |
| Push notification | Mobil cihaza push bildirim |
| E-posta | Özet veya anlık (kullanıcı tercihi) |

**Bildirim Tercihleri:**

| Bildirim Kategorisi | Varsayılan | Kullanıcı Değiştirebilir |
|--------------------|-----------|--------------------------|
| İzin onay sonucu | In-app + E-posta | ✅ (e-posta kapatılabilir) |
| Görev hatırlatma | In-app + Push | ✅ |
| Duyurular | In-app | ❌ (kapatılamaz) |
| Bordro pusulası | In-app + E-posta | ✅ |
| Vardiya değişikliği | In-app + Push | ✅ |
| Sistem bildirimleri | In-app | ❌ |

### 3.6 İş Kuralları

| Kural | Açıklama |
|-------|----------|
| IK-SSP-01 | Kullanıcı yalnızca kendi kişisel verilerini ve yetkili olduğu ekip verilerini görür |
| IK-SSP-02 | Duyuru okunma durumu kullanıcı bazında izlenir; okunma oranı İK'ya raporlanır |
| IK-SSP-03 | Salt okunur profil alanı değişikliği için talep iş akışı başlatılır |
| IK-SSP-04 | Görev kutusu modüller arası önceliklendirilmiş birleşik görünüm üretir |
| IK-SSP-05 | Bildirim tercihleri kullanıcı tarafından özelleştirilebilir; zorunlu bildirimler hariç |
| IK-SSP-06 | Duyuru son geçerlilik tarihi dolduğunda otomatik arşivlenir |

---

## 4. Veritabanı Tasarımı

### 4.1 portal_announcements

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `title` | VARCHAR(200) | Duyuru başlığı |
| `body` | TEXT | Duyuru içeriği (Markdown/HTML) |
| `priority` | ENUM DEFAULT 'normal' | `normal`, `important`, `urgent` |
| `target_type` | ENUM | `all`, `department`, `position`, `location`, `individual` |
| `target_ids` | JSONB NULL | Hedef birim/kişi ID'leri |
| `is_pinned` | BOOLEAN DEFAULT FALSE | Sabitlenmiş mi |
| `published_at` | TIMESTAMPTZ NULL | Yayın zamanı (zamanlanmış için) |
| `expires_at` | TIMESTAMPTZ NULL | Son geçerlilik |
| `attachment_url` | VARCHAR(500) NULL | Ek dosya URL |
| `created_by` | UUID FK → users | |
| `is_active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | |

### 4.2 portal_announcement_reads

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `announcement_id` | UUID FK → portal_announcements | |
| `user_id` | UUID FK → users | |
| `read_at` | TIMESTAMPTZ | Okunma zamanı |

```sql
ALTER TABLE portal_announcement_reads
  ADD CONSTRAINT uq_announcement_read
  UNIQUE (announcement_id, user_id);
```

### 4.3 portal_tasks (Materialized View / Cache Tablosu)

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `user_id` | UUID FK → users | Görev sahibi |
| `task_type` | ENUM | `leave_approval`, `overtime_approval`, `performance_review`, `document_request`, `training_assignment`, `profile_change` |
| `source_module` | VARCHAR(30) | Kaynak modül kodu |
| `source_id` | UUID | Kaynak modüldeki kayıt ID |
| `title` | VARCHAR(200) | Görev başlığı |
| `description` | TEXT NULL | Kısa açıklama |
| `due_date` | TIMESTAMPTZ NULL | Son tarih |
| `priority` | SMALLINT DEFAULT 50 | Hesaplanmış öncelik puanı |
| `status` | ENUM DEFAULT 'pending' | `pending`, `completed`, `expired` |
| `action_url` | VARCHAR(300) | İşlem yapılacak sayfa deeplink |
| `created_at` | TIMESTAMPTZ | |

### 4.4 profile_change_requests

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `employee_id` | UUID FK → employees | Talep eden |
| `field_name` | VARCHAR(50) | Değiştirilmek istenen alan |
| `old_value` | TEXT | Mevcut değer |
| `new_value` | TEXT | Talep edilen yeni değer |
| `status` | ENUM DEFAULT 'pending' | `pending`, `approved`, `rejected` |
| `decided_by` | UUID FK → users NULL | |
| `decided_at` | TIMESTAMPTZ NULL | |
| `rejection_reason` | TEXT NULL | |
| `created_at` | TIMESTAMPTZ | |

### 4.5 user_notification_preferences

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `user_id` | UUID FK → users | |
| `category` | VARCHAR(50) | Bildirim kategorisi |
| `channel_in_app` | BOOLEAN DEFAULT TRUE | Uygulama içi aktif mi |
| `channel_push` | BOOLEAN DEFAULT TRUE | Push aktif mi |
| `channel_email` | BOOLEAN DEFAULT TRUE | E-posta aktif mi |
| `updated_at` | TIMESTAMPTZ | |

---

## 5. API Endpoint Detayları

### 5.1 Dashboard

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/dashboard` | Kişiselleştirilmiş dashboard | Auth |
| `GET` | `/me/dashboard/manager` | Yönetici ek kartları | Auth + Manager role |

**GET /me/dashboard — Yanıt:**

```json
{
  "user": { "id": "emp-001", "full_name": "Zeynep Arslan", "role": "employee" },
  "cards": {
    "pending_tasks": { "count": 2, "items": [
      { "type": "training_assignment", "title": "İSG Eğitimi", "due_date": "2025-02-15" },
      { "type": "performance_review", "title": "Öz Değerlendirme Q1", "due_date": "2025-03-01" }
    ]},
    "leave_balance": { "annual_remaining": 12.0, "sick_remaining": 5.0 },
    "current_shift": { "template": "Sabah 08-16", "date": "2025-02-03" },
    "last_payslip": { "period": "2025-01", "net_amount": 28500.00 },
    "announcements": [
      { "id": "ann-001", "title": "Yeni Yan Haklar Paketi", "priority": "important", "is_read": false }
    ]
  }
}
```

### 5.2 Görev Kutusu

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/tasks` | Bekleyen görevlerim | Auth |
| `GET` | `/me/tasks/count` | Görev badge sayısı | Auth |
| `PATCH` | `/me/tasks/{id}/complete` | Görevi tamamlandı işaretle | Auth |

### 5.3 Profil

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/profile` | Profil bilgilerim | Auth |
| `PATCH` | `/me/profile` | Doğrudan düzenlenebilir alanları güncelle | Auth |
| `POST` | `/me/profile-change-requests` | Değişiklik talebi oluştur | Auth |
| `GET` | `/me/profile-change-requests` | Taleplerim listesi | Auth |

**POST /me/profile-change-requests — İstek:**

```json
{
  "field_name": "iban",
  "new_value": "TR33 0006 1005 1978 6457 8413 26",
  "reason": "Banka değişikliği"
}
```

### 5.4 Duyurular

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/announcements` | Benim görmem gereken duyurular | Auth |
| `POST` | `/me/announcements/{id}/read` | Okundu işaretle | Auth |
| `POST` | `/portal/announcements` | Duyuru oluştur | `portal:announcement:create` |
| `PUT` | `/portal/announcements/{id}` | Duyuru güncelle | `portal:announcement:create` |
| `DELETE` | `/portal/announcements/{id}` | Duyuru sil | `portal:announcement:delete` |
| `GET` | `/portal/announcements/{id}/stats` | Okunma istatistikleri | `portal:announcement:create` |

### 5.5 Belgelerim

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/documents` | Belge listesi | Auth |
| `GET` | `/me/documents/{id}/download` | Belge indir (imzalı URL) | Auth |
| `POST` | `/me/documents` | Kişisel belge yükle | Auth |

### 5.6 Bildirimler

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/notifications` | Bildirim geçmişi | Auth |
| `POST` | `/me/notifications/mark-read` | Toplu okundu | Auth |
| `GET` | `/me/notification-preferences` | Tercihlerim | Auth |
| `PUT` | `/me/notification-preferences` | Tercihleri güncelle | Auth |

### 5.7 Yönetici Spesifik

| Method | Endpoint | Açıklama | Yetki |
|--------|----------|----------|-------|
| `GET` | `/me/team` | Ekip üyeleri | Auth + Manager |
| `GET` | `/me/team/calendar` | Takım takvimi (izin+vardiya) | Auth + Manager |
| `GET` | `/me/team/pending-approvals` | Onay bekleyenler | Auth + Manager |
| `POST` | `/me/team/pending-approvals/bulk-approve` | Toplu onayla | Auth + Manager |

---

## 6. Ekranlar ve Raporlar

### 6.1 Çalışan Ana Sayfa

```
┌─────────────────────────────────────────────────────────────────┐
│  Merhaba, Zeynep 👋                              🔔 3  [Profil]│
├───────────────┬────────────────────┬────────────────────────────┤
│ 📋 Görevlerim │ 🏖 İzin Bakiyem    │ 🕐 Bu Hafta Vardiyam      │
│    2 bekleyen │  Yıllık: 12 gün   │  Pzt-Cum: 08:00-16:00    │
│  [Görüntüle]  │  Hastalık: 5 gün  │  Cmt-Paz: —              │
│               │  [İzin Talep Et]  │                            │
├───────────────┴────────────────────┴────────────────────────────┤
│ 📄 Son Bordro Pusulam              │ 📚 Yaklaşan Eğitimler     │
│  Ocak 2025 — Net: ₺28.500         │  İSG Eğitimi — 15 Şubat  │
│  [İndir]                           │  [Detay]                  │
├─────────────────────────────────────────────────────────────────┤
│ 📢 Duyurular                                                    │
│  ⭐ Yeni Yan Haklar Paketi — 2 saat önce                [Tümü] │
│     Şubat'tan itibaren yeni yan haklar devreye giriyor...       │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Yönetici Ana Sayfa (Ek Bölüm)

```
┌─────────────────────────────────────────────────────────────────┐
│  Ekibim — Yazılım Departmanı                    12 kişi aktif  │
├───────────────┬────────────────────┬────────────────────────────┤
│ ⏳ Onay Bekley.│ 📅 Takım Takvimi   │ 📊 Ekip Performansı      │
│  İzin: 3      │  Bugün izinli: 2   │  Ort. Skor: 3.8/5       │
│  Mesai: 1     │  Yarın izinli: 0   │  Tamamlanan: 85%        │
│  [Hepsini Gör]│  [Takvimi Aç]      │  [Detay]                │
├───────────────┴────────────────────┴────────────────────────────┤
│  3 İzin Onay Bekliyor:                                          │
│  Ali Y. — 3 gün yıllık (10-12 Şubat)     [Onayla] [Reddet]    │
│  Fatma S. — 1 gün hastalık (3 Şubat)     [Onayla] [Reddet]    │
│  Emre D. — 5 gün yıllık (17-21 Şubat)    [Onayla] [Reddet]    │
│                                           [Tümünü Onayla]       │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Profil Ekranı

```
┌─────────────────────────────────────────────────────────────────┐
│  Profilim                                          [Fotoğraf]   │
├─────────────────────────────────────────────────────────────────┤
│  Kişisel Bilgiler                                   🔒          │
│  Ad Soyad: Zeynep Arslan          TC: ****1234                 │
│  Doğum Tarihi: 15.03.1992                                      │
│  [Değişiklik Talep Et]                                          │
├─────────────────────────────────────────────────────────────────┤
│  İletişim Bilgileri                                 ✏️           │
│  Telefon: 0532 XXX XX XX         E-posta: zeynep@sirket.com   │
│  Adres: İstanbul, Kadıköy...     [Düzenle]                    │
├─────────────────────────────────────────────────────────────────┤
│  İş Bilgileri                                       🔒          │
│  Pozisyon: Kıdemli UX Tasarımcı   Departman: Ürün Ekibi       │
│  İşe Giriş: 01.06.2020            Yönetici: Mehmet Kaya       │
├─────────────────────────────────────────────────────────────────┤
│  Banka Bilgileri                                    🔒          │
│  IBAN: TR33 **** **** **** **13 26    Banka: Garanti          │
│  [Değişiklik Talep Et]                                          │
└─────────────────────────────────────────────────────────────────┘
  🔒 Salt okunur alan   ✏️ Doğrudan düzenlenebilir
```

### 6.4 Bildirim Merkezi

```
┌─────────────────────────────────────────────────────────────────┐
│  Bildirimler                        [Tümünü Okundu İşaretle]   │
├─────┬───────────────────────────────┬──────────────┬───────────┤
│  ●  │ İzin talebiniz onaylandı     │ 2 saat önce  │ İzin      │
│  ●  │ Yeni duyuru: Yan Haklar      │ 3 saat önce  │ Duyuru    │
│  ○  │ Bordro pusulanız hazır       │ 1 gün önce   │ Bordro    │
│  ○  │ İSG eğitimi yaklaşıyor       │ 2 gün önce   │ Eğitim    │
└─────┴───────────────────────────────┴──────────────┴───────────┘
  ● Okunmamış   ○ Okunmuş
```

---

## 7. Celery Beat / Zamanlanmış Görevler

| Görev | Cron | Açıklama |
|-------|------|----------|
| `refresh_task_inbox` | Her 10 dk | Tüm modüllerden bekleyen görevleri portal_tasks tablosuna senkronize eder |
| `archive_expired_announcements` | Her gün 01:00 | Son geçerlilik tarihi geçmiş duyuruları arşivler |
| `send_task_reminder` | Her gün 09:00 | Süresi yaklaşan görevler için hatırlatma bildirimi gönderir |
| `cleanup_old_notifications` | Her hafta Pazar 02:00 | 90 günden eski bildirimleri siler |

---

## 8. Bildirim Şablonları

| Bildirim | Kanal | Alıcı | Tetikleyici |
|----------|-------|-------|-------------|
| Yeni görev | In-app + Push | Görev sahibi | Modüller görev oluşturduğunda |
| Görev hatırlatma | In-app + Push | Görev sahibi | Görev son tarihe 1 gün kala |
| Profil değişikliği onaylandı | In-app + E-posta | Çalışan | İK talebi onayladığında |
| Profil değişikliği reddedildi | In-app + E-posta | Çalışan | İK talebi reddettiğinde |
| Yeni duyuru | In-app | Hedef kitle | Duyuru yayınlandığında |
| Zorunlu duyuru hatırlatma | Push | Okumamış kullanıcılar | Acil duyuru 24 saat okunmamışsa |
| Karşılama mesajı | In-app + E-posta | Yeni çalışan | İlk giriş yapıldığında |

---

## 9. Güvenlik ve Uyumluluk

### 9.1 Kimlik ve Oturum

| Konu | Uygulama |
|------|----------|
| Kimlik doğrulama | SSO (OAuth2 / SAML) + MFA desteği |
| Token yönetimi | Access token: 15 dk, Refresh token: 7 gün |
| Oturum kısıtı | Eşzamanlı max oturum sayısı: tenant ayarı (varsayılan 3) |
| Mobil biyometri | Parmak izi / yüz tanıma ile hızlı giriş |

### 9.2 KVKK / GDPR

| Konu | Uygulama |
|------|----------|
| Profil verileri | Çalışan kendi verilerine erişim hakkı (KVKK Md. 11) |
| Bildirim tercihleri | Açık rıza ile yapılandırılır |
| Belge indirme | İmzalı URL, erişim loglanır |
| Veri silme hakkı | Hesap kapatıldığında kişisel veriler anonimleştirilir |

### 9.3 Rol-Erişim Matrisi

| Yetki | Süper Admin | İK Uzmanı | Dept. Yöneticisi | Çalışan |
|-------|:-----------:|:---------:|:----------------:|:-------:|
| Kendi dashboard | ✅ | ✅ | ✅ | ✅ |
| Yönetici dashboard | ✅ | ✅ | ✅ | ❌ |
| Kendi profil görüntüle | ✅ | ✅ | ✅ | ✅ |
| Profil değişiklik onayı | ✅ | ✅ | ❌ | ❌ |
| Duyuru CRUD | ✅ | ✅ | ❌ | ❌ |
| Ekip takım takvimi | ✅ | ✅ | ✅ (kendi ekip) | ❌ |
| Toplu onay | ✅ | ✅ | ✅ (kendi ekip) | ❌ |
| Bildirim tercihleri | ✅ | ✅ | ✅ | ✅ |
| Belge kasası (başkasının) | ✅ | ✅ | ❌ | ❌ |

---

## 10. Bağımlılıklar

| Modül | Kullanım |
|-------|----------|
| 10 – Personel | Profil ve çalışan bilgisi, belge kasası |
| 12 – İzin | İzin bakiye kartı, izin talebi, takım takvimi |
| 13 – Performans | Öz değerlendirme ve hedef görevleri |
| 14 – Bordro | Bordro pusulası erişimi |
| 15 – Eğitim | Eğitim atama görevleri, sertifika |
| 16 – Vardiya | Vardiya takvimi kartı, mesai onayı |
| 17 – Organizasyon | Şirket rehberi, organigram |
| 18 – Raporlama | Yönetici/İK dashboard KPI kartları |
| 25 – Yetkilendirme | Rol ve yetki kontrolü |

---

## 11. Modüller Arası Servis Arayüzü

```python
class PortalService:
    """Self-Servis portal servis arayüzü."""
    
    def create_task(
        self, user_id: UUID, task_type: str, source_module: str,
        source_id: UUID, title: str, due_date: datetime | None = None
    ) -> TaskDTO:
        """
        Herhangi bir modül tarafından çağrılır;
        kullanıcının görev kutusuna yeni görev ekler.
        """
        ...
    
    def complete_task(
        self, source_module: str, source_id: UUID
    ) -> None:
        """Kaynak modülde işlem tamamlandığında görevi bitirir."""
        ...
    
    def send_notification(
        self, user_id: UUID, category: str, title: str,
        body: str, action_url: str | None = None
    ) -> None:
        """
        Kullanıcıya bildirim gönderir;
        kullanıcı tercihlerine göre kanal(lar) seçilir.
        """
        ...
    
    def get_user_dashboard(
        self, user_id: UUID
    ) -> DashboardDTO:
        """Dashboard verilerini birleştirir; frontend tarafından çağrılır."""
        ...
```

---

## 12. Performans Gereksinimleri

| Metrik | Hedef |
|--------|-------|
| Dashboard yükleme (tüm kartlar) | < 1 saniye (p95) |
| Görev kutusu yükleme | < 300 ms (p95) |
| Bildirim listesi yükleme | < 200 ms (p95) |
| Duyuru listesi yükleme | < 200 ms (p95) |
| Profil sayfası yükleme | < 500 ms (p95) |
| WebSocket bildirim iletimi | < 500 ms (p99) |
| Belge indirme URL üretimi | < 100 ms |

---

## 13. Test Senaryoları

### 13.1 Birim Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| UT-01 | Rol bazlı dashboard kartları | Çalışan yönetici kartlarını görmez |
| UT-02 | Görev önceliklendirme algoritması | Süresi yakın görev en üstte |
| UT-03 | Duyuru hedef kitle filtresi | Farklı departman duyuruyu görmez |
| UT-04 | Profil değişiklik talebi (salt okunur alan) | İş akışı başlatılır |
| UT-05 | Profil doğrudan düzenleme (iletişim) | Anında güncellenir |
| UT-06 | Bildirim tercihi: e-posta kapalı | Bildirim sadece in-app |
| UT-07 | Okunma kaydı (duyuru) | İkinci okumada duplicate oluşmaz |

### 13.2 Entegrasyon Testler

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| IT-01 | İzin talebi oluşturma → yönetici görev kutusuna düşme | Görev PortalService üzerinden oluşturulur |
| IT-02 | İzin onayı → çalışan bildirimi | Bildirim ve görev güncellenir |
| IT-03 | Bordro kapanışı → pusulası belgelerime eklenmesi | Belge kasasında görünür |
| IT-04 | Duyuru yayınlama → hedef kitleye bildirim | Doğru kullanıcılara in-app bildirim gider |
| IT-05 | Profil onay akışı → personel modülü güncelleme | Profil değişikliği personel kaydını günceller |

### 13.3 E2E Testler

| # | Senaryo | Adımlar |
|---|---------|---------|
| E2E-01 | Çalışan tam akış | Login → Dashboard → İzin talep → Onay bekle → Bildirim al → Dashboard güncelle |
| E2E-02 | Yönetici onay akışı | Login → Onay kutusu → İzin onayla → Çalışana bildirim → Takvim güncelle |
| E2E-03 | Profil değişikliği | Profil → IBAN değişiklik talebi → İK onayı → Profil güncellendi |
| E2E-04 | Mobil bildirim akışı | Push bildirim al → Tıkla → Portal aç → İlgili sayfaya yönlen |

---

## 14. Kısıtlamalar ve Varsayımlar

| # | Not |
|---|-----|
| K1 | Portal offline desteği vermez; internet bağlantısı gereklidir |
| K2 | WebSocket bağlantısı düşerse bildirimler polling ile alınır (fallback) |
| K3 | Dashboard kart sıralaması ve görünürlüğü şimdilik backend config'ten gelir; kişiselleştirme Faz 3 |
| V1 | Tüm modüller PortalService.create_task arayüzünü kullanarak görev kutusu entegrasyonu sağlar |
| V2 | Bildirim gönderimleri asenkron (Celery) olarak yapılır |
| V3 | Belge kasasındaki dosyalar S3/MinIO'da tutulur; imzalı URL ile indirilir |
