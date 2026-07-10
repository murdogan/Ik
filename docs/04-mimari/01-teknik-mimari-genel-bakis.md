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
| Worker | Celery/RQ benzeri worker | Import/export, rapor, bildirim, AI, bordro işleri |
| Object storage | S3/MinIO | Belge, bordro PDF, export dosyaları |
| Search | PostgreSQL FTS, V1 OpenSearch | Arama ve aday/doküman indeksleri |
| AI gateway | Ayrı iç servis veya modül | Maskeleme, prompt, model çağrısı, AI audit |

## 4. Modüler monolit sınırları

Tek deploy korunur; platform yetenekleri ile ürün modülleri aynı proses içinde fakat tek yönlü
import kurallarıyla ayrılır. Faz 0 hedef paketleri şöyledir:

```text
backend/app/
  platform/
    config/ db/ tenancy/ identity/ authorization/
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
| Platform | `app.platform` | Config, DB runtime, tenancy mekanikleri, identity/session, authorization, audit, event, genel API error sözleşmesi, observability, object storage ve worker yetenekleri |
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

## 5. İstek yaşam döngüsü

1. Request edge katmanından gelir.
2. Request ID ve trace ID atanır.
3. JWT/session doğrulanır.
4. Tenant context çözülür.
5. Rate limit uygulanır.
6. Permission/scope değerlendirilir.
7. Service iş kuralını çalıştırır.
8. DB transaction içinde tenant context set edilir.
9. Field masking uygulanır.
10. Audit/domain event gerekiyorsa yazılır.
11. Standart response döner.

## 6. Async işleme

| Kuyruk | İşler |
|---|---|
| `default` | Rapor, export, genel background işler |
| `notifications` | E-posta, push, SMS |
| `imports` | Çalışan import, PDKS import, belge eşleme |
| `payroll` | Puantaj/bordro export, V2 payroll run |
| `ai` | CV parse, RAG index, özetleme, öneriler |
| `integrations` | Webhook, PDKS, ERP, takvim, e-imza |

Async task kuralları:

- Task payload büyük veri taşımaz; ID taşır.
- `tenant_id` zorunludur.
- Task idempotent olmalıdır.
- Retry ve dead-letter mekanizması olmalıdır.
- Hata kullanıcıya izlenebilir status ile dönmelidir.

## 7. Veri katmanı

PostgreSQL ana veri katmanıdır.

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
