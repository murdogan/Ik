# API Standartları, OpenAPI ve Webhook

Bu doküman, IK Platform HTTP API'lerinin URL, response, hata, pagination, idempotency, async job ve webhook standartlarını tanımlar.

Bu belge hedef standardı da içerir; F1A dahil güncel yüzey
[API Implementation Status Report](../09-uygulama/11-api-implementation-status.md) ile sınırlıdır.
Aşağıdaki payroll, PDKS ve AI referansları ileri-faz capability kataloğudur; bu alanlar MVP
dışıdır ve F1A runtime davranışı, endpoint'i veya background task'ı değildir.

## 1. Temel API ilkeleri

| İlke | Karar |
|---|---|
| REST first | `/api/v1` resource-oriented endpointler |
| OpenAPI | Tüm endpointler schema ve örnekle belgelenir |
| Tenant-aware | F1A trusted injected tenant principal; Faz 2'de token/session/host eşleşmesi |
| Permission-first | Protected endpoint default-deny principal/permission dependency ister |
| Idempotency | Desteklenen kritik POST endpointlerinde opsiyonel `X-Idempotency-Key` |
| Pagination | Büyük listelerde cursor-based pagination |
| Async jobs | Import, export, payroll, AI ve rapor işlemleri async |
| Correlation | Her response `correlation_id`/`trace_id` taşır |

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
    "correlation_id": "req_..."
  }
}
```

Liste response:

```json
{
  "data": [],
  "meta": {
    "next_cursor": null,
    "correlation_id": "req_..."
  }
}
```

Faz-0 compatibility notu: mevcut employee ve leave-request endpointleri breaking response
değişikliği yapmamak için plain JSON array döndürmeye devam eder. Bu iki yüksek büyüme listesinde
ilk/uyumluluk isteği `limit` ve deprecated `offset` kabul eder; response'ta daha fazla kayıt varsa
`X-Next-Cursor` header'ı döner. Sonraki istek `cursor=<header değeri>&limit=...` kullanır. Cursor ve
positive `offset` birlikte geçersizdir. Gelecekteki `{data, meta.next_cursor}` zarfına geçiş ayrıca
versionlanmış/duyurulmuş sözleşme değişikliği olacaktır.

F1A compatibility notu: yeni yedi tenant operation'ı da mevcut uygulama standardıyla doğrudan
typed object/list döner; `{data, meta}` zarfı eklemez. Bunlar:

- `POST/GET /api/v1/platform/tenants`
- `GET/PATCH /api/v1/platform/tenants/{tenant_id}`
- `GET /api/v1/tenant`
- `GET/PATCH /api/v1/tenant/settings`

Zarf, immutable genel request context ve global correlation middleware Faz 1.2'de intentional
contract migration olarak ele alınacaktır. F1A `/api/v1/tenant/features` eklemez.

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

Faz-0 deterministic sıraları:

- employee: `employee_number asc, id asc`;
- leave request: `created_at desc, start_date asc, id asc`.

Cursor endpoint türü ve bu tam ordering tuple'ını versioned opaque token içinde taşır; tenant
scope taşımaz. Tenant predicate her zaman authenticated/request context'ten ayrıca uygulanır.

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
- Permission bilgisi extension olarak eklenebilir.
- CI'da OpenAPI lint çalıştırılır.
- Breaking change PR'da görünür olmalıdır.
- Public API dokümanı internal endpointleri içermez.
- F1A additive schema ayrı `f1a_openapi_contract.json` snapshot'ında tutulur; historical Phase-0
  manifesti overwrite edilmez.

F1A platform/tenant güvenlik standardı:

- Platform operation'ları yalnız trusted adapter'ın enjekte ettiği `PlatformPrincipal`; tenant
  operation'ları yalnız enjekte edilen immutable `TenantPrincipal` ile çalışır. Default dependency
  context yokken `403` döner. Test override'ı Phase 2 auth gelene kadarki test seam'idir.
- `X-Tenant-Id`, `X-User-Id` veya caller'ın path/query/body/header içinde verdiği başka kimlik
  authorization değildir ve principal üretemez. Tenant current/settings scope'u injected
  principal'ın tenant ID'sinden türetilir.
- Platform tenant listesi bounded `limit`/`offset` kabul eder. Response yalnız
  `id`, `slug`, `name`, `status`, `plan_code`, `data_region`, `locale`, `timezone`, lifecycle-derived
  `health`, `created_at`, `updated_at` alanlarını taşır; HR count veya employee/leave payload yoktur.
- Create/PATCH plan inputu yalnız `core|professional|enterprise` kabul eder. Existing `premium`
  satırlar response'ta read-only compatibility için tanınır; migration rewrite veya yeni
  `premium` write yoktur.
- Tenant current response'u yalnız `id`, `slug`, `name`, `status`, `plan_code`, `locale`, `timezone`;
  settings response'u yalnız `locale`, `timezone`, `week_start_day`, `date_format`, `time_format`
  alanlarını taşır. Extra request key'leri validation'da reddedilir.
- `provisioning` tenant erişimi `423`, `closed` erişimi `410`; `suspended` ve `offboarding` GET
  açıktır ama settings PATCH `423` döner.

F1A generated OpenAPI/contract gate'i 21 operation'lık additive snapshot'ı, exact tag/metadata
assertion'larını ve runtime'da çağrılan 22 documented endpoint'i doğrular.

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
