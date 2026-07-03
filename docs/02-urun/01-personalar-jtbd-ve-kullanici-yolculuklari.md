# Personalar, JTBD ve Kullanıcı Yolculukları

Bu doküman, IK Platform'un kimler için tasarlanacağını, bu kişilerin hangi işleri başarmaya çalıştığını ve ürünün hangi uçtan uca yolculukları kusursuz çözmesi gerektiğini tanımlar. Modül dokümanları yazılırken kullanıcı kararları bu dosyaya göre kontrol edilir.

## 1. Amaç

İK yazılımı yalnızca İK ekibinin kullandığı bir yönetim paneli değildir. Başarılı bir HRMS; İK uzmanı, İK müdürü, çalışan, yönetici, bordro uzmanı, IT, finans ve ileride aday gibi farklı kullanıcıların günlük işlerini aynı veri modeli üzerinde çözer.

Bu dokümanın amacı:

- Ana kullanıcı personlarını belirlemek.
- Her persona için hedef, ağrı noktası ve başarı ölçütlerini tanımlamak.
- JTBD mantığıyla gerçek kullanıcı ihtiyaçlarını yazmak.
- MVP'de kusursuz çalışması gereken yolculukları netleştirmek.
- Modül ve tasarım kararlarının insan tarafını görünür kılmaktır.

## 2. Persona haritası

| Persona | Kanonik rol | Ana hedef | En büyük ağrı | Birincil yüzey |
|---|---|---|---|---|
| Elif — İK Müdürü | `hr_director` | İK operasyonunu denetlenebilir ve ölçülebilir yönetmek | Dağınık veri, geciken rapor, belge/izin karmaşası | Web yönetim paneli |
| Deniz — İK Uzmanı | `hr_specialist` | Günlük personel, belge, izin ve talep işlerini hatasız yürütmek | Tekrarlı veri girişi, evrak takibi, çalışan soruları | Web yönetim paneli |
| Mehmet — Bordro Uzmanı | `payroll_specialist` | Bordro öncesi veriyi doğru ve zamanında kapatmak | Puantaj/izin verisinin dağınık gelmesi | Web yönetim paneli |
| Can — Beyaz yaka çalışan | `employee` | Kendi İK işlemlerini hızlı tamamlamak | İzin/belge/bordro için İK'ya sormak | Web + mobil self-servis |
| Ayşe — Mavi yaka çalışan | `employee` | Telefonda basit self-servis kullanmak | Kurumsal e-posta/bilgisayar yok, süreçler amire bağlı | Mobil/PWA |
| Selim — Yönetici | `manager` | Ekip onaylarını ve takvimini hızlı yönetmek | Onayların e-postada kaybolması | Mobil + web yönetici portalı |
| Burak — IT/Sistem yöneticisi | `it_admin` | Güvenli erişim ve entegrasyon kurmak | Ayrı kullanıcı yönetimi, veri güvenliği riski | Web admin/entegrasyon paneli |
| Nazan — CFO/Finans | `finance_user` | İşgücü maliyeti ve İK riskini görmek | İK verisinin finansla geç mutabık olması | Web dashboard |
| Zeynep — Aday | V1 `candidate` | Başvuru sürecini hızlı ve şeffaf tamamlamak | Başvuru sonrası belirsizlik | Kariyer sitesi/adaya özel portal |
| Auditor | `auditor` | Değişiklik ve erişim kayıtlarını denetlemek | Kimin ne yaptığına dair iz eksikliği | Read-only audit paneli |

MVP'de ana odak Elif, Deniz, Can, Ayşe ve Selim'dir. Mehmet, Burak ve Nazan MVP kararlarını etkiler; Zeynep V1 ATS fazında öncelik kazanır.

## 3. Persona kartları

### 3.1 Elif — İK Müdürü

