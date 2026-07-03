# MVP, V1 ve V2 Kapsam Kararları

Bu doküman, IK Platform'un hangi özellikleri ilk canlı sürüme alacağını, hangi özellikleri sonraki fazlara bırakacağını ve bu kararların nedenlerini tanımlar. Ürünün başarı şansı, MVP'yi yeterince değerli ama yeterince dar tutmaya bağlıdır.

## 1. Amaç

İK platformu doğal olarak çok geniş bir ürün alanıdır. Personel, özlük, izin, bordro, vardiya, performans, işe alım, eğitim, raporlama, self-servis, mobil, entegrasyon ve AI aynı anda düşünüldüğünde ürün kolayca yönetilemez hale gelir.

Bu dokümanın amacı:

- İlk canlıya alınacak MVP kapsamını netleştirmek.
- MVP dışı bırakılan özelliklerin neden dışarıda kaldığını açıklamak.
- V1, V2, Enterprise ve AI fazlarını birbirinden ayırmak.
- Modül dokümanlarının kapsam şişirmesini engellemek.
- Kod aşamasına geçildiğinde backlog'un hangi sırayla uygulanacağını belirlemektir.

## 2. Kapsam kararı özeti

IK Platform'un ilk canlıya çıkış stratejisi:

> Önce çalışan ana verisi, özlük, belge, izin/onay, self-servis, temel rapor ve güvenlik/audit çekirdeği kurulacak. Bordro motoru, gelişmiş PDKS/vardiya, ATS, performans, LMS, gelişmiş analytics ve AI özellikleri sonraki fazlara bırakılacak.

Bu kararın gerekçesi:

- İlk değer, şirketin çalışan verisini ve izin/özlük süreçlerini düzene sokmakla üretilebilir.
- Bordro ve mevzuat motoru yüksek yasal risk taşır; erken alınırsa ürünü kilitler.
- ATS, performans ve eğitim değerli modüllerdir ama ilk canlıya çıkış için şart değildir.
- AI, iyi veri ve governance olmadan ürün vaadini bulanıklaştırır.
- İlk pilotta başarılması gereken şey “her şeyi yapmak” değil, çekirdek İK operasyonunu güvenilir hale getirmektir.

## 3. Faz tanımları

### 3.1 MVP

MVP, ilk pilot müşteride gerçek kullanıcılarla canlıya alınabilecek minimum üründür. Demo veya prototip değildir. Kullanıcı giriş yapar, çalışan verisi girilir, izin talebi açılır, yönetici onaylar, belge yüklenir, temel rapor alınır ve tüm kritik işlemler audit log'a düşer.

MVP'nin başarı kriteri: Bir şirketin en temel İK operasyonlarını Excel ve e-posta yerine platform üzerinden yürütebilmesidir.

### 3.2 V1

V1, MVP'nin ticari ürüne dönüşme fazıdır. Amaç, daha fazla müşteri tipine satılabilir olmak ve operasyonel kapsamı genişletmektir. PDKS/vardiya, ATS, performans, gelişmiş bildirim, API/webhook ve bordro export bu fazda güçlenir.

### 3.3 V2

V2, ürünün derinleşme fazıdır. Native bordro motoru, gelişmiş people analytics, eğitim/yetkinlik/kariyer, gelişmiş organizasyon/kadro planlama ve AI destekli özellikler burada olgunlaşır.

### 3.4 Enterprise

Enterprise, büyük kurum, regüle sektör ve yüksek güvenlik ihtiyacı olan müşteriler için ayrı sertleştirme fazıdır. SSO/SAML, SCIM, SIEM, dedicated tenant, DLP, gelişmiş audit, DR ve SLA bu fazda ele alınır.

### 3.5 AI Edition

AI Edition, temel veri modeli ve güvenlik/governance oturduktan sonra açılacak destekleyici yapay zekâ katmanıdır. AI kritik İK kararlarını otomatik vermez; önerir, özetler, sınıflandırır ve insan onayından geçer.

## 4. MVP kapsamı

MVP kapsamı aşağıdaki modüllerden oluşur.

