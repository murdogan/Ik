# 06 — Sistem Mimarisi

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** Mimari yaklaşım, monorepo yapısı, katman mimarisi, modül organizasyonu, veri akışı, dağıtım topolojisi  
> **Referans:** 04-gereksinim-analizi.md, 05-teknoloji-secimi.md

---

## 1. Amaç

Bu doküman, İnsan Kaynakları Yönetim Sistemi'nin genel sistem mimarisini tanımlar. Mimari yaklaşım, monorepo organizasyonu, backend katman yapısı, modüller arası iletişim kuralları, veri akışı, istemci mimarisi ve dağıtım topolojisi bu dokümanda detaylandırılmıştır.

Mimari kararlar aşağıdaki hedefler doğrultusunda alınmıştır:

- Küçük ekiple hızlı MVP teslimatı
- Tek transaction güvencesiyle tutarlı veri yönetimi
- Operasyonel sadelik ve kolay debug/rollback
- KVKK ve veri lokalizasyonu uyumu
- İleride ölçekleme ve modül ekleme esnekliği

---

## 2. Mimari Yaklaşım: Modüler Monolith

### 2.1 Neden Modüler Monolith?

| Kriter | Microservice | Modüler Monolith | Karar |
|--------|-------------|------------------|-------|
| Geliştirme hızı | Yavaş (servisler arası kontrat, deploy koordinasyonu) | Hızlı (tek codebase, tek deploy) | **Monolith** |
| Debug ve hata takibi | Dağıtık trace gerektirir | Tek log, tek stack trace | **Monolith** |
| Transaction yönetimi | Saga pattern, eventual consistency | Tek DB transaction, anında rollback | **Monolith** |
| Operasyonel yük | Yüksek (servis başına container, network, monitoring) | Düşük (tek container, tek DB) | **Monolith** |
| Ekip büyüklüğü uyumu | Büyük ekipler için avantajlı | Küçük ekipler için ideal | **Monolith** |
| Gelecek esnekliği | Baştan dağıtık | Modül sınırları iyi çizilirse ileride ayrıştırılabilir | **Monolith** |

### 2.2 Modüler Monolith Prensipleri

1. **Tek deployable unit:** Backend tek bir FastAPI uygulaması olarak deploy edilir.
2. **Tek veritabanı:** Tüm modüller aynı PostgreSQL veritabanını paylaşır.
3. **Kod seviyesinde modül ayrımı:** Her domain kendi klasörü altında izole edilir.
4. **Doğrudan fonksiyon çağrısı:** Modüller arası iletişim Python import/çağrı ile yapılır. Event bus, message queue veya RPC kullanılmaz.
5. **Tek transaction:** Bir iş akışındaki tüm veritabanı işlemleri tek transaction'da çalışır, hata durumunda otomatik rollback gerçekleşir.
6. **Net modül sınırları:** Her modül kendi service katmanı üzerinden erişilir; bir modül başka bir modülün repository veya model katmanına doğrudan erişmez.

---

## 3. Monorepo Yapısı

Tüm proje tek bir Git reposunda tutulur. Bu sayede API değişikliği, frontend güncellemesi ve mobil uyum tek commit'te senkron kalır.

