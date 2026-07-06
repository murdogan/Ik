# Overnight Codex Control Protocol

## Amaç

00:00–05:00 Türkiye saati arasında Codex'in tek bir sprint/task ile sınırlı kalmadan, sıradaki hazır görevleri bitirdikçe güvenli şekilde yeni göreve geçmesini sağlamak.

## Temel İlke

Codex tek başına serbest bırakılmaz. Hermes saatlik cronjob kontrolü, repo durumu, test sonucu, commit durumu ve task kuyruğuna göre Codex'e bir sonraki işi verir.

## Çalışma Modeli

### 1. Branch

Gece çalışması ayrı branch üzerinde yapılır:

```text
overnight/sprint-0-wealthy-falcon
```

`main`e merge yapılmaz.

### 2. Task Queue

Task kuyruğu dosyası:

```text
/opt/data/repos/Ik/.hermes/overnight/task-queue.md
```

Her task şu statülerden birine sahip olur:

- `pending`
- `in_progress`
- `done`
- `blocked`
- `skipped`

### 3. Saatlik Orkestratör

Saatlik cronjob şu adımları uygular:

1. Codex process hâlâ çalışıyor mu kontrol eder.
2. Çalışıyorsa log + git diff + test durumunu raporlar, yeni task vermez.
3. Codex durmuşsa:
   - Son task commitlenmiş mi kontrol eder.
   - `uv run ruff check backend` çalıştırır.
   - `uv run pytest` çalıştırır.
   - Başarılıysa task'ı `done` işaretler.
   - Sıradaki `pending` task'ı seçer.
   - Yeni Codex process başlatır.
4. Test/ruff kırmızıysa yeni task vermez; önce düzeltme task'ı oluşturur.

### 4. Stop Rules

Yeni task verilmez, durum `blocked` yapılır:

- Testler 2 kontrol boyunca kırmızı kalırsa.
- Ruff kırmızı kalırsa.
- Secret/env dosyalarına dokunulursa.
- Production/staging deploy değişikliği görülürse.
- Scope dışı modül başlarsa: bordro, SGK, banka, AI, PDKS.
- Migration veri kaybı riski varsa.
- Saat 04:30 sonrası büyük yeni task başlatılmaz; sadece toparlama/fix yapılır.

## Gece Task Kuyruğu Önerisi

### T0 — Baseline ve branch hazırlığı

Status: pending

Amaç:
- Branch aç.
- Plan dosyasını commit et.
- Baseline test/ruff çalıştır.

Kabul:
- Branch hazır.
- Testler yeşil.
- Working tree temiz veya sadece bilinen plan dosyaları var.

### T1 — README ve lokal geliştirme komutları

Status: pending

Amaç:
- README lokal geliştirme komutlarını netleştir.
- uv/test/ruff/staging smoke komutlarını ekle.

Kabul:
- README güncel.
- Testler yeşil.
- Commit var.

### T2 — CI workflow

Status: pending

Amaç:
- GitHub Actions CI ekle.
- Ruff + pytest çalışsın.

Kabul:
- `.github/workflows/ci.yml` var.
- Lokal testler yeşil.
- Commit var.

### T3 — Alembic / migration foundation kontrolü

Status: pending

Amaç:
- Mevcut migration yapısını kontrol et.
- Eksikse minimum Alembic setup ekle.
- Tenant/user migration zincirini netleştir.

Kabul:
- Migration komutları dokümante.
- Testler yeşil.
- Commit var.

### T4 — Tenant/User foundation hardening

Status: pending

Amaç:
- Tenant/user modellerini mevcut testlere göre sağlamlaştır.
- Tenant isolation helper/testlerini güçlendir.

Kabul:
- Tenant/user testleri yeşil.
- Genel pytest yeşil.
- Commit var.

### T5 — Employee minimal model

Status: pending

Amaç:
- Employee model + test ekle.
- Tenant scoped olmalı.

Kabul:
- Employee model testleri var.
- Genel pytest yeşil.
- Commit var.

### T6 — Leave request minimal model

Status: pending

Amaç:
- Leave request model + test ekle.
- Pending/approved/rejected/cancelled statüleri olsun.

Kabul:
- Leave request testleri var.
- Genel pytest yeşil.
- Commit var.

### T7 — Dashboard summary endpoint

Status: pending

Amaç:
- `/api/v1/dashboard/summary` endpoint taslağı ekle.
- İlk demo kartları için response döndür.

Kabul:
- Endpoint testleri var.
- Genel pytest yeşil.
- Commit var.

### T8 — Landing brand update

Status: pending

Amaç:
- Landing adını `Wealthy Falcon HR` olarak güncelle.
- Beğenilen tasarım dilini koru.

Kabul:
- Landing testleri güncel.
- Genel pytest yeşil.
- Commit var.

### T9 — Final cleanup and report

Status: pending

Amaç:
- Ruff/test final çalıştır.
- Diff/commit özeti çıkar.
- Kalan işleri raporla.

Kabul:
- Final rapor hazır.
- Büyük yarım iş bırakılmamış.

## Codex Çalıştırma Modu

Canlı kontrol sonucu:

- Codex CLI: `codex-cli 0.142.5`
- Auth: `Logged in using ChatGPT`
- En yüksek kullanılabilir model kataloğunda: `gpt-5.5`
- `gpt-5.1-codex-max` ChatGPT hesabıyla desteklenmiyor; smoke test 400 döndü.
- `gpt-5.5` smoke test geçti.

Her gece task'ı şu modda çalıştırılır:

```bash
codex exec \
  -m gpt-5.5 \
  -c 'model_reasoning_effort="xhigh"' \
  --sandbox danger-full-access \
  "<TASK_PROMPT>"
```

Beklenen Codex header:

```text
model: gpt-5.5
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: xhigh
```

Reasoning effort test notu:

- `model_reasoning_effort="high"` çalışıyor.
- `model_reasoning_effort="max"` geçersiz; Codex desteklenen değerleri `none`, `minimal`, `low`, `medium`, `high`, `xhigh` olarak döndürdü.
- En yüksek desteklenen değer `xhigh`; smoke test geçti.

Not: `danger-full-access` güçlü moddur; güvenliği branch izolasyonu, dar workdir, stop rules, test/ruff kapısı ve commit review ile sağlanır.

## Codex Prompt Şablonu

Her task için Codex'e şu tür prompt verilir:

```text
You are working in /opt/data/repos/Ik on branch overnight/sprint-0-wealthy-falcon.
Implement ONLY task <TASK_ID>: <TASK_TITLE>.

Rules:
- Do not touch production/staging deploy or cron settings.
- Do not edit secrets or env files.
- Do not add payroll, SGK, bank, AI, PDKS features.
- Keep changes minimal and tested.
- Run: uv run ruff check backend
- Run: uv run pytest
- Commit only if tests pass.
- Use a clear commit message.
- Stop and report if blocked.
```

## Rapor Formatı

Saatlik rapor:

```text
Saat: 01:00 TR
Task: T3 Alembic / migration foundation
Codex: running / completed / blocked
Tests: green / red
Ruff: green / red
Commits: ...
Changed files: ...
Next action: continue / fix / next task / stop
```

## Final Karar

Bu model tek sprint değil, task kuyruğu bazlı çalışır. Codex bitirdikçe Hermes kontrol eder, test geçerse sıradaki task'ı verir. Böylece 00:00–05:00 arası boşta kalmaz.
