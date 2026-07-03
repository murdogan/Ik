# API Standartları, OpenAPI ve Webhook

Bu doküman, IK Platform HTTP API'lerinin URL, response, hata, pagination, idempotency, async job ve webhook standartlarını tanımlar.

## 1. Temel API ilkeleri

| İlke | Karar |
|---|---|
| REST first | `/api/v1` resource-oriented endpointler |
| OpenAPI | Tüm endpointler schema ve örnekle belgelenir |
| Tenant-aware | Tenant token/session/host üzerinden çözülür |
| Permission-first | Protected endpoint permission dependency ister |
| Idempotency | Kritik POST endpointlerinde `Idempotency-Key` |
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
| 401 | `AUTH_401_UNAUTHENTICATED` | Login/token yok |
| 403 | `AUTH_403_PERMISSION_DENIED` | Yetki yok |
| 403 | `CORE_403_TENANT_MISMATCH` | Tenant uyuşmazlığı |
| 404 | `SYS_404_NOT_FOUND` | Kaynak yok veya scope dışı |
| 409 | `SYS_409_CONFLICT` | Çakışma |
| 409 | `SYS_409_IDEMPOTENCY_MISMATCH` | Aynı key farklı gövde |
| 422 | `VAL_422_VALIDATION` | Validasyon/iş kuralı |
| 423 | `{MOD}_423_LOCKED` | Kilitli dönem |
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

## 6. Idempotency

Kritik POST endpointlerinde `X-Idempotency-Key` kullanılır.

Kurallar:

- Aynı key + aynı body = aynı response döner.
- Aynı key + farklı body = `409 SYS_409_IDEMPOTENCY_MISMATCH`.
- TTL ilk etapta 24 saat olabilir.
- Bordro/onay gibi kritik işlemler ayrıca domain state machine ile korunur.

## 7. Async operation standardı

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
