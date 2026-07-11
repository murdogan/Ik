# Teknik Mimari Genel Bakış

Bu doküman, IK Platform'un teknik mimari omurgasını tanımlar: uygulama katmanları, modüler monolit yaklaşımı, veri katmanı, async işler, entegrasyonlar, güvenlik ve ölçekleme ilkeleri.

## 1. Mimari karar özeti

IK Platform için başlangıç mimarisi:

> Next.js web yüzeyleri + FastAPI modüler monolit + PostgreSQL + Redis + S3 uyumlu dosya depolama + async worker mimarisi.

MVP'de mikroservis mimarisi tercih edilmez. Ürün alanı geniş olsa da ekip ve doğrulama aşaması için en doğru yaklaşım, güçlü modül sınırları olan modüler monolittir.

## 2. Mimari ilkeler

| İlke | Anlamı |
|---|---|
| Tenant-first | Her veri, log, cache, dosya ve event tenant bağlamı taşır |
| API-first | Web, mobil ve entegrasyonlar aynı API standardını kullanır |
| Privacy by design | Hassas alanlar varsayılan maskeli ve auditlidir |
| Modüler monolit | Tek deploy, net modül sınırları, gerektiğinde seçici ayrıştırma |
| Event-driven internal | Modüller kritik değişiklikleri domain event ile bildirir |
| Async by default | Import, export, rapor, bordro ve AI işleri background çalışır |
| Mevzuat = veri | Tatil, oran, tavan, parametre gibi değerler kod değil veri olmalıdır |
| Sıkıcı teknoloji | Kanıtlanmış teknoloji; risk ürün alanına ayrılır |

## 3. Ana bileşenler

| Bileşen | Teknoloji | Sorumluluk |
|---|---|---|
| Web uygulaması | Next.js + TypeScript | Admin panel, çalışan portalı, aday/kariyer sitesi |
| Mobil/PWA | Responsive web, ileride Flutter | Çalışan/yönetici hızlı akışları |
| API | FastAPI | Modüler monolit, iş kuralları, REST API |
| DB | PostgreSQL | Operasyonel veri, RLS, transaction |
| Cache/queue | Redis | Cache, rate limit, async broker |
| Worker | Dramatiq 2.2 + Redis hedef adapter | Import/export, rapor ve bildirim işleri; Faz 0'da yalnız provider-neutral port/fake |
| Object storage | S3/MinIO | Belge, bordro PDF, export dosyaları |
| Search | PostgreSQL FTS, V1 OpenSearch | Arama ve aday/doküman indeksleri |
| AI gateway | Ayrı iç servis veya modül | Maskeleme, prompt, model çağrısı, AI audit |

## 4. Modüler monolit sınırları

Tek deploy korunur; platform yetenekleri ile ürün modülleri aynı proses içinde fakat tek yönlü
import kurallarıyla ayrılır. Faz 0 hedef paketleri şöyledir:

```text
backend/app/
  platform/
    config/ db/ tenancy/ identity/ authorization/ idempotency/
    audit/ events/ errors/ observability/ storage/ workers/
  modules/
    core/ organization/ employees/ documents/ leave/
    self_service/ notifications/ reporting/
  api/            HTTP composition and incremental compatibility routes
  main.py
```

Bir ürün modülüne kod eklendiğinde yalnız ihtiyaç duyduğu katmanlar açılır:
`domain/`, `application/`, `infrastructure/` ve `presentation/`. Boş katmanlar veya her tabloyu
taklit eden generic repository'ler önceden üretilmez.

### 4.1 Sahiplik haritası

