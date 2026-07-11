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
