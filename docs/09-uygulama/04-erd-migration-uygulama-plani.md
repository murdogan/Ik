# ERD ve Migration Uygulama Planı

Bu doküman, foundation ERD dokümanını implementasyon sırasına indirger. Amaç tüm veritabanını bir anda kurmak değil, migration zincirini güvenli, test edilebilir ve tenant-first sırayla oluşturmaktır.

## 1. Migration ilkeleri

- Her tenant-owned tablo `tenant_id` taşır.
- Dışa açık ID'ler UUID olmalıdır.
- Migration küçük ve geri alınabilir olmalıdır.
- Büyük/destructive değişiklikler expand-contract yaklaşımıyla yapılır.
- Tenant-owned parent ilişkileri `(tenant_id, id)` candidate key ve child tarafında
  `(tenant_id, foreign_id)` composite foreign key kullanır.
- Constraint expand adımından önce orphan/cross-tenant preflight çalışır; contract ancak yeni
  constraint validate edildikten sonra eski constraint'i kaldırır.
- Migration testleri model metadata ve migration dosyası varlığını doğrular.
- Tenant guard testleri Faz 0/F1A'da başlar; F1C catalog/policy testleri her non-null `tenant_id`
  tablosunun PostgreSQL RLS enabled/forced ve amacına uygun tenant/auth policy kapsamlı olmasını
  zorunlu kılar. F1D yeni
  tenant-owned feature tablosunu kendi frozen revision inventory/policy/grant sözleşmesiyle ekler;
  F2 ve P3'te eklenen her tenant-owned tablo aynı catalog gate'ine dahil edilir.
- F1E'nin historical head'i `0015_f1d_feature_flags` idi. Güncel doğrusal zincir P3I'nin structured
  assignment/backfill revision'ı `0030_p3i_employee_assignments` üzerinden P3K'nin katalog-only
  `0031_p3k_legacy_tenant_auth_boundary` revision'ına, ardından P4A `0032` ve P4B `0033`
  revision'larına ulaşır; final gate tam bir Alembic head ister.
- P3K `0031` yeni domain tablosu veya Phase 4 verisi eklemez. Yalnız `leave:manage:tenant`
  permission'ını HR director/specialist rollerine grant ederek legacy leave mutation'larını canlı
  tenant auth'a bağlayan katalog sınırını kapatır.

### 1.1 Uygulanan P0D geçişi

Mevcut gerçek Alembic zincirindeki `0009_expand_tenant_relational_integrity`, employee/user
candidate key'lerini ve dört leave composite foreign key'ini eski scalar constraint'lerle birlikte
ekler. PostgreSQL'de yeni foreign key'ler `NOT VALID` olarak yeni write'ları hemen korur; constraint
lock'ları bırakılmadan tekrarlanan preflight concurrent-index penceresindeki write yarışını kapatır.
`0010_contract_tenant_relational_integrity` bunları validate eder ve yalnız eski tenant-owned
employee/user scalar foreign key'lerini kaldırır. Downgrade sırası önce eski constraint'leri geri
getirip validate eder. RLS bu historical geçişe dahil değildir; daha sonra Faz 1'de
`0014_f1c_postgresql_rls` ile uygulanmıştır.

### 1.2 Uygulanan P0E concurrency, idempotency ve archive geçişi

`0011_p0e_concurrency_idempotency_archive`, normal employee silme akışını veri koruyan archive
semantiğine taşır ve retry receipt'leri için tenant-owned `command_idempotency` tablosunu ekler:

- `employees.archived_at` nullable timestamptz alanı ve `(tenant_id, archived_at)` sorgu indexi
  eklenir. Mevcut satırlar `null` kaldığı için migration normal görünürlüğü değiştirmeden uygulanır.
- `command_idempotency`, tenant-global `(tenant_id, idempotency_key)` unique constraint'i,
  command adı, semantic request fingerprint'i, resource ID, ilk başarılı response JSON snapshot'ı
  ve completion timestamp'i taşır. Receipt ile domain write aynı application transaction'ındadır.
- Leave request ve leave balance child ilişkilerinin employee delete davranışı
  `ON DELETE RESTRICT` olur. Böylece normal veya doğrudan employee fiziksel silmesi mevcut geçmişi
  cascade ile yok edemez.
- Downgrade, archived employee veya idempotency receipt varsa retention preflight'ta fail olur;
  export/remediation sonrası temiz state'te child ilişkilerini önceki `CASCADE` davranışına
  döndürür, receipt tablosunu/indexini ve `archived_at` alanını kaldırır. Bu downgrade yalnız
  kontrollü rollback içindir; production retention politikası olarak kullanılmaz.

Leave karar one-winner davranışı kolon/version migration'ı gerektirmez. Application command
transaction'ı tenant + leave request ID ile `SELECT ... FOR UPDATE` kullanır; lock sonrası yalnız
`pending` state terminal karara geçebilir. Gerçek PostgreSQL concurrency testi eşzamanlı
approve/reject işlemlerinden tam birinin başarılı olduğunu doğrular.

### 1.3 Uygulanan P0F query-performance geçişi

`0012_p0f_query_performance`, public response body'yi değiştirmeden measured query planlarını
destekler:

- PostgreSQL `pg_trgm` extension'ı ve non-archived employee number/email partial GIN indexleri;
- `lower(ltrim(rtrim(department)))` stored generated `department_normalized` kolonu ile
  non-archived `(tenant_id, department_normalized)` partial B-tree indexi;
- leave keyset sırasını karşılayan
  `(tenant_id, created_at desc, start_date asc, id asc)` B-tree indexi.

Downgrade indexleri ve generated kolonu kaldırır ancak başka consumer'larca kullanılabilecek
`pg_trgm` extension'ını kaldırmaz. PostgreSQL-specific index/plan iddiaları 10,000 employee fixture
ve `EXPLAIN (ANALYZE, BUFFERS)` entegrasyon testiyle doğrulanır; SQLite yalnız zincir/model
uyumluluğu içindir.

### 1.4 F1A tenant settings geçişi

`0013_tenant_settings`, tenant lifecycle/settings vertical slice'ı için şemayı additive olarak
genişletir:

- Mevcut `tenants` şeması yeniden yazılmaz. Var olan status check'i korunur; plan, region ve locale
  için yeni DB check eklenmez veya legacy `premium` gibi satırlar normalize edilmez. Canonical yeni
  create/update inputları API/domain allowlist'iyle sınırlanır. IANA timezone katalog doğrulaması
  portable bir SQL check olmadığı için API/domain boundary'sinde uygulanır.
- `tenant_settings.tenant_id` hem primary key hem `tenants.id` için named
  `ON DELETE CASCADE` foreign key'dir. Her tenant böylece en fazla bir settings satırına sahiptir.
- Fixed settings kolonları `week_start_day` (`monday|sunday`, default `monday`), `date_format`
  (`DD.MM.YYYY|MM/DD/YYYY|YYYY-MM-DD`, default `DD.MM.YYYY`) ve `time_format`
  (`24h|12h`, default `24h`) ile non-null `created_at`/`updated_at` alanlarıdır. Arbitrary JSON,
  feature flag veya legal entity kolonu eklenmez.
- Upgrade mevcut her tenant için bir default settings satırı backfill eder. Downgrade önce
  `week_start_day=monday`, `date_format=DD.MM.YYYY`, `time_format=24h` dışındaki satırları sayar.
  `custom_tenant_settings > 0` ise export veya default restoration istenerek revision/table yerinde
  bırakılır; yalnız default-only state'te additive tablo kaldırılabilir. Tenant/employee/leave
  satırları silinmez. SQLite ve gerçek PostgreSQL zincirinde
  `0012 → head → 0012 → head` data-preserving round-trip beklenir.

F1A migration gate'i SQLite ve PostgreSQL 17.10 üzerinde backfill, metadata/schema drift,
`0012 → head → 0012 → head` round-trip, custom-settings downgrade refusal ve tenant-root foreign
key reddini doğrular.

### 1.5 Uygulanan F1C PostgreSQL RLS geçişi

`0014_f1c_postgresql_rls`, P0D/P0E ilişkisel bütünlük zincirinden ayrı olarak altı mevcut
tenant-owned tabloyu ve normal app metadata görünürlüğü için `tenants` root'unu RLS
`ENABLE + FORCE` korumasına alır. Frozen migration inventory'si stable helper ile role, policy ve
least-privilege grant'leri kurar; bağımsız PostgreSQL catalog testi yeni tenant tablosunun policy'siz
eklenmesini reddeder. SQLite branch schema DDL eklemez. Downgrade database-local policy/grant/RLS
nesnelerini kaldırır, başka disposable/operational database'in de kullanabileceği cluster-global
NOLOGIN capability rollerini düşürmez.

### 1.6 F1D typed feature rollout ve configured limit geçişi

`0015_f1d_feature_flags`, F1C capability ayrımını değiştirmeden current platform operations
metadata'sını additive genişletir:

- `tenants.active_employee_limit` nullable integer kolonunu ve
  `active_employee_limit is null or 1..1_000_000` named check'ini ekler. HTTP'de
  `limits.active_employees` olarak gösterilir; HR usage/count değildir.
- `tenant_feature_flags`, `(tenant_id,key)` named composite primary key, tenant-root named
  `ON DELETE CASCADE` FK, fixed key ve boolean enabled check'leri ile oluşturulur.
- Revision'a frozen catalog/backfill sırası `organization`, `employees`, `documents`, `leave`,
  `self_service`, `reporting`, `notifications`'tır. Existing tenant başına yedi row oluşturulur;
  yalnız `employees`, `leave`, `reporting` true'dur.
- F1C `tenants` için owner'a da FORCE RLS uygular. Bu nedenle F1D backfill ve downgrade limit
  retention sorgusu transaction içinde tenant-root RLS flag'lerini geçici kaldırıp aynı
  `ENABLE + FORCE` durumunu geri kurar; migration runtime'ı superuser/BYPASSRLS varsaymaz.
- PostgreSQL branch tabloyu RLS `ENABLE + FORCE` eder. Tenant app policy/grant yalnız `SELECT`,
  platform policy/grant yalnız `SELECT/INSERT/UPDATE` sağlar; iki capability de `DELETE` alamaz.
  SQLite aynı tablo/constraint/backfill contract'ını taşır fakat RLS/privilege kanıtı değildir.
