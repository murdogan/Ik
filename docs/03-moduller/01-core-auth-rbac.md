# CORE, AUTH ve RBAC Modülleri

Bu doküman, IK Platform'un tenant çekirdeği, kimlik doğrulama ve yetkilendirme katmanını tanımlar. Bu üç modül ayrı teknik alanlar olsa da MVP'de birlikte düşünülmelidir; çünkü tenant izolasyonu, kullanıcı girişi, rol/scope ve hassas alan maskeleme olmadan hiçbir İK verisi güvenli şekilde canlıya alınamaz.

## 1. Amaç ve karar özeti

CORE, AUTH ve RBAC ürünün temel güvenlik ve platform iskeletidir.

- **CORE:** Tenant, kurum, plan, lisans, feature flag ve temel sistem ayarlarını yönetir.
- **AUTH:** Kullanıcı kimliği, login, parola, oturum, refresh token ve MFA hazırlığını yönetir.
- **RBAC:** Rol, permission, scope, alan bazlı maskeleme ve yetki kararlarını yönetir.

MVP kararı:

> İlk canlıya çıkışta tenant izolasyonu, kullanıcı girişi, temel roller, own/team/tenant scope, audit ve hassas alan maskeleme çalışmadan ürün canlıya alınamaz.

Bu modül seti doğrudan [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md) dokümanındaki CORE, AUTH, RBAC ve KVKK kararlarını destekler.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Tenant oluşturma ve temel kurum ayarları | Çok ülkeli karmaşık tenant hiyerarşisi |
| Kullanıcı oluşturma, davet ve aktivasyon | Tam SCIM provisioning |
| E-posta/şifre login | SAML/OIDC SSO'nun tam enterprise uygulanması |
| Oturum ve refresh token yönetimi | Passwordless/passkey ilk sürüm |
| Temel MFA hazırlığı | Zorunlu gelişmiş risk motoru |
| Roller ve permission katalogu | Görsel ABAC policy editörü |
| Own/team/tenant scope | Karmaşık matris organizasyon yetkisi |
| Hassas alan maskeleme | Tam DLP ürünü |
| Audit event üretimi | SIEM export |
| Feature flag ve plan kontrolü | Karmaşık usage-based billing |

Kapsam dışı maddeler ürün vizyonundan çıkarılmış değildir; V1, V2 veya Enterprise fazına ertelenmiştir.

F1A current implementation boundary:

- Yalnız tenant lifecycle, plan/region/locale/timezone, fixed typed settings ve yedi
  platform/tenant operation'ı uygulanır. Authentication/session/RBAC, audit persistence, RLS,
  feature flags ve legal entity F1A'ya dahil değildir.
- Platform/tenant authorization caller header'ından gelmez. Trusted injected
  `PlatformPrincipal`/`TenantPrincipal` yoksa dependency `403` ile fail closed olur; Phase 2 auth
  bu seam'i dolduracaktır.
- Success body'ler Faz 1.2 `{data, meta}` compatibility geçişine kadar doğrudan typed object/list'tir.

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `super_admin` | Platform seviyesinde tenant oluşturur ve yönetir | Global/platform | Müşteri verisine gereksiz erişim olmamalı |
| `tenant_admin` | Kurum ayarları, kullanıcılar, roller ve plan ayarlarını yönetir | Tenant | Fazla yetki verilirse hassas veri açığa çıkar |
| `hr_director` | İK süreçleri için geniş tenant erişimi kullanır | Tenant / HR scope | Maaş/özel veri görünürlüğü kontrollü olmalı |
| `hr_specialist` | Operasyonel İK verisine erişir | Department/branch/tenant | Kapsam dışı çalışan görmemeli |
| `manager` | Kendi ekibini görür ve onay verir | Team scope | Maaş/TCKN gibi alanları görmemeli |
| `employee` | Kendi profili, izinleri ve belgelerini görür | Own scope | Başka çalışanın verisine erişmemeli |
| `payroll_specialist` | Bordroya esas alanları görür | Payroll field permission | İK dışı alanları değiştirmemeli |
| `it_admin` | Kullanıcı, oturum, güvenlik ve entegrasyon ayarlarını yönetir | Security/admin scope | İK içeriğine varsayılan erişmemeli |
| `auditor` | Audit kayıtlarını ve uyum çıktısını inceler | Read-only | Veri değiştirmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Tenant kaydı ve temel kurum ayarları.
- Kullanıcı daveti ve aktivasyonu.
- E-posta/şifre login.
- Güvenli parola saklama.
- Oturum ve refresh token yönetimi.
- Temel MFA altyapısı veya MFA-ready tasarım.
- Varsayılan roller.
- Permission naming standardı.
- Own/team/tenant scope.
- Hassas alan maskeleme.
- Audit event üretimi.
- Feature flag temel yapısı.

