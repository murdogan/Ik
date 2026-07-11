# IK — İnsan Kaynakları Yönetim Sistemi

Bu repo, Türkiye pazarı öncelikli ve global pazara açılabilir bir İnsan Kaynakları Yönetim Sistemi için ürün, strateji, modül, mimari, güvenlik, test, canlıya alma dokümantasyonu ve ilk backend uygulama iskeletini içerir.

## Çalışma yaklaşımı

Bu çalışma üç kaynaktan beslendi:

1. **Codex referansı:** Dosya ve modül iskeleti için ana kontrol listesi.
2. **Claude referansı:** Derinlik, detay seviyesi ve uygulanabilirlik standardı.
3. **Mevcut repo geçmişi:** Daha önce hazırlanmış dokümanlar Git geçmişinde korunur; aktif ağaçta temiz foundation tutulur.

## İlk prensipler

- Önce dokümantasyon, sonra kod.
- Her kararın sahibi ve etkisi belli olmalı.
- Her modül MVP / V1 / V2 ayrımıyla yazılmalı.
- Her modül veri, API, yetki, KVKK, audit ve test etkisiyle ele alınmalı.
- Kırık link, yarım dosya ve boş vaat bırakılmamalı.
- Kod tarafında test edilmemiş scaffold “bitti” sayılmamalı.

## Doküman yapısı

Ana giriş noktası: [docs/README.md](docs/README.md)

```text
docs/
├── 00-genel/              # Konvansiyonlar, roller, terimler, karar kayıtları
├── 01-strateji-pazar/     # Vizyon, pazar, rakipler, fiyatlandırma
├── 02-urun/               # Personalar, JTBD, MVP/V1/V2 kapsamı, metrikler
├── 03-moduller/           # Tüm ürün modülleri ve ortak modül formatı
├── 04-mimari/             # Teknik mimari, multi-tenancy, teknoloji kararları
├── 05-api-veri/           # Veritabanı, API, webhook, entegrasyon, migrasyon
├── 06-guvenlik-uyum/      # Auth, RBAC, KVKK/GDPR, OWASP, AI güvenliği
├── 07-operasyon/          # DevOps, observability, test, runbook
├── 08-yurutme/            # Roadmap, ekip, GTM, risk/backlog
└── 09-uygulama/           # Sprint backlog, OpenAPI, ERD, wireframe, import, demo, readiness
```

## Kod yapısı

```text
backend/
├── app/
│   ├── platform/          # Canonical cross-cutting port ve altyapı sınırları
│   ├── modules/           # Canonical ürün modülü sahiplik sınırları
│   ├── api/               # Geçiş alanındaki API router'ları
│   ├── core/              # Geçiş uyumluluk config/tenancy paketi
│   ├── db/                # SQLAlchemy session ve declarative base
│   ├── models/            # Geçiş alanındaki tenant-scoped ORM modelleri
│   ├── schemas/           # Geçiş alanındaki Pydantic şemaları
│   ├── services/          # Geçiş alanındaki uygulama/domain servisleri
│   └── main.py            # FastAPI app factory
└── tests/                 # Pytest testleri
```

`platform/` ve `modules/` Faz 0'da import-boundary testleriyle korunan canonical hedeftir.
F1A tenant lifecycle/value policy'sini `app.modules.core.domain` içine yerleştirir; mevcut
employee/leave kodu davranış uyumluluğu için flat paketlerde artımlı geçiş alanı olarak kalır.
F1D feature-flag katalogunu CORE domain'de, dört redacted tenant platform event sözleşmesini CORE
application katmanında tutar; `app.platform.events` yalnız framework-neutral audit primitive/port
ve provider fake/default adapter sınırıdır.
F1E yeni ürün modülü veya şema eklemeden yerel Faz 1 security/product/OpenAPI teknik gate'ini
tamamlar; exact on platform/current-tenant operation'ı
`x-required-principal: platform|tenant` metadata'sıyla belgeler ve queue'yu supervisor push +
Murat review checkpoint'inde durdurur.

## Lokal geliştirme

Gereksinim: `uv` ve Python 3.13. Komutlar repo kökünden çalıştırılır.

Kurulum:

```bash
uv sync --all-groups
```

Commit öncesi kalite kapıları:

```bash
uv run ruff check backend
uv run pytest -q
```

`uv run pytest -q` varsayılan hızlı hattıdır. PostgreSQL bağlantısı istemeden SQLite
unit/API/migration testlerini çalıştırır; `postgres` işaretli entegrasyon testleri ayrı ve
opt-in'dir.

PostgreSQL 16+ test servisini lokal Docker ile başlatıp opt-in hattı çalıştırmak için:

```bash
docker compose up -d --wait postgres
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres uv run pytest -q -m postgres
```

`docker compose` satırı yalnız local service başlangıç örneğidir. Tam lane, password saklamayan
geçici bir `LOGIN NOSUPERUSER NOBYPASSRLS` migration-owner rolüyle yeniden bağlanır; bu nedenle
disposable test cluster'ının host authentication'ı bu geçici role izin vermelidir. Stock service bu
koşul ayrıca sağlanmadan tam-lane kanıtı sayılmaz. F1E gate'i bu gereksinimi karşılayan disposable,
local-trust PostgreSQL 17.10 cluster'ında çalıştırılmıştır.

