# OpenAPI Endpoint Taslağı

Bu doküman, MVP'nin ilk dikey kesitinde uygulanacak API endpointlerini, request/response sözleşmelerini, permission etkisini ve hata davranışını taslak seviyesinde tanımlar. Amaç, backend ve frontend geliştirmeye başlamadan önce contract-first ilerlemektir.

## 0. Güncel uygulama yüzeyi

Son güncelleme: 2026-07-12 / F2F Phase 2 product hardening ve contract reconciliation.

Bu bölüm repodaki mevcut FastAPI uygulamasını özetler. Aşağıdaki endpointler testli ve
lokal backend smoke kapsamındadır. Smoke script bu tablonun endpoint setini
`docs/09-uygulama/11-api-implementation-status.md` içindeki completed surface tablosu ve kendi
runtime/OpenAPI registry'si ile karşılaştırır.

P0G'de generated Phase-0 sözleşmesi ayrıca
`backend/tests/contracts/phase0_openapi_contract.json` manifestinde top-level, operation ve
component-schema canonical hash'leriyle dondurulmuştur. Snapshot değişikliği intentional contract
diff ve bu dokümandaki migration/deprecation notu olmadan kabul edilmez. F1A'nın yedi additive
operation'ı historical `backend/tests/contracts/f1a_openapi_contract.json` snapshot'ında tutulur;
historical Phase-0 manifesti değiştirilmez. F1B contract testleri yedi success operation'ındaki
intentional envelope/header diff'ini ve Faz-0 compatibility kararını ayrıca görünür kılar.
F1D'nin additive feature/limit sözleşmesi historical
`backend/tests/contracts/f1d_openapi_contract.json` snapshot'ında korunur. F1E endpoint veya schema
eklemeden exact on Faz 1 operation'ına `x-required-principal` metadata'sı ekler ve sonucu ayrı
`backend/tests/contracts/f1e_openapi_contract.json` snapshot'ında dondurur.
F2F mevcut Phase 2 sözleşmesini yeni bir full snapshot ile çoğaltmaz: executable contract testi
F1E'nin 24 historical operation'ını aynen korur ve aşağıdaki 15 F2 operation'ının additive setini
canlı OpenAPI'den doğrular. P3C iki organization-selection operation'ı ekler; güncel registry 41
generated operation ve runtime `/openapi.json` ile 42 documented endpoint'tir.

| Method | Path | Durum | Not |
|---|---|---|---|
| GET | `/health` | Uygulandı | Public servis durumu |
| GET | `/` | Uygulandı | Wealthy Falcon HR landing HTML |
| GET | `/openapi.json` | Uygulandı | FastAPI generated schema; smoke bu şemayla documented operation drift kontrolü yapar |
| POST | `/api/v1/platform/tenants` | Uygulandı ve doğrulandı | `x-required-principal: platform`; injected platform principal ile provisioning; `{data,meta}`; status/id caller tarafından verilemez; optional configured limit |
| GET | `/api/v1/platform/tenants` | Uygulandı ve doğrulandı | `x-required-principal: platform`; deterministic opaque cursor + bounded `limit`; yalnız projected platform metadata/health/configured limit |
| GET | `/api/v1/platform/tenants/{tenant_id}` | Uygulandı ve doğrulandı | `x-required-principal: platform`; `{data,meta}` içinde yalnız tenant metadata/plan/region/lifecycle health/configured limit; HR veri/count yok |
| PATCH | `/api/v1/platform/tenants/{tenant_id}` | Uygulandı ve doğrulandı | `x-required-principal: platform`; `{data,meta}`; typed metadata/plan/status/limit update ve terminal lifecycle guard |
| GET | `/api/v1/platform/tenants/{tenant_id}/features` | Uygulandı ve doğrulandı | `x-required-principal: platform`; fixed effective flag catalog; HR veri/usage yok |
| PATCH | `/api/v1/platform/tenants/{tenant_id}/features` | Uygulandı ve doğrulandı | `x-required-principal: platform`; unique typed key + strict boolean rollout update |
| GET | `/api/v1/tenant` | Uygulandı ve doğrulandı | `x-required-principal: tenant`; `{data,meta}`; injected tenant principal scope'u, header/body authorization değil |
| GET | `/api/v1/tenant/settings` | Uygulandı ve doğrulandı | `x-required-principal: tenant`; `{data,meta}`; beş typed/allowlisted current-tenant setting |
| PATCH | `/api/v1/tenant/settings` | Uygulandı ve doğrulandı | `x-required-principal: tenant`; `{data,meta}`; extra key reddi ve lifecycle read-only guard |
| GET | `/api/v1/tenant/features` | Uygulandı ve doğrulandı | `x-required-principal: tenant`; selector kabul etmeden injected current tenant effective flag catalogu |
| POST | `/api/v1/platform/auth/login` | P3D uygulandı | Global email/parola doğrulamasından sonra aktif platform rolü; tenant/organizasyon seçimi yok; ayrı platform cookie/audience |
| POST | `/api/v1/platform/auth/refresh` | P3D uygulandı | Yalnız platform refresh cookie'sini döndürür; tenantless family rotation ve reuse koruması |
| POST | `/api/v1/platform/auth/logout` | P3D uygulandı | Yalnız platform family revoke/cookie temizleme; eşzamanlı tenant oturumuna dokunmaz |
| GET | `/api/v1/platform/me` | P3D uygulandı | `PlatformBearerAuth` + canlı tenantless session/rol/version doğrulaması; tenant alanı döndürmez |
| POST | `/api/v1/auth/login` | F2B uygulandı | Tenant-aware doğrulama, kısa ömürlü bearer ve HttpOnly cookie üzerinden hashli server session family |
| POST | `/api/v1/auth/select-organization` | P3C uygulandı | Hashli, süreli, tek kullanımlık seçim credential'ı ve opaque choice ile membership/tenant-bound session |
| POST | `/api/v1/auth/organization-selection` | P3C uygulandı | Aktif membership-bound session'dan server-derived alternatifler; kaynak family revoke; tenant selector kabul etmez |
| POST | `/api/v1/auth/refresh` | F2B uygulandı | Tek kullanımlık rotation; reuse bütün session family'yi revoke eder |
| POST | `/api/v1/auth/logout` | F2B uygulandı | Session family revoke ve refresh cookie temizleme |
| GET | `/api/v1/me` | F2D uygulandı | Bearer + aktif/versioned session doğrulamasıyla current user/tenant/role/permission bilgisi |
| POST | `/api/v1/auth/activate` | F2A uygulandı | Hashli/süreli aktivasyon credential'ı, atomik tek kullanım ve Argon2id parola kurulumu |
| POST | `/api/v1/users/invitations` | F2D uygulandı | Bearer actor/tenant scope, exact invite permission ve tenant spoof reddi |
| GET | `/api/v1/users` | F2D uygulandı | Permission-protected bounded tenant listesi ve role özetleri |
| GET | `/api/v1/users/{user_id}` | F2D uygulandı | Permission-protected role-aware detail; missing/cross-tenant aynı `404` |
| PATCH | `/api/v1/users/{user_id}` | F2D uygulandı | Exact update permission; yalnız `full_name`/`status` |
| GET | `/api/v1/roles` | F2D uygulandı | Seeded tenant rolleri ve explicit permission kodları; platform rolü yok |
| GET | `/api/v1/permissions` | F2D uygulandı | Seeded tenant permission katalogu; platform permission yok |
| PUT | `/api/v1/users/{user_id}/roles` | F2D uygulandı | Atomik replace, tenant isolation, platform-role reddi ve permission-version artışı |
| GET | `/api/v1/audit-events` | F2E uygulandı | Bearer + `audit:read:tenant`; role/category filtreli, redakte cursor sayfası |
| GET | `/api/v1/audit-events/{event_id}` | F2E uygulandı | Yalnız current tenant ve görünür kategoride salt-okunur güvenli detay |
| GET | `/api/v1/platform/audit-events` | P3D sınırıyla F2E uygulandı | Ayrı `PlatformBearerAuth` ve canlı platform session; yalnız `platform_operations`, HR payload yok |
| GET | `/api/v1/dashboard/summary` | Uygulandı | Tenant-scoped DB dashboard metrikleri, departman dağılımı ve son aktiviteler |
| GET | `/api/v1/employees` | Uygulandı | Tenant-scoped liste; filtreler, deterministic `cursor` + `X-Next-Cursor`, deprecated `offset` uyumluluğu |
| POST | `/api/v1/employees` | Uygulandı | Server tenant context, duplicate koruması ve opsiyonel tenant-global idempotency |
| GET | `/api/v1/employees/{employee_id}` | Uygulandı | Tenant scope dışı kayıt `404` |
| PATCH | `/api/v1/employees/{employee_id}` | Uygulandı | Partial update, tarih aralığı validasyonu |
| DELETE | `/api/v1/employees/{employee_id}` | Uygulandı | Aynı path/`204` ile idempotent archive; history korunur |
| GET | `/api/v1/employees/{employee_id}/leave-balances` | Uygulandı | Tenant-scoped, read-only manuel izin bakiyesi özeti; `period_year` filtresi var |
| GET | `/api/v1/leave-requests` | Uygulandı | Tenant-scoped liste; filtreler, mixed-order deterministic `cursor`, deprecated `offset` uyumluluğu |
| POST | `/api/v1/leave-requests` | Uygulandı | Pending talep; tenant guard ve opsiyonel tenant-global idempotency |
| POST | `/api/v1/leave-requests/{leave_request_id}/approve` | Uygulandı | Pending-only, row-lock one-winner ve opsiyonel idempotency |
| POST | `/api/v1/leave-requests/{leave_request_id}/reject` | Uygulandı | Decision note, row-lock one-winner ve opsiyonel idempotency |
| POST | `/api/v1/leave-requests/{leave_request_id}/cancel` | Uygulandı | Pending-only, row-lock one-winner ve opsiyonel idempotency |

