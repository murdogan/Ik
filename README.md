# IK — İnsan Kaynakları Yönetim Sistemi

Bu repo, Türkiye pazarı öncelikli ve global pazara açılabilir bir İnsan Kaynakları Yönetim Sistemi için ürün, strateji, modül, mimari, güvenlik, test, canlıya alma dokümantasyonu ve ilk backend uygulama iskeletini içerir.

## Çalışma yaklaşımı

Bu çalışma üç kaynaktan beslendi:

1. **Codex referansı:** Dosya ve modül iskeleti için ana kontrol listesi.
2. **Claude referansı:** Derinlik, detay seviyesi ve uygulanabilirlik standardı.
3. **Mevcut repo geçmişi:** Daha önce hazırlanmış dokümanlar Git geçmişinde korunur; aktif ağaçta temiz foundation tutulur.

## İlk prensipler

- Önce dokümantasyon, sonra kod.
- Her kararın sahibi ve etkisi belli olmalı.
- Her modül MVP / V1 / V2 ayrımıyla yazılmalı.
- Her modül veri, API, yetki, KVKK, audit ve test etkisiyle ele alınmalı.
- Kırık link, yarım dosya ve boş vaat bırakılmamalı.
- Kod tarafında test edilmemiş scaffold “bitti” sayılmamalı.

## Doküman yapısı

Ana giriş noktası: [docs/README.md](docs/README.md)

```text
docs/
├── 00-genel/              # Konvansiyonlar, roller, terimler, karar kayıtları
├── 01-strateji-pazar/     # Vizyon, pazar, rakipler, fiyatlandırma
├── 02-urun/               # Personalar, JTBD, MVP/V1/V2 kapsamı, metrikler
├── 03-moduller/           # Tüm ürün modülleri ve ortak modül formatı
├── 04-mimari/             # Teknik mimari, multi-tenancy, teknoloji kararları
├── 05-api-veri/           # Veritabanı, API, webhook, entegrasyon, migrasyon
├── 06-guvenlik-uyum/      # Auth, RBAC, KVKK/GDPR, OWASP, AI güvenliği
├── 07-operasyon/          # DevOps, observability, test, runbook
├── 08-yurutme/            # Roadmap, ekip, GTM, risk/backlog
└── 09-uygulama/           # Sprint backlog, OpenAPI, ERD, wireframe, import, demo, readiness
```

## Kod yapısı

```text
backend/
├── app/
│   ├── api/               # API router'ları
│   ├── core/              # Config, tenancy ve ortak altyapı
│   ├── db/                # SQLAlchemy session ve declarative base
│   ├── models/            # Tenant-scoped ORM modelleri
│   ├── schemas/           # Pydantic request/response şemaları
│   ├── services/          # Küçük domain servisleri
│   └── main.py            # FastAPI app factory
└── tests/                 # Pytest testleri
```

## Lokal geliştirme

Gereksinim: `uv` ve Python 3.13. Komutlar repo kökünden çalıştırılır.

Kurulum:

```bash
uv sync --all-groups
```

Commit öncesi kalite kapıları:

```bash
uv run ruff check backend
uv run pytest
```

Veritabanı migration komutları:

```bash
uv run alembic history
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

`alembic.ini` lokal geliştirme veritabanını hedefler. Migration komutlarını yalnızca lokal/dev
veritabanına karşı çalıştırın; production/staging migration çalıştırma bu repo task akışının
parçası değildir. Yeni migration'lar küçük, geriye uyumlu ve tenant/user zincirini bozmayacak
şekilde hazırlanmalıdır; destructive değişiklikler Sprint-0 kapsamına alınmaz.

Lokal app import smoke testi:

```bash
PYTHONPATH=backend uv run python -c "from app.main import create_app; print(create_app().title)"
```

Beklenen çıktı `IK Platform API` olmalıdır.

Lokal backend API smoke testi:

```bash
uv run python scripts/backend_api_smoke.py
```

Bu smoke testi server veya lokal PostgreSQL gerektirmez. FastAPI uygulamasını ASGI üzerinden
çalıştırır, geçici SQLite veritabanı oluşturur ve şu yüzeyi kontrol eder:

- `/health`
- `/`
- `/openapi.json`
- `/api/v1/dashboard/summary`
- `/api/v1/employees` liste + `department`/`status`/`q` filtreleri, `limit`/`offset` pagination,
  oluşturma/detay/güncelleme/silme
- `/api/v1/leave-requests` liste + `status`/`employee_id`/`start_date`/`end_date` filtreleri,
  oluşturma/onay/red/iptal

Başarılıysa `BACKEND_SMOKE_OK` çıktısı verir.

Opsiyonel lokal HTTP landing/health smoke testi:

Terminal 1:

```bash
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

Terminal 2:

```bash
uv run python scripts/staging_smoke_test.py http://127.0.0.1:8001
```

Smoke testi `/` ve `/health` endpointlerini kontrol eder; başarılıysa `SMOKE_OK` çıktısı verir.
Staging için aynı script yalnızca mevcut çalışan URL'ye karşı çalıştırılır:

```bash
uv run python scripts/staging_smoke_test.py https://<staging-url>
```

Bu komut deploy, cron veya ortam ayarı değiştirmez.

Beklenen sonuç:

- Ruff backend kontrolü hata vermez.
- Pytest tüm testleri yeşil döndürür.
- App import edilir ve `IK Platform API` çıktısı verir.
- Backend API smoke testi `BACKEND_SMOKE_OK` çıktısı verir.
- Opsiyonel HTTP landing/health smoke testi `SMOKE_OK` çıktısı verir.

## Branch iş akışı

`main` korumalıdır; değişiklikler kısa ömürlü branch üzerinde yapılır.

```bash
git switch main
git pull --ff-only
git switch -c <task-branch>
git status --short --branch
```

Task bitince kalite kapıları çalıştırılır ve yalnızca ilgili dosyalar commitlenir:

```bash
uv run ruff check backend
uv run pytest
git add README.md docs/<ilgili-dosya>.md
git commit -m "docs(T1): document local development commands"
```

## CI

GitHub Actions workflow template'i: `docs/09-uygulama/templates/backend-ci.yml`

Not: Bu template `.github/workflows/ci.yml` olarak taşındığında GitHub token'ında `workflow` scope gerekir. Mevcut ortamda bu scope olmadığı için workflow şimdilik template olarak tutulur.

CI şunları çalıştırır:

- `uv sync --all-groups`
- `uv run ruff check backend`
- `uv run pytest`

## Durum

Plan dokümantasyon seti tamamlanmıştır. Mevcut repoda daha önce eklenmiş küçük bir Sprint-0 backend scaffold'u vardır; fakat bundan sonraki kod genişletmeleri kullanıcıdan açık “koda geç” onayı alınmadan yapılmamalıdır.

Plan tamamlık kapısı: [Implementation Readiness Checklist](docs/09-uygulama/08-implementation-readiness-checklist.md).
