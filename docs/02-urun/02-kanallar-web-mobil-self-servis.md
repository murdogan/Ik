# Kanallar, Web, Mobil ve Self-Servis Deneyimi

Bu doküman, IK Platform'un hangi kullanıcı yüzeylerinden oluşacağını ve web, mobil, çalışan portalı, yönetici portalı, admin paneli gibi kanalların hangi işleri çözmesi gerektiğini tanımlar. Amaç; ürün deneyimini sadece “web panel” olarak değil, farklı kullanıcıların gerçek kullanım bağlamlarına uygun bir kanal mimarisi olarak tasarlamaktır.

## 1. Amaç

İK sistemlerinde başarısızlığın sık nedenlerinden biri, tüm kullanıcıların aynı yönetim paneline sıkıştırılmasıdır. İK uzmanı yoğun tablo ve filtre isterken, çalışan üç dokunuşta izin talebi açmak ister. Yönetici bağlamlı onay ekranı isterken, IT güvenlik ve entegrasyon ayarları ister.

Bu dokümanın amacı:

- Kanal mimarisini netleştirmek.
- MVP'de hangi yüzeylerin zorunlu olduğunu belirlemek.
- Mobil ve mavi yaka kullanımını baştan tasarıma dahil etmek.
- Self-servis deneyiminin hangi işlemleri kapsayacağını tanımlamak.
- UI/UX dokümanlarına temel olacak ürün yüzeyi kararlarını sabitlemektir.

## 2. Kanal mimarisi

| Kanal | Hedef kullanıcı | Ana işler | MVP durumu |
|---|---|---|---|
| Admin / İK Web Paneli | `tenant_admin`, `hr_director`, `hr_specialist` | Kurum ayarları, çalışan, belge, izin, rapor, kullanıcı/rol | Zorunlu |
| Yönetici Portalı | `manager` | Onay kuyruğu, ekip takvimi, ekip bilgileri | Zorunlu |
| Çalışan Self-Servis Portalı | `employee` | Profil, izin, belge, duyuru, talep durumu | Zorunlu |
| Mobil/PWA Deneyimi | `employee`, `manager` | Hızlı izin, onay, bildirim, belge/bordro görüntüleme | MVP'de temel, V1'de güçlenir |
| Finans/Rapor Dashboard'u | `finance_user`, `hr_director` | Headcount, izin, devamsızlık, export | MVP'de temel |
| IT / Entegrasyon Paneli | `it_admin` | Kullanıcı, güvenlik, API, webhook, SSO | MVP'de sınırlı, V1/Enterprise'da genişler |
| Audit Paneli | `auditor`, yetkili yönetici | Kritik işlem ve erişim kayıtları | MVP'de temel |
| Aday Portalı | V1 `candidate` | Başvuru, rıza, mülakat, teklif | V1 |
| Kariyer Sitesi | Adaylar | İlanlar ve başvuru | V1 |

## 3. MVP kanal kararları

MVP'de ürünün çok fazla yüzeye bölünmesi geliştirme ve test yükünü artırır. Bu nedenle MVP'de kanal hedefi şudur:

1. **İK Web Paneli:** Ana operasyon merkezi.
2. **Çalışan Self-Servis:** Responsive web/PWA olarak çalışır; mobilde kullanılabilir olmalıdır.
3. **Yönetici Portalı:** Web/PWA içinde ayrı rol deneyimi; mobil onay akışı önceliklidir.
4. **Temel Audit ve Rapor Görünümü:** Web panel içinde başlar.

Native mobil uygulama MVP için zorunlu değildir; ancak tasarım kararları mobil öncelikli alınmalıdır. Üretim/perakende gibi mavi yaka yoğun segmentlerde PWA'nın yeterli olup olmadığı pilotta ölçülür.

## 4. Bilgi mimarisi

### 4.1 Admin / İK web paneli

