# OpenAPI Endpoint Taslağı

Bu doküman, MVP'nin ilk dikey kesitinde uygulanacak API endpointlerini, request/response sözleşmelerini, permission etkisini ve hata davranışını taslak seviyesinde tanımlar. Amaç, backend ve frontend geliştirmeye başlamadan önce contract-first ilerlemektir.

## 0. Güncel uygulama yüzeyi (2026-07-09 / W1C6)

Bu bölüm repodaki mevcut FastAPI uygulamasını özetler. Aşağıdaki endpointler testli ve
lokal backend smoke kapsamındadır.

| Method | Path | Durum | Not |
|---|---|---|---|
| GET | `/health` | Uygulandı | Public servis durumu |
| GET | `/` | Uygulandı | Wealthy Falcon HR landing HTML |
| GET | `/api/v1/dashboard/summary` | Uygulandı | Tenant-scoped DB dashboard metrikleri, departman dağılımı ve son aktiviteler |
| GET | `/api/v1/employees` | Uygulandı | Tenant-scoped liste; `department`, `status`, `q` filtreleri ve `limit`/`offset` pagination var |
| POST | `/api/v1/employees` | Uygulandı | Server tenant context kullanır, duplicate employee number `409` |
| GET | `/api/v1/employees/{employee_id}` | Uygulandı | Tenant scope dışı kayıt `404` |
| PATCH | `/api/v1/employees/{employee_id}` | Uygulandı | Partial update, tarih aralığı validasyonu |
| DELETE | `/api/v1/employees/{employee_id}` | Uygulandı | Mevcut davranış hard delete |
| GET | `/api/v1/employees/{employee_id}/leave-balances` | Uygulandı | Tenant-scoped, read-only manuel izin bakiyesi özeti; `period_year` filtresi var |
| GET | `/api/v1/leave-requests` | Uygulandı | Tenant-scoped liste; `status`, `employee_id`, `start_date`, `end_date` filtreleri ve `limit`/`offset` pagination var |
| POST | `/api/v1/leave-requests` | Uygulandı | Pending talep oluşturur, çalışan ve isteyen kullanıcı tenant içinde olmalı |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | Uygulandı | Yalnız pending talep onaylanır |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | Uygulandı | Decision note destekler |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | Uygulandı | Yalnız pending talep iptal edilir |

Geçerli uygulama notları:

- OpenAPI dokümanı W1C5 itibarıyla okunabilir tag kataloğu kullanır:
  `System`, `Public`, `Dashboard`, `Employees`, `Leave Balances`, `Leave Requests`.
  Mevcut operasyonların her biri açık `summary` ve `description` metadata'sı taşır. Bu değişiklik
  yalnız dokümantasyon okunabilirliği içindir; request/response davranışı değişmemiştir. W1C6
  status refresh kapsamında smoke script bu operasyonları path ve HTTP method seviyesinde doğrular.
- Domain endpointleri geçerli UUID formatında `X-Tenant-Id` header'ı ister;
  `X-Tenant-Slug` opsiyoneldir ve gönderilirse boş olamaz.
- Response'lar şu an doğrudan schema/list döner. Bölüm 1'deki `{ data, meta }` zarfı hedef
  standarttır, mevcut scaffold davranışı değildir.
- Auth/session/RBAC dependency henüz uygulanmadı; tenant header geçici backend foundation
  mekanizmasıdır.
- Tenant header dependency hataları ve employee/leave endpointlerinde route seviyesinde yakalanan
  domain hataları Bölüm 1'deki error zarfını döner. FastAPI'nin diğer otomatik request
  validation `422` yanıtları henüz framework varsayılanındadır.
- Bu domain error zarfında `correlation_id`, `X-Correlation-Id` header'ı geldiyse aynı değer,
  gelmediyse `null` olur.
- Şu an kullanılan error code değerleri: `tenant_header_missing`, `tenant_header_invalid`,
  `tenant_slug_header_invalid`, `employee_not_found`, `employee_number_conflict`,
  `employee_invalid_date_range`, `employee_invalid_lifecycle`, `leave_request_not_found`,
  `leave_request_invalid_date_range`, `leave_request_transition_conflict`, `user_not_found`.
- Cursor pagination standardı, idempotency, tüm response zarfı ve global correlation middleware
  henüz TODO'dur.
- Dashboard summary tenant-scoped DB sorgularıyla `active_employee_count`,
  `pending_leave_count`, `employee_count`, `pending_leave_requests`,
  `new_starters_this_month`, `department_distribution` ve `recent_activity` döner.
  `active_employee_count` yalnız `active` çalışanları sayar; `employee_count` mevcut
  işgücü için `active` ve `on_leave` statülerini kapsar. `pending_leave_requests`,
  `pending_leave_count` ile uyumlu geriye dönük alandır.
