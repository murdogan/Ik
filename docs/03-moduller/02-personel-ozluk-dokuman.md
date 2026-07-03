# Personel, Özlük ve Doküman Yönetimi Modülü

Bu doküman, IK Platform'un çalışan ana verisi, özlük dosyası ve çalışan belgeleri yönetimi kapsamını tanımlar. EMP ve DOC modülleri MVP'de birlikte ele alınır; çünkü çalışan kartı, belge checklist'i ve self-servis belge akışı ürünün ilk değer zincirlerinden biridir.

## 1. Amaç ve karar özeti

Personel ve özlük modülü, tüm İK operasyonunun ana veri kaynağıdır. İzin, self-servis, raporlama, ileride bordro, performans, eğitim ve analytics süreçleri employee kaydına dayanır.

Karar özeti:

> MVP'de çalışan master data, temel özlük alanları, belge yükleme, zorunlu belge takibi, çalışan self-servis görüntüleme ve audit çalışmalıdır. Ücret geçmişi, gelişmiş onboarding/offboarding, e-imza ve native bordro entegrasyonu sonraki fazlara bırakılır.

Bu modülün başarısı, ürünün “tek çalışan veri modeli” farklılaşmasını doğrudan belirler.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Çalışan kaydı oluşturma ve güncelleme | Native bordro hesaplama |
| Employee master data | Gelişmiş performans/talent profili |
| Temel iş bilgileri | Karmaşık global worker tipleri |
| Departman, pozisyon, yönetici bağlantıları | Gelişmiş kadro planlama |
| Özlük belge yükleme | Tam DMS ürünü |
| Belge türü ve zorunlu belge checklist'i | E-imza zorunlu entegrasyonu |
| Geçerlilik tarihi ve belge uyarıları | Otomatik resmi kurum bildirimi |
| Self-servis profil görüntüleme | Tüm alanların çalışanca serbest güncellenmesi |
| Profil güncelleme talebi | Karmaşık approval builder |
| Toplu import/dry-run | Tüm dış HR sistemlerinden hazır migrasyon |
| Audit ve hassas alan maskeleme | Gelişmiş DLP ve OCR sınıflandırma |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `hr_director` | Tüm çalışan verisini ve raporları yönetir/görür | Tenant | Hassas alan erişimi sınırsız olmamalı |
| `hr_specialist` | Çalışan kartı, belge, özlük ve import işlemlerini yürütür | Tenant veya branch/department | Gereksiz maaş/sağlık verisi görmemeli |
| `employee` | Kendi profilini ve belgelerini görür, belirli alanlar için değişiklik talep eder | Own | Başkasının belgesine erişmemeli |
| `manager` | Ekibinin sınırlı iş bilgilerini görür | Team | TCKN, IBAN, maaş, sağlık belgesi görmemeli |
| `payroll_specialist` | Bordroya esas alanları okur | Payroll field permission | Özlük alanlarını izinsiz değiştirmemeli |
| `tenant_admin` | Belge tipleri ve alan politikalarını yönetir | Tenant admin | İçerik verisine gereksiz erişmemeli |
| `auditor` | Kayıt ve erişim izlerini inceler | Read-only | Veri değiştirmemeli |
| `it_admin` | Hesap yaşam döngüsü entegrasyonunu izler | Security/integration | İK içerik verisine varsayılan erişmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Çalışan kartı oluşturma/güncelleme.
- Temel kişisel ve iş bilgileri.
- Employee number tenant içinde benzersizliği.
- Departman, pozisyon ve yönetici ilişkisi.
- Temel belge yükleme.
- Belge tipi katalogu.
- Zorunlu belge checklist'i.
- Geçerlilik tarihi ve eksik belge raporu.
- Çalışan self-servis profil görüntüleme.
- Profil güncelleme talebi için temel akış.
- Toplu import dry-run ve hata raporu.
- Hassas alan maskeleme ve audit.

### V1

- Gelişmiş onboarding/offboarding checklist.
- Effective-dated assignment geçmişi.
- Gelişmiş belge şablonları.
- E-imza entegrasyonu.
- Bordro export için gerekli alanların doğrulama paketi.
- Çalışan yaşam döngüsü timeline'ı.
- Mobil belge yükleme ve fotoğraf/PDF iyileştirmeleri.

### V2

- Gelişmiş DMS özellikleri.
- OCR ve belge sınıflandırma.
- Saklama/imha otomasyonu.
- Gelişmiş yaşam döngüsü otomasyonları.
- Çok ülkeli worker tipleri.
- AI destekli eksik belge ve veri kalite önerileri.

### Enterprise