| Bölüm | İçerik | Kritik kontrol |
|---|---|---|
| Dashboard | Headcount, açık izin talepleri, eksik belgeler, uyarılar | Rol/scope filtreleri |
| Çalışanlar | Liste, arama, filtre, çalışan kartı | Hassas alan maskeleme |
| Özlük/Belgeler | Belge türleri, yükleme, geçerlilik, eksik belge raporu | Dosya erişim yetkisi |
| İzinler | İzin türleri, bakiye, talepler, onay durumu | Yönetici ilişkisi ve bakiye kuralları |
| Organizasyon | Departman, pozisyon, yönetici ilişkisi | Effective-dated hazırlık |
| Raporlar | Çalışan listesi, izin raporu, belge eksikleri, export | Export audit |
| Kullanıcı/Rol | Kullanıcılar, roller, temel yetkiler | RBAC değişiklik audit'i |
| Audit | Kritik işlem kayıtları | Read-only ve filtreli erişim |

### 4.2 Çalışan self-servis portalı

| Bölüm | İçerik | MVP mi? |
|---|---|---|
| Ana sayfa | Kişisel özet, bekleyen talep, duyuru | Evet |
| Profilim | Kişisel ve iş bilgileri, sınırlı düzenleme/talep | Evet |
| İzinlerim | Bakiye, talep oluşturma, geçmiş talepler | Evet |
| Belgelerim | Görüntülenebilir belgeler, belge talebi | Evet |
| Duyurular | Kurum duyuruları | Evet/sınırlı |
| Taleplerim | Talep durumu ve geçmişi | MVP sınırlı, V1 geniş |
| Bordrom | E-bordro görüntüleme | V1 |
| Vardiyam | Vardiya takvimi | V1 |

### 4.3 Yönetici portalı

| Bölüm | İçerik | MVP mi? |
|---|---|---|
| Onay Kuyruğu | İzin ve temel talepler | Evet |
| Ekip Takvimi | Ekip izinleri ve devamsızlık görünümü | Evet/sade |
| Ekip Listesi | Ekip çalışanları ve temel bilgiler | Evet |
| Delegasyon | Onay yetkisi devri | V1 |
| Performans | Hedef/geri bildirim | V1 |
| Vardiya/Puantaj | Ekip zaman verisi | V1 |

### 4.4 IT / Güvenlik paneli

| Bölüm | İçerik | Faz |
|---|---|---|
| Kullanıcı yönetimi | Aktif/pasif kullanıcılar, davetler | MVP |
| Rol ve yetki | Temel roller ve permission listesi | MVP |
| Güvenlik ayarları | Parola/MFA temel politikaları | MVP/V1 |
| API anahtarları | API credential ve webhook | V1 |
| SSO | OIDC/SAML | V1/Enterprise |
| Audit export | SIEM veya dış log aktarımı | Enterprise |

## 5. Mobil ve PWA stratejisi

### 5.1 MVP kararı

MVP'de ana karar: ürün responsive web/PWA ile mobilde kullanılabilir olmalıdır. Native mobil uygulama ancak kullanıcı testleri ve müşteri ihtiyacı bunu zorunlu kılarsa V1'e alınır.

Bu kararın gerekçeleri:

- MVP kapsamını şişirmemek.
- Aynı iş akışlarını önce web/PWA üzerinde doğrulamak.
- Çalışan ve yönetici self-servisini hızlı test etmek.
- Native mobil bakım yükünü ürün-pazar uyumu öncesi almamak.

### 5.2 Mobilde kusursuz olması gereken MVP akışları

| Akış | Kullanıcı | Hedef süre |
|---|---|---|
| Giriş / aktivasyon | `employee` | İlk kurulum hariç 30 sn altı |
| İzin talebi | `employee` | 1-2 dk |
| İzin onayı | `manager` | 30 sn altı |
| İzin durumu görme | `employee` | 15 sn altı |
| Belge görüntüleme/talep | `employee` | 1 dk altı |
| Duyuru okuma | `employee` | 15 sn altı |

