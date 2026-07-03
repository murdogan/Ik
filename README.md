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
│   └── main.py            # FastAPI app factory
└── tests/                 # Pytest testleri
```

## Lokal geliştirme

Gereksinim: `uv` ve Python 3.13.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check backend
PYTHONPATH=backend uv run python -c "from app.main import create_app; print(create_app().title)"
```

Beklenen sonuç:

- Testler yeşil: `2 passed`.
- App import edilir ve `IK Platform API` çıktısı verir.
- Ruff backend kontrolü hata vermez.

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