| Alan | Hedef paket | Sahiplik |
|---|---|---|
| Platform | `app.platform` | Config, DB runtime ve transaction/idempotency yetenekleri, tenancy mekanikleri, identity/session, authorization, audit, event, genel API error sözleşmesi, observability, object storage ve worker yetenekleri |
| Identity | `app.platform.identity` | Kullanıcı kimliği, principal ve session güvenliği; çalışan özlük kimliği değildir |
| Ürün çekirdeği | `app.modules.core` | Tenant yaşam döngüsü, ürün ayarları, plan ve feature flag; generic shared-code kovası değildir |
| Organizasyon | `app.modules.organization` | Departman, şube, pozisyon, atama ve raporlama hattı |
| Çalışanlar | `app.modules.employees` | Çalışan ana kaydı, profil ve çalışma yaşam döngüsü |
| Dokümanlar | `app.modules.documents` | Doküman metadata, checklist, hassasiyet ve retention; binary provider `platform.storage` alanındadır |
| İzin | `app.modules.leave` | İzin talebi, bakiye, tür, politika ve durum geçişleri |
| Self servis | `app.modules.self_service` | Kendi kapsamındaki çalışan/yönetici akışlarını orkestre eder; başka modül tablosu sahiplenmez |
| Bildirimler | `app.modules.notifications` | Kullanıcı bildirim tercihi, niyeti ve teslimat durumu; genel event/worker/provider platformdadır |
| Raporlama | `app.modules.reporting` | Tenant-safe dashboard, read model, rapor ve export sorguları |
| HTTP bileşimi | `app.api` | App factory, middleware/router bileşimi ve geçiş süresindeki uyumlu route girişleri |

### 4.2 Import yönü

| Kaynak katman | İzin verilen hedef | Yasaklanan yön |
|---|---|---|
| `domain` | Standard library ve aynı modülün `domain` katmanı | FastAPI, Pydantic, SQLAlchemy, settings/provider, platform, application, infrastructure, presentation ve başka modüller |
| `application` | Aynı modülün `domain/application` kodu ve gerektiğinde başka modülün açık application sözleşmesi | FastAPI, SQLAlchemy, global settings, concrete provider/platform adapter, infrastructure ve presentation |
| `infrastructure` | Aynı modülün domain/application portları, SQLAlchemy ve platform adapterları | Presentation ve başka modülün infrastructure/ORM modeli |
| `presentation` | Aynı modülün application sözleşmesi ve edge-facing platform sözleşmeleri | Infrastructure/ORM modeline doğrudan erişim |
| `platform` | Platform içi bağımlılıklar | Herhangi bir ürün modülü |

Ek kurallar:

- Modül başka modülün tablosuna doğrudan yazmaz.
- Modüller arası değişiklik yalnız açık application capability/port veya internal event ile yapılır;
  çift yönlü modül bağımlılığı kurulmaz.
- `app.platform` ve `app.modules` root paketleri import-free marker'dır; re-export ile katman
  kuralını dolanmak yerine açık capability/application paket yolu kullanılır.
- Raporlamanın ilerideki salt-okunur çapraz-modül sorgu istisnası tenant, scope ve field permission
  zorunluluklarını kaldırmaz ve ayrıca belgelenmeden import kuralı gevşetilmez.
- `backend/tests/test_import_boundaries.py`, hedef paketleri AST ile tarar; yasak yönleri, legacy'ye
  geri bağımlılığı, sibling infrastructure erişimini ve modül/Python import döngülerini reddeder.
  Negatif fixture'lar kontrolün hatalı örnekleri gerçekten yakaladığını da kanıtlar.
- Statik import testi raw SQL'in semantiğini göremez; başka modül tablosuna doğrudan yazmama kuralı
  kod incelemesi ve ilgili persistence testleriyle ayrıca korunur.

### 4.3 Artımlı ve geri alınabilir geçiş

`app.main`, `app.api`, `app.core`, `app.db`, `app.models`, `app.schemas` ve `app.services` mevcut
davranış için geçici legacy/composition migration alanıdır. Yeni hedef paket bu alana import
yapamaz; yön yalnız legacy -> hedef paket veya exact compatibility re-export olabilir.

P0B'de `TenantContext` için canonical yol `app.platform.tenancy`, genel `ApiError` sözleşmesi ve
handler için `app.platform.errors` olmuştur. `app.core.tenancy` ve `app.api.errors` eski importları
aynı class/function nesnelerini re-export eder. Employee/leave route, schema, service ve SQLAlchemy
modelleri yerinde kalır. Bu nedenle route/OpenAPI, tenant izolasyonu, migration ve veri sözleşmesi
değişmez; geçiş compatibility importları geri çevrilerek DB veya API migration olmadan alınabilir.

