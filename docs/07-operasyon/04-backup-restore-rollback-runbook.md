# Backup, Restore ve Rollback Runbook

Bu runbook, Phase 10E kapsamındaki PostgreSQL backup alma, backup doğrulama, izole
restore kanıtı ve uygulama rollback uygunluk kontrolünü tanımlar. Araç MVP seviyesinde
çalıştırılabilir bir recovery kontrolüdür; WAL/PITR, replikasyon, gerçek ortama otomatik
restore, deployment veya veritabanı downgrade sistemi değildir.

PostgreSQL dump ile object-storage mirror aynı transaction snapshot'ını paylaşmaz; iki store
arasında atomik/cross-store tutarlılık kanıtı üretmez. `SHA256SUMS` bozulma ve envanter
tutarlılığını kontrol eder, artifact'ın kaynağını veya saldırgana karşı authenticity'sini
tek başına kanıtlamaz. Kanıtlar bu nedenle ayrıca onaylı ve erişimi kısıtlı kanalda korunur.

Araç hiçbir koşulda kaynak veritabanına ya da kaynak object-storage bucket'ına restore
veya silme işlemi yapmaz. `rollback-guard` yalnızca karar girdisi üretir; deployment
çalıştırmaz. Gerçek bir recovery restore işlemi ayrı onaylı prosedür, bakım/read-only
penceresi ve SRE/DBA sahipliği gerektirir.

## 1. Roller ve zorunlu kayıtlar

Her operasyon için aşağıdakiler işlem başlamadan belirlenir:

- Operasyon sahibi ve komutu çalıştıracak SRE.
- Prod/staging işlemleri için onaylayan kişi ve geçerli change-ticket.
- Backup'ın amacı, kapsamı, saklama sınıfı ve kanıtın erişim yetkisi.
- Başlangıç/bitiş için UTC zaman penceresi.
- Restore veya rollback sırasında kullanıcı etkisi varsa bakım/read-only penceresi ve
  iletişim sahibi.
- Başarısızlık ve temizlik için DBA, storage ve incident escalation kişileri.

Prod erişimi break-glass/JIT, süreli, gerekçeli, minimum kapsamlı ve auditli olmalıdır.
Komutlar yalnızca onaylı operatör oturumundan ve repository kökünden çalıştırılır.

## 2. Değişmez güvenlik kuralları

- DSN, parola, access key, secret key, session token, hostname, port, alias ve bucket
  adı ticket'a, terminal çıktısına, manifest'e veya dosya adına kopyalanmaz.
- Credential veya endpoint CLI argümanı olarak verilmez. Değerler onaylı ortam/secret
  kanalından process environment'a sağlanır; shell tracing açılmaz.
- Kaynak veritabanına restore, `alembic downgrade`, truncate veya drop uygulanmaz.
- Kaynak bucket silinmez ve remote mirror işleminde `--remove` kullanılmaz.
- Symlink, mevcut hedef dizin, güvenli olmayan path/mode, belirsiz hedef veya beklenmeyen
  artifact görüldüğünde işlem devam ettirilmez.
- `--keep-proof-database` benzeri bir kaçış yolu yoktur. İzole proof database her sonuçta
  otomatik temizlenebilmelidir.
- Hata çıktısı generic ve secret-free tutulur. Ayrıntılı exception/command dump'ı ticket'a
  eklenmez; exit code ve machine-readable reason code korunur.

## 3. Ortam değişkenleri

`IK_ENVIRONMENT` her alt komut için zorunludur. Uygulamanın geçerli değerleri `local`,
`dev`, `test`, `staging` ve `prod` değerleridir. Bilinmeyen veya eksik değer fail-closed
sonuçlanır. Doküman topolojisindeki `pilot` ve `dr`, uygulama ayarı olarak doğrudan kabul
edilmez; bu değerlerle işlem durdurulur ve release/SRE owner'a escalation yapılır. Gerçek veri
bağlamı daha düşük bir environment gate'ine eşlenerek güvenlik kontrolleri atlanmaz.

