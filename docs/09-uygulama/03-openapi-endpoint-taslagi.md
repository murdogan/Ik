# OpenAPI Endpoint Taslağı

Bu doküman, MVP'nin ilk dikey kesitinde uygulanacak API endpointlerini, request/response sözleşmelerini, permission etkisini ve hata davranışını taslak seviyesinde tanımlar. Amaç, backend ve frontend geliştirmeye başlamadan önce contract-first ilerlemektir.

## 0. Güncel uygulama yüzeyi (2026-07-08 / N4)

Bu bölüm repodaki mevcut FastAPI uygulamasını özetler. Aşağıdaki endpointler testli ve
lokal backend smoke kapsamındadır.

| Method | Path | Durum | Not |
|---|---|---|---|
| GET | `/health` | Uygulandı | Public servis durumu |
| GET | `/` | Uygulandı | Wealthy Falcon HR landing HTML |
| GET | `/api/v1/dashboard/summary` | Uygulandı | Tenant-scoped DB sayımları, departman dağılımı ve son aktiviteler |
| GET | `/api/v1/employees` | Uygulandı | Tenant-scoped liste, şu an pagination/filter yok |
| POST | `/api/v1/employees` | Uygulandı | Server tenant context kullanır, duplicate employee number `409` |
| GET | `/api/v1/employees/{employee_id}` | Uygulandı | Tenant scope dışı kayıt `404` |
| PATCH | `/api/v1/employees/{employee_id}` | Uygulandı | Partial update, tarih aralığı validasyonu |
| DELETE | `/api/v1/employees/{employee_id}` | Uygulandı | Mevcut davranış hard delete |
| GET | `/api/v1/leave-requests` | Uygulandı | Tenant-scoped liste |
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
- Pagination, filtering, idempotency ve correlation envelope henüz TODO'dur.
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

- `cursor`
- `limit`
- `filter[status]`
- `q`
- `sort`

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
| GET | `/api/v1/leave-requests` | `leave:read:{scope}` | Liste |
| POST | `/api/v1/leave-requests/{id}/approve` | `leave:approve:team` | Onay |
| POST | `/api/v1/leave-requests/{id}/reject` | `leave:approve:team` | Red |

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