P0C'de bu artımlı geçiş, mevcut SQLAlchemy-aware employee ve leave servislerini taşımadan
uygulama komut sınırına genişletilir. Transitional `EmployeeCommandHandler` ve
`LeaveRequestCommandHandler`, tek transaction sahibi olarak `SqlAlchemyUnitOfWork.execute`
çağırır. İç servisler gerekli DB constraint ve server-default davranışını görmek için
`flush()` edebilir fakat `commit()` edemez. Bu değişiklik yeni tablo veya Alembic migration'ı
oluşturmaz; ileride audit ve outbox yazımlarını aynı transaction'a ekleyebilecek bir sınır
sağlar.

P0G bu kuralı tüm `app/services` paketi için AST gate'iyle sabitler. Lokal demo seed servisi de
flush-only'dir; yalnız standalone script `session_factory.begin()` transaction'ını tamamlar.

F1B, cross-cutting request sınırını `app.platform.request_context` ve
`app.platform.observability.correlation` altında kurar. `RequestContext` frozen/slotted'tır;
request/trace kimlikleri ile optional tenant, actor/session, authentication-strength ve
support-session placeholder'larını taşır. Trusted dependency enrichment alanları yerinde
değiştirmez, correlation kimliklerini koruyan yeni context üretip request state'e bağlar. Genel
success envelope'ları `app.platform.responses` sahipliğindedir; eski employee/leave plain-list
sözleşmesi yalnız `app.api.compatibility` içindeki açık Faz-0 adapter'ıyla korunur. Bu kesit schema
ve migration eklemez; auth/RBAC/audit persistence başlatmaz.

### 4.4 Komut transaction ve hata sınırı

Employee create/update/archive ile leave request create/approve/reject/cancel akışlarında
transaction sahipliği şöyledir:

```text
FastAPI route
  → transitional application command handler
  → SqlAlchemyUnitOfWork.execute
      → optional tenant-scoped idempotency receipt claim
      → tenant-scoped business service write + flush
      → optional response snapshot + receipt completion
      → future audit/outbox writes on the same session
  → exactly one commit, or one rollback on failure
```

`SqlAlchemyUnitOfWork.execute` bu komutların tek begin/commit/rollback sahibidir. Command handler
transaction'ı orkestre eder; `EmployeeService` ve `LeaveRequestService` bağımsız commit yapmaz.
Liste/detail/dashboard/leave-balance gibi read akışları doğrudan request-scoped session ve
SQLAlchemy-aware query service kullanmaya devam eder. UoW, SQLAlchemy metotlarını taklit eden
generic repository veya tüm modülleri kapsayan bir god object değildir.

Beklenen domain/application hataları transport-neutral `ApplicationError` tipleriyle API edge'e
ulaşır ve tek mapper mevcut HTTP status/code/message sözleşmelerini korur. Çalışan numarasının
`uq_employees_tenant_employee_number` constraint çakışması mevcut
`employee_number_conflict` yanıtıdır. Bunun dışındaki tanımlı olmayan integrity hataları
`409 data_integrity_conflict`; SQLAlchemy `StaleDataError` ve tanınan DB concurrency hataları
`409 concurrent_write_conflict` olarak, DB hata metni veya constraint detayı sızdırmadan döner.
Flush sonrası zorlanmış hata ve fresh-session doğrulamaları, employee/leave değişikliğinin
kısmi persist edilmediğini kanıtlar.

P0C transaction sınırını kurmuş, P0D tenant-owned composite foreign key'leri eklemiştir. P0E bu
temeller üzerinde durable idempotency receipt, leave decision row lock ve employee archive
semantiğini uygular; ayrıntılı karar ADR-015'tedir.

### 4.5 P0E concurrency, idempotency ve arşiv davranışı

Employee create, leave create ve leave approve/reject/cancel komutları opsiyonel
`X-Idempotency-Key` alır. Key namespace'i tenant genelidir; aynı tenant içindeki key başka bir
command adıyla yeniden kullanılamaz. İlk başarılı komutun canonical request fingerprint'i,
resource id'si ve response snapshot'ı `command_idempotency` tablosuna domain write ile aynı Unit of
Work transaction'ında yazılır. Aynı key ve aynı istek snapshot'tan replay edilir; aynı key ile
farklı command/body `409 idempotency_key_mismatch` döner. Receipt TTL veya cleanup job henüz yoktur.

