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

İlk kod tabanı tek uygulama olabilir ama modül sınırları baştan net olmalıdır.

Önerilen backend paketleri:

```text
app/
  core/          config, db, tenancy, authz, audit, events
  modules/
    auth/
    employee/
    document/
    organization/
    leave/
    selfservice/
    time_attendance/
    payroll/
    ats/
    performance/
    learning/
    reporting/
    ai/
    integrations/
  workers/
  main.py
```

Kurallar:

- Modül başka modülün tablosuna doğrudan yazmaz.
- Modüller arası değişiklik domain event veya public service interface ile yapılır.
- Raporlama read-only istisna olabilir ama field permission uygulanır.
- Kod aşamasında import sınırları CI ile kontrol edilmelidir.

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