```
ik-yonetim/
│
├── apps/
│   ├── api/                          # FastAPI backend (modüler monolith)
│   │   ├── app/
│   │   │   ├── core/                 # Çekirdek altyapı
│   │   │   │   ├── config.py         # Ortam ayarları, env yönetimi
│   │   │   │   ├── security.py       # JWT, hashing, MFA yardımcıları
│   │   │   │   ├── database.py       # SQLAlchemy engine, session factory
│   │   │   │   ├── dependencies.py   # Ortak dependency injection
│   │   │   │   ├── middleware.py     # Tenant context, CORS, request logging
│   │   │   │   └── exceptions.py    # Global hata sınıfları ve handler'lar
│   │   │   │
│   │   │   ├── modules/              # Domain modülleri
│   │   │   │   ├── auth/
│   │   │   │   ├── tenant/
│   │   │   │   ├── personnel/
│   │   │   │   ├── leave/
│   │   │   │   ├── payroll/
│   │   │   │   ├── performance/
│   │   │   │   ├── recruitment/
│   │   │   │   ├── training/
│   │   │   │   ├── shift/
│   │   │   │   ├── organization/
│   │   │   │   ├── notification/
│   │   │   │   ├── reporting/
│   │   │   │   ├── document/
│   │   │   │   └── integration/
│   │   │   │
│   │   │   ├── shared/               # Modüller arası ortak yapılar
│   │   │   │   ├── base_model.py     # Ortak SQLAlchemy base (id, tenant_id, timestamps)
│   │   │   │   ├── pagination.py     # Sayfalama yardımcıları
│   │   │   │   ├── audit.py          # Audit log mixin ve utility
│   │   │   │   └── enums.py          # Ortak enum tanımları
│   │   │   │
│   │   │   └── main.py               # FastAPI app entry point, router registration
│   │   │
│   │   ├── workers/                  # Celery task tanımları
│   │   │   ├── celery_app.py
│   │   │   ├── notification_tasks.py
│   │   │   ├── payroll_tasks.py
│   │   │   ├── document_tasks.py
│   │   │   └── import_tasks.py
│   │   │
│   │   ├── migrations/               # Alembic migration dosyaları
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   │
│   │   ├── tests/                    # Backend testleri
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── conftest.py
│   │   │
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   ├── web/                          # Next.js 15 frontend
│   │   ├── src/
│   │   │   ├── app/                  # App Router sayfaları
│   │   │   │   ├── (auth)/           # Login, şifre sıfırlama
│   │   │   │   ├── (admin)/          # İK yönetici paneli
│   │   │   │   ├── (portal)/         # Çalışan self-servis
│   │   │   │   └── (manager)/        # Departman yöneticisi
│   │   │   ├── components/           # UI bileşenleri
│   │   │   │   ├── ui/              # shadcn/ui base bileşenler
│   │   │   │   └── modules/         # Modül bazlı bileşenler
│   │   │   ├── lib/                  # Yardımcı fonksiyonlar, API client
│   │   │   ├── hooks/                # Custom React hooks
│   │   │   ├── stores/               # Zustand state yönetimi
│   │   │   └── types/                # TypeScript tip tanımları
│   │   ├── package.json
│   │   └── Dockerfile
│   │
│   └── mobile/                       # Flutter mobil uygulama
│       ├── lib/
│       │   ├── core/                 # Tema, routing, DI, network
│       │   ├── features/             # Modül bazlı ekranlar
│       │   │   ├── auth/
│       │   │   ├── leave/
│       │   │   ├── shift/
│       │   │   ├── notification/
│       │   │   ├── personnel/
│       │   │   └── approval/
│       │   └── shared/               # Ortak widget'lar, modeller
│       ├── pubspec.yaml
│       └── Dockerfile                # CI/CD build için
│
├── packages/
│   └── api-client/                   # OpenAPI'den üretilmiş TypeScript client
│       ├── generated/
│       └── package.json
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.web
│   │   ├── Dockerfile.worker
│   │   └── nginx/
│   │       └── nginx.conf
│   ├── docker-compose.yml            # Lokal geliştirme
│   ├── docker-compose.prod.yml       # Prod ortamı
│   └── monitoring/
│       ├── prometheus.yml
│       └── grafana/
│           └── dashboards/
│
├── scripts/
│   ├── seed.py                       # Test verisi oluşturma
│   ├── generate-api-client.sh        # OpenAPI → TypeScript client
│   └── backup.sh                     # DB yedekleme scripti
│
├── docs/                             # Proje dokümanları (mevcut klasör)
├── .github/
│   └── workflows/
│       ├── api.yml                   # Backend CI/CD
│       ├── web.yml                   # Frontend CI/CD
│       └── mobile.yml                # Flutter CI/CD
│
├── Makefile                          # Ortak komutlar
├── .gitignore
└── README.md
```

### 3.1 Monorepo Avantajları