| Alan | İçerik |
|---|---|
| Bağlam | 300-800 çalışanlı, büyüyen bir şirkette İK operasyonundan sorumlu. Ekibi küçük ama beklenti yüksek. |
| Hedef | Denetime hazır, ölçülebilir ve kişiye bağımlı olmayan İK operasyonu kurmak. |
| Ağrı | Excel raporları, eksik belge takibi, izin bakiyesi itirazları, yönetimden gelen ani rapor talepleri. |
| Başarı ölçütü | Denetimde belge bulgusu çıkmaması, raporların manuel birleştirilmemesi, İK ekibinin tekrar eden sorularının azalması. |
| Ürün beklentisi | Tek çalışan kaydı, eksik belge/izin raporları, self-servis, audit, temel dashboard. |

### 3.2 Deniz — İK Uzmanı

| Alan | İçerik |
|---|---|
| Bağlam | Personel kayıtları, işe giriş/çıkış, belge, izin ve çalışan talepleriyle günlük çalışan kişi. |
| Hedef | İşleri tek tek takip etmek yerine sistemli ve hatasız yürütmek. |
| Ağrı | Aynı bilgiyi tekrar girmek, evrak kovalamak, çalışanlardan gelen “bakiyem ne?” soruları. |
| Başarı ölçütü | Açık talep kuyruğunun azalması, belge eksiklerinin erken görünmesi, çalışan kaydının tek seferde doğru oluşması. |
| Ürün beklentisi | Toplu import, zorunlu alan kontrolü, belge checklist'i, kolay arama, şablon ve uyarılar. |

### 3.3 Mehmet — Bordro Uzmanı

| Alan | İçerik |
|---|---|
| Bağlam | Bordro döneminin doğru kapanmasından sorumlu, mevzuat ve puantaj konusunda hassas kullanıcı. |
| Hedef | Bordro öncesi veriyi hatasız, onaylı ve izlenebilir hale getirmek. |
| Ağrı | Puantajın Excel ile gelmesi, izinlerin geç işlenmesi, eksik gün/fazla mesai mutabakatı. |
| Başarı ölçütü | Bordro sonrası düzeltme oranının düşmesi, puantaj farklarının bordrodan önce yakalanması. |
| Ürün beklentisi | MVP'de temiz export; V1'de PDKS/puantaj entegrasyonu; V2'de kanıtlanmış bordro motoru. |

### 3.4 Can — Beyaz Yaka Çalışan

| Alan | İçerik |
|---|---|
| Bağlam | Bilgisayar ve kurumsal e-posta kullanır; bankacılık ve birçok işlemi mobilden yapmaya alışkındır. |
| Hedef | İzin, belge, duyuru ve profil işlemlerini İK'ya sormadan tamamlamak. |
| Ağrı | Belge talebinin gecikmesi, izin bakiyesini öğrenmek için mesaj atmak, duyuruları kaçırmak. |
| Başarı ölçütü | İzin talebini hızlı açabilmek, belgesine erişebilmek, talebin durumunu görebilmek. |
| Ürün beklentisi | Basit self-servis, net durum bilgisi, gereksiz bildirim almamak. |

### 3.5 Ayşe — Mavi Yaka Çalışan

| Alan | İçerik |
|---|---|
| Bağlam | Kurumsal e-postası veya masaüstü erişimi olmayabilir. Telefonda basit işlemler yapabilir. |
| Hedef | İzin, vardiya, bordro ve duyuru bilgisini telefondan görmek. |
| Ağrı | Her bilgi için amire veya İK'ya gitmek, şifre yönetiminde zorlanmak, karmaşık ekranlarda kaybolmak. |
| Başarı ölçütü | İşlemi mola sırasında 1-2 dakikada bitirmek. |
| Ürün beklentisi | SMS/telefon bazlı aktivasyon, biyometrik giriş, büyük butonlar, sade dil, düşük veri tüketimi. |

Ayşe personasi kritik önemdedir. Ürün yalnızca beyaz yaka çalışan için iyi çalışırsa üretim/perakende gibi hedef sektörlerde benimseme düşük kalır.

