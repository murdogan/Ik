# Wealthy Falcon HR Product Plan

> **For Hermes:** Planning/documentation mode. Do not implement code until Murat explicitly says: `koda geç` or `Sprint-0 kod uygulamasına geç`.

**Goal:** İsmi, görsel yönü ve MVP kapsamı netleşmiş İK/HRMS ürününü kontrollü şekilde planlayıp Sprint-0/Sprint-1 uygulamasına hazır hale getirmek.

**Architecture:** Backend mevcut FastAPI scaffold üstüne kontrollü genişleyecek. İlk ürün odağı; tenant/şirket, kullanıcı, çalışan özlük, izin/onay, dashboard ve demo-ready landing akışı olacak. Frontend/dashboard tasarımı mevcut beğenilen landing setiyle aynı görsel dilde ilerleyecek.

**Tech Stack:** FastAPI, Python, pytest, ruff, mevcut backend scaffold, markdown dokümantasyon, staging için geçici Cloudflare tunnel; kalıcı domain/tunnel ayrıca planlanacak.

---

## 1. Mevcut Bağlam

### Kararlar

- Geçici ürün/marka adı: **Wealthy Falcon**.
- Ürün konumlandırması: **Wealthy Falcon HR** veya **Wealthy Falcon — Modern HR Platform**.
- Marka hikâyesi: Aile isimlerinden gelen anlam var: **Varlıklı + Doğan**.
- Tasarım yönü: Landing’de beğenilen **BambooHR sadeliği + modern SaaS dashboard hissi** kullanılacak.
- Dashboard ve iç ekranlar bu tasarım setine göre düzenlenecek.
- Mevcut Cloudflare quick tunnel linki kalıcı değil; test kullanıcılarına vermeden önce kalıcı domain/subdomain gerekir.

### Repo / Ortam

- Repo: `/opt/data/repos/Ik`
- Staging clone: `/opt/data/staging/ik-app`
- Landing route: `/opt/data/repos/Ik/backend/app/api/landing.py`
- Public geçici staging URL: `https://suggest-offline-calcium-newman.trycloudflare.com/`
- Plan kapısı: `/opt/data/repos/Ik/docs/09-uygulama/08-implementation-readiness-checklist.md`
- Kullanıcı kuralı: Murat açıkça “koda geç” demeden kod genişletmesi yapılmayacak.

---

## 2. Ürün Pozisyonu

### Ana Mesaj

**Wealthy Falcon HR**  
Büyüyen ekipler için modern, sade ve güvenilir insan kaynakları platformu.

### Türkçe Landing Mesajı

> İnsan kaynaklarını karmaşadan çıkarıp tek ekranda yönetin.

Alt metin:

> Wealthy Falcon HR; çalışan bilgileri, izin talepleri, onboarding, dokümanlar ve raporları sade bir platformda toplar.

### Global Mesaj

> Wealthy Falcon HR — Modern HR platform for growing teams.

### Kategori Riski

“Wealthy Falcon” ismi direkt HR kategorisini anlatmaz. Bu yüzden ilk dönemde ürün adı şu formatta kullanılmalı:

- **Wealthy Falcon HR**
- **Wealthy Falcon People** ileride alternatif olabilir.
- Domain ve logo kesinleşene kadar tüm dokümanlarda “provisional brand” olarak işaretlenmeli.

---

## 3. MVP Kapsamı

### MVP’de Olacaklar

1. **Auth / Tenant Temeli**
   - Şirket/tenant modeli
   - Kullanıcı modeli
   - Rol temeli: owner/admin/employee

2. **Çalışan Yönetimi**
   - Çalışan listesi
   - Çalışan profil özeti
   - Temel özlük alanları
   - Departman/pozisyon alanları

3. **İzin Yönetimi**
   - İzin talebi oluşturma
   - Yönetici onayı/red akışı
   - Kalan/görünen izin bilgisi için ilk model

4. **Dashboard**
   - Günün İK özeti
   - Bekleyen işler
   - Çalışan sayısı
   - İzin talepleri
   - Departman dağılımı
   - Yaklaşan başlangıçlar/işe girişler

5. **Demo / Landing**
   - Beğenilen landing tasarımının marka adıyla güncellenmesi
   - Demo talep akışı için minimum form veya placeholder
   - API Docs / Health linklerinin korunması

### MVP’de Olmayacaklar

- Bordro hesaplama
- SGK entegrasyonu
- Banka entegrasyonu
- PDKS cihaz entegrasyonu
- AI özellikleri
- Gelişmiş performans/OKR
- Mobil uygulama
- Kurumsal SSO

Bunlar roadmap’te kalacak; MVP’ye alınmayacak.

---

## 4. Faz Planı

## Faz 0 — Plan Kilitleme

**Amaç:** İsim, tasarım, MVP kapsamı ve uygulama sırasını netleştirmek.

### Task 0.1: Marka kararını dokümante et

**Objective:** Wealthy Falcon kararını geçici/çalışma markası olarak dokümana eklemek.