`IK_TEST_DATABASE_URL` PostgreSQL hattı için zorunludur ve disposable PostgreSQL test cluster'ındaki
yönetim bağlantısını göstermelidir. Fixture her PostgreSQL testi için benzersiz/geçici bir test
veritabanı oluşturur ve test sonunda siler; uygulama veya geliştirici veritabanında
upgrade/downgrade çalıştırmaz. Ancak F1C/F1D migration'ları cluster-global
`wealthy_falcon_app`/`wealthy_falcon_platform` capability rollerini oluşturup/harden edip
downgrade'de bilinçli olarak korur. Bu nedenle shared operational cluster kullanılmaz; admin role
database/role/extension yönetebilmelidir. Test başına database izolasyonu, retained
archive/idempotency verisinin migration testlerini collection sırasına bağımlı yapmasını engeller.
Bu hat Alembic upgrade/downgrade ve drift kontrollerini, PostgreSQL'e özgü tip/kısıt
davranışlarını, 10k employee query planlarını ve mevcut API sözleşmesini gerçek PostgreSQL
üzerinde doğrular. P0F performans fixture'ını ve machine-readable EXPLAIN kanıtını tek başına
çalıştırmak için:

```bash
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres \
  uv run pytest -q -m postgres \
  backend/tests/integration/test_postgresql_p0f_performance.py -s
```

Ayrıntılı veri profili, query-count sınırları ve yakalanan PostgreSQL 16.4 planları
[`docs/09-uygulama/12-phase-0-query-performance-baseline.md`](docs/09-uygulama/12-phase-0-query-performance-baseline.md)
içindedir.

Uygulama veritabanı engine/sessionmaker yaşam döngüsünü FastAPI lifespan yönetir ve
kapanışta engine'i dispose eder. Runtime ayarları `IK_DATABASE_POOL_SIZE`,
`IK_DATABASE_MAX_OVERFLOW`, `IK_DATABASE_POOL_TIMEOUT_SECONDS`,
`IK_DATABASE_POOL_RECYCLE_SECONDS`, `IK_DATABASE_CONNECT_TIMEOUT_SECONDS`,
`IK_DATABASE_STATEMENT_TIMEOUT_MS` ve `IK_DATABASE_IDLE_TRANSACTION_TIMEOUT_MS` ortam
değişkenleriyle override edilebilir. PostgreSQL 16'da sorgu ve açık kalmış transaction
korumaları sırasıyla `statement_timeout` ve `idle_in_transaction_session_timeout` olarak
uygulanır. Varsayılanlar sırasıyla pool `5`, overflow `10`, pool bekleme `30` saniye,
recycle `1800` saniye, bağlantı `10` saniye, statement `30000` ms ve idle transaction
`60000` ms'dir.

P0C write transaction sınırında transitional `EmployeeCommandHandler` ve
`LeaveRequestCommandHandler`, `SqlAlchemyUnitOfWork.execute` üzerinden tek transaction sahibini
kullanır. Employee create/update/archive ile leave request create/approve/reject/cancel servisleri
gerekli constraint ve generated-value davranışı için `flush()` eder fakat `commit()` etmez;
başarılı komutu commit etme ve hata halinde rollback yapma sorumluluğu yalnız UoW'dedir. Read
path'leri request-scoped session ve doğrudan SQLAlchemy-aware service/query koduyla basit kalır;
SQLAlchemy metotlarını taklit eden generic repository eklenmemiştir. Flush sonrası zorlanmış hata
ve fresh-session testleri employee/leave değişikliklerinin kısmi persist edilmediğini doğrular.
Bu mimari değişiklik schema veya Alembic migration eklemez.
Local demo seed ayrı bir script command'dır. `seed_demo_data` servisi yalnız flush eder;
`scripts/seed_demo_data.py` içindeki `session_factory.begin()` tenant/user/employee/leave seed
adımlarının tamamı için tek dış commit/rollback sahibidir. AST architecture gate'i
`backend/app/services` altında transaction completion çağrılarını reddeder.

Faz 0 worker spike'ı ADR-008'de Dramatiq 2.2 + Redis'i hedef adapter olarak seçer. Runtime provider
ve broker kurulmamıştır. `app.platform.workers` yalnız non-zero tenant, idempotency key, JSON
payload, timeout ve attempt sınırı isteyen dar `JobQueue`/`JobSpec` portu ile deterministik test
fake'ini içerir. F1B worker request context'ini fixed JSON-safe allowlist ile doğrular:
safe request/trace, job ile aynı tenant, optional actor/session ve support UUID placeholder'ları ile
authentication strength. Extra/free-text metadata, tenant slug, PII ve raw auth materyali kabul
edilmez; tenantless request context serialize edilemez. F1E worker-fake gate'inde `tenant_id` her
job için zorunlu kalır ve `JobOrigin.REQUEST|SYSTEM` provenance'ı explicit olmak zorundadır.
Request-origin job context'siz kurulamaz; context tenant'ı job tenant'ıyla exact eşleşir ve A↔B
uyuşmazlığı enqueue edilmeden reddedilir. System/outbox job'u yalnız explicit `SYSTEM` origin ile
context'siz kurulabilir ve request context taşıyamaz. Gerçek provider ayrıca authenticated
transport ve transaction-local DB tenant binding uygulamadan HR verisi çalıştıramaz.

