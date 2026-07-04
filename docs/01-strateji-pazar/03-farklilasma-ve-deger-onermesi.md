# Farklılaşma ve Değer Önerisi

Bu doküman, IK Platform'un pazarda hangi iddiayla ayrışacağını ve farklı paydaşlara hangi değer cümlesiyle anlatılacağını tanımlar. Pazar ve rakip resmi [Pazar ve Rakip Analizi](02-pazar-ve-rakip-analizi.md) dosyasında, ürünün genel konumlandırması [Ürün Vizyonu ve Konumlandırma](01-urun-vizyonu-ve-konumlandirma.md) dosyasında ele alınmıştır.

## 1. Yönetici özeti

IK Platform'un farklılaşması tek bir özellikten gelmez. “İzin modülü var”, “personel kartı var”, “rapor var” gibi tekil özellikler kolay kopyalanır. Asıl farklılaşma, Türkiye'deki büyüyen şirketlerin dağınık İK operasyonunu tek veri modeli, self-servis deneyimi, güvenlik/KVKK disiplini ve fazlı genişleme mimarisiyle bir araya getirmekten gelir.

Temel değer önerisi:

> IK Platform, Excel ve parçalı sistemlerle büyümeye çalışan şirketlere; personel, özlük, belge, izin, onay, self-servis ve rapor süreçlerini tek güvenli platformda toplayarak İK operasyonunu kişiye bağımlı olmaktan çıkarır.

Bu değer önerisi MVP'de sade kalır. V1 ve V2'de PDKS, puantaj, bordro hazırlığı, ATS, performans, analytics ve AI ile derinleşir.

## 2. Farklılaşma mantığı

Ürün şu üç seviyede ayrışmalıdır:

1. **İlk değer:** Şirketin bugün manuel yürüttüğü personel, belge, izin ve self-servis süreçlerini dijital ve denetlenebilir hale getirmek.
2. **Operasyonel derinlik:** V1'de PDKS, puantaj, bordro export, ATS, performans ve entegrasyonlarla günlük İK operasyonunu genişletmek.
3. **Stratejik platform:** V2 ve Enterprise'da bordro motoru, people analytics, gelişmiş güvenlik, AI ve kurumsal entegrasyonlarla platform değerini artırmak.

Bu sıralama önemlidir. Ürün en başta “AI destekli dev HR suite” diye konumlanırsa MVP odağı dağılır. En başta “basit izin yazılımı” diye konumlanırsa uzun vadeli platform değeri zayıflar. Doğru ifade: **çekirdekten başlayan, platforma büyüyen İK sistemi**.

## 3. Ana farklılaşma sütunları

### 3.1 Tek çalışan veri modeli

Çoğu şirkette çalışan verisi farklı yerlerde yaşar: bordro programında ayrı, PDKS sisteminde ayrı, Excel'de ayrı, özlük klasöründe ayrı. IK Platform'un ilk ayrışması, employee master data'yı merkeze almasıdır.

Bu şu anlama gelir:

- Çalışan bir kez tanımlanır.
- Departman, pozisyon, yönetici ve çalışma bilgileri ilişkili tutulur.
- İzin, belge, talep, rapor ve ileride bordro/performans aynı çalışan kaydına bağlanır.
- Yetki ve maskeleme bu ana model üzerinde çalışır.
- Raporlar dağınık dosyalardan değil sistem verisinden beslenir.

Bu sütun MVP'nin temelidir. Eğer çalışan veri modeli zayıf kurulursa sonraki tüm modüller parçalı hale gelir.

### 3.2 Self-servis ve onay merkezi

IK Platform yalnızca İK ekibinin veri girdiği bir arka ofis sistemi olmamalıdır. Çalışan ve yönetici ilk günden ürünün parçası olmalıdır.

MVP'deki self-servis değeri:

- Çalışan izin bakiyesini görür.
- İzin talebi açar.
- Belgelerini görüntüler.
- Duyuru ve talepleri takip eder.
- Yönetici izin ve talepleri tek kuyruktan onaylar.

Bu sayede ürün, İK ekibine gelen tekrar eden soruları azaltır. En güçlü satış cümlelerinden biri budur:

> Çalışanın İK'ya sorması gereken rutin işleri self-servise taşıyoruz.

### 3.3 KVKK, yetki ve audit disiplini

İK verisi yüksek hassasiyet taşır. TCKN, IBAN, maaş, sağlık raporu, engellilik bilgisi, izin, performans, disiplin ve belge verisi herkesin görebileceği veri değildir.

