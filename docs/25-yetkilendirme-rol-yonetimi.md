# 25 — Yetkilendirme & Rol Yönetimi

> **Hazırlanma Tarihi:** 10 Nisan 2026  
> **Kapsam:** RBAC modeli, izin matrisi, tenant bazlı roller, kapsam (scope) mantığı, hiyerarşik yetki, delegasyon ve denetim  
> **Faz:** Faz 5

---

## 1. Amaç

Bu doküman, sistem genelinde rol bazlı erişim kontrolünün nasıl çalışacağını tanımlar. Hedef; her kullanıcının yalnızca görevini yapmak için gerekli minimum yetkiye sahip olmasıdır.

---

## 2. Yetkilendirme Modeli

Yetki modeli üç katmanlıdır:

1. **Rol** — Kullanıcının genel fonksiyonu (ör. İK Yöneticisi, Departman Müdürü).
2. **İzin (Permission)** — Belirli bir kaynağa uygulanan aksiyon kodu.
3. **Kapsam (Scope)** — İznin geçerli olduğu kayıt seti.

### 2.1 İzin Formatı

```text
{module}:{resource}:{action}
```

| Bileşen | Değerler |
|---------|----------|
| module | `personnel`, `leave`, `performance`, `payroll`, `training`, `shift`, `org`, `report`, `portal`, `ats` |
| resource | `employee`, `request`, `review`, `slip`, `course`, `template`, `unit`, `dashboard` vb. |
| action | `create`, `read`, `update`, `delete`, `approve`, `reject`, `export`, `publish`, `manage` |

Örnekler:

```text
personnel:employee:read         → Personel kaydı okuma
leave:request:approve           → İzin talebi onaylama
performance:review:publish      → Performans değerlendirmesi yayınlama
payroll:slip:export             → Bordro dışa aktarma
shift:template:manage           → Vardiya şablonu yönetme
org:delegation:create           → Vekalet oluşturma
```

### 2.2 İzin Çözümleme Algoritması

```
1. Kullanıcının tüm rolleri toplanır (user_roles)
2. Her rolün izinleri birleştirilir (UNION) → efektif izin seti
3. İstenen aksiyon efektif sette var mı kontrol edilir
4. Kapsam kontrolü:
   a. İzin scope'u belirlenir (self, team, department, org_tree, tenant)
   b. Hedef kaydın sahibi / departmanı çözümlenir
   c. Kullanıcının scope'u hedef kaydı kapsıyor mu → GRANT / DENY
5. Deny-by-default: Eşleşme yoksa erişim reddedilir
```

---

## 3. Standart Roller

### 3.1 Rol Tanımları

| Rol | Kod | Açıklama | Varsayılan Scope |
|-----|-----|----------|------------------|
| Süper Admin | `super_admin` | Tenant yapılandırma ve tam yetki | `tenant` |
| İK Yöneticisi | `hr_manager` | Tüm İK modüllerinde tam operasyon | `tenant` |
| İK Uzmanı | `hr_specialist` | Belirli modüllerde operasyon (bordro hariç) | `tenant` |
| Bordro Uzmanı | `payroll_specialist` | Bordro işlemleri ve sınırlı personel erişimi | `tenant` (bordro), `read` (personel) |
| Departman Yöneticisi | `dept_manager` | Kendi ekibi üzerinde yönetim | `org_tree` |
| Takım Lideri | `team_lead` | Takım operasyonları | `team` |
| Çalışan | `employee` | Kendi verisi ve self-servis | `self` |
| Denetçi | `auditor` | Salt okunur, sınırlı kapsam | `tenant` (read-only) |
| Sistem Entegrasyon | `integration` | API erişimi, belirli scope'lar | Modüle özel |

### 3.2 Tam İzin Matrisi

