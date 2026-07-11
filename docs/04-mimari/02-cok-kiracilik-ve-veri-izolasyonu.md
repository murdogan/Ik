# Çok Kiracılık ve Veri İzolasyonu

Bu doküman, IK Platform'un çok kiracılı SaaS modelini, tenant çözümleme yaklaşımını, veri izolasyonu katmanlarını ve enterprise dedicated opsiyonlarını tanımlar.

## 1. Karar özeti

Varsayılan model:

> Shared application + shared PostgreSQL schema + `tenant_id` + composite tenant foreign key +
> uygulama seviyesi tenant guard + F1C forced PostgreSQL RLS.

Enterprise için dedicated DB veya dedicated deployment opsiyonu açık bırakılır; ancak ilk ürün shared modelle ilerler.

## 2. Tenant izolasyon modelleri

| Model | Artı | Eksi | Karar |
|---|---|---|---|
| Shared DB + tenant_id | Düşük maliyet, hızlı onboarding | Disiplin ve test gerekir | Varsayılan |
| Schema per tenant | Orta izolasyon | Migration/operasyon karmaşık | Reddedildi |
| DB per tenant | Güçlü izolasyon | Maliyet ve operasyon yüksek | Enterprise opsiyon |
| Dedicated app + DB | En güçlü izolasyon | En pahalı | Private cloud/regüle müşteri |

## 3. Tenant veri modeli

Temel tenant alanları:

| Alan | Açıklama |
|---|---|
| `id` | UUID tenant kimliği |
| `slug` | Subdomain veya kısa kod |
| `name` | Kurum adı |
| `status` | provisioning, trial, active, suspended, offboarding, closed |
| `plan_code` | Canonical write: `core`, `professional`, `enterprise`; legacy `premium` read-only compatibility |
| `data_region` | `tr-1` veya `eu-1`; yalnız provisioning sırasında değişebilir |
| `db_target` | pool veya dedicated bağlantı referansı |
| `timezone` | Tenant saat dilimi |
| `locale` | Varsayılan dil/yerel ayar |

F1A'da `locale` yalnız `tr-TR|en-US`, `timezone` ise geçerli bir IANA timezone adıdır.
`tenant_settings` arbitrary JSON değildir: tenant başına tek satırda fixed
`week_start_day`, `date_format` ve `time_format` kolonlarını taşır. Feature flag tablosu veya
`/api/v1/tenant/features` endpoint'i F1A kapsamına dahil değildir.

F1D current ekleri:

- `tenants.active_employee_limit`, nullable configured platform limit metadata'sıdır. API'de
  `limits.active_employees` olarak görünür; employee tablosundan tüketim/adet ölçmez.
- `tenant_feature_flags`, `(tenant_id,key)` composite primary key ve tenant-root cascade FK taşır.
  Key allowlist'i sırayla `organization`, `employees`, `documents`, `leave`, `self_service`,
  `reporting`, `notifications`; yalnız `employees`, `leave`, `reporting` default açıktır.
- Effective response her flag için boolean `enabled` ve `default|override` source döndürür.
  `/api/v1/tenant/features` scope'u yalnız injected tenant principal'dan gelir; tenant ID alanı
  veya caller header'ı kabul etmez. Platform GET/PATCH feature path'indeki tenant UUID yalnız
  resource selector'dır ve platform authority sağlamaz.

## 4. Tenant çözümleme

Tenant şu kaynaklardan çözülür:

1. Kimlikli isteklerde JWT/session içindeki `tenant_id`.
2. Login öncesi ve public sayfalarda subdomain/custom domain.
3. Internal servis çağrılarında imzalı servis token + tenant context.

F1A geçiş kuralı: auth/session henüz Faz 2'de olduğu için platform route'ları yalnız injected
`PlatformPrincipal`, tenant route'ları yalnız injected ve immutable `TenantPrincipal` kabul eder.
Default dependency principal üretmez ve `403` ile fail closed olur; test dependency override'ı
bu production kuralını değiştirmez. `X-Tenant-Id`, başka bir header, path, query veya body değeri
bu principal'ların yerine geçemez.