### 3.6 Selim — Yönetici

| Alan | İçerik |
|---|---|
| Bağlam | Ekibi olan, yoğun çalışan, çoğu onayı mobilde vermek isteyen yönetici. |
| Hedef | Ekip izinlerini ve taleplerini iş akışını bozmadan hızlı onaylamak. |
| Ağrı | Onayların e-postada kaybolması, ekip takvimi görünmeden karar vermek, yetki devri olmaması. |
| Başarı ölçütü | Onay SLA'larının kısalması, bekleyen onayların görünür olması. |
| Ürün beklentisi | Tek onay kuyruğu, ekip takvimi, çakışma uyarısı, mobil bildirim, delegasyon. |

### 3.7 Burak — IT/Sistem Yöneticisi

| Alan | İçerik |
|---|---|
| Bağlam | SaaS güvenliği, kullanıcı erişimi ve entegrasyonlardan sorumlu. |
| Hedef | Yeni sistemin güvenli, yönetilebilir ve ileride entegre edilebilir olması. |
| Ağrı | Ayrı kullanıcı havuzları, kapalı API, belirsiz veri güvenliği, tenant izolasyonu şüphesi. |
| Başarı ölçütü | Güvenlik değerlendirmesinin sorunsuz geçmesi, erişimlerin kontrol edilebilir olması. |
| Ürün beklentisi | RBAC, audit, veri maskeleme, API/webhook yol haritası, V1/Enterprise SSO. |

### 3.8 Nazan — CFO/Finans

| Alan | İçerik |
|---|---|
| Bağlam | İnsan kaynağı maliyeti, bütçe, uyum riski ve yazılım maliyetini takip eder. |
| Hedef | İK operasyonunun maliyetini ve riskini görünür kılmak. |
| Ağrı | Headcount, izin, fazla mesai ve bordro verisinin geç ve farklı kaynaklardan gelmesi. |
| Başarı ölçütü | Yönetim raporlarının güvenilirliği, işgücü maliyet trendlerinin izlenmesi. |
| Ürün beklentisi | Temel dashboard, export, V1/V2'de maliyet ve puantaj/bordro görünürlüğü. |

### 3.9 Zeynep — Aday

| Alan | İçerik |
|---|---|
| Bağlam | V1 ATS fazında ürünün dış dünyaya açılan yüzünü kullanır. |
| Hedef | Başvurusunu hızlı yapmak ve süreci takip etmek. |
| Ağrı | Uzun formlar, başvuru sonrası belirsizlik, tekrar tekrar CV bilgisi girmek. |
| Başarı ölçütü | Başvurunun dakikalar içinde tamamlanması ve durumun görünmesi. |
| Ürün beklentisi | Mobil uyumlu başvuru, rıza metni, durum takibi, mülakat planlama. |

## 4. JTBD analizi

### 4.1 İK Müdürü

| Durum | İstek | Beklenen sonuç | Faz |
|---|---|---|---|
| Yönetim raporu istendiğinde | Güncel headcount ve izin durumunu görmek | Excel birleştirmeden rapor sunmak | MVP |
| Denetim hazırlığı gerektiğinde | Eksik belge ve audit izini görmek | Riskleri önceden kapatmak | MVP |
| Yeni şube/departman açıldığında | Organizasyon ve yönetici ilişkilerini kurmak | İzin/onay akışı doğru çalışsın | MVP/V1 |
| Büyüme döneminde | İşe giriş/çıkış yükünü sistemle yönetmek | İK ekibi boğulmasın | MVP/V1 |

### 4.2 İK Uzmanı