Historical Phase 0 OpenAPI contract'ı
`backend/tests/contracts/phase0_openapi_contract.json` içinde operation/component bazlı canonical
hash manifestiyle sabitlenir. Contract testi, metadata testleri ve backend smoke registry birlikte
o checkpoint'teki 14 generated operasyonu ve runtime `/openapi.json` dahil 15 documented endpointi
korur. Historical F1A tam olarak yedi additive platform/tenant operation'ı ekleyerek 21 generated
operation ve runtime `/openapi.json` dahil 22 documented endpoint'e ulaşmıştır. Additive snapshot ayrı
`backend/tests/contracts/f1a_openapi_contract.json` dosyasında tutulur; historical Phase-0
manifesti yeniden yazılmaz. F1A OpenAPI/metadata testleri ve runtime smoke bu iki sayıyı doğrular.
F1B yeni endpoint eklemeden F1A'nın yedi success operation'ını `{data,meta}` zarfına geçirir,
platform listesini `(created_at asc, id asc)` opaque cursor + bounded `limit` standardına taşır ve
üç safe correlation response header'ını OpenAPI'de belgeler. Historical Phase-0 employee/leave
contract'ı ayrı compatibility assertion'larıyla korunur. Historical F1D contract'ı platform feature
`GET/PATCH` ve tenant feature `GET` olmak üzere üç additive operation ile 24 generated operation ve
runtime `/openapi.json` dahil 25 documented endpoint'tir; historical F1A/F1B manifestleri overwrite
edilmeden ayrı intentional F1D diff/snapshot ile korunur. F1E operation/schema sayısını değiştirmez;
exact on Faz 1 operation'ına `x-required-principal: platform|tenant` ekleyen intentional metadata
diff'i `backend/tests/contracts/f1e_openapi_contract.json` içinde ayrıca dondurulur ve runtime
registry 25 endpoint olarak kalır. Bu extension injected-principal sınırını belgeler; Faz 2
authentication/session/RBAC uygulanmadan standard OpenAPI `security` veya sahte bearer scheme
eklenmez.

P0D ile mevcut tenant-owned parent tablolarından `employees` ve `users` için `(tenant_id, id)`
candidate key'leri; `leave_requests` ve `leave_balance_summaries` içindeki dört employee/user
referansı için `(tenant_id, foreign_id)` composite foreign key'leri eklenmiştir. `0009` expand
migration'ı sekiz mevcut ilişkiyi orphan/cross-tenant veri için tarar, PostgreSQL'de candidate
index'leri concurrent ve tekrar çalıştırılabilir biçimde kurar, yeni foreign key'leri `NOT VALID`
olarak eski scalar foreign key'lerle birlikte devreye alır ve concurrent-index penceresini kapatmak
için preflight'ı constraint lock'ları altında yeniden çalıştırır. `0010` contract migration'ı yeni
foreign key'leri validate ettikten sonra yalnız eski employee/user scalar foreign key'lerini
kaldırır. Böylece doğrudan DB write yolu tenant'lar arası employee/user bağlantısı kuramaz;
tenant root foreign key'leri ve mevcut servis guard'ları korunur. RLS bu historical P0D/F1A
değişikliklerinin parçası değildir; ayrı F1C rollout'u aşağıda bu katmanların üzerine eklenmiştir.

P0E ile kritik create/decision POST komutları opsiyonel canonical `X-Idempotency-Key` destekler.
Key tenant genelinde unique'tir; aynı tenant/key ve aynı semantik request ilk başarılı
`201`/`200` body'sini kalıcı receipt'ten tekrar oynatır. Command, hedef id veya body değişirse
`409 idempotency_key_mismatch` döner; aynı key başka tenant'ta bağımsızdır. Receipt'ler şimdilik
TTL temizliği olmadan saklanır. Leave approve/reject/cancel komutları tenant-scoped satırı
PostgreSQL row lock ile serialize eder; eşzamanlı farklı kararlardan yalnız biri kazanır ve kaybeden
mevcut `409 leave_request_transition_conflict` sözleşmesini alır.

`DELETE /api/v1/employees/{employee_id}` path ve `204` uyumluluğunu koruyarak artık
`archived_at` yazar; aynı tenant için tekrar çağrı no-op `204` döner. Normal employee
liste/detail/update, dashboard, yeni leave request ve leave-balance eligibility yolları arşivli
kaydı görünmez sayar. Employee number tarihsel kimlik olarak reserved kalır; mevcut leave request
ve balance kayıtları korunur. Bu iki child foreign key artık `ON DELETE RESTRICT` kullanır. Public
purge endpoint'i yoktur; tenant-root cascade yalnız kısıtlı operator retention/offboarding yolu
olarak değerlendirilir.

F1A `0013_tenant_settings` ile tenant başına fixed `week_start_day`, `date_format`, `time_format`
kolonlarını ve existing-tenant default backfill'ini ekler. Locale/timezone tenant'ın typed temel
alanlarıdır. Downgrade yalnız tüm settings satırları default değerlerdeyse tabloyu kaldırır;
custom değer varsa `custom_tenant_settings` sayılı preflight ile veri kaybından önce durur.
Platform provisioning/lifecycle ve tenant current/settings API'leri injected immutable
principal ister; default dependency `403` ile fail closed olur. Caller-supplied tenant/user header,
path veya body kimliği authorization değildir. Canonical create/PATCH planları
`core|professional|enterprise`; existing `premium` yalnız read compatibility'dir. Feature flags,
auth/RBAC/audit persistence/RLS/legal entity bu kesitte yoktur.

F1B global middleware'i her HTTP isteğine frozen/slotted `RequestContext` bağlar. Context safe
opaque `request_id` (en fazla 128), non-zero lowercase 32-hex `trace_id`, optional tenant,
actor/session, authentication-strength ve support-session placeholder'larını taşır; enrichment yeni
instance üretir. Invalid, duplicate, conflicting, e-posta/PII veya JWT biçimli correlation inputu
yeniden üretilir ve yansıtılmaz/loglanmaz. Her HTTP response `X-Request-Id`, `X-Trace-Id` ve
deprecated request-ID alias'ı `X-Correlation-Id` taşır. Bu context auth, RBAC veya audit persistence
uygulamaz ve F1B herhangi bir Alembic migration eklemez.

