# Alembic versions

## P0D tenant relational integrity

`0009_expand_tenant_relational_integrity` ve
`0010_contract_tenant_relational_integrity` birlikte expand-contract geçişidir.

- Expand başlamadan önce `TENANT_RELATIONSHIP_PREFLIGHT_SQL`, mevcut sekiz foreign-key
  ilişkisindeki orphan kayıtları ve dört tenant-owned child ilişkisindeki cross-tenant kayıtları
  listeler. Migration aynı sorgunun özetinde satır bulursa hiçbir constraint eklemeden fail olur.
- PostgreSQL expand adımı `employees(tenant_id, id)` ve `users(tenant_id, id)` candidate
  index'lerini `CONCURRENTLY` kurup unique constraint olarak bağlar; yarım kalmış invalid migration
  index'lerini güvenli biçimde yeniden kurabilir.
- Dört composite foreign key önce `NOT VALID` eklenir. Bu durum yeni write'ları hemen korurken eski
  scalar foreign key'leri yerinde tutar.
- Concurrent index kurulurken commit edilmiş bir write'ın ilk taramayla yeni constraint arasına
  girmemesi için aynı preflight, `NOT VALID` constraint'ler eklendikten sonra table lock'ları
  bırakılmadan yeniden çalışır. İkinci tarama fail olursa expand revision stamp edilmez.
- Contract adımı composite constraint'leri `VALIDATE CONSTRAINT` ile doğrular; ancak bundan sonra
  eski employee/user scalar foreign key'lerini kaldırır.
- Alembic `transaction_per_migration=True` kullanır; `upgrade head` contract validation'da fail
  olursa tamamlanmış expand revision'ı rollback edilmez ve onarım için iki constraint nesli korunur.
- Downgrade önce eski scalar foreign key'leri geri ekleyip validate eder, sonra expand revision'ı
  composite foreign key ve candidate key'leri kaldırabilir.

SQLite yolu yalnız migration zinciri ve model metadata uyumunu hızlı kontrol eder. PostgreSQL
concurrent index, `NOT VALID`, validation ve doğrudan write reddi için kanıt
`backend/tests/integration/test_postgresql_tenant_relational_integrity.py` içindeki gerçek
PostgreSQL testleridir.

## P0E concurrency, idempotency ve employee archive

`0011_p0e_concurrency_idempotency_archive`, P0C transaction sınırı ve P0D composite tenant
ilişkileri üzerinde üç kalıcı veri güvencesi kurar:

- `employees.archived_at` nullable timezone kolonu ile `(tenant_id, archived_at)` index'ini ekler.
  Normal employee DELETE artık satırı fiziksel olarak silmez; arşivli satır normal görünürlükten
  çıkar, aynı tenant'ta tekrarlanan archive no-op `204` olur ve mevcut
  `(tenant_id, employee_number)` unique constraint'i identifier'ı rezerve tutar.
- `command_idempotency` tablosu `(tenant_id, idempotency_key)` named unique constraint'iyle
  tenant-genel key namespace'i sağlar. Command adı, canonical request fingerprint, resource id,
  response snapshot ve completion zamanı aynı Unit of Work transaction'ında tutulur. Aynı key ve
  aynı istek snapshot'tan replay edilir; farklı command/body `409 idempotency_key_mismatch` olur.
  Receipt TTL veya cleanup migration/job'ı henüz yoktur.
- `leave_requests` ve `leave_balance_summaries` tablolarının
  `(tenant_id, employee_id) → employees(tenant_id, id)` composite foreign key'leri
  `ON DELETE RESTRICT` olur. Employee arşivi child satırlara dokunmaz; servis dışı doğrudan hard
  delete geçmiş varken DB tarafından reddedilir.
- `0011` downgrade'i, `archived_at IS NOT NULL` employee veya herhangi bir idempotency receipt'i
  varken retention state'ini sessizce düşürmez; export/remediation tamamlanana kadar preflight ile
  fail olur. Temiz state'te önceki `CASCADE` constraint'leri geri kurulabilir.