| İzin | Süper Admin | İK Yönetici | İK Uzmanı | Bordro | D. Yönetici | Takım Lid. | Çalışan | Denetçi |
|------|:-----------:|:-----------:|:---------:|:------:|:------------:|:----------:|:-------:|:-------:|
| **Personel** | | | | | | | | |
| personnel:employee:create | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| personnel:employee:read | ✅ | ✅ | ✅ | 📋 | 🌳 | 👥 | 🔒 | ✅ |
| personnel:employee:update | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | 🔒 | ❌ |
| personnel:employee:delete | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| personnel:employee:export | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **İzin** | | | | | | | | |
| leave:request:create | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | 🔒 | ❌ |
| leave:request:approve | ✅ | ✅ | ❌ | ❌ | 🌳 | 👥 | ❌ | ❌ |
| leave:balance:read | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | 🔒 | ✅ |
| leave:policy:manage | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Performans** | | | | | | | | |
| performance:review:create | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | ❌ | ❌ |
| performance:review:read | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | 🔒 | ✅ |
| performance:review:publish | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| performance:goal:manage | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | 🔒 | ❌ |
| **Bordro** | | | | | | | | |
| payroll:slip:read | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | 🔒 | ✅ |
| payroll:run:execute | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| payroll:slip:export | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | 🔒 | ✅ |
| payroll:config:manage | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Vardiya & Mesai** | | | | | | | | |
| shift:template:manage | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| shift:plan:manage | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | ❌ | ❌ |
| shift:overtime:approve | ✅ | ✅ | ❌ | ❌ | 🌳 | 👥 | ❌ | ❌ |
| shift:attendance:read | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | 🔒 | ✅ |
| **Eğitim** | | | | | | | | |
| training:course:manage | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| training:enrollment:manage | ✅ | ✅ | ✅ | ❌ | 🌳 | ❌ | 🔒 | ❌ |
| training:record:read | ✅ | ✅ | ✅ | ❌ | 🌳 | 👥 | 🔒 | ✅ |
| **Organizasyon** | | | | | | | | |
| org:unit:manage | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| org:delegation:create | ✅ | ✅ | ❌ | ❌ | 🌳 | ❌ | ❌ | ❌ |
| org:chart:read | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Raporlama** | | | | | | | | |
| report:dashboard:read | ✅ | ✅ | ✅ | 📋 | 🌳 | 👥 | 🔒 | ✅ |
| report:custom:create | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| report:export:execute | ✅ | ✅ | ✅ | 📋 | ❌ | ❌ | ❌ | ✅ |
| **İşe Alım** | | | | | | | | |
| ats:candidate:manage | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ats:evaluation:create | ✅ | ✅ | ✅ | ❌ | 🌳 | ❌ | ❌ | ❌ |
| **Sistem** | | | | | | | | |
| system:settings:manage | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| system:roles:manage | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| system:audit:read | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

**Simge açıklamaları:** ✅ = Tam erişim (tenant) | 🌳 = Org tree scope | 👥 = Team scope | 🔒 = Self scope | 📋 = Modül spesifik | ❌ = Erişim yok

---

## 4. Kapsam (Scope) Türleri

| Scope | Kod | Açıklama | Kayıt Çözümleme |
|-------|-----|----------|-----------------|
| Self | `self` | Kendi kaydı | `record.employee_id == current_user.employee_id` |
| Team | `team` | Doğrudan bağlı çalışanlar | `record.employee.manager_id == current_user.employee_id` |
| Org Tree | `org_tree` | Hiyerarşik alt ağaç | `record.employee.org_unit ∈ subtree(current_user.org_unit)` |
| Department | `department` | Belirli departman(lar) | `record.employee.department_id ∈ user.assigned_departments` |
| Tenant | `tenant` | Tüm şirket | `record.tenant_id == current_user.tenant_id` |

### 4.1 Scope Hiyerarşisi

```
tenant (tüm kayıtlar)
  └── department (belirli departmanlar)
       └── org_tree (hiyerarşik alt)
            └── team (doğrudan bağlı)
                 └── self (kendi)
```

Daha geniş scope, dar scope'u kapsar. `org_tree` yetkisi olan yönetici, `team` ve `self` scope'larına da erişir.

---

## 5. Veritabanı Şeması