- Downgrade feature override veya configured active employee limit varken
  `feature_overrides`/`configured_active_employee_limits` sayılarını raporlayıp fail eder. Yalnız
  default-only/no-limit state'te policy/grant/tablo/kolon geri alınır; audit veya HR verisine
  dokunulmaz.

Bu revision audit persistence tablosu eklemez. F1D event contract recorder seam'i application
transaction'ındadır; append-only `audit_events` migration'ı Faz 2'dir.

### 1.7 F1E Faz 1 final migration kapısı

Bu bölüm historical Faz 1 snapshot'ıdır; güncel head bilgisi değildir. F1E yeni tablo, kolon,
constraint, policy veya Alembic revision eklemez. O checkpoint'teki final migration yüzeyi
tek head `0015_f1d_feature_flags`'tır. Kapanış kanıtı:

- `uv run pytest -q backend/tests/test_migrations.py` → `36 passed`.
- `IK_TEST_DATABASE_URL=... uv run pytest -q -m postgres` → `30 passed`.
- Aynı DSN ile `backend/tests/integration/test_postgresql_baseline.py` → `8 passed`; gerçek
  upgrade/downgrade/re-upgrade, backfill/refusal, drift ve PostgreSQL API smoke.
- Aynı DSN ile `backend/tests/integration/test_postgresql_f1c_rls.py` ile
  `backend/tests/integration/test_postgresql_tenant_relational_integrity.py` → `12 passed`; catalog,
  role/ACL, tenant A/B RLS, platform-to-HR denial ve direct-DB composite-FK saldırıları.

Test fixture'ı unique disposable database'ler oluştursa da capability rolleri PostgreSQL cluster
scope'undadır ve downgrade'de bilinçli olarak düşürülmez. Bu yüzden tam lane yalnız disposable test
cluster'ında ve database/role/extension yönetebilen admin DSN ile çalıştırılır.

### 1.8 Uygulanan F2 auth, RBAC ve audit zinciri

`0016`–`0021` invitation activation, hashed refresh family/token rotation, tenant user yönetimi,
permission katalogu, append-only `audit_events` ve invited-user için dar PostgreSQL kolon grant'ini
lineer olarak ekler. Existing user, activation token ve actor foreign key'leri korunur. Audit normal
runtime role için `UPDATE/DELETE` edilemez; command ve audit aynı UoW'da commit/rollback eder.

### 1.9 Uygulanan P3A–P3E identity expand-contract zinciri

- `0022_p3a_identity_memberships`, global normalized e-posta credential sahibi `identities` ile
  tenant-local `tenant_memberships` ve `membership_roles` projection'larını mevcut user/role
  satırlarından backfill eder. Legacy ID/FK'ler contract aşamasına kadar korunur.
- `0023_p3b_email_first_login`, credential doğrulamasından önce membership metadata'sı açmayan
  dar authentication capability'sini, rate-limit bucket'larını ve hashli/süreli organization-
  selection transaction/choice tablolarını ekler. Login payload'ı yalnız e-posta/paroladır.
- `0024_p3c_organization_selection`, mevcut refresh family'leri membership'e backfill edip composite
  FK ile bağlar ve selection consume yetkisini tek-kullanımlı hale getirir. Opaque choice,
  transaction identity'si ve seçilen tenant/membership birlikte doğrulanır.
- `0025_p3d_platform_authentication`, tenantless platform role ve session family/token tablolarını
  ayrı capability, refresh cookie ve access-token audience ile ekler. Platform ve tenant token'ı
  birbirinin endpointini açamaz.
- `0026_p3e_identity_checkpoint`, hashed/süreli/tek-kullanımlı password reset tablosu ile global
  credential lock/reconciliation fonksiyonlarını ekler. Reset tenant/platform family'lerini ve açık
  organization-selection transaction'larını kapatır; existing identity daveti kendi parolasıyla
  yalnız pending membership'i aktive eder.

### 1.10 Uygulanan P3F–P3J organization zinciri

- `0027_p3f_legal_entities_branches`, tenant başına tek aktif default legal entity backfill eder;
  tenant-owned legal entity lifecycle ve branch archive history'sini stable normalized code,
  composite FK, FORCE RLS ve dar platform-provisioning policy'siyle kurar.
- `0028_p3g_department_hierarchy`, adjacency-list `departments` ile tenant-scoped
  `department_hierarchy_write_fences` tablosunu ekler. PostgreSQL integrity/deferred-cycle
  trigger'ları self, cross-tenant, same-statement ve concurrent cycle'ı reddeder.
- `0029_p3h_position_catalog`, departmandan bağımsız reusable job-title katalogunu stable code,
  terminal archive, bounded cursor ve normalized code/title arama indexleriyle ekler.
- `0030_p3i_employee_assignments`, legal entity, branch, department, position ve manager user'ı
  tenant composite FK'leriyle bağlayan effective-dated immutable history'yi ekler. Tenant/employee
  başına tek open row vardır; successor eski satırı exclusive `effective_to` ile kapatır.
- P3I backfill'i legacy `employees.department` ve `employees.position` metinlerini normalized
  tenant-local katalog kayıtlarına map eder, default structure altında assignment oluşturur ve eski
  alanları compatibility projection olarak korur. Arşivli veya ambiguous state kayıpsız preflight
  olmadan sessizce yorumlanmaz.
