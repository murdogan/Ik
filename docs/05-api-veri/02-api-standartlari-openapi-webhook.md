# API Standartları, OpenAPI ve Webhook

Bu doküman, IK Platform HTTP API'lerinin URL, response, hata, pagination, idempotency, async job ve webhook standartlarını tanımlar.

Bu belge hedef standardı da içerir; F1E review checkpoint dahil güncel yüzey
[API Implementation Status Report](../09-uygulama/11-api-implementation-status.md) ile sınırlıdır.
Aşağıdaki payroll, PDKS ve AI referansları ileri-faz capability kataloğudur; bu alanlar MVP
dışıdır ve F1E runtime davranışı, endpoint'i veya background task'ı değildir.

## 1. Temel API ilkeleri

| İlke | Karar |
|---|---|
| REST first | `/api/v1` resource-oriented endpointler |
| OpenAPI | Tüm endpointler schema ve örnekle belgelenir |
| Tenant-aware | F1A trusted injected tenant principal; Faz 2'de token/session/host eşleşmesi |
| Permission-first | Protected endpoint default-deny principal/permission dependency ve truthful OpenAPI `x-required-principal` metadata'sı ister |
| Idempotency | Desteklenen kritik POST endpointlerinde opsiyonel `X-Idempotency-Key` |
| Pagination | Büyük listelerde cursor-based pagination |
| Async jobs | Import, export, payroll, AI ve rapor işlemleri async |
| Correlation | Her HTTP response güvenli `X-Request-Id`, `X-Trace-Id` ve deprecated `X-Correlation-Id` alias'ını taşır |

## 2. URL ve naming standardı

- Base path: `/api/v1`
- Kaynak adları çoğul ve kebab-case: `/leave-requests`
- JSON alanları snake_case.
- Eylem endpointleri alt aksiyon olarak: `POST /leave-requests/{id}/approve`
- Breaking change yeni major versiyon ister.

## 3. Standart response

Başarılı tekil response:

```json
{
  "data": {
    "id": "..."
  },
  "meta": {
    "request_id": "req_...",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_..."
  }
}
```

Liste response:

```json
{
  "data": [],
  "meta": {
    "request_id": "req_...",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_...",
    "limit": 50,
    "next_cursor": null
  }
}
```

Faz-0 compatibility notu: mevcut employee ve leave-request listeleri breaking response
değişikliği yapmamak için açık bir compatibility adapter üzerinden plain JSON array döndürmeye
devam eder. Bu iki yüksek büyüme listesinde
ilk/uyumluluk isteği `limit` ve deprecated `offset` kabul eder; response'ta daha fazla kayıt varsa
`X-Next-Cursor` header'ı döner. Sonraki istek `cursor=<header değeri>&limit=...` kullanır. Cursor ve
positive `offset` birlikte geçersizdir. Bu listeleri `{data, meta.next_cursor}` zarfına geçirmek
ayrıca versionlanmış/duyurulmuş sözleşme değişikliği olacaktır. Diğer mevcut Faz-0 success
object/list shape'leri de sessizce değiştirilmez.

F1B contract kararı: F1A'da eklenen aşağıdaki yedi tenant/platform success operation'ı yeni Faz-1
standardına açık ve testli bir contract migration ile `{data, meta}` zarfına geçirilmiştir:

- `POST/GET /api/v1/platform/tenants`
- `GET/PATCH /api/v1/platform/tenants/{tenant_id}`
- `GET /api/v1/tenant`
- `GET/PATCH /api/v1/tenant/settings`

Tekil operation'larda `meta` tam olarak `request_id`, `trace_id`, `correlation_id`; platform
listesinde bunlara ek olarak `limit` ve `next_cursor` taşır. `correlation_id`, geçiş süresince
`request_id` ile aynı değerdeki deprecated body alias'ıdır. F1A/F1B
`/api/v1/tenant/features` eklemez.

Historical F1D additive operation'ları:

- `GET/PATCH /api/v1/platform/tenants/{tenant_id}/features`
- `GET /api/v1/tenant/features`

Bu üç success operation da `DataEnvelope<TenantFeaturesRead>` kullanır ve response `data.features`
alanı fixed katalog sırasında tam yedi item taşır. Her item yalnız typed `key`, strict/effective
boolean `enabled` ve `source=default|override` alanlarından oluşur. Platform PATCH body örneği:

```json
{
  "features": [
    { "key": "organization", "enabled": true }
  ]
}
```

