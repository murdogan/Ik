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
- Tenant guard testleri Faz 0/F1A'da; RLS catalog/policy testleri daha sonraki ayrı Faz 1
  rollout'unda zorunludur. F1A RLS uygulamaz.

### 1.1 Uygulanan P0D geçişi

Mevcut gerçek Alembic zincirindeki `0009_expand_tenant_relational_integrity`, employee/user
candidate key'lerini ve dört leave composite foreign key'ini eski scalar constraint'lerle birlikte
ekler. PostgreSQL'de yeni foreign key'ler `NOT VALID` olarak yeni write'ları hemen korur; constraint
lock'ları bırakılmadan tekrarlanan preflight concurrent-index penceresindeki write yarışını kapatır.
`0010_contract_tenant_relational_integrity` bunları validate eder ve yalnız eski tenant-owned
employee/user scalar foreign key'lerini kaldırır. Downgrade sırası önce eski constraint'leri geri
getirip validate eder. RLS bu geçişe dahil değildir; Faz 1 işidir.

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

## 2. Migration sırası

Bu tablo ilk ürün planındaki kavramsal uygulama sırasıdır; `Plan` değerleri yayınlanmış Alembic
revision kimliği değildir. Güncel fiziksel Alembic zinciri için yukarıdaki 1.1/1.2/1.3 bölümleri,
migration history'si ve Alembic head otoritatiftir.

| Plan | Tablo/alan | Faz | Gerekçe |
|---|---|---|---|
| Plan 01 | `tenants` | Sprint-0 | Tüm izolasyonun temeli |
| Plan 02 | `users` | Sprint-0 | Auth ve tenant admin için temel |
| Plan 03 | `roles`, `permissions`, `user_roles` | Sprint-1 | RBAC olmadan protected endpoint olmaz |
| Plan 04 | `employees` | Sprint-1 | Core HR değerinin başlangıcı |
| Plan 05 | `departments`, `positions` minimal | Sprint-1/S2 | Employee assignment için gerekli |
| Plan 06 | `employee_assignments` | S2 | Effective-dated org ilişkisi |
| Plan 07 | `audit_events` | S2 | Kritik değişikliklerin izlenmesi |
| Plan 08 | `employee_documents`, `document_types` | S3 | Özlük belge yönetimi |
| Plan 09 | `leave_types`, `leave_balances` | S4 | İzin motoru başlangıcı |
| Plan 10 | `leave_requests`, `approval_tasks` | S4/S5 | İzin ve onay akışı |

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

## 4. RBAC tabloları

### `roles`

Alanlar:

- `id`
- `tenant_id`
- `code`
- `name`
- `system_role`
- `created_at`
- `updated_at`

Unique: `(tenant_id, code)`.

### `permissions`

Alanlar:

- `id`
- `code`
- `description`
- `module`

Unique: `code`.

### `user_roles`

Alanlar:

- `tenant_id`
- `user_id`
- `role_id`
- `valid_from`
- `valid_until`

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
- `created_at`
- `updated_at`

Unique: `(tenant_id, employee_number)`.

`archived_at is null` normal employee yüzeyidir. Normal `DELETE` satırı kaldırmaz, `archived_at`
set eder ve tekrarlandığında no-op olur. Unique constraint arşivlenen employee number'ını tenant
içinde rezerve tutar.

Hassas alanlar ilk migration'a alınmayabilir; TCKN/IBAN gibi alanlar field encryption planı netleşince eklenmelidir.

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

## 6. RLS/tenant guard planı