### 5.3 Mavi yaka deneyimi

Mavi yaka çalışan için şu ilkeler uygulanmalıdır:

- Kurumsal e-posta zorunlu olmamalı veya alternatif aktivasyon planlanmalı.
- Telefon numarası, personel no, kurum kodu veya SMS OTP akışı değerlendirilmeli.
- Dil sade olmalı; teknik İK terimleri azaltılmalı.
- Büyük dokunma alanları kullanılmalı.
- Ana işlemler 3-4 adımdan uzun olmamalı.
- Zayıf internet koşulları düşünülmeli.
- Şifre unutma senaryosu kolay olmalı.
- Hassas belge/bordro ekranlarında ek güvenlik düşünülmeli.

## 6. Self-servis kapsamı

Self-servis, “çalışan kendi bilgisine baksın”dan daha geniştir. Ama MVP'de kontrollü başlamalıdır.

### 6.1 MVP self-servis kapsamı

| İşlem | Kullanıcı | Açıklama |
|---|---|---|
| Profil görüntüleme | `employee` | Kendi temel bilgilerini görür |
| Bilgi güncelleme talebi | `employee` | Belirli alanlar onaya düşer |
| İzin bakiyesi görme | `employee` | İzin hakkı ve geçmişi görünür |
| İzin talebi açma | `employee` | Yönetici onayına düşer |
| Talep durumunu izleme | `employee` | Onay/red/beklemede durumu görünür |
| Belge görüntüleme | `employee` | Yetkili olduğu belgeleri görür |
| Belge talebi | `employee` | Çalışma belgesi vb. talep oluşturur |
| Duyuru okuma | `employee` | Kurum duyurularını takip eder |

### 6.2 V1 self-servis kapsamı

- Bordro pusulası görüntüleme.
- Vardiya takvimi görüntüleme.
- Gelişmiş talep formları.
- Delegasyon ve vekalet akışları.
- Mobil push bildirimleri.
- Performans hedef/geri bildirim ekranları.
- Eğitim/kurs atamaları için temel görüntüleme.

### 6.3 V2 self-servis kapsamı

- AI destekli politika soru-cevap.
- Kişisel gelişim/kariyer önerileri.
- Gelişmiş people analytics açıklamaları.
- Doğal dil talep açma.
- Kişisel veri talepleri ve KVKK self-servis merkezi.

## 7. Bildirim stratejisi

Bildirimler kullanıcıyı boğmamalı; sadece aksiyon veya önemli bilgi için kullanılmalıdır.

| Olay | Alıcı | Kanal | Faz |
|---|---|---|---|
| İzin talebi oluşturuldu | `manager` | In-app, e-posta, mobil push | MVP/V1 |
| İzin onaylandı/reddedildi | `employee` | In-app, mobil push | MVP/V1 |
| Belge talebi sonuçlandı | `employee` | In-app, e-posta | MVP |
| Eksik belge uyarısı | `hr_specialist` | Dashboard, in-app | MVP |
| Rol/yetki değişti | `tenant_admin` | In-app, audit | MVP |
| Bordro pusulası hazır | `employee` | In-app, push | V1 |
| Vardiya değişti | `employee` | Push, in-app | V1 |
| PDKS import hatası | `hr_specialist`, `payroll_specialist` | In-app, e-posta | V1 |
| KVKK talep SLA yaklaşıyor | Yetkili kullanıcı | In-app, e-posta | V1/V2 |

## 8. Erişilebilirlik ve kullanılabilirlik ilkeleri

