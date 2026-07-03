# Fiyatlandırma ve Paketleme

Bu doküman, IK Platform'un nasıl paketleneceğini, fiyat mantığının hangi metriklere dayanacağını ve ticari kararların ürün kapsamıyla nasıl hizalanacağını tanımlar. Bu aşamadaki rakamlar kesin liste fiyatı değildir; ürün stratejisi ve satış denemeleri için kontrollü varsayımlardır.

## 1. Amaç

Fiyatlandırma sadece para belirleme işi değildir. Ürünün hangi segmenti hedeflediğini, hangi özellikleri çekirdekte sunduğunu, hangi değerleri eklentiye ayırdığını ve satışta hangi beklentileri yöneteceğini belirler.

Bu dokümanın amacı:

- MVP ve sonraki fazlarla uyumlu paketleri tanımlamak.
- Aktif çalışan bazlı lisanslama mantığını netleştirmek.
- Başlangıçta kaç paketle pazara çıkılacağını belirlemek.
- Bordro, AI, Enterprise ve destek gibi alanlarda eklenti mantığını kurmak.
- Fiyatın ürün kapsamını şişirmemesini sağlamaktır.

## 2. Fiyatlandırma ilkeleri

| İlke | Karar |
|---|---|
| Basit metrik | Ana fiyatlama aktif çalışan başına aylık modelle yapılır |
| MVP dürüstlüğü | Henüz hazır olmayan V1/V2 özellikleri MVP fiyatına gizlice satılmaz |
| Çekirdek güvenlik dahil | RBAC, audit ve temel KVKK özellikleri eklenti değil çekirdek değerdir |
| Modüler büyüme | Müşteri önce çekirdekle başlar, sonra PDKS/bordro/AI/Enterprise'a genişler |
| Fiyat savaşı yok | Ucuz ürün olmak yerine güvenli ve bütünleşik değer satılır |
| TRY önceliği | Türkiye pazarında fiyatlama TL bazlı düşünülür; döviz riski iç maliyet yönetimiyle izlenir |
| Şeffaf paketleme | Müşteri hangi fazda hangi yeteneğin geldiğini açıkça görür |

## 3. Lisans metriği

Ana lisans metriği: **aktif çalışan başına aylık ücret**.

| Terim | Tanım |
|---|---|
| Aktif çalışan | Tenant içinde aktif statüde bulunan ve özlük/İK süreçleri yönetilen kişi |
| Pasif/ayrılmış çalışan | İşten çıkışı işlenmiş, arşivde tutulan kayıt; lisans tüketmez |
| Aday | ATS içindeki candidate kaydı; employee olmadığı sürece lisans tüketmez |
| Sistem kullanıcısı | Entegrasyon/API hesabı; çalışan lisansı sayılmaz |
| Minimum fatura | Mikro müşteri yükünü engellemek için minimum aktif çalışan adedi belirlenir |

MVP döneminde önerilen minimum fatura tabanı: **50 çalışan**. Bu sınır, ürünün 1-50 çalışan mikro işletme segmentini bilinçli hedeflememesiyle uyumludur.

## 4. Paket mimarisi

### 4.1 Core paketi

Hedef segment: 100-500 çalışanlı, Excel ve manuel süreçlerden çıkmak isteyen şirketler.

Core paketinin değeri: Personel, özlük, belge, izin, self-servis ve temel rapor süreçlerini tek platforma taşır.

| Dahil | Faz |
|---|---|
| Tenant ve kurum ayarları | MVP |
| Kullanıcı, temel rol ve yetki | MVP |
| Çalışan kartı ve employee master data | MVP |
| Özlük ve belge yönetimi | MVP |
| İzin türleri, bakiye, talep ve onay | MVP |
| Çalışan self-servis | MVP |
| Yönetici onay kuyruğu | MVP |
| Temel dashboard ve export | MVP |
| Audit log ve temel KVKK kontrolleri | MVP |
| Responsive web/PWA | MVP |

Core paketi, ilk canlıya alınacak ürünün ana paketidir.

### 4.2 Professional paketi

Hedef segment: 500-2000 çalışanlı, çok şubeli veya vardiyalı operasyonu olan şirketler.

Professional paketinin değeri: Core üzerine PDKS, puantaj, bordro hazırlığı, gelişmiş self-servis, ATS/performance başlangıcı ve entegrasyon kabiliyeti ekler.

| Dahil | Faz |
|---|---|
| Core paketi | MVP |
| PDKS import / CSV / mapping | V1 |
| Vardiya ve puantaj yönetimi | V1 |
| Bordro export / bordro hazırlığı | V1 |
| ATS ve aday portalı temel | V1 |
| Performans/OKR temel | V1 |
| API ve webhook temeli | V1 |
| Gelişmiş raporlar | V1 |
| Mobil/PWA deneyim genişletmeleri | V1 |