### V1

- OIDC tabanlı SSO başlangıcı.
- Gelişmiş MFA politikaları.
- Cihaz/oturum yönetimi ekranı.
- API key / service account yönetimi.
- Delegasyon ve vekalet yetkisi.
- Daha granular permission setleri.
- Plan/lisans sayaç raporları.

### V2

- Risk bazlı doğrulama.
- Daha gelişmiş ABAC kural motoru.
- Field-level policy editor.
- Usage metering ve gelişmiş paket sınırları.
- Break-glass destek erişimi governance.

### Enterprise

- SAML 2.0 / gelişmiş OIDC SSO.
- SCIM provisioning.
- IP allowlist.
- SIEM audit export.
- Dedicated tenant / dedicated DB opsiyonlarıyla uyum.
- Enterprise SLA ve security review paketleri.

## 5. Ana kullanıcı akışları

### 5.1 Tenant oluşturma

1. `super_admin` yeni tenant oluşturur.
2. Tenant adı, şirket kodu, ülke, saat dilimi ve varsayılan dil girilir.
3. İlk `tenant_admin` kullanıcısı oluşturulur.
4. Varsayılan feature flag ve plan ayarları atanır.
5. Sistem `tenant.created` ve `user.invited` eventlerini üretir.
6. Tenant admin aktivasyon linkiyle hesabını kurar.

### 5.2 Kullanıcı daveti ve aktivasyon

1. `tenant_admin` veya yetkili HR kullanıcısı kullanıcı daveti oluşturur.
2. Davet ilgili employee kaydıyla bağlanabilir.
3. Kullanıcı e-posta veya alternatif aktivasyon yöntemiyle parolasını belirler.
4. İlk login sonrası profil ve güvenlik ayarları tamamlanır.
5. Sistem `user.activated` eventini yazar.

### 5.3 Login ve oturum yenileme

1. Kullanıcı tenant domain/kurum kodu/e-posta ile giriş ekranına gelir.
2. E-posta/şifre doğrulanır.
3. Risk veya policy gerektiriyorsa MFA challenge çalışır.
4. Access token kısa ömürlü, refresh token rotation ile verilir.
5. Refresh token tekrar kullanımı tespit edilirse session family revoke edilir.

### 5.4 Yetki kararı

1. Request tenant context ile başlar.
2. Kullanıcının rol ve permission seti alınır.
3. Scope değerlendirilir: own, team, department, branch, tenant.
4. Field policy uygulanır: allow, mask, deny veya step-up.
5. Response sadece yetkili alanları içerir.
6. Hassas görüntüleme gerekiyorsa audit event yazılır.

### 5.5 Rol değişikliği

1. `tenant_admin` kullanıcı rolünü değiştirir.
2. Sistem değişikliğin kritik olup olmadığını değerlendirir.
3. Kritik rol artışında gerekçe ve ikinci onay istenebilir.
4. Aktif session'lar permission version ile yenilenir veya revoke edilir.
5. `permission.changed` audit eventi yazılır.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| Tenant Ayarları | Şirket adı, saat dilimi, dil, temel ayarlar | MVP |
| Kullanıcılar | Kullanıcı listesi, davet, aktif/pasif, rol atama | MVP |
| Roller ve Yetkiler | Varsayılan roller ve permission görünümü | MVP sınırlı |
| Oturumlar | Aktif session listesi ve revoke | V1 |
| Güvenlik Ayarları | Parola, MFA, domain policy | MVP/V1 |
| Feature Flags | Plan ve modül aç/kapa | MVP internal |
| Audit | Kritik login, rol, export ve veri görüntüleme olayları | MVP |
| SSO Ayarları | OIDC/SAML yapılandırması | V1/Enterprise |

