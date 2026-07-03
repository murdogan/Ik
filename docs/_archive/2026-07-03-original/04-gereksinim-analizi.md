# 04 — Gereksinim Analizi

> **Hazırlanma Tarihi:** 7 Nisan 2026  
> **Kapsam:** Fonksiyonel gereksinimler, fonksiyonel olmayan gereksinimler, MoSCoW önceliklendirme, kabul kriterleri  
> **Referans:** 03-hedef-kitle-ve-kullanici-personalar.md (User Stories temel alınmıştır)

---

## 1. Fonksiyonel Gereksinimler

### 1.1 Kimlik Doğrulama & Yetkilendirme

| ID | Gereksinim | Öncelik | Detay |
|----|-----------|---------|-------|
| FR-AUTH-01 | E-posta + şifre ile giriş | Must | Güçlü şifre politikası (min 8 karakter, büyük/küçük harf, rakam, özel karakter) |
| FR-AUTH-02 | Çok faktörlü kimlik doğrulama (MFA) | Must | SMS veya authenticator app desteği |
| FR-AUTH-03 | Rol bazlı erişim kontrolü (RBAC) | Must | 5 ana rol: Süper Admin, İK Yöneticisi, Departman Yöneticisi, Çalışan, C-Level |
| FR-AUTH-04 | Oturum yönetimi | Must | Otomatik oturum sonlandırma (30 dk inaktivite), eşzamanlı oturum limiti |
| FR-AUTH-05 | Şifre sıfırlama | Must | E-posta ile token bazlı sıfırlama, 24 saat geçerlilik |
| FR-AUTH-06 | SSO (Single Sign-On) | Could | SAML 2.0 / OAuth 2.0 / OpenID Connect desteği |
| FR-AUTH-07 | LDAP / Active Directory entegrasyonu | Could | Kurumsal müşteriler için |
| FR-AUTH-08 | IP kısıtlama | Should | Belirli IP aralıklarından erişim izni |
| FR-AUTH-09 | Giriş denemeleri sınırlandırma | Must | 5 başarısız deneme → 15 dk hesap kilitleme |
| FR-AUTH-10 | Denetim günlüğü (Audit Log) | Must | Tüm giriş/çıkış, yetki değişiklikleri loglanmalı |

---

### 1.2 Personel Yönetimi

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-PER-01 | Çalışan kaydı oluşturma | Must | TC kimlik, ad-soyad, doğum tarihi, iletişim, pozisyon, departman, işe giriş tarihi zorunlu |
| FR-PER-02 | Çalışan profili düzenleme | Must | İK ve çalışan (kısıtlı alanlar) tarafından güncellenebilir |
| FR-PER-03 | Toplu veri içe aktarma (Excel/CSV) | Must | Şablon dosyası sağlanmalı, hata raporlaması yapılmalı |
| FR-PER-04 | Belge yönetimi | Must | PDF, Word, resim formatları; maks 10 MB/dosya; çalışan başına sınırsız |
| FR-PER-05 | İş sözleşmesi yönetimi | Must | Belirsiz süreli, belirli süreli, kısmi zamanlı, stajyer sözleşme türleri |
| FR-PER-06 | İşe giriş süreci (onboarding) | Must | Checklist tabanlı, görev atama, belge toplama, otomatik bildirimler |
| FR-PER-07 | İşten çıkış süreci (offboarding) | Must | Kıdem/ihbar tazminatı ön hesaplama, çıkış mülakatı, zimmet iade takibi |
| FR-PER-08 | Çalışan arama & filtreleme | Must | Departman, pozisyon, lokasyon, durum, tarih aralığı filtreleri |
| FR-PER-09 | Organizasyon şeması görüntüleme | Should | Hiyerarşik ağaç yapısı, departman bazlı, sürükle-bırak düzenleme |
| FR-PER-10 | Çalışan fotoğrafı | Should | Max 2 MB, JPEG/PNG; kırpma aracı |
| FR-PER-11 | Terfi/nakil/görev değişikliği kaydı | Must | Geçmiş kayıtları saklama, tarihçe görüntüleme |
| FR-PER-12 | Zimmet yönetimi | Should | Çalışana verilen varlıklar (laptop, telefon, araç): atama, iade, takip |
| FR-PER-13 | Acil durum kişisi bilgileri | Must | Çalışan tarafından self-servis güncellenebilir |
| FR-PER-14 | Engelli çalışan takibi | Should | Yasal kontenjan hesaplaması, raporlama |
| FR-PER-15 | Çoklu şirket / şube desteği | Must | Tek hesapta birden fazla şirket/şube yönetimi |