### roles

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `code` | VARCHAR(50) UNIQUE | `hr_manager`, `employee` vb. |
| `name` | VARCHAR(100) | Görünen ad |
| `description` | TEXT NULL | |
| `is_system` | BOOLEAN DEFAULT FALSE | Sistem rolü (silinemez) |
| `is_active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | |

### permissions

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `code` | VARCHAR(100) UNIQUE | `personnel:employee:read` |
| `module` | VARCHAR(30) | `personnel`, `leave` vb. |
| `resource` | VARCHAR(30) | `employee`, `request` vb. |
| `action` | VARCHAR(20) | `create`, `read`, `update` vb. |
| `description` | TEXT NULL | |

### role_permissions

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `role_id` | UUID FK → roles | |
| `permission_id` | UUID FK → permissions | |
| `scope` | ENUM | `self`, `team`, `org_tree`, `department`, `tenant` |
| `scope_params` | JSONB NULL | Ek kısıtlama (ör. belirli departman ID listesi) |

**UNIQUE:** `(role_id, permission_id)`

### user_roles

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `user_id` | UUID FK → users | |
| `role_id` | UUID FK → roles | |
| `scope_override` | ENUM NULL | Kullanıcıya özel scope geçersiz kılma |
| `scope_params` | JSONB NULL | Ör. belirli departman ID'leri |
| `granted_by` | UUID FK → users | Atayan kişi |
| `granted_at` | TIMESTAMPTZ | |
| `expires_at` | TIMESTAMPTZ NULL | Geçici atama süresi |
| `is_active` | BOOLEAN DEFAULT TRUE | |

**UNIQUE:** `(user_id, role_id)`

### delegations

| Kolon | Tip | Açıklama |
|-------|-----|----------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `delegator_id` | UUID FK → users | Yetki veren |
| `delegate_id` | UUID FK → users | Vekil |
| `role_id` | UUID FK → roles NULL | Spesifik rol (NULL = tüm roller) |
| `permissions` | JSONB NULL | Spesifik izin kodları listesi |
| `start_date` | DATE | |
| `end_date` | DATE | |
| `reason` | TEXT NULL | |
| `status` | ENUM | `pending`, `active`, `expired`, `revoked` |
| `approved_by` | UUID FK → users NULL | Onaylayan (İK) |
| `created_at` | TIMESTAMPTZ | |

---

## 6. Yetki İlkeleri ve İş Kuralları

| Kural | Kod | Açıklama |
|-------|-----|----------|
| Deny-by-default | YTK-01 | Eşleşen izin yoksa erişim reddedilir |
| Birleşik roller | YTK-02 | Çoklu rol UNION ile birleştirilir (en geniş yetki geçerli) |
| Scope uyumu | YTK-03 | İzin olsa da scope uygun değilse erişim engellenir |
| Delegasyon süresi | YTK-04 | `start_date` / `end_date` otomatik aktif/pasif; Celery günceller |
| Ek doğrulama | YTK-05 | Hassas export, rol atama, bordro onay → MFA tekrar gerekli |
| Kendi rolünü veremez | YTK-06 | Kullanıcı kendi sahip olduğundan daha geniş rol atayamaz |
| Admin koruması | YTK-07 | Son süper admin'in rolü kaldırılamaz |
| Audit zorunlu | YTK-08 | Tüm yetki değişiklikleri audit_logs'a yazılır |

---

## 7. API Endpoint'leri

### 7.1 Rol Yönetimi

```
GET    /api/v1/roles                → Rol listesi
POST   /api/v1/roles                → Yeni rol oluştur
GET    /api/v1/roles/{id}           → Rol detay + izinleri
PUT    /api/v1/roles/{id}           → Rol güncelle
DELETE /api/v1/roles/{id}           → Rol sil (is_system=false)
```

**POST /api/v1/roles Request:**
```json
{
  "code": "dept_hr_specialist",
  "name": "Departman İK Uzmanı",
  "description": "Belirli departmanlar için İK operasyonları",
  "permissions": [
    {"code": "personnel:employee:read", "scope": "department", "scope_params": {"department_ids": ["uuid1", "uuid2"]}},
    {"code": "leave:request:approve", "scope": "department", "scope_params": {"department_ids": ["uuid1", "uuid2"]}},
    {"code": "personnel:employee:update", "scope": "department"}
  ]
}
```

### 7.2 Kullanıcı Rol Atama

```
GET    /api/v1/users/{id}/roles            → Kullanıcı rolleri
POST   /api/v1/users/{id}/roles            → Rol ata
DELETE /api/v1/users/{id}/roles/{role_id}   → Rol kaldır
GET    /api/v1/users/{id}/effective-perms   → Efektif izin seti (çözümlenmiş)
```

**GET /api/v1/users/{id}/effective-perms Response:**
```json
{
  "user_id": "uuid",
  "roles": ["hr_manager", "dept_manager"],
  "permissions": [
    {"code": "personnel:employee:read", "scope": "tenant"},
    {"code": "leave:request:approve", "scope": "tenant"},
    {"code": "shift:plan:manage", "scope": "org_tree"}
  ],
  "delegated_permissions": [
    {"code": "payroll:slip:read", "scope": "tenant", "expires_at": "2026-05-01"}
  ]
}
```

### 7.3 Delegasyon

```
POST   /api/v1/delegations           → Vekalet oluştur
GET    /api/v1/delegations            → Aktif vekaletler
PUT    /api/v1/delegations/{id}       → Vekalet güncelle
DELETE /api/v1/delegations/{id}       → Vekalet iptal
```

### 7.4 İzin Kontrolü (Dahili Servis)

```
POST   /api/v1/auth/check-permission  → İzin doğrulama (middleware)
```

**Request:**
```json
{
  "user_id": "uuid",
  "permission": "leave:request:approve",
  "target_employee_id": "uuid"
}
```

**Response:**
```json
{
  "allowed": true,
  "matched_role": "dept_manager",
  "scope": "org_tree",
  "reason": "Target employee is in user's org subtree"
}
```

---

## 8. Yönetim Ekranları

### 8.1 Rol Listesi ve Düzenleyici

```
┌──────────────────────────────────────────────────┐
│  Rol Yönetimi                          [+ Yeni Rol] │
├──────────────────────────────────────────────────┤
│  🔍 Ara...                                         │
├──────┬──────────────┬────────┬──────────┬────────┤
│ Kod  │ Ad           │ Tür    │ Kullanıcı│ İşlem  │
├──────┼──────────────┼────────┼──────────┼────────┤
│ super│ Süper Admin  │ Sistem │    2     │  👁️    │
│ hr_m │ İK Yönetici  │ Sistem │    5     │ ✏️ 👁️  │
│ dept │ Departman Y. │ Özel   │   12     │ ✏️ 🗑️ 👁️│
└──────┴──────────────┴────────┴──────────┴────────┘
```

### 8.2 İzin Matrisi Görünümü

```
┌───────────────────────────────────────────────────────────┐
│  İzin Matrisi                                             │
│  Modül: [Tümü ▾]  Rol: [İK Yönetici ▾]                  │
├──────────────────┬─────────┬──────┬────────┬──────┬──────┤
│ İzin             │ Create  │ Read │ Update │Delete│Export│
├──────────────────┼─────────┼──────┼────────┼──────┼──────┤
│ Personel :Çalışan│ ✅ T    │ ✅ T │ ✅ T   │ ✅ T │ ✅ T │
│ İzin     :Talep  │ ✅ T    │ ✅ T │ ❌     │ ❌   │ ✅ T │
│ İzin     :Onay   │ ✅ T    │ ✅ T │ ❌     │ ❌   │ ❌   │
│ Bordro   :Slip   │ ❌      │ ✅ T │ ❌     │ ❌   │ ✅ T │
│ Vardiya  :Plan   │ ✅ T    │ ✅ T │ ✅ T   │ ❌   │ ❌   │
└──────────────────┴─────────┴──────┴────────┴──────┴──────┘
  T=Tenant  O=OrgTree  D=Department  TM=Team  S=Self
