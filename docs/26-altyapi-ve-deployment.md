# 26 — Altyapı & Deployment

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Sunucu mimarisi, Docker/Kubernetes yaklaşımı, ortamlar, ağ yapısı, gözlemlenebilirlik, yedekleme ve yayın topolojisi  
> **Faz:** Faz 6  
> **Referans:** 05-teknoloji-secimi.md, 06-sistem-mimarisi.md

---

## 1. Hedef Mimari

Sistem modüler monolith yaklaşımıyla tek repoda geliştirilir; dağıtım katmanında web, API, worker, Redis, PostgreSQL ve MinIO servisleri ayrıştırılır. İlk aşamada Docker tabanlı dağıtım tercih edilir; ölçek ihtiyacına göre Kubernetes geçişi planlanabilir.

---

## 2. Ortamlar

| Ortam | Amaç | URL Kalıbı | Deploy Tetikleyici |
|-------|------|------------|---------------------|
| Local | Geliştirici makinesi | `localhost:3000` / `:8000` | Manuel (`docker compose up`) |
| Dev | Entegre geliştirme | `dev.ikys.internal` | `develop` branch push |
| Staging | Yayın öncesi doğrulama + UAT | `staging.ikys.internal` | `release/*` branch |
| Prod | Canlı sistem | `app.ikys.com` / `{tenant}.ikys.com` | `main` tag (manuel onay) |

### 2.1 Ortam Farkları

| Parametre | Local | Dev | Staging | Prod |
|-----------|-------|-----|---------|------|
| DB | PostgreSQL (Docker) | PostgreSQL (Docker) | PostgreSQL (Managed) | PostgreSQL (Managed HA) |
| Redis | Tek instance | Tek instance | Tek instance | Redis Sentinel (3 node) |
| MinIO | Tek instance | Tek instance | Tek instance | MinIO Distributed (4 node) |
| HTTPS | Hayır | Self-signed | Let's Encrypt | Managed cert |
| Debug mode | Evet | Evet | Hayır | Hayır |
| Seed data | Test verisi | Test verisi | Üretim benze | — |
| Log seviyesi | DEBUG | DEBUG | INFO | WARNING |
| Replika sayısı | 1 | 1 | 1 | 2+ (auto-scale) |

---

## 3. Servisler ve Kaynak Boyutlandırma

| Servis | Teknoloji | Rol | CPU | RAM | Replika (Prod) |
|--------|-----------|-----|-----|-----|-----------------|
| Web | Next.js 15 (Node 20) | Kullanıcı arayüzü, SSR | 0.5 core | 512 MB | 2 |
| API | FastAPI (Gunicorn, 4 worker) | İş kuralları ve REST API | 1 core | 1 GB | 2 |
| Worker | Celery (4 concurrent) | Arka plan işler, zamanlanmış görevler | 1 core | 1 GB | 2 |
| Beat | Celery Beat | Cron scheduler | 0.25 core | 256 MB | 1 (singleton) |
| DB | PostgreSQL 17 | Ana veri deposu | 2 core | 4 GB | 1 primary + 1 replica |
| Cache/Queue | Redis 7 | Cache, session, Celery broker | 0.5 core | 1 GB | 3 (Sentinel) |
| Object Storage | MinIO | Belgeler, export dosyaları | 0.5 core | 512 MB | 4 (distributed) |
| Reverse Proxy | Nginx 1.27 | TLS, yönlendirme, rate limiting | 0.25 core | 256 MB | 2 |
| Monitoring | Prometheus + Grafana | Metrik toplama ve dashboard | 0.5 core | 512 MB | 1 |
| Log | Loki + Promtail | Merkezi log toplama | 0.5 core | 512 MB | 1 |

**Toplam Prod Kaynak (minimum):** ~12 CPU core, ~16 GB RAM

---

## 4. Docker Compose Yapısı

### 4.1 Servis Topolojisi

```yaml
# docker-compose.prod.yml (özet)
version: "3.9"

services:
  nginx:
    image: nginx:1.27-alpine
    ports: ["443:443", "80:80"]
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on: [web, api]
    restart: always

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    env_file: .env.prod
    expose: ["3000"]
    restart: always

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file: .env.prod
    expose: ["8000"]
    command: >
      gunicorn core.asgi:application
      -k uvicorn.workers.UvicornWorker
      -w 4 --bind 0.0.0.0:8000
    depends_on: [db, redis]
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file: .env.prod
    command: celery -A core worker -l info -c 4
    depends_on: [db, redis]
    restart: always

  beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file: .env.prod
    command: celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    depends_on: [db, redis]
    restart: always

  db:
    image: postgres:17-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    env_file: .env.prod
    expose: ["5432"]
    restart: always
    shm_size: "256mb"

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redisdata:/data
    expose: ["6379"]
    restart: always

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    volumes:
      - miniodata:/data
    env_file: .env.prod
    expose: ["9000", "9001"]
    restart: always

volumes:
  pgdata:
  redisdata:
  miniodata:
```