F1C `0014_f1c_postgresql_rls` ile mevcut altı tenant-owned tabloyu ve normal app rolünün metadata
görünürlüğü için `tenants` root'unu PostgreSQL RLS `ENABLE + FORCE` korumasına alır. Normal
`wealthy_falcon_app` capability rolü her transaction'da `SET LOCAL app.tenant_id` ile scope edilir;
eksik/invalid context fail closed olur ve commit/rollback sonrası pool state'i taşımaz. Ayrı
`wealthy_falcon_platform` rolü tenant metadata DML ve provisioning-only typed-settings INSERT alır;
settings read/update veya HR tablo grant/policy'si almaz. Tenant app root update'i locale/timezone
ve ORM timestamp kolonlarıyla sınırlıdır. İki rol de `NOLOGIN`, `NOINHERIT`, `NOSUPERUSER`,
`NOBYPASSRLS`'dir; production runtime login'i table owner olmamalı, `NOINHERIT` gateway olarak
yalnız bu rolleri explicit
`SET LOCAL ROLE` ile kullanmalıdır. SQLite hızlı uyumluluk lane'i olmaya devam eder; catalog,
raw-SQL, role ve pool-reuse kanıtı `-m postgres` integration lane'indedir. Endpoint/OpenAPI contract
sayısı F1C'de değişmez.

F1D `0015_f1d_feature_flags` ile `tenant_feature_flags(tenant_id,key)` tablosunu ve nullable
`tenants.active_employee_limit` platform metadata kolonunu ekler. Sabit flag sırası
`organization`, `employees`, `documents`, `leave`, `self_service`, `reporting`, `notifications`;
yalnız `employees`, `leave` ve `reporting` default `true` değerindedir. Migration mevcut tenant'ları
bu yedi defaultla backfill eder; yeni provisioning aynı satırları settings ile tek UoW'da oluşturur.
Tenant capability yalnız kendi flag satırlarını `SELECT`, platform
capability yalnız `SELECT/INSERT/UPDATE` edebilir; iki role de `DELETE` verilmez ve tablo PostgreSQL'de
RLS `ENABLE + FORCE` altındadır. API effective flag'i `default|override` kaynağıyla döndürür;
bilinmeyen key ve müşteri bazlı kod fork'u yoktur.

`GET/PATCH /api/v1/platform/tenants/{tenant_id}/features` platform rollout yüzeyidir;
`GET /api/v1/tenant/features` yalnız injected tenant principal'ın kendi effective flag'lerini okur.
Platform list/detail response'undaki configured limit yalnız
`limits.active_employees` metadata'sıdır; employee tablosundan usage/count türetilmez. Dar platform
query service açık kolon projection'ıyla yalnız `tenants` tablosunu sorgular. Offboarding/closure
transition'ı metadata değişikliğiyle aynı PATCH'te birleştirilemez; terminal durum kuralları korunur.

Başarılı actual create/status/setting/flag değişiklikleri sırasıyla `tenant.created`,
`tenant.status_changed`, `tenant.setting_changed`, `feature_flag.changed` frozen/extra-forbid
sözleşmelerini aynı command UoW içinde recorder portuna verir. Sözleşmeler request/trace ve yalnız
allowlisted platform metadata taşır; generic payload/metadata, parola/token ve employee/HR alanı
taşıyamaz. Recorder guard marker/structural nesne ve sensitive alan ekleyen subclass'ı da reddeder.
Faz 1 default recorder doğrulanan event'i discard eder ve persistence iddiasında bulunmaz; Faz 2
aynı portu aynı-session append-only audit recorder ile değiştirecektir. F1D audit tablosu veya audit
read center eklemez.

F1E Faz 1 kapanışında Alembic şeması değişmez ve tek head `0015_f1d_feature_flags` kalır. Final
kanıt tekrarları hızlı migration hattında `36 passed`, tam PostgreSQL lane'inde `30 passed`,
PostgreSQL baseline upgrade/downgrade/drift/smoke hattında `8 passed` ve RLS + direct-DB saldırı
hattında `12 passed` üretmiştir. Authentication, session, RBAC ve append-only audit persistence Faz
2 işidir ve bu checkpoint'te başlatılmamıştır.

Veritabanı migration komutları:

```bash
uv run alembic history
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

`alembic.ini` lokal geliştirme veritabanını hedefler. Migration komutlarını yalnızca lokal/dev
veritabanına karşı çalıştırın; production/staging migration çalıştırma bu repo task akışının
parçası değildir. Yeni migration'lar küçük, geriye uyumlu ve tenant/user zincirini bozmayacak
şekilde hazırlanmalıdır; destructive değişiklikler Sprint-0 kapsamına alınmaz.

Lokal demo seed komutu:

```bash
uv run alembic upgrade head
uv run python scripts/seed_demo_data.py
```

Seed komutu yalnız `IK_ENVIRONMENT=local` veya `IK_ENVIRONMENT=dev` iken çalışır. Komut
idempotenttir; iki demo tenant, beş kullanıcı, sekiz çalışan ve beş izin talebini stabil UUID'ler
ile oluşturur veya demo fixture değerlerine geri günceller. Lokal test/smoke kullanımında hedef
veritabanı `--database-url` ile geçici olarak override edilebilir; komut SQLite veya local host
veritabanı dışındaki hedefleri reddeder. Production/staging deploy, cron, token, credential veya
`.env` değişikliği yapmaz.

Lokal app import smoke testi:

```bash
PYTHONPATH=backend uv run python -c "from app.main import create_app; print(create_app().title)"
```

Beklenen çıktı `IK Platform API` olmalıdır.

Lokal backend API smoke testi:

```bash
uv run python scripts/backend_api_smoke.py
```

Bu smoke testi server veya lokal PostgreSQL gerektirmez. FastAPI uygulamasını ASGI üzerinden
çalıştırır, geçici SQLite veritabanı oluşturur ve şu yüzeyi kontrol eder:

- `/health`
- `/`
- `/openapi.json`
- `/api/v1/platform/tenants` platform-principal provisioning ve `{data,meta}` içinde bounded,
  deterministic opaque-cursor metadata-only liste
- `/api/v1/platform/tenants/{tenant_id}` platform-safe detail ve explicit lifecycle PATCH
- `/api/v1/platform/tenants/{tenant_id}/features` yedi-key typed rollout GET/PATCH, configured
  override kaynağı, tenant-principal denial ve HR verisi içermeyen platform metadata sınırı
- `/api/v1/tenant` injected tenant-principal current metadata
- `/api/v1/tenant/settings` beş-key typed/allowlisted GET/PATCH
- `/api/v1/tenant/features` injected tenant-principal scope'undan yedi effective flag GET ve
  tenant A/B izolasyonu
- `/api/v1/dashboard/summary` active employee count, pending leave count, this-month
  starters, department distribution and recent activity
- `/api/v1/employees` liste + `department`/`status`/`q` filtreleri, deterministic
  `cursor`/`X-Next-Cursor` keyset pagination, geriye uyumlu deprecated `offset`, default
  `limit=50`, max `limit=200`, oluşturma/detay/güncelleme/silme
- `/api/v1/employees/{employee_id}/leave-balances` read-only manuel izin bakiyesi özetleri,
  `period_year` filtresi, tenant-scoped çalışan kontrolü ve mevcut leave requestlerden otomatik
  bakiye üretmeme davranışı
- `/api/v1/leave-requests` liste + `status`/`employee_id`/`start_date`/`end_date` filtreleri,
  deterministic `cursor`/`X-Next-Cursor` keyset pagination, geriye uyumlu deprecated `offset`,
  default `limit=50`, max `limit=200`, oluşturma/onay/red/iptal

Smoke testi ayrıca generated OpenAPI operasyonlarını, güncel dokümanlardaki endpoint tablolarını
ve runtime'da gerçekten çağrılan endpoint setini kendi coverage registry'siyle karşılaştırır;
dokümanlanan endpoint smoke kapsamı dışında kalırsa veya smoke senaryosunda hiç çağrılmazsa komut
fail olur.

F1A smoke/contract gate'i lifecycle, default-deny principals, typed extra-key rejection,
cross-tenant principal isolation ve platform response'unda HR alanı bulunmamasını da kanıtlamalıdır;
historical F1A gate `BACKEND_SMOKE_OK` ile 22 documented endpoint'i çalıştırmış ve F1A OpenAPI
snapshot'ını 21 generated operation için doğrulamıştır.

F1B smoke aynı 22-row registry'yi korurken bütün response'larda safe correlation header'larını,
unsafe inputun yansıtılmamasını, yedi platform/tenant `{data,meta}` response'unu, deterministic
platform cursor traversal'ını ve employee/leave plain-array compatibility'sini kontrol eder.

F1E final registry 24 generated operation ve `/openapi.json` dahil 25 documented endpoint bekler.
Smoke/contract güncellemesi üç feature operation'ını, fixed flag sırasını/default ve override
kaynağını, nested configured limit metadata'sını, tenant-principal/platform ayrımını, no-HR/no-
document-payload response sınırını ve exact on Faz 1 operation'ındaki
`x-required-principal: platform|tenant` metadata'sını yürütür. Historical F1D snapshot'ı
değiştirilmez; F1E ayrı snapshot'tır. Ruff, pytest, PostgreSQL ve 25-endpoint smoke tekrarlarının
exact sonuçları implementation-status kaydındadır.

OpenAPI dokümanı `/docs` altında okunabilir tag gruplarıyla yayınlanır: `System`, `Public`,
`Platform Tenants`, `Tenant Settings`, `Dashboard`, `Employees`, `Leave Balances`,
`Leave Requests`. W4C5 OpenAPI tag hygiene
kapsamında tag açıklamaları, tenant-aware operation summary/description metinleri ve
filtre/header açıklamaları güncel API docs okunabilirliği için netleştirildi; request/response
davranışı değişmedi. Historical W4C6 checkpoint'inde endpoint değişikliği yoktu; F1A daha sonra
yukarıdaki yedi operation ve iki tag'i additive olarak ekler.

Tenant header dependency hataları, API edge'deki merkezi `ApplicationError` mapper'ının
dönüştürdüğü typed domain/application hataları ve employee, leave balance, leave request
endpointlerindeki otomatik request validation `422` hataları şu zarfla döner:
`{ "error": { "code": "...", "message": "...", "details": null, "correlation_id": null } }`.
Bu kapsam `tenant_header_missing`, `tenant_header_invalid`, `tenant_slug_header_invalid`,
not-found, conflict, date-range, employee lifecycle, `employee_validation_error`,
`leave_balance_validation_error`, `leave_request_validation_error` ve leave transition
hatalarıdır. F1A platform/tenant yolları da default-deny, lifecycle ve
`platform_tenant_validation_error`/`tenant_settings_validation_error` yanıtlarını aynı zarfla
döner. Bu aileler dışındaki otomatik FastAPI validation `422` yanıtları henüz framework
varsayılanındadır.
F1B yeni platform/tenant hata body'lerinde `correlation_id` alanını validated/generated request ID
ile doldurur. Faz-0 employee/leave body adapter'ı yalnız valid legacy alias seçilen request ID ile
aynıysa onu taşır; aksi halde historical `null` davranışı korunur. Her iki durumda canonical
request/trace response header'ları vardır.
P0C mevcut employee/leave status, code ve public mesajlarını korur. Named
`uq_employees_tenant_employee_number` DB constraint ihlali pre-check yarışında da mevcut
`409 employee_number_conflict` yanıtına map edilir. Diğer bilinmeyen integrity hataları DB
detayı sızdırmadan `409 data_integrity_conflict`; SQLAlchemy `StaleDataError` ve tanınan DB
concurrency hataları `409 concurrent_write_conflict` döner.
W4A6 itibarıyla employee, leave balance ve leave request endpointlerinde bu public hata mesajları
kod içi ortak sabitlerden üretilir. Tenant header hataları aynı request içinde payload/query/path
validation hatası olsa bile önce normalize edilir; global FastAPI validation davranışı bu kapsamda
değiştirilmedi. W4B4 itibarıyla invalid tenant id mesajı gerçek sözleşmeyi açıkça söyler:
`X-Tenant-Id header must be a single canonical hyphenated UUID`.

Demo seed sonrası employee ve leave endpointleri için örnek tenant header'ları:

```http
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Eksik veya boş `X-Tenant-Id`, canonical hyphenated UUID olmayan tenant id değerleri, tekrarlı
`X-Tenant-Id` header'ları ve boş gönderilen `X-Tenant-Slug` `400` status koduyla aynı error
zarfını döner. Tekrarlı veya boş `X-Tenant-Slug` için mesaj
`X-Tenant-Slug header must be sent at most once and be non-empty when provided` olur.