IK Platform bu alanda şunlarla ayrışmalıdır:

- Rol ve scope bazlı erişim.
- Hassas alan maskeleme.
- Kritik işlem audit log'u.
- Export/download izleme.
- Tenant izolasyonu.
- Veri saklama ve imha kararlarına hazırlık.

Bu özellikler sadece güvenlik başlığı değildir; satışta güven ve kurumsallık göstergesidir.

### 3.4 Türkiye operasyon gerçekliği

Ürün Türkiye'deki şirketlerin gerçek iş akışlarına göre düşünülmelidir:

- Özlük dosyası ve belge takibi.
- İzin türleri ve bakiye takibi.
- PDKS, vardiya, puantaj ve bordroya veri hazırlığı.
- Çok şube, departman, pozisyon ve yönetici ilişkileri.
- KVKK ve denetim ihtiyacı.
- Muhasebe/bordro yazılımı ile birlikte yaşama.

Bu, global ürünlere karşı yerel derinlik avantajı sağlar. Aynı zamanda yerli ürünlere karşı modern veri modeli ve kullanıcı deneyimiyle ayrışma alanı oluşturur.

### 3.5 Modüler ama tek platform

Modülerlik, her modülün ayrı ürün gibi kopuk çalışması anlamına gelmemelidir. IK Platform modüler paketlenebilir ama veri ve deneyim açısından tek platform olmalıdır.

Örnek:

- EMP çalışanı tanımlar.
- LEAVE bu çalışanın izin hakkını kullanır.
- SS bu çalışanın talebini açar.
- ORG yöneticisini belirler.
- REP bu verileri rapora taşır.
- V1'de TIME puantajı, PAY bordro hazırlığını besler.

Bu zincir koparsa ürün yine parçalı sistemlere dönüşür.

### 3.6 Fazlı derinleşme

IK Platform'un önemli ayrışması, her şeyi ilk günden yapmaya çalışmadan uzun vadeli platform planını korumasıdır.

| Faz | Değer önerisi |
|---|---|
| MVP | Çekirdek İK operasyonunu dijital, güvenli ve self-servis hale getirir |
| V1 | PDKS, puantaj, bordro export, ATS ve performansla günlük operasyonu genişletir |
| V2 | Bordro motoru, analytics, LMS ve AI ile stratejik platforma dönüşür |
| Enterprise | SSO, SCIM, SIEM, dedicated tenant, SLA ve gelişmiş audit ile kurumsal gereksinimleri karşılar |

## 4. Paydaş bazında değer önerisi

### 4.1 İK Müdürü

**Ana cümle:**

> Ekibinizin manuel takip ettiği çalışan, belge, izin ve onay süreçlerini tek denetlenebilir platforma taşıyoruz.

**Değerler:**

- İzin ve belge takibi tek yerde olur.
- Çalışan verisi tutarlı hale gelir.
- Denetim ve belge eksikliği riski azalır.
- Çalışan soruları self-servise taşınır.
- Yönetim raporları daha hızlı çıkar.

**Demo odağı:** Çalışan kartı, belge yükleme, izin talebi, yönetici onayı, temel dashboard.

### 4.2 İK Uzmanı

**Ana cümle:**

> Aynı veriyi farklı Excel'lere tekrar tekrar işlemek yerine, çalışan yaşam döngüsünü tek kayıttan yönetirsiniz.

**Değerler:**

- Tek çalışan kartı.
- Zorunlu alan ve belge kontrolü.
- İzin ve talep takibi.
- Eksik belge ve yaklaşan belge süresi uyarıları.
- Daha az e-posta/WhatsApp takibi.

**Risk:** Ürün İK uzmanına “daha fazla veri girme yükü” gibi hissettirilmemelidir. Onboarding, import ve otomasyon dili güçlü olmalıdır.

### 4.3 Çalışan

**Ana cümle:**

> İzin, belge, duyuru ve temel profil işlemleriniz için İK'ya sormadan kendi ekranınızdan ilerlersiniz.

**Değerler:**

- İzin bakiyesi görünür.
- Talep ve onay durumu takip edilir.
- Belgeler erişilebilir olur.
- Duyurular tek yerde toplanır.
- Şeffaf ve hızlı süreç hissi oluşur.

**Demo odağı:** Self-servis izin talebi, belge görüntüleme, duyuru ve profil ekranı.

### 4.4 Yönetici

**Ana cümle:**

> Ekibinizin izin ve taleplerini dağınık mesajlardan değil, tek onay kuyruğundan yönetirsiniz.

**Değerler:**