**Files:**
- Modify: `/opt/data/repos/Ik/docs/09-uygulama/07-demo-landing-satis-anlatisi-plani.md`
- Modify: `/opt/data/repos/Ik/docs/README.md`
- Modify: `/opt/data/project_states/ik-hrms.md`

**Acceptance Criteria:**
- Wealthy Falcon HR adı dokümanlarda geçer.
- İsim “geçici ama kullanılabilir marka” olarak not edilir.
- İleride rebrand ihtimali açık bırakılır.

### Task 0.2: Tasarım sistemini kilitle

**Objective:** Landing’de beğenilen görsel dili dashboard ve iç ekranlara uygulanacak tasarım sistemi olarak tariflemek.

**Files:**
- Modify: `/opt/data/repos/Ik/docs/09-uygulama/05-wireframe-ekran-akis-plani.md`
- Optionally create: `/opt/data/repos/Ik/docs/09-uygulama/09-ui-design-system-notlari.md`

**Design Rules:**
- Açık zemin
- Yumuşak yeşil/turkuaz vurgu
- Rounded card yapısı
- Sade dashboard kartları
- Fazla kurumsal/eski ERP hissinden kaçınma
- Mobil uyumlu layout
- Türkçe metinlerde net ve sade dil

### Task 0.3: Domain stratejisi seç

**Objective:** Test kullanıcılarına verilecek kalıcı URL stratejisini belirlemek.

**Options:**
- `wealthyfalcon.com` uygunsa ana domain
- `wealthyfalconhr.com` daha net ürün domaini
- `getwealthyfalcon.com` startup tarzı
- Mevcut başka domaine subdomain: `hr.<domain>` veya `demo.<domain>`

**Acceptance Criteria:**
- Quick Tunnel linkinin kalıcı olmadığı not edilir.
- Kalıcı domain/subdomain seçilmeden dış test kullanıcılarına link verilmez.

---

## Faz 1 — Sprint-0 Kod Hazırlığı

**Amaç:** Koda geçmeden önce mevcut scaffold’un Sprint-0 için hazır olduğunu doğrulamak.

### Task 1.1: Mevcut test tabanını doğrula

**Objective:** Kod uygulamasına geçmeden önce repo sağlığını ölçmek.

**Commands:**

```bash
cd /opt/data/repos/Ik
uv run ruff check backend
uv run pytest
```

**Expected:**
- Ruff geçmeli.
- Pytest geçmeli.
- Başarısız test varsa kod uygulamasına geçmeden raporlanmalı.

### Task 1.2: Sprint-0 backlog’u marka/tasarım kararına göre güncelle

**Files:**
- Modify: `/opt/data/repos/Ik/docs/09-uygulama/02-sprint-0-1-backlog-ve-task-plani.md`
- Modify: `/opt/data/repos/Ik/docs/09-uygulama/01-sprint-0-teknik-task-breakdown.md`

**Acceptance Criteria:**
- Sprint-0 ilk işleri şu sıraya göre düzenlenir:
  1. Tenant/user model netleştirme
  2. Employee model
  3. Leave request model
  4. Dashboard read endpoint
  5. Landing brand update
  6. Staging smoke test

---

## Faz 2 — Sprint-0 Uygulama Planı

> Bu faz sadece Murat açıkça “koda geç” derse uygulanacak.

### Task 2.1: Employee modelini ekle

**Objective:** Çalışan özlük bilgilerinin minimum modelini oluşturmak.

**Likely Files:**
- Create: `/opt/data/repos/Ik/backend/app/models/employee.py`
- Modify: `/opt/data/repos/Ik/backend/app/models/__init__.py`
- Create: `/opt/data/repos/Ik/backend/tests/test_employee_model.py`

**Fields:**
- id
- tenant_id
- first_name
- last_name
- email
- department
- position
- employment_status
- start_date
- created_at
- updated_at

**Validation:**

```bash
cd /opt/data/repos/Ik
uv run pytest backend/tests/test_employee_model.py -v
uv run pytest
```

### Task 2.2: Leave request modelini ekle

**Objective:** İzin talep/onay akışının veri temelini oluşturmak.

**Likely Files:**
- Create: `/opt/data/repos/Ik/backend/app/models/leave_request.py`
- Create: `/opt/data/repos/Ik/backend/tests/test_leave_request_model.py`

**Fields:**
- id
- tenant_id
- employee_id
- leave_type
- start_date
- end_date
- status: pending/approved/rejected/cancelled
- requested_by_user_id
- decided_by_user_id
- decision_note
- created_at
- updated_at

### Task 2.3: Dashboard summary endpoint tasarla

**Objective:** Dashboard kartlarını besleyecek minimal read endpoint oluşturmak.

**Likely Files:**
- Create: `/opt/data/repos/Ik/backend/app/api/dashboard.py`
- Modify: `/opt/data/repos/Ik/backend/app/main.py`
- Create: `/opt/data/repos/Ik/backend/tests/test_dashboard.py`