Deneyim kararı: MVP'de roller tamamen serbest özelleştirilebilir bir editörle başlamamalıdır. Önce iyi tasarlanmış varsayılan roller ve sınırlı ayar seçenekleri sunulmalıdır.

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `tenants` | Müşteri/kurum hesabı | `id`, `slug`, `name`, `status`, `plan_code`, `data_region`, `locale`, `timezone` |
| `tenant_settings` | F1A fixed kurum ayarları | `tenant_id`, `week_start_day`, `date_format`, `time_format`, timestamps; arbitrary key/value yok |
| `plans` | İleri-faz paket/limit katalogu | F1A ayrı plan tablosu kurmaz; canonical write kodları `core`, `professional`, `enterprise` |
| `feature_flags` | İleri-faz modül aç/kapa | F1A tablo veya `/api/v1/tenant/features` endpoint'i eklemez |
| `users` | Login kimliği | `id`, `tenant_id`, `email`, `password_hash`, `status` |
| `user_identities` | SSO/harici kimlik | `provider`, `subject`, `user_id` |
| `sessions` | Oturum ve cihaz bilgisi | `user_id`, `device_id`, `refresh_family_id`, `revoked_at` |
| `roles` | Rol tanımı | `tenant_id`, `code`, `name`, `system_role` |
| `permissions` | Yetki katalogu | `resource`, `action`, `scope`, `field` |
| `role_permissions` | Rol-permission eşleşmesi | `role_id`, `permission_id` |
| `user_roles` | Kullanıcı rol ataması | `user_id`, `role_id`, `valid_from`, `valid_to` |
| `field_policies` | Alan bazlı görünürlük | `resource`, `field`, `classification`, `policy` |
| `audit_events` | Kritik olay kaydı | `tenant_id`, `actor_id`, `event`, `resource`, `metadata` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| POST | `/api/v1/platform/tenants` | Platform-safe tenant provisioning | F1A |
| GET | `/api/v1/platform/tenants` | Metadata/plan/region/lifecycle health listesi; HR veri yok | F1A |
| GET | `/api/v1/platform/tenants/{tenant_id}` | Platform-safe tenant metadata detayı | F1A |
| PATCH | `/api/v1/platform/tenants/{tenant_id}` | Explicit lifecycle/typed metadata değişikliği | F1A |
| GET | `/api/v1/tenant` | Injected principal current tenant metadata | F1A |
| GET | `/api/v1/tenant/settings` | Beş typed setting | F1A |
| PATCH | `/api/v1/tenant/settings` | Fixed allowlist partial update | F1A |
| POST | `/api/v1/auth/login` | Login başlatır | MVP |
| POST | `/api/v1/auth/refresh` | Token yeniler | MVP |
| POST | `/api/v1/auth/logout` | Session kapatır | MVP |
| POST | `/api/v1/users/invite` | Kullanıcı daveti oluşturur | MVP |
| GET | `/api/v1/users` | Tenant kullanıcılarını listeler | MVP |
| PATCH | `/api/v1/users/{id}` | Kullanıcı durum/temel bilgi günceller | MVP |
| GET | `/api/v1/roles` | Roller ve permission görünümü | MVP |
| POST | `/api/v1/roles/{id}/assign` | Rol atar | MVP |
| GET | `/api/v1/me` | Aktif kullanıcı/rol/scope bilgisi | MVP |
| GET | `/api/v1/audit-events` | Audit filtreleme | MVP |
| GET | `/api/v1/me/sessions` | Kullanıcının session listesi | V1 |
| DELETE | `/api/v1/me/sessions/{id}` | Session revoke | V1 |
| POST | `/api/v1/sso/oidc` | OIDC ayarı | V1 |
| POST | `/api/v1/scim/v2/Users` | SCIM provisioning | Enterprise |

## 9. Yetki, scope ve güvenlik kuralları

| Kural | Açıklama |
|---|---|
| F1A principal default-deny | Injected trusted platform/tenant principal yoksa `403`; header/path/body kimliği authorization değil |
| Tenant context body'den alınmaz | Tenant token, subdomain veya session context'ten gelir |
| Her sorgu tenant filtreli olmalı | App katmanı ve tercihen DB RLS ile korunur |
| Kullanıcı global unique olmak zorunda değil | Aynı e-posta farklı tenantlarda olabilir; login tenant-aware olmalı |
| Access token kısa ömürlü olmalı | 10-15 dk aralığı hedeflenir |
| Refresh token rotation zorunlu | Reuse detection ile çalınan token fark edilir |
| Parola hash'i güçlü olmalı | Argon2id veya eşdeğer güçlü hash kullanılmalı |
| Kritik role MFA istenir | Tenant admin, payroll ve security işlemleri step-up isteyebilir |
| Field policy response üretiminde uygulanır | Yetkisiz alan response'a hiç girmemeli veya maskelenmeli |
| Export ayrıca permission ister | Görüntüleme yetkisi export yetkisi anlamına gelmez |

### 9.1 Permission isimlendirme

Önerilen pattern:

```text
<resource>:<action>:<scope>
<resource>:<action>:<field>
```

Örnekler:

- `employee:read:own`
- `employee:read:team`
- `employee:update:tenant`
- `employee:read:salary`
- `document:download:tenant`
- `leave:approve:team`
- `report:export:tenant`
- `audit:read:tenant`