PostgreSQL RLS uygulanacaksa tenant-owned tablolar için standart:

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON employees
USING (tenant_id = current_setting('app.tenant_id')::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

İlk aşamada RLS migration'ları ayrı ve test edilebilir tutulmalıdır.

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
| RLS catalog test | Tenant tablolarında RLS açık mı |
| Cross-tenant query | Tenant A verisi Tenant B'den görünmüyor mu |
| Relational preflight | Orphan ve cross-tenant satırlar constraint DDL'den önce raporlanıyor mu |
| PostgreSQL direct write | Her composite ilişki servis bypass edildiğinde cross-tenant write'ı reddediyor mu |
| Data-preserving round trip | Valid satırlar `0008 → head → 0008 → head` boyunca korunuyor mu |
| Concurrent leave decision | PostgreSQL row lock approve/reject için tam bir terminal winner sağlıyor mu |
| Concurrent idempotency | Aynı tenant/key ile yarışan create komutları tek resource ve receipt üretiyor mu |
| Archive retention | Normal DELETE satırı/history'yi koruyor ve child FK fiziksel silmeyi `RESTRICT` ediyor mu |
| Idempotency rollback | Başarısız keyed komut receipt bırakmadan aynı key ile retry edilebiliyor mu |

## 8. Seed planı

Mevcut local/development seed deterministik ve idempotenttir:

- 2 tenant: `wealthy-falcon-demo`, `atlas-people-demo`.
- 5 user, 8 employee ve 5 leave request.
- Department ve position değerleri mevcut employee kolonlarında sentetik metin olarak tutulur;
  ayrı role/department/position kayıtları henüz seed edilmez.
- Tenant, user, employee ve leave request UUID'leri tekrar çalıştırmalarda sabittir.

Role atamaları ile ayrı organization/department/position tablolarını içeren daha geniş seed,
ilgili ürün fazlarının şeması ve authorization sözleşmesi uygulanmadan eklenmez. Seed verisi gerçek
kişisel veri içermemelidir.

## 9. Kabul kriterleri

- Migration sırası küçük ve anlaşılırdır.
- Tenant ve user sonrası RBAC ve employee sırası nettir.
- Hassas alanlar encryption kararı olmadan rastgele eklenmez.
- RLS testleri planlanmıştır.
- Seed verisi sentetik olacaktır.
- Employee normal DELETE archive eder; history ve employee number korunur.
- Leave kararları PostgreSQL row lock ile one-winner'dır.
- Desteklenen keyed komutlar tenant-global receipt ile ilk başarılı snapshot'ı replay eder.
- P0E receipt TTL/cleanup ve employee purge HTTP endpointi eklemez.

## 10. Faz 0 karar ve uygulama durumu

| Konu | Karar / mevcut durum | Uygulama zamanı |
|---|---|---|
| UUID | Public ID'ler uygulama tarafında `uuid4` ile üretilir; DB server default eklenmez | Uygulandı |
| User email canonicalization | Mevcut `(tenant_id, email)` unique davranışı case-sensitive kalır; auth öncesi explicit `lower(btrim(email))` normalize kolon/index kullanılır, `citext` kullanılmaz | Phase 2 auth migration'ından önce |
| RLS | Faz 0 composite FK + app guard katmanını kurar; PostgreSQL RLS ve transaction-local tenant context Faz 1'de ayrı expand migration'dır | Faz 1 |
| F1A tenant settings | `0013` fixed-column settings check'leri, existing-tenant backfill ve custom-settings downgrade refusal ekler; tenant plan/region/locale input allowlist'i API/domain'dedir; arbitrary JSON/features/legal entity yoktur | F1A; SQLite + PostgreSQL 17.10 gate passed |
| Hassas alan encryption | Key/provider ve envelope encryption kararı olmadan TCKN, IBAN, ücret veya sağlık kolonları eklenmez | İlgili employee/security fazı öncesi Murat kararı |
| Audit immutability | Audit aynı PostgreSQL DB'de append-only write modelidir; runtime role update/delete engeli ve recorder Faz 2'de birlikte uygulanır | Faz 2 |

Bu tablo tamamlanmış davranış ile hedef kararı ayırır. Özellikle TCKN, IBAN ve maaş gibi alanlar,
encryption ve masking kararı netleşmeden migration'a eklenirse sonradan veri taşıma maliyeti doğar.

## 11. İlgili dokümanlar

- [Veritabanı Modeli ve ERD](../05-api-veri/01-veritabani-modeli-ve-erd.md)
- [Çok Kiracılık ve Veri İzolasyonu](../04-mimari/02-cok-kiracilik-ve-veri-izolasyonu.md)
- [Sprint-0 / Sprint-1 Backlog ve Task Planı](02-sprint-0-1-backlog-ve-task-plani.md)