| Değişken | Kullanım | Kural |
|---|---|---|
| `IK_DATABASE_URL` | `backup`, `restore-proof`, `rollback-guard` | Kaynak PostgreSQL bağlantısıdır. Database, host ve user içermeli; desteklenen PostgreSQL scheme kullanmalıdır. |
| `IK_RECOVERY_ADMIN_DATABASE_URL` | `restore-proof` | Kaynakla aynı PostgreSQL sunucusundaki maintenance database bağlantısıdır; kaynak database bağlantısı değildir. |
| `IK_RELEASE_COMMIT_SHA` | `backup` | 40 karakter lowercase hex olmalıdır. Yalnız staging/prod dışında `development` kabul edilir. |
| `IK_DOCUMENT_STORAGE_BACKEND` | Her `backup`; object içeren `restore-proof` | Backup için açıkça `disabled` veya `s3` olmalıdır; object proof için `s3` zorunludur. |
| `IK_RECOVERY_MC_SOURCE_ALIAS` | `s3` backup ve object proof | Operatör tarafından önceden ve güvenli biçimde yapılandırılmış kaynak `mc` alias'ıdır. |
| `IK_S3_BUCKET` | `s3` backup ve object proof | Kaynak bucket'tır. CLI argümanı veya manifest alanı değildir. |

Yalnız `postgresql` ve `postgresql+asyncpg` scheme'leri kabul edilir. Async driver suffix'i
client araçlarına aktarılmaz; doğrulanan bağlantı component'leri iki scheme için de ayrı
`PG*` environment değerlerine dönüştürülür. URL component'leri percent-decode edilir. Eksik database/host/user,
kontrol karakteri, desteklenmeyen scheme veya hedef kimliğini değiştiren query option varsa
işlem reddedilir. Parola child process argümanına konmaz; araç geçici, `0600` modlu
`PGPASSFILE` kullanır, child environment'ı temizler ve dosyayı her sonuçta kaldırır. Temporary
credential directory temizliği doğrulanamazsa işlem `TEMPORARY_CLEANUP_FAILED` ile başarısızdır.

Database identifier `[A-Za-z0-9_][A-Za-z0-9_$.-]{0,62}` grammar'ına uymalı ve UTF-8 olarak
63 byte'ı geçmemelidir. User boş olamaz ve UTF-8 olarak en fazla 128 byte olabilir. Port
verilmezse `5432` kullanılır. `database`, `dbname`, `host`, `hostaddr`, `passfile`, `password`,
`port`, `service`, `servicefile`, `target_session_attrs` ve `user` query option'ları hedef
kimliğini değiştirebildiği için reddedilir. Yalnız doğrulanan `sslmode`, TLS path option'ları,
`channel_binding`, `gssencmode` ve canonical `1..60` aralığındaki `connect_timeout` child
environment'a aktarılabilir.

`IK_DOCUMENT_STORAGE_BACKEND=disabled` olduğunda object storage `not_applicable` olarak
kaydedilir ve `mc` gerekmez. `s3` olduğunda source alias ve bucket strict karakter
allowlist'inden geçmelidir. Alias yapılandırma ve credential kabul etme bu CLI'ın görevi
değildir. Alias `[A-Za-z][A-Za-z0-9_-]{0,31}` grammar'ına uyar. Bucket 3..63 karakterdir ve
`[a-z0-9][a-z0-9.-]*[a-z0-9]` grammar'ına uyar; ardışık nokta, nokta-tire/tire-nokta ve IP
adresi biçimi reddedilir. `mc` çalışması için en az bir adet mutlak ve kontrol karakteri
içermeyen `HOME` veya `MC_CONFIG_DIR` mevcut olmalıdır.

## 4. Ön kontroller

1. Doğru repository/release üzerinde olunduğunu ve çalışma ağacının operasyon prosedürüne
   uygun olduğunu doğrula.
2. Operasyon sahibi, change-ticket, bakım/read-only penceresi ve escalation kişilerini kaydet.
3. Gerekli ortam değişkenlerinin onaylı kanaldan verildiğini doğrula; değerleri ekrana basma.
4. Output root, backup directory ve release manifest dosyalarının mutlak ve beklenen yerler
   olduğunu doğrula. Symlink kullanma; leaf dosya/directory current process user'ına ait
   olmalıdır. Bütün ancestor directory'ler root veya current user'a ait ve group/world-writable
   olmayan gerçek directory olmalıdır.
