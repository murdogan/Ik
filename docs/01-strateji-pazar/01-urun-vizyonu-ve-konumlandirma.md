# Ürün Vizyonu ve Konumlandırma

Bu doküman, IK Platform'un neden var olduğunu, kime hitap ettiğini, hangi problemi çözdüğünü ve pazarda nasıl konumlanacağını tanımlar. Buradaki kararlar; modül kapsamı, MVP planı, mimari kararlar, fiyatlandırma ve satış anlatısı için ana referanstır.

## 1. Yönetici özeti

IK Platform, Türkiye'deki KOBİ ve mid-market şirketlerin parçalı İK operasyonlarını tek veri modeli ve tek ürün deneyimi altında toplayan modern bir İnsan Kaynakları Yönetim Sistemi olarak konumlanır.

Türkiye pazarındaki temel sorun yalnızca “İK yazılımı yok” değildir. Asıl sorun; özlük dosyasının bir yerde, izinlerin Excel'de, PDKS verisinin ayrı cihaz yazılımında, bordro sürecinin muhasebe veya dış servis bürosunda, performansın dokümanlarda, çalışan taleplerinin e-posta/WhatsApp'ta yaşamasıdır. Bu parçalı yapı hem İK ekibinin zamanını yer hem de hata, denetim ve KVKK riskini büyütür.

IK Platform'un ilk iddiası şudur:

> Türkiye gerçeklerine uygun, mevzuat ve KVKK bilinciyle tasarlanmış, çalışan ve yönetici self-servisini merkeze alan, modüler ama tek veri modeline dayanan İK platformu.

Bu aşamada ürünün amacı Workday veya SAP SuccessFactors gibi global enterprise suite'lerle doğrudan yarışmak değildir. İlk hedef, Excel + yerli bordro/muhasebe + ayrı PDKS + manuel onay karışımından yorulmuş şirketlerde hızlı, güvenilir ve canlıya alınabilir bir çekirdek İK platformu kurmaktır.

## 2. Vizyon

IK Platform'un vizyonu:

> Türkiye'de büyüyen şirketlerin çalışan verisi, özlük, izin, onay, vardiya, bordro hazırlığı, performans ve raporlama süreçlerinde tek güvenilir kaynak olmak.

Bu vizyon üç ana ilkeye dayanır:

1. **Tek veri modeli:** Çalışan, departman, pozisyon, yönetici, izin, belge, vardiya ve rapor verileri birbirinden kopuk değil, aynı platform içinde ilişkili tutulur.
2. **Uyum ve güvenlik baştan tasarlanır:** KVKK, audit log, hassas veri maskeleme, yetki ve tenant izolasyonu sonradan eklenen özellik değil, ürünün temelidir.
3. **Self-servis gerçek değer üretir:** Çalışan ve yönetici, İK ekibine sormadan kendi rutin işlemlerini yapabilir; İK ekibi kayıt memurluğundan süreç yöneticiliğine geçer.

## 3. Misyon

IK Platform'un misyonu:

> İK ekiplerini manuel takip, belge kovalama, izin bakiyesi tartışması, onay trafiği ve dağınık veri yükünden kurtarıp; çalışanlara şeffaf, yöneticilere hızlı, şirket yönetimine ölçülebilir bir İK operasyonu sunmak.

Bu misyon gereği ürün sadece “form ve tablo” üretmeyecek; her modülün operasyonel sonucu net olacaktır:

- Personel modülü, şirketin çalışan gerçekliğini doğru tutar.
- Belge modülü, özlük dosyasını denetime hazır hale getirir.
- İzin modülü, bakiye ve onay karmaşasını azaltır.
- Self-servis, İK ekibine gelen tekrar eden soruları düşürür.
- Raporlama, yönetime manuel Excel yerine güncel veri sunar.
- Güvenlik ve audit, “kim ne yaptı?” sorusuna net cevap verir.

## 4. Problem tanımı

