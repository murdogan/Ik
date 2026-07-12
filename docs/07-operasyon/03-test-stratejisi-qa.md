# Test Stratejisi ve QA

Bu doküman, IK Platform'un test piramidi, otomasyon katmanları, domain kritik testleri, güvenlik/performance testleri, UAT ve pilot kabul kriterlerini tanımlar.

## 1. Test piramidi

| Katman | Araç örnekleri | Kapsam |
|---|---|---|
| Unit | pytest, vitest | Domain logic, validasyon, saf fonksiyonlar |
| Integration | test DB/Redis, API tests | Repository, service, migration, queue |
| Contract/API | OpenAPI diff, schemathesis | API schema uyumu |
| E2E | Playwright | Kritik kullanıcı akışları |
| Security | SAST/SCA/DAST | OWASP, secret, dependency |
| Performance | k6 | Login, rapor, import, API yükü |

Hedef: Kritik domain logic yüksek kapsam, UI/E2E daha az ama kritik akış odaklı olmalıdır.

### 1.1 Veritabanı test hatları

Varsayılan komut hızlı SQLite unit/API/migration testlerini çalıştırır. PostgreSQL
bağlantısı gerektiren testler `postgres` marker'ıyla opt-in tutulur:

```bash
uv run pytest -q
```

Gerçek PostgreSQL 16+ hattının komutu şöyledir; yönetim DSN'i disposable bir test cluster'ına ait
olmalıdır:

```bash
docker compose up -d --wait postgres
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres uv run pytest -q -m postgres
```

`docker compose` satırı yalnız local service başlangıç örneğidir. Tam lane F1C/F1D capability
rollerini cluster-global oluşturup/harden eder ve password saklamayan geçici migration-owner login'i
ile bağlanır; bu nedenle test cluster'ının host authentication'ı bu geçici role izin vermelidir.
Shared/operational cluster kullanılmaz ve örnek service bu koşul doğrulanmadan tam lane kanıtı
sayılmaz. F1E recorded gate'i disposable, local-trust PostgreSQL 17.10 cluster'ında çalıştırılmıştır.

`IK_TEST_DATABASE_URL` bu hat için zorunludur. Fixture verilen yönetim URL'si üzerinden her
PostgreSQL testi için izole ve benzersiz bir geçici veritabanı oluşturur, Alembic ve API testini
orada çalıştırır ve sonunda veritabanını siler. Bu function-scope izolasyon, retained archive veya
idempotency verisinin sonraki destructive migration testini collection sırasına bağlı biçimde
bozmasını engeller. Capability rolleri downgrade'de bilinçli olarak korunduğu için database
izolasyonu cluster izolasyonunun yerine geçmez. PostgreSQL hattı en az şunları kanıtlar:

- Alembic `base → head → base` upgrade/downgrade ve model metadata drift kontrolü.
- PostgreSQL UUID/timestamp tipleri ile index, unique, foreign-key ve check constraint davranışları.
- Tenant relational-integrity preflight'ının orphan/cross-tenant tespiti, composite foreign
  key'lerin validation durumu, servis bypass eden doğrudan write negatifleri ve valid veri koruyan
  expand-contract upgrade/downgrade akışı.
- Concurrent employee create için tek winner ve kararlı conflict mapping'i, gerçek DB lock hata
  mapping'i, leave kararlarında tam bir terminal winner, aynı idempotency key ile tek resource
  replay'i, employee archive/history `RESTRICT` davranışı ve unsafe downgrade reddi.
- Mevcut tenant-scoped API ve OpenAPI operasyon setinin PostgreSQL üzerindeki uyumluluğu.
- F1D `tenant_feature_flags` catalog/backfill/check, FORCE RLS, app tenant-scoped SELECT, platform
  SELECT/INSERT/UPDATE, no-DELETE privilege matrisi; raw tenant A/B erişimi ve platform-to-HR denial.
- Platform tenant metadata query'sinin yalnız `tenants` projection'ı kullanması; configured
  `limits.active_employees` alanının employee usage/count sorgusuna dönüşmemesi.
- Pool/bağlantı yaşam döngüsü ile `statement_timeout` ve PostgreSQL 16 uyumlu
  `idle_in_transaction_session_timeout` ayarları.
