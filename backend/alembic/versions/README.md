# Alembic versions

## P0D tenant relational integrity

`0009_expand_tenant_relational_integrity` ve
`0010_contract_tenant_relational_integrity` birlikte expand-contract geçişidir.

- Expand başlamadan önce `TENANT_RELATIONSHIP_PREFLIGHT_SQL`, mevcut sekiz foreign-key
  ilişkisindeki orphan kayıtları ve dört tenant-owned child ilişkisindeki cross-tenant kayıtları
  listeler. Migration aynı sorgunun özetinde satır bulursa hiçbir constraint eklemeden fail olur.
- PostgreSQL expand adımı `employees(tenant_id, id)` ve `users(tenant_id, id)` candidate
  index'lerini `CONCURRENTLY` kurup unique constraint olarak bağlar; yarım kalmış invalid migration
  index'lerini güvenli biçimde yeniden kurabilir.
- Dört composite foreign key önce `NOT VALID` eklenir. Bu durum yeni write'ları hemen korurken eski
  scalar foreign key'leri yerinde tutar.
- Concurrent index kurulurken commit edilmiş bir write'ın ilk taramayla yeni constraint arasına
  girmemesi için aynı preflight, `NOT VALID` constraint'ler eklendikten sonra table lock'ları
  bırakılmadan yeniden çalışır. İkinci tarama fail olursa expand revision stamp edilmez.
- Contract adımı composite constraint'leri `VALIDATE CONSTRAINT` ile doğrular; ancak bundan sonra
  eski employee/user scalar foreign key'lerini kaldırır.
- Alembic `transaction_per_migration=True` kullanır; `upgrade head` contract validation'da fail
  olursa tamamlanmış expand revision'ı rollback edilmez ve onarım için iki constraint nesli korunur.
- Downgrade önce eski scalar foreign key'leri geri ekleyip validate eder, sonra expand revision'ı
  composite foreign key ve candidate key'leri kaldırabilir.

SQLite yolu yalnız migration zinciri ve model metadata uyumunu hızlı kontrol eder. PostgreSQL
concurrent index, `NOT VALID`, validation ve doğrudan write reddi için kanıt
`backend/tests/integration/test_postgresql_tenant_relational_integrity.py` içindeki gerçek
PostgreSQL testleridir.
