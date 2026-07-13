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
| Yalnız e-posta/parola tenant login'i ve post-auth multi-org seçimi | SAML/OIDC SSO'nun tam enterprise uygulanması |
| Oturum ve refresh token yönetimi | Passwordless/passkey ilk sürüm |
| Temel MFA hazırlığı | Zorunlu gelişmiş risk motoru |
| Roller ve permission katalogu | Görsel ABAC policy editörü |
| Own/team/tenant scope | Karmaşık matris organizasyon yetkisi |
| Hassas alan policy/maskeleme temeli; mevcut response allowlist'leri | Tam DLP ürünü ve Phase 4 hassas employee alanları |
| Audit event üretimi | SIEM export |
| Feature flag ve plan kontrolü | Karmaşık usage-based billing |

Kapsam dışı maddeler ürün vizyonundan çıkarılmış değildir; V1, V2 veya Enterprise fazına ertelenmiştir.

Historical F1A implementation boundary (yalnız geçmiş checkpoint; güncel davranış değil):

- Yalnız tenant lifecycle, plan/region/locale/timezone, fixed typed settings ve yedi
  platform/tenant operation'ı uygulanır. Authentication/session/RBAC, audit persistence, RLS,
  feature flags ve legal entity F1A'ya dahil değildir.
- Platform/tenant authorization caller header'ından gelmez. Trusted injected
  `PlatformPrincipal`/`TenantPrincipal` yoksa dependency `403` ile fail closed olur; Phase 2 auth
  bu seam'i dolduracaktır.
- Success body'ler Faz 1.2 `{data, meta}` compatibility geçişine kadar doğrudan typed object/list'tir.

Historical F1D CORE boundary (yalnız geçmiş checkpoint; F2/P3 sonrası güncel değil):

- F1A/F1B/F1C'nin lifecycle, typed settings, request context ve forced-RLS katmanları korunur.
  F1D yalnız typed platform rollout/metadata ve platform-event contract yüzeyini tamamlar;
  authentication/session/RBAC ve audit persistence hâlâ Faz 2 işidir.
- Sabit flag katalog sırası `organization`, `employees`, `documents`, `leave`, `self_service`,
  `reporting`, `notifications`'tır. Default `true` değerleri yalnız `employees`, `leave`,
  `reporting`; diğerleri `false`'tur. Tenant response'u her key için effective boolean ve
  `default|override` kaynağını döndürür; arbitrary customer flag veya code fork yoktur.
- Platform tenant response'unda `limits.active_employees` nullable configured metadata'dır; aktif
  çalışan usage/count değeri değildir. Platform metadata query'si yalnız `tenants` kolonlarını
  explicit project eder ve HR tablolarına join/count yapmaz.
- `tenant.created`, `tenant.status_changed`, `tenant.setting_changed`, `feature_flag.changed`
  sözleşmeleri frozen/extra-forbid ve platform-metadata-only'dir. Varsayılan recorder discard eder;
  Faz 2 aynı UoW portuna append-only persistence adapter'ı bağlayacaktır. Audit tablosu/read center
  F1D kapsamında yoktur.

Current Phase 3 / P3K boundary:

- Tenant login yalnız global e-posta ve parola kabul eder; kurum kodu, tenant slug/ID veya
  membership ID istemez ve kabul etmez. Membership sorgusu credential doğrulamasından sonra
  çalışır. Tek aktif membership doğrudan tenant session açar; birden fazlası yalnız güvenli
  display name, opaque `selection_key` ve hashli/süreli/tek-kullanımlı transaction döndürür.
- Aktif tenant oturumundan kurum değiştirme server-derived global identity ile hazırlanır,
  kaynak session family revoke edilir ve yeni seçim transaction'ı caller tenant selector'ı kabul
  etmeden tüketilir. Enumeration, replay, forged choice, cross-identity ve cross-tenant consume
  aynı kapalı hata sınırında reddedilir.
