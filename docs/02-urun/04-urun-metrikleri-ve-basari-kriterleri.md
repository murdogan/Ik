# Ürün Metrikleri ve Başarı Kriterleri

Bu doküman, IK Platform'un ürün, müşteri, operasyon ve ticari başarı metriklerini tanımlar. Amaç; dokümantasyon ve geliştirme sürecinin yalnızca özellik listesiyle değil, ölçülebilir sonuçlarla ilerlemesini sağlamaktır.

## 1. Amaç

Bir HRMS ürününde “özellik tamamlandı” demek tek başına başarı değildir. Çalışan izin talebi açmıyorsa, yöneticiler onayları e-postadan vermeye devam ediyorsa, İK uzmanı hâlâ Excel'e dönüyorsa ve yönetim raporları güvenilmiyorsa ürün gerçek değer üretmiyor demektir.

Bu dokümanın amacı:

- MVP'nin başarı kriterlerini ölçülebilir hale getirmek.
- Ürün kullanımını, self-servis benimsemesini ve operasyonel etkiyi izlemek.
- V1/V2 genişlemeleri için hangi sinyallerin aranacağını belirlemek.
- Kod aşamasında event, analytics ve raporlama gereksinimlerine temel oluşturmaktır.

## 2. Kuzey yıldızı metriği

Önerilen kuzey yıldızı metriği:

> Haftalık aktif self-servis kullanıcısı oranı: Son 7 günde çalışan veya yönetici olarak anlamlı bir self-servis işlemi yapan aktif kullanıcıların toplam aktif çalışan sayısına oranı.

Anlamlı self-servis işlemleri:

- İzin talebi açmak.
- İzin talebini onaylamak/reddetmek.
- Belge görüntülemek veya belge talebi açmak.
- Profil bilgisi görüntülemek veya güncelleme talebi açmak.
- Duyuru okumak.
- Talep durumunu kontrol etmek.
- V1'de bordro/vardiya görüntülemek.

Bu metrik önemlidir çünkü ürün sadece İK uzmanı tarafından kullanılıyorsa platform değeri sınırlı kalır. Çalışan ve yönetici kullanımı arttıkça İK yükü azalır, müşteri bağlılığı güçlenir ve PEPM modeli daha savunulabilir olur.

## 3. MVP başarı metrikleri

| Alan | Metrik | MVP hedefi | Neden önemli? |
|---|---|---|---|
| Kurulum | İlk tenant kurulum süresi | 1 iş günü içinde temel kurulum | Onboarding karmaşıklığını ölçer |
| Veri | İlk çalışan import başarı oranı | Test importunda kritik hata olmaması | Employee modelinin sağlamlığını gösterir |
| Personel | Zorunlu alan tamamlanma oranı | Pilot veride %95+ | Veri kalitesi olmadan rapor ve izin bozulur |
| Belge | Eksik belge raporu üretilebilmesi | Evet/hayır | Özlük değerinin görünür çıktısıdır |
| İzin | İzin talebi tamamlama süresi | Çalışan için 1-2 dk | Self-servis kullanımını belirler |
| Onay | Yönetici onay tamamlama süresi | 30 sn - 1 dk | Yönetici benimsemesini belirler |
| Self-servis | Haftalık aktif self-servis oranı | Pilot sonrası ölçülecek, hedef trend artış | Ürünün çalışan katmanına indiğini gösterir |
| Audit | Kritik event kapsaması | Kritik MVP olaylarında %100 | Güvenlik/KVKK için şarttır |
| Yetki | Tenant izolasyon hatası | 0 tolerans | SaaS güvenliği için kritik |
| Rapor | Temel rapor üretimi | Çalışan/izin/belge raporları çalışır | Yönetim görünürlüğü sağlar |

## 4. Ürün kullanım metrikleri

### 4.1 Aktivasyon metrikleri

| Metrik | Tanım | Kullanım |
|---|---|---|
| Time-to-first-value | Tenant oluşturma ile ilk anlamlı çıktı arası süre | Onboarding kalitesini ölçer |
| İlk çalışan import süresi | Import şablonu yükleme ve hatasız kabul arası süre | Veri geçişini ölçer |
| İlk izin talebi süresi | Tenant açılışından ilk izin talebine kadar geçen süre | Self-servis aktivasyonunu gösterir |
| İlk yönetici onayı | İlk talep ile ilk onay arası süre | Yönetici katmanının aktive olduğunu gösterir |
| İlk rapor görüntüleme | İlk dashboard/rapor görüntüleme zamanı | Yönetim değerinin göründüğünü gösterir |

### 4.2 Benimseme metrikleri

| Metrik | Tanım | Segment |
|---|---|---|
| Weekly active employees | Haftalık anlamlı işlem yapan çalışan sayısı | Tüm çalışanlar |
| Weekly active managers | Haftalık onay/görüntüleme yapan yöneticiler | Manager |
| HR power user activity | İK panelinde günlük işlem yapan kullanıcılar | HR |
| Mobil/PWA kullanım oranı | Mobil cihazdan gelen anlamlı işlemler | Çalışan/yönetici |
| Self-servis işlem oranı | İK uzmanı yerine çalışan/yönetici tarafından başlatılan işlemler | MVP/V1 |