- Büyük ölçekli migrasyon araçları.
- Gelişmiş field-level policy.
- DLP entegrasyonu.
- Dedicated storage policy.
- Enterprise audit/export ve legal hold.

## 5. Ana kullanıcı akışları

### 5.1 Çalışan oluşturma

1. `hr_specialist` yeni çalışan kartı açar.
2. Zorunlu kişisel ve iş alanlarını girer.
3. Departman, pozisyon ve yönetici ilişkisini belirler.
4. Sistem employee number benzersizliğini ve zorunlu alanları kontrol eder.
5. Varsayılan belge checklist'i oluşur.
6. `employee.created` audit eventi yazılır.

### 5.2 Toplu import

1. HR import şablonunu indirir.
2. Çalışan listesini yükler.
3. Sistem dry-run validasyon yapar.
4. Hatalı satırlar hata nedeni ile gösterilir.
5. HR düzeltip tekrar yükler.
6. Commit sonrası çalışan kayıtları oluşur ve import summary audit'e düşer.

### 5.3 Belge yükleme ve doğrulama

1. HR veya çalışan belge yükler.
2. Belge tipi seçilir.
3. Sistem dosya tipi, boyut ve güvenlik kontrollerini yapar.
4. Belge çalışan özlük dosyasına bağlanır.
5. Hassas belge ise görünürlük policy'si uygulanır.
6. `document.uploaded` audit eventi yazılır.

### 5.4 Self-servis profil görüntüleme

1. Çalışan self-servis portalına girer.
2. Kendi profilini görüntüler.
3. Hassas alanlar maskeli gösterilir.
4. Düzenlenebilir alanlar ve talep gerektiren alanlar ayrılır.
5. Görüntüleme ve hassas alan erişimleri policy'ye göre auditlenir.

### 5.5 Profil güncelleme talebi

1. Çalışan adres, telefon veya IBAN gibi alan için değişiklik talebi açar.
2. Sistem alan politikasını kontrol eder.
3. Basit alanlar otomatik onaylanabilir; kritik alanlar HR onayına düşer.
4. IBAN gibi finansal alanlar çift kontrol veya step-up gerektirebilir.
5. Onay sonrası employee kaydı güncellenir ve audit'e önce/sonra bilgisi yazılır.

### 5.6 İşten ayrılış

MVP'de sınırlı, V1'de detaylı ele alınır.

1. HR işten ayrılış tarihini ve nedenini girer.
2. Çalışan statüsü `terminated` olur.
3. Gelecek tarihli izin ve açık talepler kontrol edilir.
4. JML/IT görevleri V1'de tetiklenir.
5. Arşiv ve saklama süreci başlar.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| Çalışan Listesi | Arama, filtre, durum, departman, hızlı aksiyon | MVP |
| Çalışan Kartı / Employee 360 | Kişisel, iş, organizasyon, belge, izin özeti | MVP |
| Belge Sekmesi | Belge listesi, yükleme, geçerlilik, görünürlük | MVP |
| Özlük Checklist | Zorunlu/eksik/tamam belge durumu | MVP |
| Profilim | Çalışan kendi bilgilerini görür | MVP |
| Profil Değişiklik Talebi | Düzenlenebilir alanlar ve onay akışı | MVP sınırlı |
| Toplu Import | Mapping, dry-run, hata raporu, commit | MVP |
| Timeline | Çalışan yaşam döngüsü geçmişi | V1 |
| Offboarding Sihirbazı | Çıkış görevleri, belge, erişim kapama | V1 |

Deneyim notları:

- İK paneli tablo/filtre/export açısından güçlü olmalı.
- Çalışan ekranı sade olmalı; TCKN/IBAN gibi alanlar maskeli görünmeli.
- Belge yükleme mobilde fotoğraf çekme/PDF yükleme senaryosunu desteklemeli.
- Import hataları teknik değil, satır bazlı ve anlaşılır gösterilmeli.

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `employees` | Çalışan ana kaydı | `tenant_id`, `employee_number`, `status`, `user_id`, `created_at` |
| `employee_profiles` | Kişisel bilgiler | `first_name`, `last_name`, `birth_date`, `national_id_encrypted`, `phone`, `address` |
| `employee_employments` | İş ilişkisi | `start_date`, `end_date`, `contract_type`, `work_type`, `status` |
| `employee_assignments` | Departman/pozisyon/yönetici ilişkisi | `department_id`, `position_id`, `manager_id`, `valid_from`, `valid_to` |
| `employee_documents` | Özlük belge kayıtları | `employee_id`, `document_type_id`, `storage_key`, `valid_until`, `sensitivity` |
| `document_types` | Belge tipi kataloğu | `code`, `name`, `required_rules`, `has_expiry`, `sensitivity` |
| `profile_change_requests` | Self-servis değişiklik talepleri | `employee_id`, `field_group`, `payload`, `status`, `decided_by` |
| `employee_import_jobs` | Toplu import işlemleri | `status`, `file_key`, `summary`, `created_by` |
| `employee_import_errors` | Import hata satırları | `row_number`, `field`, `message`, `severity` |

