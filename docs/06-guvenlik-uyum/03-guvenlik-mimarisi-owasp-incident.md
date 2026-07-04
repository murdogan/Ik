# Güvenlik Mimarisi, OWASP ve Incident Response

Bu doküman, IK Platform'un uygulama, API, veri, altyapı ve operasyon güvenlik kontrollerini; OWASP eşlemesini ve incident response yaklaşımını tanımlar.

## 1. Güvenlik kontrol kataloğu

| Alan | Kontrol |
|---|---|
| Uygulama | OWASP ASVS ve OWASP API Security Top 10'a göre tasarım |
| API | AuthN/AuthZ, BOLA testleri, schema validation, rate limit |
| Veri | Encryption at rest, field-level encryption, masking |
| Secret | Secret manager, rotation, no secret in repo/log |
| Audit | Audit log ve security event log |
| Tenant | RLS, tenant-aware cache/search/storage |
| CI/CD | SAST, dependency scan, container scan, secret scan |
| Runtime | WAF, network policy, least privilege |
| Admin | MFA, break-glass, just-in-time access |

## 2. OWASP API Top 10 eşlemesi

| Risk | Kontrol |
|---|---|
| Broken Object Level Authorization | Her object access'te tenant + scope + ABAC kontrolü |
| Broken Authentication | MFA, lockout, refresh rotation, session revoke |
| Broken Object Property Level Authorization | Field-level permission ve response filtering |
| Unrestricted Resource Consumption | Rate limit, pagination, async export |
| Broken Function Level Authorization | Endpoint permission dependency |
| Sensitive Business Flows | Payroll/export/role change için step-up ve approval |
| SSRF | URL allowlist, metadata IP blokajı, egress kontrolü |
| Security Misconfiguration | Hardened baseline, config scan |
| Improper Inventory Management | OpenAPI catalog ve diff kontrolü |
| Unsafe Consumption of APIs | Connector sandbox, timeout, schema validation |

## 3. Threat model özeti

| Aktör | Risk | Kontrol |
|---|---|---|
| Dış saldırgan | Credential stuffing, DDoS | Rate limit, MFA, WAF |
| Kötü niyetli tenant kullanıcısı | Yetki dışı çalışan/maaş erişimi | Scope, field permission, RLS |
| Müşteri iç kullanıcısı | Toplu export sızıntısı | Export permission, audit, watermark |
| Platform operasyonu | Müşteri verisine uygunsuz erişim | Break-glass, JIT, immutable audit |
| Tedarik zinciri | Zararlı paket/imaj | SCA, SBOM, image scan, protected branch |

## 4. Şifreleme ve key yönetimi

| Veri | Kontrol |
|---|---|
| DB at rest | Managed disk encryption veya eşdeğer |
| Hassas alan | Envelope encryption |
| Object storage | SSE-KMS veya provider encryption |
| In transit | TLS 1.2+ / TLS 1.3 tercih |
| Backup | Şifreli, ayrı key, restore testi |
| JWT signing | `kid` ile rotation destekli key yönetimi |

Hassas alanlar için önerilen sınıflar:

- TCKN/YKN/pasaport.
- IBAN.
- Maaş/bordro.
- Sağlık/engellilik.
- Performans ve disiplin notları.
- AI output ve prompt kayıtları.

## 5. Secret management

| Secret | Yönetim |
|---|---|
| DB credential | Secret manager, rotation |
| JWT private key | KMS/HSM veya güvenli secret store |
| API keys | Hash/encrypted storage, masked UI |
| Webhook secrets | Per endpoint HMAC secret |
| Provider tokenları | Connector vault ve scope limit |
| SMTP/SMS secret | Tenant bazlı veya platform secret |

Kurallar:

- Secret repo içinde tutulmaz.
- Secret log'a yazılmaz.
- Secret UI'da bir kez gösterilir veya maskelenir.
- Rotation prosedürü olmalıdır.

## 6. Audit ve security event log