| Durum | İstek | Beklenen sonuç | Faz |
|---|---|---|---|
| Yeni çalışan başladığında | Zorunlu alan ve belge checklist'i görmek | Özlük dosyası eksik kalmasın | MVP |
| Çalışan bilgi güncellemek istediğinde | Onaylı self-servis talebi almak | Telefonla veri toplamayım | MVP |
| Belge talebi geldiğinde | Şablondan belge üretmek veya dosyayı göstermek | Manuel Word/e-posta işi azalsın | MVP/V1 |
| Toplu import gerektiğinde | Şablonla çalışanları yüklemek | Tek tek kayıt açmayayım | MVP |

### 4.3 Çalışan

| Durum | İstek | Beklenen sonuç | Faz |
|---|---|---|---|
| İzin planlarken | Bakiyemi ve talep durumumu görmek | İK'ya sormadan ilerlemek | MVP |
| Belgeye ihtiyacım olduğunda | Self-servisten talep/görüntüleme yapmak | Beklemeden sonuca ulaşmak | MVP |
| Bordrom yayınlandığında | Güvenli şekilde görüntülemek | Kâğıt veya e-posta beklememek | V1 |
| Duyuru yayınlandığında | Telefona bildirim almak | Bilgiyi kaçırmamak | MVP/V1 |

### 4.4 Yönetici

| Durum | İstek | Beklenen sonuç | Faz |
|---|---|---|---|
| İzin talebi geldiğinde | Bakiye ve ekip takvimiyle birlikte görmek | Doğru onay kararı vermek | MVP |
| Yoğun dönemde | Onayları tek kuyrukta görmek | E-postada kaybolmasın | MVP |
| Tatildeyken | Yetkimi geçici devretmek | Süreç kilitlenmesin | V1 |
| Performans dönemi geldiğinde | Hedef ve geri bildirim akışını yönetmek | Yıl sonu sürprizi olmasın | V1 |

### 4.5 Bordro Uzmanı

| Durum | İstek | Beklenen sonuç | Faz |
|---|---|---|---|
| Ay sonu yaklaşırken | İzin ve puantaj verisinin eksiklerini görmek | Bordro öncesi hatayı yakalamak | V1 |
| Bordro sistemine veri verirken | Temiz export almak | Elle veri taşımamak | V1 |
| Mevzuat değiştiğinde | Parametre ve hesap kararlarını izlemek | Hangi dönemde ne geçerli bilmek | V2 |

### 4.6 IT/Güvenlik

| Durum | İstek | Beklenen sonuç | Faz |
|---|---|---|---|
| Sistemi değerlendirirken | Güvenlik ve veri erişim modelini görmek | Veto riskini azaltmak | MVP |
| Kullanıcı erişimi yönetirken | Rol ve yetki modelini kontrol etmek | Gereksiz erişim olmasın | MVP |
| Enterprise müşteride | SSO/SCIM/SIEM entegrasyonu | Kurumsal güvenlik standardı sağlansın | Enterprise |

## 5. Kritik kullanıcı yolculukları

### 5.1 Yolculuk 1: İlk tenant kurulumu ve çalışan importu

| Adım | Kullanıcı | Sistem davranışı | Başarı kriteri |
|---|---|---|---|
| Kurum oluşturulur | `super_admin` veya `tenant_admin` | Tenant ve varsayılan ayarlar açılır | Kurum dakikalar içinde oluşur |
| Rol seti tanımlanır | `tenant_admin` | Varsayılan roller atanır | HR, manager, employee ayrımı net |
| Çalışan listesi yüklenir | `hr_specialist` | Import doğrulama ve hata listesi üretir | Hatalar satır bazında görünür |
| Departman/yönetici ilişkisi kurulur | `hr_specialist` | ORG ilişkileri oluşur | İzin akışı yöneticiye düşebilir |
| İlk rapor alınır | `hr_director` | Headcount ve eksik alan raporu görünür | İlk değer gösterilir |

### 5.2 Yolculuk 2: Çalışan oluşturma ve belge yönetimi