Leave decision blocking row lock davranışı schema nesnesi eklemez: application sorgusu kaydı
`tenant_id + leave_request_id` ile `SELECT ... FOR UPDATE` seçer. Bağımsız transaction'lardan yalnız
biri pending transition'ı commit eder; bekleyen transaction güncel terminal status'u görür.

Public employee purge endpoint'i yoktur. Root `tenant_id → tenants.id` cascade sahipliği yalnız
kısıtlı operatör retention/offboarding prosedürü içindir; normal employee silme yolu değildir.

SQLite yalnız hızlı migration/model uyumu sağlar. Duplicate winner, concurrent leave decision,
same-key replay ve `RESTRICT` hard-delete reddi gerçek PostgreSQL bağımsız-session testleriyle
kanıtlanır.

## P0F query-performance baseline

`0012_p0f_query_performance`, mevcut response sözleşmesini değiştirmeden ölçülen liste/search
sorgularını destekler:

- PostgreSQL'de `pg_trgm` extension'ını `IF NOT EXISTS` ile hazırlar. Non-archived employee
  `employee_number` ve `email` alanlarına partial GIN trigram indexleri ekler. Migration downgrade'i
  başka schema/uygulamalarca da kullanılabilecek extension'ı düşürmez.
- `department_normalized`, `lower(ltrim(rtrim(department)))` stored generated kolonudur;
  non-archived `(tenant_id, department_normalized)` partial indexi exact case-insensitive
  department filtresini destekler.
- `ix_leave_requests_tenant_created_cursor`, public listenin
  `(tenant_id, created_at desc, start_date asc, id asc)` keyset sırasını karşılar.
- SQLite migration yolu zincir/model/API smoke uyumluluğu içindir. `pg_trgm`, partial GIN ve
  `EXPLAIN (ANALYZE, BUFFERS)` iddiaları yalnız
  `backend/tests/integration/test_postgresql_p0f_performance.py` gerçek PostgreSQL testiyle
  kanıtlanır.

Extension oluşturma yetkisi managed PostgreSQL'de migration rolüne verilmiyorsa `pg_trgm`
platform operatörü tarafından upgrade öncesi provision edilmelidir; index migration'ı extension
yoksa fail ederek indexsiz aramaya sessizce geçmez.

## F1A typed tenant settings

`0013_tenant_settings`, tenant başına tek fixed settings satırı ekler. `tenant_id` hem primary key
hem `tenants.id` için named `ON DELETE CASCADE` root foreign key'dir. `week_start_day`,
`date_format` ve `time_format` named allowlist check'leri taşır; arbitrary JSON veya feature flag
kolonu yoktur. Upgrade mevcut tenant'ları `monday`, `DD.MM.YYYY`, `24h` defaultlarıyla backfill
eder.

Downgrade non-default settings sayısını önce kontrol eder. Herhangi bir custom değer varsa
`custom_tenant_settings=<count>` ile fail eder ve revision/table'ı yerinde bırakır; yalnız yeniden
üretilebilir default-only satırlar düşürülebilir. SQLite ve PostgreSQL 17.10 testleri backfill,
round-trip, custom-settings refusal, schema drift, native check'ler ve tenant-root FK reddini
doğrular.

## F1C PostgreSQL RLS foundation

`0014_f1c_postgresql_rls`, hızlı SQLite migration zincirini değiştirmeden gerçek PostgreSQL'de
normal tenant ve platform operasyonlarını iki ayrı capability role ayırır:

- `wealthy_falcon_app` ve `wealthy_falcon_platform` cluster role'leri idempotent olarak oluşturulur
  veya güvenli attribute'lara geri çekilir. İkisi de `NOLOGIN`, `NOSUPERUSER`, `NOCREATEDB`,
  `NOCREATEROLE`, `NOINHERIT`, `NOBYPASSRLS` ve `NOREPLICATION` taşır. Runtime gateway üyeliği ve
  credential provisioning migration'ın işi değildir. Reused capability rolü başka bir parent
  role üyesiyse daha geniş role geçebilme riskine karşı upgrade preflight fail eder.