Bu W4B3 örnekleri existing Faz-0 FastAPI davranışını gösterir: employee ve leave endpointleri
explicit compatibility olarak doğrudan schema/list döner. F1A'nın yedi tenant/platform success
operation'ı F1B ile `{data,meta}` standardına geçmiştir; bu migration Faz-0 örneklerini sessizce
değiştirmez.
HTTP request bloklarında gösterilen tenant header'ları her domain endpoint için zorunludur.
List endpointleri plain JSON array döner; eşleşen kayıt yoksa `200 []` yanıtı alınır ve pagination
body metadata dönmez. Employee ve leave-request listelerinde başka sayfa varsa response
`X-Next-Cursor` header'ı taşır; devam isteği `cursor` query parametresiyle yapılır. Bounded
`offset` yolu geriye uyumluluk için korunur ancak deprecated'dir. Create ve decision örneklerindeki
yeni `id` değerleri temsili server-generated kayıtlardır; gerçek çağrıda aktif tenant içindeki
mevcut kayıt id'leri kullanılmalıdır.

Employee list örneği:

```http
GET /api/v1/employees?department=Engineering&status=active&q=WF&limit=2&offset=0
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Response `200`:

```http
X-Next-Cursor: <opaque-versioned-cursor>
```

```json
[
  {
    "id": "f3000000-0000-4000-8000-000000000002",
    "employee_number": "WF-002",
    "first_name": "Bora",
    "last_name": "Demir",
    "email": "bora.demir@wealthyfalcon.demo",
    "department": "Engineering",
    "position": "Backend Engineer",
    "status": "active",
    "employment_start_date": "2026-06-10",
    "employment_end_date": null
  }
]
```

Employee create request/response örneği:

```http
POST /api/v1/employees
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
Content-Type: application/json
```

```json
{
  "employee_number": "WF-010",
  "first_name": "Selin",
  "last_name": "Arslan",
  "email": "selin.arslan@wealthyfalcon.demo",
  "department": "People",
  "position": "HR Operations Specialist",
  "status": "active",
  "employment_start_date": "2026-08-01",
  "employment_end_date": null
}
```

Response `201`:

```json
{
  "id": "f3000000-0000-4000-8000-000000000010",
  "employee_number": "WF-010",
  "first_name": "Selin",
  "last_name": "Arslan",
  "email": "selin.arslan@wealthyfalcon.demo",
  "department": "People",
  "position": "HR Operations Specialist",
  "status": "active",
  "employment_start_date": "2026-08-01",
  "employment_end_date": null
}
```

Employee detail/update/delete örnekleri:

```http
GET /api/v1/employees/f3000000-0000-4000-8000-000000000002
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Response `200`:

```json
{
  "id": "f3000000-0000-4000-8000-000000000002",
  "employee_number": "WF-002",
  "first_name": "Bora",
  "last_name": "Demir",
  "email": "bora.demir@wealthyfalcon.demo",
  "department": "Engineering",
  "position": "Backend Engineer",
  "status": "active",
  "employment_start_date": "2026-06-10",
  "employment_end_date": null
}
```

```http
PATCH /api/v1/employees/f3000000-0000-4000-8000-000000000002
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
Content-Type: application/json
```

```json
{
  "position": "Senior Backend Engineer",
  "status": "on_leave"
}
```

Response `200`:

```json
{
  "id": "f3000000-0000-4000-8000-000000000002",
  "employee_number": "WF-002",
  "first_name": "Bora",
  "last_name": "Demir",
  "email": "bora.demir@wealthyfalcon.demo",
  "department": "Engineering",
  "position": "Senior Backend Engineer",
  "status": "on_leave",
  "employment_start_date": "2026-06-10",
  "employment_end_date": null
}
```

