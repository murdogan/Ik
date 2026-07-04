# Sprint-0 / Sprint-1 Backlog ve Task Planı

Bu doküman, IK Platform'da kodlamaya geçmeden önce ilk iki sprintin iş kırılımını, bağımlılıklarını, kabul kriterlerini ve teslim ritmini netleştirir. Amaç, geliştiricinin “nereden başlayacağız?” sorusunu yoruma bırakmamaktır.

## 1. Kapsam

Kapsam içi:

- Sprint-0 ve Sprint-1 teknik/ürün backlog'u.
- Task öncelikleri.
- Bağımlılıklar.
- Kabul kriterleri.
- Test/doğrulama notları.
- Commit/PR sırası önerisi.

Kapsam dışı:

- Kod implementasyonu.
- Gerçek müşteri verisi.
- UI tasarım dosyası üretimi.
- Canlı ortam kurulumu.

## 2. Sprint-0 hedefi

Sprint-0 hedefi: teknik iskeleti, çalışma standardını ve ilk güvenlik/tenant omurgasını kurmak.

Çıkış kriterleri:

- Lokal geliştirme komutları net.
- Backend health endpoint çalışır.
- DB migration zinciri başlar.
- Tenant ve user veri modeli tanımlıdır.
- Test runner ve kalite kapısı çalışır.
- İlk task listesi GitHub/Jira'ya taşınabilir durumdadır.

## 3. Sprint-0 backlog

| ID | Başlık | Öncelik | Bağımlılık | Kabul kriteri |
|---|---|---:|---|---|
| S0-001 | Repo standardı ve lokal komutlar | P0 | Yok | README lokal kurulum komutlarını içerir |
| S0-002 | Backend app skeleton | P0 | S0-001 | App import edilir, `/health` 200 döner |
| S0-003 | Test/ruff kalite kapısı | P0 | S0-002 | Test ve lint komutları yeşil çalışır |
| S0-004 | DB migration altyapısı | P0 | S0-001 | Alembic history görünür |
| S0-005 | Tenant modeli | P0 | S0-004 | Tenant migration ve model testleri vardır |
| S0-006 | User modeli | P0 | S0-005 | Tenant bazlı user email unique planlanır |
| S0-007 | Auth endpoint taslak sözleşmesi | P0 | S0-006 | OpenAPI taslağı docs içinde yazılıdır |
| S0-008 | Employee minimal model taslağı | P1 | S0-005 | ERD/migration planında alanlar netleşir |
| S0-009 | CI workflow hazırlığı | P1 | S0-003 | Workflow template hazırdır |
| S0-010 | Sprint-1 backlog refinement | P0 | Tüm S0 | Sprint-1 story'leri DoR seviyesindedir |

## 4. Sprint-1 hedefi

Sprint-1 hedefi: auth + tenant + employee minimal dikey kesitini planlı şekilde uygulamaya hazır hale getirmek.

Sprint-1 sonunda beklenen ürün davranışı:

- Tenant oluşturma/seed akışı tanımlıdır.
- User invite/login veri sözleşmesi tanımlıdır.
- Employee minimal CRUD kapsamı netleşmiştir.
- Permission modeli ilk sürümde hangi endpointleri koruyacak belli olur.

## 5. Sprint-1 backlog

| ID | Başlık | Öncelik | Bağımlılık | Kabul kriteri |
|---|---|---:|---|---|
| S1-001 | Auth API endpoint sözleşmeleri | P0 | S0-007 | Login, refresh, logout, me endpointleri tanımlı |
| S1-002 | Password hashing tasarımı | P0 | S1-001 | Argon2id/bcrypt kararı ve test kriteri net |
| S1-003 | Session/refresh token modeli | P0 | S1-001 | Token rotation alanları migration planında |
| S1-004 | RBAC seed planı | P0 | S0-006 | employee, manager, hr, tenant_admin rolleri net |
| S1-005 | Employee minimal schema | P0 | S0-008 | Zorunlu alanlar ve validation kuralları yazılı |
| S1-006 | Employee CRUD endpoint taslağı | P0 | S1-005 | List/create/read/update endpointleri tanımlı |
| S1-007 | Tenant isolation test planı | P0 | S0-005 | Tenant A/B negatif testleri listeli |
| S1-008 | Audit event ilk sözlük | P1 | S1-001 | auth.login, employee.created gibi eventler net |
| S1-009 | Web admin ilk ekran planı | P1 | S1-006 | Login + employee list wireframe hazır |
| S1-010 | Demo seed verisi planı | P1 | S1-005 | 2 tenant, 5 kullanıcı, 20 çalışan seed planı |

## 6. Story formatı

Her story şu formatla açılmalıdır:

```text
Bir <rol> olarak, <işlem> yapmak istiyorum; böylece <değer>.
```

Her story şunları içermelidir:

- Rol.
- Veri etkisi.
- API etkisi.
- Yetki etkisi.
- KVKK/güvenlik etkisi.
- Test kabul kriteri.
- Demo senaryosu.

## 7. Sprint-1 öncesi DoR kontrolü

- Auth endpointleri OpenAPI taslağında var.
- Employee minimal alanları ERD planında var.
- RBAC ilk rol listesi net.
- Tenant isolation test yaklaşımı yazılı.
- UI ilk iki ekran akışı yazılı.
- Veri import şablonlarında employee zorunlu alanları belli.

## 8. Teslim sırası önerisi

1. Auth/session veri sözleşmesi.
2. RBAC seed ve permission naming.
3. Employee minimal model.
4. Employee endpoint sözleşmeleri.
5. Tenant isolation test senaryoları.
6. Admin web ilk akış planı.
7. Demo seed planı.

## 9. Riskler

| Risk | Azaltım |
|---|---|
| Sprint-1 çok teknik kalır | Her task demo davranışına bağlanır |
| Auth kapsamı şişer | SSO/MFA ileri seviye V1'e bırakılır |
| Employee modeli fazla detaylanır | MVP minimal alan setiyle başlanır |
| Testler unutulur | DoD test maddesi zorunlu |
| UI/API ayrışır | OpenAPI taslağı ekran akışlarıyla birlikte güncellenir |

## 10. İlgili dokümanlar

- [Sprint-0 Teknik Task Breakdown](01-sprint-0-teknik-task-breakdown.md)
- [OpenAPI Endpoint Taslağı](03-openapi-endpoint-taslagi.md)
- [ERD ve Migration Uygulama Planı](04-erd-migration-uygulama-plani.md)
- [Wireframe ve Ekran Akış Planı](05-wireframe-ekran-akis-plani.md)