- `users`, `employees`, `leave_requests`, `leave_balance_summaries`, `command_idempotency` ve
  `tenant_settings` tenant-owned envanteri revision içinde sabittir. Bu tablolar ile tenant metadata
  root'u `tenants` üzerinde RLS hem `ENABLE` hem `FORCE` edilir.
- Normal app policy'si tenant-owned tablolarda `tenant_id`, root tabloda `id` değerini
  `nullif(current_setting('app.tenant_id', true), '')::uuid` ile karşılaştırır. Aynı predicate
  `USING` ve `WITH CHECK` üzerinde role-scoped uygulanır; eksik context satır göstermez/yazdırmaz,
  invalid UUID ise sorguyu fail closed eder.
- App role yalnız mevcut ürünün kullandığı `SELECT`/`INSERT`/`UPDATE` haklarını alır; `tenants`
  update grant'i yalnız `locale`, `timezone` ve ORM on-update `updated_at` kolonlarıdır, dolayısıyla
  platform-controlled lifecycle/plan/region/name/slug değiştirilemez. İki role de `DELETE`
  verilmez. Upgrade önce iki capability role ait bu database/schema üzerindeki eski direct
  table/column grant'lerini temizleyip exact matrisi yeniden kurar. Platform role `tenants` metadata işlemleri ile
  provisioning sırasında `tenant_settings` INSERT yapabilir; settings SELECT/UPDATE ve employee,
  user, leave, balance veya idempotency tablo grant/policy'si yoktur. Settings mapper'ında implicit
  `RETURNING` kapalı olduğundan provisioning INSERT'i gereksiz settings SELECT yetkisi istemez.
- SQLite upgrade/downgrade bu PostgreSQL güvenlik DDL'ini no-op olarak geçer. Downgrade database'e
  ait grant/policy/RLS durumunu geri alır fakat başka database'lerce kullanılabilecek cluster
  role'lerini düşürmez.

Yeni tenant-owned tablo ekleyen her sonraki revision, aynı stable migration helper'ını açık ve o
revision'a sabitlenmiş bir tablo listesiyle çağırmalıdır. ORM metadata'sından dinamik migration
envanteri türetilmez. PostgreSQL catalog, raw-SQL isolation, role privilege ve pool-reuse kanıtı
`backend/tests/integration/test_postgresql_f1c_rls.py` içinde gerçek normal role ile çalışır.

## F1D typed feature rollout and configured limit metadata

`0015_f1d_feature_flags`, `0014_f1c_postgresql_rls` üzerine iki additive platform metadata
değişikliği kurar:

- `tenants.active_employee_limit` nullable integer'dır; yalnız `1..1_000_000` aralığındaki configured
  limit metadata'sını taşır. `null` limitsiz kullanım iddiası veya HR usage ölçümü değildir.
- `tenant_feature_flags` composite primary key olarak `(tenant_id, key)` kullanır; tenant root'una
  named `ON DELETE CASCADE` foreign key ile bağlıdır. `key` ve boolean `enabled` named check
  constraint'lerle korunur.
- Revision'a frozen flag sırası `organization`, `employees`, `documents`, `leave`, `self_service`,
  `reporting`, `notifications`'tır. Upgrade her mevcut tenant için tam yedi satır backfill eder;
  yalnız `employees`, `leave`, `reporting` default `true`, diğerleri `false` olur.
- F1C tenant root'ta owner dahil FORCE RLS uyguladığı için upgrade backfill'i ve downgrade limit
  retention sorgusu migration/table owner adına transaction içinde tenant RLS flag'lerini geçici
  kaldırır ve `ENABLE + FORCE` durumunu geri kurar. Non-superuser, `NOBYPASSRLS` migration-owner
  PostgreSQL testi hem yedi-row backfill'i hem failed downgrade sonrası flag restoration'ı kanıtlar.
- PostgreSQL'de yeni tablo RLS `ENABLE + FORCE` durumundadır. `wealthy_falcon_app` yalnız tenant
  policy'si altında `SELECT`; `wealthy_falcon_platform` unrestricted platform policy'si altında
  `SELECT/INSERT/UPDATE` alır. İki capability role de tablo üzerinde `DELETE` alamaz. SQLite branch
  şema/constraint/API compatibility testidir, bu privilege/RLS iddiasının kanıtı değildir.