### 9.2 Scope tanımları

| Scope | Tanım |
|---|---|
| `own` | Kullanıcının kendi kaydı |
| `team` | Yönetici olduğu doğrudan veya policy'ye göre dolaylı ekip |
| `department` | Belirli departman kapsamı |
| `branch` | Belirli şube/lokasyon kapsamı |
| `tenant` | Tüm tenant kapsamı |
| `global` | Platform operasyon kapsamı; müşteri verisine varsayılan erişim vermemeli |

## 10. KVKK, audit ve saklama gereksinimleri

| Olay | Audit gerekli mi? | Not |
|---|---|---|
| Login başarılı/başarısız | Evet | Güvenlik analizi için |
| Parola sıfırlama | Evet | Token detayı yazılmaz |
| Kullanıcı daveti | Evet | Kim davet etti bilgisi |
| Rol atama/değiştirme | Evet | Önce/sonra ve gerekçe |
| Hassas alan görüntüleme | Evet | Alan adı ve actor yazılır |
| Export oluşturma | Evet | Filtre, alan ve dosya tipi |
| Feature flag değişimi | Evet | Plan ve modül etkisi |
| Tenant ayarı değişimi | Evet | Önce/sonra snapshot |
| Session revoke | Evet | Kullanıcı veya admin aksiyonu |

Saklama kararı: Güvenlik ve audit logları operasyonel ihtiyaç ve yasal saklama politikasıyla uyumlu şekilde ayrı retention sınıfına alınmalıdır. Hassas metadata minimum tutulmalıdır.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal | Faz |
|---|---|---|---|
| Kullanıcı daveti | Davet edilen kullanıcı | E-posta/SMS opsiyon | MVP |
| Parola sıfırlama | Kullanıcı | E-posta/SMS opsiyon | MVP |
| Rol değişikliği | Kullanıcı + tenant admin | In-app/e-posta | MVP/V1 |
| Şüpheli login | Kullanıcı/security admin | E-posta/in-app | V1 |
| Session revoke | Kullanıcı | In-app/e-posta | V1 |
| SSO ayarı değişimi | IT/security admin | E-posta/audit | V1/Enterprise |

Arka plan işler:

- Süresi dolan davetleri pasifleştirme.
- Eski session ve token kayıtlarını temizleme.
- Feature flag cache yenileme.
- Audit retention job.
- Lisans sayacı snapshot job.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Permission parser doğru çalışır |
| Unit | Masking formatları doğru uygulanır |
| Unit | Token expiry ve refresh rotation kuralları |
| Integration | Login → refresh → logout akışı |
| Integration | Role değişince yetki etkisi |
| Integration | Tenant A kullanıcısı Tenant B kaydını göremez |
| E2E | Tenant admin kullanıcı davet eder ve rol atar |
| E2E | Manager sadece kendi ekibini görür |
| Security | Broken object level authorization denemeleri |
| Security | Export yetkisi olmayan kullanıcı export alamaz |
| Security | Hassas alan görüntüleme audit'e düşer |

## 13. Kabul kriterleri

- Her API request'i tenant context ile çalışır.
- Tenant dışı veri hiçbir endpointte dönmez.
- Kullanıcı login, refresh ve logout akışları çalışır.
- Varsayılan roller ve permission setleri seed edilir.
- Own/team/tenant scope ayrımı testlerle doğrulanır.
- TCKN, IBAN, maaş gibi hassas alanlar permission olmadan tam görünmez.
- Rol değişiklikleri audit'e düşer.
- Export işlemleri ayrı permission ve audit ister.
- Feature flag ile modül/özellik erişimi kontrol edilebilir.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Rol modeli fazla karmaşık başlarsa MVP yavaşlar | Önce varsayılan roller, sınırlı özelleştirme |
| Risk | Tenant izolasyonu sadece app katmanında kalırsa açık riski artar | DB/RLS veya merkezi tenant guard testleri planlanmalı |
| Risk | IT admin İK verisine gereksiz erişirse KVKK riski oluşur | IT rolü güvenlik ayarı yapar, İK içeriğini varsayılan görmez |
| Risk | SSO erken yapılırsa MVP odağı dağılır | MVP'de SSO-ready tasarım, V1/Enterprise'da uygulama |
| Açık soru | Mavi yaka için SMS/telefon login MVP'de olacak mı? | Pilot segmentine göre karar verilecek |
| Açık soru | MFA MVP'de zorunlu mu, opsiyonel mi? | Admin/payroll için step-up önerilir |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [Ürün Metrikleri ve Başarı Kriterleri](../02-urun/04-urun-metrikleri-ve-basari-kriterleri.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