### 4.1 Bugünkü tipik durum

Orta ölçekli bir Türkiye şirketinde İK süreçleri çoğunlukla aşağıdaki gibi parçalanmıştır:

| Süreç | Bugünkü araç | Sorun |
|---|---|---|
| Personel ve özlük | Excel, klasör, ağ diski | Tek doğruluk kaynağı yok, belge eksikleri geç fark edilir |
| İzin | Excel, e-posta, WhatsApp | Bakiye hatası, onay izi eksikliği, ekip takvimi karmaşası |
| PDKS ve vardiya | Cihaz yazılımı veya manuel puantaj | Bordro öncesi elle düzeltme ve mutabakat gerekir |
| Bordro | Muhasebe yazılımı veya dış servis | İK verisi ve puantaj dış sistemlere elle taşınır |
| Performans | Word/Excel formları | Geçmiş veri kaybolur, hedef takibi düzenli yapılmaz |
| İşe alım | E-posta, kariyer portalları | Aday havuzu ve KVKK saklama düzeni zayıf kalır |
| Duyuru/talep | E-posta, WhatsApp, sözlü takip | İş akışı ve sorumluluk izi yoktur |
| Raporlama | Manuel Excel | Yönetim güncel veri yerine gecikmeli rapor görür |

### 4.2 Parçalılığın maliyeti

Bu parçalı yapı şirketlere şu maliyetleri üretir:

- İK ekibinin zamanının büyük kısmı veri toplama ve düzeltmeye gider.
- Çalışanlar basit bilgi için İK'ya bağımlı kalır.
- İzin ve puantaj hataları bordro döneminde ortaya çıkar.
- Denetim veya KVKK talebinde veri bulmak zorlaşır.
- Yönetim doğru headcount, turnover, devamsızlık ve maliyet verisini geç alır.
- Yeni çalışan işe girişi ve işten çıkış süreçleri kişiye bağlı yürür.

Bu sorunlar özellikle çalışan sayısı 100'ü geçtikten sonra hızla büyür. 20 kişilik şirkette Excel kabul edilebilirken, 300 kişilik şirkette aynı yöntem operasyonel risk haline gelir.

## 5. Hedef müşteri segmenti

### 5.1 Birincil segment

İlk hedef segment:

| Kriter | Hedef |
|---|---|
| Çalışan sayısı | 100-1000 |
| Şirket tipi | Büyüyen KOBİ ve mid-market |
| İK ekibi | 1-8 kişilik İK/operasyon ekibi |
| Mevcut durum | Excel + ayrı bordro/muhasebe + manuel onaylar |
| Ana acı | Personel, izin, belge, onay ve rapor süreçlerinin dağınıklığı |
| Satın alma motivasyonu | Operasyonu düzene sokmak, denetime hazır olmak, çalışan self-servisi kurmak |

Bu segment seçilmelidir çünkü ürün değeri hızlı gösterilebilir. Çok küçük şirketler fiyat duyarlı ve süreçleri basittir. Çok büyük enterprise müşteriler ise uzun satış döngüsü, entegrasyon, SSO, özel SLA ve uyarlama ister.

### 5.2 İkincil segment

V1 ve sonrası için hedef segment:

| Kriter | Hedef |
|---|---|
| Çalışan sayısı | 1000-5000 |
| Şirket tipi | Çok şubeli, vardiyalı, üretim/perakende/hizmet şirketleri |
| Ana ihtiyaç | PDKS, vardiya, puantaj, gelişmiş onay, entegrasyon ve raporlama |
| Ürün gereksinimi | Daha güçlü TIME, PAY export, API, SSO ve gelişmiş audit |

### 5.3 Bilinçli kapsam dışı segmentler