- **Tek commit senkronizasyonu:** API endpoint değişikliği + frontend form güncellemesi + mobil ekran uyumu aynı PR'da yapılır.
- **Otomatik API client üretimi:** FastAPI'nin OpenAPI spec'i → TypeScript client (web) ve Dart client (mobile) otomatik üretilir.
- **Ortak CI/CD:** GitHub Actions path-filtered workflow'lar ile sadece değişen parça build/test edilir.
- **Kolay onboarding:** Yeni geliştirici `make dev` ile tüm sistemi ayağa kaldırır.

### 3.2 Monorepo Araç Seçimi

| Alan | Araç | Gerekçe |
|------|------|---------|
| Python bağımlılık yönetimi | uv | Hızlı kurulum, lockfile desteği, pyproject.toml uyumu |
| Node.js bağımlılık yönetimi | pnpm workspace | Disk verimli, monorepo workspace desteği |
| Flutter | Standart Flutter CLI | Ek araç gerekmiyor |
| Ortak komutlar | Makefile | `make dev`, `make test`, `make migrate`, `make build` |
| CI/CD | GitHub Actions | Path-filter ile seçici pipeline tetikleme |

---

## 4. Backend Katman Mimarisi

### 4.1 Katman Yapısı

Her backend modülü dört katmanlı bir yapıda organize edilir:

```
İstek Akışı:

HTTP İsteği
    │
    ▼
┌─────────────────────┐
│   Router (router.py) │  ← Endpoint tanımları, HTTP method, path, response model
│   Controller Katmanı │  ← Request parsing, response formatting
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Service (service.py)│  ← İş mantığı, validasyon, yetkilendirme kontrolleri
│  Business Katmanı    │  ← Diğer modüllerin service'lerini çağırabilir
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────┐
│ Repository (repository.py)│  ← Veritabanı sorguları, CRUD operasyonları
│ Data Access Katmanı       │  ← SQLAlchemy query'leri
└──────────┬────────────────┘
           │
           ▼
┌─────────────────────────┐
│  Models (models.py)      │  ← SQLAlchemy tablo tanımları
│  Schemas (schemas.py)    │  ← Pydantic request/response modelleri
└─────────────────────────┘
```

### 4.2 Modül İç Yapısı

Her modül aşağıdaki dosyalardan oluşur:

```
modules/leave/
├── __init__.py
├── router.py          # API endpoint tanımları
├── service.py         # İş mantığı
├── repository.py      # Veritabanı sorguları
├── models.py          # SQLAlchemy tablo tanımları
├── schemas.py         # Pydantic request/response modelleri
├── dependencies.py    # Modüle özel dependency injection
└── exceptions.py      # Modüle özel hata sınıfları
```

### 4.3 Katman Kuralları

| Kural | Açıklama |
|-------|----------|
| Router sadece Service'i çağırır | Router içinde doğrudan DB sorgusu veya iş mantığı yazılmaz |
| Service iş mantığını yönetir | Validasyon, yetkilendirme, iş kuralları burada uygulanır |
| Service başka modülün Service'ini çağırabilir | `payroll/service.py` → `leave/service.py` doğrudan import |
| Repository sadece kendi modülünün modeline erişir | Başka modülün tablosuna doğrudan sorgu atmaz |
| Schemas dışarıya açılan kontratı tanımlar | Request/response modelleri, iç modelleri (SQLAlchemy) dışarıya sızdırmaz |
| Exceptions modüle özeldir | Her modül kendi hata tiplerini tanımlar, global handler yakalar |

### 4.4 Modüller Arası İletişim

Modüller arası iletişim doğrudan Python fonksiyon çağrısı ile yapılır:

```python
# payroll/service.py
from app.modules.leave.service import LeaveService
from app.modules.shift.service import ShiftService
from app.modules.personnel.service import PersonnelService

class PayrollService:
    def __init__(
        self,
        payroll_repo: PayrollRepository,
        personnel_service: PersonnelService,
        leave_service: LeaveService,
        shift_service: ShiftService,
    ):
        self._payroll_repo = payroll_repo
        self._personnel = personnel_service
        self._leave = leave_service
        self._shift = shift_service

    async def calculate_salary(self, employee_id: int, period: str):
        employee = await self._personnel.get_employee(employee_id)
        leaves = await self._leave.get_leaves_for_period(employee_id, period)
        shifts = await self._shift.get_worked_hours(employee_id, period)

        # Tek transaction içinde hesaplama
        gross = employee.base_salary
        deductions = self._calculate_deductions(gross, leaves)
        net = gross - deductions

        return await self._payroll_repo.save_payslip(employee_id, period, gross, net)
```

