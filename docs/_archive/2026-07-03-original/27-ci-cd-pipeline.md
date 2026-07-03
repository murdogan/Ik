# 27 — CI/CD Pipeline

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Build, test, lint, image üretimi, deploy pipeline, ortam promosyonu, release tagging ve rollback yaklaşımı  
> **Faz:** Faz 6

---

## 1. Amaç

CI/CD hattının amacı; kod kalitesini otomatik kontrollerle güvence altına almak, build ve test süreçlerini standardize etmek ve dağıtımı tekrar edilebilir hale getirmektir.

---

## 2. Pipeline Aşamaları

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Validate │→│   Test   │→│  Build   │→│ Security │→│ Release  │→│  Deploy  │
│          │  │          │  │          │  │          │  │          │  │          │
│ • Lint   │  │ • Unit   │  │ • Docker │  │ • Snyk   │  │ • Tag    │  │ • Staging│
│ • Format │  │ • Integ. │  │   image  │  │ • Trivy  │  │ • GHCR   │  │ • Prod   │
│ • Type   │  │ • Cov.   │  │ • Assets │  │ • Gitleak│  │ • Notes  │  │ • Smoke  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

| Aşama | İçerik | Başarısız → |
|-------|--------|-------------|
| Validate | Lint (ruff, eslint), format check (black, prettier), type check (mypy, tsc) | Pipeline durur |
| Test | Unit testler, entegrasyon testleri, coverage raporu | Pipeline durur |
| Build | Docker image build (API, Web, Worker), static asset build | Pipeline durur |
| Security | Dependency scan (Snyk), image scan (Trivy), secret scan (Gitleaks) | Pipeline durur (critical/high) |
| Release | Image push (GHCR/ECR), git tag, release notes | — |
| Deploy | Staging otomatik, Prod manuel onay + smoke test | Rollback |

---

## 3. GitHub Actions Workflow'ları

### 3.1 PR Validation Workflow

```yaml
# .github/workflows/pr-validation.yml
name: PR Validation

on:
  pull_request:
    branches: [main, develop]

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
    steps:
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'apps/api/**'
              - 'requirements*.txt'
            frontend:
              - 'apps/web/**'
              - 'package*.json'

  backend-validate:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
      redis:
        image: redis:7-alpine
        ports: ['6379:6379']
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt

      - name: Lint (ruff)
        run: ruff check apps/api/

      - name: Format check (black)
        run: black --check apps/api/

      - name: Type check (mypy)
        run: mypy apps/api/ --config-file pyproject.toml

      - name: Security lint (bandit)
        run: bandit -r apps/api/ -c pyproject.toml

      - name: Unit tests
        run: |
          pytest apps/api/tests/unit/ \
            --cov=apps/api \
            --cov-report=xml \
            --cov-fail-under=80 \
            -x --tb=short
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0

      - name: Integration tests
        run: |
          pytest apps/api/tests/integration/ \
            -x --tb=short
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          flags: backend

  frontend-validate:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: apps/web/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: apps/web

      - name: Lint (eslint)
        run: npm run lint
        working-directory: apps/web

      - name: Type check (tsc)
        run: npx tsc --noEmit
        working-directory: apps/web

      - name: Unit tests
        run: npm run test -- --coverage --watchAll=false
        working-directory: apps/web

      - name: Build check
        run: npm run build
        working-directory: apps/web

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Secret scan (Gitleaks)
        uses: gitleaks/gitleaks-action@v2

      - name: Dependency scan (Snyk)
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=high
```

### 3.2 Release & Deploy Workflow

```yaml
# .github/workflows/release-deploy.yml
name: Release & Deploy

on:
  push:
    tags: ['v*']

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [api, web, worker]
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v5
        with:
          context: ./apps/${{ matrix.service }}
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.service }}:${{ github.ref_name }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.service }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Image scan (Trivy)
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.service }}:${{ github.ref_name }}
          severity: CRITICAL,HIGH
          exit-code: '1'

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to staging
        run: |
          ssh deploy@staging.ikys.internal << 'EOF'
            cd /opt/ikys
            docker compose pull
            docker compose run --rm api python manage.py migrate
            docker compose up -d --remove-orphans
          EOF

      - name: Smoke test
        run: |
          sleep 10
          curl -f https://staging.ikys.internal/api/health || exit 1

  deploy-prod:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://app.ikys.com
    steps:
      - name: Deploy to production
        run: |
          ssh deploy@prod.ikys.internal << 'EOF'
            cd /opt/ikys
            docker compose pull
            docker compose run --rm api python manage.py migrate --check
            docker compose run --rm api python manage.py migrate
            docker compose up -d --remove-orphans
          EOF

      - name: Health check
        run: |
          for i in $(seq 1 6); do
            curl -sf https://app.ikys.com/api/health && exit 0
            sleep 10
          done
          exit 1

      - name: Smoke tests
        run: |
          curl -sf https://app.ikys.com/api/health/ready
          curl -sf https://app.ikys.com/api/v1/auth/csrf
```

