# OpenAPI Endpoint Taslağı

Bu doküman, MVP'nin ilk dikey kesitinde uygulanacak API endpointlerini, request/response sözleşmelerini, permission etkisini ve hata davranışını taslak seviyesinde tanımlar. Amaç, backend ve frontend geliştirmeye başlamadan önce contract-first ilerlemektir.

## 0. Güncel uygulama yüzeyi (2026-07-09 / W1A6)

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
| GET | `/api/v1/leave-requests` | Uygulandı | Tenant-scoped liste; `status`, `employee_id`, `start_date`, `end_date` filtreleri ve `limit`/`offset` pagination var |
| POST | `/api/v1/leave-requests` | Uygulandı | Pending talep oluşturur, çalışan ve isteyen kullanıcı tenant içinde olmalı |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | Uygulandı | Yalnız pending talep onaylanır |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | Uygulandı | Decision note destekler |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | Uygulandı | Yalnız pending talep iptal edilir |

Geçerli uygulama notları:

- Domain endpointleri `X-Tenant-Id` header'ı ister; `X-Tenant-Slug` opsiyoneldir.
- Response'lar şu an doğrudan schema/list döner. Bölüm 1'deki `{ data, meta }` zarfı hedef
  standarttır, mevcut scaffold davranışı değildir.
- Auth/session/RBAC dependency henüz uygulanmadı; tenant header geçici backend foundation
  mekanizmasıdır.
- Employee ve leave endpointlerinde route seviyesinde yakalanan domain hataları Bölüm 1'deki
  error zarfını döner. FastAPI'nin otomatik request validation `422` yanıtları henüz framework
  varsayılanındadır.
- Bu domain error zarfında `correlation_id`, `X-Correlation-Id` header'ı geldiyse aynı değer,
  gelmediyse `null` olur.
- Şu an kullanılan domain error code değerleri: `employee_not_found`,
  `employee_number_conflict`, `employee_invalid_date_range`, `leave_request_not_found`,
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
- Leave request detail endpointi (`GET /api/v1/leave-requests/{id}`) henüz yoktur.

Lokal smoke komutu:

```bash
uv run python scripts/backend_api_smoke.py
```

Bu komut deploy, staging URL, cron, token, `.env` veya dış servis kullanmaz; in-memory SQLite
ile yukarıdaki API yüzeyini ASGI üzerinden doğrular.

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

Response item:

```json
{
  "id": "uuid",
  "employee_number": "EMP-001",
  "first_name": "Ayşe",
  "last_name": "Yılmaz",
  "status": "active",
  "department": { "id": "uuid", "name": "İK" },
  "position_title": "İK Uzmanı"
}
```

### `POST /api/v1/employees`

Yetki: `employee:create:tenant`.

Request minimal:

```json
{
  "employee_number": "EMP-001",
  "first_name": "Ayşe",
  "last_name": "Yılmaz",
  "email": "ayse@example.com",
  "employment_start_date": "2026-09-01",
  "department_id": "uuid",
  "position_id": "uuid"
}
```

### `GET /api/v1/employees/{id}`

Yetki: `employee:read:{scope}`.

Hassas alanlar field permission'a göre maskelenir.

### `PATCH /api/v1/employees/{id}`

Yetki: `employee:update:tenant`.

Critical: before/after audit üretir.

## 8. Leave endpointleri

| Method | Path | Permission | Not |
|---|---|---|---|
| GET | `/api/v1/leave-types` | `leave:read` | Tenant izin türleri |
| GET | `/api/v1/leave-balances/me` | `leave:read:own` | Çalışan bakiyesi |
| POST | `/api/v1/leave-requests` | `leave:create:own` | İzin talebi |
| GET | `/api/v1/leave-requests` | `leave:read:{scope}` | Liste; status, employee, tarih aralığı filtreleri ve pagination |
| POST | `/api/v1/leave-requests/{id}/approve` | `leave:approve:team` | Onay |
| POST | `/api/v1/leave-requests/{id}/reject` | `leave:approve:team` | Red |

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