Liste non-empty, key'ler unique ve allowlisted, boolean değer strict olmalıdır. Unknown/duplicate/
null/numeric/string boolean veya arbitrary nested payload `422 platform_tenant_validation_error`
ile reddedilir. Tenant feature GET tenant selector kabul etmez; scope injected principal'dan gelir.
Provisioning tenant GET `423 tenant_not_ready`, closed tenant GET `410 tenant_closed`; suspended ve
offboarding read-only flag görünürlüğünü korur. Platform flag PATCH closed/offboarding tenant'ta
`409 tenant_lifecycle_conflict` döner.

Platform tenant create/list/detail/PATCH `TenantPlatformRead` response'u F1D'de nested
`limits.active_employees` alanını taşır. Değer nullable configured platform metadata'dır; HR usage
veya employee count değildir. Query service yalnız allowlisted `tenants` kolonlarını project eder.

F1E yeni endpoint, request/response modeli veya authentication mekanizması eklemez. Mevcut on Faz-1
platform/tenant operation'ı generated OpenAPI'de zorunlu `x-required-principal` vendor extension'ı
taşır: altı platform operation'ında değer `platform`, dört current-tenant operation'ında `tenant`tır.
Bu metadata dependency'nin beklediği trusted principal türünü makine-okunur biçimde belgeler;
request header'ı veya başka bir caller credential sözleşmesi değildir.

Hata response:

```json
{
  "error": {
    "code": "AUTH_403_PERMISSION_DENIED",
    "message": "Bu işlem için yetkiniz yok.",
    "details": [],
    "correlation_id": "req_..."
  }
}
```

Yeni Faz-1 hata yanıtlarında `error.correlation_id`, doğrulanmış/üretilmiş `request_id` alias'ıdır.
Faz-0 employee/leave hata body uyumluluğu explicit adapter ile korunur: yalnız geçerli ve seçilen
request ID ile aynı legacy correlation inputu body'ye yansır; diğer durumda eski `null` davranışı
korunur. Her iki durumda güvenli canonical request/trace değerleri response header'larındadır.

### 3.1 Request context ve correlation standardı

Her HTTP isteği middleware tarafından oluşturulan `frozen=True, slots=True` bir `RequestContext`
ile başlar. Context route/service kodu tarafından mutate edilemez; trusted dependency tenant,
actor/session, authentication strength veya support-session placeholder'ı ekleyecekse aynı
request/trace değerlerini koruyan yeni bir instance türetir. F1B yalnız bu typed taşıma sınırını
kurar; auth/session doğrulaması, RBAC kararı ve audit persistence Faz 2 işidir.

Giriş ve çıkış kuralları:

- `X-Request-Id` en fazla 128 karakterlik, log-safe opaque ASCII token'dır. Alfanümerik karakterle
  başlar/biter; içte yalnız alfanümerik, `.`, `_` ve `-` kabul edilir. JWT biçimli çok noktalı
  değerler kabul edilmez.
- `X-Trace-Id` tam 32 karakter lowercase hexadecimal ve sıfırdan farklıdır.
- `X-Correlation-Id`, `X-Request-Id` için deprecated giriş/çıkış alias'ıdır. İki header birlikte
  gönderilirse yalnız tekil, geçerli ve birbirine eşit olduklarında korunur.
- Eksik değer server tarafından üretilir. Invalid, duplicate, birbiriyle çelişen, PII biçimli
  (örneğin e-posta) veya JWT biçimli inputlar hata detayı yapılmadan yeniden üretilir; ham input
  response body/header'a yansıtılmaz ve completion log'una yazılmaz.
- Middleware upstream'in aynı adlı response header'larını kaldırıp tam bir canonical set ekler:
  `X-Request-Id`, `X-Trace-Id`, `X-Correlation-Id`. Alias değeri request ID'ye eşittir.

Public error metadata allowlist'i yalnız `request_id` ve `trace_id` kaynağıdır. Structured
completion log allowlist'i request/trace, authentication strength ve varsa opaque tenant/support
session ID'si ile HTTP method/status bilgisini taşıyabilir; actor ID, end-user session ID,
support-operator actor ID, tenant slug, PII, secret veya raw authorization/token/header materyali
log metadata'sına girmez.

## 4. Hata kodları