5. Alt komutun ihtiyaç duyduğu executable'ların onaylı PATH üzerinde olduğunu doğrula:

   | Alt komut | Zorunlu executable |
   |---|---|
   | `backup` | `pg_dump`, `psql`, `pg_restore`, `alembic`; storage `s3` ise ayrıca `mc` |
   | `verify-backup` | `pg_restore` |
   | `restore-proof` | `psql`, `pg_restore`, `createdb`, `dropdb`, `alembic`; object proof varsa ayrıca `mc` |
   | `rollback-guard` | `psql`, `alembic` |

   Araç her executable'ı canonical mutlak, regular ve executable bir PATH girdisi olarak
   fail-closed çözer. Binary ile bütün canonical parent'ları root/current-user owned ve
   group/world-writable olmayan path'ler olmalıdır; ilgisiz binary zorunlu tutulmaz.
   `restore-proof`, database oluşturmadan önce `createdb` description/connection-limit ve
   `dropdb --force` desteğini de bounded `--help` probe'uyla doğrular. Alembic revision
   değerleri strict ve read-only `public.alembic_version` sorgusuyla alınır; `alembic`
   executable'ı yalnız ilgili revision işlemlerinde güvenli PATH prerequisite'i olarak çözülür.
6. Restore proof için proof database adını ve otomatik drop yetkisini önceden doğrula.
   Temizliğin garanti edilemediği durumda proof başlatma.
7. Object restore proof isteniyorsa kaynak ile aynı olmayan, dedicated ve non-production
   boş proof alias/bucket'ı ile bunların yaşam döngüsü sahibini önceden belirle.

Komutlar shell açmadan, argument array ve bounded timeout ile çalışır. `N`, `1..86400`
aralığında tam sayı saniyedir; verilmezse `1800` kullanılır. Timeout her child process için
uygulanır. Timeout veya prerequisite hatasında aynı komutu körlemesine tekrarlamak yerine
aşağıdaki stop/escalation kuralları uygulanır.

### 4.1 Machine-readable sonuç

Başarılı `backup`, `status=completed`, UTC completion timestamp ve güvenli backup adını;
`verify-backup`, `status=verified` ve UTC verification timestamp'i; `restore-proof`,
`status=restore_proof_succeeded` ile aşağıda tanımlanan generic ölçümleri; `rollback-guard`
yalnız `safe_for_application_rollback=true` değerini JSON olarak stdout'a yazar.

Rollback guard dışındaki başarısızlıklar `status=failed` ve `reason_code`; rollback guard
başarısızlığı `safe_for_application_rollback=false` ve `reason_code` üretir. İnsan stderr'i
yalnız generic `Recovery operation failed.` mesajıdır. Restore proof içindeki SIGINT/SIGTERM,
cleanup sonrası `INTERRUPTED` reason code ile kontrollü non-zero sonuçlanır; top-level
`KeyboardInterrupt` path'i `130` döner. Diğer kontrollü başarısızlıklar non-zero'dur. JSON ve
exit code birlikte kanıt olarak saklanır.

## 5. Backup alma

Arayüz:

```bash
python3 scripts/ops/recovery.py backup \
  --output-root ABS \
  [--timeout-seconds N]
```

`ABS` önceden mevcut, mutlak, `/` olmayan, current process user'ına ait ve group/world-writable
olmayan output root'tur. Path'in hiçbir component'i symlink olamaz. Araç her zaman
`backup-YYYYMMDDTHHMMSSZ-<8-lowercase-hex>` biçiminde generic, yeni bir child adı üretir;
operatörden artifact/target adı kabul etmez ve çakışan mevcut adı reddeder. Backup directory ve
alt directory'ler `0700`, regular artifact'lar `0600`, current-user-owned ve single-link
oluşturulur.

PostgreSQL backup şu güvenli profile sahiptir:

- `pg_dump --format=custom --no-owner --no-privileges --no-password`
- Shell kullanılmadan doğrudan output dosyasına yazım
- Bounded subprocess timeout
- Kaynak üzerinde schema/data değişikliği yapmayan okuma
- Dump öncesi ve sonrası `alembic_version` revision listesinin `psql` ile exact karşılaştırması

Başarılı backup directory aşağıdaki artifact sınıflarını içerir:

- `database.dump` adlı PostgreSQL custom-format dump.
- Canonical ve atomik yazılmış `manifest.json`.
- Kendisi dışındaki bütün backup artifact'larını kapsayan `SHA256SUMS`.
- Object storage dahilse `objects/` altında local mirror; dahil değilse object durumu
  `not_applicable`.

