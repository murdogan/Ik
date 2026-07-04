# Modül Formatı ve Ortak Kararlar

Bu doküman, IK Platform içindeki tüm modül dokümanlarının aynı kalite ve yapı standardıyla yazılmasını sağlar. Her modül farklı iş alanını ele alsa da ürün, veri, API, yetki, güvenlik, test ve fazlama açısından aynı çerçeveye oturmalıdır.

## 1. Amaç

Modül dokümanları sadece “bu özellik olsun” listesi değildir. Bir modül dokümanı; ürün yöneticisinin kapsamı yönetebilmesi, tasarımcının ekranları çıkarabilmesi, geliştiricinin veri/API etkisini görebilmesi, QA ekibinin test senaryosu yazabilmesi ve canlıya alma ekibinin operasyon risklerini anlayabilmesi için hazırlanır.

Bu nedenle her modül dokümanı şu sorulara cevap vermelidir:

- Bu modül hangi işi çözer?
- Hangi kullanıcı rolleri bu modülü kullanır?
- MVP'de ne var, ne yok?
- Veritabanında hangi varlıklar gerekir?
- API yüzeyleri nasıl şekillenir?
- Hangi yetkiler ve scope'lar gerekir?
- Hangi kişisel/hassas veriler işlenir?
- Hangi audit kayıtları zorunludur?
- Hangi testler olmadan canlıya çıkılamaz?
- Hangi entegrasyonlar modülü etkiler?

## 2. Modül listesi

Kanonik modül listesi aşağıdaki gibidir:

| Kod | Modül | Faz önerisi | Açıklama |
|---|---|---|---|
| CORE | Tenant, kurum ve platform çekirdeği | MVP | Kurum, plan, lisans, feature flag, temel ayarlar |
| AUTH | Kimlik doğrulama | MVP | Login, parola, oturum, MFA, SSO hazırlığı |
| RBAC | Yetki ve rol yönetimi | MVP | Rol, permission, scope, hassas alan maskeleme |
| EMP | Personel ve özlük | MVP | Çalışan master data, yaşam döngüsü, özlük kartı |
| DOC | Belge yönetimi | MVP | Dosya yükleme, şablon, belge geçerliliği |
| LEAVE | İzin ve devamsızlık | MVP | İzin türleri, bakiye, talep, onay, takvim |
| SS | Self-servis ve talep | MVP | Çalışan portalı, yönetici onayı, talep merkezi temeli |
| REP | Temel raporlar | MVP/V1 | Headcount, izin, export, dashboard |
| TIME | Vardiya, mesai, PDKS, puantaj | V1 | Çalışma takvimi, PDKS import/API, puantaj kilidi |
| PAY | Bordro, ücret ve mevzuat | V1/V2 | Bordro export MVP sonrası; native motor V2 |
| ATS | İşe alım ve aday portalı | V1 | İlan, aday, mülakat, teklif |
| PERF | Performans ve OKR | V1 | Hedef, değerlendirme, 360 geri bildirim |
| LMS | Eğitim, yetkinlik ve kariyer | V2 | Eğitim planı, sertifika, succession |
| ORG | Organizasyon ve kadro | MVP/V1 | Departman/pozisyon MVP; kadro planlama V1/V2 |
| AI | AI özellikleri ve governance | V1/V2 | Düşük riskli AI V1; karar destek V2/Enterprise |
| INT | Entegrasyon altyapısı | MVP/V1 | E-posta/SMS MVP; SGK/banka/PDKS V1+ |
| OPS | Operasyon ve canlıya alma | MVP | Ortam, release, backup, observability, incident |

## 3. Her modül dosyasında zorunlu başlıklar

Her modül dokümanı aşağıdaki başlık yapısını kullanmalıdır.