| Modül | MVP'deki kapsam | Neden gerekli? |
|---|---|---|
| CORE | Tenant, kurum ayarları, plan/feature flag temeli | Her müşteri izole hesap olarak kurulmalı |
| AUTH | Login, parola, oturum, temel MFA hazırlığı | Güvenli erişim olmadan ürün canlıya alınamaz |
| RBAC | Temel roller, permission, own/team/tenant scope | Hassas İK verisi rol bazlı korunmalı |
| EMP | Çalışan kartı, employee master data, durum yönetimi | Tüm İK süreçlerinin ana verisi |
| DOC | Belge yükleme, belge türü, geçerlilik takibi | Özlük dosyası ve denetim değeri için şart |
| LEAVE | İzin türleri, bakiye, talep, yönetici onayı | En hızlı self-servis değeri veren süreç |
| SS | Çalışan portalı, yönetici onay kuyruğu, temel talep | İK yükünü azaltan kullanıcı katmanı |
| ORG | Departman, pozisyon, yönetici ilişkisi temel modeli | Yetki, rapor ve izin akışı için gerekli |
| REP | Temel dashboard, çalışan listesi, izin raporu, export | Yönetim ve İK için görünür çıktı |
| OPS | Audit log, temel hata izleme, backup disiplini | Canlı ürün güvenliği ve destek için şart |
| KVKK | Aydınlatma/rıza kaydı, veri maskeleme, saklama prensibi | İK verisi kişisel/hassas veri içerir |

## 5. MVP kapsam dışı

Aşağıdaki özellikler bilinçli olarak MVP dışıdır.

| Özellik | Neden MVP dışı? | Hangi faz? | MVP'deki basit alternatif |
|---|---|---|---|
| Native bordro hesaplama motoru | Yasal risk ve test yükü yüksek | V2 | Puantaj/bordro export hazırlığı |
| Gelişmiş PDKS cihaz entegrasyonları | Her cihaz farklı veri formatı üretir | V1 | CSV import veya manuel puantaj girişi |
| Gelişmiş vardiya optimizasyonu | Karmaşık planlama algoritması gerektirir | V1/V2 | Basit çalışma takvimi ve vardiya alanları |
| ATS ve aday portalı | Çekirdek İK operasyonu için ilk şart değil | V1 | Çalışan işe giriş süreci EMP içinde yürür |
| Performans/OKR/360 | Kültürel ve süreçsel tasarım ister | V1 | Çalışan/organizasyon verisi hazır tutulur |
| Eğitim/LMS/succession | İleri yetenek yönetimi alanıdır | V2 | Sertifika/belge takibi DOC içinde sınırlı tutulur |
| Gelişmiş people analytics | Veri hacmi ve modelleme olgunluğu ister | V2 | Temel dashboard ve export |
| AI karar destek | Veri, izin, model governance gerektirir | V1/V2 | AI'sız manuel süreçler |
| SAML/SCIM/SIEM | Enterprise müşteri ihtiyacı | Enterprise | Temel kullanıcı/rol yönetimi |
| Dedicated tenant/on-prem | Operasyonel maliyet yüksek | Enterprise | Standart multi-tenant SaaS |
| Çok ülkeli payroll | Mevzuat kapsamı çok geniş | V2/Enterprise | Türkiye odaklı veri modeli |

## 6. MVP kullanıcı hikayesi omurgası

MVP, aşağıdaki uçtan uca akışları çalıştırmalıdır.

### 6.1 Kurum kurulumu

1. Super admin veya tenant admin yeni kurum hesabını oluşturur.
2. Kurum adı, vergi bilgisi, temel ayarlar ve saat dilimi tanımlanır.
3. İlk tenant admin kullanıcısı oluşturulur.
4. Temel roller ve varsayılan izinler atanır.
5. Audit log `tenant.created` ve `user.created` olaylarını yazar.

### 6.2 Çalışan oluşturma

1. HR specialist çalışan kartı oluşturur.
2. Zorunlu kişisel ve kurumsal alanlar doldurulur.
3. Departman, pozisyon ve yönetici ilişkisi atanır.
4. Hassas alanlar yetkiye göre maskelenir.
5. Audit log `employee.created` olayını yazar.

### 6.3 Belge yükleme

1. HR specialist çalışan kartından belge yükler.
2. Belge türü, geçerlilik tarihi ve görünürlük seviyesi seçilir.
3. Sistem belgeyi ilgili çalışan özlük dosyasına bağlar.
4. Yetkisiz kullanıcı belgeyi göremez veya indiremez.
5. Audit log `document.uploaded` ve indirme olursa `document.downloaded` yazar.

### 6.4 İzin talebi ve onay