Leave approve/reject/cancel sorgusu `tenant_id + leave_request_id` predicate'iyle blocking
PostgreSQL row lock alır. İlk terminal transition commit edene kadar ikinci transaction bekler;
ardından güncel status'u okuyup `leave_request_transition_conflict` döner. Böylece approve ve
reject aynı request için birlikte başarılı olamaz.

Compatibility `DELETE /api/v1/employees/{id}` route'u employee satırını silmez;
`employees.archived_at` alanını set eder. Arşivli kayıt normal employee list/detail/update,
leave-create ve leave-balance yüzeylerinde görünmez; dashboard workforce sorgularından çıkar.
Aynı tenant'ta tekrar DELETE state değişikliği yapmadan `204` döner. Arşivli satır mevcut
`(tenant_id, employee_number)` unique constraint'inde kaldığı için identifier rezerve kalır.
Leave request ve leave balance satırları korunur; bu child ilişkiler `ON DELETE RESTRICT` ile
doğrudan employee hard delete'i de engeller.

Public purge endpoint'i yoktur. Root tenant cascade yalnız kısıtlı operatör
retention/offboarding prosedüründe kullanılabilecek bir sahiplik mekanizmasıdır; normal employee
silme yetkisi veya tenant izolasyonu bypass'ı değildir.

## 5. Hedef istek yaşam döngüsü

Aşağıdaki listenin correlation/request-context bölümü F1B'de, tenant header compatibility guard'ı,
request-scoped DB session, application command/UoW ve typed error mapping ise önceki kesitlerde
uygulanmıştır. Authenticated actor/session, permission, transaction-local RLS context, field masking
ve audit persistence henüz uygulanmamıştır; tam akış Faz 1–2 boyunca tamamlanacaktır.

1. Request edge katmanından gelir.
2. Middleware safe request ID ve trace ID'yi doğrular veya üretir, immutable `RequestContext`'e
   bağlar ve canonical response header'larında taşır.
3. JWT/session doğrulanır.
4. Tenant context çözülür.
5. Rate limit uygulanır.
6. Permission/scope değerlendirilir.
7. Read query doğrudan çalışır veya write isteği application command handler'a gider.
8. Write komutu tek Unit of Work transaction'ı içinde ve tenant-scoped sorgularla çalışır;
   sağlanan idempotency key aynı transaction'da claim/complete edilir. PostgreSQL
   transaction-local tenant/RLS context'i Faz 1 rollout kapsamındadır.
9. Field masking uygulanır.
10. Audit/domain event gerekiyorsa yazılır.
11. Standart response döner.

## 6. Async işleme

Faz 0, `app.platform.workers` altında yalnız dar `JobQueue` portunu, tenant-aware `JobSpec`
envelope'unu ve deterministik `RecordingJobQueue` fake'ini uygular. ADR-008 ile Dramatiq 2.2 +
Redis hedef adapter seçilmiştir; provider dependency'si, broker bağlantısı, worker process'i,
schedule veya deployment bu checkpoint'te yoktur.

F1B ile `JobSpec`, optional serialized request context'i yalnız sabit JSON-safe allowlist olarak
alabilir: request/trace, zorunlu ve job ile aynı tenant ID, optional actor/session UUID'leri,
authentication strength ve optional support-session/operator UUID'leri. Extra/free-text alan,
tenant slug, PII, raw auth veya token kabul edilmez. Tenantless `RequestContext` worker payload'ına
serialize edilemez; legacy job `correlation_id` verilirse context `request_id` ile aynı olmalıdır.

| Kuyruk | İşler |
|---|---|
| `default` | Rapor, export, genel background işler |
| `notifications` | E-posta, push, SMS |
| `imports` | Çalışan import, PDKS import, belge eşleme |
| `payroll` | Puantaj/bordro export, V2 payroll run |
| `ai` | CV parse, RAG index, özetleme, öneriler |
| `integrations` | Webhook, PDKS, ERP, takvim, e-imza |

Bu tablo ileri fazlar için hedef capability kataloğudur; Faz 0 runtime queue veya task
envanteri değildir. Payroll, PDKS ve AI MVP dışıdır ve bu checkpoint'te bunlara ait task,
adapter, broker ya da entegrasyon uygulanmamıştır.

