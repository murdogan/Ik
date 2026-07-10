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
│   ├── api/               # API router'ları
│   ├── core/              # Config, tenancy ve ortak altyapı
│   ├── db/                # SQLAlchemy session ve declarative base
│   ├── models/            # Tenant-scoped ORM modelleri
│   ├── schemas/           # Pydantic request/response şemaları
│   ├── services/          # Küçük domain servisleri
│   └── main.py            # FastAPI app factory
└── tests/                 # Pytest testleri
```

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

Gerçek PostgreSQL 16 entegrasyon, API ve migration hattını lokal Docker ile çalıştırmak için:

```bash
docker compose up -d --wait postgres
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres uv run pytest -q -m postgres
```

`IK_TEST_DATABASE_URL` PostgreSQL hattı için zorunludur. Test fixture'ı bu URL'yi yalnızca
yönetim bağlantısı olarak kullanır, her PostgreSQL testi için benzersiz ve geçici bir test
veritabanı oluşturur ve test sonunda siler; uygulama veya geliştirici veritabanında
upgrade/downgrade çalıştırmaz. Test başına izolasyon, retained archive/idempotency verisinin
migration testlerini collection sırasına bağımlı yapmasını engeller.
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
fake'ini içerir.

Phase 0 OpenAPI contract'ı
`backend/tests/contracts/phase0_openapi_contract.json` içinde operation/component bazlı canonical
hash manifestiyle sabitlenir. Contract testi, metadata testleri ve backend smoke registry birlikte
14 generated operasyonu ve runtime `/openapi.json` dahil 15 documented endpointi korur.

P0D ile mevcut tenant-owned parent tablolarından `employees` ve `users` için `(tenant_id, id)`
candidate key'leri; `leave_requests` ve `leave_balance_summaries` içindeki dört employee/user
referansı için `(tenant_id, foreign_id)` composite foreign key'leri eklenmiştir. `0009` expand
migration'ı sekiz mevcut ilişkiyi orphan/cross-tenant veri için tarar, PostgreSQL'de candidate
index'leri concurrent ve tekrar çalıştırılabilir biçimde kurar, yeni foreign key'leri `NOT VALID`
olarak eski scalar foreign key'lerle birlikte devreye alır ve concurrent-index penceresini kapatmak
için preflight'ı constraint lock'ları altında yeniden çalıştırır. `0010` contract migration'ı yeni
foreign key'leri validate ettikten sonra yalnız eski employee/user scalar foreign key'lerini
kaldırır. Böylece doğrudan DB write yolu tenant'lar arası employee/user bağlantısı kuramaz;
tenant root foreign key'leri ve mevcut servis guard'ları korunur. RLS bu değişikliğin parçası
değildir ve Faz 1'de ayrıca uygulanacaktır.

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

OpenAPI dokümanı `/docs` altında okunabilir tag gruplarıyla yayınlanır: `System`, `Public`,
`Dashboard`, `Employees`, `Leave Balances`, `Leave Requests`. W4C5 OpenAPI tag hygiene
kapsamında tag açıklamaları, tenant-aware operation summary/description metinleri ve
filtre/header açıklamaları güncel API docs okunabilirliği için netleştirildi; request/response
davranışı değişmedi. W4C6 implementation report refresh kapsamında tamamlanmış API yüzeyi ve
kalan backend backlog'u güncellendi; yeni endpoint veya API davranış değişikliği eklenmedi.

Tenant header dependency hataları, API edge'deki merkezi `ApplicationError` mapper'ının
dönüştürdüğü typed domain/application hataları ve employee, leave balance, leave request
endpointlerindeki otomatik request validation `422` hataları şu zarfla döner:
`{ "error": { "code": "...", "message": "...", "details": null, "correlation_id": null } }`.
Bu kapsam `tenant_header_missing`, `tenant_header_invalid`, `tenant_slug_header_invalid`,
not-found, conflict, date-range, employee lifecycle, `employee_validation_error`,
`leave_balance_validation_error`, `leave_request_validation_error` ve leave transition
hatalarıdır. Diğer endpointlerdeki otomatik FastAPI validation `422` yanıtları henüz framework
varsayılanındadır.
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

Bu W4B3 örnekleri mevcut FastAPI davranışını gösterir: employee ve leave endpointleri bugün
doğrudan schema/list döner; `{ data, meta }` zarfı henüz uygulanmış response shape değildir.
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

Plan dokümantasyon seti tamamlanmıştır. Mevcut repoda daha önce eklenmiş küçük bir Sprint-0 backend scaffold'u vardır; fakat bundan sonraki kod genişletmeleri kullanıcıdan açık “koda geç” onayı alınmadan yapılmamalıdır.

Plan tamamlık kapısı: [Implementation Readiness Checklist](docs/09-uygulama/08-implementation-readiness-checklist.md).
