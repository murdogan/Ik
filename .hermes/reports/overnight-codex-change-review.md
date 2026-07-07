# Overnight Codex Change Review — Wealthy Falcon HR

Branch: `overnight/sprint-0-wealthy-falcon`  
Base: `main`  
Status: `ruff` green, `pytest` green (`43 passed`)  
Worktree: clean

## Kısa özet

Gece Codex Sprint-0/Sprint-1 başlangıcı için backend foundation'ı ilerletti:

- CI workflow eklendi.
- README lokal geliştirme komutları güncellendi.
- Alembic migration zinciri 0001→0004 olarak genişledi.
- Employee modeli eklendi.
- LeaveRequest modeli eklendi.
- Dashboard summary endpoint eklendi.
- Landing markası `Wealthy Falcon HR` olarak güncellendi.
- Tenant/User model testleri güçlendirildi.
- Migration, tenant, employee, leave request, dashboard testleri eklendi.

## Değişen ana dosyalar

### CI / DevOps

- `.github/workflows/ci.yml`
  - Backend CI eklendi.
  - `ruff check backend` ve `pytest` çalıştırıyor.

- `README.md`
  - Lokal geliştirme komutları eklendi/güncellendi.
  - Test/lint/migration komutları netleştirildi.

- `docs/07-operasyon/01-devops-ortamlar-surum-yonetimi.md`
  - DevOps ortam/sürüm yönetimi notları genişletildi.

### Migration / Database

- `backend/alembic/versions/0003_create_employees.py`
  - `employees` tablosu eklendi.
  - Tenant scoped employee yapısı.
  - Email unique constraint tenant bazlı.
  - Status check constraint.
  - Tenant/status ve tenant/email indexleri.

- `backend/alembic/versions/0004_create_leave_requests.py`
  - `leave_requests` tablosu eklendi.
  - Tenant + employee ilişkisi.
  - Status check constraint: pending/approved/rejected/cancelled.
  - Date order constraint: `end_date >= start_date`.
  - Tenant/status/date indexleri.

### Backend modelleri

- `backend/app/models/employee.py`
  - Employee domain modeli eklendi.
  - Tenant ilişkisi var.
  - User ilişkisi opsiyonel/ileriye dönük.
  - Alanlar: first_name, last_name, email, title, department, start_date, status.

- `backend/app/models/leave_request.py`
  - LeaveRequest domain modeli eklendi.
  - Employee ve tenant ilişkisi var.
  - Alanlar: leave_type, start_date, end_date, status, reason, requested_by_user_id.

- `backend/app/models/tenant.py`
  - Employee/leave ilişkileri için ilişki tanımları genişletildi.

- `backend/app/models/user.py`
  - Employee/leave request bağlantıları için ilişki hazırlığı yapıldı.

- `backend/app/models/__init__.py`
  - Yeni modeller export edildi.

### Tenancy

- `backend/app/core/tenancy.py`
  - Tenant guard yardımcıları güçlendirildi.
  - Tenant scoped query pattern testlendi.

### API

- `backend/app/api/dashboard.py`
  - Yeni endpoint: `/api/dashboard/summary`
  - Şimdilik minimal summary döndürüyor:
    - employee_count
    - pending_leave_requests
    - active_tenant_count

- `backend/app/main.py`
  - Dashboard router uygulamaya bağlandı.

- `backend/app/api/landing.py`
  - Landing copy/brand `Wealthy Falcon HR` yönüne çevrildi.

### Testler

- `backend/tests/test_employee_model.py`
- `backend/tests/test_leave_request_model.py`
- `backend/tests/test_dashboard.py`
- `backend/tests/test_tenant_model.py`
- `backend/tests/test_user_model.py`
- `backend/tests/test_tenancy.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_landing.py`

Toplam test sonucu:

```text
43 passed, 1 warning
```

## Commit listesi

```text
432d3e7 docs(T0): prepare baseline branch
a4cab3b docs(T1): document local development commands
f0fe761 chore: update overnight queue after T1
2aa4153 ci(T2): add backend GitHub Actions workflow
35a51cd chore: update overnight queue after T2
2075b90 chore(T3): document and verify alembic foundation
9f1cc6b chore: update overnight queue after T3
366acd4 T4 harden tenant user foundation
fced72c chore: update overnight queue after T4
346b4ff T5 add tenant-scoped employee model
d1ab04c chore: update overnight queue after T5
6c52f1f T6 add leave request minimal model
2b90f07 chore: update overnight queue after T6
0785c3b T7 add dashboard summary endpoint
fa58afb chore: update overnight queue after T7
b12c433 T8 landing brand update
1eef799 chore: update overnight queue after T8
8835e5d T9 final cleanup and report
```

## Görülebilir demo durumu

Bu branch henüz `main`e merge edilmedi ve public staging'e alınmadı.  
O yüzden dış linkte görmemen normal.

Görmen için sonraki güvenli adım:

1. Branch review.
2. Gerekirse küçük düzeltmeler.
3. Merge/push.
4. Staging clone güncelleme.
5. Public URL smoke test.

## Benim hızlı değerlendirmem

Kod temel olarak temiz ve testler yeşil. Ama public'e almadan önce özellikle şunları manuel review etmek doğru olur:

- Migration dosyaları prod/staging DB için doğru mu?
- Dashboard endpoint şimdilik mock/minimal mi, gerçek DB sayımı mı yapıyor?
- Employee/LeaveRequest enum/status alanları MVP için yeterli mi?
- Landing'de `Wealthy Falcon HR` ismini şimdilik kullanıyor muyuz, yoksa çalışma markası olarak mı tutuyoruz?
