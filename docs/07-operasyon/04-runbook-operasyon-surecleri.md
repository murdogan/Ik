# Runbook ve Operasyon Süreçleri

Bu doküman, IK Platform için kritik operasyon senaryolarında izlenecek runbook'ları ve genel operasyon prensiplerini tanımlar.

## 1. Runbook prensipleri

Her runbook şu bilgileri içermelidir:

- Tetikleyen alert veya belirti.
- Etki ve severity.
- İlk 5 dakika aksiyonları.
- Teşhis adımları.
- Containment adımları.
- Recovery adımları.
- Müşteri iletişimi gereksinimi.
- Postmortem gereksinimi.

## 2. Genel incident ilk aksiyonu

1. Alert doğrulanır.
2. Etki kapsamı belirlenir: servis, tenant, kullanıcı sayısı.
3. Severity atanır.
4. Incident kanalı açılır.
5. Son deploy ve config değişiklikleri kontrol edilir.
6. Müşteri etkisi varsa iletişim sahibi atanır.
7. Containment uygulanır.
8. Recovery sonrası postmortem açılır.

## 3. Auth outage runbook

Belirtiler:

- Login hata oranı artışı.
- Token refresh hataları.
- SSO provider hatası.

İlk aksiyonlar:

- Auth endpoint 5xx ve latency dashboard kontrol edilir.
- Son deploy incelenir.
- DB/Redis bağlantısı kontrol edilir.
- SSO kaynaklıysa password login fallback policy değerlendirilir.
- Refresh reuse spike varsa güvenlik incident'e yükseltilir.

Recovery:

- Feature flag rollback.
- Önceki image rollback.
- SSO connector disable/fallback.
- Etkilenen session family revoke.

## 4. DB high CPU / slow query runbook

Belirtiler:

- API latency artışı.
- DB CPU yüksek.
- Connection pool waiting artışı.

Teşhis:

- Top slow queries.
- Lock bekleyen sorgular.
- Son migration/deploy.
- Tenant bazlı ağır sorgu.
- Rapor/export job etkisi.

Aksiyon:

- Ağır job durdurulur veya queue limitlenir.
- Problemli query kill edilir.
- Feature flag kapatılır.
- Gerekirse rollback.
- Index/migration fix PR açılır.

## 5. Queue backlog runbook

Belirtiler:

- Queue depth veya oldest age artışı.
- Worker offline.
- Rapor/export gecikmesi.

Aksiyon:

- Worker pod durumu kontrol edilir.
- DLQ ve task hata oranı incelenir.
- İlgili queue scale edilir.
- Hatalı task tipi disable edilir.
- Tenant noisy-neighbor varsa concurrency düşürülür.

## 6. PDKS import failure runbook

Belirtiler:

- Import job failed.
- Hatalı satır oranı yüksek.
- Vendor API timeout.

Aksiyon:

- Staging import raporu incelenir.
- File hash/format doğrulanır.
- Mapping değişiklikleri kontrol edilir.
- Commit yapılmadıysa tekrar dry-run.
- Commit sonrası problem varsa data correction prosedürü uygulanır.

## 7. Sensitive export alert runbook

Belirtiler:

- Olağan dışı export sayısı.
- Hassas alan içeren export.
- Gece/sıra dışı kullanıcı davranışı.

Aksiyon:

- Export actor, scope, IP, tenant incelenir.
- Kullanıcının rol ve permission geçmişi kontrol edilir.
- Gerekirse session revoke.
- Tenant admin bilgilendirme gereksinimi değerlendirilir.
- Security incident seviyesine göre postmortem açılır.

## 8. Cross-tenant alert runbook

Bu SEV1 adayıdır.

İlk aksiyon:

- İlgili endpoint/feature flag kapatılır.
- Etkilenen token/sessionlar revoke edilir.
- Son deploy rollback değerlendirilir.
- Log, trace, audit snapshot alınır.
- Etkilenen tenant ve veri kategorisi belirlenir.
- Hukuk/DPO süreci başlatılır.

## 9. Secret leak runbook

Aksiyon:

1. Secret kaynağı doğrulanır.
2. Secret hemen rotate edilir.
3. Eski secret revoke edilir.
4. Etki penceresi belirlenir.
5. Audit/log taraması yapılır.
6. Repo geçmişi ve build artifact kontrol edilir.
7. Gerekirse müşteri/otorite bildirimi değerlendirilir.

## 10. AI provider outage runbook

Belirtiler:

- AI request failure rate artışı.
- Provider timeout.
- Kota/maliyet limit hatası.

Aksiyon:

- AI feature flag tenant bazında kapatılır veya degraded mode açılır.
- Kullanıcıya fallback mesajı gösterilir.
- Queue retry storm engellenir.
- Provider status kontrol edilir.
- Alternatif model/provider varsa routing değiştirilir.

## 11. Backup failed / restore runbook

Backup failed:

- Alert doğrulanır.
- Son başarılı backup zamanı not edilir.
- Storage/KMS/credential kontrol edilir.
- Manuel backup tetiklenir.
- RPO riski varsa SEV yükseltilir.

Restore tatbikatı:

- Staging/izole ortam hazırlanır.
- Backup restore edilir.
- Migration version doğrulanır.
- Smoke test çalıştırılır.
- Sonuç raporu kaydedilir.

## 12. Postmortem standardı

Postmortem şu alanları içerir:

- Özet.
- Etki süresi.
- Etkilenen tenant/kullanıcı sayısı.
- Timeline.
- Root cause.
- Detection gap.
- Response gap.
- Kalıcı aksiyonlar.
- Sahip ve tarih.

## 13. Kabul kriterleri

- Kritik alertlerin runbook linki vardır.
- SEV1/SEV2 incident akışı tanımlıdır.
- Cross-tenant ve secret leak runbookları ayrı yazılmıştır.
- Backup restore prosedürü test edilebilir durumdadır.
- Postmortem standardı nettir.

## 14. İlgili dokümanlar

- [Observability, SLO ve Alarm](02-observability-slo-alarm.md)
- [DevOps, Ortamlar ve Sürüm Yönetimi](01-devops-ortamlar-surum-yonetimi.md)
- [Güvenlik Mimarisi, OWASP ve Incident](../06-guvenlik-uyum/03-guvenlik-mimarisi-owasp-incident.md)