Manifest yalnız sanitized generic metadata yayımlar: UTC oluşturma zamanı, format/schema
version, database identifier, kaynak migration revision ID'leri, dump digest/boyut,
object-storage durumu ve dahilse aggregate digest/count/bytes ile kaynak release commit SHA.
Host, user, DSN, port, tenant, tablo adı, satır değeri/count'u, source alias/bucket ve object
adı yayımlanmaz. `SHA256SUMS` object artifact'larının traversal/control-character içermeyen
backup-relative encoded path'lerini içerebilir; bu nedenle dosya da `0600` korunur.

`s3` seçildiyse `mc`, kaynak bucket'ı silmeden `objects/` altına mirror eder. Her local object
internal olarak hash edilir; manifest'e yalnız deterministik aggregate digest, generic object
count ve total bytes girer.

Backup komutu tamamlanmadan önce kendi ürettiği directory üzerinde aynı strict verification'ı
çalıştırır. Dump öncesi/sonrası revision listesi değişirse `BACKUP_CONSISTENCY_FAILED` ile
başarısız olur. Başarısız backup için yeni oluşturduğu directory'yi kaldırmayı dener; kalan
partial directory veya doğrulanamayan temizlik `BACKUP_CLEANUP_FAILED` sayılır; artifact kanıt
değildir, erişimi sınırlandırılır ve escalation yapılır. Başarılı backup üzerinde ayrıca
bağımsız `verify-backup` çalıştırılmadan artifact recovery girdisi olarak kabul edilmez.

## 6. Backup doğrulama

Arayüz:

```bash
python3 scripts/ops/recovery.py verify-backup \
  --backup-dir ABS \
  [--timeout-seconds N]
```

Bu alt komut backup directory ve artifact'ları üzerinde read-only çalışır; veritabanına veya
object storage'a bağlanmaz. Aşağıdakilerin tamamını doğrular:

- Directory/artifact symlink değildir; path'ler güvenlidir ve current user'a aittir.
- Beklenen bütün dosyalar vardır, extra veya unmanifested dosya yoktur.
- Directory modları tam `0700`; regular-file modları tam `0600` ve link count tam `1`'dir.
- Manifest canonical schema'ya uyar, malformed/extra alan veya unsafe path içermez.
- Her artifact'ın SHA-256 değeri checksum kaydıyla; dump size ve object aggregate total bytes
  değerleri manifest ile aynıdır.
- `SHA256SUMS` kapsamı eksiksizdir ve kendisini listelemez.
- PostgreSQL archive `pg_restore --list` ile okunabilir ve corrupt değildir.
- Object artifact'ları varsa internal aggregate digest/count/bytes manifest ile aynıdır.
- `staging`/`prod` bağlamında source release commit değeri `development` değildir.

Bir kontrol başarısızsa backup kullanılmaz, değiştirilerek “onarılmaz” ve restore proof'a
taşınmaz. Artifact erişimi sınırlandırılır; reason code, exit code ve sanitized kanıt operasyon
sahibine iletilir.

## 7. İzole restore proof

Arayüz:

```bash
python3 scripts/ops/recovery.py restore-proof \
  --backup-dir ABS \
  --proof-database NAME \
  --confirm-isolated-restore \
  [--confirm-non-production-target --change-ticket ID] \
  [--include-objects --proof-object-alias ALIAS --proof-object-bucket BUCKET] \
  [--timeout-seconds N]
```

`--confirm-isolated-restore` exact acknowledgement olmadan işlem başlamaz. `staging` ve
`prod` bağlamında ayrıca `[A-Z][A-Z0-9]{1,15}-[1-9][0-9]{0,11}` grammar'ından geçen
`--change-ticket ID` ve `--confirm-non-production-target` birlikte zorunludur. Diğer ortamlarda
change-ticket opsiyoneldir ama verilirse aynı grammar'a uymalıdır. Bu flag'ler target'ın güvenli
olduğunu kendiliğinden kanıtlamaz; operator preflight ve onay kayıtları yine gereklidir.

`NAME` tam olarak aşağıdaki grammar'a uymalıdır:

```text
^[a-z][a-z0-9_]{2,62}_restore_proof$
```

Regex'e ek olarak ad ASCII olarak toplam 63 byte'ı geçemez.

Proof database:

- Kaynak ve maintenance database adlarından farklı olmalıdır.
- `postgres`, `template0` veya `template1` olamaz.
- İşlem başında mevcut olmamalıdır.
- Backup manifest'indeki database identifier, `IK_DATABASE_URL` source database adıyla exact
  aynı olmalıdır.
- `staging`/`prod` bağlamında backup source release commit değeri `development` olamaz.
- `IK_RECOVERY_ADMIN_DATABASE_URL` source ile aynı host ve portta, farklı bir maintenance
  database'inde olmalıdır. User operatör tarafından yalnız bu proof işi için ayrılmış ve bu
  işlem boyunca exclusive kullanılan login rolüdür. CLI rolün `CREATEDB` taşıdığını;
  `CREATEROLE`, superuser, replication veya `BYPASSRLS` taşımadığını; başka hiçbir role üye
  olmadığını ve preflight anında database/tablespace sahibi olmadığını doğrular. Başka
  database'lerdeki object grant/ownership ile operasyonel exclusivity catalog'dan bütünüyle
  kanıtlanamayacağı için bunlar owner'ın zorunlu ön koşuludur. Restore archive SQL sandbox
  kabul edilmez.
- `template0` ve `UTF8` ile boş olarak oluşturulur.
- Araç oluşturma çağrısında rastgele generic description marker'ı ile atomik, rastgele yüksek
  connection-limit kimliği ekler; bu connection-limit değeri önceden bütün database catalog'unda
  yokluk kontrolünden geçer. Restore'a yalnız marker, connection-limit, owner ve database OID
  kimliği doğrulanınca geçer. Cleanup aynı OID'yi; OID henüz kaydedilemediyse önceden kaydedilen
  aktif role OID'si ile atomik connection-limit kimliğinin ikisini birden arar. Yalnız owner
  eşleşmesi hiçbir zaman silme yetkisi vermez. Aynı role/proof adını eşzamanlı kullanan başka
  operasyon yasaktır; isim/kimlik belirsizliğinde işlem fail-closed escalation yapar.
- Restore, `pg_restore --no-owner --no-privileges --exit-on-error --no-password` ile yapılır.
- Başarı, hata, timeout, SIGINT veya SIGTERM sonrasında `finally` cleanup mutlaka denenir.
  Credential ve temporary-artifact scope'larında SIGINT/SIGTERM kaydedilip cleanup bitene kadar
  ertelenir. Doğrulanmış kimlik drop edilir; adın, marker'ın, atomik connection-limit kimliğinin
  ve kaydedilebildiyse OID'nin catalog'da yokluğu doğrulanır.

Araç normal preflight'ta cleanup yetki ve client kabiliyetini kanıtlayamıyorsa restore'u
başlatmaz. Sonradan oluşan bağlantı/host kaybı nedeniyle drop doğrulanamazsa işlem başarılı
sayılmaz; erişim kısıtlı tutulur ve DBA/SRE'ye derhal escalation yapılır. Proof database'i
isteyerek tutma seçeneği yoktur.

Restore sonrasında araç aşağıdakilerin tamamını doğrular:

1. Backup verification halen başarılıdır.
2. Proof PostgreSQL bağlantısı kurulabilir.
3. Restore edilmiş current Alembic revision ID kümesi manifest kaynak revision kümesiyle
   tam olarak aynıdır.
4. `public` schema'da en az bir base table vardır.
5. RLS-enabled table sayısı generic count olarak sorgulanabilir; `0` ile public base-table count
   arasındadır.
6. Object proof seçildiyse restored object aggregate count/bytes/digest backup ile aynıdır.

Sonuç yalnız concise JSON olarak status, UTC timestamps, duration, migration revision ID'leri,
generic table count, generic RLS-enabled count ve object aggregate status/count/bytes içerir.
DSN, host, user, alias, bucket, tablo/object adı veya exception text içermez.
Object status yalnız `verified`, `not_requested` veya `not_applicable` değerlerinden biridir.

### 7.1 Object restore proof

Object proof yalnız aşağıdaki üç argüman birlikte verildiğinde yapılır:

- `--include-objects`
- `--proof-object-alias ALIAS`
- `--proof-object-bucket BUCKET`