### 4.3 İşlem metrikleri

| Metrik | Tanım | İyi sinyal |
|---|---|---|
| İzin talebi başarı oranı | Başlatılan talebin gönderime ulaşma oranı | Yüksek oran, düşük terk |
| Onay SLA | Taleplerin belirlenen sürede onaylanma oranı | Yönetici benimsemesi |
| Belge talebi tamamlama süresi | Talep açılışından sonuçlanmaya kadar geçen süre | İK operasyon verimi |
| Eksik belge kapatma oranı | Eksik belgelerin belirli sürede tamamlanması | Özlük kalitesi |
| Export kullanımı | Yetkili rapor/export sayısı | Yönetim/operasyon değeri |

## 5. İş değeri metrikleri

| Alan | Metrik | Ölçüm yöntemi |
|---|---|---|
| İK yükü | Tekrar eden İK sorusu sayısı | Pilot öncesi/sonrası sayım |
| İzin operasyonu | İzin talebi/onay çevrim süresi | Sistem event zamanları |
| Belge operasyonu | Eksik belge sayısı ve kapanma süresi | DOC raporları |
| Raporlama | Manuel rapor hazırlama süresi | Kullanıcı görüşmesi + sistem raporu |
| Denetim hazırlığı | Denetim için belge/audit çıkarma süresi | Test senaryosu |
| Çalışan deneyimi | Self-servis memnuniyeti | Mini anket / CSAT |
| Yönetici deneyimi | Onay memnuniyeti ve onay gecikmesi | Event + anket |

## 6. Güvenlik ve uyum metrikleri

| Metrik | Hedef | Not |
|---|---|---|
| Tenant izolasyon ihlali | 0 | Kritik blocker |
| Yetkisiz erişim denemesi | İzlenir | Güvenlik ve UX hatası ayrıştırılır |
| Hassas alan görüntüleme audit oranı | %100 | Maaş/TCKN/IBAN gibi alanlar için |
| Export audit oranı | %100 | CSV/XLSX/PDF export dahil |
| Rol değişikliği audit oranı | %100 | Yetki yönetimi için şart |
| Silme/anonimleştirme talebi SLA | V1/V2'de tanımlanır | KVKK süreci olgunlaşınca |
| Kritik güvenlik bulgusu | 0 açık kritik | Canlıya alma ön koşulu |

## 7. Teknik ve operasyonel metrikler

MVP dokümantasyon aşamasında kod yoktur; ancak ileride ürünün izlenebilmesi için şu metrikler tasarımda düşünülmelidir.

| Alan | Metrik | Hedef / Not |
|---|---|---|
| API sağlığı | Health check ve hata oranı | MVP'de temel monitoring |
| Sayfa performansı | Ana ekran yüklenme süresi | Kullanılabilirlik için kritik |
| Arama performansı | Çalışan listesi arama süresi | İK paneli için kritik |
| Background job | Import/export tamamlanma oranı | Veri işlemleri için kritik |
| Bildirim | Bildirim gönderim başarı oranı | E-posta/push/SMS için |
| Backup | Yedek alma ve geri yükleme testi | Canlıya alma ön koşulu |
| Log kalitesi | Correlation id / tenant id kapsaması | Debug ve audit için kritik |

## 8. Ticari metrikler

| Metrik | Anlamı | Neden önemli? |
|---|---|---|
| MRR/ARR | Aylık/yıllık tekrar eden gelir | SaaS ana metriği |
| Net Revenue Retention | Mevcut müşteriden büyüme/azalma | Ürün değerinin sürdüğünü gösterir |
| Logo churn | Müşteri kaybı | Ürün-pazar uyumu sinyali |
| Expansion rate | Paket yükseltme/eklenti satışı | Platform genişlemesini gösterir |
| CAC payback | Müşteri edinme maliyetinin geri dönüşü | Satış modelinin sağlığı |
| Gross margin | Abonelik kârlılığı | Altyapı/destek sürdürülebilirliği |
| Implementation margin | Kurulum hizmetinin kârlılığı | Operasyon yükünü ölçer |

## 9. Paket/faz bazlı başarı kriterleri

### 9.1 Core / MVP

Core başarı kriterleri:

- Tenant kurulumu tamamlanır.
- Çalışan importu yapılır.
- Personel kartı ve belge yükleme çalışır.
- İzin talebi ve yönetici onayı uçtan uca tamamlanır.
- Çalışan self-servisi kullanılabilir.
- Temel raporlar alınır.
- Kritik audit event'leri yazılır.

### 9.2 Professional / V1

Professional başarı kriterleri:

- PDKS veya puantaj verisi sisteme alınır.
- Bordro hazırlığı/export akışı çalışır.
- ATS veya performans temel akışlarından en az biri canlı müşteride kullanılır.
- API/webhook entegrasyonu en az bir müşteri senaryosunda doğrulanır.
- Yönetici/çalışan mobil/PWA kullanımı belirgin artar.

