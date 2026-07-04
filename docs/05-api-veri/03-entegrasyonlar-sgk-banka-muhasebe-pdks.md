# Entegrasyonlar: SGK, Banka, Muhasebe, PDKS ve Diğer Sistemler

Bu doküman, IK Platform'un dış sistemlerle entegrasyon prensiplerini, connector modelini ve öncelikli entegrasyon alanlarını tanımlar.

## 1. Karar özeti

Entegrasyonlar tek tek özel kod parçaları olarak değil, ortak connector framework üzerinden yönetilmelidir.

> Her entegrasyon credential, mapping, schedule, run log, hata listesi, retry ve audit modelini paylaşır.

## 2. Entegrasyon ilkeleri

| İlke | Karar |
|---|---|
| Connector framework | Her entegrasyon ortak yapı kullanır |
| Secret güvenliği | Token/şifre plaintext loglanmaz, UI'da maskeli görünür |
| Idempotency | Import/export tekrar çalıştırılabilir olmalı |
| Staging | Dış veri validasyon sonrası commit edilir |
| Audit | Her import/export run loglanır |
| Data minimization | Dış sisteme sadece gereken veri gönderilir |
| Retry | Geçici hatalar retry, kalıcı hatalar exception |

## 3. Entegrasyon katalogu

| Sistem | Yön | Veri | Faz |
|---|---|---|---|
| E-posta | Outbound | Bildirim, aday iletişimi | MVP |
| SMS | Outbound | OTP, kritik bildirim | MVP/V1 |
| PDKS | Import/API/SFTP | Giriş/çıkış eventleri | V1 |
| Muhasebe/ERP | Export/API | Bordro fişi, maliyet merkezi | V1 |
| Bankalar | Export/SFTP/API | Maaş ödeme dosyası | V1/V2 |
| Takvim | Two-way | Mülakat, izin, vardiya | V1 |
| E-imza | API | Sözleşme ve belge imza | V1 |
| SAML/OIDC | Auth | SSO login | V1/Enterprise |
| SCIM | Provisioning | Kullanıcı ve grup | Enterprise |
| SGK/e-SGK | Export/API hazırlık | İşe giriş/çıkış, bildirge | V2 |
| BI tools | Export/API | Analytics dataset | V2 |
| LMS | API/xAPI | Eğitim ve tamamlama | V2 |

## 4. Connector veri modeli

| Tablo | Amaç | Kritik alanlar |
|---|---|---|
| `integration_connectors` | Connector kaydı | `tenant_id`, `type`, `name`, `status`, `config_schema_version` |
| `integration_credentials` | Secret referansı | `connector_id`, `secret_ref`, `expires_at`, `last_rotated_at` |
| `integration_mappings` | Alan eşleştirme | `source_field`, `target_field`, `transform` |
| `integration_runs` | Çalıştırma kaydı | `direction`, `status`, `started_at`, `finished_at`, `row_count` |
| `integration_errors` | Hata listesi | `run_id`, `severity`, `code`, `message`, `raw_ref` |
| `external_identities` | Dış ID eşleşmesi | `provider`, `external_id`, `local_type`, `local_id` |

## 5. PDKS entegrasyonu

V1 için öncelikli entegrasyondur.

| Konu | Karar |
|---|---|
| Kaynak | CSV, SFTP, API veya manuel upload |
| Mapping | Device user ID / card ID → employee |
| Staging | Import önce staging'e alınır |
| Validasyon | Duplicate event, missing direction, unknown card |
| Commit | Onay sonrası `time_clock_events` yazılır |
| Idempotency | File hash ve event key ile tekrar engellenir |

## 6. Banka entegrasyonu

| Konu | Karar |
|---|---|
| MVP/V1 | Dosya export yaklaşımı |
| V2 | SFTP/API opsiyonu |
| Güvenlik | Şifreli dosya, maker-checker onay |
| Audit | Dosya hash, oluşturan, indiren |
| Veri minimizasyonu | IBAN, tutar, açıklama dışı veri gönderilmez |

## 7. Muhasebe/ERP entegrasyonu

Öncelikli hedef Logo/Netsis/Mikro gibi yerel ekosistemlerle export tabanlı uyumdur.

| Konu | Karar |
|---|---|
| Veri | Cost center, hesap kodu, bordro fişi |
| Format | CSV/XLSX/XML/API opsiyon |
| Mapping | Pay component → GL account |
| Kontrol | Borç/alacak toplamı dengesi |
| Audit | Export hash ve actor |

## 8. SSO ve directory

| Sağlayıcı | Protokol | Faz |
|---|---|---|
| Entra ID | OIDC/SAML/SCIM | V1/Enterprise |
| Okta | OIDC/SAML/SCIM | V1/Enterprise |
| Keycloak | OIDC/SAML | V1 |
| LDAP/AD | LDAP sync | Enterprise |

SSO claim mapping role ve employee eşleşmesini etkileyeceği için IT admin panelinde test aracı gerekir.

## 9. E-imza entegrasyonu

V1 adayıdır.

Kullanım alanları:

- İş sözleşmesi.
- KVKK tebliğ/onay kayıtları.
- Zimmet formu.
- Belge imza akışları.

Kural: E-imza sağlayıcısı değişebilir olmalı; belge metadata platformda, imzalı dosya object storage'da tutulmalıdır.

## 10. Webhook ve dışa veri aktarımı

Webhook payload minimal olmalıdır. Maaş, TCKN, IBAN gibi hassas veri webhook payload içinde taşınmaz.

Dışa veri aktarımı için:

- DPA/yasal dayanak kaydı.
- Alan minimizasyonu.
- Export audit.
- Expiring download link.
- Watermark opsiyonu.

## 11. Kabul kriterleri

- Credential plaintext log/response içinde görünmez.
- Import staging hatalı satırları açıklamalı gösterir.
- Her integration run row count, hata ve süre ile loglanır.
- Connector disable edilince scheduled job durur.
- Dış sisteme PII aktarımı audit ve data minimization ile yapılır.
- Idempotent import/export davranışı test edilir.

## 12. İlgili dokümanlar

- [API Standartları, OpenAPI ve Webhook](02-api-standartlari-openapi-webhook.md)
- [Zaman, Vardiya, PDKS ve Puantaj Modülü](../03-moduller/04-zaman-vardiya-pdks-puantaj.md)
- [Bordro, Ücret ve Mevzuat Modülü](../03-moduller/05-bordro-ucret-mevzuat.md)