Backup object durumu `included` değilse object proof istenmez. Proof alias ve bucket yukarıdaki
strict allowlist'lerden geçmelidir; proof alias kaynak alias'tan ve proof bucket kaynak bucket'tan
ayrı ayrı farklı olmalıdır. Proof target önceden mevcut, boş, dedicated, non-production ve ilgili
change-ticket kapsamında olmalıdır. Alias önceden yapılandırılır; credential CLI'a verilmez.
Araç boşluğu önce proof preflight'ta, sonra upload'dan hemen önce tekrar kontrol eder; bu iki
kontrol external writer'a karşı atomik kilit değildir, bu yüzden target için operasyonel
exclusive ownership yine zorunludur.

Araç remote target üzerinde `--remove` kullanmaz ve object adı yazdırmaz. Sonuç, `0700`
temporary local mirror üzerinden aggregate olarak doğrulanır; temporary mirror işlem sonunda
kaldırılır. Temporary mirror temizliği doğrulanamazsa işlem `TEMPORARY_CLEANUP_FAILED` ile
başarısızdır. CLI remote proof bucket'ını otomatik silmez; retention/cleanup kararı storage
sahibi tarafından change-ticket ve kurumun onaylı storage prosedürüyle yönetilir.

## 8. Rollback guard

Feature kaynaklı incident'ta ilk aksiyon ilgili feature flag'i kapatmaktır. Etki sürüyorsa ikinci
seçenek, guard sonucu uygunsa önceki application image/release'e rollback'tir. Veritabanı için
otomatik downgrade yapılmaz.

Arayüz:

```bash
python3 scripts/ops/recovery.py rollback-guard \
  --current-release-manifest FILE \
  --target-release-manifest FILE \
  [--timeout-seconds N]
```

İki release manifest'i de strict JSON object olmalı; aşağıdaki dört key dışında key içeremez:

| Key | Tip ve format |
|---|---|
| `release_commit_sha` | 40 karakter lowercase hexadecimal string. |
| `build_timestamp_utc` | Tam `YYYY-MM-DDTHH:MM:SSZ` biçiminde, calendar-valid UTC timestamp string. Offset ve fractional second kabul edilmez. |
| `app_version` | `[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}` grammar'ına uyan string. |
| `compatible_migration_head_ids` | `1..64` elemanlı, lexicographic sıralı ve tekrarsız revision ID string listesi. Her ID en fazla 128 karakterdir ve `[0-9a-z_]+` grammar'ına uyar. |

Dosyalar mutlak path'te, regular, symlink olmayan, single-link, current process user'ına ait,
group/world-writable olmayan ve en fazla `65536` byte büyüklüğünde onaylı release pipeline
çıktıları olmalıdır; credential veya endpoint içermemelidir. Duplicate JSON key, extra key ve
non-standard JSON sabiti reddedilir. Current ve target commit farklı olmalıdır. Guard
`IK_DATABASE_URL` üzerinden current database revision ID'lerini read-only sorgular ve şu üç
canonical sıralı listenin exact eşitliğini arar:

- Current database revision ID'leri.
- Current release manifest `compatible_migration_head_ids` değeri.
- Target release manifest `compatible_migration_head_ids` değeri.

Bütün schema, commit ve revision kontrolleri geçerse yalnız
`safe_for_application_rollback=true` üretilebilir. Diğer bütün sonuçlar non-zero exit ve generic,
stable reason code ile `safe_for_application_rollback=false` üretir ve fail-closed'dur. Araç
image değiştirmez, deployment çalıştırmaz ve veritabanı downgrade etmez.

Guard güvenli sonucu sonrasında release captain/SRE onayıyla yalnız application image rollback
edilir. Ardından health/readiness ve tenant-isolation smoke sonuçları gözlem penceresinde
kaydedilir. Guard güvenli değilse migration geçmişine müdahale edilmez; maintenance/read-only
penceresi korunur ve DBA/release owner escalation süreci başlatılır.

## 9. Current head uyumluluğu

Revision ID contract'ı strict `[0-9a-z_]+` allowlist'i ve ID başına en fazla 128 karakterdir.
Phase 10'a giren `0042_p9_privacy_evidence_hardening` database head'i 34 karakterdir ve bu
contract'a uyar. Backup öncesi/sonrası revision capture, backup manifest doğrulaması, restore
proof karşılaştırması ve rollback guard'ın live/current/target release-manifest kontrolleri aynı
grammar'ı kullanır.

