# Import Şablonları ve Veri Hazırlık Planı

Bu doküman, pilot ve MVP onboarding için gerekli veri import şablonlarını, kolonları, validasyon kurallarını ve dry-run davranışını tanımlar.

## 1. Amaç

Pilot başarısının en kritik kısmı veri migrasyonudur. Bu nedenle çalışan, organizasyon ve izin bakiyesi importları koddan önce planlanmalıdır.

## 2. MVP import şablonları

| Şablon | Faz | Amaç |
|---|---|---|
| `employees.xlsx` | MVP | Çalışan ana verisi |
| `departments.xlsx` | MVP | Organizasyon birimleri |
| `positions.xlsx` | MVP | Pozisyon listesi |
| `leave_balances.xlsx` | MVP | Açılış izin bakiyeleri |
| `documents_metadata.xlsx` | MVP/V1 | Belge tipi ve geçerlilik bilgisi |
| `pdks_mapping.xlsx` | V1 | Cihaz kullanıcı ID eşleşmesi |

## 3. Çalışan import kolonları

| Kolon | Zorunlu | Örnek | Validasyon |
|---|---|---|---|
| `employee_number` | Evet | EMP-001 | Tenant içinde unique |
| `first_name` | Evet | Ayşe | Boş olamaz |
| `last_name` | Evet | Yılmaz | Boş olamaz |
| `email` | Hayır | ayse@example.com | Format kontrolü |
| `phone` | Hayır | +905... | Format kontrolü |
| `employment_start_date` | Evet | 2026-09-01 | Tarih formatı |
| `employment_status` | Evet | active | Enum |
| `department_code` | Evet | HR | Department importunda var olmalı |
| `position_code` | Hayır | HR-SPEC | Position importunda var olmalı |
| `manager_employee_number` | Hayır | EMP-010 | Mevcut çalışan olmalı |
| `national_id` | Hayır | 11111111110 | Masking/encryption planına tabi |

## 4. Departman import kolonları

| Kolon | Zorunlu | Örnek | Validasyon |
|---|---|---|---|
| `department_code` | Evet | HR | Unique |
| `department_name` | Evet | İnsan Kaynakları | Boş olamaz |
| `parent_department_code` | Hayır | HQ | Varsa mevcut olmalı |
| `manager_employee_number` | Hayır | EMP-010 | Mevcut çalışan olmalı |

## 5. Pozisyon import kolonları

| Kolon | Zorunlu | Örnek | Validasyon |
|---|---|---|---|
| `position_code` | Evet | HR-SPEC | Unique |
| `position_title` | Evet | İK Uzmanı | Boş olamaz |
| `department_code` | Evet | HR | Mevcut olmalı |
| `job_level` | Hayır | specialist | Enum/serbest metin |

## 6. İzin bakiyesi import kolonları

| Kolon | Zorunlu | Örnek | Validasyon |
|---|---|---|---|
| `employee_number` | Evet | EMP-001 | Mevcut çalışan |
| `leave_type_code` | Evet | ANNUAL | Tanımlı izin türü |
| `period_year` | Evet | 2026 | Sayı |
| `opening_balance_days` | Evet | 14 | Negatif olamaz |
| `used_days` | Hayır | 3 | Negatif olamaz |

## 7. Dry-run davranışı

Dry-run şunları üretir:

- Toplam satır.
- Başarılı satır.
- Hatalı satır.
- Uyarılı satır.
- Duplicate satır.
- Bilinmeyen referanslar.
- Commit sonrası oluşacak yeni/güncellenecek kayıt sayısı.

## 8. Hata kodları

| Kod | Anlam |
|---|---|
| `IMPORT_REQUIRED_FIELD_MISSING` | Zorunlu alan eksik |
| `IMPORT_INVALID_DATE` | Tarih formatı hatalı |
| `IMPORT_DUPLICATE_KEY` | Unique alan tekrar ediyor |
| `IMPORT_UNKNOWN_REFERENCE` | Referans kayıt yok |
| `IMPORT_INVALID_ENUM` | Geçersiz enum değeri |
| `IMPORT_SENSITIVE_FIELD_BLOCKED` | Hassas alan policy gereği alınmadı |

## 9. Pilot veri hazırlık checklist'i

- Müşteri HR export formatı alındı.
- Çalışan sayısı ve alan kalitesi analiz edildi.
- Departman/pozisyon kodları normalize edildi.
- E-posta olmayan çalışanlar için aktivasyon yöntemi belirlendi.
- Hassas alanların import edilip edilmeyeceği onaylandı.
- Dry-run raporu müşteriyle paylaşıldı.
- Commit öncesi onay alındı.

## 10. Kabul kriterleri

- MVP için minimum üç şablon net: employees, departments, leave_balances.
- Her kolonun zorunluluk ve validasyon kuralı vardır.
- Dry-run commit'ten ayrıdır.
- Hatalı satır kullanıcıya anlaşılır döner.
- Gerçek veri local/dev ortamlarına girmez.

## 11. Müşteri sorumlulukları

Pilot başlamadan müşteri tarafında şu hazırlıklar istenmelidir:

- Güncel çalışan listesinin tek dosyada çıkarılması.
- Departman ve pozisyon adlarının normalize edilmesi.
- İşten ayrılmış çalışanların ayrı işaretlenmesi.
- Yönetici ilişkilerinin employee number ile kurulması.
- Eksik e-posta veya telefon kayıtları için alternatif aktivasyon yönteminin belirlenmesi.
- Hassas alanların paylaşımı için yetkili kişinin yazılı onay vermesi.

Bu hazırlıklar yapılmadan import commit edilmemelidir. Dry-run raporu müşteriyle birlikte okunmalı, kritik hatalar kapatılmadan canlı tenant'a veri alınmamalıdır.

## 12. İlgili dokümanlar

- [Veri Migrasyonu, Import ve Export](../05-api-veri/04-veri-migrasyonu-import-export.md)
- [Wireframe ve Ekran Akış Planı](05-wireframe-ekran-akis-plani.md)
- [ERD ve Migration Uygulama Planı](04-erd-migration-uygulama-plani.md)