| HTTP | Code | Anlam |
|---|---|---|
| 400 | `SYS_400_MALFORMED_REQUEST` | Bozuk istek |
| 400 | `idempotency_key_invalid` | Opsiyonel key boş, whitespace içeriyor, çok uzun veya tekrarlı |
| 401 | `AUTH_401_UNAUTHENTICATED` | Login/token yok |
| 403 | `AUTH_403_PERMISSION_DENIED` | Yetki yok |
| 403 | `platform_access_denied` / `tenant_access_denied` | F1A trusted injected principal yok |
| 403 | `CORE_403_TENANT_MISMATCH` | Tenant uyuşmazlığı |
| 404 | `SYS_404_NOT_FOUND` | Kaynak yok veya scope dışı |
| 410 | `tenant_closed` | Closed tenant'ın tenant yüzeyi artık kullanılabilir değil |
| 409 | `SYS_409_CONFLICT` | Çakışma |
| 409 | `tenant_slug_conflict` / `tenant_lifecycle_conflict` | Duplicate slug veya izin verilmeyen tenant değişikliği |
| 409 | `idempotency_key_mismatch` | Aynı tenant key'i farklı komut, hedef veya semantic body ile kullanıldı |
| 422 | `VAL_422_VALIDATION` | Validasyon/iş kuralı |
| 423 | `{MOD}_423_LOCKED` | Kilitli dönem |
| 423 | `tenant_not_ready` / `tenant_read_only` | Provisioning current/settings yüzeyi veya suspended/offboarding settings PATCH kapalı |
| 429 | `SYS_429_RATE_LIMITED` | Limit aşıldı |
| 500 | `SYS_500_INTERNAL` | Beklenmeyen hata |

## 5. Listeleme standardı

| Konu | Standart |
|---|---|
| Pagination | `cursor` + `limit`, max limit 200 |
| Filtering | `filter[status]=active` |
| Sorting | `sort=-created_at,last_name` |
| Field selection | `fields=id,first_name,status` |
| Expand | `expand=position,manager` |
| Search | `q=` modül tanımlı arama |

Compatibility yüzeylerinin güncel deterministic sıraları:

- employee: `Employee.id ASC`;
- leave request: `created_at desc, start_date asc, id asc`.

Cursor endpoint türü ve bu tam ordering tuple'ını versioned opaque token içinde taşır; tenant
scope taşımaz. Tenant predicate her zaman authenticated/request context'ten ayrıca uygulanır.

F1B platform tenant listesi yeni liste standardını uygular:

- yalnız `limit` (`1..200`, default `50`) ve opaque `cursor` kabul eder; `offset` bu yeni
  endpointte kabul edilmez;
- sıra ve keyset tuple'ı `(created_at asc, id asc)` olarak deterministiktir;
- devam değeri body'deki `meta.next_cursor` alanındadır; `meta.limit` uygulanan page limitidir;
- invalid/repeated cursor veya limit ve legacy `offset` kullanımı
  `422 platform_tenant_validation_error` döner.

## 6. Idempotency

Mevcut Faz-0 yüzeyinde employee create, leave request create ve leave
approve/reject/cancel komutları opsiyonel `X-Idempotency-Key` kabul eder. Header gönderilmezse
geriye dönük uyumlu normal komut davranışı korunur.

Kurallar:

- Key tenant genelinde tektir; aynı key farklı tenant'larda birbirinden bağımsızdır.
- Key 1-128 whitespace içermeyen karakterdir. Boş, whitespace içeren veya tekrarlı header
  `400 idempotency_key_invalid` döner.
- Aynı key + aynı semantic komut/hedef/body, ilk başarılı response snapshot'ını ve aynı resource
  ID/status değerini tekrar döner. JSON alan sırası veya schema'nın normalize ettiği eşdeğer input
  yeni bir write üretmez.
- Aynı tenant key'inin farklı komut, hedef veya semantic body ile tekrar kullanılması
  `409 idempotency_key_mismatch` döner ve ikinci write çalışmaz.
- Idempotency receipt'i ve domain write aynı Unit of Work transaction'ındadır. Başarısız komut
  receipt'i de geri alır; düzeltilmiş altyapı/veri sonrası aynı semantic istek aynı key ile yeniden
  denenebilir.
- Henüz TTL veya cleanup işi yoktur. Receipt silinmediği sürece key aynı tenant içinde rezerve
  kalır; 24 saatlik expiry uygulanmış gibi varsayılmaz.
- İzin kararları idempotency'ye ek olarak tenant-scoped row lock ve pending-only state machine ile
  korunur; idempotency key state transition kuralının yerine geçmez.

### 6.1 Employee archive ve retention sınırı