Bu head yalnız canonical sıralı revision listeleri ilgili bütün girdilerde exact eşleştiğinde
kabul edilir. Grammar dışı, uppercase, 128 karakteri aşan veya listeler arasında uyuşmayan bir
revision değeri fail-closed sonuçlanır; operatör revision değerini yeniden adlandırmaz, migration
history/file oluşturmaz ve manifest'i elle farklı bir değerle yazmaz.

## 10. Kanıt kaydı

Secret-free operasyon kaydı en az şunları içerir:

- Operasyon sahibi, onaylayan, change-ticket ve UTC başlangıç/bitiş zamanı.
- Kullanılan release commit/build/app version kimliği ve release manifest dosyalarının onaylı
  digest'leri.
- Çalıştırılan alt komut ve yalnız sanitized argümanlar; environment değerleri kayda alınmaz.
- Exit code, stable reason code ve CLI'ın concise JSON sonucu.
- Backup için erişimi sınırlandırılmış `manifest.json` ve `SHA256SUMS`, ayrıca bağımsız
  `verify-backup` sonucu.
- Restore proof için database cleanup sonucu ve object proof varsa aggregate doğrulama ile
  storage sahibinin retention/cleanup kaydı.
- Rollback/restore sonrasında health, readiness, tenant-isolation smoke ve gözlem penceresi
  sonucu.
- Başarısızlıkta alınan stop kararı, veri/artifact erişim durumu ve escalation zamanı.

`SHA256SUMS` object-relative path içerebileceğinden ve manifest database identifier/revision
bilgisi taşıdığından bu dosyalar public ticket'a yapıştırılmaz; `0600` erişimli kanıt deposunda
saklanır. Ticket'a yalnız onaylı digest ve sanitized sonuç bağlanır.

## 11. Restore ve rollback sonrası kontroller

Gerçek bir recovery restore veya onaylı application rollback sonrası:

1. Maintenance/read-only penceresini health kontrolleri tamamlanana kadar koru.
2. Uygulamanın health ve readiness kontrollerini çalıştır; başarısızsa trafiği açma.
3. Tenant-isolation smoke ile bir tenant'ın başka tenant verisine erişemediğini doğrula; müşteri
   verisini loglama.
4. Current migration revision kümesini onaylı manifest ile exact karşılaştır.
5. Worker/queue ve document-storage readiness sinyallerini generic seviyede doğrula.
6. Hata oranı, latency ve kritik worker sinyallerini belirlenen gözlem penceresinde izle.
7. Kanıtları change-ticket'a bağla; release captain, SRE ve QA onayı olmadan pencereyi kapatma.

## 12. Stop ve escalation koşulları

Aşağıdaki koşullardan herhangi birinde işlem durur ve non-zero sonuç başarılı kabul edilmez:

- `IK_ENVIRONMENT` veya gerekli database/storage/release ayarı eksik ya da geçersizdir.
- Prod/staging change-ticket veya explicit non-production acknowledgement eksiktir.
- PostgreSQL target kimliği kesin değildir; URL/identifier validation başarısızdır.
- Prerequisite binary yoktur, güvenli PATH'ten çözülemez veya timeout oluşur.
- Path symlink'tir; target mevcuttur; mode güvensizdir; extra/missing artifact vardır.
- Manifest/schema/checksum/size/archive/object aggregate doğrulaması başarısızdır.
- Revision ID grammar'a uymaz veya manifest/database revision kümeleri exact eşit değildir.
- Proof database adı geçersiz, reserved, mevcut ya da source/maintenance ile aynıdır.
- Proof database cleanup garanti edilemez veya drop doğrulanamaz.
- Backup directory, `PGPASSFILE` ya da temporary object mirror temizliği doğrulanamaz.
- Object proof target kaynakla aynıdır, dedicated değildir ya da aggregate doğrulaması tutmaz.
- Restore edilen database'e bağlantı kurulamaz, public base table yoktur veya RLS count sorgusu
  güvenilir biçimde tamamlanamaz.
- `rollback-guard` safe sonucu üretmez.
- SIGINT/SIGTERM, beklenmeyen child-process sonucu veya kanıt bütünlüğü şüphesi oluşur.
- Health/readiness ya da tenant-isolation smoke başarısızdır.

Bu durumlarda kaynakta düzeltici/destructive komut çalıştırılmaz. Bakım/read-only durumu ve
erişim sınırları korunur; sanitized reason code ile operasyon sahibi, SRE/DBA, release owner,
security veya storage owner'dan ilgili olanlara escalation yapılır.