**Endpoint Draft:**

```http
GET /api/v1/dashboard/summary
```

**Response Draft:**

```json
{
  "employee_count": 42,
  "pending_leave_requests": 6,
  "new_starters_this_month": 3,
  "open_tasks": 8,
  "department_distribution": [
    {"department": "Sales", "count": 12},
    {"department": "Operations", "count": 9}
  ]
}
```

### Task 2.4: Landing marka güncellemesi

**Objective:** Landing’de Wealthy Falcon HR adını kullanmak ve mevcut tasarım dilini korumak.

**Likely Files:**
- Modify: `/opt/data/repos/Ik/backend/app/api/landing.py`
- Modify: `/opt/data/repos/Ik/backend/tests/test_landing.py`

**Text Direction:**
- Logo/title: `Wealthy Falcon HR`
- Hero: `İnsan kaynaklarını karmaşadan çıkarıp tek ekranda yönetin.`
- CTA: `Demo talep et`

### Task 2.5: Staging smoke test

**Objective:** Main branch staging’e alındığında public sayfanın ve health’in çalıştığını doğrulamak.

**Commands:**

```bash
cd /opt/data/repos/Ik
uv run pytest
uv run python scripts/staging_smoke_test.py
```

**Expected:**
- `/health` 200
- `/` 200
- Landing title doğru
- Hero metni doğru

---

## Faz 3 — Dashboard UI Planı

**Amaç:** Beğenilen landing tasarım setini iç ürün ekranlarına taşımak.

### Dashboard Ekranları

1. **Ana Dashboard**
   - Sol sidebar
   - Üst arama/aksiyon alanı
   - KPI kartları
   - Bekleyen işler
   - Departman dağılımı
   - İzin talepleri

2. **Çalışanlar**
   - Filtrelenebilir çalışan listesi
   - Departman/pozisyon/konum filtreleri
   - Çalışan profil drawer/detail

3. **İzinler**
   - Bekleyen izin talepleri
   - Onay/red aksiyonları
   - Takvim görünümü ileride

4. **Ayarlar**
   - Şirket bilgisi
   - Roller
   - Departmanlar

### UI İlkeleri

- Landing ile aynı renk ve kart dili.
- “ERP ekranı” gibi yoğun tablo hissinden kaçın.
- İlk demo ekranlarında veri az ama görsel güçlü olsun.
- Demo data gerçekçi ama uydurma müşteri markası içermesin.
- Türkçe metinler sade: “Bekleyen izinler”, “Çalışan merkezi”, “Bugünün özeti”.

---

## 5. Riskler

### Risk 1: Marka-kategori uyumu

**Sorun:** Wealthy Falcon ismi HR kategorisini direkt anlatmıyor.

**Çözüm:** İlk dönemde her yerde `Wealthy Falcon HR` kullan.

### Risk 2: Geçici tunnel linki

**Sorun:** `trycloudflare.com` linki değişebilir.

**Çözüm:** Test kullanıcılarından önce kalıcı domain/subdomain kur.

### Risk 3: MVP şişmesi

**Sorun:** Bordro, SGK, performans, AI gibi büyük modüller erken eklenirse proje yavaşlar.

**Çözüm:** MVP sadece employee + leave + dashboard + demo akışında kalmalı.

### Risk 4: Tasarım tutarsızlığı

**Sorun:** Landing güzel ama iç ekranlar eski/dağınık görünürse ürün algısı bozulur.

**Çözüm:** Dashboarddan önce küçük design system notu yazılmalı.

---

## 6. Açık Sorular

1. Ürünü dışarıya ilk etapta **Wealthy Falcon** mı, **Wealthy Falcon HR** mı diye sunacağız?
2. Domain için `.com` şart mı, yoksa `.app`, `.io`, `.co` veya mevcut domaine subdomain olur mu?
3. İlk test kullanıcıları kim olacak: tanıdık küçük işletme mi, HR profesyoneli mi, şirket sahibi mi?
4. Demo verileri Türkçe mi İngilizce mi olacak?
5. İlk dashboard web app olarak mı yapılacak, yoksa şimdilik backend-rendered HTML demo yeterli mi?

---

## 7. Onay Kapısı

Kod uygulamasına geçmek için Murat’tan açık onay gerekir.

Kabul edilecek onay örneği:

```text
Planı onaylıyorum, artık Sprint-0 kod uygulamasına geç.
```

Bu onay gelmeden:

- Yeni backend model kodu eklenmeyecek.
- Yeni frontend/dashboard kodu yazılmayacak.
- Deploy otomasyonu değiştirilmayacak.
- Sadece doküman/plan revizyonu yapılacak.

---

## 8. Önerilen Hemen Sonraki Adım

1. Murat bu planı hızlıca okur.
2. Marka adı formatı seçilir: `Wealthy Falcon` vs `Wealthy Falcon HR`.
3. Domain opsiyonları kontrol edilir.
4. Design system notu yazılır.
5. Murat onay verirse Sprint-0 kod uygulamasına başlanır.