---

### 1.3 İzin & Devamsızlık Yönetimi

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-IZN-01 | İzin türleri tanımlama | Must | Yıllık ücretli, mazeret, hastalık (raporlu/raporsuz), evlilik, doğum, ölüm, ücretsiz, idari |
| FR-IZN-02 | Kıdeme göre otomatik kota hesaplama | Must | 4857 sayılı İş Kanunu'na uygun: 1-5 yıl → 14 gün, 5-15 yıl → 20 gün, 15+ → 26 gün |
| FR-IZN-03 | İzin talebi oluşturma | Must | Başlangıç/bitiş tarihi, izin türü, açıklama, belge ekleme (rapor vb.) |
| FR-IZN-04 | Çok seviyeli onay akışı | Must | Çalışan → Yönetici → (opsiyonel) İK onayı |
| FR-IZN-05 | İzin bakiyesi görüntüleme | Must | Anlık bakiye: toplam hak, kullanılan, kalan, bekleyen talepler |
| FR-IZN-06 | İzin takvimi (ekip/departman) | Must | Çakışma uyarısı, resmi tatil gösterimi |
| FR-IZN-07 | İzin devri (yıl sonu) | Should | Devreden izin politikası: otomatik devir, üst limit, sıfırlama |
| FR-IZN-08 | Yarım gün / saatlik izin | Must | AM/PM seçimi veya saat aralığı belirtme |
| FR-IZN-09 | Resmi tatil takvimi | Must | Türkiye resmi tatilleri otomatik, özel şirket tatilleri eklenebilir |
| FR-IZN-10 | Devamsızlık takibi | Must | Mazeretsiz devamsızlık kaydı, İK uyarı mekanizması |
| FR-IZN-11 | Mobil izin talebi/onayı | Must | Push notification ile yöneticiye bildirim, tek tuş onay/red |
| FR-IZN-12 | Toplu izin tanımlama | Should | Belirli departman/şubeye toplu idari izin verme |
| FR-IZN-13 | İzin iptal/değişiklik | Must | Talebi geri çekme veya tarih değişikliği, onay akışı tekrar başlar |

---

### 1.4 Bordro & Maaş Yönetimi

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-BRD-01 | Brüt → Net maaş hesaplama | Must | SGK işçi payı (%14), işsizlik sigortası (%1), gelir vergisi (kümülatif matrah), damga vergisi (%0,759) |
| FR-BRD-02 | Kümülatif vergi matrahı takibi | Must | Yıl içi vergi dilimi geçişleri otomatik hesaplanmalı |
| FR-BRD-03 | SGK prim bildirgesi (APHB) verileri | Must | Gün sayısı, kazanç türleri, eksik gün nedenleri dışa aktarım |
| FR-BRD-04 | Fazla mesai hesaplama | Must | Normal FM (%50), hafta tatili FM (%100), gece FM ağırlığı |
| FR-BRD-05 | Ek ödeme kalemleri | Must | Prim, ikramiye, yol yardımı, yemek yardımı, aile yardımı, çocuk yardımı |
| FR-BRD-06 | Kesinti yönetimi | Must | İcra kesintisi, sendika aidatı, avans mahsubu, özel sağlık/BES kesintisi |
| FR-BRD-07 | AGİ hesaplama | Must | Medeni durum ve çocuk sayısına göre otomatik hesaplama |
| FR-BRD-08 | Bordro PDF oluşturma | Must | Çalışan bazında aylık maaş bordrosu (yasal format) |
| FR-BRD-09 | Banka dosyası oluşturma | Should | EFT/havale için banka formatında (txt/xml) dışa aktarım |
| FR-BRD-10 | Maaş simülasyonu | Should | "Ya X TL zam verirsem?" senaryosu — brüt/net/maliyet karşılaştırma |
| FR-BRD-11 | Mevzuat güncelleme mekanizması | Must | Asgari ücret, SGK tavan/taban, vergi dilimleri güncelleme paneli |
| FR-BRD-12 | Kıdem/ihbar tazminatı hesaplama | Must | Çalışma süresi, son brüt maaş, tavan kontrolü ile otomatik hesaplama |
| FR-BRD-13 | Geçmişe dönük bordro görüntüleme | Must | Çalışan ve İK tarafından geçmiş bordrolara erişim |
| FR-BRD-14 | Bordro kilitleme | Must | Onaylanmış bordro değiştirilemez, fark bordrosu oluşturulabilir |
| FR-BRD-15 | Engelli/teşvik indirimi hesaplama | Should | 5746 AR-GE teşviki, engelli istihdam teşviki, SGK prim teşvikleri |
| FR-BRD-16 | Çoklu ödeme dönemi | Should | Aylık, 15 günlük, haftalık ödeme periyotları |

