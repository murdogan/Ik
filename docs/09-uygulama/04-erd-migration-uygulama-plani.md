# ERD ve Migration Uygulama Planı

Bu doküman, foundation ERD dokümanını implementasyon sırasına indirger. Amaç tüm veritabanını bir anda kurmak değil, migration zincirini güvenli, test edilebilir ve tenant-first sırayla oluşturmaktır.

## 1. Migration ilkeleri

- Her tenant-owned tablo `tenant_id` taşır.
- Dışa açık ID'ler UUID olmalıdır.
- Migration küçük ve geri alınabilir olmalıdır.
- Büyük/destructive değişiklikler expand-contract yaklaşımıyla yapılır.
- Migration testleri model metadata ve migration dosyası varlığını doğrular.
- RLS/tenant guard testleri DB bağlantısı hazır olduğunda zorunlu olur.

## 2. Migration sırası

| Rev | Tablo/alan | Faz | Gerekçe |
|---|---|---|---|
| 0001 | `tenants` | Sprint-0 | Tüm izolasyonun temeli |
| 0002 | `users` | Sprint-0 | Auth ve tenant admin için temel |
| 0003 | `roles`, `permissions`, `user_roles` | Sprint-1 | RBAC olmadan protected endpoint olmaz |
| 0004 | `employees` | Sprint-1 | Core HR değerinin başlangıcı |
| 0005 | `departments`, `positions` minimal | Sprint-1/S2 | Employee assignment için gerekli |
| 0006 | `employee_assignments` | S2 | Effective-dated org ilişkisi |
| 0007 | `audit_events` | S2 | Kritik değişikliklerin izlenmesi |
| 0008 | `employee_documents`, `document_types` | S3 | Özlük belge yönetimi |
| 0009 | `leave_types`, `leave_balances` | S4 | İzin motoru başlangıcı |
| 0010 | `leave_requests`, `approval_tasks` | S4/S5 | İzin ve onay akışı |

## 3. İlk tenant tabloları

### `tenants`

Zorunlu alanlar:

- `id`
- `slug`
- `name`
- `status`
- `plan_code`
- `data_region`
- `locale`
- `timezone`
- `created_at`
- `updated_at`

Kısıtlar:

- `slug` unique.
- `status` enum/check.

### `users`

Zorunlu alanlar:

- `id`
- `tenant_id`
- `email`
- `full_name`
- `status`
- `password_hash`
- `created_at`
- `updated_at`

Kısıtlar:

- `(tenant_id, email)` unique.
- `tenant_id` foreign key.
- `status` enum/check.

## 4. RBAC tabloları

### `roles`

Alanlar:

- `id`
- `tenant_id`
- `code`
- `name`
- `system_role`
- `created_at`
- `updated_at`

Unique: `(tenant_id, code)`.

### `permissions`

Alanlar:

- `id`
- `code`
- `description`
- `module`

Unique: `code`.

### `user_roles`

Alanlar:

- `tenant_id`
- `user_id`
- `role_id`
- `valid_from`
- `valid_until`

## 5. Employee minimal ERD

### `employees`

MVP minimal alanlar:

- `id`
- `tenant_id`
- `employee_number`
- `first_name`
- `last_name`
- `email`
- `status`
- `employment_start_date`
- `employment_end_date`
- `created_at`
- `updated_at`

Unique: `(tenant_id, employee_number)`.

Hassas alanlar ilk migration'a alınmayabilir; TCKN/IBAN gibi alanlar field encryption planı netleşince eklenmelidir.

## 6. RLS/tenant guard planı

PostgreSQL RLS uygulanacaksa tenant-owned tablolar için standart:

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON employees
USING (tenant_id = current_setting('app.tenant_id')::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

İlk aşamada RLS migration'ları ayrı ve test edilebilir tutulmalıdır.

## 7. Test planı

| Test | Amaç |
|---|---|
| Metadata registration | Model Base metadata'ya kayıtlı mı |
| Required columns | Zorunlu kolonlar var mı |
| Migration exists | Migration dosyası var mı |
| Alembic history | Zincir doğru mu |
| RLS catalog test | Tenant tablolarında RLS açık mı |
| Cross-tenant query | Tenant A verisi Tenant B'den görünmüyor mu |

## 8. Seed planı

Demo/development seed:

- 2 tenant: `demo`, `acme`.
- Her tenant için 1 `tenant_admin`.
- Her tenant için 1 `hr_specialist`.
- Demo tenant için 20 employee.
- 3 department, 5 position.

Seed verisi gerçek kişisel veri içermemelidir.

## 9. Kabul kriterleri

- Migration sırası küçük ve anlaşılırdır.
- Tenant ve user sonrası RBAC ve employee sırası nettir.
- Hassas alanlar encryption kararı olmadan rastgele eklenmez.
- RLS testleri planlanmıştır.
- Seed verisi sentetik olacaktır.

## 10. Uygulamaya geçmeden önce açık kontroller

Kodlama başlamadan önce şu kararlar netleşmelidir:

- PostgreSQL UUID üretimi uygulama tarafında mı DB tarafında mı yapılacak?
- Email case-insensitive unique için `citext` extension kullanılacak mı?
- RLS ilk migration ile mi, yoksa tenant guard testleri tamamlandıktan sonra ayrı migration ile mi açılacak?
- Hassas alanlarda envelope encryption için kolon tipi ne olacak?
- Audit tablosu append-only olacaksa DB trigger mı uygulama servisi mi kullanılacak?

Bu kararlar verilmeden employee detay alanlarına geçilmemelidir. Özellikle TCKN, IBAN ve maaş gibi alanlar, encryption ve masking kararı netleşmeden migration'a eklenirse sonradan veri taşıma maliyeti doğar.

## 11. İlgili dokümanlar

- [Veritabanı Modeli ve ERD](../05-api-veri/01-veritabani-modeli-ve-erd.md)
- [Çok Kiracılık ve Veri İzolasyonu](../04-mimari/02-cok-kiracilik-ve-veri-izolasyonu.md)
- [Sprint-0 / Sprint-1 Backlog ve Task Planı](02-sprint-0-1-backlog-ve-task-plani.md)
