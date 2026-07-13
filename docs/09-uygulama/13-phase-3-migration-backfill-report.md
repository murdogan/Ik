# Phase 3 Migration and Backfill Report

Date: 2026-07-13

Branch: `codex/mvp-phase3-identity-org-until-20260714-0900`

Gate: `P3K combined identity and organization hardening`

## Sonuç

Phase 3A kimlik sınırı ile Phase 3B organizasyon çekirdeği tek doğrusal Alembic zincirinde
doğrulandı. Güncel ve tek head:

```text
0031_p3k_legacy_tenant_auth_boundary (head)
```

`0031` şema tablosu eklemez. Mevcut permission kataloğuna
`leave:manage:tenant` kaydını idempotent ve çakışma kontrollü biçimde ekler; grant yalnız
`hr_director` ve `hr_specialist` rollerine verilir. Employee/manager gibi tenant rolleri bu
yetkiyi miras almaz.

## Doğrulanan migration zinciri

| Revision | P3 kapsamı | Veri/uyumluluk kararı |
|---|---|---|
| `0022_p3a_identity_memberships` | Global identity ve tenant membership ayrımı | Mevcut kullanıcı/üyelik verisi korunarak expand edilir |
| `0023_p3b_email_first_login` | Email-first credential doğrulama | Organizasyon bilgisi başarılı credential doğrulamasından önce açıklanmaz |
| `0024_p3c_organization_selection` | Tek kullanımlık organization-selection işlemi | Seçim transaction/key hash olarak saklanır; replay ve membership drift reddedilir |
| `0025_p3d_platform_authentication` | Ayrı platform session/role realm'i | Platform audience/cookie/principal tenant realm'inden ayrıdır |
| `0026_p3e_identity_checkpoint` | Password recovery ve kimlik checkpoint kapanışı | Davet/aktivasyon ve legacy credential projection korunur |
| `0027_p3f_legal_entities_branches` | Legal entity ve branch/location | Her tenant için deterministic default legal entity backfill edilir |
| `0028_p3g_department_hierarchy` | Department hierarchy ve concurrency fence | Cycle/terminal archive kontrolleri PostgreSQL'de enforce edilir |
| `0029_p3h_position_catalog` | Position/job-title kataloğu | Legacy `employees.position` kaldırılmaz |
| `0030_p3i_employee_assignments` | Structured assignment ve manager scope | Legacy department/position stringlerinden deterministic expand-contract backfill yapılır |
| `0031_p3k_legacy_tenant_auth_boundary` | Legacy HR route permission kapanışı | Yeni HR-only leave mutation permission'ı; mevcut route/payload contract'ı korunur |

## Populated backfill kanıtı

Gerçek PostgreSQL testi boş bir `head` upgrade ile yetinmez. `0029` seviyesinde dört legacy
employee ve mevcut organization katalog satırları oluşturur, ardından `head`'e yükseltir ve raporu
okur.

- Dört employee için tam bir effective-dated assignment oluşur; işe giriş/çıkış tarihleri interval
  sınırlarına taşınır. Terminated employee'nin exclusive `effective_to` değeri
  `employment_end_date + 1 gün` olur.
- Mevcut `Engineering` department ve `Developer` position normalize edilmiş eşleşmelerde yeniden
  kullanılır; kopya katalog kaydı oluşmaz.
- Boş legacy değerler deterministic `Unspecified` kayıtlarına, yeni normalize edilmiş değerler
  deterministic tenant-scoped katalog UUID'lerine eşlenir.
- Tenant başına yalnız bir `LEGACY` branch oluşturulur ve tüm backfill assignment'ları default legal
  entity'ye bağlanır.
- Sentetik raporun exact çıktısı `4 legacy employee -> 4 assignment`, `1 LEGACY branch`, toplam
  `3 department` ve `3 position` katalog satırıdır; bunların mevcut eşleşmeleri reuse edilir.
- Kaynak `employees.department` ve `employees.position` stringleri, boşluk/case dahil, aynen kalır;
  contract adımı yapılmaz. Current reads structured assignment'ı tercih eder ve gerektiğinde legacy
  alana fallback eder.
- Assignment UUID'leri ve oluşturulan katalog UUID'leri aynı tenant/veri girdisi için tekrar
  üretilebilir. Backfill ikinci bir belirsiz eşleşme kaynağı eklemez.

Bu sayılar sentetik gate fixture'ına aittir; production veri sayısı olarak sunulmaz. Testin amacı
dolu şemada determinism, veri koruma ve mapping davranışını kanıtlamaktır.

## PostgreSQL güvenlik ve performans kanıtı

- Tam PostgreSQL lane'i 57 test ile geçti. Migration round-trip ve sıfır autogenerate schema drift,
  FORCE RLS, runtime grants,
  tenant/platform token cross-use, membership selection replay/tamper/cross-tenant saldırıları,
  department cycle ve eşzamanlı move senaryoları, archive history, manager scope ve migrated API
  smoke bu lane içindedir.
- P3K assignment gate'i 2.481 effective assignment içeren iki tenantlı fixture üzerinde yalnız
  authenticated manager'ın doğrudan takımını döndürdü. Her 25 satırlık sayfa sabit 3 SELECT / 5
  statement kullandı; indirect ve diğer-tenant satırları sonuçlara girmedi.
- `EXPLAIN ANALYZE`, manager-scope okumasında
  `ix_employee_assignments_tenant_manager_scope` indeksinin kullanıldığını doğruladı.
- PostgreSQL iddia etmeyen hızlı migration lane'i ayrıca 56 test ile geçti: doğrusal tek head,
  SQLite compatibility, offline SQL üretimi, exact katalog parity ve expand-contract round-trip.

## Contract ve geri dönüş kararı

- Migrationlar expand-contract yaklaşımındadır; davetler, activation akışı, mevcut global
  identity'ler, tenant membership'ler ve Phase 2 API davranışı korunur.
- Legacy employee organization stringleri P3K'de silinmez. Bunların kaldırılması ancak ayrı veri
  raporu ve sonradan onaylanmış contract adımıyla yapılabilir.
- `0031` downgrade, permission üzerinde beklenmeyen role grant'i varsa veri kaybı yaratmak yerine
  reddeder. Beklenen iki grant'i ve permission kaydını kontrollü siler.
- Demo seed migration değildir. Lokal/dev-only idempotent seed, aynı canonical admin identity'yi iki
  tenant membership'i ve ayrı platform rolüyle kurar; `--auth-demo` admin/manager aktivasyon
  URL'lerini etiketli üretir.
- Phase 4 employee master data, field-security, payroll, SGK, banking, PDKS, AI ve dış entegrasyon
  değişikliği bu raporun ve P3K'nın dışındadır.

## Tekrarlanabilir gate komutları

```bash
uv run alembic heads
uv run pytest -q backend/tests/test_migrations.py
IK_TEST_DATABASE_URL=<local-disposable-postgres-url> uv run pytest -q -m postgres
IK_TEST_DATABASE_URL=<local-disposable-postgres-url> \
  uv run pytest -q -m postgres \
  backend/tests/integration/test_postgresql_p3k_assignment_gate.py -s
```

Tüm PostgreSQL testleri disposable lokal test veritabanlarında çalışır; staging/production veri
kaynağına migration uygulanmamıştır.