---

### 1.5 Performans Yönetimi

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-PRF-01 | Değerlendirme dönemi tanımlama | Must | Yıllık, 6 aylık, çeyreklik dönemler; başlangıç/bitiş/hatırlatma tarihleri |
| FR-PRF-02 | Hedef belirleme (OKR) | Must | Objective + Key Results yapısı; ağırlıklandırma; ilerleme yüzdesi |
| FR-PRF-03 | KPI tanımlama ve takibi | Must | Sayısal hedefler, otomatik ilerleme hesaplama |
| FR-PRF-04 | Yönetici değerlendirmesi | Must | Puan veya ölçek bazlı (1-5, 1-10), yorum alanı |
| FR-PRF-05 | Öz değerlendirme (Self-Assessment) | Must | Çalışanın kendi performansını değerlendirmesi |
| FR-PRF-06 | 360° feedback | Should | Kişi seçimi, anonim/açık seçeneği, çoklu değerlendirici |
| FR-PRF-07 | Yetkinlik matrisi | Should | Pozisyon bazlı yetkinlik tanımlama, mevcut seviye vs beklenen seviye |
| FR-PRF-08 | Performans görüşme notları | Should | 1:1 toplantı notları, aksiyon maddeleri |
| FR-PRF-09 | Performans puanı raporlaması | Must | Departman bazlı dağılım, bell curve, trend analizi |
| FR-PRF-10 | Performans-ücret ilişkilendirme | Could | Performans sonuçlarına göre zam/prim önerisi |
| FR-PRF-11 | Sürekli geri bildirim | Should | Anlık kudos/tebrik, iyileştirme notu; dönem dışı da kullanılabilir |

---

### 1.6 İşe Alım & Aday Takip (ATS)

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-ATS-01 | İş ilanı oluşturma | Must | Pozisyon, departman, gereksinimler, iş tanımı, son başvuru tarihi |
| FR-ATS-02 | Çoklu kanal yayınlama | Should | Kariyer sayfası, LinkedIn, Kariyer.net entegrasyonu (API) |
| FR-ATS-03 | Başvuru toplama | Must | Online form, CV yükleme (PDF/Word), e-posta ile başvuru |
| FR-ATS-04 | Kanban aday takibi | Must | Aşamalar: Başvuru → Ön Eleme → Mülakat → Değerlendirme → Teklif → İşe Alındı / Reddedildi |
| FR-ATS-05 | Aday puanlama / derecelendirme | Must | Her aşamada puan, not, skor kartı |
| FR-ATS-06 | Mülakat planlama | Should | Takvim entegrasyonu, e-posta davetiyesi, video mülakat linki |
| FR-ATS-07 | Teklif mektubu oluşturma | Should | Şablon bazlı, PDF çıktı, e-imza |
| FR-ATS-08 | Aday havuzu | Should | Reddedilen/bekleyen adayları gelecek pozisyonlar için saklama |
| FR-ATS-09 | İşe alım metrikleri | Should | Time-to-hire, cost-per-hire, kaynak analizi, dönüşüm oranları |
| FR-ATS-10 | Aday iletişim geçmişi | Must | E-posta, telefon, mülakat notları — kronolojik kayıt |
| FR-ATS-11 | Kariyer sayfası (embed) | Could | Şirket web sitesine gömülebilir ilan sayfası |
| FR-ATS-12 | KVKK aday rızası | Must | Başvuru sırasında açık rıza onayı, veri saklama süresi |

---