**İletişim Kuralları:**

1. Bir modül, başka modülün **Service** katmanını çağırır.
2. Başka modülün **Repository** veya **Model** katmanına doğrudan erişilmez.
3. Tüm modüller arası çağrılar aynı **DB session/transaction** içinde çalışır.
4. Hata durumunda tüm transaction otomatik rollback olur.

### 4.5 Arka Plan İşleri (Celery)

Uzun süren veya asenkron işler Celery worker'larında çalıştırılır. Bu işler ana transaction'dan bağımsızdır:

| İş Türü | Tetikleyici | Worker Task |
|---------|-------------|-------------|
| E-posta / SMS / Push gönderimi | İzin onayı, bordro hazır, hatırlatma | `notification_tasks.py` |
| Bordro PDF üretimi | Aylık bordro hesaplaması sonrası | `payroll_tasks.py` |
| Toplu Excel import | İK kullanıcısı dosya yüklediğinde | `import_tasks.py` |
| Rapor üretimi | Zamanlanmış veya kullanıcı talebiyle | `reporting_tasks.py` |
| Belge dönüştürme | Sözleşme şablonu → PDF | `document_tasks.py` |

```python
# İzin onaylandıktan sonra bildirim gönderimi
class LeaveService:
    async def approve_leave(self, leave_id: int, approver_id: int):
        leave = await self._repo.get_by_id(leave_id)
        leave.status = LeaveStatus.APPROVED
        leave.approved_by = approver_id
        await self._repo.save(leave)

        # Bildirim arka planda gönderilir
        send_notification.delay(
            user_id=leave.employee_id,
            template="leave_approved",
            data={"start": leave.start_date, "end": leave.end_date}
        )
```

---

## 5. Veritabanı Mimarisi

### 5.1 Tek Veritabanı Yaklaşımı

Tüm modüller tek bir PostgreSQL veritabanını paylaşır. Tablolar modül bazlı öneklerle adlandırılır:

| Modül | Tablo Önek Örnekleri |
|-------|---------------------|
| auth | `auth_users`, `auth_sessions`, `auth_roles` |
| tenant | `tenant_companies`, `tenant_branches` |
| personnel | `personnel_employees`, `personnel_contracts`, `personnel_documents` |
| leave | `leave_types`, `leave_requests`, `leave_balances` |
| payroll | `payroll_payslips`, `payroll_parameters`, `payroll_deductions` |
| shift | `shift_templates`, `shift_assignments`, `shift_attendance` |
| organization | `org_departments`, `org_positions`, `org_hierarchy` |
| notification | `notif_templates`, `notif_logs` |

### 5.2 Multi-Tenant Stratejisi

```
┌─────────────────────────────────────────────────┐
│              Tek PostgreSQL Veritabanı           │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Tenant A │  │ Tenant B │  │ Tenant C │      │
│  │  (Şirket) │  │  (Şirket) │  │  (Şirket) │      │
│  │ tenant_id │  │ tenant_id │  │ tenant_id │      │
│  │  = 1      │  │  = 2      │  │  = 3      │      │
│  └──────────┘  └──────────┘  └──────────┘      │
│                                                  │
│  Her tablo tenant_id kolonu içerir               │
│  Her sorgu WHERE tenant_id = ? filtresi taşır    │
└─────────────────────────────────────────────────┘
```

**Tenant izolasyonu iki katmanda sağlanır:**

1. **Uygulama katmanı (birincil):** SQLAlchemy global query filter ile her sorguya otomatik `tenant_id` filtresi eklenir. Middleware, gelen isteğin JWT'sindeki tenant bilgisini çıkarır ve request context'e yazar.

2. **Veritabanı katmanı (kritik tablolar):** Bordro, özlük bilgileri ve audit log gibi hassas tablolarda PostgreSQL Row Level Security (RLS) ek güvence olarak devreye alınır.