### 4.2 Nginx Konfigürasyonu (Özet)

```nginx
upstream api_backend {
    server api:8000;
}

upstream web_frontend {
    server web:3000;
}

server {
    listen 443 ssl http2;
    server_name app.ikys.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.3;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # API
    location /api/ {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        client_max_body_size 20M;

        # Rate limiting
        limit_req zone=api burst=20 nodelay;
    }

    # Frontend
    location / {
        proxy_pass http://web_frontend;
        proxy_set_header Host $host;
    }

    # Static / media
    location /media/ {
        proxy_pass http://minio:9000;
    }
}
```

---

## 5. Deployment Yaklaşımı

### 5.1 Deploy Pipeline

```
                       ┌─────────────┐
                       │  Git Tag     │
                       │  (v1.2.3)    │
                       └──────┬──────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  CI Build & Test │
                    │  (GitHub Actions)│
                    └────────┬─────────┘
                             │
                    ┌────────┼────────┐
                    ▼        ▼        ▼
              Build API   Build Web  Build Worker
              Image       Image      Image
                    │        │        │
                    └────────┼────────┘
                             │
                    ┌────────▼────────┐
                    │  Registry Push  │
                    │  (GHCR / ECR)   │
                    └────────┬────────┘
                             │
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
          Staging        Prod (onay)    Rollback
          auto-deploy    manual gate    (1 click)
```

### 5.2 Deploy Adımları

| Adım | Komut / Aksiyon | Açıklama |
|------|-----------------|----------|
| 1 | `docker compose pull` | Yeni image'ları çek |
| 2 | `docker compose run api python manage.py migrate --check` | Migration kontrolü |
| 3 | `docker compose run api python manage.py migrate` | DB migration |
| 4 | `docker compose up -d --remove-orphans` | Servisleri güncelle |
| 5 | Health check bekle | `/api/health` endpoint 200 |
| 6 | Smoke test | Kritik endpoint'lerin çalışması |

### 5.3 Rollback

| Yöntem | Açıklama |
|--------|----------|
| Image rollback | Önceki tag'e dönüş: `docker compose pull && docker compose up -d` |
| DB rollback | `python manage.py migrate {app} {previous_migration}` |
| Hızlı geri dönüş | Staging'de test edilmiş önceki sürüm <5 dk'da deploy |

### 5.4 Health Check Endpoint'leri

| Endpoint | Kontrol | Kullanım |
|----------|---------|----------|
| `GET /api/health` | API çalışıyor | Liveness probe |
| `GET /api/health/ready` | DB + Redis + MinIO bağlantısı | Readiness probe |
| `GET /api/health/detail` | Bağımlılık detay (sadece internal) | Monitoring |

**GET /api/health/detail Response:**
```json
{
  "status": "healthy",
  "version": "1.2.3",
  "uptime_seconds": 86400,
  "checks": {
    "database": {"status": "ok", "latency_ms": 2},
    "redis": {"status": "ok", "latency_ms": 1},
    "minio": {"status": "ok", "latency_ms": 5},
    "celery": {"status": "ok", "active_workers": 4}
  }
}
```

---

## 6. Monitoring ve Gözlemlenebilirlik

### 6.1 Metrik Toplama (Prometheus)

| Metrik | Tip | Açıklama | Alarm Eşiği |
|--------|-----|----------|-------------|
| `http_requests_total` | Counter | Toplam HTTP istek | — |
| `http_request_duration_seconds` | Histogram | İstek süresi | p95 > 500ms |
| `http_errors_total` | Counter | 5xx hataları | > 10/dk |
| `db_query_duration_seconds` | Histogram | DB sorgu süresi | p95 > 200ms |
| `celery_tasks_active` | Gauge | Çalışan task sayısı | — |
| `celery_tasks_failed_total` | Counter | Başarısız task | > 5/saat |
| `celery_queue_length` | Gauge | Kuyruk derinliği | > 100 |
| `redis_memory_used_bytes` | Gauge | Redis bellek | > %80 |
| `postgres_connections_active` | Gauge | Aktif DB bağlantı | > %80 pool |
| `minio_disk_used_bytes` | Gauge | Disk kullanımı | > %85 |