Normal `DELETE /api/v1/employees/{employee_id}` fiziksel silme yapmaz; aynı path ve `204`
sözleşmesini koruyarak `archived_at` set eder. Tekrarlı DELETE no-op olarak yine `204` döner.
Arşivlenen çalışan normal liste/detail/update, yeni izin talebi, bakiye okuma ve dashboard işgücü
yüzeylerinden gizlenir; employee number tenant içinde rezerve kalır ve mevcut leave/balance geçmişi
korunur.

Employee purge için HTTP endpoint yoktur. Child employee ilişkileri geçmişi korumak için
`ON DELETE RESTRICT` kullanır. Fiziksel tenant graph temizliği yalnız açık retention/onay ve
offboarding kontrolleri olan kısıtlı tenant-root operasyonuna aittir; normal employee API'sinin
yetkisi değildir.

### 6.2 P4A employee directory uyumluluk sözleşmesi

`GET /api/v1/employees`, mevcut plain JSON array response'unu ve `X-Next-Cursor` header'ını
korur; `{data,meta}` zarfına geçirilmez. Default `limit=50`, max `200` ve deprecated bounded
`offset` uyumluluğu devam eder. P4A aşağıdaki additive query alanlarını kullanır:

- `q`: employee number, ad+soyad ve non-null iş e-postasında case-insensitive contains;
- `status`: mevcut employee lifecycle enum'u;
- `department`: legacy/current projection üzerinde exact case-insensitive uyumluluk filtresi;
- `legal_entity_id`, `branch_id`, `department_id`, `position_id`: aynı currently-effective Phase 3
  assignment satırında kesişen UUID filtreleri.

Employee directory opaque cursor payload'ı yalnız `id: UUID` taşır. Sıra `Employee.id ASC`, devam
predicate'i tam olarak `Employee.id > cursor.id`'dir. Strict cursor schema'sı ek alanları
yasakladığı için eski `employee_number` ve `created_at` cursor payload'ları reddedilir; cursor tenant
scope taşımaz ve güncellenebilir `employee_number` ordering/key alanı değildir. Bu sözleşmede
datetime normalizasyonu veya dialect'e özel `julianday` yolu yoktur.

List/detail item'ına optional-compatible `version` ve `current_assignment` eklenir. Legacy
`department`/`position` alanları kaldırılmaz; current structured değer varsa onu projekte eder,
yoksa raw legacy text'e düşer. Page employee query'sinden sonra bütün current assignment etiketleri
tek bounded batch query ile çözülür; per-row assignment sorgusu yapılmaz.

Employee number ve non-null `email` (UI: **İş e-postası**) Unicode uç whitespace trim + lowercase
normalizasyonuyla tenant içinde DB-enforced unique'tir; arşivli kayıt anahtarı reserve etmeye devam
eder. Birden çok `NULL` e-posta geçerlidir, blank e-posta geçersizdir. Advisory service precheck'i
ürün mesajını hızlandırır; named DB index'i yarışın authoritative sınırıdır. Çakışmalar sırasıyla
`409 employee_number_conflict` ve `409 employee_work_email_conflict` döner.

PATCH body'deki optional pozitif `version`, last-read token ile eşleşmezse
`409 concurrent_write_conflict` döner. Alanı göndermemek legacy partial-update contract'ını korur;
SQLAlchemy mapper version predicate'i iki eşzamanlı yazardan kaybedeni yine aynı conflict ailesine
çevirir. Employee create/update/archive audit'i yalnız allowlisted changed-field adlarını taşır;
değer snapshot'ı, e-posta veya hassas payload taşımaz.

## 7. Async operation standardı

Bu bölüm hedef sözleşmeyi tanımlar. Faz 0 yalnız provider-neutral worker portu/fake'i
içerir; `operations` endpoint'i, broker ve aşağıdaki işler henüz uygulanmamıştır.

Uzun işlemler `202 Accepted` döner:

```json
{
  "data": {
    "operation_id": "op_...",
    "status": "queued"
  }
}
```

Durum endpointi:

`GET /api/v1/operations/{id}`

Status değerleri:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Kullanım alanları:

- Çalışan import.
- PDKS import.
- Rapor export.
- Bordro export/run.
- AI batch işleri.

## 8. OpenAPI yönetişimi

- Her endpoint OpenAPI'de yer alır.
- Her endpoint tag, summary, request/response schema ve hata örneği içerir.
- Mevcut on Faz-1 platform/tenant operation'ı zorunlu `x-required-principal: platform|tenant`
  vendor extension'ı taşır; protected operation metadata'sız kabul edilmez.