### 1.7 Eğitim & Gelişim

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-EGT-01 | Eğitim tanımlama | Must | Eğitim adı, tür (online/sınıf/hibrit), süre, eğitimci, kapasite |
| FR-EGT-02 | Eğitim planı oluşturma | Must | Yıllık/dönemsel plan, departman/pozisyon bazlı atama |
| FR-EGT-03 | Eğitim katılım takibi | Must | Katılım durumu, tamamlama yüzdesi |
| FR-EGT-04 | Sertifika yönetimi | Must | Sertifika yükleme, geçerlilik tarihi, süre dolmadan uyarı |
| FR-EGT-05 | Eğitim değerlendirme anketi | Should | Eğitim sonrası memnuniyet anketi |
| FR-EGT-06 | Eğitim bütçe takibi | Should | Planlanan vs harcanan bütçe, departman bazlı |
| FR-EGT-07 | Zorunlu eğitim takibi | Should | İSG, KVKK gibi zorunlu eğitimlerin tamamlanma durumu |
| FR-EGT-08 | Eğitim kataloğu | Could | Çalışanın göz atıp talep edebileceği eğitim listesi |
| FR-EGT-09 | Kariyer yol haritası | Could | Pozisyon bazlı gelişim yolu, gerekli eğitim/deneyim gösterimi |

---

### 1.8 Vardiya & Mesai Yönetimi

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-VRD-01 | Vardiya şablonu tanımlama | Must | Başlangıç/bitiş saati, mola süreleri; sabit/esnek/dönüşümlü tipler |
| FR-VRD-02 | Vardiya planlama (takvim) | Must | Haftalık/aylık sürükle-bırak planlama, çoklu atama |
| FR-VRD-03 | Vardiya çakışma kontrolü | Must | Aynı kişiye çakışan vardiya atanmasını engelleme |
| FR-VRD-04 | Fazla mesai otomatik hesaplama | Must | Haftalık 45 saat üzeri otomatik FM hesabı |
| FR-VRD-05 | PDKS cihaz entegrasyonu | Should | Suprema, ZKTeco, Anviz gibi cihazlardan veri çekme (API/dosya) |
| FR-VRD-06 | Mobil giriş/çıkış (GPS) | Should | Konum doğrulamalı mobil check-in/check-out |
| FR-VRD-07 | Çalışan vardiya görüntüleme | Must | Mobilde kendi vardiya programını görme, bildirim alma |
| FR-VRD-08 | Vardiya değişiklik talebi | Should | Çalışan talep eder, yönetici onaylar |
| FR-VRD-09 | Puantaj raporu | Must | Aylık puantaj: çalışılan gün, izinli gün, FM saati, eksik gün |
| FR-VRD-10 | Gece vardiyası hesaplama | Should | 20:00-06:00 arası gece zammı hesabı |

---

### 1.9 Organizasyon Şeması

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-ORG-01 | Departman yapısı tanımlama | Must | Hiyerarşik departman/alt departman ağacı |
| FR-ORG-02 | Pozisyon tanımlama | Must | Pozisyon adı, departman, üst pozisyon, kadro sayısı |
| FR-ORG-03 | Görsel organizasyon şeması | Should | Ağaç yapısında otomatik oluşan, tıklanabilir, çalışan fotoğraflı |
| FR-ORG-04 | Kadro planlama | Should | Dolu/boş kadro takibi, bütçelenmiş pozisyon yönetimi |
| FR-ORG-05 | Çoklu lokasyon/şube | Must | Her lokasyonun kendi org yapısı, birleşik görünüm |

---

### 1.10 Raporlama & Analitik

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-RPR-01 | Ana dashboard | Must | Headcount, devamsızlık oranı, işe giriş/çıkış, maliyet özeti, izin durumu |
| FR-RPR-02 | Hazır rapor şablonları | Must | Min 15 hazır rapor (departman dağılımı, yaş, cinsiyet, kıdem, maliyet vb.) |
| FR-RPR-03 | Özel rapor oluşturma | Should | Sürükle-bırak alan seçimi, filtre, gruplama |
| FR-RPR-04 | Grafik / veri görselleştirme | Must | Çubuk, pasta, çizgi, donut grafikleri |
| FR-RPR-05 | Dışa aktarım | Must | PDF, Excel (xlsx), CSV formatları |
| FR-RPR-06 | Otomatik rapor gönderimi | Could | Haftalık/aylık otomatik e-posta ile rapor |
| FR-RPR-07 | Trend analizi | Should | Geçmiş dönem karşılaştırma, yıl bazlı trendler |
| FR-RPR-08 | Rol bazlı dashboard filtreleme | Must | Her rol kendi verisini görür (yönetici → kendi ekibi) |

---