Veri modeli kararları:

- `tenant_id` tüm tablolarda zorunludur.
- TCKN, IBAN ve sağlık/özel nitelikli veri şifreli tutulmalıdır.
- Arama için hassas alanlarda plaintext index kullanılmamalıdır; gerekiyorsa blind index tasarlanmalıdır.
- Hard delete yerine statü/arşiv/saklama yaklaşımı kullanılmalıdır.

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/employees` | Filtreli çalışan listesi | MVP |
| POST | `/api/v1/employees` | Çalışan oluşturma | MVP |
| GET | `/api/v1/employees/{id}` | Employee 360 detay | MVP |
| PATCH | `/api/v1/employees/{id}` | Çalışan güncelleme | MVP |
| POST | `/api/v1/employees/imports` | Import dry-run başlatma | MVP |
| GET | `/api/v1/employees/imports/{id}` | Import sonucu | MVP |
| POST | `/api/v1/employees/{id}/documents` | Belge yükleme | MVP |
| GET | `/api/v1/employees/{id}/documents` | Belge listesi | MVP |
| GET | `/api/v1/document-types` | Belge tipi listesi | MVP |
| POST | `/api/v1/profile-change-requests` | Profil değişiklik talebi | MVP |
| POST | `/api/v1/profile-change-requests/{id}/approve` | Talep onayı | MVP/V1 |
| POST | `/api/v1/employees/{id}/terminate` | İşten ayrılış başlatma | V1 |
| GET | `/api/v1/employees/{id}/timeline` | Yaşam döngüsü timeline | V1 |

Entegrasyon etkileri:

- AUTH/RBAC: Kullanıcı hesabı, own/team scope ve field masking.
- ORG: Departman, pozisyon ve yönetici ilişkileri.
- LEAVE: İzin hakkı ve onay akışları employee kaydına bağlıdır.
- SS: Çalışan profil ve belge self-servisi.
- REP: Headcount, eksik belge ve çalışan raporları.
- PAY/TIME: V1/V2'de bordro ve puantaj için employee/employment verisi.

## 9. Yetki, scope ve güvenlik kuralları

| İşlem | `employee` | `manager` | `hr_specialist` | `hr_director` | `payroll_specialist` | `auditor` |
|---|---|---|---|---|---|---|
| Kendi profilini okuma | Own | - | Tenant/scope | Tenant | Sınırlı | Read-only |
| Ekip profilini okuma | - | Team sınırlı | Scope | Tenant | Sınırlı | Read-only |
| Çalışan oluşturma | Hayır | Hayır | Evet | Evet | Hayır | Hayır |
| Hassas alan tam görüntüleme | Own maskeli | Hayır | Permission'a bağlı | Permission'a bağlı | Bordro alanları | Gerekçeli/read-only |
| Belge yükleme | Own talep | Hayır | Evet | Evet | Bordro belgesi | Hayır |
| Belge indirme | Own izinli | Hayır | Permission'a bağlı | Permission'a bağlı | Bordro belgesi | Permission'a bağlı |
| Import | Hayır | Hayır | Evet | Evet | Hayır | Hayır |
| Export | Hayır | Team sınırlı? | Permission | Permission | Bordro alanı | Read-only/export permission |
| Silme/anonimleştirme | Hayır | Hayır | Talep | Onay | Hayır | Denetler |

Güvenlik kuralları:

- Employee kendi kaydı dışında hiçbir çalışan kaydına erişemez.
- Manager maaş, TCKN, IBAN, sağlık raporu gibi alanları görmez.
- Belge download pre-signed URL tenant ve permission kontrolünden sonra üretilir.
- Export görüntüleme yetkisinden ayrı permission ister.
- Hassas alan görüntüleme auditlenir.

## 10. KVKK, audit ve saklama gereksinimleri

| Veri tipi | Sınıf | Kontrol |
|---|---|---|
| Ad, soyad, iletişim | Kişisel veri | Aydınlatma, yetki, saklama |
| TCKN/YKN/pasaport | Hassas kişisel veri niteliğinde yüksek riskli | Şifreleme, maskeleme, audit |
| IBAN | Finansal kişisel veri | Şifreleme, çift onay, audit |
| Sağlık raporu/engellilik | Özel nitelikli veri | Ayrı permission, güçlü audit, minimizasyon |
| Maaş/ücret | Finansal/İK hassas veri | Field permission ve maskeleme |
| Belgeler | Karma veri | Belge tipi bazlı sensitivity ve retention |

Audit eventleri:

- `employee.created`
- `employee.updated`
- `employee.status_changed`
- `employee.sensitive_field.viewed`
- `employee.import.started`
- `employee.import.completed`
- `document.uploaded`
- `document.viewed`
- `document.downloaded`
- `document.deleted_or_archived`
- `profile_change.requested`
- `profile_change.approved`
- `profile_change.rejected`

Saklama kararı: MVP'de belge ve çalışan verisi için retention metadata tutulmalıdır; otomatik imha/anonimleştirme V2'de derinleşebilir.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal | Faz |
|---|---|---|---|
| Eksik belge var | Çalışan, HR | In-app/e-posta/push | MVP |
| Belge geçerliliği yaklaşıyor | HR, çalışan | In-app/e-posta | MVP/V1 |
| Profil değişiklik talebi açıldı | HR | In-app | MVP |
| Profil talebi onaylandı/reddedildi | Çalışan | In-app/e-posta | MVP |
| Import tamamlandı | HR | In-app/e-posta | MVP |
| İşten çıkış görevleri | HR, IT, manager | In-app/e-posta | V1 |

Arka plan işler:

- Belge geçerlilik hatırlatmaları.
- Eksik belge raporu snapshot'ı.
- Import job işleme ve hata üretimi.
- Belge virüs taraması / güvenlik kontrolü.
- Arşiv ve retention uyarıları.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Employee number tenant içinde benzersiz |
| Unit | TCKN/IBAN format ve masking fonksiyonları |
| Unit | Belge tipi required rule değerlendirmesi |
| Integration | Çalışan oluşturma → belge checklist oluşması |
| Integration | Belge yükleme → metadata → audit |
| Integration | Profil değişiklik talebi → onay → kayıt güncelleme |
| Integration | Import dry-run → hata satırları |
| E2E | HR çalışan oluşturur, çalışan self-serviste profilini görür |
| E2E | Employee izinli belgeyi görüntüler, yetkisiz belgeyi göremez |
| Security | Manager maaş/TCKN/IBAN göremez |
| Security | Tenant A belge URL'i Tenant B tarafından açılamaz |
| Performance | Büyük çalışan listesinde filtreleme ve arama |

## 13. Kabul kriterleri

- HR yetkili kullanıcı çalışan oluşturabilir ve güncelleyebilir.
- Employee number tenant içinde benzersizdir.
- Çalışan kartı departman/pozisyon/yönetici ilişkisini taşır.
- Belge yüklenebilir ve çalışanla ilişkilendirilebilir.
- Zorunlu belge checklist'i ve eksik belge raporu üretilebilir.
- Çalışan kendi profilini self-servisten görebilir.
- Profil değişiklik talebi oluşturulabilir ve onaylanabilir/reddedilebilir.
- Hassas alanlar yetkisiz kullanıcıya maskeli veya gizli gelir.
- Tüm belge görüntüleme/indirme işlemleri audit'e düşer.
- Import dry-run hatalı satırları anlaşılır şekilde gösterir.
- Tenant dışı hiçbir employee/document kaydı dönmez.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Employee modeli zayıf kurulursa tüm modüller etkilenir | MVP'de dar ama sağlam master data modeli kurulmalı |
| Risk | Belge yönetimi DMS'e dönüşürse kapsam şişer | MVP belge metadata + dosya + checklist ile sınırlı |
| Risk | Hassas belge erişimi yanlış tasarlanırsa KVKK riski oluşur | Sensitivity + field/document permission + audit zorunlu |
| Risk | Import zayıf olursa onboarding çok zaman alır | Dry-run ve satır bazlı hata MVP'de olmalı |
| Açık soru | TCKN doğrulaması MVP'de checksum ile mi sınırlı olacak? | Resmi kurum doğrulaması MVP dışı |
| Açık soru | E-imza entegrasyonu hangi fazda gelecek? | V1 adayı, pilot ihtiyacına göre |
| Açık soru | Mavi yaka belge yüklemesi mobil fotoğrafla yapılacak mı? | PWA testlerinde doğrulanacak |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [CORE, AUTH ve RBAC Modülleri](01-core-auth-rbac.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
- [Personalar, JTBD ve Kullanıcı Yolculukları](../02-urun/01-personalar-jtbd-ve-kullanici-yolculuklari.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [Ürün Metrikleri ve Başarı Kriterleri](../02-urun/04-urun-metrikleri-ve-basari-kriterleri.md)
