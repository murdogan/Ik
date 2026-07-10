# Çok Kiracılık ve Veri İzolasyonu

Bu doküman, IK Platform'un çok kiracılı SaaS modelini, tenant çözümleme yaklaşımını, veri izolasyonu katmanlarını ve enterprise dedicated opsiyonlarını tanımlar.

## 1. Karar özeti

Varsayılan model:

> Shared application + shared PostgreSQL schema + `tenant_id` + composite tenant foreign key +
> uygulama seviyesi tenant guard + Faz 1 PostgreSQL RLS.

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
| `plan_code` | Core, Professional, Enterprise |
| `data_region` | Veri bölgesi |
| `db_target` | pool veya dedicated bağlantı referansı |
| `timezone` | Tenant saat dilimi |
| `locale` | Varsayılan dil/yerel ayar |

Tenant ayarları `tenant_settings`, modül aç/kapa kararları `tenant_feature_flags` ile tutulmalıdır.

## 4. Tenant çözümleme

Tenant şu kaynaklardan çözülür:

1. Kimlikli isteklerde JWT/session içindeki `tenant_id`.
2. Login öncesi ve public sayfalarda subdomain/custom domain.
3. Internal servis çağrılarında imzalı servis token + tenant context.

Kurallar:

- Body içindeki `tenant_id` authorization için asla güvenilir kaynak değildir.
- JWT tenant ile host tenant uyuşmazsa istek reddedilir.
- Kullanıcı birden fazla tenant'ta varsa ayrı oturum bağlamı gerekir.
- Tenant context request boyunca immutable olmalıdır.

## 5. Veri izolasyonu katmanları

| Katman | Kontrol |
|---|---|
| Auth | JWT/session içinde tenant claim |
| Middleware | Tenant context zorunlu |
| Repository | Her sorguda tenant filtresi |
| DB | Tenant-owned ilişkilerde composite foreign key; Faz 1'de RLS |
| Cache | `tenant:{tenant_id}` prefix |
| Object storage | Tenant prefix ve metadata |
| Search/vector | Tenant filter ve ACL hash |
| Logs | Tenant tag var, PII yok |
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

RLS Faz 1'de uygulanırsa her tenant tablosunda şu prensip uygulanır:

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON employees
USING (tenant_id = current_setting('app.tenant_id')::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

Uygulama transaction başında `SET LOCAL app.tenant_id = ...` yapmalıdır.

Kritik noktalar:

- Uygulama DB rolünde `BYPASSRLS` olmamalıdır.
- Background job da tenant context set etmelidir.
- Faz 1 RLS rollout'u başladığında policy'siz tenant tablosu CI'da fail etmelidir.

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

| Aşama | Sistem davranışı |
|---|---|
| Provisioning | Tenant, ilk admin, varsayılan roller, ayarlar seed edilir |
| Trial | Limitli kullanım, demo/pilot veri importu |
| Active | Sözleşme ve ödeme aktif, prod kullanım |
| Suspended | Login ve scheduled job policy'ye göre kapatılır |
| Offboarding | Veri export, bekleme süresi, imha planı |
| Closed | Veri imha ve kapanış audit kaydı |

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
- Uygulama servisleri bypass edilse bile PostgreSQL doğrudan write ile Tenant A child kaydı Tenant B
  employee/user kaydına bağlanamaz.
- Preflight orphan ile cross-tenant satırları ayrı raporlar; valid veri upgrade/downgrade boyunca
  korunur.
- Tenant A document URL'i Tenant B'de çalışmaz.
- Cache key cross-tenant çakışmaz.
- Background job tenant context olmadan fail eder.
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