- Onay bekleyen izinler görünür.
- Ekip takvimi takip edilir.
- Çakışma ve devamsızlık daha kolay fark edilir.
- Karar gerekçesi kayıt altına alınır.
- Ekip verisine yetkisi kadar erişir.

### 4.5 CFO / Genel Müdür

**Ana cümle:**

> İK operasyonunu kişiye bağlı manuel süreçlerden çıkarıp ölçülebilir, raporlanabilir ve denetlenebilir hale getiriyoruz.

**Değerler:**

- Headcount ve devamsızlık görünürlüğü.
- Operasyonel hata ve zaman kaybı azalması.
- Denetim hazırlığı.
- Büyümede süreçlerin dağılmaması.
- V1/V2'de puantaj, bordro hazırlığı ve maliyet görünürlüğü.

### 4.6 IT / Güvenlik

**Ana cümle:**

> İK verisini rol, scope, tenant izolasyonu, audit ve maskeleme kurallarıyla koruyan, entegrasyona hazır bir platform tasarlıyoruz.

**Değerler:**

- Tenant izolasyonu.
- Rol ve yetki matrisi.
- Hassas alan maskeleme.
- Audit log.
- API/webhook yol haritası.
- Enterprise fazında SSO/SCIM/SIEM.

## 5. Rakiplere karşı pozisyonlama

### 5.1 Global suite'lere karşı

Global suite'ler çok güçlüdür ama Türkiye mid-market için çoğu zaman ağırdır.

**Mesaj:**

> Global suite ağırlığına girmeden, Türkiye'deki gerçek İK operasyonunuzu hızlı ve güvenli şekilde platforma taşıyoruz.

**Vurgu:**

- Daha hızlı kurulum.
- Yerel operasyon diline uygunluk.
- Daha düşük karmaşıklık.
- MVP'de dar ama çalışan ürün.
- V1/V2 ile genişleme.

### 5.2 Global mid-market ürünlere karşı

Global mid-market ürünler modern deneyim sunar ama Türkiye süreçlerine doğrudan oturmayabilir.

**Mesaj:**

> Modern HR deneyimini Türkiye'nin izin, özlük, PDKS, bordro hazırlığı ve KVKK gerçekleriyle birleştiriyoruz.

**Vurgu:**

- Yerel süreç ve terimler.
- KVKK/audit odağı.
- PDKS ve bordro hazırlığı yol haritası.
- TRY ve yerel satış/destek olasılığı.

### 5.3 Yerli KOBİ İK ürünlerine karşı

Yerli KOBİ ürünleri kolay başlangıçta güçlü olabilir.

**Mesaj:**

> Basit başlangıcın ötesinde, büyüyen şirketin güvenlik, veri modeli, yetki, entegrasyon ve platform ihtiyacına göre tasarlanıyoruz.

**Vurgu:**

- 100+ çalışan segmenti.
- Yetki ve hassas alan derinliği.
- Modüler platform yolu.
- PDKS/bordro/self-servis zinciri.

### 5.4 Bordro/ERP ürünlerine karşı

Bordro/ERP ürünleri muhasebe ve mevzuat tarafında güçlüdür.

**Mesaj:**

> Bordro sisteminizi ilk gün değiştirmek zorunda değilsiniz; önce İK operasyon katmanını düzene sokuyoruz, sonra puantaj ve bordro hazırlığıyla derinleşiyoruz.

**Vurgu:**

- Sök-at değil, birlikte yaşama.
- Export/import yaklaşımı.
- Çalışan deneyimi ve self-servis.
- İK'nın muhasebe modülüne sıkışmaması.

### 5.5 Statükoya karşı

En büyük rakip çoğu zaman “böyle devam edelim”dir.

**Mesaj:**

> Excel bugün ucuz görünüyor; ama çalışan sayısı arttıkça hata, zaman, denetim ve kişiye bağımlılık maliyeti büyür.

**Vurgu:**

- İzin bakiye hataları.
- Belge eksikleri.
- Yönetim raporu gecikmesi.
- Çalışan soruları.
- Denetim hazırlığı.

## 6. Ürün paketleme değer mantığı

Bu aşamada kesin fiyat değil, değer paketleme mantığı tanımlanır.

| Paket fikri | Hedef segment | Değer |
|---|---|---|
| Core | 100-500 çalışan | Personel, özlük, belge, izin, self-servis, temel rapor |
| Professional | 500-2000 çalışan | Core + PDKS, puantaj, bordro export, ATS/performance temel |
| Enterprise | 2000+ çalışan | Professional + SSO, SCIM, SIEM, SLA, dedicated opsiyon |
| AI Edition | Olgun veri ve süreç sahibi müşteri | AI asistan, özetleme, öneri, anomali ve governance |