F2A historical F1E yüzeyine activation/login/invitation ile üç; F2B refresh/logout/me ile üç;
F2C user list/detail/update ile üç; F2D role/permission catalog ve exact role replacement ile üç;
F2E tenant audit list/detail ve platform audit list ile üç generated operation daha ekler. Lokal
executable smoke tenant-admin user/role/audit akışını ve invite/activation sonrasında login → me →
refresh rotation → logout yaşam döngüsünü çalıştırır; tenant header spoof'un scope'u
değiştiremediğini ve revoke edilen session'ın yeniden kullanılamadığını doğrular. F2F focused
matrix ayrıca yedi tenant rolünün her user/role/audit endpoint kararını ve
tenant_admin/tenant_security/hr_operations kategori görünürlüğünü doğrular; employee genel
yönetim/audit center'da fail closed kalır. Credential/token değerleri çıktıya yazılmaz.

Geçerli uygulama notları:

- Historical F1A tam olarak yedi operation ekler: platform tenant `POST/GET`, platform tenant detail
  `GET/PATCH`, current tenant `GET` ve tenant settings `GET/PATCH`. `/api/v1/tenant/features`
  o checkpoint'te eklenmez. Historical registry 21 generated operation ve runtime
  `/openapi.json` dahil 22 endpoint'tir; additive F1A snapshot bu tarihi davranışı korur.
- Historical F1D üç additive operation ekler: platform tenant feature `GET/PATCH` ve current tenant
  feature `GET`. F1E operation sayısını değiştirmez: final registry 24 generated operation ve
  runtime `/openapi.json` dahil 25 endpoint'tir. Historical Phase-0/F1A/F1B/F1D snapshotları
  overwrite edilmez; F1E exact principal-metadata diff'i ayrı snapshot'ta, 25-endpoint runtime smoke
  sonucu ise implementation-status gate kaydında tutulur.
- Exact on Faz 1 operation'ının altı platform route'u `x-required-principal: platform`, dört current
  tenant route'u `x-required-principal: tenant` taşımaya devam eder. F2'nin on tenant
  auth/RBAC/audit operation'ı gerçek kısa ömürlü access credential için standard
  `BearerAuth` security scheme'ini taşır. Public activation/login/refresh/logout ile ayrı trusted
  principal kullanan platform audit route'u bearer authority varmış gibi belgelenmez.
- Historical Faz 1 platform route'ları injected immutable `PlatformPrincipal`, tenant route'ları
  injected immutable `TenantPrincipal` ister. Default dependencies principal üretmez ve `403`
  döner; testler bu trusted seam'i dependency override ile çalıştırır. Caller-supplied
  `X-Tenant-Id`, user/tenant ID header'ı, query, path veya body değeri authorization değildir.
- F1B, F1A'da eklenen yedi success operation'ını intentional contract migration ile
  `{data, meta}` zarfına geçirir. Tekil `meta`, `request_id`, `trace_id`, deprecated alias
  `correlation_id`; platform list meta'sı ayrıca `limit` ve `next_cursor` taşır. Existing Faz-0
  employee/leave success shape'leri bu değişiklikten etkilenmez.
- Create/PATCH plan allowlist'i `core|professional|enterprise`, region `tr-1|eu-1`, locale
  `tr-TR|en-US`; timezone geçerli IANA adıdır. Pre-F1A `premium` plan response'ta read-only
  compatibility'dir, write inputu değildir ve migration'da dönüştürülmez. Region yalnız
  `provisioning` sırasında değişebilir. Tenant settings
  request/response key'leri yalnız `locale`, `timezone`, `week_start_day`, `date_format`,
  `time_format` alanlarıdır; extra ve null PATCH alanları reddedilir.
- Lifecycle access/health: `provisioning → platform_only/provisioning`, `trial|active →
  read_write/healthy`, `suspended → read_only/restricted`, `offboarding →
  read_only/offboarding`, `closed → denied/closed`. Provisioning `/tenant` ve settings GET/PATCH
  `423`, closed aynı tenant operasyonlarında `410`; suspended/offboarding GET açıktır fakat
  settings PATCH `423` döner.
  Platform `health` yalnız bu status'tan türetilir; employee/leave join, count veya payload yoktur.
- F1D platform tenant response'u ayrıca nullable `limits.active_employees` configured metadata'sını
  taşır. Bu alan active employee usage/count değildir. Platform list/detail dedicated query service
  ile yalnız `tenants` kolonlarını project eder; HR model/tablosu import/join/count yoktur.
- Fixed flag sırası `organization`, `employees`, `documents`, `leave`, `self_service`, `reporting`,
  `notifications`; yalnız `employees`, `leave`, `reporting` default enabled'dır. Her effective item
  `key`, `enabled`, `source=default|override` taşır.