| Adım | Kullanıcı | Sistem davranışı | Başarı kriteri |
|---|---|---|---|
| Yeni çalışan açılır | `hr_specialist` | Zorunlu alanları kontrol eder | Eksik alanla aktif edilemez |
| Pozisyon/yönetici atanır | `hr_specialist` | ORG ve scope ilişkisi kurulur | Manager kendi ekibini görebilir |
| Belge yüklenir | `hr_specialist` | DOC kaydı ve dosya bağlantısı oluşur | Yetkisiz kullanıcı göremez |
| Çalışan self-servise girer | `employee` | Kendi bilgilerini görüntüler | Own scope çalışır |
| Audit incelenir | `auditor` veya yetkili rol | Değişiklik kaydı görünür | Kim/ne zaman/ne yaptı belli |

### 5.3 Yolculuk 3: İzin talebi ve yönetici onayı

| Adım | Kullanıcı | Sistem davranışı | Başarı kriteri |
|---|---|---|---|
| Çalışan izin türü seçer | `employee` | Bakiye ve tarih kontrolü yapar | Hatalı tarih/bakiye uyarılır |
| Talep gönderilir | `employee` | Onay akışı oluşur | Talep doğru manager'a düşer |
| Yönetici talebi inceler | `manager` | Bakiye ve ekip takvimi gösterilir | Karar bağlamlı verilir |
| Onay/red yapılır | `manager` | Çalışana bildirim gider | Durum anında güncellenir |
| Rapor güncellenir | `hr_specialist` | İzin raporu ve audit güncellenir | Rapor manuel işlem istemez |

### 5.4 Yolculuk 4: Mavi yaka mobil self-servis

| Adım | Kullanıcı | Sistem davranışı | Başarı kriteri |
|---|---|---|---|
| İlk aktivasyon | `employee` | Telefon/SMS veya kurum kodu ile giriş akışı | Kurumsal e-posta gerekmez |
| Basit giriş | `employee` | Biyometrik veya kısa güvenli giriş | Şifre unutma yükü azalır |
| İzin talebi | `employee` | Büyük butonlu sade akış | 1-2 dakikada tamamlanır |
| Bildirim | Sistem | Onay/red sonucu push/in-app gösterir | Çalışan sonucu takip eder |
| Offline okuma | `employee` | Son duyuru/bakiye sınırlı cache | Zayıf internette temel bilgi görünür |

### 5.5 Yolculuk 5: Bordro öncesi veri hazırlığı

Bu yolculuk MVP'de tam bordro motoru anlamına gelmez; V1'e hazırlık zinciridir.

| Adım | Kullanıcı | Sistem davranışı | Faz |
|---|---|---|---|
| İzinler kapanır | `manager` / `hr_specialist` | Onaylı izin verisi oluşur | MVP |
| Puantaj verisi hazırlanır | `payroll_specialist` | Manuel/CSV veri kontrol edilir | V1 |
| Farklar incelenir | `payroll_specialist` | Eksik veri ve onaysız kayıt raporu | V1 |
| Export alınır | `payroll_specialist` | Dış bordro sistemine dosya hazırlanır | V1 |
| Audit yazılır | Sistem | Export ve dönem kilidi kaydı | V1 |

## 6. Persona bazlı öncelik matrisi

| Özellik | Elif | Deniz | Mehmet | Can | Ayşe | Selim | Burak | Nazan | Faz |
|---|---|---|---|---|---|---|---|---|---|
| Çalışan kartı | Yüksek | Kritik | Orta | Düşük | Düşük | Orta | Düşük | Orta | MVP |
| Belge yönetimi | Kritik | Kritik | Düşük | Orta | Orta | Düşük | Düşük | Orta | MVP |
| İzin talebi | Yüksek | Yüksek | Orta | Kritik | Kritik | Kritik | Düşük | Orta | MVP |
| Self-servis | Yüksek | Yüksek | Düşük | Kritik | Kritik | Orta | Düşük | Düşük | MVP |
| Audit/yetki | Yüksek | Orta | Orta | Düşük | Düşük | Orta | Kritik | Yüksek | MVP |
| PDKS/puantaj | Orta | Orta | Kritik | Düşük | Orta | Orta | Orta | Yüksek | V1 |
| ATS | Orta | Orta | Düşük | Düşük | Düşük | Orta | Düşük | Orta | V1 |
| Performans | Orta | Düşük | Düşük | Orta | Düşük | Kritik | Düşük | Orta | V1 |
| Bordro motoru | Yüksek | Orta | Kritik | Orta | Orta | Düşük | Orta | Kritik | V2 |
| AI | Orta | Orta | Orta | Düşük | Düşük | Orta | Orta | Orta | V1/V2 |