```python
# shared/base_model.py
class TenantBaseModel(Base):
    __abstract__ = True

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenant_companies.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

### 5.3 Audit Log

Tüm kritik veri değişiklikleri audit log tablosunda kaydedilir:

| Alan | Açıklama |
|------|----------|
| `tenant_id` | Hangi şirket |
| `user_id` | İşlemi yapan kullanıcı |
| `action` | CREATE, UPDATE, DELETE |
| `table_name` | Etkilenen tablo |
| `record_id` | Etkilenen kaydın ID'si |
| `old_values` | Önceki değerler (JSONB) |
| `new_values` | Yeni değerler (JSONB) |
| `ip_address` | İstek kaynağı |
| `timestamp` | İşlem zamanı |

---

## 6. İstemci Mimarisi

### 6.1 Web Frontend (Next.js 15)

Tek bir Next.js uygulaması, rol bazlı routing ile farklı kullanıcı deneyimlerini sunar:

```
src/app/
├── (auth)/                    # Giriş, şifre sıfırlama, MFA
│   ├── login/
│   └── reset-password/
│
├── (admin)/                   # İK Yöneticisi / Süper Admin
│   ├── dashboard/
│   ├── personnel/
│   ├── leave-management/
│   ├── payroll/
│   ├── recruitment/
│   ├── reports/
│   ├── settings/
│   └── layout.tsx             # Admin sidebar, header
│
├── (portal)/                  # Çalışan Self-Servis
│   ├── my-profile/
│   ├── my-leaves/
│   ├── my-payslips/
│   ├── my-shifts/
│   ├── announcements/
│   └── layout.tsx             # Portal sidebar, header
│
├── (manager)/                 # Departman Yöneticisi
│   ├── team/
│   ├── approvals/
│   ├── team-calendar/
│   └── layout.tsx             # Manager sidebar, header
│
└── layout.tsx                 # Root layout, providers
```

**Frontend Veri Akışı:**

```
Kullanıcı Etkileşimi
    │
    ▼
React Component (Client/Server Component)
    │
    ▼
TanStack Query (cache, refetch, optimistic update)
    │
    ▼
