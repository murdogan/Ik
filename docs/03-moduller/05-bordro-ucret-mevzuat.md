# Bordro, Ücret ve Mevzuat Modülü

Bu doküman, IK Platform'un ücret, bordro hazırlığı, bordro export, bordro pusulası ve uzun vadede Türkiye bordro motoru kapsamını tanımlar.

## 1. Amaç ve karar özeti

Bordro yüksek mevzuat riski taşıdığı için MVP'de native hesaplama motoru yapılmaz. İlk fazda doğru çalışan/izin/puantaj verisini dış bordro sistemine aktarmak hedeflenir.

Karar özeti:

> MVP'de bordro motoru yoktur. V1'de bordro hazırlığı, puantaj export ve e-bordro dağıtımı; V2'de native Türkiye bordro motoru, teşvik, kıdem/ihbar, banka ve muhasebe çıktıları hedeflenir.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Bordroya esas veri hazırlığı | MVP'de native bordro hesaplama |
| Ücret/IBAN gibi alanların güvenli yönetimi | Mevzuat danışmanlığı garantisi |
| Puantaj/bordro export | Çok ülkeli payroll |
| E-bordro PDF import ve dağıtım | SGK sistemine otomatik canlı gönderim |
| Bordro dönemi hazırlık checklist'i | Banka entegrasyonlarında tüm bankalar |
| Payroll audit | Teşvik optimizasyonu ilk sürüm |
| V2 mevzuat parametre versiyonlama | Hukuki karar otomasyonu |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `payroll_specialist` | Bordro verisini hazırlar, kontrol eder, export alır | Payroll tenant | Hatalı veri maaş hatası yaratır |
| `finance_user` | Ödeme/maliyet onayını verir | Finance scope | Maaş verisi gereksiz açılmamalı |
| `hr_specialist` | Ücret/yan hak değişikliği talebi başlatır | Kısıtlı | Payroll alanını izinsiz değiştirmemeli |
| `employee` | Kendi bordro pusulasını görür | Own | Başkasının pusulasına erişmemeli |
| `auditor` | Bordro audit ve çıktı izlerini inceler | Read-only | Veri değiştirmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Bordroya esas employee alanlarının doğru modellenmesi.
- Hassas ücret/IBAN alanlarının maskeleme ve audit'i.
- Bordro export hazırlığı için veri standardı.
- Bordro modülünün kapsam dışı olduğunun net ürün/satış dili.

### V1

- Puantaj/bordro export.
- E-bordro PDF import ve çalışan self-servis dağıtımı.
- Bordro hazırlık checklist'i.
- Bordro dönem kilidiyle uyum.
- Payroll exception raporu.

### V2

- Native Türkiye bordro motoru.
- Mevzuat parametre versiyonlama.
- Brüt-net/net-brüt simülasyon.
- Teşvik, kıdem/ihbar hesapları.
- Banka dosyası ve muhasebe fişi.

### Enterprise

- Çok şirketli bordro kapsamı.
- Çift onay ve SoD kontrolleri.
- SIEM/audit export.
- Dedicated payroll processing worker.

## 5. Ana kullanıcı akışları

### 5.1 Bordro veri hazırlığı

1. Payroll dönemi için çalışan kapsamını seçer.
2. Sistem aktif çalışan, IBAN, ücret, izin ve puantaj veri eksiklerini gösterir.
3. Hatalar HR/payroll tarafından düzeltilir.
4. Export dosyası üretilir.
5. Export audit'e düşer.

### 5.2 E-bordro dağıtımı

1. Dış bordro sisteminden PDF pusulalar alınır.
2. Sistem çalışan eşleştirmesi yapar.
3. Hatalı/eşleşmeyen PDF'ler exception listesine düşer.
4. Pusulalar self-serviste yayınlanır.
5. Çalışana bildirim gider.

### 5.3 Native bordro run

V2 akışıdır.