- Faz 2 öncesinde doğrulanmış bir caller credential olmadığı için bu operation'larda standard
  OpenAPI `security` alanı ve top-level `components.securitySchemes` yayımlanmaz. Sahte bearer/OAuth
  şeması trusted dependency seam'ini authentication uygulanmış gibi gösteremez.
- CI'da OpenAPI lint çalıştırılır.
- Breaking change PR'da görünür olmalıdır.
- Public API dokümanı internal endpointleri içermez.
- Historical F1A additive schema ayrı `f1a_openapi_contract.json` snapshot'ında, Faz-0 schema ise
  kendi immutable manifestinde tutulur. F1B intentional envelope/header/pagination diff'ini contract
  testleriyle açıkça doğrular; historical Faz-0 manifesti overwrite edilmez. F1D üç additive
  feature operation'ı ve limit/feature component değişikliklerini ayrı historical snapshot/diff ile
  doğrular; historical F1A/F1B snapshotları da overwrite edilmez. F1E snapshot'ı operation setini
  büyütmeden yalnız aşağıdaki on operation'ın principal documentation digest'ini değiştirir;
  historical F1D snapshot'ını, schema components gruplarını ve OpenAPI top-level digest'ini korur.

Historical F1A platform/tenant güvenlik standardı:

- Platform operation'ları yalnız trusted adapter'ın enjekte ettiği `PlatformPrincipal`; tenant
  operation'ları yalnız enjekte edilen immutable `TenantPrincipal` ile çalışır. Default dependency
  context yokken `403` döner. Test override'ı Phase 2 auth gelene kadarki test seam'idir.
- `X-Tenant-Id`, `X-User-Id` veya caller'ın path/query/body/header içinde verdiği başka kimlik
  authorization değildir ve principal üretemez. Tenant current/settings scope'u injected
  principal'ın tenant ID'sinden türetilir.
- Platform tenant listesi bounded `limit`/opaque `cursor` kabul eder. Response `data` içinde yalnız
  `id`, `slug`, `name`, `status`, `plan_code`, `data_region`, `locale`, `timezone`, lifecycle-derived
  `health`, `created_at`, `updated_at` alanlarını; `meta` içinde safe correlation, limit ve
  continuation alanlarını taşır. HR count veya employee/leave payload yoktur.
- Create/PATCH plan inputu yalnız `core|professional|enterprise` kabul eder. Existing `premium`
  satırlar response'ta read-only compatibility için tanınır; migration rewrite veya yeni
  `premium` write yoktur.
- Tenant current response'u yalnız `id`, `slug`, `name`, `status`, `plan_code`, `locale`, `timezone`;
  settings response'u yalnız `locale`, `timezone`, `week_start_day`, `date_format`, `time_format`
  alanlarını taşır. Extra request key'leri validation'da reddedilir.
- `provisioning` tenant erişimi `423`, `closed` erişimi `410`; `suspended` ve `offboarding` GET
  açıktır ama settings PATCH `423` döner.

Historical F1D ek güvenlik/metadata standardı:

- Tenant principal hiçbir platform operation'ını authorize etmez. Platform feature path'indeki
  tenant UUID resource selector'dır; caller header/body/query authority değildir.
- Feature key katalogu sırayla `organization|employees|documents|leave|self_service|reporting|
  notifications`; default true yalnız `employees|leave|reporting`'dir. Customer-specific key veya
  fork yoktur.
- Platform response yalnız tenant identity/lifecycle/plan/region/locale/timezone/timestamps,
  lifecycle-derived health, configured `limits.active_employees` ve typed feature rollout metadata
  taşır. Employee/user/leave/document schema, record, count veya usage alanı referanslanamaz.
- Successful actual platform/tenant mutations exact redacted event contract'ını command UoW içinde
  async recorder portuna verir. Faz 1 default adapter discard eder; audit persistence ve audit read
  endpointleri Faz 2'ye aittir.

F1E principal metadata matrisi:

| `x-required-principal` | Operation'lar |
|---|---|
| `platform` | `POST/GET /api/v1/platform/tenants`; `GET/PATCH /api/v1/platform/tenants/{tenant_id}`; `GET/PATCH /api/v1/platform/tenants/{tenant_id}/features` |
| `tenant` | `GET /api/v1/tenant`; `GET/PATCH /api/v1/tenant/settings`; `GET /api/v1/tenant/features` |