- Platform yönetimi `/api/v1/platform/auth/*` altında ayrı login/refresh/logout, tenantless
  `PlatformPrincipal`, platform access-token audience ve ayrı HttpOnly refresh cookie kullanır.
  Tenant token/cookie platform API'sini; platform token/cookie tenant API'sini açamaz. Eşzamanlı
  tenant ve platform oturumları birbirini sessizce dönüştürmez.
- Invitations, existing-identity membership acceptance, activation, global password recovery,
  refresh rotation/reuse detection, role version invalidation ve append-only tenant/platform audit
  kalıcı olarak uygulanmıştır.
- P3K'nin katalog-only `0031_p3k_legacy_tenant_auth_boundary` revision'ı
  `leave:manage:tenant` permission'ını HR director ve HR specialist rollerine explicit grant eder;
  legacy leave mutation'ları read scope'u veya caller-supplied actor ile authorize edilmez. Phase 4
  tablosu veya yeni ürün modülü eklenmez.

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `super_admin` | Ayrı platform realm'inde tenant metadata/rollout yönetir | Global/platform | Müşteri HR verisine varsayılan erişim olmamalı |
| `tenant_admin` | Kurum ayarları, kullanıcılar ve tenant rollerini yönetir | Tenant | Fazla yetki verilirse hassas veri açığa çıkar |
| `hr_director` | İK süreçleri için geniş tenant erişimi kullanır | Tenant / HR scope | Maaş/özel veri görünürlüğü kontrollü olmalı |
| `hr_specialist` | Operasyonel İK verisine erişir | Department/branch/tenant | Kapsam dışı çalışan görmemeli |
| `manager` | Kendi ekibini görür ve onay verir | Team scope | Maaş/TCKN gibi alanları görmemeli |
| `employee` | Kendi profili, izinleri ve belgelerini görür | Own scope | Başka çalışanın verisine erişmemeli |
| `it_admin` | Kullanıcı dizinini okur, session/security audit operasyonlarını yönetir | Security/admin scope | İK içeriğine varsayılan erişmemeli |
| `auditor` | Audit kayıtlarını ve uyum çıktısını inceler | Read-only | Veri değiştirmemeli |

Güncel seeded tenant rol katalogu `tenant_admin`, `hr_director`, `hr_specialist`, `it_admin`,
`auditor`, `manager`, `employee` rolleridir. `super_admin` tenant rolü değil, ayrı
`platform_identity_roles` authority'sidir. Payroll/finance gibi roller sonraki payroll/workforce
fazlarında planlanır; Phase 3'te varmış gibi yetki verilmez.

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
- Response allowlist/redaction temeli; TCKN/IBAN/ücret gibi Phase 4+ alanları henüz şemada yoktur.
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

1. `super_admin` ayrı `/platform/login` ekranında platform email/parolasıyla oturum açar.
2. Platform shell yalnız tenant metadata/plan/region/lifecycle/configured limit ve feature rollout
   yüzeylerini kullanır; customer HR kaydı listelemez.
3. `POST /api/v1/platform/tenants` yeni tenant ve default typed ayarlarını provision eder; Phase 3
   migration/provisioning yolu tek aktif default legal entity'yi de garanti eder.
4. İlk tenant admin daveti ayrı authenticated tenant invitation akışıyla yönetilir; platform
   tenant provisioning response'u parola veya tenant session üretmez.
5. `platform.tenant.created` append-only platform audit event'i yazılır.

### 5.2 Kullanıcı daveti ve aktivasyon

1. `tenant_admin` veya yetkili HR kullanıcısı kullanıcı daveti oluşturur.
2. Server aynı tenant'ta invited user ile global identity/membership projection'ını kurar;
   güncel invitation payload'ı employee ID almaz.
3. Yeni global identity linkle ilk parolasını belirler; mevcut identity kendi parolasıyla yalnız
   yeni tenant membership'ini kabul eder.
4. Aktivasyon token'ı hashli, süreli ve tek kullanımlıdır; tamamlanınca
   `auth.activation.completed` audit event'i aynı transaction'da yazılır.
5. Kullanıcı email/password tenant login akışına devam eder.