### 6.2 Grafana Dashboard'ları

| Dashboard | İçerik |
|-----------|--------|
| Sistem Özet | CPU, RAM, disk, network tüm servisler |
| API Performans | Request rate, latency (p50/p95/p99), error rate, status code dağılımı |
| Celery İzleme | Task throughput, kuyruk derinliği, ortalama süre, başarısızlık oranı |
| Veritabanı | Aktif bağlantılar, slow query sayısı, replication lag, tablo boyutları |
| İK İş Metrikleri | Aktif kullanıcı, izin talep/gün, bordro çalışma süresi |

### 6.3 Alarm Kuralları

| Alarm | Koşul | Kanal | Seviye |
|-------|-------|-------|--------|
| API Down | Health check 3 kez başarısız | Slack + SMS | P1 |
| Yüksek hata oranı | 5xx > %5 (5 dk pencere) | Slack | P2 |
| Yavaş API | p95 latency > 1s (10 dk) | Slack | P3 |
| Worker backlog | Kuyruk > 500 (15 dk) | Slack | P2 |
| Disk doluluk | > %85 | Slack + e-posta | P2 |
| DB connection pool | > %80 dolu | Slack | P2 |
| Replication lag | > 30s | Slack + SMS | P1 |
| SSL sertifika | < 14 gün kala | E-posta | P3 |

### 6.4 Log Yönetimi

| Bileşen | Log Formatı | Hedef |
|---------|-------------|-------|
| API | JSON structured (timestamp, level, request_id, user_id, msg) | stdout → Promtail → Loki |
| Worker | JSON structured (task_id, task_name, status, duration) | stdout → Promtail → Loki |
| Nginx | Combined + request_id | Log dosyası → Promtail → Loki |
| Audit | DB tablosu (audit_logs) | PostgreSQL |

---

## 7. Yedekleme Stratejisi

| Parametre | Değer |
|-----------|-------|
| Tam yedek | Günlük 02:00 (pg_dump + gzip + AES-256) |
| WAL arşivi | Sürekli (PITR için) |
| Yedek hedefi | Farklı AZ + S3 uyumlu bucket (cross-region) |
| Yedek saklama | 30 gün günlük, 12 ay aylık snapshot |
| RPO | ≤ 1 saat (WAL tabanlı) |
| RTO | ≤ 4 saat |
| MinIO yedek | MinIO mirror komutu → farklı bucket (günlük) |
| Redis yedek | RDB snapshot (6 saatte bir) → S3 |
| Geri dönüş testi | Otomatik: her hafta staging'de restore + doğrulama |

### 7.1 Yedek Doğrulama Süreci

```
Cron (Pazar 04:00) → pg_restore → staging DB
    │
    ▼
Otomatik test suite çalıştır (temel CRUD)
    │
    ├── Başarılı → Slack #ops: "✅ Backup verify OK"
    └── Başarısız → Slack #ops: "🚨 Backup verify FAILED" → P1 alarm
```

---

## 8. Ölçeklendirme Stratejisi

| Bileşen | Yatay Ölçeklendirme | Dikey Ölçeklendirme |
|---------|---------------------|---------------------|
| API | Nginx upstream'e replika ekle | Worker sayısı arttır |
| Web | Replika ekle | — |
| Worker | Celery worker sayısı arttır | Concurrency arttır |
| DB | Read replica ekle (okuma) | CPU/RAM arttır |
| Redis | Redis Cluster (sharding) | maxmemory arttır |

### 8.1 Ölçeklendirme Tetikleyicileri

| Metrik | Eşik | Aksiyon |
|--------|------|---------|
| API CPU | > %70 (5 dk) | +1 replika |
| Worker kuyruk | > 200 (10 dk) | +1 worker |
| DB CPU | > %80 (10 dk) | Read replica ekle |
| Aktif kullanıcı | > 1000 eşzamanlı | API + Web replika arttır |

---

## 9. SSL / Domain Yapısı

| Domain | Kullanım | Sertifika |
|--------|----------|-----------|
| `app.ikys.com` | Ana uygulama | Managed / Let's Encrypt |
| `api.ikys.com` | API (opsiyonel ayrı domain) | Managed / Let's Encrypt |
| `{tenant}.ikys.com` | Tenant alt domain (opsiyonel) | Wildcard cert |
| `cdn.ikys.com` | Statik dosyalar (opsiyonel) | CloudFlare |