- P3J org chart yeni DDL eklemez. `employee_assignments` manager/effective indexleriyle root veya tek
  direct-report seviyesini bounded/lazy okur.

### 1.11 P3K katalog-only kapanış ve final migration raporu

`0031_p3k_legacy_tenant_auth_boundary`, P3K için tek head'tir ve yalnız authorization katalogunu
genişletir. `leave:manage:tenant` HR director ve HR specialist rollerine explicit olarak bağlanır;
read scope mutation authority olarak kullanılmaz. Revision tablo/kolon, Phase 4 employee kaydı,
payroll veya başka ürün modülü eklemez.

Final P3K raporu en az şunları kaydeder: tek Alembic head; `base → head` ve desteklenen
round-trip; identity/membership/role ve organization/assignment backfill sayıları; autogenerate
metadata drift; FORCE RLS/policy/ACL katalogu; cross-tenant composite-FK negatifleri; auth realm ve
membership-selection saldırıları; departman concurrency/cycle; manager scope ve bounded query
planları. PostgreSQL-specific iddialar disposable gerçek PostgreSQL lane'inde kanıtlanır.

### 1.12 Uygulanan P4A–P4B employee-master genişlemesi

- `0032_p4a_employee_directory`, `employees` üzerinde normalized employee-number/non-null work-email
  benzersizliği, full-name normalization, pozitif optimistic version ve immutable-ID directory
  indexlerini additive kurar. Phase 3 assignment/history ve legacy alanlar korunur.
- `0033_p4b_employee_profiles`, focused `employee_profiles` ve `employee_employments` tablolarını
  ekler. İki tabloda da UUID ID, tenant/employee ID, timestamps, pozitif bağımsız version,
  `(tenant_id,id)` candidate key, çalışan başına `(tenant_id,employee_id)` unique ve composite
  employee FK vardır.
- Personal satır yalnız `preferred_name`, `birth_date`, `phone`; employment satır yalnız
  `contract_type=indefinite|fixed_term` ve `work_type=full_time|part_time` taşır. Core kimlik,
  `employment_start_date`, status/end-date `employees` üzerinde; organizasyon sahipliği Phase 3
  `employee_assignments` üzerinde kalır.
- Upgrade tablo DDL'inden önce deterministic UUID collision preflight'i çalıştırır, arşivli ve
  terminated kayıtlar dahil her employee için tam bir personal/employment satırı backfill eder ve
  missing/orphan sayımlarını aynı transaction'da doğrular. Employee population taraması için
  `employees` FORCE RLS geçici kaldırılıp başarıda geri kurulur.
- PostgreSQL'de inherited/default ACL sıfırlanır. Yeni tablolar `ENABLE + FORCE RLS` ve app-only
  tenant policy kullanır; tenant app table `SELECT,INSERT` ile yalnız onaylı alanlar,
  `version,updated_at` için column `UPDATE` alır. Public/platform/auth capability grant'i yoktur.
- Downgrade, herhangi bir profil alanı yazılmış veya section version ilerlemişse counted preflight
  ile durur. Untouched state'te yalnız yeni policy/grant/tablolar kalkar; employee ve assignment
  verisi korunur. P4B PostgreSQL testi eklenmiştir fakat bu ortamda `IK_TEST_DATABASE_URL` olmadığı
  için gerçek PostgreSQL execution sonucu iddia edilmez.

## 2. Migration sırası

Alembic history ve `alembic heads` çıktısı fiziksel sıra için otoritatiftir. Phase 3 ile güncel
P4A/P4B'de uygulanan eklemeler şöyledir:

| Revision | Dilim | Fiziksel etki |
|---|---|---|
| `0022` | P3A | Global identity, tenant membership ve membership-role projection/backfill |
| `0023` | P3B | E-posta-öncelikli auth capability, rate limit ve organization-selection state |
| `0024` | P3C | Membership-bound tenant session family ve tek-kullanımlı selection consume |
| `0025` | P3D | Ayrı tenantless platform role/session realm'i |
| `0026` | P3E | Global recovery, existing-identity membership acceptance ve credential lock |
| `0027` | P3F | Default legal entity backfill, legal entity ve branch/location |
| `0028` | P3G | Department hierarchy, write fence ve PostgreSQL cycle trigger'ları |
| `0029` | P3H | Reusable position/job-title katalogu |
| `0030` | P3I | Structured effective-dated assignment ve legacy string backfill |
| `0031` | P3K | Catalog-only `leave:manage:tenant` role grant kapanışı |
| `0032` | P4A | Employee normalization, optimistic version ve directory/assignment filtre indexleri |
| `0033` | P4B | Focused personal/employment bire-bir kayıtları, backfill, RLS/ACL ve downgrade guard |

P3J bu fiziksel sıraya revision eklemez. Employee documents ve diğer P4C+ alt kayıtları;
holiday/time, payroll, ATS, performance, LMS ve gelişmiş workflow tabloları kendi sonraki
fazlarında planlanır.

## 3. İlk tenant tabloları

### `tenants`

Zorunlu alanlar:

- `id`
- `slug`
- `name`
- `status`
- `plan_code`
- `data_region`
- `locale`
- `timezone`
- `created_at`
- `updated_at`

Kısıtlar:

- `slug` unique.
- `status` allowlist/check: `provisioning`, `trial`, `active`, `suspended`, `offboarding`, `closed`.
- Yeni/update API `plan_code` allowlist'i: `core`, `professional`, `enterprise`; legacy satırlar
  migration'da dönüştürülmez.
- Yeni/update API `data_region` allowlist'i: `tr-1`, `eu-1`; provisioning sonrası değişiklik
  domain/API kuralıyla reddedilir.
- Yeni/update API `locale` allowlist'i: `tr-TR`, `en-US`.
- `timezone` geçerli IANA timezone adı olmalıdır.

### `tenant_settings`

Zorunlu alanlar:

- `tenant_id` (primary key ve tenant foreign key)
- `week_start_day`
- `date_format`
- `time_format`
- `created_at`
- `updated_at`

Kısıtlar:

- `tenant_id → tenants.id` named `ON DELETE CASCADE` foreign key.
- `week_start_day`: `monday|sunday`.
- `date_format`: `DD.MM.YYYY|MM/DD/YYYY|YYYY-MM-DD`.
- `time_format`: `24h|12h`.
- JSON settings/config/feature blob'u yoktur. API'nin settings allowlist'i tenant tablosundaki
  `locale`/`timezone` ile bu üç fixed kolondan oluşur.

### `users`

Zorunlu alanlar:

- `id`
- `tenant_id`
- `email`
- `full_name`
- `status`
- `password_hash`
- `created_at`
- `updated_at`

Kısıtlar:

- `(tenant_id, email)` unique.
- `tenant_id` foreign key.
- `status` enum/check.

`users` Phase 3'te credential otoritesi değil, korunmuş tenant-local compatibility projection'dır.
Canonical credential global unique `identities.email_normalized`/`password_hash` alanındadır;
`tenant_memberships(tenant_id, identity_id)` bir identity'nin birden fazla tenant'a erişimini ve
tenant-local status/permission version'ını taşır. `membership_roles` rol authority'sini global
identity yerine composite tenant-membership anahtarına bağlar. Tenant login bu modelde kurum kodu
almaz; membership listesi ancak global credential doğrulandıktan sonra bulunur.

## 4. RBAC tabloları

### `roles`

Alanlar:

- `id`
- `code`
- `name`
- `description`
- `scope_type` (`tenant|platform`)
- `system_role`
- `created_at`
- `updated_at`

Unique: `code`. Rol katalogu sistem-global tanımdır; authority ataması tenant için
`user_roles`/`membership_roles`, platform için `platform_identity_roles` üzerinden scope-qualified
kurulur.

### `permissions`

Alanlar:

- `id`
- `code`
- `resource`
- `action`
- `target`
- `target_type` (`scope|field`)
- `description`

Unique: `code`.

### `user_roles`

Alanlar:

- `tenant_id`
- `user_id`
- `role_id`
- `role_scope_type` (yalnız `tenant`)
- `active`
- timestamps

`membership_roles` P3 expand projection'ı aynı tenant role authority'sini
`(tenant_id,membership_id,role_id)` ile temsil eder. `platform_identity_roles` ayrı tenantless
platform realm'ine aittir ve tenant rol liste/atama endpointlerinde gösterilmez.

## 5. Employee minimal ERD

### `employees`

MVP minimal alanlar:

- `id`
- `tenant_id`
- `employee_number`
- `first_name`
- `last_name`
- `email`
- `status`
- `employment_start_date`
- `employment_end_date`
- `archived_at`
- P4A generated `employee_number_normalized`, `email_normalized`, `full_name_normalized`
- pozitif P4A `version`
- `created_at`
- `updated_at`

Unique: `(tenant_id, employee_number)`.

`archived_at is null` normal employee yüzeyidir. Normal `DELETE` satırı kaldırmaz, `archived_at`
set eder ve tekrarlandığında no-op olur. Unique constraint arşivlenen employee number'ını tenant
içinde rezerve tutar.

TCKN/IBAN gibi hassas alanlar P4B'ye alınmamıştır; ancak ayrı onaylı field-encryption/policy
diliminde değerlendirilebilir.

### P4B focused profile tabloları

`employee_profiles`:

- `id`, `tenant_id`, `employee_id`
- nullable `preferred_name`, `birth_date`, `phone`
- pozitif bağımsız `version`
- `created_at`, `updated_at`

`employee_employments`:

- `id`, `tenant_id`, `employee_id`
- nullable `contract_type` (`indefinite|fixed_term`)
- nullable `work_type` (`full_time|part_time`)
- pozitif bağımsız `version`
- `created_at`, `updated_at`

Her tabloda `(tenant_id,employee_id)` unique ile employee başına tam bir satır ve
`(tenant_id,employee_id) → employees(tenant_id,id)` composite `ON DELETE RESTRICT` FK vardır.
`0033` mevcut her employee için iki satırı backfill eder. İşe başlangıç tarihi
`employees.employment_start_date` alanında kalır; status/end-date lifecycle veya assignment alanı
bu focused tablolara kopyalanmaz.

### Phase 3 structured organization ERD

- `legal_entities`: tenant-owned stable `code`, temel tescilli ad/ülke/vergi/timezone alanları,
  `active|inactive` durumu ve tenant başına tek aktif default marker.