1. Dönem açılır.
2. Mevzuat parametre versiyonu seçilir.
3. Puantaj, ücret ve yan hak verisi toplanır.
4. Hesaplama run'ı async çalışır.
5. Exception listesi çözülür.
6. Payroll ve finance onayı sonrası dönem kilitlenir.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| Payroll Readiness | Eksik IBAN, ücret, puantaj, izin kontrolü | V1 |
| Bordro Export | Filtre, format, dosya hash | V1 |
| E-Bordro Dağıtım | PDF import, eşleşme, yayınlama | V1 |
| Bordro Run | Hesaplama ve exception merkezi | V2 |
| Mevzuat Parametreleri | Versiyon, effective date, onay | V2 |
| Kıdem/İhbar Simülasyonu | Ayrılış hesap taslağı | V2 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `payroll_periods` | Dönem | `legal_entity_id`, `period`, `status`, `locked_at` |
| `payroll_exports` | Export kaydı | `period_id`, `format`, `file_hash`, `generated_by` |
| `payslips` | Bordro pusulası | `employee_id`, `period`, `storage_key`, `published_at` |
| `pay_components` | Gelir/kesinti türleri | `code`, `type`, `taxable`, `recurring` |
| `employee_pay_components` | Çalışana bağlı ücret kalemi | `employee_id`, `amount_encrypted`, `effective_date` |
| `legislation_parameters` | Mevzuat parametreleri | `code`, `value`, `effective_from`, `approved_by` |
| `payroll_exceptions` | Hata/uyarı | `severity`, `code`, `message`, `employee_id` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/payroll/readiness` | Veri hazırlık kontrolü | V1 |
| POST | `/api/v1/payroll/exports` | Bordro export üretme | V1 |
| POST | `/api/v1/payslips/imports` | PDF pusula import | V1 |
| GET | `/api/v1/me/payslips` | Kendi pusulalarım | V1 |
| POST | `/api/v1/payroll/periods` | Dönem açma | V2 |
| POST | `/api/v1/payroll/runs` | Native hesaplama | V2 |
| POST | `/api/v1/payroll/runs/{id}/approve` | Bordro onayı | V2 |
| POST | `/api/v1/payroll/severance/simulate` | Kıdem/ihbar simülasyon | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Maaş, IBAN ve pusula yüksek hassasiyetli alandır.
- Employee sadece kendi pusulasını görür.
- Manager varsayılan olarak maaş/pusula görmez.
- Payroll export ayrı permission ve MFA step-up isteyebilir.
- Banka dosyası ve bordro export audit'e düşmelidir.
- Mevzuat parametresi onaysız canlı hesaplamaya girmemelidir.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `payroll_export.generated` | Kapsam, format, hash |
| `payslip.imported` | Dosya sayısı, hata sayısı |
| `payslip.viewed` | Actor, cihaz, zaman |
| `payroll.run.calculated` | V2 hesaplama özeti |
| `legislation_parameter.changed` | Eski/yeni hash, onay |
| `bank_export.generated` | Dosya hash ve actor |

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Bordro veri eksiği | Payroll/HR | In-app/e-posta |
| Pusula yayınlandı | Çalışan | In-app/push |
| Bordro onay bekliyor | Finance/payroll | In-app |
| Parametre onay bekliyor | Yetkili onaycı | In-app |

Arka plan işler: export generation, PDF matching, payslip publish, payroll run, exception calculation.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | IBAN masking ve field permission |
| Integration | Puantaj export üretimi |
| Integration | PDF import → çalışan eşleşme → yayınlama |
| Security | Başka çalışanın pusulasına erişim engeli |
| Regression | V2 golden payroll dataset |
| Performance | Büyük export async tamamlanır |

## 13. Kabul kriterleri

- Bordro hazırlık ekranı eksik veri gösterir.
- Export ayrı permission ve audit ile alınır.
- E-bordro import çalışanla doğru eşleşir.
- Çalışan sadece kendi pusulasını görür.
- Maaş/IBAN/pusula alanları maskelenir veya gizlenir.
- V2 hesaplamaları parametre versiyonuyla izlenebilir olur.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Native bordro erken alınırsa ürün kilitlenir | V2'ye bırakılır |
| Risk | Pusula eşleşme hatası veri sızıntısı yaratır | Hash/eşleşme ve manuel kontrol zorunlu |
| Açık soru | İlk export formatı hangi bordro ürününe göre olacak? | Pilot müşteriyle belirlenecek |

## 15. İlgili dokümanlar

- [Zaman, Vardiya, PDKS ve Puantaj Modülü](04-zaman-vardiya-pdks-puantaj.md)
- [Personel, Özlük ve Doküman Yönetimi Modülü](02-personel-ozluk-dokuman.md)
- [Fiyatlandırma ve Paketleme](../01-strateji-pazar/04-fiyatlandirma-ve-paketleme.md)
