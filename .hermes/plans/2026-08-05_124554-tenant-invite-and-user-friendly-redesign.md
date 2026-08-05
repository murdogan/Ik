# Tenant Davet Linki ve Kullanıcı Dostu Arayüz Yenileme Planı

> **For Hermes:** Kullanıcı 5 Ağustos 2026’da uygulama onayı verdi. Planı TDD + fiziksel izole Codex (`gpt-5.6-sol`, `ultra`) akışıyla, dikey dilimler halinde uygula. Görsel referans Gmail’de “Hermes foto” konulu mesajdan alındı.

**Goal:** Platform yöneticisinin SMTP olmadan güvenli, süreli ve tek kullanımlık tenant yönetici davet linki üretip kopyalayabilmesini sağlamak; tenant kullanıcı arayüzünü BambooHR benzeri sıcak, sade, erişilebilir ve kullanıcı dostu bir deneyime dönüştürmek.

**Architecture:** Mevcut credential-safe resend endpointi değişmeden kalacak; manuel paylaşım için ayrı ve daha açık güvenlik sözleşmeli additive endpoint eklenecek. Tenant UI yenilemesi yalnız tenant shell ve genel bakış yüzeyini kapsayacak; platform admin güvenlik alanı ve auth realm görsel/teknik olarak ayrı kalacak. Davranışlar önce Playwright/pytest RED testleriyle sabitlenecek.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL/SQLite test adapterları, Next.js 16, React, TypeScript, CSS Modules, Playwright, pytest.

---

## Kapsam ve sınırlar

### Bu fazda yapılacak

- Tenant detayında “Yeni davet linki üret” ve “Linki kopyala” akışı.
- Önceki aktif davet tokenlarının atomik revoke edilmesi.
- Linkin yalnız yetkili platform yöneticisine, başarılı mutation yanıtında gösterilmesi.
- Linkin audit/outbox/log/kalıcı frontend storage içine yazılmaması.
- Tenant app shell: sidebar, üst bar, yuvarlak profil menüsü, erişilebilir mobil menü.
- Çıkış için açık onay dialog’u.
- Genel bakışta küçük başlıklar, samimi karşılama, rol bazlı öncelikli işler ve kompakt metrikler.
- Desktop + tablet + mobil responsive ve keyboard/focus davranışları.
- Gerçek public staging browser smoke.

### Bu fazda yapılmayacak

- Platform admin login/shell tasarımını tenant tasarımına dönüştürmek.
- Organizasyon kodunu login ekranına geri eklemek.
- SMTP provider kurulumu.
- Tüm alt modül ekranlarını baştan çizmek.
- Yeni genel amaçlı component framework veya design-system paketi eklemek.
- Kullanıcı/çalışan verisini platform admin response’larına açmak.

---

## Araştırma tabanlı tasarım yönü — kesinleşti

Telegram görseli iki denemede de ortam izin hatası nedeniyle okunamadı. Kullanıcının yönlendirmesiyle görsel artık blocker değildir; tasarım BambooHR, HiBob, Deel HR, Rippling ve Factorial’ın güncel kamuya açık ürün deneyimleri ile mevcut repo incelemesine dayanacaktır.

### Benchmark’tan alınan ilkeler

- **BambooHR:** sıcak, insan odaklı dil; yeşil marka karakteri; karmaşık İK işlerini sade gruplama.
- **HiBob:** çalışan, yönetici ve İK rollerine göre farklı günlük öncelikler.
- **Deel HR:** “hangi modül?” yerine “ne yapmak istiyorum?” odaklı hızlı işlemler.
- **Rippling:** onayları ve bekleyen işleri merkezi, aksiyon alınabilir kartlarda toplama.
- **Factorial:** boş durumlarda kullanıcıyı elinden tutan açıklama ve mobil temel işlemler.

### Seçilen görsel sistem

