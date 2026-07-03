# 28 — Test Stratejisi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** Birim, entegrasyon, E2E, performans ve güvenlik test yaklaşımı; test verisi, sorumluluklar ve kalite kapıları  
> **Faz:** Faz 6

---

## 1. Test Piramidi

```
              ┌─────────┐
              │   E2E   │  ~%10 (kritik akışlar)
              │  (Slow) │
           ┌──┴─────────┴──┐
           │  Integration  │  ~%30 (API + DB)
           │   (Medium)    │
       ┌───┴───────────────┴───┐
       │      Unit Tests       │  ~%60 (iş kuralları)
       │       (Fast)          │
       └───────────────────────┘
```

| Seviye | Amaç | Araç | Hedef Kapsam |
|--------|------|------|--------------|
| Unit | İş kurallarını hızlı doğrulamak | pytest (backend), Jest (frontend) | ≥ %80 (backend), ≥ %70 (frontend) |
| Integration | API + servis + DB etkileşimi | pytest + TestClient + PostgreSQL | Tüm API endpoint'leri |
| E2E | Kritik kullanıcı akışları | Playwright | 15-20 kritik senaryo |
| Non-functional | Performans, güvenlik, yük | Locust, OWASP ZAP | SLA hedefleri |

---

## 2. Kapsam Öncelikleri

| Öncelik | Alan | Coverage Hedefi |
|---------|------|-----------------|
| P1 | Auth, yetkilendirme, tenant izolasyonu | ≥ %90 |
| P1 | Personel CRUD, izin talebi ve onay | ≥ %85 |
| P1 | Bordro hesaplama (maaş, SGK, vergi) | ≥ %90 |
| P2 | İşe alım, performans döngüsü | ≥ %80 |
| P2 | Vardiya, eğitim, raporlama | ≥ %75 |
| P3 | Self-servis portal, organizasyon şeması | ≥ %70 |
| P3 | Bildirim, export, UI bileşenleri | ≥ %60 |

---

## 3. Test Türleri ve Detaylar

### 3.1 Birim Test (Unit)

| Konu | Araç | Yaklaşım |
|------|------|----------|
| İş kuralları | pytest | Pure function test, mock dış bağımlılıklar |
| Validasyon | pytest | Pydantic model validation |
| Hesaplama | pytest | Parametrized testler (bordro, izin bakiye, mesai) |
| Yetki kararları | pytest | ScopeResolver, PermissionChecker mock senaryoları |
| React bileşenleri | Jest + React Testing Library | Render, event, state testleri |
| Form validasyonu | Jest | Zod/yup schema testleri |

**Örnek: Bordro hesaplama unit test**
```python
@pytest.mark.parametrize("gross,expected_net,expected_sgk", [
    (30000.00, 22845.67, 4200.00),   # Normal maaş
    (100000.00, 68234.12, 14000.00),  # Yüksek dilim
    (17002.00, 14384.69, 2380.28),    # Asgari ücret
])
def test_calculate_net_salary(gross, expected_net, expected_sgk):
    result = PayrollCalculator.calculate(
        gross_salary=gross,
        year=2026,
        month=1,
        disability_degree=0,
        cumulative_tax_base=0,
    )
    assert result.net_salary == pytest.approx(expected_net, rel=0.01)
    assert result.sgk_employee == pytest.approx(expected_sgk, rel=0.01)
```

### 3.2 Entegrasyon Test (Integration)

| Konu | Araç | Yaklaşım |
|------|------|----------|
| API endpoint'leri | pytest + httpx (TestClient) | Gerçek DB + Redis, her test transaction rollback |
| DB sorgular | pytest + SQLAlchemy | Migration doğrulama, index performansı |
| Celery task'ları | pytest + celery.contrib.testing | Senkron task çalıştırma |
| Dosya upload | pytest + MinIO mock | Signed URL, format kontrolü |
| Tenant izolasyonu | pytest | 2 tenant oluştur, çapraz erişim dene (403 beklenir) |

