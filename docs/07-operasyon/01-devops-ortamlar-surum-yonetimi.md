# DevOps, Ortamlar ve Sürüm Yönetimi

Bu doküman, IK Platform'un ortam topolojisi, CI/CD hattı, deployment stratejisi, migration, rollback, backup ve disaster recovery yaklaşımını tanımlar.

## 1. Ortamlar

| Ortam | Amaç | Veri | Erişim |
|---|---|---|---|
| `local` | Geliştirici | Sentetik | Geliştirici |
| `dev` | Entegrasyon geliştirme | Sentetik | Geliştirici/QA |
| `staging` | Release doğrulama | Anonimleştirilmiş/sentetik | Ekip |
| `pilot` | Pilot müşteri | Gerçek veri, sınırlı kullanıcı | Pilot ekip |
| `prod` | Canlı SaaS | Gerçek veri | Kısıtlı, auditli |
| `dr` | Felaket kurtarma | Replike backup | SRE |

Kurallar:

- Gerçek kişisel veri local/dev ortamlarında yasaktır.
- Staging verisi anonimleştirilmiş olmalıdır.
- Prod erişimi break-glass/JIT yaklaşımıyla auditlenir.
- İmaj farkı değil, config farkı olmalıdır.

## 2. Repo ve branch stratejisi

MVP için tek repo yeterlidir:

```text
backend/
web/
docs/
infra/
.github/
```

Branch yaklaşımı:

- `main` korumalı.
- Feature branch kısa ömürlü.
- PR review zorunlu.
- Conventional commit önerilir.
- Büyük özellikler feature flag arkasında merge edilir.

Pratik branch komutları:

```bash
git switch main
git pull --ff-only
git switch -c <task-branch>
git status --short --branch
```

Gece Sprint-0 işleri için ayrılmış branch:

```bash
git switch overnight/sprint-0-wealthy-falcon
```

Phase 10 commit öncesi statik kalite kontrolleri:

```bash
uv run ruff check backend scripts/ops
uv run ruff format --check backend scripts/ops
```

İlgili dosyalar dar kapsamla stage edilir:

```bash
git add README.md docs/<ilgili-dosya>.md
git commit -m "docs(T1): document local development commands"
```

### 2.1 Lokal geliştirme komutları

Kurulum:

```bash
uv sync --all-groups
```

Backend statik kalite kontrolü:

```bash
uv run ruff check backend scripts/ops
uv run ruff format --check backend scripts/ops
```

Geniş `pytest` regresyon kapısı, geçmiş fixture/snapshot onarımı tamamlandıktan sonra Phase 11'de
yeniden etkinleştirilir.

App import smoke testi:

```bash
PYTHONPATH=backend uv run python -c "from app.main import create_app; print(create_app().title)"
```

Lokal backend API smoke testi:

```bash
uv run python scripts/backend_api_smoke.py
```

Bu komut server, lokal PostgreSQL, deploy, cron, token veya `.env` gerektirmez. In-memory
SQLite ile health, landing, OpenAPI, platform tenant lifecycle/metadata/limit/feature işlemleri,
current tenant settings/features, principal-denial sınırları, dashboard summary, employee CRUD ve
leave request workflow endpointlerini ASGI üzerinden doğrular.

Opsiyonel lokal HTTP landing/health smoke testi:

Terminal 1:

```bash
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

Terminal 2:

```bash
uv run python scripts/staging_smoke_test.py http://127.0.0.1:8001
```

Staging smoke testi, yalnızca zaten çalışan staging URL'sine karşı çalıştırılır:

```bash
uv run python scripts/staging_smoke_test.py https://<staging-url>
```

Bu smoke komutu deploy, cron veya ortam ayarı değiştirmez.

## 3. CI pipeline

Uzun vadeli pipeline kapsamı aşağıdaki aşamalardan oluşur:

| Aşama | Kontrol |
|---|---|
| Lint | Python/TypeScript/Markdown kontrolleri |
| Type check | Backend ve frontend tip kontrolü |
| Unit test | Domain logic ve UI unit testleri |
| Integration | DB/Redis/API entegrasyonu |
| Migration check | Upgrade/downgrade smoke |
| Security | Secret scan, SAST, dependency scan |
| Build | Docker image |
| Contract | OpenAPI diff ve client generation |
| Smoke | Auth, tenant, core akışlar |

### 3.1 Aktif Phase 10 kalite kapısı

`.github/workflows/quality.yml`; pull request'lerde, `main` push'larında ve manuel tetiklemede
salt-okunur yetkiyle çalışır. Aynı ref için daha yeni bir çalışma başladığında önceki çalışma iptal
edilir. Aktif kapılar şunlardır:

- Backend işi Ubuntu ve Python 3.13 üzerinde kilitli `uv.lock` ile kurulum yapar; backend ile üretim
  operasyon scriptlerinde Ruff lint/format kontrolü ve Python derleme kontrolü çalıştırır. OpenAPI
  şemasını lokal modda üretip `/health/live`, `/health/ready` ve
  `/api/v1/tenant/readiness` yollarını ve yalnızca tenant readiness yolundaki BearerAuth güvenlik
  sözleşmesini doğrular. Alembic kontrolü yalnızca veritabanına bağlanmayan `alembic heads` ile
  statik sınırda kalır; `alembic check` bu koşul kanıtlanmadan çalıştırılmaz.
- Frontend işi paket engine şartını karşılayan Node sürümü ve `npm ci` ile typecheck, lint ve üretim
  build kontrollerini çalıştırır.
- Release-manifest işi yalnızca `main` push'unda veya manuel tetiklemede, backend ve frontend işleri
  başarılı olduktan sonra çalışır.

Phase 10 kalite workflow'u bilerek geniş `pytest` regresyon paketini ve Playwright/E2E'yi çalıştırmaz.
Tam backend regresyonu ve E2E kapısı, geçmiş fixture/snapshot onarımı tamamlandıktan sonra Phase 11'de
etkinleştirilir; mevcut Phase 10 kapıları tam regresyon sonucu olarak yorumlanmaz.

## 4. CD ve deployment

| Strateji | Kullanım |
|---|---|
| Rolling update | Stateless API/web |
| Blue/green | Büyük release |
| Canary | Riskli backend değişiklikleri |
| Feature flag | Tenant/modül bazlı rollout |
| Maintenance window | Büyük DB migration veya payroll dönemi etkisi |

MVP'de basit deployment yeterlidir; V1/Enterprise için Kubernetes + Helm + GitOps önerilir.

Staging deploy, checkout ve bağımlılık senkronizasyonundan sonra mevcut prosesi durdurmadan önce özel
bir release dizininde manifesti üretir, checksum ve şemayı doğrular ve hedefli üretim preflight
kontrollerini tamamlar. Bu aşamalardan biri başarısız olursa çalışan proses durdurulmaz. Yeni proses
başlatılırken doğrulanmış manifest değerleri `IK_RELEASE_COMMIT_SHA` ve
`IK_RELEASE_BUILD_TIMESTAMP` olarak Uvicorn ortamına verilir. Bu iki değişken staging ve production
için zorunludur; commit değeri 40 karakterlik küçük harf hexadecimal SHA, timestamp değeri kesirsiz
UTC `YYYY-MM-DDTHH:MM:SSZ` biçimindedir ve uygulama çalışırken `.git` içeriğinden türetilmez.

Başlangıç kontrolü `/health/ready` üzerinden yapılır. Yanıttaki `commit_sha`, deploy edilen
`remote_rev` ile birebir eşleşmeden deployment başarılı sayılmaz; readiness yanıt gövdesi ve release
ortam değerleri loglanmaz.

## 5. Migration stratejisi

Migration kuralları:

- Geriye uyumlu migration önceliklidir.
- Destructive change iki fazlı yapılır: expand → deploy → contract.
- Büyük tablo değişiklikleri lock riski açısından incelenir.
- Tenant tablolarında `tenant_id` ve RLS guard kontrol edilir.
- Migration PR'ı rollback planı içermelidir.

## 6. Rollback yaklaşımı

| Alan | İlk aksiyon |
|---|---|
| Feature hatası | Feature flag kapat |
| Uygulama hatası | Önceki image/sürüm rollback |
| Migration hatası | Backward compatible ise app rollback; data fix ayrı onay |
| AI model hatası | Önceki approved model/prompt version |
| Entegrasyon hatası | Connector disable veya retry durdurma |

## 7. Backup ve DR

| Hedef | MVP | Enterprise |
|---|---:|---:|
| RPO | 4 saat | 15 dk - 1 saat |
| RTO | 8 saat | 1 - 4 saat |
| PITR | 7-14 gün | 35 gün |
| Backup test | Çeyreklik | Aylık |
| Object versioning | Evet | Evet + immutable |

Backup kapsamı:

- PostgreSQL.
- Object storage.
- Secret/config backup policy.
- Audit log retention.
- OpenAPI/docs/deploy repo zaten git üzerinde.

## 8. Release yönetimi

### 8.1 Değişmez release manifesti

`scripts/ops/release_manifest.py`, her release için canonical JSON biçiminde şu kapalı şemayı üretir:
`release_commit_sha`, `build_timestamp_utc`, `app_version` ve
`compatible_migration_head_ids`. Yanındaki `<manifest>.sha256` dosyası manifestin SHA-256 özetini ve
yalnızca manifest dosya adını içerir. Manifest ile checksum özel dosya izinleriyle atomik yazılır ve
doğrulandıktan sonra aynı release kimliğinin değişmez kaydı olarak kullanılır.

Aktif CI release-manifest işi commit SHA ve UTC build timestamp ile manifesti yeniden üretir, strict
şemayı ve checksum'u doğrular, ardından manifest ile checksum'u güvenli kısa SHA içeren isimle ve
sonlu saklama süresiyle tek artifact olarak yükler. Artifact credential, host veya repository yolu
içermez. Manifestteki migration head listesi Phase 10E rollback guard ile uyumludur; uygulama rollback
kararı ancak canlı migration head'leri hem mevcut hem hedef release manifestiyle aynıysa verilir.

Uzun vadeli release checklist'i (tam regresyon/E2E maddeleri Phase 11 sınırındadır):

- CI yeşil.
- Migration smoke yeşil.
- OpenAPI diff incelendi.
- Security taraması temiz veya onaylı exception.
- Staging smoke geçti.
- Kritik E2E akışlar geçti.
- Rollback planı hazır.
- Release notu yazıldı.

Release rolleri:

| Rol | Sorumluluk |
|---|---|
| Release captain | Release kararını ve iletişimi yönetir |
| SRE | Deploy, rollback ve gözlem penceresini yönetir |
| QA | Smoke/regression sonucunu onaylar |
| Security | Kritik güvenlik exceptionlarını onaylar |
| Product owner | Kullanıcı etkisi ve release notunu onaylar |

## 9. Feature flag ve rollout

Feature flag kullanımı:

- Yeni modül tenant bazında açılır.
- Riskli backend değişiklikleri dark launch ile gözlenir.
- AI ve payroll gibi yüksek riskli alanlar default kapalı gelir.
- Flag değişikliği auditlenir.
- Eski flagler düzenli temizlenir; kalıcı config'e dönüşenler dokümante edilir.

Rollout sırası:

1. Internal tenant.
2. Staging/pilot tenant.
3. Küçük gerçek tenant grubu.
4. Tüm standart tenantlar.
5. Enterprise dedicated tenantlar.

## 10. Operasyonel erişim

Prod erişim ilkeleri:

- Doğrudan DB erişimi normal operasyon değildir.
- Gerekirse süreli ve gerekçeli erişim açılır.
- Her erişim auditlenir.
- Data fix scriptleri PR/review ile çalıştırılır.
- Müşteri verisine erişim minimum kapsamla yapılır.

## 11. Kabul kriterleri

- Local/dev gerçek veri barındırmaz.
- Phase 10 CI statik backend/frontend kapılarını ve immutable manifest doğrulamasını çalıştırır;
  tam regresyon/E2E Phase 11 sınırındadır.
- Deployment rollback stratejisi tanımlıdır.
- Backup restore testi planlanmıştır.
- Migration geriye uyumlu tasarlanır.
- Prod değişiklikleri auditlenir.

## 12. İlgili dokümanlar

- [Observability, SLO ve Alarm](02-observability-slo-alarm.md)
- [Test Stratejisi ve QA](03-test-stratejisi-qa.md)
- [Backup, Restore ve Rollback Runbook](04-backup-restore-rollback-runbook.md)
- [Güvenlik Mimarisi, OWASP ve Incident](../06-guvenlik-uyum/03-guvenlik-mimarisi-owasp-incident.md)