- Revision, migration owner'ın hostile `ALTER DEFAULT PRIVILEGES` ayarını miras bırakmamak için
  yeni tablo grant'lerini önce `PUBLIC`, tenant ve platform capability'lerinde sıfırlar; exact
  least-privilege matrisini bundan sonra verir.
- Downgrade yalnız bütün flag satırları frozen default değerlerde ve hiçbir tenant'ta configured
  active employee limit yokken çalışır. Override veya configured limit varsa sayılı
  `feature_overrides`/`configured_active_employee_limits` preflight hatasıyla revision ve veriyi
  yerinde bırakır; sessiz rollout/limit metadata kaybı yapmaz.

F1D migration, `audit_events` veya başka audit persistence tablosu eklemez. Dört platform event
sözleşmesi application/UoW portudur; append-only audit modeli Faz 2 migration'ında kurulacaktır.
SQLite round-trip/drift ile gerçek PostgreSQL 17.10 catalog/RLS/grant/cross-tenant,
hostile-default-ACL ve non-BYPASS migration-owner testleri geçmiştir; exact sonuçlar
implementation-status dokümanında kayıtlıdır.

## P3A global identity and tenant-membership expand foundation

`0022_p3a_identity_memberships`, tenant-scoped `users` sözleşmesini kaldırmadan global credential
kimliği ile tenant erişimini ayıran additive expand adımıdır.

- `identities`, normalized e-posta için global unique anahtar ile gelecekte credential-wide
  `pending|active|locked|disabled` durumu ve parola sahipliği kurulacak target projection'dır.
  P3A compatibility checkpoint'inde activation/login/user servislerinin canlı write sahibi hâlâ
  `users`/`user_roles`'dır; canonical write cutover ve sürekli senkronizasyon sonraki identity
  checkpoint adımlarına bırakılır.
- `tenant_memberships`, mevcut public user ID'sini membership ID olarak korur; tenant-local ad,
  `invited|active|locked|disabled` durumu ve `permission_version` taşır. Böylece bir tenant'taki
  lock/disable başka tenant membership'ini veya global credential'ı kapatmaz.
- `membership_roles`, role bağlantısını `(tenant_id,membership_id)` composite foreign key ile
  tenant-qualified tutar. Legacy `user_roles` bu checkpoint'te kaldırılmaz.
- Backfill normalized e-posta başına en düşük UUID'li legacy user'ı canonical identity ID/e-posta
  kaynağı seçer; her legacy user aynı ID'li membership'e, her `user_roles` satırı membership role'a
  dönüşür. Bir e-posta grubunda birden fazla farklı non-null parola hash'i varsa migration seçim
  yapmaz ve `conflicting_password_identities` sayısıyla atomik olarak durur. Onarım, kimlik sahibi
  doğrulaması + parola resetiyle legacy hash'leri tek canonical değere getiren açık forward data-fix
  üzerinden yapılır; hash lexical olarak seçilmez veya sessizce silinmez.
- PostgreSQL'de membership tabloları `ENABLE + FORCE RLS` ve tenant policy altında yalnız `SELECT`
  grant'i alır. Platform capability hiçbir membership/identity grant'i almaz. Global credential
  tablosu FORCE RLS altında policy'siz/default-deny kalır; ilerideki login geçişi platform rolünü
  yeniden kullanmak yerine ayrı dar authentication capability'si kurmalıdır.
- Uygulama binary'si legacy tablolardan çalışmaya devam ettiği için schema downgrade olmadan geri
  alınabilir. Schema downgrade yalnız identity, membership ve role satırları legacy projection'dan
  birebir yeniden üretilebiliyorsa çalışır. `identity_drift`, `membership_drift` veya `role_drift`
  varsa ya da legacy credential grubu artık tek hash'e indirgenemiyorsa veri düşürmek yerine fail
  eder; target state forward reconciliation revision'ıyla onarılır ve sonra yeniden değerlendirilir.