1. Employee self-servis üzerinden izin talebi açar.
2. Sistem izin türünü ve bakiye uygunluğunu kontrol eder.
3. Talep manager onay kuyruğuna düşer.
4. Manager onaylar veya gerekçeyle reddeder.
5. Sonuç çalışana bildirilir.
6. Audit log `leave.requested`, `leave.approved` veya `leave.rejected` yazar.

### 6.5 Temel raporlama

1. HR specialist çalışan listesi, izin raporu ve belge eksik raporunu görüntüler.
2. Yetkisi olan kullanıcı CSV/XLSX export alır.
3. Export işlemi audit log'a düşer.
4. Hassas alanlar export yetkisine göre maskelenir.

## 7. MVP başarı kriterleri

MVP tamamlandı sayılmadan önce aşağıdaki kriterler sağlanmalıdır.

| Alan | Kabul kriteri |
|---|---|
| Tenant izolasyonu | Bir tenant kullanıcısı başka tenant çalışanını göremez |
| Auth | Kullanıcı güvenli şekilde giriş/çıkış yapabilir |
| RBAC | Employee kendi verisini, manager ekibini, HR tenant kapsamını görür |
| Personel | Çalışan CRUD, durum yönetimi ve temel arama çalışır |
| Belge | Belge yükleme, görüntüleme, indirme ve audit çalışır |
| İzin | Talep, bakiye kontrolü, onay/red ve bildirim çalışır |
| Self-servis | Çalışan kendi izin/belge/profil alanlarını görür |
| Rapor | Temel çalışan ve izin raporları alınır |
| KVKK | Hassas alan maskeleme ve audit event'ler vardır |
| Test | Kritik akışlar otomatik veya manuel kabul testinden geçer |

## 8. V1 kapsamı

V1, MVP sonrası ilk ticari genişleme fazıdır.

| Modül | V1 kapsamı | Değer |
|---|---|---|
| TIME | PDKS import, vardiya, puantaj kilidi | Bordro öncesi zaman verisini düzene sokar |
| PAY | Bordro export, banka/muhasebe dosya hazırlığı | Native motor olmadan bordro sürecine değer katar |
| ATS | İlan, aday, mülakat, teklif temel süreci | İşe alımı sisteme bağlar |
| PERF | Hedef, değerlendirme dönemi, yönetici geri bildirimi | Çalışan performans sürecini dijitalleştirir |
| SS | Gelişmiş talep formları, duyuru, delegasyon | Self-servis değerini artırır |
| INT | API, webhook, e-posta/SMS/push genişlemesi | Platformu dış sistemlere açar |
| Mobil/PWA | İzin, onay, profil, duyuru mobil deneyimi | Çalışan kullanımını artırır |
| REP | Daha fazla dashboard ve export | Yönetim görünürlüğünü artırır |

V1'in hedefi: Ürünün sadece özlük/izin aracı değil, orta ölçekli şirketin günlük İK operasyon platformu haline gelmesidir.

## 9. V2 kapsamı

V2, derinleşme ve otomasyon fazıdır.

| Modül | V2 kapsamı | Değer |
|---|---|---|
| PAY | Native bordro/mevzuat motoru | En güçlü yerel farklılaşma alanı |
| REP | People analytics, özel rapor, semantic layer | Stratejik İK içgörüsü |
| LMS | Eğitim, yetkinlik, kariyer, succession | Yetenek yönetimi derinliği |
| ORG | Kadro planlama, norm kadro, senaryo analizi | İnsan kaynağı planlama |
| AI | HR asistan, özetleme, anomali, öneri | Operasyonel verimlilik ve karar destek |
| Workflow | Gelişmiş iş akışı ve kural motoru | Modüller arası otomasyon |

V2'nin hedefi: Ürünü yalnızca operasyon sistemi olmaktan çıkarıp karar destek ve otomasyon platformuna taşımaktır.

## 10. Enterprise kapsamı

Enterprise fazı büyük kurum ve regüle sektör gereksinimlerini karşılar.

| Alan | Enterprise kapsamı |
|---|---|
| Kimlik | SAML/OIDC SSO, SCIM, gelişmiş MFA politikaları |
| Güvenlik | SIEM export, IP allowlist, DLP, gelişmiş audit |
| Altyapı | Dedicated tenant, özel veritabanı, private cloud/on-prem opsiyonu |
| Operasyon | SLA, DR, backup testleri, sandbox tenant |
| Yetki | Gelişmiş ABAC, alan bazlı ve kayıt bazlı yetki |
| Uyum | Denetim paketleri, veri saklama/imha otomasyonu |