## 7. MVP tasarım kararlarına etkisi

Bu persona çalışması aşağıdaki MVP kararlarını doğrudan destekler:

1. **MVP'de self-servis zorunlu:** Çünkü çalışan ve yönetici kullanımı olmadan ürün sadece İK kayıt sistemi olur.
2. **Mobil deneyim ihmal edilemez:** Ayşe personasi, üretim/perakende hedefi için kritik benimseme noktasıdır.
3. **Belge ve izin akışı ilk sırada:** İK müdürü ve uzman için en hızlı değer bu akışlardadır.
4. **RBAC ve maskeleme baştan şart:** İK verisi rol/scope olmadan güvenli yönetilemez.
5. **Bordro motoru ertelenmeli ama veri hazırlığı düşünülmeli:** Mehmet ve Nazan'ın ihtiyacı V1/V2'de güçlü şekilde gelir; MVP'de temel veri doğru kurulmalıdır.
6. **Aday personası V1'e alınmalı:** ATS değerli ama MVP çekirdeği tamamlanmadan öncelik olmamalıdır.

## 8. Kullanıcı araştırmasıyla doğrulanacak varsayımlar

| Varsayım | Doğrulama yöntemi |
|---|---|
| 100-1000 çalışan segmentinde izin/özlük/self-servis yeterli MVP değeri üretir | 10 hedef müşteri görüşmesi ve demo geri bildirimi |
| Mavi yaka çalışan mobil self-servisi benimser | Pilot kullanıcı testi ve aktivasyon oranı ölçümü |
| İK uzmanı import/onboarding akışını yeterli bulur | Gerçek anonim çalışan listesiyle kurulum testi |
| Yönetici onay ekranında ekip takvimi görmek ister | Prototip testinde karar süresi ölçümü |
| Bordro motoru MVP dışı kalınca satış kaybı sınırlı olur | Demo sonrası kayıp/kazanım sebebi analizi |
| KVKK/audit satışta güven yaratır | IT/hukuk değerlendirme görüşmeleri |

## 9. Kabul kriterleri

Bu doküman doğrultusunda ürün tasarımı kabul edilebilir sayılmak için:

- MVP akışlarında Elif, Deniz, Can, Ayşe ve Selim için net değer görünmeli.
- Çalışan self-servis işlemleri 3-4 adımdan uzun olmamalı.
- Yönetici onay ekranı bağlamsız “onayla/reddet” butonu olmamalı; bakiye ve ekip takvimi göstermeli.
- Hassas alanlar her persona için varsayılan görünür olmamalı.
- Mavi yaka çalışan kurumsal e-posta olmadan aktivasyon yapabilmeli veya bunun alternatifi planlanmalı.
- Audit ve yetki gereksinimleri persona akışlarına gömülü olmalı.

## 10. Bağlı dokümanlar

- [Doküman İndeksi](../README.md)
- [Ürün Vizyonu ve Konumlandırma](../01-strateji-pazar/01-urun-vizyonu-ve-konumlandirma.md)
- [MVP, V1 ve V2 Kapsam Kararları](03-mvp-v1-v2-kapsam-kararlari.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](02-kanallar-web-mobil-self-servis.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
