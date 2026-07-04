# Uygulama Yüzeyleri: Web, Mobil ve API

Bu doküman, IK Platform'un kullanıcıya ve dış sistemlere açılan yüzeylerini tanımlar: web panel, çalışan portalı, yönetici portalı, aday/kariyer sitesi, mobil/PWA ve public/internal API.

## 1. Amaç ve karar özeti

Ürün tek bir admin panelden ibaret değildir. Farklı kullanıcı tipleri farklı yüzeylere ihtiyaç duyar.

Karar özeti:

> MVP'de ana yüzeyler web admin panel, çalışan/yönetici responsive portalı ve REST API'dir. Native mobil uygulama, kariyer sitesi ve gelişmiş public API sonraki fazlarda büyür.

## 2. Yüzey listesi

| Yüzey | Kullanıcı | Faz | Not |
|---|---|---|---|
| İK Web Paneli | HR, tenant admin | MVP | Ana operasyon merkezi |
| Çalışan Portalı | Employee | MVP | Profil, izin, belge, duyuru |
| Yönetici Portalı | Manager | MVP | Onay kuyruğu ve ekip takvimi |
| Superadmin Panel | Platform ops | MVP internal | Tenant ve destek operasyonu |
| Kariyer Sitesi | Candidate | V1 | Public ilanlar |
| Aday Portalı | Candidate | V1 | Başvuru ve durum takibi |
| Mobil/PWA | Employee/manager | MVP/V1 | Kritik akışlar mobilde çalışmalı |
| Public API | Partner/entegrasyon | V1 | API key/OAuth scope gerektirir |
| Webhook | Dış sistemler | V1 | Event teslimi |

## 3. Web uygulamaları

### 3.1 İK Web Paneli

Kapsam:

- Çalışan yönetimi.
- Belge ve özlük.
- İzin yönetimi.
- Organizasyon ayarları.
- Raporlar.
- Kullanıcı/rol ayarları.
- Audit görünümü.

Tasarım:

- Yoğun veri tabloları.
- Filtre, kolon seçimi, export.
- Drawer/detail panel kullanımı.
- Hassas alan masking.

### 3.2 Çalışan Portalı

Kapsam:

- Profilim.
- İzinlerim.
- Belgelerim.
- Taleplerim.
- Duyurular.
- V1 bordro/vardiya.

Tasarım:

- Sade dil.
- Mobil öncelikli.
- Hızlı aksiyon kartları.
- Büyük dokunma alanları.

### 3.3 Yönetici Portalı

Kapsam:

- Onay kuyruğu.
- Ekip takvimi.
- Ekip listesi.
- V1 performans/puantaj.

Tasarım:

- Onay bağlamı görünür olmalı.
- Bakiye, ekip çakışması ve talep gerekçesi aynı ekranda olmalı.

## 4. Mobil/PWA stratejisi

MVP kararı:

- Native app zorunlu değil.
- Responsive web/PWA kritik akışları taşımalıdır.

Mobilde iyi çalışması gereken MVP akışları:

- Login/aktivasyon.
- İzin talebi.
- Yönetici onayı.
- Talep durumu.
- Duyuru okuma.
- Belge görüntüleme.

Native mobil tetikleyicileri:

- PWA aktivasyon oranı düşük kalırsa.
- Push/biyometri/offline ihtiyaçları kritikleşirse.
- Mavi yaka pilotlarında kullanım zorluğu görülürse.

## 5. API yüzeyi

MVP API:

- Internal/public ayrımı net olmalıdır.
- Web ve mobil aynı API kontratını kullanmalıdır.
- OpenAPI şeması üretilmelidir.

API ilkeleri:

| İlke | Karar |
|---|---|
| Versioning | `/api/v1/...` |
| Auth | Bearer/session + tenant context |
| Error format | Standart hata zarfı |
| Pagination | Cursor veya limit/offset standardı |
| Idempotency | Import/export ve kritik POST işlemlerinde destek |
| Audit | Kritik action endpointlerinde zorunlu |
| Rate limit | Tenant/user/IP bazlı |

## 6. Webhook yüzeyi

V1'de webhook altyapısı planlanır.

Örnek eventler:

- `employee.created`
- `employee.updated`
- `leave.approved`
- `document.uploaded`
- `timesheet.locked`
- `payslip.published`
- `candidate.hired`

Webhook kuralları:

- Signed payload.
- Retry ve exponential backoff.
- Delivery log.
- Tenant secret rotation.
- Idempotency event ID.

## 7. Public kariyer yüzeyi

V1 kapsamı:

- Public ilan listesi.
- İlan detay sayfası.
- Başvuru formu.
- CV upload.
- KVKK aydınlatma/rıza.
- Adaya başvuru alındı bildirimi.

SEO ve performans gerektirir. Bu nedenle Next.js SSR/SSG avantajlıdır.

## 8. Güvenlik gereksinimleri

- Web panel ve çalışan portalı aynı tenant context'i kullanır.
- Superadmin panel ayrı origin/session policy ile ayrılmalıdır.
- Public kariyer endpointleri tenant izolasyonuna sahip olmalıdır.
- Dosya download pre-signed URL ile ve kısa süreli olmalıdır.
- API CORS ve CSRF kararları client türüne göre netleşmelidir.
- Mobil token secure storage gerektirir.

## 9. Kabul kriterleri

- HR web panel MVP operasyonlarını yapabilir.
- Çalışan portalı izin/profil/belge akışlarını taşır.
- Yönetici portalı onay kuyruğunu gösterir.
- Mobil/PWA kritik akışları telefonda tamamlanabilir.
- API OpenAPI standardına göre dokümante edilir.
- Public kariyer sitesi tenant dışı veri sızdırmaz.

## 10. İlgili dokümanlar

- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [Teknik Mimari Genel Bakış](01-teknik-mimari-genel-bakis.md)
- [CORE, AUTH ve RBAC Modülleri](../03-moduller/01-core-auth-rbac.md)