### 1.11 Self-Servis Portal & Bildirimler

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-SSP-01 | Çalışan dashboard'u | Must | İzin bakiyesi, yaklaşan izinler, duyurular, görevler |
| FR-SSP-02 | Talep yönetimi | Must | İzin, avans, masraf, fazla mesai, belge talebi oluşturma |
| FR-SSP-03 | Duyuru sistemi | Must | Şirket geneli / departman bazlı duyurular, okundu takibi |
| FR-SSP-04 | Şirket rehberi | Should | Çalışan listesi, fotoğraf, telefon, e-posta, departman |
| FR-SSP-05 | Doğum günü & yıl dönümü | Should | Otomatik bildirimler, tebrik kartı |
| FR-SSP-06 | Push notification (mobil) | Must | İzin onayı, talep sonucu, duyuru, hatırlatma |
| FR-SSP-07 | E-posta bildirimi | Must | Tüm kritik olaylarda e-posta, tercih yönetimi (opt-in/opt-out) |
| FR-SSP-08 | Bildirim tercihleri | Should | Kullanıcı bazında hangi bildirimleri almak istediğini seçme |
| FR-SSP-09 | Yönetici panel | Must | Ekip izin durumu, bekleyen onaylar, performans özeti |

---

### 1.12 Entegrasyonlar

| ID | Gereksinim | Öncelik | Kabul Kriteri |
|----|-----------|---------|---------------|
| FR-ENT-01 | SGK e-Bildirge veri aktarımı | Must | APHB formatında dışa aktarım |
| FR-ENT-02 | e-Devlet sorgulamaları | Should | TC kimlik doğrulama, adres bilgisi sorgulama |
| FR-ENT-03 | Banka EFT dosyası | Should | Yaygın banka formatlarında maaş ödeme dosyası |
| FR-ENT-04 | Muhasebe yazılımı entegrasyonu | Should | Logo, Mikro, Netsis, Luca — maaş fişi/muhasebe kaydı |
| FR-ENT-05 | Takvim entegrasyonu | Should | Google Calendar, Outlook Calendar — izin, mülakat |
| FR-ENT-06 | PDKS cihaz entegrasyonu | Should | Suprema, ZKTeco API entegrasyonu |
| FR-ENT-07 | İşbirliği araçları | Could | Slack, Microsoft Teams — bildirim gönderimi |
| FR-ENT-08 | SMS gateway | Should | İzin onayı, mülakat hatırlatma SMS'i |
| FR-ENT-09 | E-posta servisi | Must | SMTP/API bazlı e-posta gönderimi (SendGrid, AWS SES vb.) |
| FR-ENT-10 | Webhook / REST API | Must | 3. parti entegrasyonlar için açık API; API key + OAuth 2.0 |
| FR-ENT-11 | İş ilanı platformları | Could | Kariyer.net, LinkedIn, Indeed API entegrasyonu |

---

## 2. Fonksiyonel Olmayan Gereksinimler (NFR)

### 2.1 Performans

| ID | Gereksinim | Hedef | Ölçüm Yöntemi |
|----|-----------|-------|---------------|
| NFR-PER-01 | Sayfa yükleme süresi | < 2 saniye (ilk yükleme), < 500ms (sonraki navigasyon) | Lighthouse, Web Vitals |
| NFR-PER-02 | API yanıt süresi | < 200ms (basit sorgular), < 1 saniye (karmaşık raporlar) | APM monitoring |
| NFR-PER-03 | Eşzamanlı kullanıcı desteği | Min 1.000 eşzamanlı kullanıcı | Load testing (k6/JMeter) |
| NFR-PER-04 | Bordro hesaplama performansı | 500 çalışan bordrosu < 30 saniye | Unit benchmark |
| NFR-PER-05 | Arama yanıt süresi | < 300ms (çalışan arama, filtreleme) | APM monitoring |
| NFR-PER-06 | Mobil performans | FCP < 1.5s, LCP < 2.5s, CLS < 0.1 | Lighthouse Mobile |

### 2.2 Ölçeklenebilirlik

| ID | Gereksinim | Hedef |
|----|-----------|-------|
| NFR-SCL-01 | Yatay ölçekleme | Stateless servisler, container bazlı (Docker/K8s) |
| NFR-SCL-02 | Multi-tenant mimari | Paylaşımlı altyapı, tenant izolasyonu (veritabanı düzeyinde) |
| NFR-SCL-03 | Veri büyüklüğü | 100.000+ çalışan kaydını performans kaybı olmadan desteklemeli |
| NFR-SCL-04 | Dosya depolama | Nesne depolama (S3 uyumlu), otomatik ölçekleme |

### 2.3 Güvenlik