| Segment | Neden şimdi değil? |
|---|---|
| 1-50 çalışanlı mikro işletmeler | Fiyat hassasiyeti yüksek, ürünün derinliği fazla gelebilir |
| 5000+ global enterprise | Satış döngüsü uzun, özel entegrasyon ve güvenlik beklentisi ağır |
| Sadece bordro isteyen müşteriler | Ürünün ana tezi tek başına bordro değil, bütünleşik İK operasyonudur |
| Sadece ATS isteyen müşteriler | ATS modülü değerli ama ilk wedge özlük + izin + self-servis olmalıdır |

## 6. Konumlandırma cümlesi

Kısa konumlandırma:

> IK Platform; Türkiye'deki büyüyen şirketler için personel, özlük, izin, onay, belge ve raporlama süreçlerini tek güvenli platformda toplayan, KVKK ve self-servis odaklı modern İK yönetim sistemidir.

Daha geniş konumlandırma:

> IK Platform, Excel ve parçalı sistemlerle büyümeye çalışan şirketlere; çalışan verisini tek kaynakta tutan, izin ve belge süreçlerini dijitalleştiren, yönetici/çalışan self-servisini kuran, KVKK ve audit disiplinini ürüne gömen modüler bir HRMS sunar. Global ürünlerin Türkiye pratiklerinden uzak kaldığı, yerli ürünlerin de çoğu zaman modern UX, API ve genişletilebilirlikte zayıfladığı noktada; yerel gerçeklere uygun ama modern SaaS disipliniyle ilerleyen bir alternatif oluşturur.

## 7. Değer önerisi

### 7.1 İK ekibi için

- Tek çalışan kaydı üzerinden tüm süreçleri yönetir.
- Belge, izin, talep ve onay takibini manuel listelerden çıkarır.
- Denetim için gereken kayıtları ve audit izini sistemde tutar.
- Çalışanlardan gelen tekrar eden soruları self-servise taşır.
- Yönetim raporlarını elle toplamadan üretir.

### 7.2 Çalışan için

- Kendi izin bakiyesini görür.
- İzin talebini platformdan açar.
- Belgelerini ve duyuruları tek yerden takip eder.
- Profil bilgilerinin doğruluğunu kontrol eder.
- İK'ya sormadan rutin süreçleri tamamlar.

### 7.3 Yönetici için

- Ekibinin izin taleplerini görür ve onaylar.
- Ekip takvimi ve devamsızlık durumunu takip eder.
- Çalışan bilgilerine yetkisi kadar erişir.
- Onay bekleyen işleri tek kuyrukta görür.

### 7.4 Şirket yönetimi için

- Headcount, devamsızlık, izin kullanımı ve temel İK metriklerini görür.
- İK operasyonunun kişiye bağlı değil sisteme bağlı yürümesini sağlar.
- KVKK ve denetim risklerini azaltır.
- Büyüme döneminde süreçlerin dağılmasını engeller.

## 8. Farklılaşma sütunları

### 8.1 Türkiye pratiğine uygun kapsam

Ürün; izin, özlük, belge, bordro hazırlığı, PDKS, vardiya ve KVKK gibi Türkiye şirketlerinin gerçek ihtiyaçlarını merkeze alır. Global ürünlerdeki soyut HR terminolojisi yerine yerel süreçler ve pratik operasyon hedeflenir.

### 8.2 Tek veri modeli

Çalışan bilgisi bir kez tanımlanır; izin, belge, performans, puantaj, rapor ve self-servis aynı çalışan kaydına bağlanır. Böylece modüller “yan yana duran ayrı ürünler” değil, aynı sistemin parçaları olur.

### 8.3 Self-servis ve onay merkezi

Çalışan ve yönetici tarafı ilk günden düşünülür. Ürün yalnızca İK uzmanının kullandığı bir arka ofis sistemi olmaz; çalışan deneyimi de ürünün değerinin parçası olur.

### 8.4 KVKK, güvenlik ve audit disiplini

Hassas alan maskeleme, tenant izolasyonu, audit log, veri saklama ve erişim yetkisi ürün tasarımında baştan yer alır. Bu, özellikle çalışan verisi gibi hassas bir alanda güven yaratır.