**Örnek: İzin talebi API entegrasyon testi**
```python
class TestLeaveRequestAPI:
    def test_create_leave_request(self, auth_client, employee):
        response = auth_client.post("/api/v1/leave/requests", json={
            "leave_type": "annual",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "reason": "Tatil"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["working_days"] == 5

    def test_manager_approve(self, manager_client, pending_request):
        response = manager_client.post(
            f"/api/v1/leave/requests/{pending_request.id}/approve"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    def test_cross_tenant_access_denied(self, tenant_a_client, tenant_b_request):
        response = tenant_a_client.get(
            f"/api/v1/leave/requests/{tenant_b_request.id}"
        )
        assert response.status_code == 403
```

### 3.3 E2E Test (End-to-End)

| # | Senaryo | Adımlar | Öncelik |
|---|---------|---------|---------|
| 1 | Çalışan izin talebi → yönetici onay | Login → talep oluştur → çıkış → yönetici login → onay → bakiye kontrolü | P1 |
| 2 | Personel onboarding | İK login → yeni çalışan ekle → 5 adım sihirbaz tamamla → pozisyon ata | P1 |
| 3 | Performans çevrimi | Hedef gir → dönem kapat → değerlendirme → yöneticiye yayınla | P1 |
| 4 | Bordro kapanış | Puantaj onayla → bordro hesapla → slip PDF oluştur → export | P1 |
| 5 | İşe alım pipeline | İlan oluştur → aday ekle → mülakat planla → teklif gönder | P2 |
| 6 | Vardiya planlama | Şablon oluştur → haftalık plan → çalışan ata → PDKS kontrolü | P2 |
| 7 | Rapor oluşturma ve export | Dashboard → rapor builder → filtrele → PDF export | P2 |
| 8 | Rol ve yetki yönetimi | Yeni rol oluştur → izin ata → kullanıcıya ata → erişim doğrula | P1 |
| 9 | Self-servis profil güncelleme | Çalışan login → profil düzenle → değişiklik talebi → İK onay | P2 |
| 10 | MFA etkinleştirme | Ayarlar → MFA etkinleştir → TOTP doğrula → çıkış → MFA ile giriş | P1 |

**E2E Test Altyapısı:**
```typescript
// playwright.config.ts (özet)
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
```

### 3.4 Performans Testleri

| Test | Araç | Senaryo | Hedef |
|------|------|---------|-------|
| Yük testi | Locust | 200 eşzamanlı kullanıcı, karma akışlar | p95 < 500ms |
| Stres testi | Locust | 500+ kullanıcı, kademeli artış | Kırılma noktası tespit |
| Dayanıklılık testi | Locust | 100 kullanıcı, 4 saat sürekli | Memory leak yok, latency kayması yok |
| DB performans | pgbench + custom | Büyük tablolar (100K+ kayıt) | Sorgu < 200ms |
| Rapor yükü | Locust | 50 eşzamanlı dashboard isteği | p95 < 2s |

**Locust senaryo örneği:**
```python
class HRUserBehavior(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def view_dashboard(self):
        self.client.get("/api/v1/portal/dashboard")

    @task(2)
    def list_employees(self):
        self.client.get("/api/v1/personnel/employees?page=1&size=20")

    @task(1)
    def create_leave_request(self):
        self.client.post("/api/v1/leave/requests", json={...})

    @task(1)
    def view_payroll_slip(self):
        self.client.get("/api/v1/payroll/my-slips?year=2026&month=1")
```

### 3.5 Güvenlik Testleri

| Test | Araç | Sıklık | Detay |
|------|------|--------|-------|
| OWASP ZAP baseline | OWASP ZAP | Her release | Otomatik, CI entegrasyonu |
| OWASP ZAP full scan | OWASP ZAP | Aylık | Aktif tarama, staging ortamı |
| Penetrasyon testi | Dış firma | 6 aylık | Black-box + grey-box |
| Dependency scan | Snyk | Her CI | Critical/High = blokaj |
| Secret scan | Gitleaks | Her commit | Repo tarihçesi dahil |

---

## 4. Test Veri Yönetimi

### 4.1 Factory Pattern

