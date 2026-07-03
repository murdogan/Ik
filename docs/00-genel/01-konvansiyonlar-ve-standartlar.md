# Konvansiyonlar ve Standartlar

Bu doküman, IK ürün dokümantasyon setinin kanonik karar kaynağıdır. Başka dokümanlarda farklı terim, farklı rol adı veya farklı faz tanımı kullanılamaz. Bir karar değişecekse önce bu dosya güncellenir, sonra bağlı dokümanlar revize edilir.

## 1. Dokümanın amacı

IK projesi geniş kapsamlı bir İnsan Kaynakları Yönetim Sistemi olacağı için ürün, tasarım, backend, frontend, mobil, güvenlik, uyum, test ve operasyon ekiplerinin aynı dili konuşması zorunludur. Bu dosya şu sorulara tek cevap verir:

- Ürünün fazları nasıl adlandırılır?
- MVP sınırı nedir?
- Rol adları ve yetki dili nasıl yazılır?
- Modül kodları nelerdir?
- Dokümanlarda hangi kalite standardı aranır?
- Teknik kararlar nerede tutulur?
- KVKK, güvenlik ve audit gereksinimleri nasıl ele alınır?

## 2. Ürün çalışma adı

Çalışma adı geçici olarak **IK Platform** kabul edilir. Bu ad nihai marka değildir. Dokümanlarda marka gerektiren yerlerde şu kullanım tercih edilir:

- Ürün/genel bağlam: **IK Platform**
- Teknik sistem: **platform**
- Müşteri hesabı: **tenant** veya **kurum**
- Kullanıcı şirket: **müşteri kurum**

Nihai marka kararı verilene kadar dokümanlarda rastgele marka adı türetilmez. Eski kaynaklarda geçen HRX, PeopleCore veya benzeri isimler referans kabul edilmez; marka kararı ayrıca alınır.

## 3. Dil ve yazım standardı

- Doküman dili Türkçedir.
- Teknik terimler gerekirse İngilizce bırakılabilir: tenant, RBAC, API, webhook, audit, SSO, SLA, SLO, endpoint, feature flag.
- Her dosyada markdown başlıkları gerçek `#`, `##`, `###` formatıyla yazılır.
- Büyük metin blokları yerine tablo, liste, akış ve kabul kriterleri tercih edilir.
- Belirsiz cümlelerden kaçınılır. “Gerekirse yapılır” yerine “MVP dışı, V1 adayı” yazılır.
- Varsayımlar açıkça `Varsayım` etiketiyle belirtilir.
- Kararlar `Karar` etiketiyle, açık sorular `Açık soru` etiketiyle yazılır.

## 4. Faz tanımları

Tüm ürün kapsamı aşağıdaki fazlarla ifade edilir.

### MVP

İlk pilot müşteride gerçek iş değerini kanıtlayan, canlıya alınabilir minimum üründür. MVP kapsamı şu özellikleri taşımalıdır:

- Kurum/tenant oluşturulabilir.
- Kullanıcı giriş yapabilir.
- Roller ve temel yetkiler çalışır.
- Personel ve özlük kayıtları yönetilebilir.
- Belge yükleme ve özlük dosyası temel seviyede çalışır.
- İzin talebi, yönetici onayı ve bakiye görüntüleme çalışır.
- Çalışan self-servis portalı temel ihtiyaçları karşılar.
- Temel dashboard ve export vardır.
- Audit log, KVKK aydınlatma/rıza temeli ve veri maskeleme prensipleri uygulanır.

MVP, bordro motoru, gelişmiş ATS, gelişmiş performans, gelişmiş analytics veya kapsamlı AI ürünü değildir.

### V1

MVP sonrası ticari ürünleşme fazıdır. Amaç, daha fazla müşteri segmentine satılabilir hale gelmektir. V1 adayları:

- ATS ve aday portalı
- Performans/OKR temeli
- PDKS/vardiya/puantaj entegrasyonları
- Bordro export ve dış sistem entegrasyonları
- Gelişmiş bildirim ve duyuru sistemi
- Mobil deneyimin genişlemesi

### V2

Operasyonel derinlik ve otomasyon fazıdır. V2 adayları:

- Yerel bordro hesaplama motoru
- Gelişmiş people analytics
- Eğitim, yetkinlik ve kariyer planlama
- Organizasyon/kadro planlama derinliği
- Gelişmiş iş akışı motoru
- AI destekli öneri, özetleme ve risk sinyalleri

### Enterprise

Büyük kurum, regüle sektör ve yüksek SLA ihtiyaçlarına yönelik fazdır. Enterprise adayları:

- Dedicated tenant veya isolated deployment
- SSO/SAML/OIDC ve SCIM
- SIEM entegrasyonu
- Gelişmiş DLP, veri sınıflandırma ve denetim
- Çoklu ülke, çoklu şirket, gelişmiş onay hiyerarşisi
- Yüksek erişilebilirlik, DR ve özel SLA

## 5. Kanonik modül kodları

Tüm dokümanlarda şu modül kodları kullanılacaktır:

- **CORE:** Tenant, plan, kurum ayarları, feature flag, lisans, temel platform ayarları.
- **AUTH:** Kimlik doğrulama, oturum, MFA, parola, SSO, cihaz yönetimi.
- **RBAC:** Roller, izinler, scope, yetki matrisi, hassas alan maskeleme.
- **EMP:** Personel, özlük, employee master data, çalışan yaşam döngüsü.
- **DOC:** Belge yönetimi, doküman şablonları, dosya yükleme, imzalı belgeler.
- **LEAVE:** İzin, devamsızlık, bakiye, onay, ekip takvimi.
- **TIME:** Çalışma takvimi, vardiya, mesai, PDKS, puantaj.
- **PAY:** Bordro, ücret, yan hak, prim, mevzuat parametreleri, banka/muhasebe export.
- **ATS:** İşe alım, ilan, aday, mülakat, teklif, aday portalı.
- **PERF:** Performans, OKR/KPI, 360 değerlendirme, geri bildirim.
- **LMS:** Eğitim, yetkinlik, kariyer, sertifika, succession.
- **ORG:** Organizasyon, departman, pozisyon, kadro, org chart.
- **SS:** Self-servis, talep merkezi, duyuru, onay merkezi, delegasyon.
- **REP:** Raporlama, dashboard, people analytics, export.
- **AI:** AI asistan, CV parsing, özetleme, öneri, governance.
- **INT:** Entegrasyon altyapısı, webhook, outbox, connector, dış sistem adaptörleri.
- **OPS:** DevOps, observability, release, backup, DR, incident response.

## 6. Kanonik kullanıcı rolleri

Kullanıcı rolleri modül bazında genişleyebilir; ancak temel rol isimleri şu şekildedir:

- **platform_owner:** Ürünün sahibi; tüm sistem stratejisi ve ticari kararları yönetir.
- **super_admin:** SaaS sağlayıcı tarafındaki platform yöneticisi; tenant oluşturma, plan/limit yönetimi ve destek operasyonu yapar.
- **tenant_admin:** Müşteri kurumun sistem yöneticisi; kurum ayarları, kullanıcılar, roller, modül yapılandırmaları.
- **hr_director:** İK direktörü veya İK müdürü; stratejik raporlar, onay politikaları, insan kaynağı planlama.
- **hr_specialist:** İK uzmanı; personel, izin, belge, işe giriş/çıkış, operasyonel süreçler.
- **manager:** Ekip yöneticisi; ekip izinleri, performans, onaylar, ekip verileri.
- **employee:** Çalışan; self-servis, izin talebi, belge görüntüleme, profil bilgisi.
- **payroll_specialist:** Bordro/ücret uzmanı; puantaj, bordro export, ücret verileri, yasal parametreler.
- **recruiter:** İşe alım uzmanı; ilan, aday, mülakat, teklif süreci.
- **finance_user:** Finans/CFO rolü; işgücü maliyeti, bütçe, bordro ödeme dosyası, raporlar.
- **auditor:** İç/dış denetçi; sadece okuma, audit log ve uyum raporu erişimi.
- **it_admin:** Müşteri BT yöneticisi; SSO, entegrasyon, PDKS, güvenlik yapılandırmaları.

Rol adları Türkçe cümlede açıklanabilir ama teknik alanlarda yukarıdaki kodlar kullanılmalıdır.

## 7. Yetki dili

Yetkiler `resource:action` formatında yazılır.

Örnekler:

- `employee:create`
- `employee:read`
- `employee:update_sensitive`
- `leave:approve`
- `document:download`
- `payroll:export`
- `audit_log:read`

Hassas veri içeren işlemler ayrı yetkiyle tanımlanır. Örneğin maaş alanını görmek ile çalışan listesini görmek aynı yetki değildir.

## 8. Veri hassasiyet sınıfları

Tüm modüllerde veri alanları aşağıdaki sınıflardan biriyle düşünülmelidir:

- **Public:** Kurum içinde genel görülebilir bilgiler; örnek: duyuru başlığı.
- **Internal:** Sadece kurum kullanıcılarına açık operasyonel veri; örnek: departman adı.
- **Personal:** Kişisel veri; örnek: ad, soyad, telefon, e-posta.
- **Sensitive Personal:** Hassas veya yüksek riskli kişisel veri; örnek: TCKN, sağlık raporu, engellilik bilgisi.
- **Financial:** Ücret, IBAN, bordro, prim, maliyet bilgisi.
- **Security:** Parola hash, MFA secret, oturum token, IP, cihaz bilgisi.
- **Audit:** İşlem kaydı, erişim izi, eski/yeni değer, onay geçmişi.

Her modül dokümanı veri hassasiyet etkisini ayrıca belirtmelidir.

## 9. Tenant ve kurum dili

Ürün çok kiracılı SaaS olarak tasarlanır. Bu nedenle:

- Her operasyon bir tenant bağlamında çalışır.
- Tenant verisi başka tenant tarafından görülemez.
- Super admin erişimi istisnadır; gerekçe, süre ve audit kaydı ister.
- Raporlama, background job, webhook ve export işlemleri tenant bağlamını kaybetmemelidir.

Dokümanlarda “şirket” kelimesi müşteri kurum anlamında kullanılabilir; ancak teknik izolasyon için “tenant” kavramı korunur.

## 10. Doküman kalite standardı

Her ana dokümanda en az şu bölümler beklenir:

1. Amaç
2. Kapsam içi / kapsam dışı
3. Kullanıcı rolleri
4. MVP / V1 / V2 ayrımı
5. Ana akışlar
6. Veri etkisi
7. API veya entegrasyon etkisi
8. Yetki ve güvenlik etkisi
9. KVKK/audit etkisi
10. Test senaryoları veya kabul kriterleri
11. Açık kararlar ve riskler

Kısa doküman yazılabilir; ancak eksik karar bırakan doküman kabul edilmez.

## 11. Kaynak kullanım standardı

Yeni dokümanlar yazılırken kaynak önceliği:

1. Codex zip: kapsam ve dosya iskeleti.
2. Claude zip: kalite ve detay standardı.
3. Mevcut repo arşivi: önceki emek ve yerel detaylar.
4. Güncel mevzuat veya teknik kaynaklar: gerektiğinde ayrıca araştırılır.

Eski kaynaklardan doğrudan kopyalama yapılacaksa çelişki kontrolü yapılır. Örneğin eski repo Django diyorsa ama yeni mimari FastAPI diyorsa karar dokümanında gerekçe yazılmadan taşınmaz.

## 12. Açık karar yönetimi

Her açık karar şu formatta yazılır:

- **Açık karar:** Kısa başlık
- **Seçenekler:** A / B / C
- **Etkisi:** Ürün, teknik, maliyet, zaman
- **Öneri:** Geçici öneri
- **Karar tarihi:** Boş bırakılabilir
- **Sahip:** Kim karar verecek

Kararı netleşmemiş konu kod geliştirmeyi engelliyorsa `blocker` olarak işaretlenir.

## 13. MVP dışı bırakma standardı

Bir özellik MVP dışı bırakılırken “sonra bakılır” denmez. Şu bilgiler yazılır:

- Neden MVP dışı?
- Hangi faza aday?
- MVP'de yerine hangi basit çözüm var?
- Müşteri satışında nasıl anlatılacak?

Örnek: Native bordro hesaplama MVP dışıdır; MVP'de puantaj ve bordro export vardır. Çünkü bordro motoru mevzuat, test ve yasal risk açısından ayrı derinlik ister.

## 14. Bağlı temel dokümanlar

- [Doküman İndeksi](../README.md)
- [Terimler, Roller ve Karar Kaydı](02-terimler-roller-ve-karar-kaydi.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