Bu paketleme kesin ticari karar değildir. Fiyatlandırma ve Paketleme dokümanında ayrıca detaylandırılacaktır.

## 7. Değer kanıtı üretme planı

Farklılaşma iddiaları yalnızca dokümanda kalmamalıdır. Her iddia için kanıt üretilmelidir.

| İddia | Kanıt yöntemi |
|---|---|
| İK iş yükünü azaltır | Pilot öncesi/sonrası tekrar eden İK soruları sayılır |
| İzin sürecini hızlandırır | İzin talebi ve onay tamamlama süresi ölçülür |
| Belge denetim riskini azaltır | Eksik belge raporu ve belge geçerlilik takibi gösterilir |
| Güvenli veri erişimi sağlar | Rol/scope/hassas alan testleri yapılır |
| Yönetim görünürlüğü sağlar | Headcount, izin, devamsızlık dashboard'u sunulur |
| PDKS/bordro köprüsü kurar | V1'de puantaj export/import PoC yapılır |

## 8. Demo anlatısı

İlk satış demosu geniş modül turu olmamalıdır. En güçlü demo zinciri şu olmalıdır:

1. Tenant ve kurum ayarları.
2. Çalışan kartı oluşturma.
3. Departman/pozisyon/yönetici ilişkisi.
4. Belge yükleme ve yetkiyle görüntüleme.
5. Çalışanın izin talebi açması.
6. Yöneticinin onaylaması.
7. İK'nın izin ve çalışan raporunu görmesi.
8. Audit log'da kritik işlemlerin görünmesi.

Bu demo, ürünün MVP değer zincirini gösterir. ATS, performans, AI, bordro motoru gibi alanlar roadmap olarak anlatılır; ilk demoda ana değer zincirini dağıtmaz.

## 9. Pazarlama mesajları

### 9.1 Kısa mesajlar

- “Excel'den gerçek İK platformuna geçiş.”
- “Personel, izin, belge ve self-servis tek yerde.”
- “İK operasyonunuzu kişiye bağlı olmaktan çıkarın.”
- “Çalışan sormadan görsün, yönetici beklemeden onaylasın.”
- “KVKK ve audit bilinciyle tasarlanmış modern İK sistemi.”

### 9.2 Kaçınılacak mesajlar

- “Tüm İK problemlerini çözer.”
- “Bordroda hatasız otomasyon.”
- “AI işe alım kararını verir.”
- “Workday alternatifi” ifadesi erken aşamada fazla iddialı olabilir.
- “Her şirkete uygun” mesajı hedef segmenti bulanıklaştırır.

## 10. Riskler ve sınırlar

| Risk | Açıklama | Önlem |
|---|---|---|
| Farklılaşmanın fazla geniş anlatılması | Her şeyi yapıyoruz algısı yaratır | MVP değer zinciri öne çıkarılır |
| Bordro motoru beklentisi | Müşteri ilk günden native bordro bekleyebilir | MVP'de bordro hazırlığı/export, V2'de motor net anlatılır |
| AI beklentisi | AI vurgusu ürün odağını bozabilir | AI destekleyici ve sonraki faz olarak konumlanır |
| Yerli rakiplerle fiyat savaşı | Ürün sadece fiyatla kıyaslanabilir | Güvenlik, self-servis, veri modeli ve ölçeklenebilirlik anlatılır |
| Global ürünlerle yanlış kıyas | Enterprise suite gibi davranmak beklenebilir | Hedef segment ve fazlı büyüme net tutulur |

## 11. Sonuç

IK Platform'un farklılaşması şudur:

- Yerel süreçleri bilen ama eski nesil olmayan bir ürün.
- Basit izin aracından daha derin, ama enterprise suite kadar ağır olmayan bir platform.
- Önce çekirdek İK değerini canlıya alan, sonra PDKS, bordro, performans, analytics ve AI ile büyüyen bir yapı.
- Güvenlik, KVKK, audit ve yetki konularını sonradan değil baştan ele alan bir sistem.

Bu konum korunursa ürün hem ilk canlıya çıkabilir hem de uzun vadede güçlü bir HRMS platformuna dönüşebilir.

## 12. Bağlı dokümanlar

- [Ürün Vizyonu ve Konumlandırma](01-urun-vizyonu-ve-konumlandirma.md)
- [Pazar ve Rakip Analizi](02-pazar-ve-rakip-analizi.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