```

### 8.3 Kullanıcı Yetki Detay

```
┌──────────────────────────────────────────────────┐
│  Ahmet Yılmaz — Efektif Yetkiler                │
├──────────────────────────────────────────────────┤
│  Roller: [İK Uzmanı] [Bordro Uzmanı]            │
│  Vekaletler: Merve K. → payroll:run (30 Nis'e)  │
├──────────────────────────────────────────────────┤
│  Birleşik İzinler:                               │
│  ✅ personnel:employee:read    (tenant)           │
│  ✅ leave:request:approve      (tenant)           │
│  ✅ payroll:slip:read           (tenant)           │
│  ✅ payroll:run:execute         (tenant, delegated)│
│  ❌ system:settings:manage                        │
└──────────────────────────────────────────────────┘
```

---

## 9. Celery Görevleri

| Görev | Cron | Açıklama |
|-------|------|----------|
| `activate_delegations` | Her 15 dk | `start_date` bugün olan vekaletleri `active` yapar |
| `expire_delegations` | Her 15 dk | `end_date` geçmiş vekaletleri `expired` yapar |
| `expire_temp_roles` | Her saat | `expires_at` geçmiş kullanıcı rollerini pasifleştirir |
| `audit_permission_report` | Haftalık | Tüm kullanıcı yetki özetini dışa aktarır (denetim) |

---

## 10. Django Middleware / Decorator Entegrasyonu

### 10.1 Permission Decorator

```python
# Kullanım örneği
@require_permission("leave:request:approve", scope_field="employee_id")
def approve_leave_request(request, request_id):
    ...
```

### 10.2 Scope Resolver

```python
class ScopeResolver:
    def resolve(self, user, permission_code, target_employee_id) -> bool:
        """
        1. user'ın efektif izinlerini çözümle (roller + delegasyonlar)
        2. permission_code eşleşmesi kontrol et
        3. Scope'a göre target_employee erişimi doğrula
        """
        ...

    def get_accessible_employee_ids(self, user, permission_code) -> QuerySet:
        """Kullanıcının bu izinle erişebildiği tüm employee ID'leri"""
        ...

    def filter_queryset(self, user, permission_code, queryset) -> QuerySet:
        """QuerySet'i kullanıcının scope'una göre filtrele (list endpoint'leri)"""
        ...
```

---

## 11. Audit ve Test

### 11.1 Audit Logları

| Olay | Loglanan Bilgi |
|------|----------------|
| Rol oluşturma / güncelleme | Rol kodu, değişen izinler, yapan kullanıcı |
| Rol atama / kaldırma | Hedef kullanıcı, rol kodu, atayan |
| Delegasyon oluşturma | Delegator, delegate, izin kapsamı, süre |
| İzin reddi | Kullanıcı, istenen izin, hedef kayıt, red sebebi |
| Hassas erişim | Maaş, TCKN okuma olayları |

### 11.2 Test Senaryoları

| # | Test | Beklenen Sonuç |
|---|------|----------------|
| 1 | Çalışan başkasının izin talebini okumaya çalışır | 403 Forbidden |
| 2 | Departman yöneticisi kendi alt ağacındaki çalışanı onaylar | 200 OK |
| 3 | Departman yöneticisi farklı departman çalışanını okur | 403 Forbidden |
| 4 | Süper admin son süper admin rolünü kaldırmaya çalışır | 400 Bad Request |
| 5 | Vekalet süresi dolmuş kullanıcı delegated izni kullanır | 403 Forbidden |
| 6 | İK uzmanı bordro slip okumaya çalışır | 403 Forbidden |
| 7 | Çoklu rol birleşimi — en geniş scope geçerli | UNION scope çalışır |
| 8 | Tenant A kullanıcısı Tenant B kaydına erişir | 403 Forbidden |
| 9 | Expire olmuş geçici rol ile giriş | Rol listede görünmez |
| 10 | Rol değişikliği yapılır, audit log kontrol | Log kaydı oluşmuş |