Professional, uzun vadede ana gelir paketi olabilir. Ancak MVP'de Professional adı kullanılacaksa hangi yeteneklerin daha sonra açılacağı net yazılmalıdır.

### 4.3 Enterprise paketi

Hedef segment: 2000+ çalışan veya regüle/güvenlik hassasiyeti yüksek kurumlar.

Enterprise paketinin değeri: Güvenlik, entegrasyon, operasyon ve SLA beklentilerini karşılar.

| Dahil | Faz |
|---|---|
| Professional paketi | V1 |
| SSO / SAML / OIDC | V1/Enterprise |
| SCIM provisioning | Enterprise |
| SIEM audit export | Enterprise |
| IP allowlist | Enterprise |
| Dedicated tenant / dedicated DB opsiyonu | Enterprise |
| Gelişmiş audit ve DLP kontrolleri | Enterprise |
| SLA ve premium destek | Enterprise |
| Sandbox tenant | Enterprise |

Enterprise, MVP satış hedefi değildir. Erken dönemde yalnızca stratejik tasarım ortağı varsa kontrollü ele alınmalıdır.

### 4.4 AI Edition

AI Edition ayrı bir paket/eklenti olarak düşünülmelidir; çekirdek ürünün yerine geçmez.

| Özellik | Faz | Not |
|---|---|---|
| Politika dokümanı soru-cevap | V1 | Düşük riskli destek alanı |
| İlan metni önerisi | V1 | İnsan onaylı |
| CV ayrıştırma taslağı | V1 | ATS'e bağlı |
| Rapor özetleme | V1/V2 | Karar vermez, açıklar |
| Attrition risk sinyali | V2 | Yüksek dikkat ve governance ister |
| Anomali tespiti | V2 | Bordro/puantaj verisi olgunlaşınca |

AI fiyatlaması ayrı izlenmelidir çünkü maliyet tarafı API/token/döviz etkisine açık olabilir.

## 5. Paket-özellik matrisi

| Yetenek | Core | Professional | Enterprise | AI Edition |
|---|---|---|---|---|
| Tenant / kurum ayarları | Dahil | Dahil | Dahil | - |
| Auth / temel MFA hazırlığı | Dahil | Dahil | Dahil | - |
| RBAC / scope / maskeleme | Dahil | Dahil | Dahil | - |
| Personel ve özlük | Dahil | Dahil | Dahil | - |
| Belge yönetimi | Dahil | Dahil | Dahil | - |
| İzin ve onay | Dahil | Dahil | Dahil | - |
| Self-servis | Dahil | Dahil | Dahil | - |
| Temel rapor | Dahil | Dahil | Dahil | - |
| PDKS / vardiya / puantaj | Sınırlı hazırlık | Dahil | Dahil | - |
| Bordro export | Eklenti/adım | Dahil | Dahil | - |
| Native bordro motoru | Yok | V2 adayı | V2/Enterprise | - |
| ATS | Yok | Dahil | Dahil | CV AI opsiyonel |
| Performans | Yok | Dahil | Dahil | Özetleme opsiyonel |
| LMS / kariyer | Yok | V2 | Dahil/V2 | Öneri opsiyonel |
| API / webhook | Yok/sınırlı | Dahil | Dahil | - |
| SSO / SCIM / SIEM | Yok | Sınırlı/opsiyon | Dahil | - |
| Dedicated tenant | Yok | Yok | Opsiyon | - |
| AI asistan | Yok | Eklenti | Eklenti | Dahil |

## 6. Fiyat seviyesi varsayımları

Bu bölüm kesin fiyat listesi değildir. İlk müşteri görüşmeleri, rakip teklifleri ve pilot geri bildirimiyle doğrulanmalıdır.

| Paket | Fiyat mantığı | Not |
|---|---|---|
| Core | Düşük-orta PEPM | İlk geçişi kolaylaştırmalı ama ucuz ürün algısı yaratmamalı |
| Professional | Core'un belirgin üstü | Ana gelir paketi, PDKS/bordro hazırlığı değerini taşır |
| Enterprise | Özel teklif | SLA, güvenlik, entegrasyon ve operasyon maliyeti değişkendir |
| AI Edition | Ek PEPM veya kullanım kotası | Maliyet ve değer ayrı izlenmeli |
| Kurulum | Paket/çalışan sayısı bazlı | Veri migrasyonu, eğitim ve yapılandırma için alınabilir |

Örnek fiyatlar ancak müşteri keşfi sonrası kesinleşmelidir. Bu aşamada önemli olan fiyat rakamı değil, paket mantığının ürün stratejisiyle uyumudur.

## 7. Kurulum ve hizmet kalemleri