- Historical F1B auth/session/RBAC, audit persistence, PostgreSQL RLS, feature flag, legal entity, authorized
  support access veya başka ürün modülü eklemez. Request context'teki identity/auth-strength/
  support alanları yalnız typed placeholder'dır.
- F1D ve F1E authentication/session/RBAC veya audit persistence eklemez. Dört exact redacted event
  contract'ı command UoW içindeki replaceable recorder'a verilir; default recorder discard eder,
  audit table/read center Faz 2'ye kalır.

- Global correlation middleware tüm HTTP response'lara birer `X-Request-Id`, `X-Trace-Id` ve
  deprecated `X-Correlation-Id` alias'ı ekler. Request ID safe opaque ve en fazla 128 karakter;
  trace ID non-zero lowercase 32 hex'tir. Invalid, duplicate, conflicting, e-posta/PII veya JWT
  biçimli input yeniden üretilir; ham değer response/error/log yüzeyine yansıtılmaz.

- OpenAPI dokümanı okunabilir tag kataloğu kullanır: `System`, `Public`, `Authentication`,
  `Authorization`, `User Administration`, `Audit`, `Platform Audit`, `Platform Tenants`,
  `Tenant Settings`, `Dashboard`, `Employees`, `Leave Balances`, `Leave Requests`.
  İlk altı ürün/system tag'i W4C5'te sabitlenmiş; F1A `Platform Tenants` ve `Tenant Settings`
  gruplarını additive olarak eklemiştir. F1D feature operation'ları aynı sahiplik tag'lerini
  kullanır; yeni bir audit veya generic feature-admin tag'i açmaz.
  Mevcut operasyonların her biri açık, tenant-aware `summary` ve `description` metadata'sı taşır;
  tag açıklamaları, route açıklamaları ve filtre/header açıklamaları docs okunabilirliği için
  netleştirilmiştir. Operation summary metinleri tenant kapsamını, public/system ayrımını ve
  pending leave request karar akışını daha açık gösterir. Bu değişiklik yalnız dokümantasyon
  okunabilirliği içindir; request/response davranışı değişmemiştir. W4C6 itibarıyla smoke script
  generated OpenAPI operasyon seti, documented smoke registry, güncel endpoint tabloları ve
  runtime smoke senaryolarında gerçekten çağrılan endpoint setini path ve HTTP method seviyesinde
  doğrular.
  F1E historical metadata gate'i exact on Faz 1 operation'ının doğru `x-required-principal`
  değerini korur. F2F metadata ve smoke gate'leri yalnız gerçek bearer kullanan F2 tenant
  operation'larında `BearerAuth` bulunduğunu ve public/trusted-principal route'lara yayılmadığını
  doğrular.
- Historical W4C6 yalnız uygulama raporu ve smoke governance yenilemesiydi. O checkpoint'teki
  15 endpoint Phase-0 yüzeyini temsil eder; F1A current tabloya yedi additive operation ekler ve
  güncel snapshot/metadata/runtime smoke gate'leri bu additive sözleşmeyi doğrular.
- P0C endpoint setini veya success response shape'ini değiştirmez. Employee ve leave write
  operasyonları transitional application command handler üzerinden
  `SqlAlchemyUnitOfWork.execute` ile tek transaction'da çalışır; business servisleri flush eder
  fakat commit etmez. Read operasyonları request-scoped session ile doğrudan SQLAlchemy-aware
  service/query kodunu kullanır. Generic repository eklenmemiştir.
- W4B3 kapsamında bu taslak, mevcut FastAPI response shape'ine göre employee ve leave API'leri
  için concrete request/response örneklerini güncel tutar. Örnekler method/path, tenant header,
  query/body, success status/body, empty-list davranışı ve temsilî error zarflarını gösterir.
  Existing employee ve leave endpointleri explicit Faz-0 compatibility olarak doğrudan
  schema/list döner. Yeni Faz-1 operation'ları Bölüm 1'deki `{data, meta}` standardını kullanır.
- Domain endpointleri canonical hyphenated UUID formatında `X-Tenant-Id` header'ı ister.
  Compact, braces veya `urn:uuid:` UUID formları ve tekrarlı `X-Tenant-Id` header'ları
  geçersizdir. `X-Tenant-Slug` opsiyoneldir ve gönderilirse boş olamaz.
- Employee create, leave request create ve approve/reject/cancel endpointleri opsiyonel
  `X-Idempotency-Key` kabul eder. Key tenant genelinde tektir. Aynı semantic komut, hedef ve body
  ilk başarılı response snapshot'ını tekrar döner; farklı komut, hedef veya body aynı key ile
  gönderilirse ikinci write çalışmadan `409 idempotency_key_mismatch` döner. Receipt ve domain
  write aynı transaction'dadır; başarısız komut key'i rezerve bırakmaz. Henüz TTL/cleanup yoktur.
  Boş, whitespace içeren, 128 karakterden uzun veya tekrarlı key
  `400 idempotency_key_invalid` döner.
- F1A'nın yedi platform/tenant success operation'ı `{data, meta}` standardındadır. Existing Faz-0
  employee/leave/dashboard success shape'leri doğrudan schema/list kalır ve explicit adapter veya
  deprecation notu olmadan değiştirilemez.
- F1D'nin üç feature success operation'ı da aynı tekil `{data,meta}` standardını ve üç safe
  correlation response header'ını kullanır.
- F2 activation, tenant-aware login, server-side refresh rotation/reuse detection, logout,
  live-session `/me`, deny-by-default RBAC ve append-only audit read/write modelini uygular. F1A
  platform/tenant route'ları fail-closed injected principal seam'ini korur; tenant header yalnız
  legacy employee/leave backend foundation compatibility mekanizmasıdır ve F2 user/RBAC/audit
  operation'larını authorize etmez.
- Tenant header dependency hataları, API edge'de merkezi olarak map edilen typed
  `ApplicationError` hataları ve employee, leave balance, leave request endpointlerindeki otomatik
  request validation `422` hataları Bölüm 1'deki error zarfını döner. Diğer endpointlerdeki
  otomatik FastAPI validation yanıtları henüz framework varsayılanındadır.
- Yeni Faz-1 error zarfında `correlation_id`, middleware'in doğruladığı/ürettiği request ID'dir.
  Existing Faz-0 employee/leave error body adapter'ı yalnız geçerli legacy correlation inputu
  seçilen request ID ile aynıysa bu değeri taşır; diğer durumda eski `null` davranışını korur.
  Canonical request/trace her durumda response header'larındadır.
- W4A6 itibarıyla employee, leave balance ve leave request endpointlerinde public hata mesajları
  kod içi ortak sabitlerden üretilir ve regresyon testleri tenant-header hatalarının payload/query
  validation hatalarından önce aynı zarfla döndüğünü, null employee status lifecycle mesajını,
  invalid leave request `employee_id` filtre mesajını ve approve/reject/cancel transition conflict
  mesajını sabitler. Global FastAPI validation davranışı bu kapsamda değiştirilmemiştir.
