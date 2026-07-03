# Terimler, Roller ve Karar Kaydı

Bu dosya, IK Platform dokümantasyonunda kullanılan temel terimleri, rol ayrımlarını ve erken dönem karar kayıtlarını tutar. [Konvansiyonlar ve Standartlar](01-konvansiyonlar-ve-standartlar.md) dosyası ana kaynak kabul edilir; bu dosya ise tanımları daha anlaşılır hale getirir ve kararların izini tutar.

## 1. Amaç

İK ürünü çok modüllü olduğu için aynı kelime farklı kişiler için farklı anlama gelebilir. Örneğin “yönetici” bazen platform yöneticisi, bazen şirket yöneticisi, bazen ekip yöneticisi anlamına gelir. Bu belirsizlik ileride yanlış yetki, yanlış ekran ve yanlış veri modeli üretir.

Bu dokümanın amacı:

- Temel ürün terimlerini netleştirmek.
- Rol isimlerini teknik ve iş bağlamında açıklamak.
- Karar kayıtlarını tek yerde toplamak.
- Açık soruları görünür kılmak.
- Dokümanlar arasında tutarlılığı korumaktır.

## 2. Temel ürün terimleri

### Tenant

SaaS sisteminde birbirinden izole müşteri kurum hesabıdır. Her tenant kendi kullanıcılarına, çalışanlarına, belgelerine, izin kayıtlarına ve ayarlarına sahiptir. Tenant verisi başka tenant tarafından görülemez.

### Kurum

Müşteri şirketin iş tarafındaki adıdır. Kullanıcı arayüzünde “kurum” veya “şirket” denebilir; teknik dokümanlarda tenant kavramı korunur.

### Çalışan

Kurumun personel kayıtlarında bulunan kişidir. Her çalışan sisteme kullanıcı olarak giriş yapmak zorunda değildir. Örneğin eski çalışan veya pasif personel bir employee kaydı olabilir ama aktif user hesabı olmayabilir.

### Kullanıcı

Sisteme giriş yapabilen hesaptır. Kullanıcı bir çalışanla ilişkili olabilir veya SaaS sağlayıcı tarafında super admin olabilir.

### Rol

Kullanıcının iş bağlamındaki konumunu ifade eder. Örnek: `hr_specialist`, `manager`, `employee`.

### Yetki

Kullanıcının belirli bir kaynak üzerinde belirli bir işlemi yapabilme iznidir. Format: `resource:action`.

### Scope

Yetkinin hangi veri alanında geçerli olduğunu belirtir. Örnekler:

- `own`: sadece kendi verisi
- `team`: kendi ekibi
- `department`: departmanı
- `tenant`: tüm kurum
- `platform`: tüm platform, sadece sağlayıcı tarafı

### Hassas alan

Maaş, TCKN, IBAN, sağlık, engellilik, sendika, disiplin, özel nitelikli kişisel veri veya güvenlik bilgisi gibi erişimi ayrı kontrol edilmesi gereken alandır.

### Audit log

Sistemde önemli bir işlemin kim tarafından, ne zaman, hangi tenant bağlamında, hangi eski/yeni değerlerle yapıldığını kaydeden değiştirilemez izdir.

### Feature flag

Bir özelliğin tenant, rol veya kullanıcı bazında açılıp kapatılmasını sağlayan kontrollü yayın mekanizmasıdır.

### Effective-dated veri

Bir kaydın geçmiş, bugün ve gelecek tarihli geçerliliğini koruyan veri modelidir. İK sistemlerinde pozisyon, departman, ücret, izin hakkı ve yönetici ilişkisi için kritiktir.

## 3. Rol haritası

### Platform rolleri

#### platform_owner

Ürünün sahibi veya ürün ekibi lideridir. Strateji, fiyatlandırma, hedef pazar, roadmap ve yatırım kararlarıyla ilgilenir. Günlük müşteri verisine erişimi olması beklenmez.

#### super_admin

SaaS sağlayıcısı tarafında operasyonel yönetici rolüdür. Tenant açma, plan atama, limit kontrolü, destek için sınırlı erişim ve sistem sağlığını izleme işlerini yapar.

**Risk:** Super admin yanlış tasarlanırsa tenant izolasyonu zedelenir. Bu nedenle break-glass erişim gerekçeli ve audit kayıtlı olmalıdır.