| ID | Gereksinim | Hedef |
|----|-----------|-------|
| NFR-SEC-01 | Veri şifreleme (at-rest) | AES-256 ile veritabanı ve dosya şifreleme |
| NFR-SEC-02 | Veri şifreleme (in-transit) | TLS 1.3, HTTPS zorunlu |
| NFR-SEC-03 | OWASP Top 10 uyumluluğu | Injection, XSS, CSRF, Broken Auth vb. önlemleri |
| NFR-SEC-04 | SQL injection koruması | Parametrized queries, ORM kullanımı zorunlu |
| NFR-SEC-05 | Güvenlik taramaları | Haftalık otomatik SAST/DAST taraması |
| NFR-SEC-06 | Penetrasyon testi | Yılda 2 kez bağımsız pen-test |
| NFR-SEC-07 | Veri maskeleme | Hassas veriler (TC kimlik, maaş) loglarda maskelenmeli |
| NFR-SEC-08 | Rate limiting | API'lerde IP/kullanıcı bazlı rate limit (429 Too Many Requests) |
| NFR-SEC-09 | CORS politikası | Sadece izin verilen domain'lerden erişim |

### 2.4 Güvenilirlik & Erişilebilirlik

| ID | Gereksinim | Hedef |
|----|-----------|-------|
| NFR-REL-01 | Uptime (SLA) | %99,5 aylık uptime (max ~3,65 saat/ay kesinti) |
| NFR-REL-02 | Yedekleme | Günlük otomatik yedek, 30 gün saklama, farklı bölgede kopya |
| NFR-REL-03 | Felaket kurtarma (DR) | RPO < 1 saat, RTO < 4 saat |
| NFR-REL-04 | Graceful degradation | Bir servis çökerse diğerleri çalışmaya devam etmeli |
| NFR-REL-05 | Health check endpoint | Her servis için `/health` endpoint'i |

### 2.5 Kullanılabilirlik (Usability)

| ID | Gereksinim | Hedef |
|----|-----------|-------|
| NFR-USE-01 | Öğrenme süresi | Yeni kullanıcı 15 dakikada temel işlemleri yapabilmeli |
| NFR-USE-02 | Tutarlı tasarım | Design system ile bileşen tutarlılığı |
| NFR-USE-03 | Erişilebilirlik | WCAG 2.1 AA seviyesi uyumluluk |
| NFR-USE-04 | Çoklu dil desteği | Türkçe (birincil), İngilizce (ikincil); i18n altyapısı |
| NFR-USE-05 | Responsive tasarım | 320px (mobil) → 2560px (4K) arası sorunsuz |
| NFR-USE-06 | Hata mesajları | Kullanıcı dostu, yönlendirici hata mesajları (teknik jargon yok) |
| NFR-USE-07 | Klavye navigasyonu | Tab, Enter, Escape ile tam navigasyon desteği |

### 2.6 Uyumluluk & Yasal

| ID | Gereksinim | Hedef |
|----|-----------|-------|
| NFR-CMP-01 | KVKK uyumu | 6698 sayılı Kişisel Verilerin Korunması Kanunu — tam uyum |
| NFR-CMP-02 | GDPR uyumu | Uluslararası müşteriler için GDPR hazırlığı |
| NFR-CMP-03 | Açık rıza yönetimi | Çalışan/aday verileri için açık rıza toplama ve yönetme |
| NFR-CMP-04 | Veri silme hakkı | "Unutulma hakkı" — talep üzerine kişisel verilerin silinmesi |
| NFR-CMP-05 | Veri taşınabilirliği | Çalışan verilerinin standart formatta dışa aktarımı |
| NFR-CMP-06 | Veri lokalizasyonu | Verilerin Türkiye'de barındırılması seçeneği |
| NFR-CMP-07 | Saklama süreleri | İş hukuku (10 yıl), SGK (10 yıl), vergi (5 yıl) saklama süreleri |
| NFR-CMP-08 | 4857 İş Kanunu uyumu | İzin, fazla mesai, kıdem/ihbar hesaplama kuralları |
| NFR-CMP-09 | 5510 SGK Kanunu uyumu | Prim hesaplama, bildirge, işe giriş/çıkış bildirimleri |

### 2.7 Bakım & İşletim

