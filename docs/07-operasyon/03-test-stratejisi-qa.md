# Test Stratejisi ve QA

Bu doküman, IK Platform'un test piramidi, otomasyon katmanları, domain kritik testleri, güvenlik/performance testleri, UAT ve pilot kabul kriterlerini tanımlar.

## 1. Test piramidi

| Katman | Araç örnekleri | Kapsam |
|---|---|---|
| Unit | pytest, vitest | Domain logic, validasyon, saf fonksiyonlar |
| Integration | test DB/Redis, API tests | Repository, service, migration, queue |
| Contract/API | OpenAPI diff, schemathesis | API schema uyumu |
| E2E | Playwright | Kritik kullanıcı akışları |
| Security | SAST/SCA/DAST | OWASP, secret, dependency |
| Performance | k6 | Login, rapor, import, API yükü |

Hedef: Kritik domain logic yüksek kapsam, UI/E2E daha az ama kritik akış odaklı olmalıdır.

## 2. Kritik E2E akışları

- Login + MFA hazırlığı.
- Personel oluşturma.
- Belge yükleme ve görüntüleme.
- İzin talebi → onay → bakiye kontrolü.
- Yönetici onay kuyruğu.
- PDKS import dry-run.
- Rapor export.
- Rol atama ve yetki etkisi.
- Hassas alan maskeleme.
- Çalışan portalı mobil görünüm.
- Aday başvurusu V1.
- Webhook test event V1.

## 3. Test verisi yönetimi

| Konu | Standart |
|---|---|
| Fabrika | Her model için factory |
| Tenant fixture | En az iki tenant ile izolasyon testi |
| Determinizm | Sabit seed ve zaman dondurma |
| Staging veri | Anonimleştirilmiş/sentetik |
| PII | Test ortamlarında gerçek kişisel veri yasak |
| Mevzuat | Test parametre setleri versiyonlu |

## 4. Domain kritik testleri

### 4.1 Yetkilendirme

- Her protected endpoint permission metadata taşır.
- Role × scope × endpoint matrisi test edilir.
- Tenant A token'ı Tenant B kaydını göremez.
- Yetkisiz kaynak için 404/403 politikası tutarlı olmalıdır.
- Hassas alanlar exportta da maskelenir.

### 4.2 İzin

- Kıdem yılına göre hak ediş.
- Yıl devri/devir tavanı.
- Negatif bakiye policy.
- Resmi tatil ve hafta sonu hesapları.
- Onay iptalinde bakiye iadesi.

### 4.3 PDKS/Puantaj

- Duplicate event.
- Eksik giriş/çıkış.
- Gece vardiyası.
- Hatalı device user mapping.
- Kilitli dönem değişmezliği.

### 4.4 Bordro/export

MVP'de bordro motoru yerine export doğruluğu önceliklidir.

Testler:

- Pay component mapping.
- Cost center mapping.
- Banka dosyası formatı.
- Kilitli dönem export.
- Maker-checker onay.

V1 yerleşik bordro motorunda golden dataset zorunlu olur.

## 5. RLS ve tenant izolasyonu testleri

- Tenant tablosunda `tenant_id` bulunur.
- RLS veya tenant guard eksik tablo CI'da yakalanır.
- App katmanı bypass edilerek DB seviyesinde cross-tenant erişim test edilir.
- Cache key tenant prefix içerir.
- Object storage pre-signed URL tenant kontrolü ister.
- Search/vector sonuçları tenant dışına çıkmaz.

## 6. Güvenlik testleri

| Test | Kapsam |
|---|---|
| Secret scan | Repo içinde secret yok |
| SAST | Güvenlik anti-patternleri |
| SCA | Dependency vulnerability |
| API fuzz | Şema dışı ve sınır değerler |
| DAST | Staging üzerinde baseline tarama |
| BOLA | Object-level authorization |
| File upload | EICAR, çift uzantı, boyut limitleri |
| SSRF | Webhook/connector URL kontrolleri |
| Webhook | HMAC, replay, timestamp |

## 7. Performance testleri

| Senaryo | Hedef |
|---|---|
| Login fırtınası | p95 < 500 ms, hata düşük |
| Employee list read | p95 < 300 ms hedef |
| İzin onayı | p95 < 800 ms hedef |
| Rapor üretimi | p95 < 10 sn |
| PDKS import | 100k satır async işlenebilir |
| Webhook patlaması | DLQ kalıcı artmaz |
| Soak test | Bellek/connection leak yok |

## 8. Regression ve smoke

| Paket | Tetik |
|---|---|
| PR hızlı paket | Unit + integration + contract + smoke |
| Gece tam paket | E2E, security, performance subset |
| Deploy sonrası smoke | Prod sentetik tenant |
| Release regresyonu | Staging bake + kritik flows |

Flaky test politikası:

- E2E max 2 retry.
- Sık kırılan test quarantine olur.
- Quarantine 1 sprint içinde düzeltilir veya kaldırılır.

## 9. UAT ve pilot kabul

GA/pilot çıkış kriterleri:

- Açık P1/P2 hata yok.
- UAT senaryolarının en az %95'i geçti.
- Security kritik/yüksek bulgu yok veya süreli exception var.
- Veri migrasyonu doğrulandı.
- Kritik SLO'lar staging'de kabul edildi.
- Rollback ve backup prosedürü hazır.

## 10. Definition of Done

- Yeni davranış unit test içerir.
- API değiştiyse OpenAPI güncellenir.
- Yetki değiştiyse permission matrix güncellenir.
- Migration varsa migration smoke geçer.
- Kritik akış etkileniyorsa E2E güncellenir.
- Security taraması temizdir.
- Docs ilgili yerde güncellenmiştir.

## 11. İlgili dokümanlar

- [DevOps, Ortamlar ve Sürüm Yönetimi](01-devops-ortamlar-surum-yonetimi.md)
- [Observability, SLO ve Alarm](02-observability-slo-alarm.md)
- [Kimlik Doğrulama ve Yetkilendirme](../06-guvenlik-uyum/01-kimlik-dogrulama-yetkilendirme.md)