| Kalem | Açıklama | Paket ilişkisi |
|---|---|---|
| Self-servis onboarding | Şablon import, yardım dokümanı, dijital eğitim | Core |
| Rehberli kurulum | Uzaktan eğitim ve ilk veri yükleme desteği | Core/Professional |
| Veri migrasyonu | Çalışan, departman, izin bakiyesi, belge aktarımı | Professional+ |
| Entegrasyon kurulumu | PDKS, e-posta, SMS, API, bordro export | Professional+ |
| Güvenlik workshop | IT değerlendirme, SSO, audit, veri saklama | Enterprise |
| Yerinde eğitim | Çok lokasyonlu veya mavi yaka yoğun şirketler | Professional/Enterprise |

Kurulum hizmeti kâr merkezi olmak zorunda değildir; asıl amacı müşterinin ilk değere hızlı ulaşmasını sağlamaktır. Ancak ücretsiz sınırsız hizmet verilirse operasyon sürdürülemez hale gelir.

## 8. İndirim politikası

İndirim kontrolsüz yapılırsa ürün erken dönemde ucuz konumlanır ve büyüme aşamasında fiyat artırmak zorlaşır.

| İndirim tipi | Ne zaman kullanılmalı? | Risk |
|---|---|---|
| Yıllık peşin ödeme indirimi | Nakit akışını iyileştirmek için | Çok yüksek olmamalı |
| İlk pilot/tasarım ortağı indirimi | Referans ve geri bildirim karşılığında | Sonsuz indirim beklentisi yaratabilir |
| Hacim indirimi | Büyük çalışan sayısı için | Minimum marj korunmalı |
| Kurulum indirimi | Satışı hızlandırmak için | Ürün fiyatı değil hizmet indirilmeli |
| Partner indirimi | Kanal komisyonu gibi ele alınmalı | Müşteriye farklı fiyat karmaşası yaratmamalı |

Kural: Ürün abonelik fiyatı kolay kırılmamalı; gerekiyorsa kurulum veya pilot süresi üzerinden esneklik sağlanmalıdır.

## 9. Fiyatlandırma riskleri

| Risk | Etki | Önlem |
|---|---|---|
| Core fazla ucuz konumlanır | Professional'a geçiş zorlaşır | Core kapsamı net, Professional değer farkı belirgin tutulur |
| Bordro motoru erken fiyatlanır | Hazır olmayan özellik için güven kaybı | Bordro V1/V2 fazı açık yazılır |
| AI maliyeti marjı düşürür | Kullanım arttıkça zarar edilebilir | AI Edition ayrı izlenir, kota ve overage düşünülür |
| Enterprise erken satılır | Destek ve güvenlik yükü ürünü yavaşlatır | Enterprise satışları kontrollü kabul edilir |
| Rakip fiyat savaşı | Değer yerine fiyat konuşulur | TCO, güvenlik, self-servis ve operasyon değeri anlatılır |
| Kurulum bedeli itirazı | Satış kapanışı zorlaşır | Kurulumun neyi kapsadığı net gösterilir |

## 10. Validasyon planı

Fiyatlandırma kesinleşmeden önce şu çalışmalar yapılmalıdır:

1. 10-15 hedef müşteriyle paket algısı görüşmesi.
2. Core vs Professional değer farkı testleri.
3. “Bordro olmadan alır mısınız?” sorusunun sistematik ölçümü.
4. Kurulum ücreti itirazlarının kaydı.
5. Rakip teklifleri ve win/loss analizleri.
6. Pilot müşterilerde çalışan sayısı/fiyat hassasiyeti ölçümü.
7. AI Edition için ödeme isteği testi.

## 11. MVP için ticari öneri

İlk canlıya çıkış için önerilen paketleme:

- Ana paket adı: **Core** veya geçici olarak **IK Core**.
- Dahil: Personel, özlük, belge, izin, self-servis, temel rapor, RBAC, audit.
- V1 roadmap açıkça gösterilir: PDKS, bordro export, ATS, performans, API.
- Enterprise ve AI özellikleri satış vaadi değil, roadmap/faz olarak anlatılır.
- İlk tasarım ortaklarına sınırlı süreli indirim verilebilir; karşılığında düzenli geri bildirim ve referans hakkı alınmalıdır.

## 12. Bağlı dokümanlar

- [Ürün Vizyonu ve Konumlandırma](01-urun-vizyonu-ve-konumlandirma.md)
- [Pazar ve Rakip Analizi](02-pazar-ve-rakip-analizi.md)
- [Farklılaşma ve Değer Önerisi](03-farklilasma-ve-deger-onermesi.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
- [Ürün Metrikleri ve Başarı Kriterleri](../02-urun/04-urun-metrikleri-ve-basari-kriterleri.md)