Async task kuralları:

- Task payload büyük veri taşımaz; ID taşır.
- `tenant_id` zorunludur.
- Task idempotent olmalıdır.
- Retry ve dead-letter mekanizması olmalıdır.
- Hata kullanıcıya izlenebilir status ile dönmelidir.

Provider adapter devreye alındığında `tenant_id` concurrency key'inin parçası olacak; retry,
timeout ve terminal dead-letter/failed-state davranışı Redis-backed integration testleriyle
kanıtlanacaktır. Queue receipt'i business idempotency/outbox kaydının yerine geçmez.

## 7. Veri katmanı

PostgreSQL ana veri katmanıdır.

User email mevcut şemada case-sensitive unique'tir. Auth phase'inden önce explicit
`lower(btrim(email))` normalize kolon/index migration'ı yapılacak; `citext` kullanılmayacaktır.
Employee directory araması bundan farklı bir sözleşmedir ve ADR-016'daki `ILIKE`/`pg_trgm`
stratejisini kullanır. F1B HTTP completion log'u allowlisted request/trace, optional tenant/support
session ID, authentication strength ve method/status taşır; actor/session, raw auth ve PII taşımaz.
PII-safe slow-query instrumentation ve DB transaction correlation ise henüz runtime'da yoktur.

Kullanım gerekçeleri:

- Transaction güvenilirliği.
- JSONB özel alanlar.
- RLS ile tenant izolasyonu.
- FTS/trigram ile MVP arama.
- pgvector olasılığı.
- Geniş ekosistem.

S3 uyumlu object storage belge ve export dosyaları için kullanılmalıdır. Dosya yolu tenant prefix içermelidir.

## 8. Entegrasyon mimarisi

Entegrasyonlar connector framework üzerinden yönetilmelidir.

Her connector için ortak alanlar:

- Credential/secret referansı.
- Mapping kuralları.
- Schedule.
- Import/export yönü.
- Run log.
- Hata listesi.
- Retry politikası.

İlk öncelikli entegrasyonlar:

- E-posta bildirimi.
- SMS/OTP opsiyonu.
- PDKS CSV/API import.
- Bordro export.
- Takvim entegrasyonu.
- V1/V2 e-imza ve SSO.

## 9. Güvenlik mimarisi etkileri

- Tenant context immutable olmalıdır.
- Her endpoint permission dependency ile korunmalıdır.
- Hassas alanlar field policy ile maskelenmelidir.
- Export ve belge download auditlenmelidir.
- Background job tenant context olmadan çalışmamalıdır.
- Object storage pre-signed URL tenant ve ACL kontrolünden sonra üretilmelidir.

## 10. Ölçekleme stratejisi

| Alan | Strateji |
|---|---|
| API | Stateless replika ve horizontal scaling |
| DB | Index, partition, read replica, büyük tenant için dedicated opsiyon |
| Worker | Kuyruk bazlı ayrı worker ve tenant eşzamanlılık limiti |
| Export/report | Async job ve dosya linki |
| AI | Gateway, kota, model yönlendirme, cache |
| Object storage | Tenant prefix, lifecycle policy |

## 11. Kabul kriterleri

- Mimari tenant izolasyonunu tüm katmanlarda destekler.
- MVP modülleri tek deploy içinde geliştirilebilir.
- Async işler tenant-aware çalışır.
- Belge/export dosyaları object storage'da tutulur.
- API ve worker tarafında audit/event altyapısı düşünülmüştür.
- V1/V2'de ayrışabilecek alanlar baştan izole edilmiştir: payroll, AI, reporting, integrations.

## 12. İlgili dokümanlar

- [Çok Kiracılık ve Veri İzolasyonu](02-cok-kiracilik-ve-veri-izolasyonu.md)
- [Teknoloji Kararları ADR](03-teknoloji-kararlari-adr.md)
- [Uygulama Yüzeyleri Web, Mobil ve API](04-uygulama-yuzeyleri-web-mobil-api.md)
- [CORE, AUTH ve RBAC Modülleri](../03-moduller/01-core-auth-rbac.md)