### 9.3 Enterprise

Enterprise başarı kriterleri:

- SSO/SCIM gibi kimlik entegrasyonları çalışır.
- SIEM/audit export yapılabilir.
- Gelişmiş güvenlik değerlendirmesi geçilir.
- SLA ve destek süreçleri ölçülür.
- Dedicated veya özel dağıtım ihtiyacı operasyonel olarak karşılanabilir.

### 9.4 AI Edition

AI başarı kriterleri:

- AI önerileri insan onayı olmadan kritik karar üretmez.
- AI çıktıları loglanır ve izlenebilir olur.
- Yanlış/zararlı öneri oranı izlenir.
- Kullanıcı memnuniyeti ve zaman kazancı ölçülür.
- AI maliyeti paket gelirini aşındırmaz.

## 10. Event ve ölçüm gereksinimleri

Kod aşamasına geçildiğinde şu event'ler planlanmalıdır:

| Event | Ne zaman? | Kullanım |
|---|---|---|
| `tenant.created` | Tenant açıldığında | Aktivasyon |
| `user.login` | Kullanıcı giriş yaptığında | Benimseme/güvenlik |
| `employee.created` | Çalışan oluşturulduğunda | Aktivasyon/veri |
| `employee.import.completed` | Import tamamlandığında | Onboarding |
| `document.uploaded` | Belge yüklendiğinde | Özlük değeri |
| `document.viewed` | Belge görüntülendiğinde | Self-servis/audit |
| `leave.requested` | İzin talebi açıldığında | Self-servis |
| `leave.approved` | İzin onaylandığında | Onay SLA |
| `report.viewed` | Rapor görüntülendiğinde | Yönetim değeri |
| `export.generated` | Export alındığında | Audit/güvenlik |
| `permission.changed` | Yetki değiştiğinde | Güvenlik |

Her event'te en az şu alanlar düşünülmelidir:

- `tenant_id`
- `actor_user_id`
- `actor_role`
- `resource_type`
- `resource_id`
- `timestamp`
- `source_channel`
- `result`
- `metadata`

## 11. Dashboard gereksinimleri

MVP sonrası ürün içinde en az iki dashboard düşünülmelidir:

### 11.1 İK operasyon dashboard'u

- Aktif çalışan sayısı.
- Eksik belge sayısı.
- Bekleyen izin talepleri.
- Yaklaşan belge geçerlilik tarihleri.
- Departman bazlı çalışan dağılımı.
- Son audit olayları.

### 11.2 Ürün kullanım dashboard'u

- Haftalık aktif self-servis kullanıcıları.
- İzin talebi sayısı.
- Onay SLA durumu.
- Mobil/PWA kullanım oranı.
- En çok kullanılan self-servis işlemleri.
- Hata/terk oranları.

Bu dashboard önce internal/admin görünüm olarak başlayabilir; daha sonra müşteri yöneticilerine ürün içi sağlık raporu olarak sunulabilir.

## 12. Canlıya alma başarı kriterleri

Bir pilot canlıya alınmadan önce şu kriterler sağlanmalıdır:

- Kritik MVP akışları manuel veya otomatik testten geçmiştir.
- En az bir tenant ve gerçekçi çalışan veri setiyle import denenmiştir.
- Tenant izolasyonu test edilmiştir.
- Hassas alan maskeleme test edilmiştir.
- İzin talebi/onay akışı uçtan uca tamamlanmıştır.
- Audit log kritik event'leri üretmiştir.
- Temel raporlar alınmıştır.
- Backup ve geri dönüş prosedürü yazılmıştır.
- Kullanıcı eğitim/destek notları hazırlanmıştır.

## 13. Riskler

| Risk | Etki | Önlem |
|---|---|---|
| Çok fazla metrik izlenir | Odak dağılır | MVP'de 5-10 kritik metrik seçilir |
| Vanity metric'e takılmak | Gerçek değer görünmez | İşlem ve sonuç metrikleri önceliklendirilir |
| Self-servis oranı düşük kalır | Ürün sadece İK paneli olur | Mobil/PWA ve çalışan deneyimi erken test edilir |
| Event tasarımı geç yapılır | Sonradan ölçüm zorlaşır | Kod başlamadan event kataloğu hazırlanır |
| Müşteri ROI ölçülmez | Satış ve yenileme zayıflar | Pilot öncesi/sonrası karşılaştırma yapılır |

## 14. Bağlı dokümanlar

- [MVP, V1 ve V2 Kapsam Kararları](03-mvp-v1-v2-kapsam-kararlari.md)
- [Personalar, JTBD ve Kullanıcı Yolculukları](01-personalar-jtbd-ve-kullanici-yolculuklari.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](02-kanallar-web-mobil-self-servis.md)
- [Fiyatlandırma ve Paketleme](../01-strateji-pazar/04-fiyatlandirma-ve-paketleme.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