SQLite hattı deterministic projection, unique/check/FK metadata ve guarded downgrade için hızlı
kanıttır. FORCE RLS, exact ACL, platform denial ve cross-tenant visibility iddiaları yalnız
`backend/tests/integration/test_postgresql_p3a_identity_memberships.py` ile gerçek PostgreSQL'de
kanıtlanır.

## P3B email-first tenant login capability

`0023_p3b_email_first_login`, P3A target projection'ını tenant login'in credential kaynağı yapar.

- `wealthy_falcon_authentication`, tenant ve platform rollerinden ayrı `NOLOGIN`, `NOINHERIT`,
  `NOBYPASSRLS` capability'sidir. Yalnız global identity doğrulaması, aktif membership discovery,
  güvenli tenant ad/slug okuması, global-safe başarısız login audit INSERT'i ve PII-free rate-limit
  bucket'ları için exact column grant/policy alır. Önceden var olan rolün stale table, column,
  sequence ve function grant'ları önce sıfırlanır; employee/leave veya başka HR tablolarına erişmez.
- Birden fazla aktif membership yalnız hash olarak saklanan, beş dakikalık
  `organization_selection_transactions` credential'ı ve transaction'a bağlı random choice
  anahtarları üretir. Tenant/platform capability'leri bu tabloları okuyamaz; raw transaction
  credential'ı hiçbir audit/DB alanına yazılmaz.
- Tenant invitation/activation expand compatibility'si
  `sync_current_tenant_identity_membership(uuid, boolean)` SECURITY DEFINER sınırıyla aynı
  transaction'da korunur. Fonksiyon yalnız aktif `app.tenant_id` içindeki gerçek legacy user'ı
  projekte eder ve dışarıdan `SET ROLE` edilemeyen `wealthy_falcon_identity_projection` owner
  capability'siyle çalışır. Tenant invitation token'ı aktif global identity parolasını
  değiştiremez; bu durum token tüketilmeden generic activation hatasıyla kapanır. Pending identity
  activation'ı yarış sırasında active/locked/disabled duruma geçerse fonksiyon aynı transaction'ı
  `WF001` ile geri alır; mevcut identity kabulü sonraki identity-authenticated akışa bırakılır.
- Cluster-global roller migration downgrade'da düşürülmez. Production/runtime gateway'in yeni
  authentication rolünü assume etme üyeliği, önceki capability'lerde olduğu gibi migration ve repo
  secret kapsamı dışındaki kontrollü database provisioning sorumluluğudur.

SQLite testleri contract/constraint ve ürün akışı kanıtıdır. FORCE RLS, exact ACL, HR denial,
tenant/platform selection-table denial ve projection-function sınırı
`backend/tests/integration/test_postgresql_p3b_email_first_login.py` ile disposable PostgreSQL
hattında kanıtlanır.

## P3C–P3E identity checkpoint closure

`0024_p3c_organization_selection`, refresh session'ını canonical membership'e bağlar ve hashli
organization-selection credential'ının tek kullanımlık tüketimini açar. `0025_p3d_platform_authentication`,
tenant session/cookie/audience sınırından ayrı platform identity role ve session tablolarını ekler.

`0026_p3e_identity_checkpoint`, P3A–P3E / Phase 3A kimlik sınırını kapatan additive revision'dır:

- `password_reset_tokens`, yalnız SHA-256 hash, identity FK, süre ve mutually-exclusive
  consumed/revoked terminal durumlarını saklar; raw token DB'ye yazılmaz.
- Tablo PostgreSQL'de `ENABLE + FORCE RLS` altındadır. Tenant, platform ve authentication
  capability'leri tablo grant'i almaz; authentication capability yalnız dar
  `issue_identity_password_reset` ve `complete_identity_password_reset` fonksiyonlarını çalıştırır.
  Non-login recovery owner yeniden kullanılıyorsa bütün stale object/column grant'leri sıfırlanır;
  rolün beklenmeyen member'ı veya önceden sahip olduğu public object varsa migration fail closed
  olur.
- `accept_existing_identity_membership(uuid,text)` SECURITY DEFINER fonksiyonu, tenant context
  içindeki invited legacy user ile `active` global identity'nin doğrulanmış ve değişmemiş Argon
  hash'ini atomik kontrol eder. Yalnız membership/user durumunu aktive eder; global credential'ı
  değiştirmez. Aktivasyon token'ı yine süreli, hashli ve tek kullanımlıktır.