| Token/alan | Karar |
|---|---|
| Uygulama zemini | Sıcak kırık beyaz `#F6F7F3` |
| Birincil yüzey | Beyaz `#FFFFFF` |
| Sidebar | Derin yeşil `#173F35`; aktif öğe `#255B4C` |
| Primary accent | Dostça yeşil `#2F7D5A`; açık tonu `#E8F3EC` |
| Ana metin | `#1F2A27` |
| İkincil metin | `#66736E` |
| Border | `#DEE5E0` |
| Tehlikeli aksiyon | `#B93838`; yalnız destructive işlemler |
| Sidebar genişliği | Açık `232px`, daraltılmış `72px` |
| Desktop header | `64px` |
| Card radius | `14–16px`; hafif border, çok düşük gölge |
| Avatar | `40×40px`, tam yuvarlak |
| Profil menüsü | Yaklaşık `280px`, sağa hizalı, keyboard-accessible |

Bu palet BambooHR’ın sıcaklığından esinlenir; ürünün renklerini veya sayfa kompozisyonunu birebir kopyalamaz.

### Bilgi mimarisi kararı

- Desktop’ta daraltılabilir sidebar; etiket ve erişilebilir inline SVG ikonlar.
- Harici ikon dependency’si eklenmez; küçük ortak icon component’i oluşturulur.
- Header’ın solunda yalnız sayfa bağlamı/breadcrumb; kullanıcı adı ve e-posta header boyunca uzanmaz.
- Header sağında bildirim, gerekiyorsa kurum değiştir ve yuvarlak profil avatarı bulunur.
- Mobilde `Genel bakış`, persona’ya göre `Çalışanlar/Profilim`, `Talepler` ve `Daha fazla` olmak üzere en çok dört ana aksiyonlu alt navigasyon kullanılır.
- “Daha fazla” paneli yalnız permission/feature filtresinden geçen ikincil rotaları gösterir.
- Tenant ve platform admin kabukları görsel ve teknik olarak ayrı kalır.

---

### Task 1: Güvenli manuel davet linki API sözleşmesini TDD ile sabitle

**Objective:** Mevcut resend sözleşmesini bozmadan, yalnız platform tenant güncelleme yetkisine açık additive manual-link endpoint tanımlamak.

**Files:**
- Modify: `backend/tests/test_tenant_api_f1a.py`
- Modify: `backend/tests/test_openapi_metadata.py`
- Modify: `backend/app/schemas/tenant.py`
- Modify: `backend/app/api/platform_tenants.py`
- Modify: `backend/app/api/dependencies.py`

**Endpoint contract:**

- Method/path: `POST /api/v1/platform/tenants/{tenant_id}/initial-admin-invitation/manual-link`
- Permission: `tenant:update:platform`
- Request body: yok
- Success: `201 Created`
- Data keys exactly: `status`, `activation_url`, `expires_at`
- Status: `manual_link_ready`
- URL: configured HTTPS frontend origin + `/activate#token=...`
- Headers: `Cache-Control: no-store` ve `Pragma: no-cache`
- Conflict: mevcut `tenant_initial_admin_unavailable` ile missing/activated state enumeration kapalı kalır.
- Response e-posta, identity ID, membership ID veya password içermez.

**RED assertions:**

1. Endpoint henüz olmadığı için exact API testi 404 ile fail eder.
2. OpenAPI path/schema testi endpoint olmadığı için fail eder.
3. Yetkisiz platform principal 403 alır ve mutation oluşmaz.
4. Missing ve activated tenant aynı 409 contractını verir.
5. Response URL token içerirken audit/outbox serialized payload token içermez.

**Focused commands:**

```bash
cd backend
uv run pytest tests/test_tenant_api_f1a.py -k 'manual_initial_admin_link' -q
uv run pytest tests/test_openapi_metadata.py -k 'manual_initial_admin_link' -q
```

Expected RED: endpoint/path bulunamadığı için kontrollü fail.

---

### Task 2: Deterministik ve retry-safe credential üretimini uygula

**Objective:** Manuel kopyalanan linkin notification worker retry’sı sırasında geçersiz kalmasını önlemek.