### Kurum yönetim rolleri

#### tenant_admin

Müşteri kurumun sistem yöneticisidir. Kullanıcı, rol, kurum ayarı, departman, modül yapılandırması ve entegrasyon ayarlarını yönetir.

#### hr_director

İK stratejisinden sorumlu üst roldür. Headcount, turnover, izin trendi, performans, kadro, maliyet ve uyum raporlarına ihtiyaç duyar.

#### hr_specialist

Günlük İK operasyonunu yürütür. Personel kayıtları, özlük belgeleri, işe giriş/çıkış, izin düzeltmeleri, belge talepleri ve çalışan yaşam döngüsü süreçlerini yönetir.

#### payroll_specialist

Bordro ve ücret operasyonundan sorumludur. Ücret, yan hak, puantaj, eksik gün, fazla mesai, banka ödeme dosyası ve bordro export süreçlerinde çalışır.

#### finance_user

Finans veya CFO tarafıdır. Bordro maliyeti, işgücü bütçesi, fazla mesai maliyeti, departman bazlı ücret dağılımı gibi raporlara ihtiyaç duyar. Her çalışanın tüm özlük detayını görmesi gerekmez.

#### it_admin

SSO, PDKS, LDAP/AD, e-posta, SMS, webhook, IP allowlist ve güvenlik yapılandırmalarıyla ilgilenir.

### Operasyon rolleri

#### manager

Ekip yöneticisidir. Ekip üyelerinin izin taleplerini onaylar, ekip takvimini görür, performans geri bildirimi verir ve belirli raporları takip eder.

#### employee

Çalışandır. Kendi profilini, izin bakiyesini, belgelerini, bordro pusulasını, duyuruları ve taleplerini self-servis üzerinden yönetir.

#### recruiter

İşe alım operasyonunu yürütür. İlan, aday, mülakat, değerlendirme ve teklif süreçlerini yönetir.

#### auditor

Denetim rolüdür. Veri değiştirmez; sadece yetkili olduğu audit log, rapor ve uyum kayıtlarını okur.

## 4. Scope örnekleri

| Scope | Açıklama | Örnek kullanım |
|---|---|---|
| `own` | Kullanıcının kendi verisi | Çalışan kendi izin bakiyesini görür |
| `team` | Kullanıcının doğrudan ekibi | Yönetici ekip izinlerini onaylar |
| `department` | Departman kapsamı | Departman yöneticisi rapor görür |
| `tenant` | Kurum geneli | İK müdürü tüm çalışanları görür |
| `platform` | SaaS sağlayıcı kapsamı | Super admin tenant listesini görür |

Scope her zaman tenant izolasyonu içinde değerlendirilir. `tenant` scope başka tenant verisine erişim anlamına gelmez.

## 5. Karar kayıtları

### ADR-0001 — Önce dokümantasyon, sonra kod

- **Durum:** Kabul edildi
- **Karar:** Kod iskeleti oluşturulmadan önce ürün, modül, mimari, güvenlik ve yürütme dokümantasyonu tamamlanacaktır.
- **Gerekçe:** Ürün kapsamı geniştir. Erken kod yazmak, yanlış mimari ve gereksiz modül şişmesi riski taşır.
- **Etkisi:** Bu fazda `apps/`, `infra/`, CI/CD veya framework scaffold oluşturulmaz.

### ADR-0002 — Codex iskeleti, Claude derinliği

- **Durum:** Kabul edildi
- **Karar:** Doküman ağacı ve modül kapsamı Codex referansından; detay seviyesi ve uygulanabilirlik Claude referansından alınacaktır.
- **Gerekçe:** Codex daha düzenli ve tam kapsamlı; Claude daha derin ve karar odaklıdır.
- **Etkisi:** Her dosya yazılırken iki kaynak birlikte kontrol edilir.

### ADR-0003 — Mevcut repo dokümanları arşivlenecek, silinmeyecek

- **Durum:** Kabul edildi
- **Karar:** Eski `docs/*.md` dosyaları `_archive/2026-07-03-original` altında korunacaktır.
- **Gerekçe:** Eski dosyalarda değerli modül detayları vardır; ancak yeni yapı daha tutarlı bir omurga gerektirir.
- **Etkisi:** Yeni dokümanlar arşivden yararlanır ama eski dosya adları ana yapı olarak korunmaz.