| ID | Gereksinim | Hedef |
|----|-----------|-------|
| NFR-OPS-01 | Loglama | Merkezi log toplama (ELK/Loki), yapılandırılmış log formatı (JSON) |
| NFR-OPS-02 | Monitoring | Uygulama metrikleri (Prometheus/Grafana veya benzeri) |
| NFR-OPS-03 | Alerting | Kritik olaylarda anlık uyarı (PagerDuty/OpsGenie/e-posta) |
| NFR-OPS-04 | CI/CD | Otomatik build, test, deploy pipeline |
| NFR-OPS-05 | Sıfır kesintili deploy | Blue-green veya rolling deployment stratejisi |
| NFR-OPS-06 | Konfigürasyon yönetimi | Environment variable bazlı, secret management (Vault/KMS) |

---

## 3. MoSCoW Önceliklendirme Özeti

### 3.1 Must Have (MVP — Faz 1)

Sistemi son kullanıcıya açmak için **mutlaka olması gereken** özellikler:

| Alan | Gereksinimler |
|------|--------------|
| **Kimlik Doğrulama** | E-posta/şifre giriş, MFA, RBAC (5 rol), şifre sıfırlama, oturum yönetimi, audit log, rate limiting |
| **Personel** | Çalışan CRUD, toplu import, belge yönetimi, sözleşme, onboarding, offboarding, terfi/nakil, çoklu şube |
| **İzin** | İzin türleri, kıdem bazlı kota, talep/onay akışı, bakiye, takvim, yarım gün, resmi tatil, mobil, iptal |
| **Self-Servis** | Çalışan dashboard, talep yönetimi, duyuru, push/e-posta bildirim, yönetici panel |
| **Raporlama** | Ana dashboard, hazır raporlar, grafikler, dışa aktarım, rol bazlı filtreleme |
| **Entegrasyon** | E-posta servisi, REST API / Webhook |

### 3.2 Should Have (Faz 2)

MVP sonrasında hızla eklenmesi gereken özellikler:

| Alan | Gereksinimler |
|------|--------------|
| **Bordro** | Brüt→Net hesaplama, SGK/vergi, fazla mesai, ek ödeme, kesinti, AGİ, PDF, mevzuat güncelleme, kıdem/ihbar, bordro kilitleme |
| **Performans** | Değerlendirme dönemi, OKR/KPI, yönetici/öz değerlendirme, puan raporlaması |
| **Vardiya** | Vardiya şablonu, planlama, çakışma kontrolü, FM hesaplama, puantaj, mobil |
| **Organizasyon** | Departman yapısı, pozisyon, görsel org şeması, çoklu lokasyon |
| **Entegrasyon** | SGK veri aktarımı, banka dosyası, muhasebe, takvim, PDKS, SMS |
| **Güvenlik** | IP kısıtlama, bildirim tercihleri |

### 3.3 Could Have (Faz 3)

Değer katan ama ertelenebilir özellikler:

| Alan | Gereksinimler |
|------|--------------|
| **İşe Alım (ATS)** | İlan oluşturma, başvuru toplama, kanban takip, iletişim geçmişi, KVKK rızası, çoklu kanal, mülakat planlama, aday havuzu, metrikler |
| **Eğitim** | Eğitim tanımlama, plan, katılım takibi, sertifika, anket, bütçe, zorunlu eğitim |
| **Gelişmiş Raporlama** | Özel rapor oluşturma, trend analizi, otomatik rapor gönderimi |
| **Gelişmiş Bordro** | Maaş simülasyonu, teşvik, çoklu ödeme dönemi |

### 3.4 Won't Have (Bu Sürümde Yok)

Gelecek fazlarda değerlendirilecek:

| Alan | Gereksinimler |
|------|--------------|
| **SSO / LDAP** | Kurumsal SSO, Active Directory entegrasyonu |
| **AI Chatbot** | Türkçe doğal dil İK asistanı |
| **GenAI** | İlan yazma, performans özeti, eğitim önerisi |
| **Blockchain** | Sertifika doğrulama |
| **Kariyer Sayfası** | Embed edilebilir ilan sayfası |
| **Performans-Ücret** | Otomatik zam/prim önerisi |
| **Kariyer Yol Haritası** | Pozisyon bazlı gelişim yolu |
| **Eğitim Kataloğu** | Çalışanın göz atıp talep ettiği eğitim listesi |

---

## 4. Gereksinim İzleme Matrisi (Traceability)

### Persona → Gereksinim Eşleşmesi