```python
# tests/factories.py
import factory
from factory.django import DjangoModelFactory

class TenantFactory(DjangoModelFactory):
    class Meta:
        model = Tenant
    name = factory.Sequence(lambda n: f"Firma {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))

class EmployeeFactory(DjangoModelFactory):
    class Meta:
        model = Employee
    tenant = factory.SubFactory(TenantFactory)
    first_name = factory.Faker("first_name", locale="tr_TR")
    last_name = factory.Faker("last_name", locale="tr_TR")
    tckn = factory.Sequence(lambda n: f"{10000000000 + n}")
    email = factory.LazyAttribute(lambda o: f"{o.first_name.lower()}.{o.last_name.lower()}@test.com")
    department = factory.SubFactory(DepartmentFactory)
    hire_date = factory.Faker("date_between", start_date="-5y")

class LeaveRequestFactory(DjangoModelFactory):
    class Meta:
        model = LeaveRequest
    employee = factory.SubFactory(EmployeeFactory)
    leave_type = "annual"
    start_date = factory.Faker("future_date")
    end_date = factory.LazyAttribute(lambda o: o.start_date + timedelta(days=3))
    status = "pending"
```

### 4.2 Seed Data Stratejisi

| Ortam | Veri | Yöntem |
|-------|------|--------|
| Test (CI) | Factory ile her test'te üretilir | Transaction rollback |
| Dev | Örnek tenant + 50 çalışan + 1 yıl veri | `python manage.py seed_dev` |
| Staging | Prod benzeri (anonimleştirilmiş) | `python manage.py load_anonymized` |
| Prod | Boş (fresh) veya migrasyon | — |

### 4.3 Veri Anonimleştirme

| Alan | Yöntem |
|------|--------|
| Ad / Soyad | Faker TR rastgele isim |
| TCKN | Rastgele 11 hane (geçerli checksum) |
| E-posta | `user{id}@test.local` |
| Telefon | `+90 500 000 {random 4}` |
| IBAN | Rastgele format-uyumlu |
| Maaş | ±%20 rastgele sapma |

---

## 5. Kalite Kapıları (Quality Gates)

| Kapı | Kriter | Otomatik |
|------|--------|----------|
| PR açma | Lint + type check başarılı | ✅ |
| PR merge | Unit test + integration test + coverage ≥ %80 (backend) | ✅ |
| Staging deploy | E2E smoke test (10 kritik senaryo) başarılı | ✅ |
| Prod deploy | Staging E2E tam suite + güvenlik taraması temiz + kritik bug açık yok | ✅ + 🔒 onay |
| Release | Performans testi SLA karşılanıyor + penetrasyon testi raporu mevcut | Manuel |

---

## 6. Test Ortamları

| Ortam | DB | Süre | Temizlik |
|-------|-----|------|----------|
| CI (Unit) | SQLite in-memory veya PostgreSQL Docker | ~3 dk | Transaction rollback |
| CI (Integration) | PostgreSQL Docker (services) | ~5 dk | Her test class'ta reset |
| CI (E2E) | PostgreSQL + Redis Docker Compose | ~10 dk | Seed → test → teardown |
| Staging | Managed PostgreSQL | Sürekli | Haftalık reset |

---

## 7. Sorumluluklar

| Rol | Sorumluluk | Araç |
|-----|------------|------|
| Backend Geliştirici | Unit + integration test yazma, coverage koruma | pytest |
| Frontend Geliştirici | Component test + unit test yazma | Jest, RTL |
| QA Mühendisi | E2E test geliştirme, regresyon suite bakımı | Playwright |
| DevOps | CI pipeline ve test ortamı güvenilirliği | GitHub Actions |
| Ürün Sahibi / İK | UAT kabul testi, senaryoları doğrulama | Manuel |
| Güvenlik Mühendisi | Pentest koordinasyonu, OWASP ZAP review | ZAP, Burp |

---

## 8. Test Raporlama

| Rapor | Araç | Sıklık |
|-------|------|--------|
| Coverage raporu | Codecov | Her PR |
| Test sonuç özeti | GitHub Actions summary | Her CI çalışması |
| E2E trace ve screenshot | Playwright HTML report | Başarısızlıkta |
| Performans test raporu | Locust HTML report | Release öncesi |
| Güvenlik tarama raporu | ZAP HTML + Snyk dashboard | Aylık |

---

## 9. Regresyon Stratejisi

| Kural | Açıklama |
|-------|----------|
| Her bug fix ile test | Fix yapılan hata için regression test eklenir |
| Haftalık full suite | Tüm E2E senaryoları staging'de çalıştırılır |
| Release öncesi | Full regression (unit + integration + E2E + performance) |
| Flaky test yönetimi | 3 kez flaky olan test `quarantine` etiketiyle ayrılır, 1 hafta içinde düzeltilir |