- `branches`: composite legal-entity FK, tenant-wide stable code, lokasyon/timezone alanları ve
  fiziksel silme yerine `active|archived` history.
- `departments`: tenant-wide stable code, composite self-parent FK, `active|archived` history ve
  `department_hierarchy_write_fences` üzerinden serialize edilen cycle-safe adjacency list.
- `positions`: departman/manager FK'si taşımayan reusable tenant job-title katalogu; stable code,
  mutable title ve terminal archive.
- `employee_assignments`: employee, legal entity, branch, department, position ve optional
  `manager_user_id` composite FK'leri; `effective_from`, exclusive `effective_to`, optional
  `supersedes_assignment_id`, change reason ve actor. Employee başına tek open row vardır.

Inactive legal entity ile archived branch/department/position yeni assignment'ta kullanılamaz;
var olan assignment history'si silinmez ve API resolved historical labels ile okunabilir. Manager
team ve lazy org chart yalnız
bugün yürürlükteki structured assignment bağından türetilir; legacy department/position metni
authorization kaynağı değildir.

### `command_idempotency`

Faz-0 alanları:

- `id`
- `tenant_id`
- `idempotency_key`
- `command_name`
- `request_fingerprint`
- `resource_id`
- `response_payload`
- `created_at`
- `completed_at`

Unique: `(tenant_id, idempotency_key)`. Aynı key başka tenant'ta bağımsızdır; aynı tenant'ta
farklı komut, hedef veya semantic body ile reuse `idempotency_key_mismatch` üretir. Başarılı
receipt ilk response snapshot'ını replay eder. Henüz TTL/cleanup migration'ı veya worker'ı yoktur;
key receipt kaldığı sürece rezerve kalır.

### Employee history ve retention sınırı

- `leave_requests(tenant_id, employee_id)` ve
  `leave_balance_summaries(tenant_id, employee_id)` current head'de
  `employees(tenant_id, id)` parent'ına `ON DELETE RESTRICT` ile bağlıdır.
- Normal employee list/detail/update, yeni leave request ve leave-balance erişimi yalnız
  `archived_at is null` employee'leri kabul eder; dashboard workforce/employee activity de archive
  kayıtlarını dışlar.
- Eski leave request ve leave balance satırları korunur. Employee number yeniden dağıtılmaz.
- Employee purge için HTTP endpoint yoktur. Tenant-owned kayıtların `tenant_id → tenants.id`
  root ownership FKs'i graph-level `ON DELETE CASCADE` sınırı olarak kalır; bu sınır yalnız açık
  retention/onay politikasına bağlı, kısıtlı tenant-root offboarding operasyonunda kullanılabilir.
  Normal employee komutu veya kullanıcı yetkisi değildir.

## 6. RLS/tenant guard standardı