- P0F disposable fixture'ında 10,000 employee + 5,000 leave seed'i sonrası selective search ve
  deterministic employee/leave keyset sorgularının `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
  index/row-bound kanıtları.

PostgreSQL'e özgü bir iddia SQLite sonucu ile geçmiş sayılmaz. FastAPI lifespan runtime engine
ve sessionmaker'ın sahibidir; shutdown testi engine dispose davranışını da kapsar.

Repo içinde PostgreSQL service'ini tarif eden
`docs/09-uygulama/templates/backend-ci.yml` şablonu vardır; aktif `.github/workflows` dosyası
yoktur. Bu nedenle P0G kanıtı lokal gerçek PostgreSQL çalıştırmasıdır, aktif PR CI lane'i gibi
sunulmaz. Workflow aktivasyonu repo yönetimi/supervisor işidir.

Historical Phase-0 OpenAPI gate'i `backend/tests/contracts/phase0_openapi_contract.json`, F1A gate'i
`backend/tests/contracts/f1a_openapi_contract.json` manifestinde top-level metadata, her operasyon
ve her component schema için canonical SHA-256 snapshot tutar. F1B historical envelope diff'i ve
historical F1D additive diff'i ayrı snapshot/assertion olarak korunur; önceki manifestler overwrite
edilmez. F1E snapshot'ı yalnız exact on Faz 1 operation'ındaki
`x-required-principal: platform|tenant` metadata diff'ini ekler; component ve top-level digest'leri
korur. Current assertions 24 generated path/method operation registry kontrolü, iki doküman tablosu
ve runtime `/openapi.json` dahil 25 endpoint smoke coverage ile tamamlanır.
Contract değişikliği ancak intentional diff ve aynı commit'teki snapshot/doküman güncellemesiyle
kabul edilir. F1E sonucu final contract/security/smoke komutları çalışmadan `passed` sayılmaz.

P0F query-plan prosedürünü kanıt satırıyla tek başına çalıştırmak için:

```bash
IK_TEST_DATABASE_URL=postgresql+asyncpg://ik:ik@127.0.0.1:5432/postgres \
  uv run pytest -q -m postgres \
  backend/tests/integration/test_postgresql_p0f_performance.py -s