API Client (OpenAPI'den üretilmiş, type-safe)
    │
    ▼
FastAPI Backend (/api/v1/...)
```

- **Server Components:** Veri okuma ağırlıklı ekranlar (dashboard, listeler, raporlar)
- **Client Components:** Form, modal, takvim, sürükle-bırak gibi etkileşimli alanlar
- **Zustand:** Sidebar durumu, kullanıcı tercihleri gibi yerel UI state
- **TanStack Query:** Tüm API verileri, cache yönetimi, background refetch

### 6.2 Mobil Uygulama (Flutter)

Flutter uygulaması çalışan ve yönetici odaklı işlemlere odaklanır:

```
lib/
├── core/
│   ├── theme/                # Renk, tipografi, spacing
│   ├── router/               # GoRouter ile navigasyon
│   ├── network/              # Dio HTTP client, interceptor'lar
│   ├── di/                   # Riverpod provider tanımları
│   └── storage/              # Hive ile yerel saklama
│
├── features/
│   ├── auth/                 # Giriş, biyometrik, MFA
│   ├── leave/                # İzin talebi, bakiye, takvim
│   ├── shift/                # Vardiya görüntüleme, check-in/out
│   ├── approval/             # Onay bekleyen talepler
│   ├── notification/         # Bildirim merkezi
│   ├── profile/              # Profil görüntüleme/düzenleme
│   ├── payslip/              # Bordro görüntüleme
│   └── announcement/         # Duyurular
│
└── shared/
    ├── widgets/              # Ortak bileşenler
    └── models/               # Ortak veri modelleri
```

**Offline Destek:**

Kritik ekranlar (vardiya programı, izin bakiyesi, profil bilgileri) yerel olarak cache'lenir. İnternet olmadığında son senkronize edilen veri gösterilir, bağlantı gelince otomatik güncellenir.

---

## 7. API Kontrat Paylaşımı

Monorepo'nun en büyük avantajlarından biri API kontratlarının otomatik paylaşımıdır:

```
FastAPI Backend
    │
    │  Otomatik OpenAPI spec üretimi
    ▼
openapi.json
    │
    ├──► openapi-typescript-codegen  ──►  packages/api-client/  ──►  Next.js Web
    │
    └──► openapi-generator (dart)    ──►  mobile/lib/core/network/  ──►  Flutter App
```

**Akış:**

1. FastAPI, Pydantic schema'lardan otomatik `openapi.json` üretir.
2. `make generate-client` komutu TypeScript ve Dart client'larını yeniden üretir.
3. Web ve mobil uygulamalar type-safe, güncel client ile API'ye erişir.
4. API'de breaking change olduğunda frontend/mobile derleme hatası verir — sorun commit öncesi yakalanır.

---

## 8. Güvenlik Mimarisi

### 8.1 Kimlik Doğrulama Akışı

```
İstemci (Web/Mobil)
    │
    │  POST /api/v1/auth/login  {email, password}
    ▼
FastAPI Auth Modülü
    │
    ├── Şifre doğrulama (bcrypt)
    ├── MFA kontrolü (etkinse TOTP doğrulama)
    ├── Rate limit kontrolü (Redis)
    │
    ▼
JWT Token Çifti Üretimi
    ├── Access Token  (15 dk ömür, kullanıcı bilgileri + roller + tenant_id)
    └── Refresh Token (7 gün ömür, DB'de saklanır, tek kullanımlık)
```

### 8.2 İstek Yetkilendirme Akışı

```
Her API İsteği
    │
    │  Authorization: Bearer <access_token>
    ▼
Auth Middleware
    ├── JWT doğrulama (imza, süre)
    ├── Tenant context çıkarma
    ├── Rate limit kontrolü
    │
    ▼
RBAC Kontrolü
    ├── Endpoint erişim izni (rol bazlı)
    ├── Veri erişim izni (tenant bazlı)
    │
    ▼
İstek İşleme
```

### 8.3 Rol Yapısı

| Rol | Erişim Kapsamı |
|-----|---------------|
| Süper Admin | Tüm tenant verileri, sistem ayarları, kullanıcı yönetimi |
| İK Yöneticisi | Kendi tenant'ındaki tüm İK modülleri |
| Departman Yöneticisi | Kendi departmanındaki çalışanların verileri, onay işlemleri |
| Çalışan | Kendi profili, izin talebi, bordro görüntüleme, self-servis |
| C-Level | Dashboard, raporlar, üst düzey görünüm |

---

## 9. Dağıtım Topolojisi

### 9.1 Geliştirme Ortamı (Lokal)

```
docker-compose.yml ile tek komutta ayağa kalkar:

┌──────────────────────────────────────────────────────┐
│                  Docker Compose                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ FastAPI   │  │ Celery   │  │ Next.js  │           │
│  │ :8000     │  │ Worker   │  │ :3000    │           │
│  └─────┬────┘  └─────┬────┘  └──────────┘           │
│        │              │                               │
│  ┌─────┴──────────────┴────┐                         │
│  │                          │                         │
│  │  ┌────────┐ ┌────────┐  │                         │
│  │  │ Postgres│ │ Redis  │  │                         │
│  │  │ :5432   │ │ :6379  │  │                         │
│  │  └────────┘ └────────┘  │                         │
│  │  ┌────────┐ ┌────────┐  │                         │
│  │  │ MinIO  │ │ MailHog│  │                         │
│  │  │ :9000  │ │ :1025  │  │                         │
│  │  └────────┘ └────────┘  │                         │
│  └──────────────────────────┘                         │
└──────────────────────────────────────────────────────┘
```

### 9.2 Üretim Ortamı (MVP)

MVP aşamasında tek sunucu + Docker Compose ile başlanır:

```
                    İnternet
                       │
                       ▼
              ┌────────────────┐
              │     Nginx      │
              │  (Reverse Proxy│
              │   SSL/TLS 1.3) │
              └───────┬────────┘
                      │
        ┌─────────────┼──────────────┐
        │             │              │
        ▼             ▼              ▼
  ┌──────────┐ ┌──────────┐  ┌──────────┐
  │ Next.js  │ │ FastAPI  │  │ FastAPI  │
  │ (SSR)    │ │ Instance │  │ Instance │
  │          │ │    #1    │  │    #2    │
  └──────────┘ └────┬─────┘  └────┬─────┘
                    │              │
              ┌─────┴──────────────┘
              │
        ┌─────┴─────┐
        │            │
   ┌────┴───┐  ┌────┴───┐
   │Postgres│  │ Redis  │
   │  (Ana) │  │        │
   └────┬───┘  └────────┘
        │
   ┌────┴───┐
   │Postgres│     ┌────────┐    ┌────────┐
   │(Replica│     │ MinIO  │    │ Celery │
   │ Read)  │     │        │    │ Worker │
   └────────┘     └────────┘    └────────┘
```

**Nginx Sorumlulukları:**

| Görev | Açıklama |
|-------|----------|
| SSL Termination | Let's Encrypt ile TLS 1.3 |
| Reverse Proxy | `/api/*` → FastAPI, `/` → Next.js |
| Static Files | Next.js build çıktıları, cache header'ları |
| Rate Limiting | Temel düzeyde istek sınırlama |
| WebSocket/SSE Proxy | Bildirim kanallarını yönlendirme |

### 9.3 Ölçekleme Yolu

MVP sonrası ihtiyaç durumunda adım adım ölçeklenir:

```
Faz 1 (MVP):      Tek sunucu, Docker Compose
                        │
Faz 2:              2-3 sunucu ayrımı
                    (API+Worker | DB+Redis | MinIO+Nginx)
                        │
Faz 3:              Container orkestrasyon (Docker Swarm veya K8s)
                    Yatay pod ölçekleme
                        │
Faz 4:              Managed DB (RDS/CloudSQL), CDN, Load Balancer
```

---

## 10. Gözlemlenebilirlik

### 10.1 Katmanlı İzleme

```
┌──────────────────────────────────────┐
│            Grafana Dashboard          │
│  (İK Metrikleri, Sistem Sağlığı)     │
└──────────────┬───────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Prometheus│ │ Sentry │ │ Uygulama│
│ Metrik  │ │ Hata   │ │  Logları│
│ Toplama │ │ Takibi │ │ (JSON) │
└────────┘ └────────┘ └────────┘
```

| Katman | Araç | İzlenen |
|--------|------|---------|
| Metrikler | Prometheus | API yanıt süreleri, istek sayıları, DB bağlantı havuzu, Celery kuyruk derinliği |
| Hatalar | Sentry | Uygulama hataları, stack trace, kullanıcı bağlamı |
| Loglar | Yapılandırılmış JSON log | İstek/yanıt logları, iş mantığı logları, audit trail |
| Dashboard | Grafana | Sistem sağlığı, performans trendleri, iş metrikleri |

### 10.2 Kritik Alarm Kuralları

| Alarm | Koşul | Aksiyon |
|-------|-------|---------|
| API yanıt süresi | p95 > 500ms (5 dk) | Slack bildirimi |
| Hata oranı | 5xx > %1 (5 dk) | Slack + e-posta |
| DB bağlantı havuzu | Kullanım > %80 | Slack bildirimi |
| Celery kuyruk derinliği | > 1000 bekleyen iş (10 dk) | Slack bildirimi |
| Disk kullanımı | > %85 | Slack + e-posta |

---

## 11. Realtime İletişim

### 11.1 Kanal Seçimi

| İhtiyaç | Teknoloji | Gerekçe |
|---------|-----------|---------|
| Bildirimler (izin onayı, duyuru, hatırlatma) | SSE (Server-Sent Events) | Tek yönlü, basit, HTTP uyumlu, yeterli |
| Onay bekleyen sayacı güncelleme | SSE | Anlık badge güncelleme |

WebSocket şu an gerekli değildir. SSE tüm bildirim senaryolarını karşılar. İleride canlı sohbet veya collaborative düzenleme gibi çift yönlü iletişim gerekirse WebSocket eklenebilir.

### 11.2 SSE Akışı

```
İstemci (Web/Mobil)
    │
    │  GET /api/v1/notifications/stream
    │  Accept: text/event-stream
    ▼
FastAPI SSE Endpoint
    │
    │  Redis Pub/Sub dinleme
    ▼
Redis Channel: notifications:{user_id}
    │
    ▲
Celery Worker / Service
    │
    │  İzin onayı, bordro hazır, duyuru vb.
    └── Redis PUBLISH
```

---

## 12. Ortam Yönetimi

### 12.1 Ortamlar

| Ortam | Amaç | Altyapı |
|-------|------|---------|
| Local (dev) | Geliştirici makinesi | Docker Compose, hot-reload |
| Staging | Test ve demo | Prod benzeri, seed data |
| Production | Canlı ortam | Tam altyapı, yedekleme, monitoring |

### 12.2 Konfigürasyon Yönetimi

- Her ortam için `.env` dosyası (`.env.local`, `.env.staging`, `.env.production`)
- Hassas değerler (DB şifresi, JWT secret, API key'ler) ortam değişkenlerinde tutulur
- Uygulama konfigürasyonu `core/config.py`'de Pydantic Settings ile yönetilir
- Docker Compose ortam değişkenlerini `.env` dosyasından okur

---

## 13. Gereksinimlerle Uyum

| Gereksinim | Mimari Karşılığı |
|------------|-----------------|
| Hızlı MVP geliştirme | Modüler monolith, tek deploy, tek DB |
| Kolay debug ve rollback | Tek transaction, tek log, tek stack trace |
| 1.000 eşzamanlı kullanıcı | Stateless API, Nginx load balancing, Redis cache |
| 100.000+ çalışan kaydı | PostgreSQL indeksleme, pagination, lazy loading |
| KVKK / veri lokalizasyonu | Self-host PostgreSQL + MinIO + Docker, Türkiye sunucusu |
| Multi-tenant | Shared DB + tenant_id + SQLAlchemy global filter + RLS |
| Web + Mobil | Tek API, OpenAPI kontrat paylaşımı, Next.js + Flutter |
| RBAC + Audit | Auth modülü, middleware, audit log tablosu |
| Arka plan işleri | Celery + Redis, modül bazlı task dosyaları |
| Entegrasyonlar (SGK, banka, PDKS) | Integration modülü, adaptör pattern |
| Ölçekleme esnekliği | Container bazlı, yatay ölçeklemeye hazır |

---

## 14. Riskler ve Önlemler

| Risk | Etki | Önlem |
|------|------|-------|
| Monolith büyüdükçe karmaşıklık artması | Geliştirme hızının düşmesi | Net modül sınırları, katman kurallarına uyum, code review |
| Tek DB'de performans darboğazı | Sorgu yavaşlaması | İndeksleme stratejisi, read replica, materialized view |
| Celery worker yükünün artması | İş kuyruğunda birikim | Worker sayısını artırma, öncelikli kuyruklar |
| Monorepo'da CI/CD süresinin uzaması | Yavaş pipeline | Path-filter ile sadece değişen parçayı build/test etme |
| Tenant veri sızıntısı | Güvenlik ihlali | Global query filter + RLS + düzenli güvenlik testi |

---

## 15. Sonuç

Sistem mimarisi aşağıdaki temel kararlar üzerine inşa edilmiştir:

- **Modüler monolith:** Tek deployable unit, tek DB, doğrudan fonksiyon çağrısı ile modüller arası iletişim
- **Monorepo:** API, web ve mobil tek repoda; otomatik OpenAPI kontrat paylaşımı
- **Dört katmanlı backend:** Router → Service → Repository → Model, net sorumluluk ayrımı
- **Tek transaction güvencesi:** Rollback otomatik, saga pattern gereksiz
- **Nginx reverse proxy:** SSL, routing, rate limiting — API Gateway'e gerek yok
- **Celery arka plan işleri:** Bildirim, PDF, import, rapor — event bus gereksiz
- **Adım adım ölçekleme:** Docker Compose → çoklu sunucu → Kubernetes

Bu mimari ile bir sonraki adımda [07-veritabani-tasarimi.md](07-veritabani-tasarimi.md) dokümanında tablo yapıları, ilişkiler, indeksleme stratejisi ve migration yaklaşımı detaylandırılacaktır.