F1C ile uygulanan tenant-owned tablo standardı:

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_app ON employees
TO wealthy_falcon_app
USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
```

Her sonraki tenant-owned tablo RLS migration'ını ayrı/frozen inventory ile ekler ve independent
PostgreSQL catalog discovery testini günceller. SQLite bu standardın güvenlik kanıtı değildir.
P4B profil tabloları için tenant app policy dışında policy yoktur; table `SELECT,INSERT` ve dar
column `UPDATE` dışındaki inherited/default grant'ler revision içinde sıfırlanır. Public, platform
ve authentication capability'leri tablo veya kolon erişimi almaz.

## 7. Test planı

| Test | Amaç |
|---|---|
| Metadata registration | Model Base metadata'ya kayıtlı mı |
| Required columns | Zorunlu kolonlar var mı |
| Migration exists | Migration dosyası var mı |
| Alembic history | Zincir doğru mu |
| Existing tenant settings backfill | Her mevcut tenant tam bir default settings satırı alıyor mu |
| Settings downgrade refusal | Default dışı typed settings sayılı preflight ile kayıp öncesi downgrade'i durduruyor mu |
| Tenant lifecycle/catalog parity | Domain/schema allowlist'leri ve mevcut DB status check'i uyumlu mu; legacy plan satırları korunuyor mu |
| Settings allowlist | Sabit kolonlar ve API typed key'leri dışındaki payload reddediliyor mu |
| Feature catalog/backfill | Existing tenant başına ordered yedi default row ve exact key/enabled check var mı |
| Feature downgrade refusal | Override/configured limit varken sayılı preflight veri kaybından önce duruyor mu |
| RLS catalog test | Tenant tablolarında RLS açık mı |
| Faz 1 feature privilege | Tenant yalnız kendi SELECT; platform SELECT/INSERT/UPDATE; iki role de DELETE yok mu |
| Cross-tenant query | Tenant A verisi Tenant B'den görünmüyor mu |
| Platform-to-HR negative | Metadata/feature platform capability'si HR tablo/query/schema erişimi alamıyor mu |
| Relational preflight | Orphan ve cross-tenant satırlar constraint DDL'den önce raporlanıyor mu |
| PostgreSQL direct write | Her composite ilişki servis bypass edildiğinde cross-tenant write'ı reddediyor mu |
| Data-preserving round trip | Desteklenen round-trip valid satırları koruyor; retention preflight destructive downgrade'ı sayılı biçimde reddediyor mu |
| Concurrent leave decision | PostgreSQL row lock approve/reject için tam bir terminal winner sağlıyor mu |
| Concurrent idempotency | Aynı tenant/key ile yarışan create komutları tek resource ve receipt üretiyor mu |
| Archive retention | Normal DELETE satırı/history'yi koruyor ve child FK fiziksel silmeyi `RESTRICT` ediyor mu |
| Idempotency rollback | Başarısız keyed komut receipt bırakmadan aynı key ile retry edilebiliyor mu |
| Identity/membership backfill | Existing user/role projection sayıları ve drift preflight'i tutarlı mı |
| Auth realm cross-use | Tenant bearer/cookie platform API'sinde ve platform bearer/cookie tenant API'sinde reddediliyor mu |
| Membership abuse | Credential öncesi enumeration, forged choice, replay, cross-identity ve cross-tenant consume reddediliyor mu |
| Department concurrency | Same-statement ve concurrent graph write'ları PostgreSQL trigger/fence ile cycle oluşturamıyor mu |
| Assignment history | Successor eski open row'u exclusive boundary'de kapatıyor ve archived referans geçmişi okunuyor mu |
| Manager scope | Team/org chart yalnız current `manager_user_id` bağından türetiliyor mu |
| Bounded query | Department tree, position search, assignment/team ve org-chart sorguları index/limit bütçesine uyuyor mu |
| P3K permission catalog | `leave:manage:tenant` yalnız hedef HR rolleri için eklenip read permission mutation authority olmaktan çıkıyor mu |
| P4A compatibility | Existing employee create/list/detail/PATCH/archive ve assignment contract'ları `0032` sonrasında korunuyor mu |
| P4B profile backfill | Her existing employee için tenant-consistent tam bir personal/employment satırı var mı |
| P4B section concurrency | Personal ve employment version'ları bağımsız stale write'ı `409` ile reddedip başarıda bir kez ilerliyor mu |
| P4B transaction/audit | Core + section + allowlisted before/after audit aynı UoW'da mı; failure partial state/event bırakmıyor mu |
| P4B PostgreSQL catalog | Composite FK/check/unique, FORCE RLS, app-only policy ve dar table/column grants exact mı |

## 8. Seed planı

Mevcut local/development seed deterministik ve idempotenttir:

- 2 tenant: `wealthy-falcon-demo`, `atlas-people-demo`.
- 5 user, 8 employee ve 5 leave request.
- Aynı `admin@wealthyfalcon.demo` global identity'si iki tenant membership'iyle multi-org seçim
  yolunu temsil eder; tenant-local user/membership ID'leri korunur. Bu shared identity ayrı
  `super_admin` platform role projection'ını da alır; platform login yine ayrı route/cookie/audience
  kullanır ve tenant membership'i platform principal'a dönüşmez.
- Wealthy Falcon demo admin'i `tenant_admin` yanında `hr_specialist` rolünü alır; böylece aynı
  review identity'si tenant seçiminden sonra organization assignment happy path'ini kullanabilir.
- Her tenant için organization feature açık, tek aktif default legal entity ve bir aktif demo
  branch vardır. Legacy employee department/position etiketlerinden normalized stable-code
  department ve position katalogları ile her employee için structured assignment oluşturulur.
- Assignment manager'ı tenant'ın seeded manager user'ıdır; böylece `/teams/me` ve lazy org chart
  manuel demoda gerçek structured scope gösterir. Terminated employee interval'i employment end
  tarihinin ertesi günü exclusive olarak kapanır.
- Tenant, user, employee, leave ve generated organization/assignment UUID'leri tekrar
  çalıştırmalarda deterministiktir. Var olan assignment history'si seed tarafından overwrite
  edilmez; conflict sessizce yorumlanmak yerine fail eder.
- `0033` migration'ı upgrade anında mevcut her employee için boş/default personal ve employment
  satırını backfill eder; güncel demo seed migration sonrasında oluşturulan/onarılmış employee'ler
  için aynı iki focused kaydı idempotent tamamlar. Seed TCKN, IBAN, ücret, sağlık veya başka
  P4B-dışı profil değeri üretmez.
- `scripts/seed_demo_data.py --auth-demo` yalnız local/dev ve local database hedefinde `wf_admin`
  ile `wf_manager` kullanıcılarını invited duruma getirip iki etiketli, farklı, tek-kullanımlı
  activation URL üretir. Seed plaintext/default parola yazmaz. Admin aktivasyonu global shared
  credential'ı kurup email-only multi-org ve ayrı platform-login demolarını; manager aktivasyonu
  derived team görünümünü açar. Veriler sentetiktir.

## 9. Kabul kriterleri

- Migration sırası küçük ve anlaşılırdır.
- Tenant ve user sonrası RBAC ve employee sırası nettir.
- Hassas alanlar encryption kararı olmadan rastgele eklenmez.
- RLS catalog, role/ACL, tenant A/B raw-SQL ve platform-to-HR negatifleri gerçek PostgreSQL'de
  geçmiştir; SQLite bu iddianın kanıtı değildir.
- Seed verisi sentetiktir.
- Employee normal DELETE archive eder; history ve employee number korunur.
- Leave kararları PostgreSQL row lock ile one-winner'dır.
- Desteklenen keyed komutlar tenant-global receipt ile ilk başarılı snapshot'ı replay eder.
- P0E receipt TTL/cleanup ve employee purge HTTP endpointi eklemez.
- Faz 1 final feature katalog/backfill/API sırası birebir uyumludur; tenant A/B ve platform-to-HR
  PostgreSQL negatifleri gerçek role'lerle doğrulanır.
- Configured `limits.active_employees` hiçbir platform query'sinde employee count/usage'a
  dönüştürülmez.
- Historical F1D revision'ı audit persistence tablosu eklememiştir; bu yüzey F2E'de uygulanıp P3
  organization/auth eventleriyle genişletilmiştir.
- Phase 3 tarihsel olarak `0031_p3k_legacy_tenant_auth_boundary` ile kapanır; `0031` katalog-only'dir
  ve Phase 4 tablosu eklemez. Güncel P4B zinciri tek head `0033_p4b_employee_profiles` ile biter.
- Email/password-only tenant login, post-auth multi-org selection ve ayrı platform auth realm'i
  migration/grant/catalog negatifleriyle uyumludur.
- Legal entity/branch/department/position/assignment backfill'i legacy alanları korur; manager team
  scope ve lazy org chart structured assignment'tan türetilir.
- P4B her existing employee için tam bir focused personal/employment satırı sağlar; core/start-date
  ve organization ownership kaynaklarını çoğaltmaz, changed-data downgrade'ını reddeder.
- PostgreSQL lane cycle/concurrency, RLS/grant, composite-FK ve bounded-query iddialarını gerçek
  PostgreSQL'de kanıtlar; SQLite sonucu bu iddialar için yeterli değildir.

## 10. Karar ve uygulama durumu

| Konu | Karar / mevcut durum | Uygulama zamanı |
|---|---|---|
| UUID | Public ID'ler uygulama tarafında `uuid4` ile üretilir; DB server default eklenmez | Uygulandı |
| User email canonicalization | Legacy `(tenant_id, email)` unique davranışı korunur; canonical auth `identities.email_normalized=lower(btrim(email))` global unique projection'ını kullanır, `citext` kullanılmaz | P3A–P3E uygulandı |
| RLS | Faz 0 composite FK + app guard üzerinde `0014` forced RLS, app/platform capability rolleri ve transaction-local tenant context uygulanır | F1E final tekrar: tam PostgreSQL `30`, RLS + direct attack `12` passed |
| F1A tenant settings | `0013` fixed-column settings check'leri, existing-tenant backfill ve custom-settings downgrade refusal ekler; tenant plan/region/locale input allowlist'i API/domain'dedir; arbitrary JSON/features/legal entity yoktur | F1A; SQLite + PostgreSQL 17.10 gate passed |
| Faz 1 feature/limit metadata | `0015` fixed feature table/backfill, nullable configured active employee limit, FORCE RLS ve exact tenant/platform/no-DELETE grants ekler; downgrade override/limit kaybını reddeder | Historical F1E snapshot; güncel head P4B `0033` |
| Hassas alan encryption | Key/provider ve envelope encryption kararı olmadan TCKN, IBAN, ücret veya sağlık kolonları eklenmez | İlgili employee/security fazı öncesi Murat kararı |
| Audit immutability | Audit aynı PostgreSQL DB'de append-only write modelidir; runtime role update/delete engeli ve recorder Faz 2'de birlikte uygulanır | Faz 2 |
| Global identity / membership | E-posta global normalized identity'de unique; tenant yetkisi membership ve membership-role projection'ındadır | P3A–P3E uygulandı |
| Tenant login | Request yalnız e-posta/parola; membership metadata credential doğrulamasından sonra, multi-org consume opaque ve tek-kullanımlıdır | P3B/P3C uygulandı |
| Platform realm | Ayrı route, principal, access audience, refresh cookie ve tenantless session family; cross-use denied | P3D/P3K gate |
| Structured organization | Legal entity/branch, cycle-safe department, reusable position, effective-dated assignment, derived team ve lazy chart | P3F–P3J uygulandı |
| Legacy leave auth boundary | `leave:manage:tenant` HR director/specialist katalog grant'i; read scope mutation authority değil | P3K `0031` |
| Employee directory compatibility | Normalized employee number/work email, positive version ve immutable-ID cursor/index contract'ı | P4A `0032` uygulandı |
| Focused Employee 360 persistence | Employee başına personal/employment record, independent versions, safe backfill, FORCE RLS ve narrow grants | P4B `0033` uygulandı; PostgreSQL runtime lane DSN yokluğu nedeniyle çalıştırılmış sayılmaz |

Bu tablo tamamlanmış davranış ile hedef kararı ayırır. Özellikle TCKN, IBAN ve maaş gibi alanlar,
encryption ve masking kararı netleşmeden migration'a eklenirse sonradan veri taşıma maliyeti doğar.

## 11. İlgili dokümanlar

- [Veritabanı Modeli ve ERD](../05-api-veri/01-veritabani-modeli-ve-erd.md)
- [Çok Kiracılık ve Veri İzolasyonu](../04-mimari/02-cok-kiracilik-ve-veri-izolasyonu.md)
- [Sprint-0 / Sprint-1 Backlog ve Task Planı](02-sprint-0-1-backlog-ve-task-plani.md)