- Employee listesinde `department`, `status` ve employee number/email üzerinden `q` filtreleri
- Employee listesinde `limit`/`offset` pagination (`limit` varsayılan `50`, maksimum `200`; `offset` varsayılan `0`)
  uygulanmıştır.
- Leave request listesinde `status`, `employee_id` ve inclusive `start_date`/`end_date` tarih
  aralığı filtreleri uygulanmıştır. Tarih aralığı, izin kaydının tarihleriyle overlap eden
  talepleri döndürür.
- Leave request listesinde `limit`/`offset` pagination (`limit` varsayılan `50`, maksimum `200`;
  `offset` varsayılan `0`) uygulanmıştır.
- Leave balance summary endpointi `leave_balance_summaries` read modelini okur. Bu W1C2
  placeholder'ı yalnız manuel/açılış özet değerlerini döner; hak ediş/accrual motoru, resmi tatil
  hesabı, payroll/bordro, SGK, banka, PDKS, AI veya dış entegrasyon içermez. Response içinde
  `calculation_mode: "manual_placeholder"` ve `external_integration_enabled: false` döner.
  `remaining_days`, `opening_balance_days - used_days - planned_days` olarak türetilir. Tenant
  içindeki çalışanın hiç bakiye özeti yoksa `200 []`, tenant scope dışı çalışan için
  `employee_not_found` `404` döner.
- Employee ve leave tarih alanları yalnız `YYYY-MM-DD` full-date değerlerini kabul eder;
  midnight datetime stringleri tarih olarak coerce edilmez. Employee create/update ve leave create
  date order kontrolleri servis katmanında da korunur; `employees` tablosunda date-order check
  constraint vardır.
- Leave request detail endpointi (`GET /api/v1/leave-requests/{id}`) henüz yoktur.

Lokal smoke komutu:

```bash
uv run python scripts/backend_api_smoke.py
```

Bu komut deploy, staging URL, cron, token, `.env` veya dış servis kullanmaz; in-memory SQLite
ile yukarıdaki API yüzeyini ASGI üzerinden doğrular.

Lokal demo seed komutu:

```bash
uv run python scripts/seed_demo_data.py
```

Bu komut API yüzeyi eklemez veya değiştirmez. Yalnız `local`/`dev` ortamında iki demo tenant,
beş kullanıcı, sekiz çalışan ve beş izin talebini idempotent şekilde seed eder.

Bu dokümandaki güncel employee ve leave örnekleri demo seed içindeki Wealthy Falcon HR tenant'ını
kullanır:

```http
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Eksik `X-Tenant-Id`, boş `X-Tenant-Id`, geçersiz UUID formatı veya boş gönderilen
`X-Tenant-Slug` `400` döner. Örnek:

```json
{
  "error": {
    "code": "tenant_header_invalid",
    "message": "X-Tenant-Id header must be a valid UUID",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

## 1. API ilkeleri

- Base path: `/api/v1`
- Response zarfı: `{ data, meta }`
- Error zarfı: `{ error: { code, message, details, correlation_id } }`
- Protected endpointlerde tenant context zorunlu.
- Büyük listelerde pagination zorunlu.
- Kritik POST işlemlerinde idempotency header desteklenmelidir.

## 2. MVP endpoint grupları

| Grup | Amaç | Faz |
|---|---|---|
| System | Health ve operasyonel kontrol | Sprint-0 |
| Auth | Login/session/me | Sprint-1 |
| Tenant | Tenant ayar ve onboarding | Sprint-1/S2 |
| Users/RBAC | Kullanıcı, rol ve permission | Sprint-1/S2 |
| Employees | Çalışan master data | Sprint-1/S2 |
| Documents | Özlük belgeleri | Sprint-3/S4 |
| Leave | İzin talep ve onay | Sprint-4/S5 |
| Reports | Hazır rapor ve export | Sprint-7/S8 |

## 3. System endpointleri

### `GET /health`

Amaç: servis ayakta mı kontrolü.

Response:

```json
{
  "status": "ok",
  "service": "IK Platform API",
  "version": "0.1.0",
  "environment": "local"
}
```

Yetki: public.

## 4. Auth endpointleri

### `POST /api/v1/auth/login`

Request:

```json
{
  "tenant_slug": "acme",
  "email": "ayse@example.com",
  "password": "********"
}
```

Response:

```json
{
  "data": {
    "access_token": "jwt",
    "refresh_token": "opaque",
    "expires_in": 900,
    "user": {
      "id": "uuid",
      "tenant_id": "uuid",
      "email": "ayse@example.com",
      "full_name": "Ayşe Yılmaz",
      "roles": ["hr_specialist"]
    }
  },
  "meta": { "correlation_id": "req_..." }
}
```

Hatalar:

- `AUTH_401_INVALID_CREDENTIALS`
- `AUTH_423_ACCOUNT_LOCKED`
- `CORE_403_TENANT_SUSPENDED`

### `POST /api/v1/auth/refresh`

Request:

```json
{ "refresh_token": "opaque" }
```

Davranış:

- Refresh token rotation yapar.
- Eski token tekrar gelirse token family revoke edilir.

### `POST /api/v1/auth/logout`

Yetki: authenticated.

Davranış: aktif session ve refresh token revoke edilir.

### `GET /api/v1/auth/me`

Yetki: authenticated.

Response kullanıcı, roller, permission özeti ve tenant bilgisini döner.

## 5. Tenant endpointleri

### `GET /api/v1/tenant/current`

Yetki: authenticated.

Response:

```json
{
  "data": {
    "id": "uuid",
    "slug": "acme",
    "name": "Acme A.Ş.",
    "status": "active",
    "plan_code": "core",
    "locale": "tr-TR",
    "timezone": "Europe/Istanbul"
  }
}
```

### `PATCH /api/v1/tenant/settings`

Yetki: `tenant:update`.

Kapsam: logo, timezone, locale, temel tenant ayarları.

## 6. User ve RBAC endpointleri

| Method | Path | Permission | Not |
|---|---|---|---|
| GET | `/api/v1/users` | `user:read:tenant` | Kullanıcı listesi |
| POST | `/api/v1/users/invite` | `user:invite:tenant` | Davet gönderir |
| PATCH | `/api/v1/users/{id}` | `user:update:tenant` | Status/name günceller |
| GET | `/api/v1/roles` | `role:read:tenant` | Rol listesi |
| POST | `/api/v1/roles/{id}/assign` | `role:assign:tenant` | Kullanıcıya rol atar |

Kritik davranış: role assignment audit event üretmelidir.

## 7. Employee endpointleri

### `GET /api/v1/employees`

Yetki: `employee:read:{scope}`.

Query:

- `department`: Departman adına göre case-insensitive exact match.
- `status`: `active`, `on_leave`, `terminated`.
- `q`: `employee_number` ve `email` üzerinde case-insensitive contains araması.
- `limit`: Dönen kayıt sayısı. Varsayılan `50`, maksimum `200`.
- `offset`: Sıralı sonuçta atlanacak kayıt sayısı. Varsayılan `0`.

Not: Cursor-based pagination ve `sort` ayrı backlog'dur; mevcut uygulama basit `limit`/`offset` kullanır.

Request örneği:

```http
GET /api/v1/employees?department=Engineering&status=active&q=WF&limit=2&offset=0
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
```

Response `200` örneği:

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

### `POST /api/v1/employees`

Yetki: `employee:create:tenant`.

Request örneği:

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

Response `201` örneği:

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

Lifecycle kuralı: `terminated` status `employment_end_date` gerektirir; `active` ve `on_leave`
kayıtlarda `employment_end_date` `null` olmalıdır.

Duplicate employee number `409` örneği:

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

### `GET /api/v1/employees/{id}`

Yetki: `employee:read:{scope}`.

Tenant scope dışındaki kayıtlar `404` döner. Mevcut `EmployeeRead` response örneği:

```http
GET /api/v1/employees/f3000000-0000-4000-8000-000000000002
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
```

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

Hedef davranış: hassas alanlar field permission'a göre maskelenir. Mevcut `EmployeeRead`
response hassas kimlik, ücret veya belge alanı taşımaz.

Not-found `404` örneği:

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

### `PATCH /api/v1/employees/{id}`

Yetki: `employee:update:tenant`.

Hedef davranış: critical update işlemleri before/after audit üretir.

Request örneği:

```json
{
  "position": "Senior Backend Engineer",
  "status": "on_leave"
}
```

Response `200` örneği:

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

Invalid date range `422` örneği:

```json
{
  "error": {
    "code": "employee_invalid_date_range",
    "message": "Employment end date must be on or after start date",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Invalid lifecycle `422` örneği:

```json
{
  "error": {
    "code": "employee_invalid_lifecycle",
    "message": "Terminated employees must have an employment end date",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

### `DELETE /api/v1/employees/{id}`

Yetki: `employee:update:tenant`.

Response `204`: body dönmez.

## 8. Leave endpointleri

| Method | Path | Permission | Not |
|---|---|---|---|
| GET | `/api/v1/leave-types` | `leave:read` | Tenant izin türleri |
| GET | `/api/v1/leave-balances/me` | `leave:read:own` | Çalışan bakiyesi |
| GET | `/api/v1/employees/{id}/leave-balances` | `leave:read:{scope}` | Yetkili çalışanın manuel bakiye özeti |
| POST | `/api/v1/leave-requests` | `leave:create:own` | İzin talebi |
| GET | `/api/v1/leave-requests` | `leave:read:{scope}` | Liste; status, employee, tarih aralığı filtreleri ve pagination |
| POST | `/api/v1/leave-requests/{id}/approve` | `leave:approve:team` | Onay |
| POST | `/api/v1/leave-requests/{id}/reject` | `leave:approve:team` | Red |
| POST | `/api/v1/leave-requests/{id}/cancel` | `leave:create:own` | İptal |

### `GET /api/v1/employees/{id}/leave-balances`

Yetki: `leave:read:{scope}`.

Query:

- `period_year`: Opsiyonel dönem yılı. `1900..2200` aralığıyla sınırlıdır.

Not: Bu endpoint W1C2 için bilinçli olarak read-only ve manuel placeholder'dır. İzin hak edişi,
resmi tatil/hafta sonu hesabı, payroll/bordro, SGK, banka, PDKS, AI veya dış entegrasyon çalıştırmaz.
Çalışan tenant içinde varsa ama bakiye özeti yoksa `200 []` döner.

Request örneği:

```http
GET /api/v1/employees/f3000000-0000-4000-8000-000000000002/leave-balances?period_year=2026
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
```

Response `200` örneği:

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

### `GET /api/v1/leave-requests`

Yetki: `leave:read:{scope}`.

Query:

- `status`: `pending`, `approved`, `rejected`, `cancelled`.
- `employee_id`: Çalışan UUID filtresi. Her zaman aktif tenant scope içinde uygulanır.
- `start_date`: Inclusive tarih aralığı başlangıcı.
- `end_date`: Inclusive tarih aralığı bitişi.
- `limit`: Dönen kayıt sayısı. Varsayılan `50`, maksimum `200`.
- `offset`: Sıralı sonuçta atlanacak kayıt sayısı. Varsayılan `0`.

Not: `start_date`/`end_date` filtresi, izin kaydı tarih aralığı sorgu aralığıyla overlap eden
talepleri döndürür. `end_date < start_date` istekleri `422` döner.

Request örneği:

```http
GET /api/v1/leave-requests?status=pending&employee_id=f3000000-0000-4000-8000-000000000002&start_date=2026-08-01&end_date=2026-08-31&limit=10&offset=0
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
```

Response `200` örneği:

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

Invalid filter range `422` örneği:

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

### `POST /api/v1/leave-requests`

Yetki: `leave:create:own`.

Request örneği:

```json
{
  "employee_id": "f3000000-0000-4000-8000-000000000003",
  "leave_type": "annual",
  "start_date": "2026-09-14",
  "end_date": "2026-09-18",
  "requested_by_user_id": "f2000000-0000-4000-8000-000000000002"
}
```

Response `201` örneği:

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

Cross-tenant `employee_id` veya `requested_by_user_id` referansları tenant scope içinde
bulunamadığı için sırasıyla `employee_not_found` veya `user_not_found` `404` yanıtı döner.

### `POST /api/v1/leave-requests/{id}/approve`

Yetki: `leave:approve:team`.

Request örneği:

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Approved with team coverage."
}
```

Response `200` örneği:

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

### `POST /api/v1/leave-requests/{id}/reject`

Yetki: `leave:approve:team`.

Request örneği:

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Customer launch coverage is required."
}
```

Response `200` örneği:

```json
{
  "id": "f4000000-0000-4000-8000-000000000001",
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

### `POST /api/v1/leave-requests/{id}/cancel`

Yetki: `leave:create:own`.

Request örneği:

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000002",
  "decision_note": "Employee cancelled the request."
}
```

Response `200` örneği:

```json
{
  "id": "f4000000-0000-4000-8000-000000000001",
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

Non-pending transition `409` örneği:

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

## 9. Import/export endpointleri

| Method | Path | Amaç |
|---|---|---|
| POST | `/api/v1/imports/employees/dry-run` | Çalışan import validasyonu |
| POST | `/api/v1/imports/{id}/commit` | Validated import commit |
| POST | `/api/v1/exports/employees` | Async çalışan export |
| GET | `/api/v1/operations/{id}` | Async operasyon durumu |

## 10. Kabul kriterleri

- İlk uygulama öncesi endpoint listesi bu dokümanla uyumlu olmalıdır.
- Her protected endpoint permission taşır.
- Auth ve employee endpointleri Sprint-1 önceliğindedir.
- Employee response hassas alan masking kararına uyar.
- Import/export async operation standardına uyar.

## 11. İlgili dokümanlar

- [API Standartları, OpenAPI ve Webhook](../05-api-veri/02-api-standartlari-openapi-webhook.md)
- [Kimlik Doğrulama ve Yetkilendirme](../06-guvenlik-uyum/01-kimlik-dogrulama-yetkilendirme.md)
- [Sprint-0 / Sprint-1 Backlog ve Task Planı](02-sprint-0-1-backlog-ve-task-plani.md)