### 5.3 Login ve oturum yenileme

1. Kullanıcı yalnız global e-posta ve parolasını girer; kurum kodu istenmez.
2. Credential doğrulandıktan sonra aktif tenant membership'leri bulunur.
3. Tek membership doğrudan session açar; çoklu membership güvenli display name seçimi gösterir.
4. Access token kısa ömürlü, refresh token rotation ile verilir.
5. Refresh token tekrar kullanımı tespit edilirse session family revoke edilir. MFA challenge UI'ı
   Phase 3'te uygulanmış değildir; auth-strength modeli sonraki step-up dilimine hazırdır.

Kurum kodu/tenant ID hiçbir tenant login adımında istenmez. Hatalı e-posta/parola, inactive
identity ve uygun membership bulunmaması aynı genel credential hata sınırını kullanır; membership
display name'i başarısız credential denemesine sızmaz.

### 5.4 Kurum değiştirme

1. Authenticated tenant kullanıcısı çalışma alanından kurum değiştirmeyi başlatır.
2. Server global identity'yi canlı membership-bound session'dan türetir; body/query tenant ID'si
   kabul etmez.
3. Kaynak tenant session family revoke edilir ve alternatif aktif membership'ler için yeni opaque
   selection transaction'ı döner.
4. Tek-kullanımlı seçim tüketilince yeni membership/tenant-bound session açılır; replay veya stale
   seçim kullanıcıyı email/parola login'e döndürür.

### 5.5 Ayrı platform login

1. Yetkili platform kullanıcısı `/platform/login` üzerinde email/parola girer.
2. Global credential doğrulansa bile aktif platform rolü yoksa tenant membership bilgisi
   dönmeden istek reddedilir.
3. Başarı ayrı platform access audience ve refresh cookie oluşturur; kurum seçimi yapılmaz.
4. `/api/v1/platform/me` canlı tenantless session/role/version doğrular. Tenant bearer burada,
   platform bearer `/api/v1/me` veya tenant domain API'lerinde reddedilir.

Local review seed'inde `admin@wealthyfalcon.demo` tek global identity olarak iki tenant membership'i,
Wealthy Falcon'da tenant admin + HR specialist rollerini ve ayrı `super_admin` platform role
projection'ını taşır. `scripts/seed_demo_data.py --auth-demo`, plaintext/default parola yazmadan
`wf_admin` ve `wf_manager` için iki etiketli tek-kullanımlı activation URL üretir. Admin aktivasyonu
email-only multi-org, organization admin/assignment ve ayrı platform-login akışlarını; manager
aktivasyonu derived direct-team akışını manuel review'a açar.

### 5.6 Yetki kararı

1. Request tenant context ile başlar.
2. Kullanıcının rol ve permission seti alınır.
3. Scope değerlendirilir: own, team, department, branch, tenant.
4. Güncel resource permission/scope fail closed uygulanır ve response allowlist/redaction'ı
   yalnız yetkili alanları döndürür.
5. Phase 4+ hassas alanları geldiğinde field-level allow/mask/deny/step-up ve sensitive-read audit
   ayrı acceptance gate'iyle etkinleştirilir.

### 5.7 Rol değişikliği

1. `tenant_admin` kullanıcı rolünü değiştirir.
2. `PUT /api/v1/users/{user_id}/roles` tenant rollerini atomik replace eder; platform rolü bu katalog
   yüzeyinden atanamaz.
3. Permission version artar; eski access/session snapshot'ı tekrar authorize edemez.
4. `user.roles.replaced` append-only audit event'i yazılır. İkinci onay/delegation daha sonraki
   governance dilimidir.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| Tenant Login | Yalnız e-posta/parola; kurum kodu yok | Uygulandı |