### 3.3 Scheduled Security Workflow

```yaml
# .github/workflows/nightly-security.yml
name: Nightly Security Scan

on:
  schedule:
    - cron: '0 2 * * *'  # Her gece 02:00 UTC

jobs:
  dependency-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Python dependency audit
        run: pip-audit -r requirements.txt

      - name: NPM audit
        run: npm audit --audit-level=high
        working-directory: apps/web

      - name: Notify on failure
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          payload: '{"text": "🚨 Nightly security scan failed!"}'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

### 3.4 Path Filter Yaklaşımı

| Yol | Etkilenen İş Akışları |
|-----|-----------------------|
| `apps/api/**` | Backend validate, test, API image build |
| `apps/web/**` | Frontend validate, test, Web image build |
| `requirements*.txt` | Backend validate, security scan |
| `package*.json` | Frontend validate, security scan |
| `infra/**`, `docker-compose*` | Deployment kontrolleri |
| `.github/workflows/**` | İlgili workflow tekrar çalışır |

---

## 4. Release Kuralları ve Branch Stratejisi

### 4.1 Branch Modeli

```
main (production-ready)
  ├── develop (geliştirme entegrasyonu)
  │     ├── feature/IKYS-123-izin-modulu
  │     ├── feature/IKYS-124-bordro-fix
  │     └── bugfix/IKYS-130-login-error
  ├── release/1.2.0 (staging testi)
  └── hotfix/1.1.1 (acil düzeltme)
```

### 4.2 Branch Kuralları

| Kural | Kod | Açıklama |
|-------|-----|----------|
| Korumalı branch | CICD-01 | `main` ve `develop` branch'lerine direct push yasak |
| PR zorunluluğu | CICD-02 | En az 1 review + CI başarılı → merge |
| Squash merge | CICD-03 | Feature branch'ler squash merge ile birleştirilir |
| Staging geçiş | CICD-04 | Prod dağıtımı staging doğrulaması sonrası |
| Migration onay | CICD-05 | Kritik migration içeren PR'larda DBA review |
| Release notes | CICD-06 | Conventional Commits + otomatik changelog |
| Semantic versioning | CICD-07 | `v{major}.{minor}.{patch}` formatı |

### 4.3 Commit Convention

```
feat(leave): add annual leave balance calculation
fix(payroll): correct overtime multiplier for weekends
docs(api): update shift management endpoint docs
chore(deps): bump fastapi to 0.111.0
perf(report): optimize dashboard query with materialized view
```

---

## 5. Artifact Yönetimi

| Artifact | Depolama | Saklama |
|----------|----------|---------|
| Docker image | GitHub Container Registry (GHCR) | Son 20 tag + tüm production tag'ler |
| Coverage raporu | Codecov | Sınırsız |
| Test sonuçları | GitHub Actions artifacts | 30 gün |
| SBOM (Software BOM) | GHCR ile ilişkili | Her release ile |
| Release notes | GitHub Releases | Kalıcı |

---

## 6. Ortam Promosyonu

```
develop → Dev (otomatik) → Staging (release branch) → Prod (tag + onay)
```

| Ortam | Tetikleyici | Onay | Rollback |
|-------|-------------|------|----------|
| Dev | `develop` push | Otomatik | Yeni commit |
| Staging | `release/*` branch | Otomatik | Branch sil |
| Production | `v*` tag | Manuel (GitHub Environment) | Önceki tag deploy |

---

## 7. Başarı Metrikleri

| Metrik | Hedef | Ölçüm |
|--------|-------|-------|
| PR doğrulama süresi | < 10 dakika | GitHub Actions run time |
| Prod deploy süresi (zero-downtime) | < 15 dakika | Tag → healthy |
| Rollback süresi | < 5 dakika | Önceki image pull + up |
| Test coverage (backend) | ≥ %80 | Codecov |
| Test coverage (frontend) | ≥ %70 | Codecov |
| Build başarı oranı | ≥ %95 | GitHub Actions stats |
| Security scan geçme oranı | %100 (critical/high=0) | Snyk + Trivy |
| Deploy frekansı | Haftada 2-3 kez | Release count |