- `issue_identity_password_reset(uuid,uuid,text,timestamptz)` aktif identity'yi kilitler, önceki
  canlı resetleri iptal eder ve en fazla bir saatlik yeni hashli credential'ı atomik oluşturur.
- `complete_identity_password_reset(uuid,text,text)` yalnız doğru, canlı reset hash'iyle global
  credential ve legacy credential projection'larını aynı değere getirir; reset token'ını tüketir,
  diğer resetleri iptal eder ve tenant/platform refresh family'leri ile açık organization-selection
  transaction'larını revoke/consume eder.
- Login, activation ve recovery public denemeleri PII-free HMAC bucket'larıyla kaynak ve
  identity/token bazında sınırlandırılır. Recovery request'i bilinen/bilinmeyen hesap için aynı
  response ve audit şeklini korur; reset confirm kaynak/token limitini pahalı Argon işleminden önce
  tüketir. Downgrade, P3E scope satırlarını non-BYPASS owner ile silebilmek için rate-limit tablosunda
  FORCE RLS'i transaction içinde geçici kaldırır ve constraint contract'tan sonra geri kurar.

SQLite migration/model/API hattı hızlı compatibility kanıtıdır. Function owner, exact ACL/RLS,
tenant/platform denial, existing-identity kabulü, tek identity/iki membership ve recovery session
revoke iddiaları `backend/tests/integration/test_postgresql_p3e_identity_checkpoint.py` ile gerçek
PostgreSQL'de doğrulanır. Bu revision sonrası tek head `0026_p3e_identity_checkpoint`'tır; P3F
organization tabloları bu checkpoint'e dahil değildir.

## P3F legal entity ve branch/location temeli

`0027_p3f_legal_entities_branches`, tenant organization dilimini additive olarak başlatır:

- `legal_entities`, case-insensitive generated `code_normalized`, tenant içi kalıcı kod,
  active/inactive durum, typed legal metadata (`registered_name`, `country_code`, `tax_number`,
  timezone) ve tenant başına en fazla bir aktif default entity saklar. Mevcut her tenant için
  `id=tenant.id`, `code=DEFAULT`, ad/registered-name ve timezone tenant metadata'sından gelen
  deterministic default satır backfill edilir.
- `branches`, aynı generated/kod benzersizliğiyle active veya archived location durumunu saklar.
  `archived_at` durumla birlikte constraint altındadır; `(tenant_id, legal_entity_id)` composite
  foreign key başka tenant'ın legal entity'sine bağlanmayı veritabanında engeller. Runtime
  `DELETE` grant'i almaz; archive, allowlisted kolon update'idir ve tarihsel satırı korur.
- Her iki tablo PostgreSQL'de `ENABLE + FORCE RLS` altındadır. Tenant capability yalnız
  `SELECT/INSERT` ve modelin mutable/archive kolonlarına column-level `UPDATE` alır; kimlik,
  tenant, legal-entity bağı, kalıcı kod ve default işareti runtime'da değiştirilemez. Platform
  capability yeni tenant provisioning'i için yalnız `legal_entities INSERT` ve default-entity
  şekline kısıtlı insert-only policy alır; legal-entity `SELECT/UPDATE`, bütün branch erişimi ve
  `DELETE` kapalıdır.
- Authorization catalog'a stable 31/32 numaralı `organization:read:tenant` ve
  `organization:update:tenant` permission'ları eklenir. Tenant admin, HR director ve HR specialist
  read/update; auditor yalnız read grant'i alır.
- Downgrade, branch veya default placeholder dışı legal-entity state'i varsa veri düşürmek
  yerine fail eder. PostgreSQL RLS/ACL iddiaları disposable PostgreSQL integration hattında
  kanıtlanmalıdır; SQLite hattı generated kolon, constraint, backfill ve schema uyumunu kanıtlar.

Bu revision sonrası tek head `0027_p3f_legal_entities_branches`'tır.