- Metadata runtime enforcement'ın yerine geçmez. Default dependencies principal üretmez ve on
  operation'ın tamamı yetkisiz çağrıyı database/product operation'ından önce `403` ile reddeder;
  authorized test context doğru typed principal'ı dependency override ile enjekte eder. Tenant
  principal platform operation'ını, platform principal current-tenant operation'ını authorize
  edemez; spoofed header/path/query/body identity sonucu değiştirmez.
- Platform response contract'larında employee, leave veya document payload alanı sıfırdır. Typed
  feature anahtarlarındaki `employees|leave|documents` değerleri yalnız rollout katalog ismidir;
  customer record, schema, count, usage veya belge içeriği değildir. Platform-safe configured
  `limits.active_employees` de kullanım sayacı değil ticari limit metadata'sıdır.
- Error fixture'ları safe `correlation_id` alias'ını, completion-log fixture'ları safe request/trace
  kimliklerini ve dört frozen event fixture'ı doğrulanmış request/trace kimliklerini taşır. Ham
  authorization, token, secret, PII, employee/leave/document payload'u ve arbitrary
  metadata/before/after snapshot'ı bu yüzeylere giremez.
- F1E yalnız contract evidence ve Phase-1 review checkpoint'idir. Authentication/session, RBAC
  permission enforcement, audit persistence/read API ve Phase-2 product davranışı eklemez. Ruff,
  fast/PostgreSQL/Alembic/RLS/OpenAPI/smoke ve git-hygiene komutlarının ayrıntılı kanonik sonucu
  [API Implementation Status Report](../09-uygulama/11-api-implementation-status.md) içinde
  kaydedilir; burada kopyalanarak drift yaratılmaz.

Historical F1B generated OpenAPI 21 operation'lık yüzeyi korumuştur. Historical F1D üç additive
operation ile 24 generated operation'a ulaşmıştır. Current F1E operation setini değiştirmez:
24 generated operation ve runtime `/openapi.json` dahil 25 documented endpoint vardır. Contract
assertions F1B'nin yedi envelope/cursor kararını, F1D feature/limit componentlerini, F1E'nin exact
on-operation principal metadata diff'ini ve Faz-0 employee/leave plain-array + deprecated-offset
compatibility kararını birlikte görünür kılar.

## 9. Webhook mimarisi

Webhook payload minimal PII taşır. Detay gerekiyorsa alıcı API'den yetkisiyle çeker.

Header standardı:

```text
X-IK-Event: leave.approved
X-IK-Delivery-Id: evt_...
X-IK-Timestamp: 1783070000
X-IK-Signature: sha256=...
```

İmza:

- HMAC SHA-256.
- Timestamp + raw body üzerinden hesaplanır.
- Replay için 5 dakika tolerans.

## 10. Webhook event katalogu

| Event | Açıklama |
|---|---|
| `employee.created` | Çalışan oluşturuldu |
| `employee.updated` | Çalışan güncellendi |
| `employee.terminated` | Çalışan ayrıldı |
| `leave.requested` | İzin talebi açıldı |
| `leave.approved` | İzin onaylandı |
| `timesheet.locked` | Puantaj kilitlendi |
| `payslip.published` | Bordro pusulası yayınlandı |
| `candidate.applied` | Aday başvurdu |
| `candidate.hired` | Aday işe alındı |
| `request.approved` | Genel talep onaylandı |
| `core.operation.completed` | Async işlem tamamlandı |

## 11. Webhook retry

- 2xx başarıdır.
- Timeout 10 saniye olabilir.
- Retry: 1 dk, 5 dk, 30 dk, 2 saat, 6 saat, 24 saat.
- Sürekli hata subscription'ı pasifleştirebilir.
- Delivery log UI'da görülebilir.

## 12. API güvenlik kabul kriterleri

- Protected endpoint permission olmadan deploy edilemez.
- Object ID erişiminde tenant + scope kontrolü vardır.
- Büyük listeler pagination olmadan dönmez.
- Export endpointleri async ve auditlidir.
- Webhook secret plaintext gösterilmez.
- Error response stack trace sızdırmaz.

## 13. İlgili dokümanlar

- [Teknik Mimari Genel Bakış](../04-mimari/01-teknik-mimari-genel-bakis.md)
- [Veritabanı Modeli ve ERD](01-veritabani-modeli-ve-erd.md)
- [Entegrasyonlar](03-entegrasyonlar-sgk-banka-muhasebe-pdks.md)