| Log tipi | İçerik |
|---|---|
| Audit log | İş olayları ve veri değişiklikleri |
| Security event | Auth, risk, suspicious access |
| Access log | HTTP metadata, PII redacted |
| Admin log | Tenant/security config değişiklikleri |
| AI log | Model, prompt version, review status |
| Export log | Dosya hash, actor, zaman, kapsam |

Security event örnekleri:

| Event | Severity | Otomatik aksiyon |
|---|---|---|
| `auth.refresh.reuse_detected` | High | Session family revoke |
| `tenant.cross_access_denied` | High | Security alert |
| `sensitive_export.generated` | Medium | Audit + notification |
| `break_glass.started` | Critical | Müşteri/security bildirimi |
| `sso.config.changed` | High | Admin notification |
| `ai.prompt_injection.detected` | Medium | Output block/review |

## 7. Secure SDLC

| Aşama | Kontrol |
|---|---|
| Tasarım | Threat model ve privacy impact |
| Geliştirme | Secure coding, code review |
| CI | SAST, dependency scan, secret scan |
| Test | API authz/BOLA, tenant isolation |
| Release | Migration ve config review |
| Operasyon | Vulnerability management, patch SLA |

## 8. Dosya yükleme güvenliği

Dosya yükleme HR ürünlerinde kritik yüzeydir.

Kontroller:

- Uzantı allowlist.
- MIME ve magic byte kontrolü.
- Maksimum boyut limiti.
- Malware scan.
- Object storage'a doğrudan yükleme.
- Public inline render yerine güvenli download.
- Presigned URL kısa ömürlü.
- Belge erişimi field/scope permission ile korunur.

## 9. SSRF ve entegrasyon güvenliği

Webhook ve connector URL'leri için:

- HTTPS zorunlu.
- Localhost, private IP, metadata IP blokajı.
- DNS rebinding kontrolü.
- Redirect kısıtı.
- Timeout ve response size limiti.
- Egress allowlist V1/Enterprise.

## 10. Incident response planı

| Aşama | Aksiyon | Hedef |
|---|---|---|
| Detect | Alert, SIEM/log, müşteri bildirimi sinyali | 15 dk triage |
| Triage | Severity, tenant, veri etkisi | 1 saat |
| Contain | Token revoke, feature disable, network block | Kritik: 2 saat |
| Eradicate | Root cause fix, secret rotation | Olaya göre |
| Recover | Servis restore, veri doğrulama | RTO hedefi |
| Notify | Müşteri/DPO/otorite değerlendirmesi | Hukuki süreler |
| Learn | Postmortem, kontrol güncelleme | 5 iş günü |

## 11. Incident severity

| Seviye | Örnek |
|---|---|
| SEV1 | Cross-tenant veri sızıntısı, prod DB compromise |
| SEV2 | Tek tenant hassas veri ifşası, auth bypass |
| SEV3 | Sınırlı kullanıcı veri erişim hatası, provider outage |
| SEV4 | Düşük etkili güvenlik uyarısı |

## 12. Güvenlik testleri

| Test | Sıklık |
|---|---|
| API authz/BOLA automated | Her CI |
| Tenant isolation suite | Her CI |
| Dependency scan | Her PR |
| Container scan | Her build |
| Secret scan | Her PR |
| DAST staging | Haftalık/V1 |
| External pentest | Major release veya yıllık |
| Tabletop exercise | Enterprise öncesi |

## 13. Kabul kriterleri

- Protected endpointler permission olmadan deploy edilmez.
- Cross-tenant negatif testler CI'da koşar.
- Export ve break-glass olayları auditlenir.
- Secret plaintext log ve response'ta görünmez.
- Dosya upload güvenli tarama ve limitlerden geçer.
- Incident severity ve aksiyon akışı tanımlıdır.

## 14. İlgili dokümanlar

- [Kimlik Doğrulama ve Yetkilendirme](01-kimlik-dogrulama-yetkilendirme.md)
- [KVKK, GDPR ve Veri Yönetişimi](02-kvkk-gdpr-veri-yonetisimi.md)
- [API Standartları, OpenAPI ve Webhook](../05-api-veri/02-api-standartlari-openapi-webhook.md)