```

Test elapsed-time'ı donanıma bağlı olduğu için hard CI bütçesi yapmaz; query count, returned row
bound, cursor `rows removed` sınırı ve kullanılan kritik index adları regression gate'tir. Yakalanan timing/buffer baseline'ı
`docs/09-uygulama/12-phase-0-query-performance-baseline.md` içinde tutulur.

## 2. Kritik E2E akışları

- Yeni identity invite → activation → login.
- Mevcut identity invite → current-password membership kabulü → çoklu kurum seçimi.
- Forgot/reset password known/unknown aynı request response'u, fragment scrub, expiry/replay ve
  tenant/platform session revoke.
- Tenant email/password login + MFA hazırlığı; kurum kodu alanı yok.
- Personel oluşturma.
- Belge yükleme ve görüntüleme.
- İzin talebi → onay → bakiye kontrolü.
- Yönetici onay kuyruğu.
- PDKS import dry-run.
- Rapor export.
- Rol atama ve yetki etkisi.
- Hassas alan maskeleme.
- Çalışan portalı mobil görünüm.
- Aday başvurusu V1.
- Webhook test event V1.

## 3. Test verisi yönetimi

| Konu | Standart |
|---|---|
| Fabrika | Her model için factory |
| Tenant fixture | En az iki tenant ile izolasyon testi |
| Determinizm | Sabit seed ve zaman dondurma |
| Staging veri | Anonimleştirilmiş/sentetik |
| PII | Test ortamlarında gerçek kişisel veri yasak |
| Mevzuat | Test parametre setleri versiyonlu |

## 4. Domain kritik testleri

### 4.1 Yetkilendirme

- Her protected endpoint permission metadata taşır.
- Role × scope × endpoint matrisi test edilir.
- Tenant A token'ı Tenant B kaydını göremez.
- Yetkisiz kaynak için 404/403 politikası tutarlı olmalıdır.
- Hassas alanlar exportta da maskelenir.

### 4.2 İzin

- Kıdem yılına göre hak ediş.
- Yıl devri/devir tavanı.
- Negatif bakiye policy.
- Resmi tatil ve hafta sonu hesapları.
- Onay iptalinde bakiye iadesi.

### 4.3 PDKS/Puantaj

- Duplicate event.
- Eksik giriş/çıkış.
- Gece vardiyası.
- Hatalı device user mapping.
- Kilitli dönem değişmezliği.

### 4.4 Bordro/export

MVP'de bordro motoru yerine export doğruluğu önceliklidir.

Testler:

- Pay component mapping.
- Cost center mapping.
- Banka dosyası formatı.
- Kilitli dönem export.
- Maker-checker onay.

V1 yerleşik bordro motorunda golden dataset zorunlu olur.

## 5. RLS ve tenant izolasyonu testleri

- Tenant tablosunda `tenant_id` bulunur.
- RLS veya tenant guard eksik tablo CI'da yakalanır.
- Feature rollout tablosu fixed catalog/check, FORCE RLS ve exact role privilege matrisi dışında
  bırakılamaz; SQLite privilege/RLS kanıtı sayılmaz.
- App katmanı bypass edilerek DB seviyesinde cross-tenant erişim test edilir.
- Tenant-owned foreign key'ler için yanlış `(tenant_id, foreign_id)` kombinasyonu her ilişki ve
  named constraint bazında gerçek PostgreSQL'de reddedilir.
- Cache key tenant prefix içerir.
- Worker fake her job'da non-zero tenant ve explicit `JobOrigin.REQUEST|SYSTEM` ister. Request-origin
  context'siz kurulamaz; context/job A↔B uyuşmazlığı enqueue öncesi reddedilir. System origin request
  context kabul etmez. Gerçek provider için authenticated transport ve transaction-local DB tenant
  binding ayrıca zorunludur.
- Object storage pre-signed URL tenant kontrolü ister.
- Search/vector sonuçları tenant dışına çıkmaz.

## 6. Güvenlik testleri

| Test | Kapsam |
|---|---|
| Secret scan | Repo içinde secret yok |
| SAST | Güvenlik anti-patternleri |
| SCA | Dependency vulnerability |
| API fuzz | Şema dışı ve sınır değerler |
| DAST | Staging üzerinde baseline tarama |
| BOLA | Object-level authorization |
| File upload | EICAR, çift uzantı, boyut limitleri |
| SSRF | Webhook/connector URL kontrolleri |
| Webhook | HMAC, replay, timestamp |

## 7. Performance testleri

| Senaryo | Hedef |
|---|---|
| Login fırtınası | p95 < 500 ms, hata düşük |
| Employee list read | p95 < 300 ms hedef |
| İzin onayı | p95 < 800 ms hedef |
| Rapor üretimi | p95 < 10 sn |
| PDKS import | 100k satır async işlenebilir |
| Webhook patlaması | DLQ kalıcı artmaz |
| Soak test | Bellek/connection leak yok |

## 8. Regression ve smoke

| Paket | Tetik |
|---|---|
| Hedef PR hızlı paket | SQLite unit/API + contract + smoke; aktif workflow henüz yok |
| Hedef PR PostgreSQL paket | Gerçek DB API + migration upgrade/downgrade/drift; aktif workflow henüz yok |
| Gece tam paket | E2E, security, performance subset |
| Deploy sonrası smoke | Prod sentetik tenant |
| Release regresyonu | Staging bake + kritik flows |

Flaky test politikası:

- E2E max 2 retry.
- Sık kırılan test quarantine olur.
- Quarantine 1 sprint içinde düzeltilir veya kaldırılır.

## 9. UAT ve pilot kabul

GA/pilot çıkış kriterleri:

- Açık P1/P2 hata yok.
- UAT senaryolarının en az %95'i geçti.
- Security kritik/yüksek bulgu yok veya süreli exception var.
- Veri migrasyonu doğrulandı.
- Kritik SLO'lar staging'de kabul edildi.
- Rollback ve backup prosedürü hazır.

## 10. Definition of Done

- Yeni davranış unit test içerir.
- API değiştiyse OpenAPI güncellenir.
- Yetki değiştiyse permission matrix güncellenir.
- Migration varsa migration smoke geçer.
- PostgreSQL'e özgü persistence/migration değişikliğinde `postgres` hattı geçer.
- Kritik akış etkileniyorsa E2E güncellenir.
- Security taraması temizdir.
- Docs ilgili yerde güncellenmiştir.

## 11. İlgili dokümanlar

- [DevOps, Ortamlar ve Sürüm Yönetimi](01-devops-ortamlar-surum-yonetimi.md)
- [Observability, SLO ve Alarm](02-observability-slo-alarm.md)
- [Kimlik Doğrulama ve Yetkilendirme](../06-guvenlik-uyum/01-kimlik-dogrulama-yetkilendirme.md)
