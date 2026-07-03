# Sprint-0 Teknik Task Breakdown

Bu doküman, foundation doküman setinden uygulamaya geçiş için ilk teknik sprintte yapılacak işleri küçük, test edilebilir parçalara böler.

## 1. Sprint-0 hedefi

Sprint-0 sonunda repo şu yeteneklere sahip olmalıdır:

- Çalışan backend app skeleton.
- Health endpoint.
- Tenant context temel modeli.
- Test runner.
- CI için çalıştırılabilir komutlar.
- İleride web/worker/db katmanlarının ekleneceği klasör düzeni.

## 2. İlk teknik kapsam

| Alan | Task | Çıktı |
|---|---|---|
| Repo | Python project metadata | `pyproject.toml` |
| Backend | FastAPI app factory | `backend/app/main.py` |
| Core | Config ve tenant context | `backend/app/core/*` |
| API | Health endpoint | `/health` |
| Test | Pytest health/config tests | `backend/tests/*` |
| Docs | Sprint-0 task breakdown | Bu dosya |

## 3. Kapsam dışı

- Gerçek DB bağlantısı.
- Auth/JWT implementasyonu.
- Employee CRUD.
- Frontend uygulaması.
- Docker/Kubernetes deployment.
- Production-grade observability.

Bunlar Sprint-1 ve sonrası işleridir.

## 4. Sonraki teknik sıra

1. Alembic + PostgreSQL bağlantısı.
2. Tenant tablosu migration.
3. RLS/tenant guard denemesi.
4. User/session modeli.
5. Login endpoint.
6. RBAC permission seed.
7. Employee minimal CRUD.
8. Web admin skeleton.

## 5. Kabul kriterleri

- `uv run pytest` yeşil çalışır.
- Health endpoint app import edildiğinde test edilebilir.
- Config environment değişkenlerinden okunabilir.
- Tenant context için basic validation vardır.
- Repo temiz şekilde commit/push edilir.

## 6. Sprint-0 task listesi

| ID | Task | Kabul |
|---|---|---|
| S0-BE-001 | FastAPI app factory | `create_app()` testte import edilir |
| S0-BE-002 | Health endpoint | `/health` 200 döner |
| S0-BE-003 | Settings modeli | `IK_` prefix'li env okunabilir |
| S0-BE-004 | Tenant context helper | Cache prefix tenant scoped üretir |
| S0-TEST-001 | Pytest konfigürasyonu | `uv run pytest` root'tan çalışır |
| S0-DOC-001 | Uygulama planı | Bu dosya README ağacına eklenir |

## 7. Mimari notlar

Bu iskelet bilerek küçük tutulmuştur. Amaç bir anda tüm HRMS'i kodlamak değil, test edilen ilk yürüyen çekirdeği oluşturmaktır. Bundan sonra her yeni domain modülü aynı kalıpla eklenecektir:

1. Doküman ve kabul kriteri.
2. Model/schema taslağı.
3. Service/repository interface.
4. API endpoint.
5. Permission metadata.
6. Unit/integration test.
7. Audit/event davranışı.

## 8. Sprint-1 hazırlığı

Sprint-1'e geçmeden önce hazırlanacak dosyalar:

- Alembic migration iskeleti.
- PostgreSQL local compose.
- Tenant model migration.
- User/session model taslağı.
- Auth endpoint OpenAPI taslağı.
- Employee minimal model taslağı.

## 9. Riskler

| Risk | Önlem |
|---|---|
| İskelet fazla büyür | Sprint-0 sadece yürüyen çekirdek |
| DB erken karmaşıklaşır | Tenant + user ile sınırlı başlanır |
| Test sonradan eklenir | Her dosya testle birlikte gelir |
| Doküman/kod ayrışır | İlgili docs commit içinde güncellenir |
| Frontend erken şişer | Önce backend contract ve web skeleton |

## 10. Komutlar

Geliştirici lokalinde ilk doğrulama komutları:

```bash
uv run pytest
uv run python -c "from app.main import create_app; print(create_app().title)"
```

Beklenen sonuç:

- Pytest tüm testleri yeşil döndürür.
- App import hatası vermez.
- Health endpoint test client ile 200 döner.

## 11. İlk kodlama prensipleri

Sprint-0 sonrası kod yazarken şu kurallar uygulanmalıdır:

- Tenant bağlamı olmayan domain kodu kabul edilmez.
- API response modelleri açık schema ile dönmelidir; ORM nesnesi doğrudan dışarı verilmez.
- Yeni endpoint için permission metadata ve test planı aynı PR'da olmalıdır.
- Hassas alanlar ilk günden classification ile işaretlenmelidir.
- Background job payload'ları büyük veri değil ID taşımalıdır.
- Import/export gibi uzun işler HTTP request içinde çalıştırılmamalıdır.

## 12. Sprint-0 bitti sayılması için

Sprint-0 yalnız bu commit ile bitmez. Bu commit ilk yürüyen backend çekirdeğidir. Sprint-0'ın tam kapanışı için ayrıca şunlar gerekir:

- CI workflow dosyası eklenir.
- Local PostgreSQL/Redis compose eklenir.
- Alembic migration zinciri başlatılır.
- Tenant migration ve en az bir RLS/guard testi yazılır.
- README'ye lokal geliştirme komutları eklenir.
- İlk auth/user taskları GitHub issue veya backlog dokümanına dökülür.