F1B'de her HTTP isteği immutable `RequestContext` ile başlar. Context request/trace kimlikleri ile
optional tenant, actor/session, authentication-strength ve support-session placeholder'larını
taşıyabilir. Tenant-principal dependency yalnız trusted principal'dan immutable `TenantContext`
türetir; caller correlation veya tenant header'ı principal üretmez. Legacy employee/leave
`X-Tenant-Id` seçimi ayrı Faz-0 compatibility dependency'sidir ve yeni protected endpointler için
authorization kaynağı olarak kullanılamaz. F1B actor/session alanlarının varlığı auth veya RBAC'ın
uygulandığı anlamına gelmez.

Kurallar:

- Body içindeki `tenant_id` authorization için asla güvenilir kaynak değildir.
- JWT tenant ile host tenant uyuşmazsa istek reddedilir.
- Kullanıcı birden fazla tenant'ta varsa ayrı oturum bağlamı gerekir.
- Tenant context request boyunca immutable olmalıdır.

## 5. Veri izolasyonu katmanları

| Katman | Kontrol |
|---|---|
| Auth/context | Immutable `RequestContext` + F1A trusted injected principal; Faz 2'de JWT/session claim |
| Middleware | Safe request/trace context zorunlu; tenant scope protected dependency'den gelir |
| Repository | Her sorguda tenant filtresi |
| DB | Tenant-owned ilişkilerde composite foreign key + forced PostgreSQL RLS |
| Cache | `tenant:{tenant_id}` prefix |
| Object storage | Tenant prefix ve metadata |
| Search/vector | Tenant filter ve ACL hash |
| Logs | Allowlisted opaque request/trace ve optional tenant/support-session tag'i; actor/session/raw auth/PII yok |
| Tests | Cross-tenant negatif testler |

## 6. İlişkisel tenant bütünlüğü

Faz 0'da doğrudan DB write'ları dahil tenant sahipliği şu kuralla korunur:

- Tenant-owned bir tablo başka bir tenant-owned parent'a bağlanıyorsa parent üzerinde
  `(tenant_id, id)` candidate key bulunur.
- Child foreign key hem tenant'ı hem referansı taşır:
  `(tenant_id, foreign_id) → parent(tenant_id, id)`.
- `tenants` global ownership root'udur; `child.tenant_id → tenants.id` ilişkileri scalar kalır.
- Nullable referanslarda PostgreSQL varsayılanı `MATCH SIMPLE` korunur. Örneğin henüz
  kararlaştırılmamış izin talebinin `decided_by_user_id` değeri null olabilir.

Mevcut uygulama yüzeyinde candidate key'ler `employees` ve `users`; composite ilişkiler ise izin
talebinin employee/requester/decider referansları ile izin bakiye özetinin employee referansıdır.
Expand-contract migration önce orphan/cross-tenant preflight çalıştırır, yeni constraint'leri eski
constraint'lerle birlikte ekler ve validate eder; contract ancak doğrulamadan sonra eski scalar
referansları kaldırır. Uygulama tenant guard'ları korunur. Composite foreign key ile RLS birbirinin
alternatifi değildir.

## 7. PostgreSQL RLS yaklaşımı