```http
DELETE /api/v1/employees/f3000000-0000-4000-8000-000000000002
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Response `204`: no body.

Employee lifecycle kuralı: `terminated` status `employment_end_date` gerektirir; `active` ve
`on_leave` kayıtlarda `employment_end_date` `null` olmalıdır. Mevcut kayıtla birleştirildikten
sonra bu kuralı bozan güncellemeler `employee_invalid_lifecycle` koduyla `422` döner.
Employee endpointlerinde generic request validation hataları `employee_validation_error` kodu ve
`Employee request validation failed` mesajıyla aynı error zarfını kullanır.
Null `status` gibi lifecycle validation hataları ise generic validation yerine
`employee_invalid_lifecycle` kodu ve sabit lifecycle mesajıyla döner.

Employee `404` not-found ve tenant scope dışı kayıt örneği:

```json
{
  "error": {
    "code": "employee_not_found",
    "message": "Employee not found",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Employee duplicate number `409` örneği:

```json
{
  "error": {
    "code": "employee_number_conflict",
    "message": "Employee number already exists for this tenant",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Leave balance summary örneği:

```http
GET /api/v1/employees/f3000000-0000-4000-8000-000000000002/leave-balances?period_year=2026
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Response `200`:

```json
[
  {
    "id": "f5000000-0000-4000-8000-000000000001",
    "employee_id": "f3000000-0000-4000-8000-000000000002",
    "leave_type": "annual",
    "period_year": 2026,
    "opening_balance_days": 20.0,
    "used_days": 5.0,
    "planned_days": 2.0,
    "remaining_days": 13.0,
    "calculation_mode": "manual_placeholder",
    "external_integration_enabled": false
  }
]
```

Bu endpoint W1C2/W2C2/W3C2/W4C2 kapsamında yalnız read-only manuel placeholder'dır. İzin hak
edişi/accrual, resmi tatil hesabı, payroll/bordro, SGK, banka, PDKS, AI veya dış entegrasyon
içermez. `external_integration_enabled` alanı bu placeholder yüzeyinde sabit `false` döner.
W3C2 testleri persistence katmanının yalnız manuel summary kolonlarını taşıdığını ve response
schema'sının manuel placeholder dışı calculation mode kabul etmediğini sabitler.
W4C2 regresyonu, çalışanın mevcut leave request kayıtları olsa bile manuel summary satırı yoksa
endpointin sentetik bakiye üretmeden `200 []` döndüğünü sabitler.
Leave balance endpointinde generic request validation hataları `leave_balance_validation_error`
kodu ve `Leave balance request validation failed` mesajıyla aynı error zarfını kullanır.
Eksik tenant header, invalid path/query validation hatalarından önce `tenant_header_missing`
zarfına normalize edilir.
Tenant içindeki çalışan için manuel bakiye özeti yoksa response `200 []` olur; tenant scope dışı
çalışan için `employee_not_found` `404` zarfı döner.

Leave request list örneği:

```http
GET /api/v1/leave-requests?status=pending&employee_id=f3000000-0000-4000-8000-000000000002&start_date=2026-08-01&end_date=2026-08-31&limit=10&offset=0
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Response `200`:

```json
[
  {
    "id": "f4000000-0000-4000-8000-000000000001",
    "employee_id": "f3000000-0000-4000-8000-000000000002",
    "leave_type": "annual",
    "start_date": "2026-08-03",
    "end_date": "2026-08-07",
    "status": "pending",
    "requested_by_user_id": "f2000000-0000-4000-8000-000000000002",
    "decided_by_user_id": null,
    "decision_note": null
  }
]
```

Leave request create request/response örneği:

```http
POST /api/v1/leave-requests
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
Content-Type: application/json
```

```json
{
  "employee_id": "f3000000-0000-4000-8000-000000000003",
  "leave_type": "annual",
  "start_date": "2026-09-14",
  "end_date": "2026-09-18",
  "requested_by_user_id": "f2000000-0000-4000-8000-000000000002"
}
```

Response `201`:

```json
{
  "id": "f4000000-0000-4000-8000-000000000010",
  "employee_id": "f3000000-0000-4000-8000-000000000003",
  "leave_type": "annual",
  "start_date": "2026-09-14",
  "end_date": "2026-09-18",
  "status": "pending",
  "requested_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decided_by_user_id": null,
  "decision_note": null
}
```

Leave request endpointlerinde generic request validation hataları
`leave_request_validation_error` kodu ve `Leave request validation failed` mesajıyla aynı error
zarfını kullanır. Leave create tarih sırası ve liste tarih aralığı kuralları
`leave_request_invalid_date_range` koduyla `422` döner.
Approve/reject/cancel decision endpointlerinde non-pending talepler aynı
`leave_request_transition_conflict` kodu ve `Only pending leave requests can be decided` mesajını
kullanır.

Invalid leave request date filter `422` örneği:

```json
{
  "error": {
    "code": "leave_request_invalid_date_range",
    "message": "Leave request end_date filter must be on or after start_date",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Cross-tenant veya eksik talep sahibi kullanıcı `404` örneği:

```json
{
  "error": {
    "code": "user_not_found",
    "message": "User not found",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Leave approve request/response örneği:

```http
POST /api/v1/leave-requests/f4000000-0000-4000-8000-000000000001/approve
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
Content-Type: application/json
```

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Approved with team coverage."
}
```

Response `200`:

```json
{
  "id": "f4000000-0000-4000-8000-000000000001",
  "employee_id": "f3000000-0000-4000-8000-000000000002",
  "leave_type": "annual",
  "start_date": "2026-08-03",
  "end_date": "2026-08-07",
  "status": "approved",
  "requested_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Approved with team coverage."
}
```

Leave reject/cancel response shape'i aynı decision body ile çalışır. Aşağıdaki path id'leri
bağımsız örneklerde pending talepleri temsil eder:

```http
POST /api/v1/leave-requests/f4000000-0000-4000-8000-000000000011/reject
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
Content-Type: application/json
```

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Customer launch coverage is required."
}
```

Response `200`:

```json
{
  "id": "f4000000-0000-4000-8000-000000000011",
  "employee_id": "f3000000-0000-4000-8000-000000000002",
  "leave_type": "annual",
  "start_date": "2026-08-03",
  "end_date": "2026-08-07",
  "status": "rejected",
  "requested_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Customer launch coverage is required."
}
```

```http
POST /api/v1/leave-requests/f4000000-0000-4000-8000-000000000012/cancel
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
Content-Type: application/json
```

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decision_note": "Employee cancelled the request."
}
```

Response `200`:

```json
{
  "id": "f4000000-0000-4000-8000-000000000012",
  "employee_id": "f3000000-0000-4000-8000-000000000002",
  "leave_type": "annual",
  "start_date": "2026-08-03",
  "end_date": "2026-08-07",
  "status": "cancelled",
  "requested_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decision_note": "Employee cancelled the request."
}
```

Pending olmayan talepte tekrar decision işlemi `409` döner:

```json
{
  "error": {
    "code": "leave_request_transition_conflict",
    "message": "Only pending leave requests can be decided",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Başarılıysa `BACKEND_SMOKE_OK` çıktısı verir.

Opsiyonel lokal HTTP landing/health smoke testi:

Terminal 1:

```bash
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

Terminal 2:

```bash
uv run python scripts/staging_smoke_test.py http://127.0.0.1:8001
```

Smoke testi `/` ve `/health` endpointlerini kontrol eder; başarılıysa `SMOKE_OK` çıktısı verir.
Staging için aynı script yalnızca mevcut çalışan URL'ye karşı çalıştırılır:

```bash
uv run python scripts/staging_smoke_test.py https://<staging-url>
```

Bu komut deploy, cron veya ortam ayarı değiştirmez.

Beklenen sonuç:

- Ruff backend kontrolü hata vermez.
- Pytest tüm testleri yeşil döndürür.
- App import edilir ve `IK Platform API` çıktısı verir.
- Backend API smoke testi `BACKEND_SMOKE_OK` çıktısı verir.
- Opsiyonel HTTP landing/health smoke testi `SMOKE_OK` çıktısı verir.

## F2A invitation → activation → login demo

The local bootstrap creates no committed password or token. It resets only the synthetic demo
admin and prints one short-lived activation URL to the current terminal:

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run python scripts/seed_demo_data.py --auth-demo
```

Start the API and web app in separate terminals:

```bash
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open the printed `DEMO_AUTH_ACTIVATION_URL`, choose a password of at least 12 characters, then log
in at `http://localhost:3000/login` with organization code `wealthy-falcon-demo` and email
`admin@wealthyfalcon.demo`.

An API client can use that login response's short-lived `data.access_token` as
`Authorization: Bearer <token>` when calling `POST /api/v1/users/invitations`; the response returns
the new user's fragment-based activation URL once. Caller-supplied tenant headers and body fields
do not select the invitation tenant.

Local/dev uses a process-local random signing key. Staging/production deliberately refuses to
start without `IK_AUTH_SIGNING_KEY` supplied out of band and an HTTPS `IK_FRONTEND_BASE_URL`; no
secret or `.env` file is part of this repository flow. Set the non-secret `BACKEND_API_URL` during
`next build` for staging because the Next.js rewrite destination is compiled into the build.

## Branch iş akışı

`main` korumalıdır; değişiklikler kısa ömürlü branch üzerinde yapılır.

```bash
git switch main
git pull --ff-only
git switch -c <task-branch>
git status --short --branch
```

Task bitince kalite kapıları çalıştırılır ve yalnızca ilgili dosyalar commitlenir:

```bash
uv run ruff check backend
uv run pytest
git add README.md docs/<ilgili-dosya>.md
git commit -m "docs(T1): document local development commands"
```

## CI

GitHub Actions workflow template'i: `docs/09-uygulama/templates/backend-ci.yml`

Not: Bu template `.github/workflows/ci.yml` olarak taşındığında GitHub token'ında `workflow` scope gerekir. Mevcut ortamda bu scope olmadığı için workflow şimdilik template olarak tutulur.

Template aktive edildiğinde şunları çalıştıracaktır; repoda aktif `.github/workflows` dosyası
henüz yoktur:

- `uv sync --all-groups`
- `uv run ruff check backend`
- `uv run pytest -q -m "not postgres"`
- PostgreSQL 16 service ile `uv run pytest -q -m postgres`

## Durum

P0A–P0G ile Faz 0 ve F1A–F1D base review branch kapıları tamamlanmıştır; F1E yerel Faz 1 kapanış
teknik gate'leri yeşildir, supervisor push kabulü bekler. Güncel uygulama yüzeyi, intentional
OpenAPI farkları, PostgreSQL/SQLite kanıtları
ve açık plan sapmaları
[API Implementation Status Report](docs/09-uygulama/11-api-implementation-status.md) içinde kayıtlıdır.

Queue `STOP — supervisor F1E push pending; awaiting Murat review` checkpoint'indedir. Yerel Phase 1
teknik gate'leri geçmiştir; Faz 2
authentication/session/RBAC/audit persistence başlatılmamıştır. F1D base commit'i `54a3678` review
branch'inde pushed durumdadır; F1E HEAD'inin review branch'ine push edilmesi supervisor
sorumluluğundadır ve remote sync doğrulanmadan F1E push gate'i tamam sayılmaz. Yürütme otoritesi
[MVP First Release Master Development Plan](.hermes/plans/2026-07-10_122125-mvp-first-release-master-development-plan.md)'dır;
[Implementation Readiness Checklist](docs/09-uygulama/08-implementation-readiness-checklist.md)
ise uygulama öncesi tarihsel planlama kapısı olarak korunur.