```text
# Modül Adı

## 1. Amaç ve karar özeti
## 2. Kapsam içi / kapsam dışı
## 3. Kullanıcı rolleri ve sorumluluklar
## 4. MVP / V1 / V2 / Enterprise ayrımı
## 5. Ana kullanıcı akışları
## 6. Ekranlar ve deneyim notları
## 7. Veri modeli etkisi
## 8. API ve entegrasyon ihtiyaçları
## 9. Yetki, scope ve güvenlik kuralları
## 10. KVKK, audit ve saklama gereksinimleri
## 11. Bildirimler ve arka plan işler
## 12. Test senaryoları
## 13. Kabul kriterleri
## 14. Riskler, açık sorular ve kararlar
## 15. İlgili dokümanlar
```

Başlıklar modüle göre zenginleşebilir ama bu ana yapı silinmemelidir.

## 4. Amaç ve karar özeti standardı

Her modülün ilk bölümünde kısa ama net bir karar özeti olmalıdır:

- Modül neden var?
- Hangi iş problemini çözüyor?
- MVP'deki rolü nedir?
- Bu modül hangi modüllere bağımlı?
- Bu modül hangi modüllere veri sağlar?

Örnek:

```text
Personel ve özlük modülü, tüm İK operasyonunun ana veri kaynağıdır. İzin, bordro, performans, eğitim, raporlama ve self-servis süreçleri employee kaydına dayanır. Bu nedenle MVP'de bu modül dar ama sağlam kurulmalıdır.
```

## 5. Kapsam içi / kapsam dışı standardı

Her modülde iki sütunlu kapsam tablosu bulunmalıdır.

Örnek:

| Kapsam içi | Kapsam dışı |
|---|---|
| Çalışan kartı oluşturma | Native bordro hesaplama |
| Zorunlu özlük alanları | Gelişmiş succession planning |
| Belge yükleme | E-imza entegrasyonu zorunluluğu |
| Temel import/export | Tüm dış sistemlerle hazır entegrasyon |

Kapsam dışı maddeler “yok” anlamına gelmez; MVP dışı anlamına gelebilir. Bu yüzden yanında faz notu yazılmalıdır.

## 6. Faz ayrımı standardı

Her modülde özellikler şu seviyelerde ayrılmalıdır:

### MVP

İlk pilot müşteride çalışması zorunlu işlevler. MVP maddesi canlı kullanımda değer üretmeli ve test edilebilir olmalıdır.

### V1

MVP sonrası ticari ürünü genişleten, satış ve müşteri başarısını güçlendiren işlevler.

### V2

Daha derin otomasyon, gelişmiş raporlama, mevzuat motoru, ileri seviye entegrasyon veya karmaşık kurumsal akışlar.

### Enterprise

Dedicated deployment, gelişmiş güvenlik, büyük kurum onay hiyerarşileri, yüksek SLA, SIEM/SCIM/SSO gibi kurumsal ihtiyaçlar.

## 7. Roller ve sorumluluk standardı

Her modülde rol etkisi yazılmalıdır.

Örnek tablo:

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `hr_specialist` | Çalışan kaydı oluşturur ve günceller | Tenant içi operasyon | Hassas alanlara gereksiz erişim |
| `manager` | Ekibinin kayıtlarını sınırlı görür | Team scope | Maaş/TCKN görmemeli |
| `employee` | Kendi profilini ve belgelerini görür | Own scope | Başkasının verisine erişmemeli |
| `auditor` | Audit ve uyum kayıtlarını okur | Read-only | Veri değiştirmemeli |

Rol listesi [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md) ile uyumlu olmalıdır.

## 8. Ana akış standardı

Her modülde en az 2-5 ana akış yazılmalıdır. Akışlar sadece metin değil, adım adım olmalıdır.

Örnek format:

```text
Akış: Çalışan işe giriş süreci
1. hr_specialist yeni çalışan kaydı başlatır.
2. Zorunlu kişisel ve kurumsal alanlar doldurulur.
3. Sistem TCKN, e-posta ve zorunlu alan doğrulaması yapar.
4. Belge checklist'i oluşur.
5. Onboarding görevleri ilgili rollere atanır.
6. Çalışan aktif statüye geçer.
7. Audit log employee.created ve onboarding.started olaylarını yazar.
```