- Şu an kullanılan error code değerleri: `platform_access_denied`, `tenant_access_denied`,
  `platform_tenant_validation_error`, `tenant_settings_validation_error`, `tenant_not_found`,
  `tenant_slug_conflict`, `tenant_lifecycle_conflict`, `tenant_not_ready`, `tenant_read_only`,
  `tenant_closed`, `tenant_header_missing`, `tenant_header_invalid`, `tenant_slug_header_invalid`,
  `employee_not_found`, `employee_number_conflict`,
  `employee_invalid_date_range`, `employee_invalid_lifecycle`, `employee_validation_error`,
  `leave_balance_validation_error`, `leave_request_not_found`,
  `leave_request_invalid_date_range`, `leave_request_transition_conflict`,
  `leave_request_validation_error`, `user_not_found`, `idempotency_key_invalid`,
  `idempotency_key_mismatch`, `data_integrity_conflict` ve `concurrent_write_conflict`.
- `uq_employees_tenant_employee_number` unique constraint ihlali, pre-check yarışında da mevcut
  `409 employee_number_conflict` code/message sözleşmesini korur. Başka bir tanımlı olmayan
  integrity hatası SQL veya constraint detayı sızdırmadan `409 data_integrity_conflict` ve
  `The request conflicts with persisted data` mesajını döner. SQLAlchemy `StaleDataError` veya
  tanınan bir DB concurrency hatası `409 concurrent_write_conflict` ve
  `The request conflicted with another write; retry the request` mesajını döner. Her iki yanıtta
  da mevcut error zarfı ve correlation davranışı korunur.
- P0C'nin transaction sınırı korunur. P0E `command_idempotency` receipt'ini domain write ile aynı
  Unit of Work içine alır; leave karar satırını tenant-scoped `SELECT ... FOR UPDATE` ile kilitler.
  Aynı pending talebe eşzamanlı çelişkili kararların yalnız biri başarılı olur; lock sonrası
  terminal state'i gören kaybeden mevcut `409 leave_request_transition_conflict` sözleşmesini alır.
  Gerçek PostgreSQL testleri one-winner davranışını ve concurrent aynı-key replay'i kanıtlar.
- P0E employee DELETE'i fiziksel silmeden archive'a çevirir. `archived_at` set edilen kayıt normal
  employee list/detail/update, yeni leave create, leave-balance okuma, dashboard workforce ve
  employee activity yüzeylerinden gizlenir. Aynı DELETE tekrar `204` döner; employee number
  rezerve, mevcut leave/balance geçmişi kalıcıdır. Employee child foreign key'leri
  `ON DELETE RESTRICT` kullanır.
- Employee/leave high-growth listelerinde additive cursor standardı ve explicit Faz-0 plain-array
  adapter'ı uygulanmıştır. Global correlation middleware ve yeni Faz-1 `{data,meta}` standardı
  F1B'de uygulanmıştır; global sort controls henüz yoktur. Idempotency'nin mevcut kapsamı yalnız
  yukarıda sayılan POST/decision komutlarıdır; receipt TTL/cleanup işi ayrıca backlog'dur.
- Dashboard summary tenant-scoped DB sorgularıyla `active_employee_count`,
  `pending_leave_count`, `employee_count`, `pending_leave_requests`,
  `new_starters_this_month`, `department_distribution` ve `recent_activity` döner.
  `active_employee_count` yalnız `active` çalışanları sayar; `employee_count` mevcut
  işgücü için `active` ve `on_leave` statülerini kapsar. `pending_leave_requests`,
  `pending_leave_count` ile uyumlu geriye dönük alandır. W4A5 kapsamında bu zenginleştirilmiş
  alanlar API seviyesinde DB-backed ve tenant-scoped testle sabitlenmiştir.
- Employee listesinde `department`, `status` ve employee number/email üzerinden `q` filtreleri
  uygulanır.
- Employee list/detail/update normal yüzeyi yalnız `archived_at is null` kayıtları görür.
  Arşivlenmiş employee'nin eski leave request kayıtları tenant-scoped leave history listesinde
  tutulmaya devam eder; yeni leave request veya normal balance erişimi açılamaz.
- Employee listesinde `limit` + `(employee_number asc, id asc)` cursor uygulanmıştır. Devam varsa
  `X-Next-Cursor` döner; plain-array body ve deprecated `offset` compatibility yolu korunur.
- Leave request listesinde W2A3 itibarıyla `status`, `employee_id` ve inclusive
  `start_date`/`end_date` tarih aralığı filtreleri testlerle sabitlenmiştir. Tarih aralığı, izin
  kaydının tarihleriyle overlap eden talepleri döndürür; tek taraflı tarih filtreleri de tenant
  scope içinde çalışır.
- Leave request listesinde `limit` + full `(created_at desc, start_date asc, id asc)` cursor
  sözleşmesi testlerle sabitlenmiştir. Deprecated `offset` compatibility yolu korunur. Pagination
  tenant scope ve filtrelerden sonra uygulanır.
- Leave balance summary endpointi `leave_balance_summaries` read modelini okur. Bu W1C2/W2C2
  placeholder'ı yalnız manuel/açılış özet değerlerini döner; hak ediş/accrual motoru, resmi tatil
  hesabı, payroll/bordro, SGK, banka, PDKS, AI veya dış entegrasyon içermez. Response içinde
  `calculation_mode: "manual_placeholder"` ve sabit `external_integration_enabled: false` döner.
  `remaining_days`, `opening_balance_days - used_days - planned_days` olarak türetilir. Tenant
  içindeki çalışanın hiç bakiye özeti yoksa `200 []`, tenant scope dışı çalışan için
  `employee_not_found` `404` döner. W4C2 regresyonu, mevcut leave request kayıtlarının bu
  placeholder yüzeyinde otomatik bakiye satırı üretmediğini sabitler.
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
beş kullanıcı, sekiz çalışan ve beş izin talebini idempotent şekilde seed eder. SQLite veya local
host dışındaki database URL hedeflerini bağlantı açmadan reddeder.

Bu dokümandaki güncel employee ve leave örnekleri demo seed içindeki Wealthy Falcon HR tenant'ını
kullanır:

```http
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Request-Id: req_wf_demo_001
X-Trace-Id: 0123456789abcdef0123456789abcdef
X-Correlation-Id: req_wf_demo_001
```

`X-Request-Id` canonical header'dır; `X-Correlation-Id` yalnız deprecated alias olarak aynı
değerle kabul edilir. Aşağıdaki historical Faz-0 örneklerinde yalnız alias gösterilmiş olsa da
middleware her HTTP response'ta canonical request/trace ile alias header'larını birer kez döndürür.

Örnek kapsamı:

- Employee örnekleri mevcut `EmployeeRead`, `EmployeeCreate` ve `EmployeeUpdate` alanlarıyla
  sınırlıdır; hassas kimlik, ücret, belge veya bordro alanı yoktur.
- Employee list ve leave request list response body bugün plain JSON array'dir. Devam metadata'sı
  body yerine `X-Next-Cursor` response header'ındadır; `offset` örnekleri compatibility yoludur.
- Leave request örnekleri mevcut `LeaveRequestRead`, `LeaveRequestCreate` ve
  `LeaveRequestDecision` alanlarını gösterir. Approval/reject/cancel işlemleri aynı decision body
  shape'ini kullanır.
- Leave balance örneği read-only manuel placeholder response shape'ini gösterir. Demo seed çalışan
  ve leave request kayıtları üretir; bakiye read modeli ayrıca manuel/test verisiyle doldurulur.