### ADR-0004 — MVP kapsamı dar tutulacak

- **Durum:** Öneri, kullanıcı onayı bekler
- **Karar önerisi:** MVP; tenant/auth, personel/özlük, belge, izin/onay, self-servis, temel rapor ve audit/KVKK temeliyle sınırlandırılsın.
- **Gerekçe:** Bordro motoru, ATS, performans, AI ve gelişmiş analytics aynı anda MVP'ye girerse ürün canlıya çıkamaz.
- **Etkisi:** Gelişmiş modüller V1/V2'ye alınır; MVP daha hızlı pilotlanır.

### ADR-0005 — Marka adı sonra belirlenecek

- **Durum:** Açık
- **Karar önerisi:** Şimdilik `IK Platform` çalışma adı kullanılsın.
- **Gerekçe:** Erken marka kararı dokümantasyon üretimini yavaşlatmamalı; marka ayrı strateji çalışmasıdır.
- **Etkisi:** Dokümanlarda marka yerine çalışma adı kullanılır.

## 6. Açık sorular

### Q-0001 — Hedef müşteri segmenti kesinleşmeli mi?

- **Seçenek A:** KOBİ odaklı başlamak
- **Seçenek B:** Mid-market odaklı başlamak
- **Seçenek C:** KOBİ + mid-market arası modüler konumlandırma
- **Öneri:** C. Çünkü self-servis + izin + özlük KOBİ'ye, çoklu tenant + yetki + entegrasyon mid-market'e hitap eder.

### Q-0002 — İlk pilot müşteri tipi ne olacak?

- **Seçenek A:** 50-200 çalışanlı şirket
- **Seçenek B:** 200-1000 çalışanlı şirket
- **Seçenek C:** Muhasebe/bordro ofisi gibi çok müşterili hizmet veren yapı
- **Öneri:** A veya B. Çok müşterili hizmet veren yapı ek karmaşıklık yaratır.

### Q-0003 — Bordro motoru MVP'ye girecek mi?

- **Öneri:** Hayır. MVP'de bordro export ve puantaj verisi hazırlığı olsun. Native bordro motoru V2 adayı olsun.

### Q-0004 — Mobil native mi responsive web mi?

- **Öneri:** MVP'de responsive web/PWA öncelikli. Native mobil V1 veya V2'de değerlendirilsin; ancak UX dokümanları mobil öncelikli düşünülmeli.

### Q-0005 — AI özellikleri erken mi geç mi?

- **Öneri:** AI, MVP'de karar verici değil yardımcı olmalı. Örneğin doküman özetleme, ilan metni önerisi veya rapor açıklaması gibi düşük riskli alanlar V1 adayıdır. Hassas karar önerileri V2/Enterprise governance gerektirir.

## 7. Terim kullanım kuralları

- “Personel” ve “çalışan” iş metninde kullanılabilir; veri modeli için `employee` tercih edilir.
- “İzin” LEAVE modülünü, “devamsızlık” mazeretsiz/raporlu/eksik gün gibi durumları ifade eder.
- “Puantaj” bordroya esas zaman verisidir; TIME ile PAY arasındaki köprüdür.
- “Bordro” sadece maaş hesaplama değildir; ücret, kesinti, teşvik, yan hak, banka dosyası, muhasebe fişi ve e-bordro dağıtımıyla birlikte düşünülür.
- “Self-servis” sadece çalışan ekranı değildir; yönetici onay merkezi, talep merkezi ve duyuru/bildirim deneyimini de kapsar.
- “Raporlama” hazır raporlar, dashboard, export ve people analytics seviyelerine ayrılır.

## 8. Karar güncelleme süreci

1. Yeni karar ihtiyacı ilgili dokümanda açık soru olarak yazılır.
2. Karar bu dosyaya ADR olarak eklenir.
3. Etkilenen dokümanlar güncellenir.
4. Eğer karar MVP kapsamını değiştiriyorsa yol haritası ve backlog da revize edilir.

## 9. Bağlantılı dokümanlar

- [Konvansiyonlar ve Standartlar](01-konvansiyonlar-ve-standartlar.md)
- [Doküman İndeksi](../README.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
