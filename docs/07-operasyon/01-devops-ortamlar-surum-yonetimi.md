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

Commit öncesi kalite kapıları:

```bash
uv run ruff check backend
uv run pytest
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

Backend kalite kontrol:

```bash
uv run ruff check backend
uv run pytest
```

App import smoke testi:

```bash
PYTHONPATH=backend uv run python -c "from app.main import create_app; print(create_app().title)"
```

Lokal HTTP smoke testi:

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

## 4. CD ve deployment

| Strateji | Kullanım |
|---|---|
| Rolling update | Stateless API/web |
| Blue/green | Büyük release |
| Canary | Riskli backend değişiklikleri |
| Feature flag | Tenant/modül bazlı rollout |
| Maintenance window | Büyük DB migration veya payroll dönemi etkisi |

MVP'de basit deployment yeterlidir; V1/Enterprise için Kubernetes + Helm + GitOps önerilir.

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

Release checklist:

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
- CI test ve güvenlik kontrollerini çalıştırır.
- Deployment rollback stratejisi tanımlıdır.
- Backup restore testi planlanmıştır.
- Migration geriye uyumlu tasarlanır.
- Prod değişiklikleri auditlenir.

## 12. İlgili dokümanlar

- [Observability, SLO ve Alarm](02-observability-slo-alarm.md)
- [Test Stratejisi ve QA](03-test-stratejisi-qa.md)
- [Güvenlik Mimarisi, OWASP ve Incident](../06-guvenlik-uyum/03-guvenlik-mimarisi-owasp-incident.md)