- Error örnekleri employee, leave balance ve leave request endpointlerinde kullanılan normalize
  `{ "error": { ... } }` zarfına aittir; diğer endpointlerdeki FastAPI validation yanıtları henüz
  bu kapsamda değildir.
- Create response örneklerindeki `id` değerleri server-generated temsili UUID'lerdir; request body
  içinde gönderilmez.
- Decision transition örneklerindeki `f400...0011` ve `f400...0012` gibi path id'leri bağımsız
  senaryolarda mevcut tenant içindeki pending kayıtları temsil eder; gerçek çağrıda tenant-scoped
  mevcut bir pending leave request id'si kullanılmalıdır.

Eksik `X-Tenant-Id`, boş `X-Tenant-Id`, canonical hyphenated UUID olmayan değerler, tekrarlı
`X-Tenant-Id` header'ları veya boş/tekrarlı gönderilen `X-Tenant-Slug` `400` döner. Örnek:

```json
{
  "error": {
    "code": "tenant_header_invalid",
    "message": "X-Tenant-Id header must be a single canonical hyphenated UUID",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

## 1. API ilkeleri

- Base path: `/api/v1`
- Yeni Faz-1 response zarfı: `{ data, meta }`; tekil meta
  `request_id|trace_id|correlation_id`, liste meta'sı ayrıca `limit|next_cursor` taşır.
- Error zarfı: `{ error: { code, message, details, correlation_id } }`
- F1A'nın yedi platform/tenant success operation'ı F1B'de bu zarfa intentional olarak geçirilmiştir.
  F1D'nin üç additive feature operation'ı ilk günden bu zarfı kullanır.
  Existing Faz-0 employee/leave/dashboard success response'ları explicit compatibility olarak
  doğrudan object/list kalır.
- Her HTTP response `X-Request-Id`, `X-Trace-Id` ve deprecated `X-Correlation-Id` taşır.
- Historical protected platform endpointlerde injected platform principal, current-tenant settings
  endpointlerinde injected tenant principal zorunludur; caller header/body kimliği authorization
  değildir. Exact on Faz 1 operation'ı bu sınırı OpenAPI'de
  `x-required-principal: platform|tenant` ile taşır.
- F2 `/me`, user, role, permission ve tenant-audit operation'ları gerçek kısa ömürlü access
  credential için OpenAPI `BearerAuth` taşır. Login/activation public credential exchange,
  refresh/logout ise HttpOnly cookie yaşam döngüsüdür; platform audit ayrı trusted principal
  sınırını korur.
- Büyük listelerde pagination zorunlu.
- Desteklenen kritik POST işlemlerinde opsiyonel `X-Idempotency-Key` kullanılır.

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

### `POST /api/v1/auth/activate`

Request:

```json
{
  "token": "fragmentten-alinan-tek-kullanimlik-deger",
  "password": "en-az-12-karakter"
}
```

Token veritabanında yalnız hashli ve süreli tutulur; başarılı kullanım aynı transaction'da
credential'ı consume eder ve Argon2id password hash'ini yazar. Browser token'ı URL query yerine
fragmentten okur ve API çağrısından önce adres çubuğu/history state'ten kaldırır. Invalid, expired
veya reused credential aynı `400 activation_invalid`; malformed payload
`422 auth_validation_error` zarfını döner.

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
    "token_type": "bearer",
    "expires_in": 900,
    "user": {
      "id": "uuid",
      "tenant_id": "uuid",
      "email": "ayse@example.com",
      "full_name": "Ayşe Yılmaz",
      "tenant": { "slug": "acme", "name": "Acme" },
      "workspace_scope": "tenant",
      "roles": [
        {
          "id": "uuid",
          "code": "employee",
          "name": "Employee",
          "scope_type": "tenant"
        }
      ],
      "permissions": ["dashboard:read:own", "employee:read:own"],
      "permission_version": 1
    }
  },
  "meta": {
    "request_id": "req_...",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_..."
  }
}
```

Refresh credential JSON'a girmez; `HttpOnly`, host-only, `SameSite=Lax`, `Path=/` cookie olarak
verilir ve staging/production'da `Secure` + `__Host-` policy zorunludur.

Hatalar:

- `401 invalid_credentials`: unknown tenant/email, wrong password and unavailable account/tenant
  aynı generic response'u kullanır.
- `422 auth_validation_error`: malformed/extra credential payload.

### `POST /api/v1/auth/refresh`

Request body yoktur; browser/BFF HttpOnly refresh cookie'yi gönderir.

Davranış:

- Refresh token rotation yapar.
- Eski token tekrar gelirse token family revoke edilir.
- Missing/expired/revoked/reused credential `401 session_invalid`; response cookie'yi de temizler.

### `POST /api/v1/auth/logout`

Davranış: cookie veya valid bearer ile seçilen aktif session family idempotent revoke edilir,
refresh cookie temizlenir ve body olmadan `204` döner. Credential yok/invalid ise de bilgi
sızdırmadan idempotent `204` + cookie clear uygulanır.

### `GET /api/v1/me`

Yetki: authenticated.

Response doğrulanmış kullanıcı/tenant bilgisini, active role özetlerini, effective permission
kodlarını, workspace scope ve permission version'ı döner. Bearer credential tek başına yeterli
değildir; canlı server session family, kullanıcı/tenant durumu ve permission version yeniden
doğrulanır.

## 5. Platform ve tenant endpointleri — F1E final Faz 1 yüzeyi

F1A–F1E historical platform operasyonları yalnız trusted boundary'den injected
`PlatformPrincipal`, tenant operasyonları yalnız injected `TenantPrincipal` ile çalışır. Default
dependency context yokken `403` döner; caller-supplied header/path/query/body kimliği authorization
değildir. Tenant principal platform operation'ını authorize edemez. F1B'deki yedi operation ve F1D
üç additive feature operation'ı `{data,meta}` döner. F1E bu on operation'ı
`x-required-principal: platform|tenant` ile belgeler. F2'nin bearer scheme'i bu historical trusted
principal operation'larına geriye dönük olarak uygulanmaz. Tekil response meta örneği:

```json
{
  "request_id": "req_wf_demo_001",
  "trace_id": "0123456789abcdef0123456789abcdef",
  "correlation_id": "req_wf_demo_001"
}
```

`correlation_id`, migration süresince `request_id` ile aynı deprecated body alias'ıdır.

### `POST /api/v1/platform/tenants`

Amaç: platform provisioning ile tenant ve typed default settings satırını atomik oluşturmak.

Request:

```json
{
  "slug": "acme-tr",
  "name": "Acme A.Ş.",
  "plan_code": "professional",
  "data_region": "tr-1",
  "locale": "tr-TR",
  "timezone": "Europe/Istanbul",
  "settings": {
    "week_start_day": "monday",
    "date_format": "DD.MM.YYYY",
    "time_format": "24h"
  },
  "limits": {
    "active_employees": 500
  }
}
```

`plan_code`, `data_region`, `locale`, `timezone` ve nested settings gönderilmezse sırasıyla
`core`, `tr-1`, `tr-TR`, `Europe/Istanbul`, `monday`, `DD.MM.YYYY`, `24h` kullanılır; limit
gönderilmezse `limits.active_employees=null` olur. `id` ve
`status` request alanı değildir; extra key'ler reddedilir ve server status'u `provisioning` yapar.
`premium` yalnız mevcut legacy row response uyumluluğudur; create/PATCH plan değeri olamaz.
Duplicate slug `409 tenant_slug_conflict`; typed request ihlali
`422 platform_tenant_validation_error` döner.