| Kurum Seçimi | Credential sonrası safe display-name kartları ve opaque seçim | Uygulandı |
| Platform Login/Shell | Ayrı realm, tenant metadata ve platform audit | Uygulandı |
| Tenant Ayarları | Şirket adı, saat dilimi, dil, temel ayarlar | API uygulandı; dedicated UI sonraki dilim |
| Kullanıcılar | Kullanıcı listesi, davet, aktif/pasif, rol atama | Uygulandı |
| Roller ve Yetkiler | Varsayılan roller ve permission görünümü | Uygulandı, sabit katalog |
| Oturumlar | Aktif session listesi ve revoke | V1 |
| Güvenlik Ayarları | Parola, MFA, domain policy | V1 planı; recovery UI ayrı uygulandı |
| Feature Flags | Plan ve modül aç/kapa | Platform shell/internal uygulandı |
| Audit | Tenant ve ayrı platform category-filtered explorer | Uygulandı |
| SSO Ayarları | OIDC/SAML yapılandırması | V1/Enterprise |

Deneyim kararı: MVP'de roller tamamen serbest özelleştirilebilir bir editörle başlamamalıdır. Önce iyi tasarlanmış varsayılan roller ve sınırlı ayar seçenekleri sunulmalıdır.

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `tenants` | Müşteri/kurum hesabı | `id`, `slug`, `name`, `status`, `plan_code`, `data_region`, `locale`, `timezone`, nullable configured `active_employee_limit` |
| `tenant_settings` | F1A fixed kurum ayarları | `tenant_id`, `week_start_day`, `date_format`, `time_format`, timestamps; arbitrary key/value yok |
| `plans` | İleri-faz paket katalogu | Ayrı plan tablosu yok; canonical write kodları `core`, `professional`, `enterprise`; F1D tek configured active-employee limitini tenant metadata'sında taşır |
| `tenant_feature_flags` | F1D tenant/modül rollout state'i | Composite `(tenant_id,key)` PK; fixed key check, boolean enabled, timestamps; default/override effective read |
| `identities` | Global credential sahibi | `id`, global unique `email_normalized`, `password_hash`, credential-wide `status`, platform permission version |
| `tenant_memberships` | Identity'nin tenant erişimi | `tenant_id`, `identity_id`, `legacy_user_id`, tenant-local `status`, `permission_version` |
| `users` | Expand-contract tenant projection | `id`, `tenant_id`, `email`, reconciled `password_hash`, `status` |
| `password_reset_tokens` | Tek-kullanım recovery | `identity_id`, yalnız token hash, `expires_at`, `consumed_at`, `revoked_at` |
| `refresh_session_families`, `refresh_session_tokens` | Tenant membership-bound session rotation | tenant/user/membership, permission version, expiry/revoke, yalnız token hash |
| `platform_identity_roles` | Ayrı platform authority | `identity_id`, platform `role_id`, active |
| `platform_refresh_session_families`, `platform_refresh_session_tokens` | Tenantless platform session rotation | identity, platform permission version/auth strength, expiry/revoke, yalnız token hash |
| `organization_selection_transactions`, `organization_selection_choices` | Credential sonrası multi-org seçim | identity, yalnız token hash, expiry/consume; opaque choice → tenant/membership |
| `roles` | Global system rol katalogu | unique `code`, `name`, `scope_type=tenant|platform`, `system_role` |
| `permissions` | Yetki katalogu | unique `code`, `resource`, `action`, `target`, `target_type=scope|field` |
| `role_permissions` | Rol-permission eşleşmesi | `role_id`, `permission_id` |
| `user_roles` | Legacy tenant user rol projection'ı | `tenant_id`, `user_id`, `role_id`, tenant scope, `active` |
| `membership_roles` | Canonical tenant authority | `tenant_id`, `membership_id`, `role_id`, tenant scope, `active` |
| `user_identities` | SSO/harici kimlik | V1/Enterprise planı; Phase 3 tablosu değil |
| `field_policies` | Alan bazlı görünürlük | Phase 4+ planı; mevcut allowlist/redaction kodu ayrı generic policy tablosu kullanmaz |
| `audit_events` | Append-only tenant/platform olayı | `scope_type`, nullable `tenant_id`, `actor_user_id`, `event_type`, category/severity/result, resource, request/trace ve redacted before/after/metadata |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| POST | `/api/v1/platform/tenants` | Platform-safe tenant provisioning | F1A |
| GET | `/api/v1/platform/tenants` | Metadata/plan/region/lifecycle health listesi; HR veri yok | F1A |
| GET | `/api/v1/platform/tenants/{tenant_id}` | Platform-safe tenant metadata detayı | F1A |
| PATCH | `/api/v1/platform/tenants/{tenant_id}` | Explicit lifecycle/typed metadata değişikliği | F1A |
| GET | `/api/v1/tenant` | Canlı tenant session'dan current tenant metadata | F1A/P3K |
| GET | `/api/v1/tenant/settings` | Beş typed setting | F1A |
| PATCH | `/api/v1/tenant/settings` | Fixed allowlist partial update | F1A |
| GET | `/api/v1/platform/tenants/{tenant_id}/features` | Bir tenant'ın effective rollout metadata'sı | F1D |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/features` | Typed, allowlisted tenant flag değişikliği | F1D |
| GET | `/api/v1/tenant/features` | Canlı tenant session'ının kendi effective flag'leri | F1D/P3K |
| POST | `/api/v1/auth/login` | Login başlatır | MVP |
| POST | `/api/v1/auth/select-organization` | One-use transaction + opaque choice ile tenant session açar | P3C |
| POST | `/api/v1/auth/organization-selection` | Canlı tenant session'dan kontrollü kurum switch'i hazırlar | P3C |
| POST | `/api/v1/auth/refresh` | Token yeniler | MVP |
| POST | `/api/v1/auth/logout` | Session kapatır | MVP |
| POST | `/api/v1/auth/activate` | Yeni identity aktivasyonu veya mevcut identity membership kabulü | MVP/P3E |
| POST | `/api/v1/auth/password-reset/request` | Enumeration-resistant recovery isteği | MVP/P3E |
| POST | `/api/v1/auth/password-reset/confirm` | Global credential reset + session revoke | MVP/P3E |
| POST | `/api/v1/platform/auth/login` | Ayrı platform role/session realm login'i | P3D |
| POST | `/api/v1/platform/auth/refresh` | Yalnız platform refresh cookie rotation | P3D |
| POST | `/api/v1/platform/auth/logout` | Yalnız platform session revoke | P3D |
| GET | `/api/v1/platform/me` | Tenantless platform principal/session doğrulama | P3D |
| POST | `/api/v1/users/invitations` | Kullanıcı daveti oluşturur | MVP |
| GET | `/api/v1/users` | Tenant kullanıcılarını listeler | MVP |
| GET | `/api/v1/users/{user_id}` | Current-tenant kullanıcı detayı | MVP |
| PATCH | `/api/v1/users/{user_id}` | Kullanıcı durum/temel bilgi günceller | MVP |
| GET | `/api/v1/roles` | Roller ve permission görünümü | MVP |
| GET | `/api/v1/permissions` | Tenant permission katalogu | MVP |
| PUT | `/api/v1/users/{user_id}/roles` | Tenant rollerini atomik replace eder | MVP |
| GET | `/api/v1/me` | Aktif kullanıcı/rol/scope bilgisi | MVP |
| GET | `/api/v1/audit-events` | Audit filtreleme | MVP |
| GET | `/api/v1/me/sessions` | Kullanıcının session listesi | V1 |
| DELETE | `/api/v1/me/sessions/{id}` | Session revoke | V1 |
| POST | `/api/v1/sso/oidc` | OIDC ayarı | V1 |
| POST | `/api/v1/scim/v2/Users` | SCIM provisioning | Enterprise |

## 9. Yetki, scope ve güvenlik kuralları

| Kural | Açıklama |
|---|---|
| Canlı session default-deny | Protected route bearer'ın audience/signature'ını ve server-side family/role/version state'ini doğrular; header/path/body kimliği authorization değil |
| Platform/tenant realm ayrımı | Ayrı route, principal, access audience ve refresh cookie; cross-use her iki yönde reddedilir |
| Platform metadata isolation | Platform query/response plan, configured limit, lifecycle health ve rollout metadata'sıyla sınırlıdır; HR record/count yoktur |
| Tenant context body'den alınmaz | Validated membership-bound session'dan gelir; subdomain, kurum kodu, tenant header/path/body seçici değildir |
| Her sorgu tenant filtreli olmalı | App guard, composite FK ve PostgreSQL FORCE RLS birlikte zorunludur |
| E-posta global identity'de unique | Aynı normalized e-posta tek credential identity'sidir; farklı tenant erişimleri ayrı membership'lerdir |
| Membership discovery post-auth | Credential başarısızken kurum adı/sayısı/status'u açıklanmaz; seçim token'ı hashli, süreli ve tek kullanımlıdır |
| Access token kısa ömürlü olmalı | 10-15 dk aralığı hedeflenir |
| Refresh token rotation zorunlu | Reuse detection ile çalınan token fark edilir |
| Parola hash'i güçlü olmalı | Argon2id veya eşdeğer güçlü hash kullanılmalı |
| Kritik role MFA hazırlığı | Auth strength ve step-up modeli hazırdır; zorunlu MFA enrollment/challenge sonraki güvenlik dilimidir |
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
| `team` | Phase 3 organization modelinde current assignment'ın `manager_user_id` bağından doğrudan ekip |
| `department` | Belirli departman kapsamı |
| `branch` | Belirli şube/lokasyon kapsamı |
| `tenant` | Tüm tenant kapsamı |
| `platform` | Ayrı platform operasyon kapsamı; müşteri HR verisine varsayılan erişim vermez |

## 10. KVKK, audit ve saklama gereksinimleri

| Olay | Audit gerekli mi? | Not |
|---|---|---|
| Login başarılı/başarısız | Evet | Güvenlik analizi için |
| Parola sıfırlama | Evet | Token detayı yazılmaz |
| Kullanıcı daveti | Evet | Kim davet etti bilgisi |
| Rol atama/değiştirme | Evet | Önce/sonra ve gerekçe |
| Hassas alan görüntüleme | Evet | Alan adı ve actor yazılır |
| Export oluşturma | Evet | Filtre, alan ve dosya tipi |
| Tenant oluşturma/durum değişimi | Evet | F1D exact redacted contract; yalnız typed platform metadata |
| Feature flag değişimi | Evet | Typed key ve before/after boolean; arbitrary payload yok |
| Tenant ayarı değişimi | Evet | Yalnız non-empty allowlisted changed-field tuple; değer/entity snapshot'ı yok |
| Session revoke | Evet | Kullanıcı veya admin aksiyonu |

Saklama kararı: Güvenlik ve audit logları operasyonel ihtiyaç ve yasal saklama politikasıyla uyumlu şekilde ayrı retention sınıfına alınmalıdır. Hassas metadata minimum tutulmalıdır.
F1D historical olarak yalnız recorder contract'ını kurmuştur. Güncel F2/P3 uygulaması
append-only `audit_events` persistence/read modelini kullanır; tenant ve platform audit endpointleri
ayrı principal/category sınırındadır. Auth ve organization command audit'i domain write ile aynı
UoW'da commit veya rollback eder; token/parola ve arbitrary payload metadata'ya yazılmaz.

## 11. Bildirimler ve arka plan işler

Bu tablo delivery hedefidir. Güncel local/dev invitation response'u manuel activation URL,
password recovery ise ayrı delivery portunun local fake'ini kullanır; production e-posta/SMS,
notification worker, cleanup ve retention job'ları Phase 3'te uygulanmış sayılmaz.

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
| Integration/Security | Tenant login request'i kurum kodu kabul etmiyor; credential başarısızken membership metadata'sı açılmıyor |
| Integration/Security | Organization selection replay, forged choice, cross-identity ve cross-tenant consume reddediliyor |
| Integration/Security | Tenant/platform bearer ve refresh cookie cross-use iki yönde reddediliyor |
| Integration | Role değişince yetki etkisi |
| Integration | Tenant A kullanıcısı Tenant B kaydını göremez |
| Integration | Tenant A effective flag'i Tenant B override'ını göremez; tenant principal platform feature route'unda `403` alır |
| Integration/PostgreSQL | Tenant flag tablosu FORCE RLS; app yalnız tenant SELECT, platform yalnız SELECT/INSERT/UPDATE; iki role de DELETE yok |
| Contract | Dört F1D event yalnız allowlisted metadata kabul eder; parola/token/employee/HR ve generic payload reddedilir |
| E2E | Tenant admin kullanıcı davet eder ve rol atar |
| E2E | Manager sadece kendi ekibini görür |
| Security | Broken object level authorization denemeleri |
| Sonraki faz security gate | Export yetkisi olmayan kullanıcı export alamaz |
| Phase 4+ security gate | Hassas alan görüntüleme field permission ve audit ister |

## 13. Kabul kriterleri

- Her protected tenant-domain request'i validated membership session ve tenant context ile çalışır;
  public auth ile ayrı tenantless platform route'ları bu kurala karıştırılmaz.
- Tenant-domain endpointi authenticated tenant dışı HR verisi döndürmez; platform endpointi
  yalnız allowlisted platform metadata döndürür.
- Kullanıcı login, refresh ve logout akışları çalışır.
- Varsayılan roller ve permission setleri seed edilir.
- Own/team/tenant scope ayrımı testlerle doğrulanır.
- Mevcut response'lar allowlist/redaction uygular; Phase 4+ TCKN, IBAN ve ücret alanları
  eklenmeden önce ayrı field-permission/masking gate'i tamamlanır.
- Rol değişiklikleri audit'e düşer.
- Export yüzeyi eklendiğinde ayrı permission ve audit ister; Phase 3 export endpointi iddiasında
  bulunmaz.
- Feature flag ile modül/özellik erişimi kontrol edilebilir.
- Platform plan/limit/health/flag response'ları customer HR kaydı veya usage count içermez.
- Feature flag katalogu typed ve tenant-aware'dir; unknown key fail closed olur.
- Tenant login yalnız e-posta/parola kabul eder; multi-org seçim credential sonrası, opaque,
  süreli ve tek-kullanımlıdır.
- Tenant ve platform auth realm'leri route/principal/audience/cookie/session seviyesinde ayrıdır;
  token veya cookie cross-use fail closed olur.
- Append-only audit persistence ve tenant/platform read surface'leri uygulanmıştır; auth/RBAC
  command audit'i aynı UoW'da atomiktir.
- P3K `leave:manage:tenant` katalog grant'i legacy leave mutation'larını live tenant auth'a bağlar;
  read permission veya caller actor ID mutation authority değildir.
- TCKN, IBAN ve maaş Phase 3 şemasında yoktur; Phase 4+ eklendiğinde field permission/masking
  acceptance gate'i zorunludur.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Rol modeli fazla karmaşık başlarsa MVP yavaşlar | Önce varsayılan roller, sınırlı özelleştirme |
| Risk | Tenant izolasyonu app katmanında bypass edilirse veri sızabilir | Composite FK + FORCE RLS + gerçek PostgreSQL catalog/direct-attack gate'i uygulanır |
| Risk | IT admin İK verisine gereksiz erişirse KVKK riski oluşur | IT rolü güvenlik ayarı yapar, İK içeriğini varsayılan görmez |
| Risk | SSO erken yapılırsa MVP odağı dağılır | MVP'de SSO-ready tasarım, V1/Enterprise'da uygulama |
| Karar | SMS/telefon login | Phase 3 dışı; tenant login email/password-only kalır |
| Açık soru | MFA ne zaman zorunlu olacak? | Auth-strength/step-up modeli hazır; enrollment/challenge ayrı güvenlik diliminde kararlaştırılır |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [Ürün Metrikleri ve Başarı Kriterleri](../02-urun/04-urun-metrikleri-ve-basari-kriterleri.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