Enterprise fazı MVP'ye karıştırılmamalıdır. Aksi halde ürün ilk müşteriye çıkmadan kurumsal altyapı ağırlığı altında yavaşlar.

## 11. AI kapsamı

AI özellikleri ürünün uzun vadeli fark yaratma alanıdır; ancak erken fazda kontrollü ilerlemelidir.

### MVP'de AI

MVP'de AI zorunlu değildir. MVP'nin AI'sız değer üretmesi gerekir.

### V1 AI adayları

- İlan metni önerisi
- Çalışan politika dokümanı soru-cevap asistanı
- CV alan ayrıştırma taslağı
- Rapor açıklaması veya özetleme

### V2 AI adayları

- Aday eşleştirme skoru
- Attrition risk sinyali
- Performans değerlendirme özetleri
- Anomali tespiti
- Doğal dil rapor sorgusu

### AI için değişmeyen kural

AI, hukuki veya finansal sonucu olan İK kararını otomatik vermez. İnsan onayı, açıklanabilirlik, loglama, veri minimizasyonu ve tenant izolasyonu zorunludur.

## 12. Önceliklendirme ilkeleri

Bir özellik faza yerleştirilirken şu sorular sorulur:

1. İlk pilot müşteride bu olmadan gerçek kullanım mümkün mü?
2. Bu özellik veri modelinin temelini mi kuruyor, yoksa üst katman mı?
3. Yasal veya finansal hata riski yüksek mi?
4. Entegrasyon bağımlılığı var mı?
5. Manuel/import/export alternatifi MVP için yeterli mi?
6. Bu özellik satışta kritik mi, yoksa “güzel olur” mu?
7. Test ve destek yükü ilk ekip kapasitesini aşar mı?

Bu soruların cevabına göre özellik MVP, V1, V2 veya Enterprise'a alınır.

## 13. Fazlar arası bağımlılık haritası

| Önce gereken | Sonra gelen | Gerekçe |
|---|---|---|
| CORE + AUTH + RBAC | Tüm modüller | Güvenli tenant ve kullanıcı temeli olmadan modül çalışmaz |
| EMP + ORG | LEAVE, PAY, PERF, REP | Çalışan ve organizasyon verisi ana kaynaktır |
| EMP + DOC | Özlük, onboarding, offboarding | Belge süreçleri çalışan kaydına bağlıdır |
| LEAVE + SS | Yönetici/çalışan self-servis | İzin en hızlı self-servis kullanım senaryosudur |
| TIME | PAY | Puantaj bordro verisinin girdisidir |
| REP | Tüm operasyon verileri | Raporlama veri üreten modüllerden beslenir |
| Güvenlik/KVKK | Tüm modüller | Hassas İK verisi her modülde korunmalıdır |
| Veri olgunluğu | AI | AI güvenilir veri ve governance ister |

## 14. MVP canlıya çıkış tanımı

MVP canlıya çıkış, sadece kodun deploy edilmesi değildir. Aşağıdaki koşullar gerekir:

- En az bir pilot tenant kurulmuş olmalı.
- Gerçek veya gerçekçi anonimleştirilmiş çalışan verisi import edilmiş olmalı.
- En az bir izin talebi uçtan uca tamamlanmış olmalı.
- Belge yükleme ve yetkili görüntüleme doğrulanmış olmalı.
- Audit log kritik işlemleri kaydetmiş olmalı.
- Tenant izolasyonu test edilmiş olmalı.
- Hassas alan maskeleme test edilmiş olmalı.
- Temel backup ve rollback prosedürü yazılmış olmalı.
- Kullanıcı eğitim notu ve destek akışı hazırlanmış olmalı.

## 15. Bu dokümana göre sonraki iş sırası

1. Pazar ve rakip analizi netleştirilecek.
2. Farklılaşma ve değer önerisi yazılacak.
3. Personalar ve kullanıcı yolculukları yazılacak.
4. Core/Auth/RBAC modül dokümanı yazılacak.
5. Personel/özlük/doküman modülü yazılacak.
6. İzin/onay/self-servis modülü yazılacak.
7. Sonra mimari ve veri modeli detaylarına geçilecek.

## 16. Bağlı dokümanlar

- [Doküman İndeksi](../README.md)
- [Ürün Vizyonu ve Konumlandırma](../01-strateji-pazar/01-urun-vizyonu-ve-konumlandirma.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
- [Terimler, Roller ve Karar Kaydı](../00-genel/02-terimler-roller-ve-karar-kaydi.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