**Files:**
- Modify: `backend/app/services/initial_tenant_admin_provisioner.py`
- Modify: `backend/app/services/tenant_commands.py`
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/modules/core/application/events.py` yalnız yeni audit event gerekiyorsa
- Test: `backend/tests/test_tenant_api_f1a.py`
- Test: ilgili provisioner/worker unit testleri

**Implementation contract:**

1. Yeni activation UUID transaction içinde oluşturulur.
2. `ActivationDeliveryTokenCodec` configured auth signing key ile tenant ID + activation ID’den deterministik credential üretir.
3. PostgreSQL reissue function’a bu token hash’i verilir; önceki aktif tokenlar aynı transaction’da revoke edilir.
4. Aynı outbox invitation event’i oluşturulur; worker aynı codec ile aynı tokenı tekrar üretir.
5. Command sonucu raw tokenı yalnız request memory’sinde tutar ve configured frontend URL ile link üretir.
6. Audit event credential-free kalır; metadata/before/after boş veya allowlisted non-secret alanlarla sınırlıdır.
7. Raw token logger, exception, database payload, delivery prepared fields veya analytics’e yazılmaz.
8. Signing key yoksa release ortamında fail closed davranış döner; uydurma link üretilmez.

**GREEN verification:**

- API response token hash’i, aktif `user_activation_tokens.token_hash` ile eşleşir.
- Worker prepare/retry sonrası hash değişmez.
- İkinci manual-link çağrısı ilk linki geçersiz kılar ve yeni linki aktif yapar.
- Transaction/audit failure tüm revoke/insert/outbox değişikliklerini rollback eder.

---

### Task 3: Platform tenant detayına link üret/kopyala UX’i ekle

**Objective:** SMTP’siz operasyonu platform arayüzünde anlaşılır ve güvenli hale getirmek.

**Files:**
- Modify: `frontend/src/lib/platform-tenants.ts`
- Modify: `frontend/src/components/platform/tenant-detail-screen.tsx`
- Modify: `frontend/src/components/platform/platform-tenant-operations.module.css`
- Modify: `frontend/tests/platform-tenant-operations.spec.ts`

**User flow:**

1. “Yeni davet linki üret” butonu yalnız `tenant:update:platform` yetkisinde ve eligible tenant lifecycle’da görünür.
2. Confirmation dialog şu sonucu açıklar: eski link iptal olur, yeni link süreli/tek kullanımlıdır, yalnız güvenilir kişiye gönderilmelidir.
3. Başarılı response ayrı sonuç panelinde link + son kullanma zamanı gösterir.
4. “Linki kopyala” `navigator.clipboard` ile kopyalar; başarı durumu `aria-live` ile duyurulur.
5. Link sayfa yenilenince veya panel kapanınca tekrar gösterilmez; local/session storage’a yazılmaz.
6. Ambiguous mutation outcome mevcut initial-admin safety latch’i kullanır; otomatik ikinci link üretimi yapılmaz.
7. Sonuç response shape’i exact-key/value validator ile doğrulanır; malformed response link olarak gösterilmez.

**RED Playwright:**

- Button/confirmation/result panel henüz olmadığı için fail.
- Çift click tek POST üretmeli.
- Eski link revoke uyarısı görünmeli.
- Link yalnız success response sonrası görünmeli ve clipboard’a exact URL gitmeli.
- Permission revoked olduğunda buton ve açık dialog DOM’dan kalkmalı.
- Malformed/network outcome secret veya sahte başarı göstermemeli.

---

### Task 4: Tenant app shell ve profil menüsünü yenile

**Objective:** Kimliği header boyunca sola taşıyan mevcut düzeni, sağ üstte kompakt ve kullanıcı dostu profil menüsüne dönüştürmek.

**Files:**
- Modify: `frontend/src/components/dashboard/tenant-shell.tsx`
- Modify: `frontend/src/components/dashboard/tenant-shell.module.css`
- Modify: `frontend/tests/session-flow.spec.ts`
- Modify: `frontend/tests/role-aware-navigation.spec.ts`
- Muhtemel create: `frontend/src/components/dashboard/profile-menu.tsx`
- Muhtemel create: `frontend/src/components/dashboard/logout-confirmation-dialog.tsx`

**Behavior contract:**

- Header yüksekliği yaklaşık 64–72 px; başlık/metin blokları header’da sola yayılmaz.
- Sağ üstte kullanıcının baş harflerinden oluşan dairesel avatar button bulunur.
- Avatar button `aria-haspopup="menu"`, `aria-expanded`, Escape/outside-click ve focus return destekler.
- Menü içinde ad, e-posta, rol, “Profilim”, “Kurum değiştir” ve “Çıkış yap” bulunur; permission/feature görünürlüğü mevcut kurallara uyar.
- “Çıkış yap” doğrudan API çağırmaz; modal confirmation açar.
- Modal: “Oturumu kapatmak istediğinize emin misiniz?”; “Vazgeç” primary-safe, “Çıkış yap” destructive action.
- Confirmation açıkken focus trap; Escape iptal; onay sonrası tek logout mutation.
- Sidebar öğeleri görsel gruplara ayrılır ancak route/permission/feature filtreleri değişmez.
- Mobilde erişilebilir menü trigger ve en az 44 px touch target korunur.

**RED Playwright:**

1. Doğrudan “Çıkış yap” header butonu bulunmamalı.
2. Avatar menüsü açılmadan kullanıcı detayları görünmemeli.
3. Menüden çıkış seçilince API çağrısı hâlâ 0; confirmation görünmeli.
4. Vazgeç sonrası API 0 ve focus avatar/menu trigger’a dönmeli.
5. Onay sonrası logout API tam 1 kez çağrılmalı.
6. Escape ve keyboard navigation çalışmalı.

---

### Task 5: Genel bakış ekranını samimi ve kompakt hale getir

**Objective:** Büyük pazarlama başlığı hissini kaldırıp günlük iş odaklı, sıcak ve okunabilir HR ana sayfası oluşturmak.

**Files:**
- Modify: `frontend/src/components/dashboard/dashboard-overview.tsx`
- Modify: `frontend/src/components/dashboard/tenant-shell.module.css`
- Modify: dashboard/role-aware Playwright testleri

**Content hierarchy:**

1. Kompakt selamlama: `Günaydın/İyi günler/İyi akşamlar, {firstName}` veya zaman bağımsız `Merhaba, {firstName}`.
2. Alt satır: kurum adı + kısa doğal cümle; “rol kapsamı/güvenli tenant” gibi teknik metin kullanıcı yüzünden kaldırılır.
3. Öncelikli işler bölümü: bekleyen izin, eksik belge, yaklaşan süre gibi mevcut endpoint verilerinden türetilen 2–3 action card.
4. Metrikler: 4 ana kart üstte, diğerleri ikincil özet/ayrıntı alanında; başlıklar 12–14 px, değerler 24–30 px.
5. Son hareketler ve departman dağılımı daha doğal başlıklarla korunur.
6. Güvenli oturum kartı kaldırılır; güvenlik implementasyon detayı dashboard içeriği değildir.
7. Empty state’ler sakin, açıklayıcı ve sonraki aksiyona yönlendirici olur.

**Endpoint policy:**

- Önce mevcut `/api/v1/dashboard/summary` verisi kullanılır.
- Görsel hedef için zorunlu olmayan yeni endpoint eklenmez.
- Yeni kullanıcı değeri mevcut summary ile üretilemiyorsa önce additive, role/tenant-scoped endpoint tasarlanır; RLS/permission/audit sınırı test edilmeden UI’a bağlanmaz.

---

### Task 6: Görsel sistem, responsive ve erişilebilirlik

**Objective:** Kullanıcının göndereceği referans görsele sadık, tüm tenant ekranlarında sürdürülebilir tokenlar oluşturmak.

**Files:**
- Modify: `frontend/src/app/globals.css` yalnız tenant-safe global token gerekiyorsa
- Modify: `frontend/src/components/dashboard/tenant-shell.module.css`
- Gerekirse create: `frontend/src/components/dashboard/tenant-theme.module.css`

**Kesin tipografi ölçeği:**

- Dashboard karşılama H1: desktop `28px`, mobile `24px`, weight `650–700`, line-height `1.2`.
- Diğer sayfa H1: desktop `24px`, mobile `22px`; protected app içinde `32px` üstüne çıkılmaz.
- Bölüm H2: `18px`, weight `650`.
- Card başlığı: `15–16px`, weight `600`.
- Metrik değeri: desktop `28px`, mobile `24px`.
- Body: `14px`, line-height `1.5`; uzun açıklama gerektiğinde `15px`.
- Caption/meta: `12–13px`; okunabilirlik için `12px` altına inilmez.
- Header/sidebar controls: `13–14px`.
- Minimum touch target: `44×44px`.

**Visual checks:**

- Desktop: 1440×900.
- Tablet: 1024×768.
- Mobile: 390×844 ve keyboard-shortened 390×320.
- No horizontal overflow.
- Text contrast WCAG AA.
- `prefers-reduced-motion` korunur.
- Menu/dialog z-index, scroll lock ve focus görünürlüğü manuel kontrol edilir.

---

### Task 7: Entegrasyon, staging ve gerçek persona smoke

**Objective:** Davet linkinden aktivasyona ve yenilenmiş dashboard’a kadar gerçek akışı public staging’de kanıtlamak.

**Automated gates:**

```bash
cd backend
uv run pytest <focused manual-link nodes> -q
uv run ruff check app tests/<changed-tests>
uv run mypy app