| Persona | Kritik Gereksinimler |
|---------|---------------------|
| **Ayşe (İK Müdürü)** | FR-PER-*, FR-IZN-*, FR-BRD-*, FR-PRF-*, FR-RPR-*, FR-ENT-01 |
| **Mehmet (Yönetici)** | FR-IZN-04/05/11, FR-VRD-02/07, FR-PRF-02/04, FR-SSP-09 |
| **Zeynep (Çalışan)** | FR-IZN-01/03/11, FR-BRD-08/13, FR-SSP-01/02/06, FR-PER-02/04/13 |
| **Hakan (C-Level)** | FR-RPR-01/04/05/07, FR-SSP-01 |
| **Emre (KOBİ Sahibi)** | FR-PER-01/03/15, FR-IZN-01/02, FR-BRD-01/08, FR-AUTH-01 |
| **Fatma (İşe Alım)** | FR-ATS-*, FR-PER-06 |

### Modül → Faz Eşleşmesi

```
Faz 1 (MVP):     Personel + İzin + Self-Servis + Raporlama (Temel) + Auth
Faz 2 (Core):    Bordro + Performans + Vardiya + Organizasyon
Faz 3 (Growth):  İşe Alım (ATS) + Eğitim + Gelişmiş Raporlama
Faz 4 (Scale):   AI + SSO + Gelişmiş Entegrasyonlar
```

---

## 5. Kısıtlamalar & Varsayımlar

### 5.1 Kısıtlamalar

| # | Kısıt | Etki |
|---|-------|------|
| K1 | Türkiye'de veri barındırma zorunluluğu (KVKK) | Cloud sağlayıcı Türkiye region olmalı veya yerli DC |
| K2 | Türk iş hukuku sık değişiyor | Bordro motoru modüler ve hızlı güncellenebilir olmalı |
| K3 | Faklı sektörlerin farklı izin/vardiya kuralları var | Konfigürasyon bazlı esneklik gerekli |
| K4 | Mobil internet hızı değişken (saha çalışanları) | Offline capability veya hafif veri modeli düşünülmeli |
| K5 | Küçük ekip ile geliştirme | MVP kapsamı daraltılmalı, modüler mimari şart |

### 5.2 Varsayımlar

| # | Varsayım | Risk |
|---|---------|------|
| V1 | Kullanıcıların çoğunluğu modern tarayıcı kullanıyor (Chrome, Safari, Edge son 2 sürüm) | Düşük |
| V2 | Mobil kullanıcılar iOS 15+ veya Android 10+ kullanıyor | Düşük |
| V3 | İK uzmanlarının temel bilgisayar okuryazarlığı var | Düşük |
| V4 | İlk 6 ayda 100'den fazla müşteriye ulaşılacak | Orta |
| V5 | SGK API'leri dışa aktarım formatı (XML/CSV) kısa vadede değişmeyecek | Orta |
| V6 | Asgari ücret ve vergi dilimleri yılda en fazla 2 kez değişecek | Düşük |

---

## 6. Sayısal Özet

| Kategori | Toplam | Must | Should | Could | Won't |
|----------|--------|------|--------|-------|-------|
| Kimlik Doğrulama & Yetkilendirme | 10 | 6 | 1 | 2 | 1 |
| Personel Yönetimi | 15 | 10 | 5 | 0 | 0 |
| İzin & Devamsızlık | 13 | 9 | 3 | 0 | 1 |
| Bordro & Maaş | 16 | 9 | 5 | 2 | 0 |
| Performans Yönetimi | 11 | 5 | 4 | 1 | 1 |
| İşe Alım (ATS) | 12 | 5 | 4 | 2 | 1 |
| Eğitim & Gelişim | 9 | 4 | 3 | 2 | 0 |
| Vardiya & Mesai | 10 | 5 | 4 | 0 | 1 |
| Organizasyon Şeması | 5 | 3 | 2 | 0 | 0 |
| Raporlama & Analitik | 8 | 4 | 2 | 1 | 1 |
| Self-Servis & Bildirimler | 9 | 5 | 3 | 0 | 1 |
| Entegrasyonlar | 11 | 3 | 5 | 3 | 0 |
| **TOPLAM FR** | **129** | **68** | **41** | **11** | **7** |
| **NFR (Non-Functional)** | **37** | — | — | — | — |
| **GENEL TOPLAM** | **166** | — | — | — | — |

---

> **Sonraki Adım:** [05-teknoloji-secimi.md](05-teknoloji-secimi.md) — Frontend, backend, veritabanı, altyapı teknoloji stack'i karşılaştırması ve seçimi  
> **Not:** Faz 1 (Analiz) tamamlandı. Faz 2 (Teknoloji & Mimari Kararlar) başlıyor.