Response `201`:

```json
{
  "data": {
    "id": "d1000000-0000-4000-8000-000000000001",
    "slug": "acme-tr",
    "name": "Acme A.Ş.",
    "status": "provisioning",
    "plan_code": "professional",
    "data_region": "tr-1",
    "locale": "tr-TR",
    "timezone": "Europe/Istanbul",
    "health": "provisioning",
    "limits": { "active_employees": 500 },
    "created_at": "2026-07-11T12:00:00Z",
    "updated_at": "2026-07-11T12:00:00Z"
  },
  "meta": {
    "request_id": "req_wf_demo_001",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_wf_demo_001"
  }
}
```

### `GET /api/v1/platform/tenants`

Query: `limit` default `50`, minimum `1`, maximum `200`; optional `cursor` önceki response'un
`meta.next_cursor` alanındaki opaque değerdir. `offset` bu yeni Faz-1 listesinde kabul edilmez.
Deterministic sıra/keyset tuple'ı `(created_at asc, id asc)`'dir. Response `data` listesinde her item
yalnız `TenantPlatformRead` alanlarını taşır: `id`, `slug`, `name`, `status`, `plan_code`,
`data_region`, `locale`, `timezone`, `health`, nested `limits.active_employees`, `created_at`,
`updated_at`. `meta`, safe correlation
alanları yanında uygulanan `limit` ve nullable `next_cursor` taşır. Employee/leave count, kayıt,
belge, payload, usage veya başka HR alanı yoktur. Query yalnız allowlisted `tenants` kolonlarını
project eder.

```json
{
  "data": [],
  "meta": {
    "request_id": "req_wf_demo_001",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_wf_demo_001",
    "limit": 50,
    "next_cursor": null
  }
}
```

### `GET /api/v1/platform/tenants/{tenant_id}`

Response `200`, create örneğiyle aynı `{data,meta}` shape'idir; `data` bir
`TenantPlatformRead`'dir. `health` persisted bir operasyon metriği değil, lifecycle'dan
deterministik türetilir. `limits.active_employees` configured metadata olup employee count değildir.
Bulunmayan tenant `404`; platform principal yokluğu
`403 platform_access_denied` döner.

### `PATCH /api/v1/platform/tenants/{tenant_id}`

Partial request allowlist'i yalnız `name`, `status`, `plan_code`, `data_region`, `locale`,
`timezone` ve nested `limits.active_employees` alanlarıdır. Limit strict integer `1..1_000_000`
veya create'te absent/null olabilir; PATCH explicit null kabul etmez. `slug`, `id`, empty body,
explicit `null` ve extra alan reddedilir.

```json
{
  "status": "active",
  "plan_code": "enterprise",
  "timezone": "Europe/Istanbul",
  "limits": { "active_employees": 2500 }
}
```

Response `200`, `{data: TenantPlatformRead, meta: ResponseMeta}` döner. `data_region` yalnız mevcut status
`provisioning` iken değişebilir. Closed tenant metadata'sı immutable; offboarding tenant yalnız
`closed` durumuna geçebilir. Same-state update no-op kabul edilir. İzin verilen farklı-state graph:

- `provisioning → trial|active|closed`
- `trial → active|suspended|offboarding`
- `active → suspended|offboarding`
- `suspended → trial|active|offboarding`
- `offboarding → closed`
- `closed` terminal.

Listelenmeyen transition veya lifecycle'a aykırı metadata değişikliği
`409 tenant_lifecycle_conflict` döner.
`offboarding` veya `closed` transition'ı name/plan/region/locale/timezone/limit değişikliğiyle aynı
PATCH'te birleştirilemez; terminal transition ayrı command olmalıdır. Same-value/status no-op response
başarılı olabilir fakat actual-change event üretmez.

### `GET /api/v1/tenant`

Tenant ID request'ten değil injected `TenantPrincipal` scope'undan alınır. Response `200`:

```json
{
  "data": {
    "id": "d1000000-0000-4000-8000-000000000001",
    "slug": "acme-tr",
    "name": "Acme A.Ş.",
    "status": "active",
    "plan_code": "enterprise",
    "locale": "tr-TR",
    "timezone": "Europe/Istanbul"
  },
  "meta": {
    "request_id": "req_wf_demo_001",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_wf_demo_001"
  }
}
```

`provisioning` `423 tenant_not_ready`, `closed` `410 tenant_closed` döner. `trial`, `active`,
`suspended` ve `offboarding` read erişimine açıktır. Platform-only `data_region`, health ve
timestamp alanları tenant response'unda yoktur.

### `GET /api/v1/tenant/settings`

Response `200` data alanında yalnız beş typed key taşır:

```json
{
  "data": {
    "locale": "tr-TR",
    "timezone": "Europe/Istanbul",
    "week_start_day": "monday",
    "date_format": "DD.MM.YYYY",
    "time_format": "24h"
  },
  "meta": {
    "request_id": "req_wf_demo_001",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_wf_demo_001"
  }
}
```

Lifecycle read kuralları `GET /api/v1/tenant` ile aynıdır.

### `PATCH /api/v1/tenant/settings`

Partial request ve response allowlist'i tam olarak `locale`, `timezone`, `week_start_day`,
`date_format`, `time_format` alanlarıdır. Empty body, explicit `null`, arbitrary key ve logo/config/
feature payload'u reddedilir.

```json
{
  "locale": "en-US",
  "timezone": "Europe/London",
  "week_start_day": "sunday",
  "date_format": "MM/DD/YYYY",
  "time_format": "12h"
}
```

Response `200`, GET ile aynı `{data: TenantSettingsRead, meta: ResponseMeta}` zarfını kullanır.

Canonical değerler: locale `tr-TR|en-US`; timezone recognized IANA adı; week start
`monday|sunday`; date format `DD.MM.YYYY|MM/DD/YYYY|YYYY-MM-DD`; time format `24h|12h`.
`trial|active` write erişimine açıktır. `provisioning` `423 tenant_not_ready`, suspended/offboarding
`423 tenant_read_only`, `closed` `410 tenant_closed` döner. Scope injected principal'dan gelir;
başka tenant ID'si request içinde verilemez.
Request validation kodu `tenant_settings_validation_error`; principal yokluğu
`tenant_access_denied`'dır.

### `GET /api/v1/platform/tenants/{tenant_id}/features`

Injected `PlatformPrincipal` ile target tenant'ın fixed katalog sırasındaki effective rollout
metadata'sını okur. Path UUID yalnız resource selector'dır. Closed/offboarding dahil mevcut tenant
metadata'sı platform tarafından okunabilir; bulunmayan tenant `404 tenant_not_found`, principal
yokluğu veya yalnız tenant principal bulunması `403 platform_access_denied` döner.

Response `200`:

```json
{
  "data": {
    "features": [
      { "key": "organization", "enabled": false, "source": "default" },
      { "key": "employees", "enabled": true, "source": "default" },
      { "key": "documents", "enabled": false, "source": "default" },
      { "key": "leave", "enabled": true, "source": "default" },
      { "key": "self_service", "enabled": false, "source": "default" },
      { "key": "reporting", "enabled": true, "source": "default" },
      { "key": "notifications", "enabled": false, "source": "default" }
    ]
  },
  "meta": {
    "request_id": "req_wf_demo_001",
    "trace_id": "0123456789abcdef0123456789abcdef",
    "correlation_id": "req_wf_demo_001"
  }
}
```

`source=override`, effective boolean katalog defaultundan farklıysa döner; arbitrary source veya
customer-specific key saklanmaz. Query/response employee, user, leave, document veya HR usage
payload'u taşımaz.

### `PATCH /api/v1/platform/tenants/{tenant_id}/features`

Yalnız platform principal typed rollout override yazabilir:

```json
{
  "features": [
    { "key": "organization", "enabled": true },
    { "key": "notifications", "enabled": true }
  ]
}
```

Liste en az bir item taşır, key'ler request içinde unique ve katalogdan olmalıdır; `enabled` strict
boolean'dır. `payroll`, arbitrary/customer key, duplicate, null, `0|1`, `"true"|"false"`, nested
payload veya extra field `422 platform_tenant_validation_error` döndürür. Response GET ile aynı tam
yedi-item effective katalogdur; değiştirilen iki default-false key `source=override` olur.
Closed/offboarding tenant mutation'ı `409 tenant_lifecycle_conflict` ile reddedilir. Aynı effective
değeri tekrar yazmak no-op'tur ve `feature_flag.changed` üretmez.

### `GET /api/v1/tenant/features`

Path/query/body/header tenant selector kabul etmez. Tenant ID yalnız injected `TenantPrincipal` ile
enriched immutable request context'ten alınır; spoofed `X-Tenant-Id` scope'u değiştiremez. Response
platform GET ile aynı fixed `TenantFeaturesRead` contract'ıdır. Lifecycle davranışı:

- `provisioning`: `423 tenant_not_ready`
- `trial|active|suspended|offboarding`: `200` read
- `closed`: `410 tenant_closed`

Tenant surface flag mutation endpoint'i yoktur; rollout platform-controlled kalır.

### F1D platform event boundary

Successful actual create/status/setting/feature changes command UoW callback'i içinde sırasıyla
`tenant.created`, `tenant.status_changed`, `tenant.setting_changed`, `feature_flag.changed` exact
contract'ını async recorder'a verir. Sözleşmeler frozen/extra-forbid ve fixed tenant/platform-ops
metadata'sıyla sınırlıdır; generic payload/metadata/entity snapshot, password/hash/token/OTP/secret
ve employee/HR alanı kabul etmez. Faz 1 default recorder discard eder. Bu API yüzeyi audit table,
audit query endpoint'i veya kalıcı audit merkezi sunmaz; Phase 2 transactional adapter aynı portu
değiştirir.

## 6. User, RBAC ve audit endpointleri

| Method | Path | Permission | Not |
|---|---|---|---|
| POST | `/api/v1/users/invitations` | `user:invite:tenant` | Session-derived tenant/actor ile davet; activation URL yalnız response'ta bir kez görünür |
| GET | `/api/v1/users` | `user:read:tenant` | Bounded cursor, indexed search/status filter ve role özetli tenant listesi |
| GET | `/api/v1/users/{user_id}` | `user:read:tenant` | Missing/cross-tenant target aynı `404` |
| PATCH | `/api/v1/users/{user_id}` | `user:update:tenant` | Yalnız `full_name`/`status`; lock/disable canlı credential'ları revoke eder |
| GET | `/api/v1/roles` | `role:read:tenant` | Yalnız tenant-assignable seeded roller; platform rolü dışarıda |
| GET | `/api/v1/permissions` | `permission:read:tenant` | Yalnız tenant permission katalogu |
| PUT | `/api/v1/users/{user_id}/roles` | `role:assign:tenant` | Exact replace, permission-version artışı, platform/cross-tenant role reddi |
| GET | `/api/v1/audit-events` | `audit:read:tenant` | Role/category filtreli, redacted, bounded cursor listesi |
| GET | `/api/v1/audit-events/{event_id}` | `audit:read:tenant` | Visible current-tenant event için salt-okunur safe detail |
| GET | `/api/v1/platform/audit-events` | trusted platform principal | Yalnız `platform_operations`; tenant security/HR event'i seçilmez |

Actual invitation, user update ve role replacement aynı command transaction'ında redacted audit
event üretir. Tenant audit API'sinde update/delete operation'ı yoktur; PostgreSQL runtime
capability'si audit row update/delete alamaz ve cross-tenant/hidden IDs not-found olarak kapanır.

## 7. Employee endpointleri

### `GET /api/v1/employees`

Yetki: `employee:read:{scope}`.

Query:

- `department`: Departman adına göre case-insensitive exact match.
- `status`: `active`, `on_leave`, `terminated`.
- `q`: `employee_number` ve `email` üzerinde case-insensitive contains araması.
- `limit`: Dönen kayıt sayısı. Varsayılan `50`, maksimum `200`.
- `cursor`: Önceki response'un `X-Next-Cursor` header'ından opaque keyset değeri.
- `offset`: Deprecated compatibility yolu; cursor ile positive değer birlikte kullanılamaz.

Sıra `(employee_number asc, id asc)` ile deterministiktir. Global `sort` ayrı backlog'dur.

Request örneği:

```http
GET /api/v1/employees?department=Engineering&status=active&q=WF&limit=2&offset=0
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
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

Eşleşen kayıt yoksa response `200` ve boş array'dir:

```json
[]
```

### `POST /api/v1/employees`

Yetki: `employee:create:tenant`.

Request örneği:

```http
POST /api/v1/employees
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
X-Idempotency-Key: employee-create-wf-010
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

Bu header opsiyoneldir. Aynı tenant içinde `employee-create-wf-010` key'i ve aynı normalize
edilmiş body tekrar gönderilirse yeni employee oluşturulmaz; yukarıdaki ilk başarılı `201`
snapshot'ı aynı `id` ile replay edilir. Aynı key başka bir create body veya başka bir komut için
kullanılırsa `409 idempotency_key_mismatch` döner. Arşivlenen kayıt satırda kaldığı için employee
number da tenant içinde rezerve kalır ve yeni create `employee_number_conflict` alır.

Lifecycle kuralı: `terminated` status `employment_end_date` gerektirir; `active` ve `on_leave`
kayıtlarda `employment_end_date` `null` olmalıdır.

Otomatik request validation hataları employee endpointlerinde `employee_validation_error` `422`
zarfına normalize edilir. Tarih sırası ve lifecycle iş kuralları daha spesifik
`employee_invalid_date_range` veya `employee_invalid_lifecycle` kodlarını kullanır.
Eksik tenant header varsa employee endpointleri payload/path validation hatalarından önce
`tenant_header_missing` `400` zarfını döner.

Generic employee validation `422` örneği:

```json
{
  "error": {
    "code": "employee_validation_error",
    "message": "Employee request validation failed",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Bu zarf invalid `status`, `limit > 200`, `limit < 1`, `offset < 0`, geçersiz UUID path ve field
validation hataları için de kullanılır.

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
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
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

Request örneği:

```http
DELETE /api/v1/employees/f3000000-0000-4000-8000-000000000002
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
```

Response `204`: body dönmez.

Bu operasyon fiziksel delete değildir. Tenant içindeki kayıt bulunursa `archived_at` set edilir;
aynı path tekrar çağrıldığında timestamp değiştirilmeden no-op `204` döner. Arşivlenen, eksik veya
tenant scope dışındaki çalışan normal detail/update/leave-balance yüzeyinde aynı
`employee_not_found` `404` zarfını döner ve normal list/dashboard workforce yüzeyine girmez. Yeni
leave request açılamaz.

Employee satırı, employee number ve mevcut leave request/leave balance geçmişi korunur. Bu child
ilişkiler `ON DELETE RESTRICT` olduğundan geçmişi olan employee satırı doğrudan fiziksel silinemez.
Employee purge HTTP endpointi yoktur. Fiziksel tenant graph temizliği ancak açık retention/onay
politikasına bağlı, kısıtlı tenant-root offboarding operasyonudur; normal employee API kapsamı
değildir.

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

Not: Bu endpoint W1C2/W2C2/W3C2/W4C2 için bilinçli olarak read-only ve manuel placeholder'dır.
İzin hak edişi, resmi tatil/hafta sonu hesabı, payroll/bordro, SGK, banka, PDKS, AI veya dış
entegrasyon çalıştırmaz. Mevcut leave request kayıtlarından otomatik/sentetik bakiye satırı
üretilmez. Çalışan tenant içinde varsa ama bakiye özeti yoksa `200 []` döner.

Request örneği:

```http
GET /api/v1/employees/f3000000-0000-4000-8000-000000000002/leave-balances?period_year=2026
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
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

Çalışan tenant içindeyse ama manuel bakiye özeti yoksa response `200` ve boş array'dir:

```json
[]
```

Generic leave balance validation `422` örneği:

```json
{
  "error": {
    "code": "leave_balance_validation_error",
    "message": "Leave balance request validation failed",
    "details": null,
    "correlation_id": "req_wf_demo_001"
  }
}
```

Tenant scope dışındaki veya eksik çalışan için employee endpointleriyle aynı `employee_not_found`
`404` zarfı döner.

### `GET /api/v1/leave-requests`

Yetki: `leave:read:{scope}`.

Query:

- `status`: `pending`, `approved`, `rejected`, `cancelled`.
- `employee_id`: Çalışan UUID filtresi. Her zaman aktif tenant scope içinde uygulanır.
- `start_date`: Inclusive tarih aralığı başlangıcı.
- `end_date`: Inclusive tarih aralığı bitişi.
- `limit`: Dönen kayıt sayısı. Varsayılan `50`, maksimum `200`.
- `cursor`: Önceki response'un `X-Next-Cursor` header'ından opaque keyset değeri.
- `offset`: Deprecated compatibility yolu; cursor ile positive değer birlikte kullanılamaz.

Not: `start_date`/`end_date` filtresi, izin kaydı tarih aralığı sorgu aralığıyla overlap eden
talepleri döndürür. `end_date < start_date` istekleri `422` döner.
Sıra ve cursor tuple'ı `(created_at desc, start_date asc, id asc)` ile deterministiktir.

Request örneği:

```http
GET /api/v1/leave-requests?status=pending&employee_id=f3000000-0000-4000-8000-000000000002&start_date=2026-08-01&end_date=2026-08-31&limit=10&offset=0
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
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

Eşleşen talep yoksa response `200` ve boş array'dir:

```json
[]
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

```http
POST /api/v1/leave-requests
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
X-Idempotency-Key: leave-create-2026-09-14
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

Aynı tenant-global key ve aynı semantic leave create body tekrar gönderilirse ikinci talep
oluşturulmaz; ilk `201` snapshot'ı aynı leave request `id` ile replay edilir. Arşivlenmiş employee
tenant içinde normal create hedefi sayılmaz ve `employee_not_found` döner; geçmiş leave kayıtları
silinmez.

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
Otomatik request validation hataları leave request endpointlerinde
`leave_request_validation_error` `422` zarfına normalize edilir. Leave create tarih sırası ve
liste tarih aralığı iş kuralları `leave_request_invalid_date_range` kodunu kullanır.
Eksik tenant header varsa leave request endpointleri payload/query validation hatalarından önce
`tenant_header_missing` `400` zarfını döner.

Generic leave request validation `422` örneği:

```json
{
  "error": {
    "code": "leave_request_validation_error",
    "message": "Leave request validation failed",
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

### `POST /api/v1/leave-requests/{id}/approve`

Yetki: `leave:approve:team`.

Decision örnekleri bağımsız senaryolardır; path içindeki `id` değeri mevcut tenant içindeki
`pending` bir izin talebini temsil eder.

Request örneği:

```http
POST /api/v1/leave-requests/f4000000-0000-4000-8000-000000000001/approve
X-Tenant-Id: f1000000-0000-4000-8000-000000000001
X-Tenant-Slug: wealthy-falcon-demo
X-Correlation-Id: req_wf_demo_001
X-Idempotency-Key: leave-decision-f400-0001
Content-Type: application/json
```

```json
{
  "decided_by_user_id": "f2000000-0000-4000-8000-000000000003",
  "decision_note": "Approved with team coverage."
}
```

Karar komutu tenant-scoped leave request satırını transaction içinde `FOR UPDATE` ile kilitler.
Approve/reject/cancel aynı pending satır için eşzamanlı çalışırsa lock'u alan yalnız bir komut
terminal kararı yazar; diğer komut commit sonrasında terminal state'i görür ve
`409 leave_request_transition_conflict` alır. Aynı `X-Idempotency-Key` ile aynı kararın retry'ı ise
transition'ı tekrar çalıştırmaz, ilk başarılı `200` snapshot'ını replay eder.

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

Response `200` örneği:

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

### `POST /api/v1/leave-requests/{id}/cancel`

Yetki: `leave:create:own`.

Request örneği:

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

Response `200` örneği:

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

Aynı tenant-global idempotency key'in başka action, leave request hedefi veya decision body ile
yeniden kullanılması ikinci karar write'ını çalıştırmadan aşağıdaki `409` zarfını döner:

```json
{
  "error": {
    "code": "idempotency_key_mismatch",
    "message": "X-Idempotency-Key was already used for a different request in this tenant",
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

- Güncel 39 generated operation ve runtime `/openapi.json`, Bölüm 0 ile implementation-status
  tablosunda exact method/path olarak aynı olmalıdır.
- Exact on historical Faz 1 protected operation doğru `x-required-principal` metadata'sını;
  gerçek bearer kullanan exact on F2 tenant operation ise `BearerAuth` security metadata'sını
  taşır. Public ve trusted-principal operation'lara bearer scheme eklenmez.
- Invite → activate → login → refresh → logout, tenant-admin user/role/audit ve employee denial
  browser gate'leri geçmelidir.
- Employee response hassas alan masking kararına uyar.
- Import/export async operation standardına uyar.

## 11. İlgili dokümanlar

- [API Standartları, OpenAPI ve Webhook](../05-api-veri/02-api-standartlari-openapi-webhook.md)
- [Kimlik Doğrulama ve Yetkilendirme](../06-guvenlik-uyum/01-kimlik-dogrulama-yetkilendirme.md)
- [Sprint-0 / Sprint-1 Backlog ve Task Planı](02-sprint-0-1-backlog-ve-task-plani.md)