cd ../frontend
npx playwright test <focused invite/shell/dashboard tests> --reporter=line
npm run typecheck
npm run lint
npm run build
```

**Manual browser journey:**

1. Platform admin `/platform/login` ile giriş yapar.
2. Tenant detayında “Yeni davet linki üret” onaylanır.
3. Link kopyalanır ve yeni private browser context’te `/activate#token=...` açılır.
4. QA persona parola belirler; `/login` üzerinden organizasyon kodu olmadan giriş yapar.
5. Yeni dashboard desktop/mobile görsel olarak incelenir.
6. Avatar menüsü, profil linki, kurum değiştir ve çıkış confirmation test edilir.
7. Logout sonrası protected route `/login`’e döner ve session cookie temizlenir.
8. Test session/credential ve geçici QA verileri resmi akışlarla temizlenir; kullanıcının gerçek tenant yöneticisi hesabına müdahale edilmez.

**Release:**

- Clean diff + `git diff --check`.
- Codex yazarlığı açıkça raporlanır.
- `main` exact SHA push/read-back.
- Mevcut staging backup/deploy scripti ile release.
- API readiness exact SHA ve public browser smoke.
- TryCloudflare URL’nin kalıcı production domain olmadığı açıkça belirtilir.

---

## Riskler ve korumalar