| İlke | Açıklama |
|---|---|
| Sade dil | Çalışan ekranlarında mevzuat dili azaltılır |
| Görsel hiyerarşi | En önemli aksiyon birinci sırada gösterilir |
| Büyük dokunma alanı | Mobilde butonlar küçük olmamalı |
| Klavye erişimi | Web panel klavye ile kullanılabilir olmalı |
| Kontrast | Kritik durumlar renk dışında metin/ikonla da anlatılmalı |
| Hata mesajı | Kullanıcıya ne yapacağını söylemeli |
| Boş durum | “Henüz veri yok” yerine sonraki eylemi göstermeli |
| Yükleme durumu | Uzun işlemlerde durum ve ilerleme gösterilmeli |

## 9. Hassas veri deneyimi

Hassas veri gösterimi kullanıcı deneyiminin parçasıdır.

- TCKN, IBAN, maaş, sağlık ve özel belge bilgileri varsayılan maskeli gelmelidir.
- Görüntüleme yetkisi olan kullanıcı “göster” aksiyonu ile açabilir.
- Kritik alan görüntüleme audit log'a düşmelidir.
- Export işlemleri ayrıca yetki ve audit gerektirmelidir.
- Çalışan sadece kendi hassas verisine erişebilir; başkasının verisine erişemez.
- Yönetici ekip bilgilerini görür ama maaş veya TCKN gibi alanları varsayılan görmemelidir.

## 10. Kanal bazlı MVP kabul kriterleri

| Kanal | Kabul kriteri |
|---|---|
| İK Web Paneli | HR uzmanı çalışan oluşturabilir, belge yükleyebilir, izinleri görebilir |
| Çalışan Portalı | Çalışan kendi profilini, izin bakiyesini ve taleplerini görebilir |
| Yönetici Portalı | Yönetici kendi ekibinden gelen izin talebini bağlamıyla onaylayabilir |
| Mobil/PWA | Çalışan ve yönetici kritik akışları telefondan tamamlayabilir |
| Rapor | Yetkili kullanıcı temel çalışan/izin/belge raporu görebilir |
| Audit | Kritik işlemler kullanıcı, zaman, tenant ve olay bilgisiyle kaydedilir |
| Yetki | Own/team/tenant scope ayrımı kullanıcı yüzeylerinde doğru çalışır |

## 11. Kanal riskleri

| Risk | Etki | Önlem |
|---|---|---|
| Mobil deneyim zayıf kalır | Mavi yaka ve yönetici benimsemesi düşer | PWA akışları baştan mobil test edilir |
| Self-servis fazla karmaşık olur | Çalışan İK'ya sormaya devam eder | İlk ekranlar sade ve görev odaklı tasarlanır |
| İK paneli fazla basit kalır | Operasyon kullanıcıları Excel'e döner | Tablo, filtre, export ve toplu işlem ihtiyaçları korunur |
| Bildirimler fazla gelir | Kullanıcı bildirimleri kapatır | Bildirim tercihleri ve olay önceliği tanımlanır |
| Hassas veri yanlış görünür | Güvenlik/KVKK riski oluşur | Masking, permission testleri ve audit zorunlu tutulur |
| Native mobil erken başlar | MVP kapsamı şişer | Önce responsive/PWA ile değer doğrulanır |

## 12. Sonraki dokümanlara etkisi

Bu doküman şu alanlara doğrudan girdi verir:

- UI/UX tasarım sistemi.
- Sayfa akışları ve wireframe notları.
- AUTH ve RBAC modül tasarımı.
- EMP, LEAVE, SS ve REP modül dokümanları.
- Mobil/PWA teknoloji kararı.
- Bildirim ve event modeli.
- Test senaryoları ve E2E kabul akışları.

## 13. Bağlı dokümanlar

- [Doküman İndeksi](../README.md)
- [Personalar, JTBD ve Kullanıcı Yolculukları](01-personalar-jtbd-ve-kullanici-yolculuklari.md)
- [MVP, V1 ve V2 Kapsam Kararları](03-mvp-v1-v2-kapsam-kararlari.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
- [Modül Formatı ve Ortak Kararlar](../03-moduller/00-modul-format-ve-ortak-kararlar.md)
