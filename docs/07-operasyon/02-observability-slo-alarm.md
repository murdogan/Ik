# Observability, SLO ve Alarm

Bu doküman, IK Platform'un metrics, logs, traces, SLO, alert ve dashboard yaklaşımını tanımlar.

## 1. Observability mimarisi

Üç ana sinyal kullanılır:

| Sinyal | Araç örneği | Kullanım |
|---|---|---|
| Metrics | Prometheus/Grafana | SLO, alert, kapasite |
| Logs | Loki/ELK | Teşhis ve audit dışı uygulama logları |
| Traces | OpenTelemetry/Tempo | Request zinciri ve latency analizi |
| Errors | Sentry | Backend/web/mobile hata takibi |

## 2. Log standardı

Structured JSON log zorunludur.

| Alan | Zorunlu | Not |
|---|---|---|
| `timestamp` | Evet | UTC |
| `level` | Evet | INFO/WARN/ERROR |
| `service` | Evet | api/web/worker |
| `env` | Evet | local/dev/staging/prod |
| `trace_id` | Evet | Request korelasyonu |
| `tenant_id` | Bağlam varsa | PII değil |
| `user_id_hash` | Opsiyonel | Ham user id yerine hash |
| `event` | Önerilir | `module.entity.action` |
| `duration_ms` | API/job | Performans analizi |
| `error_code` | Hata | API hata kodu |

Log'a yazılması yasak:

- Şifre, token, cookie.
- TCKN/YKN, IBAN.
- Maaş tutarı.
- Sağlık verisi.
- Request/response body tamamı.
- Aday/çalışan tam PII.

## 3. Metrik kataloğu

| Metrik | Amaç |
|---|---|
| `http_requests_total` | Trafik ve hata oranı |
| `http_request_duration_seconds` | API latency |
| `job_duration_seconds` | Worker iş süreleri |
| `queue_depth` | Kuyruk birikmesi |
| `queue_oldest_age_seconds` | Kuyruk gecikmesi |
| `db_connections_active` | DB havuz sağlığı |
| `webhook_deliveries_total` | Webhook başarı/hata |
| `login_attempts_total` | Auth güvenliği |
| `export_jobs_total` | Export aktivitesi |
| `ai_requests_total` | AI kullanım/kota |

## 4. SLO hedefleri

| Alan | Hedef |
|---|---|
| API availability | MVP %99,5; Enterprise %99,9+ |
| API read latency | p95 < 300 ms hedef |
| API write latency | p95 < 800 ms hedef |
| Auth latency | p95 < 500 ms |
| Hazır rapor | p95 < 10 sn |
| Webhook teslim | %99 ilk 15 dk içinde |
| Notification delivery | %95 ilk 5 dk içinde |
| Backup RPO | MVP 4 saat; Enterprise 15 dk-1 saat |

## 5. Alert kuralları

| Alert | Eşik | Severity |
|---|---|---|
| API 5xx spike | 5 dk boyunca %2 üstü | High |
| Auth failure spike | Tenant baseline + anomali | Medium/High |
| Refresh reuse detected | Tek olay | High |
| Queue backlog | 15 dk eşik üstü | Medium |
| Payroll run failure | Tek kritik hata | High |
| Backup failed | Tek hata | Critical |
| DB disk high | %80 uyarı, %90 kritik | High |
| Webhook DLQ growing | Sürekli artış | Medium |
| Cross-tenant denied spike | Tekrarlı olay | Critical |
| AI provider errors | Eşik üstü | Medium |

## 6. Dashboardlar

| Dashboard | Paneller |
|---|---|
| Platform sağlık | API/web/worker/DB/Redis durumu |
| API performans | RPS, p95/p99, 5xx/4xx, yavaş endpointler |
| DB | Bağlantı, yavaş sorgu, lock, disk |
| Kuyruklar | Derinlik, yaş, worker sayısı, DLQ |
| Tenant görünümü | Tenant hata oranı, kullanım, webhook |
| Güvenlik | Login spike, refresh reuse, suspicious access |
| AI | Token, hata, maliyet, review backlog |
| SLO | Error budget, burn rate, trend |

## 7. Synthetic monitoring

Prod smoke/synthetic akışlar sentetik tenant ile çalışmalıdır:

- Login.
- Employee list read.
- Leave request create/cancel.
- Report job start.
- Webhook echo delivery.
- Document metadata read.

## 8. On-call ve incident entegrasyonu

Alert routing:

- SEV1/SEV2: on-call anında bildirim.
- SEV3: çalışma saatlerinde triage.
- SEV4: backlog.

Alert açıklaması şunları içermelidir:

- Etkilenen servis.
- Etkilenen tenant varsa tenant id.
- Grafana linki.
- Son deploy SHA.
- Önerilen runbook linki.

## 9. Kabul kriterleri

- Her response trace/correlation id taşır.
- Uygulama logları JSON ve PII-free olur.
- Kritik SLO'lar dashboard'da izlenir.
- Alertlerin runbook bağlantısı vardır.
- Prod smoke sentetik tenant ile çalışır.
- Backup, queue, auth ve DB için kritik alarm vardır.

## 10. İlgili dokümanlar

- [DevOps, Ortamlar ve Sürüm Yönetimi](01-devops-ortamlar-surum-yonetimi.md)
- [Runbook ve Operasyon Süreçleri](04-runbook-operasyon-surecleri.md)
- [Güvenlik Mimarisi, OWASP ve Incident](../06-guvenlik-uyum/03-guvenlik-mimarisi-owasp-incident.md)