### 8.5 Modüler büyüme

MVP dar ama sağlam başlar. TIME, PAY, ATS, PERF, LMS, AI gibi derin modüller kontrollü fazlarla eklenir. Böylece ürün hem ilk canlıya hızlı çıkabilir hem de uzun vadede genişleyebilir.

## 9. Ürün ilkeleri

| İlke | Uygulama kararı |
|---|---|
| Önce çekirdek veri | Personel ve organizasyon modeli sağlam olmadan ileri modül yazılmaz |
| Self-servis varsayılandır | Çalışanın kendisinin yapabileceği işlem İK'ya yüklenmez |
| Yetki en baştan tasarlanır | Hassas veri sonradan saklanmaz; baştan role/scope ile korunur |
| MVP şişirilmez | İlk canlıya değer üretmeyen özellik V1/V2'ye taşınır |
| Entegrasyon gerçekçi kurulur | MVP'de her entegrasyon native olmak zorunda değildir; import/export geçiş çözümü olabilir |
| AI karar vermez | AI özellikleri ileride destekleyici olur; hukuki/finansal sonucu olan kararlarda insan onayı gerekir |
| Dokümansız kod yok | Kod aşamasına ancak ürün ve mimari kararları netleşince geçilir |

## 10. Başarı metrikleri

| Metrik | MVP hedefi | Neden önemli? |
|---|---|---|
| İlk tenant kurulum süresi | 1 iş günü içinde temel kurulum | Ürünün kurulum karmaşıklığını ölçer |
| İlk çalışan importu | Hatasız örnek import | Personel veri modelinin çalıştığını gösterir |
| İzin talebi tamamlama | Çalışan için 1 dakikanın altında | Self-servis değerini gösterir |
| Yönetici onay tamamlama | 30 saniyenin altında | Yönetici deneyimini ölçer |
| İK destek sorusu azalması | Pilot sonrası ölçüm | Self-servisin işe yarayıp yaramadığını gösterir |
| Audit kapsaması | Kritik işlemlerin tamamı | Denetim ve güvenlik temelidir |
| Kırık veri/tenant izolasyon hatası | 0 tolerans | SaaS güvenliği için kritiktir |

## 11. Stratejik riskler

| Risk | Etki | Azaltım |
|---|---|---|
| MVP'nin aşırı büyümesi | Canlıya çıkış gecikir | Faz kararları sıkı tutulur |
| Bordro motorunun erken alınması | Yasal/test riski büyür | MVP'de bordro export/hazırlık; native motor V2 |
| Enterprise müşteriye erken odaklanma | Satış döngüsü uzar | İlk hedef 100-1000 çalışan segmenti |
| Yerli rakiplerle fiyat savaşı | Marj düşer | Self-servis, güvenlik, API ve bütünleşik değer satılır |
| AI beklentisinin şişmesi | Ürün odağı bozulur | AI düşük riskli destek özelliklerine ertelenir |
| KVKK/güvenlik eksikliği | Güven kaybı | Başlangıçtan audit, maskeleme, scope ve saklama politikası |

## 12. Kapsam dışı netlik

Bu ürün ilk aşamada şunları vaat etmez:

- Tüm bordro mevzuatını hesaplayan eksiksiz native bordro motoru.
- Workday/SAP seviyesinde global enterprise suite.
- Her PDKS cihazına hazır entegrasyon.
- Tam otomatik AI işe alım veya performans kararı.
- Her sektöre özel uçtan uca çözüm.

Bu netlik önemlidir; çünkü ürünün ilk başarısı her şeyi yapmakla değil, doğru çekirdeği hızlı ve sağlam canlıya almakla gelecektir.

## 13. Bağlı dokümanlar

- [Doküman İndeksi](../README.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
- [Terimler, Roller ve Karar Kaydı](../00-genel/02-terimler-roller-ve-karar-kaydi.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