## 9. Ekran ve deneyim standardı

Her modül ürün yüzeylerini belirtmelidir:

- Admin web ekranları
- HR operasyon ekranları
- Yönetici ekranları
- Çalışan self-servis ekranları
- Mobil/PWA etkisi
- Export/import arayüzleri
- Bildirim ve e-posta yüzeyleri

Ekran listesi wireframe olmak zorunda değildir; ancak hangi ekranların çıkacağı net olmalıdır.

## 10. Veri modeli standardı

Her modül veri etkisini yazmalıdır. Bu aşamada tam SQL şeması gerekmeyebilir ama entity ve ilişkiler belirtilmelidir.

Örnek:

| Entity | Açıklama | Kritik alanlar | Hassasiyet |
|---|---|---|---|
| `employee` | Çalışan ana kaydı | tenant_id, employee_no, status | Personal |
| `employee_identity` | Kimlik bilgileri | national_id, birth_date | Sensitive Personal |
| `employment_assignment` | Departman/pozisyon ataması | position_id, manager_id, effective_dates | Personal |
| `employee_document` | Özlük belgesi | document_type, file_id, expiry_date | Sensitive Personal |

Veri modeli her zaman tenant izolasyonu ve audit ihtiyacıyla birlikte düşünülmelidir.

## 11. API standardı

Her modül API ihtiyaçlarını kaynak bazında yazmalıdır.

Örnek:

| Kaynak | Metod | Amaç | Yetki |
|---|---|---|---|
| `/employees` | GET | Çalışan listesi | `employee:read` |
| `/employees` | POST | Çalışan oluşturma | `employee:create` |
| `/employees/{id}` | PATCH | Çalışan güncelleme | `employee:update` |
| `/employees/{id}/documents` | POST | Belge yükleme | `document:create` |

Bu tablolar nihai OpenAPI değildir; ancak API tasarım dokümanına temel oluşturur.

## 12. Yetki ve güvenlik standardı

Her modül şu soruları yanıtlamalıdır:

- Hangi işlemler hangi role açık?
- Own/team/tenant/platform scope nasıl işler?
- Hangi alanlar maskelenir?
- Hangi işlemler çift onay veya gerekçe ister?
- Hangi işlemler audit log zorunludur?
- Export/download işlemleri nasıl sınırlandırılır?

Özellikle TCKN, IBAN, maaş, sağlık, disiplin ve bordro verileri için ayrı yetki yazılmalıdır.

## 13. KVKK ve audit standardı

Her modülde şu başlıklar değerlendirilmelidir:

- İşlenen kişisel veri kategorileri
- Açık rıza veya aydınlatma ihtiyacı
- Saklama ve imha süresi
- Veri sahibi talebi etkisi
- Export ve paylaşım riski
- Audit event listesi

Örnek audit event'ler:

- `employee.created`
- `employee.sensitive_field_viewed`
- `document.downloaded`
- `leave.approved`
- `payroll.exported`
- `role.permission_changed`

## 14. Bildirim standardı

Her modülde bildirim ihtiyacı ayrı yazılmalıdır.

| Olay | Alıcı | Kanal | MVP mi? |
|---|---|---|---|
| İzin talebi oluşturuldu | manager | E-posta + in-app | Evet |
| Belge süresi yaklaşıyor | hr_specialist | In-app | Evet |
| Rol değişti | tenant_admin | Audit + in-app | Evet |
| Bordro export hazır | payroll_specialist | In-app | V1 |

Bildirimler ürün deneyimi kadar audit ve operasyon için de önemlidir.

## 15. Test senaryosu standardı

Her modülde en az şu test tipleri düşünülmelidir:

- Unit test: iş kuralı veya hesaplama
- Integration test: API + DB + tenant izolasyonu
- Permission test: rol/scope/hassas alan
- E2E test: kullanıcı akışı
- Security test: yetkisiz erişim, IDOR, export riski
- Regression test: kritik mevzuat veya bakiye senaryosu

Örnek:

```gherkin
Scenario: Manager sadece kendi ekibinin izin talebini onaylar
  Given iki farklı departmanda iki çalışan vardır
  And manager sadece birinci çalışanın yöneticisidir
  When manager ikinci çalışanın izin talebini onaylamaya çalışır
  Then sistem 403 döner
  And audit log unauthorized_access_attempt kaydı üretir
```

## 16. Kabul kriteri standardı

Kabul kriterleri test edilebilir olmalıdır.

Kötü örnek:

```text
Sistem kolay kullanılabilir olmalı.
```

İyi örnek:

```text
Bir hr_specialist, zorunlu alanları doldurmadan çalışan kaydını aktif statüye alamaz. Eksik alanlar alan bazlı hata mesajıyla gösterilir ve audit log employee.validation_failed olayı yazılır.
```

## 17. Modüller arası bağımlılık standardı

Her modül bağımlılıklarını yazmalıdır.

Örnek:

| Bu modül | Bağımlı olduğu modül | Nedeni |
|---|---|---|
| LEAVE | EMP | İzin hakkı çalışan kıdemine bağlıdır |
| LEAVE | SS | İzin talebi self-servis üzerinden açılır |
| PAY | TIME | Puantaj bordroya veri sağlar |
| REP | Tüm modüller | Raporlar operasyon verilerinden beslenir |
| AI | Güvenlik/uyum | Hassas veri maskeleme ve governance gerekir |

## 18. MVP kapsamını koruma kuralları

Modül dokümanları yazılırken MVP'nin şişmemesi için şu kurallar uygulanır:

1. Eğer özellik ilk pilotta zorunlu değilse V1/V2'ye alınır.
2. Eğer özellik yasal risk taşıyorsa basit export/manual süreç MVP'ye alınabilir, tam otomasyon ertelenir.
3. Eğer özellik entegrasyon bağımlıysa mock/import/export ile MVP çözümü düşünülür.
4. Eğer özellik AI veya gelişmiş analytics istiyorsa önce manuel/rapor tabanlı alternatif yazılır.
5. Eğer özellik enterprise müşteriye özel ise MVP'ye alınmaz.

## 19. Modül dokümanı hazır kabul kriterleri

Bir modül dokümanı tamamlandı sayılmadan önce:

- Kapsam içi/dışı tablosu var.
- MVP/V1/V2 ayrımı var.
- En az üç rol için sorumluluk yazılmış.
- En az iki ana kullanıcı akışı var.
- Veri entity tablosu var.
- API kaynak listesi var.
- Yetki/scope tablosu var.
- KVKK/audit etkisi var.
- En az beş test senaryosu var.
- Açık sorular ve riskler var.
- İç linkler kırık değil.

## 20. İlk yazılacak modül önerisi

Temel dokümanlar tamamlandıktan sonra ilk detay modül sırası şu olmalıdır:

1. `01-core-tenant-auth-rbac.md`
2. `02-personel-ozluk-dokuman.md`
3. `03-izin-devamsizlik-onay.md`
4. `10-self-servis-talep-duyuru.md`

Bu sıra MVP değer zincirini kurar: kurum açılır, kullanıcı girer, çalışan kaydı oluşur, izin talebi akar, çalışan ve yönetici self-servis kullanır.

## 21. Bağlı dokümanlar

- [Doküman İndeksi](../README.md)
- [Konvansiyonlar ve Standartlar](../00-genel/01-konvansiyonlar-ve-standartlar.md)
- [Terimler, Roller ve Karar Kaydı](../00-genel/02-terimler-roller-ve-karar-kaydi.md)
