# Veri Migrasyonu, Import ve Export

Bu doküman, IK Platform'a müşteri verisinin güvenli ve kontrollü şekilde aktarılması, import validasyonu, export yönetimi ve offboarding veri teslimi süreçlerini tanımlar.

## 1. Amaç ve karar özeti

İlk müşteri başarısı büyük ölçüde veri migrasyonuna bağlıdır. Çalışan, izin bakiyesi, belge ve organizasyon verisi hatalı gelirse ürün daha ilk günde güven kaybeder.

Karar özeti:

> MVP'de çalışan import, temel org import, belge metadata/import ve rapor export kontrollü şekilde desteklenmelidir. Her import dry-run, satır bazlı hata ve commit adımı içermelidir.

## 2. Import prensipleri

| İlke | Karar |
|---|---|
| Dry-run önce | Veri commit edilmeden validasyon yapılır |
| Satır bazlı hata | Hata satırı, alanı ve nedeni görünür |
| Idempotency | Aynı dosya yanlışlıkla tekrar import edilirse kontrol edilir |
| Mapping | Kolon eşleştirme kullanıcıya gösterilir |
| Staging | Veri önce staging alanına alınır |
| Audit | Kim, ne zaman, hangi dosyayla import yaptı kaydedilir |
| Rollback | Commit sonrası düzeltme prosedürü olmalıdır |

## 3. MVP import kapsamı

| Veri | Format | Faz |
|---|---|---|
| Çalışan listesi | CSV/XLSX | MVP |
| Departman/pozisyon | CSV/XLSX | MVP |
| Yönetici ilişkisi | CSV/XLSX | MVP |
| İzin bakiyeleri | CSV/XLSX | MVP |
| Belge metadata | CSV/XLSX | MVP |
| Belge dosyaları | ZIP/S3 upload | V1 |
| PDKS mapping | CSV/XLSX | V1 |
| Aday verisi | CSV/XLSX | V1 |
| Bordro geçmişi | CSV/XLSX | V2 |

## 4. Import akışı

1. Kullanıcı şablon indirir.
2. Dosyayı yükler.
3. Sistem dosya hash'i alır.
4. Kolon mapping önerilir.
5. Dry-run validasyon çalışır.
6. Hata raporu gösterilir.
7. Kullanıcı düzeltir veya uyarıları kabul eder.
8. Commit işlemi başlatılır.
9. Sonuç raporu ve audit oluşur.

## 5. Validasyon tipleri

| Tip | Örnek |
|---|---|
| Zorunlu alan | Ad, soyad, employee number boş olamaz |
| Format | TCKN, IBAN, tarih, e-posta formatı |
| Referans | Departman/pozisyon var mı? |
| Benzersizlik | Employee number tenant içinde tekil mi? |
| İlişki | Manager employee mevcut mu? |
| Tarih | İşe giriş tarihi geçerli mi? |
| Güvenlik | Hassas veri doğru alana mı geliyor? |
| Uyarı | Eksik opsiyonel alan, tanınmayan belge tipi |

## 6. Export prensipleri

| İlke | Karar |
|---|---|
| Yetki | Export görüntüleme yetkisinden ayrı permission ister |
| Audit | Her export kaydı tutulur |
| Async | Büyük export background job olur |
| Expiry | Link süreli olur |
| Watermark | Hassas exportlarda opsiyonel watermark |
| Masking | Yetkiye göre alanlar maskelenir veya çıkarılır |
| Format | CSV/XLSX/JSON opsiyonları |

## 7. Export kapsamı

| Export | Faz |
|---|---|
| Çalışan listesi | MVP |
| İzin raporu | MVP |
| Eksik belge raporu | MVP |
| Audit export | MVP/V1 |
| Bordro hazırlık export | V1 |
| Puantaj export | V1 |
| Aday pipeline export | V1 |
| Tüm tenant veri exportu | Offboarding/V1 |

## 8. Veri migrasyonu rolleri

| Rol | Sorumluluk |
|---|---|
| `hr_specialist` | Veri şablonunu doldurur, hataları düzeltir |
| `tenant_admin` | Import ayarlarını ve mapping'i onaylar |
| `implementation_consultant` | Profesyonel kurulumda migrasyonu yürütür |
| `auditor` | Import/export kayıtlarını inceler |
| `security_admin` | Hassas exportları izler |

## 9. Offboarding veri teslimi

Müşteri ayrılırsa:

1. Tenant veri export talebi açılır.
2. Yetkili kişi doğrulanır.
3. JSON/CSV + belgeler paketlenir.
4. Dosya hash ve manifest üretilir.
5. Süreli indirme linki paylaşılır.
6. İndirme auditlenir.
7. Sözleşme ve saklama süresi sonunda imha süreci başlar.

## 10. Veri kalite metrikleri

| Metrik | Anlamı |
|---|---|
| Import başarı oranı | Hatasız satır / toplam satır |
| Kritik hata sayısı | Commit engelleyen hata |
| Uyarı sayısı | Commit'e izin veren ama dikkat isteyen kayıt |
| İlk importtan ilk değere süre | Onboarding başarısı |
| Duplicate oranı | Veri temizliği göstergesi |
| Eksik zorunlu alan oranı | Müşteri veri kalitesi |

## 11. Kabul kriterleri

- Çalışan import dry-run çalışır.
- Hatalı satır ve alan kullanıcıya anlaşılır gösterilir.
- Commit öncesi kullanıcı summary görür.
- Import işlemi audit'e düşer.
- Export yetkisiz kullanıcı tarafından alınamaz.
- Büyük export async job olarak çalışır.
- Offboarding export manifest ve hash üretir.

## 12. İlgili dokümanlar

- [Veritabanı Modeli ve ERD](01-veritabani-modeli-ve-erd.md)
- [API Standartları, OpenAPI ve Webhook](02-api-standartlari-openapi-webhook.md)
- [Personel, Özlük ve Doküman Yönetimi Modülü](../03-moduller/02-personel-ozluk-dokuman.md)