| Risk | Koruma |
|---|---|
| Manuel link worker retry sonrası bozulur | Aynı `ActivationDeliveryTokenCodec` ve activation ID ile deterministik token |
| Token log/audit/storage’a sızar | Response-only secret, credential-free audit/outbox, exact negative assertions |
| Kullanıcı çift tıkla birden fazla link üretir | Mutation lock, disabled state, ambiguous-outcome latch |
| Eski link aktif kalır | Aynı transaction’da revoke + insert |
| Platform/tenant auth realm karışır | Platform shell kapsam dışı, ayrı endpoint permission ve session client |
| Redesign permission görünürlüğünü bozar | Mevcut navigation filter korunur, role-aware zero-request tests |
| Tasarım tüm alt ekranları kırar | Önce shell + dashboard dikey dilimi; global selector yerine scoped CSS |
| Görsel referansla plan çelişir | UX Task 4–6 başlamadan visual design lock güncellenir |

---

## Uygulama onay kapısı

Araştırma ve repo keşfi tamamlandı; tasarım yönü artık görsele bağlı değildir. Kodlama için kalan tek açık kapı:

- [x] HR ürün benchmark’ı tamamlandı.
- [x] Mevcut tenant shell/dashboard/test yüzeyi incelendi.
- [x] Sidebar/header/dashboard yönü kesinleştirildi.
- [x] Mobil navigasyon biçimi kesinleştirildi.
- [x] Kullanıcı “bu plana göre koda geç” onayı verdi.

Onay geldiğinde önce manuel davet linki dikey dilimi, ardından tenant shell ve dashboard dilimleri uygulanır. Her dilim ayrı RED/GREEN test, browser kanıtı ve commit ile tamamlanır.