F1C historical revision ile o checkpoint'teki altı tenant-owned tabloda (`users`, `employees`, `leave_requests`,
`leave_balance_summaries`, `command_idempotency`, `tenant_settings`) RLS hem enabled hem forced
durumdadır. Normal tenant rolünün platform metadata root'u üzerinden başka tenant keşfetmemesi için
`tenants.id` de aynı transaction tenant'ına scope edilir:

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_app ON employees
TO wealthy_falcon_app
USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
```

Uygulama transaction başında önce `SET LOCAL ROLE wealthy_falcon_app`, sonra
`SET LOCAL app.tenant_id = ...` uygular. Her iki değer de commit/rollback ile otomatik sıfırlanır;
pool'a dönen bağlantıda tenant veya capability state'i kalmaz. UoW bunu operation'dan önce zorlar,
read-only SQLAlchemy autobegin transaction'ları da aynı session hook'undan geçer. SQLite yolu hızlı
servis/API uyumluluğu için no-op'tur; güvenlik kanıtı değildir.

Kritik noktalar:

- `wealthy_falcon_app` ve `wealthy_falcon_platform` capability rolleri `NOLOGIN`, `NOINHERIT`,
  `NOSUPERUSER` ve `NOBYPASSRLS`'dir. Runtime login `NOINHERIT` olmalı ve yalnız açık transaction
  yolu ile ilgili role geçebilmelidir; migration/table owner login'i HTTP runtime'da kullanılmaz.
- Platform rolü `tenants` metadata işlemleri ve provisioning-only `tenant_settings` INSERT alır;
  settings SELECT/UPDATE ile `users`, `employees`, leave ve idempotency tablo grant/policy'si
  yoktur. Tenant app, `tenants` üzerinde yalnız locale/timezone ve ORM timestamp kolonlarını update
  edebilir; platform-controlled lifecycle/plan/region/name/slug alanlarını değiştiremez.
- F1D `tenant_feature_flags` tablosunu ayrıca RLS `ENABLE + FORCE` eder. Tenant app yalnız kendi
  satırlarını `SELECT`; platform role yalnız `SELECT/INSERT/UPDATE` eder. İki role de feature
  tablosunda `DELETE` verilmez. Platform role HR tablo grant/policy'si yine almaz.
- Eksik GUC `NULL`/empty üzerinden policy'yi false yapar; malformed UUID context sorguyu hatayla
  durdurur. Her iki durum da veri göstermeden fail closed olur.
- Lokal seed/migration gibi tenant'lar arası bootstrap işlemleri HTTP platform session'ını yeniden
  kullanmaz; ayrı ve açık operator/test-admin bağlantısıdır.
- Background job DB adapter'ı da tenant context'i transaction-locally set etmelidir.
- Mevcut worker fake/transport sınırı tenant-required serialized context allowlist'ini doğrular;
  extra metadata, tenant slug veya raw auth materyali taşımaz. Gerçek worker'ın DB transaction'ında
  aynı binder kullanılmadan HR sorgusu çalıştırmasına izin verilmez.
- PostgreSQL catalog testi non-null `tenant_id` taşıyan tabloları bağımsız keşfeder; migration'ın
  frozen inventory'si, forced flags ve app policy coverage farklıysa CI fail eder.

## 8. Cache, dosya ve arama izolasyonu

| Alan | Kural |
|---|---|
| Redis cache | Helper dışında key yazımı yasak; key tenant prefix içerir |
| Rate limit | Tenant + user + IP kombinasyonu |
| Object storage | `/{tenant_id}/{module}/{entity_id}/...` path standardı |
| Pre-signed URL | ACL ve tenant kontrolünden sonra üretilir |
| Search index | Metadata tenant filter zorunlu |
| Vector index | ACL hash ve tenant_id olmadan arama yapılmaz |

## 9. Tenant yaşam döngüsü

Same-state PATCH idempotent no-op'tur. İzin verilen farklı-state geçişleri:

- `provisioning → trial|active|closed`
- `trial → active|suspended|offboarding`
- `active → suspended|offboarding`
- `suspended → trial|active|offboarding`
- `offboarding → closed`
- `closed` terminaldir.

Listelenmeyen transition `409` ile reddedilir. Tenant access mode ve platform health yalnız
lifecycle'dan türetilir:

| Aşama | Tenant API davranışı | Platform health |
|---|---|---|
| `provisioning` | `/tenant` ve settings GET/PATCH `423`; yalnız platform provisioning yüzeyi | `provisioning` |
| `trial` | Read/write | `healthy` |
| `active` | Read/write | `healthy` |
| `suspended` | GET açık, settings PATCH `423` | `restricted` |
| `offboarding` | GET açık, settings PATCH `423`; export/retention orkestrasyonu F1A dışı | `offboarding` |
| `closed` | `/tenant` ve settings GET/PATCH `410` | `closed` |

Platform metadata list/detail yalnız tenant metadata, plan, region, configured
`limits.active_employees` ve bu lifecycle-derived health'i döndürür. Dar platform query service
yalnız `tenants` kolonlarını explicit project eder; employee/leave/user tablosuna join/count yapmaz
ve müşteri HR verisi içermez. Tenant silme, audit persistence, support/break-glass ve legal entity
bu kesitte yoktur. Feature rollout F1D'de yukarıdaki typed/RLS yüzeyle eklenmiştir.

## 10. Enterprise dedicated opsiyon

Enterprise müşteriler için:

- Dedicated DB.
- Dedicated object storage bucket/prefix.
- Dedicated worker queue.
- Dedicated namespace/deployment opsiyonu.
- Aynı kod tabanı ve aynı migration seti.

Kural: Müşteri bazlı fork yapılmaz; özelleştirme feature flag ve ayarlarla yapılır.

## 11. Noisy neighbor önlemleri

| Kaynak | Önlem |
|---|---|
| API | Tenant bazlı rate limit |
| Worker | Tenant başına concurrency limiti |
| DB | Statement timeout, ağır sorgu izleme |
| Export | Async job ve dosya boyutu limiti |
| AI | Tenant kota ve kullanım limiti |
| Webhook | Devre kesici ve retry sınırı |

## 12. Test gereksinimleri

- Tenant A kullanıcısı Tenant B employee kaydını göremez.
- Injected Tenant A principal'ı Tenant B'nin current/settings kaydını göremez veya değiştiremez;
  request header/body/path bu scope'u override edemez.
- Platform endpointleri principal injection yokken `403` döner ve tenant metadata response'unda
  employee/leave count veya payload alanı bulunmaz.
- Yalnız tenant principal enjekte edilmiş caller platform tenant/feature route'larında `403` alır;
  caller header/path/body platform principal üretemez.
- Tenant A feature GET'i Tenant B override'ını göstermez; bilinmeyen flag key API ve DB allowlist
  sınırında reddedilir.
- PostgreSQL'de app role feature satırlarında cross-tenant read/write yapamaz, platform role HR
  tablolarını okuyamaz ve hiçbir runtime capability feature satırı DELETE edemez.
- Tenant settings downgrade custom typed değerleri sessizce atmaz; default dışı satır sayısı ile
  fail eder ve revision/table'ı korur.
- Uygulama servisleri bypass edilse bile PostgreSQL doğrudan write ile Tenant A child kaydı Tenant B
  employee/user kaydına bağlanamaz.
- Preflight orphan ile cross-tenant satırları ayrı raporlar; valid veri upgrade/downgrade boyunca
  korunur.
- Tenant A document URL'i Tenant B'de çalışmaz.
- Cache key cross-tenant çakışmaz.
- Background job tenant context olmadan fail eder.
- Worker context tenant/job eşleşmesi, safe request/trace formatı ve fixed-key allowlist dışındaki
  metadata reddi test edilir.
- Export sadece tenant kapsamındaki satırları içerir.
- Search/vector sonuçları tenant dışına çıkmaz.

## 13. Riskler

| Risk | Önlem |
|---|---|
| Repository'de tenant filtresi unutulur | Zorunlu query guard + negatif test + Faz 1 RLS |
| Cache sızıntısı | Tenant-aware helper zorunlu |
| Object URL sızıntısı | Pre-signed URL ACL kontrolü |
| Superadmin kötüye kullanım | Break-glass, süreli erişim, tam audit |
| Dedicated müşteride migration sapması | Migration dashboard ve aynı kod tabanı |

## 14. İlgili dokümanlar

- [Teknik Mimari Genel Bakış](01-teknik-mimari-genel-bakis.md)
- [CORE, AUTH ve RBAC Modülleri](../03-moduller/01-core-auth-rbac.md)
- [AI Özellikleri ve Governance Modülü](../03-moduller/12-ai-ozellikleri-ve-governance.md)
