# IK Dokümantasyon İndeksi

Bu klasör, İnsan Kaynakları Yönetim Sistemi'nin ürün ve geliştirme dokümantasyonunun ana kaynağıdır. Amaç; fikir seviyesinde kalan notları, geliştirme ekibinin doğrudan iş çıkarabileceği, yatırımcıya veya iş ortağına anlatılabilecek, test ve canlıya alma süreçlerine bağlanabilecek düzenli bir dokümantasyon setine dönüştürmektir.

## Kullanılacak kalite standardı

Bu doküman setinde iki referans yaklaşım birleştirilir:

- **Codex yaklaşımı:** Klasör yapısı, modül listesi, kapsama kontrol listesi ve düzen.
- **Claude yaklaşımı:** Uzun, detaylı, gerekçeli, uygulanabilir ve karar odaklı içerik kalitesi.

Her yeni dosya yazılırken önce ilgili Codex dosyası kapsam kontrolü için, sonra Claude dosyası kalite ve detay standardı için taranır. Eski repo dokümanları aktif ağaçta tutulmaz; gerekirse Git geçmişinden bakılır.

## Okuma sırası

Yeni biri projeye girdiğinde şu sırayı takip etmelidir:

1. [Konvansiyonlar ve Standartlar](00-genel/01-konvansiyonlar-ve-standartlar.md)
2. [Terimler, Roller ve Karar Kaydı](00-genel/02-terimler-roller-ve-karar-kaydi.md)
3. [Modül Formatı ve Ortak Kararlar](03-moduller/00-modul-format-ve-ortak-kararlar.md)
4. Ürün vizyonu ve strateji dokümanları
5. MVP/V1/V2 kapsam dokümanları
6. Sorumlu olduğu modül dokümanı
7. İlgili mimari, API/veri, güvenlik ve test dokümanları

## Doküman ağacı

```text
docs/
├── README.md
├── 00-genel/
│   ├── 01-konvansiyonlar-ve-standartlar.md
│   └── 02-terimler-roller-ve-karar-kaydi.md
├── 01-strateji-pazar/
│   ├── 01-urun-vizyonu-ve-konumlandirma.md
│   ├── 02-pazar-ve-rakip-analizi.md
│   ├── 03-farklilasma-ve-deger-onermesi.md
│   └── 04-fiyatlandirma-ve-paketleme.md
├── 02-urun/
│   ├── 01-personalar-jtbd-ve-kullanici-yolculuklari.md
│   ├── 02-kanallar-web-mobil-self-servis.md
│   ├── 03-mvp-v1-v2-kapsam-kararlari.md
│   └── 04-urun-metrikleri-ve-basari-kriterleri.md
├── 03-moduller/
│   ├── 00-modul-format-ve-ortak-kararlar.md
│   ├── 01-core-tenant-auth-rbac.md
│   ├── 02-personel-ozluk-dokuman.md
│   ├── 03-izin-devamsizlik-onay.md
│   ├── 04-zaman-vardiya-pdks-puantaj.md
│   ├── 05-bordro-ucret-mevzuat.md
│   ├── 06-ise-alim-ats-aday-portali.md
│   ├── 07-performans-okr-360.md
│   ├── 08-egitim-yetkinlik-kariyer.md
│   ├── 09-organizasyon-kadro-pozisyon.md
│   ├── 10-self-servis-talep-duyuru.md
│   ├── 11-raporlama-people-analytics.md
│   └── 12-ai-ozellikleri-ve-governance.md
├── 04-mimari/
│   ├── 01-teknik-mimari-genel-bakis.md
│   ├── 02-cok-kiracilik-ve-veri-izolasyonu.md
│   ├── 03-teknoloji-kararlari-adr.md
│   └── 04-uygulama-yuzeyleri-web-mobil-api.md
├── 05-api-veri/
│   ├── 01-veritabani-modeli-ve-erd.md
│   ├── 02-api-standartlari-openapi-webhook.md
│   ├── 03-entegrasyonlar-sgk-banka-muhasebe-pdks.md
│   └── 04-veri-migrasyonu-import-export.md
├── 06-guvenlik-uyum/
│   ├── 01-kimlik-dogrulama-yetkilendirme.md
│   ├── 02-kvkk-gdpr-veri-yonetisimi.md
│   ├── 03-guvenlik-mimarisi-owasp-incident.md
│   └── 04-ai-guvenligi-ve-model-yonetisimi.md
├── 07-ui-ux/
│   ├── 01-tasarim-sistemi-ve-bilesenler.md
│   ├── 02-sayfa-akislari-ve-wireframe-notlari.md
│   └── 03-mobil-deneyim-stratejisi.md
├── 08-devops-test/
│   ├── 01-devops-surumleme-ortamlar.md
│   ├── 02-observability-slo-sla.md
│   └── 03-test-stratejisi-kalite-kapilari.md
└── 09-yurutme/
    ├── 01-yol-haritasi.md
    ├── 02-backlog-epic-user-story.md
    ├── 03-sprint-plani.md
    ├── 04-ekip-maliyet-operasyon-plani.md
    └── 05-lansman-pilot-hypercare.md
```

## Doküman statüleri

Aşağıdaki statüler kullanılacaktır:

- **Planlandı:** Dosya yeri ve amacı belli, içerik henüz yazılmadı.
- **Taslak:** İlk sürüm yazıldı, kalite kontrol ve kullanıcı onayı bekliyor.
- **Onaylı:** Kullanıcı tarafından içerik yönü onaylandı.
- **Revizyon gerekli:** Kapsam veya kalite beklentisini karşılamıyor.
- **Arşiv:** Aktif doküman ağacında kullanılmaz; eski içerik yalnızca Git geçmişinden incelenir.

## Faz 1: Temel dosyalar

Bu ilk turda oluşturulan temel dosyalar:

- [Konvansiyonlar ve Standartlar](00-genel/01-konvansiyonlar-ve-standartlar.md)
- [Terimler, Roller ve Karar Kaydı](00-genel/02-terimler-roller-ve-karar-kaydi.md)
- [Modül Formatı ve Ortak Kararlar](03-moduller/00-modul-format-ve-ortak-kararlar.md)

Bu dosyalar tamamlanmadan detay modül dokümanlarına geçilmemelidir; çünkü rol adları, faz kapsamı, yazım formatı, yetki dili ve kalite çıtası burada sabitlenir.

## Kapsam disiplini

MVP, ilk canlıya alınabilir ürün demektir; bütün hayalleri ilk sürüme doldurmak değildir. Bu nedenle her dokümanda özellikler dört seviyeye ayrılır:

- **MVP:** İlk pilot müşteride gerçek değer üreten zorunlu minimum.
- **V1:** MVP sonrası ilk ticari genişleme.
- **V2:** Daha derin operasyon ve otomasyon.
- **Enterprise:** Büyük kurum, regüle sektör, gelişmiş entegrasyon ve yüksek SLA ihtiyaçları.

## Kalite kapıları

Her yeni dokümanda şu kontroller aranır:

1. En az bir net amaç bölümü.
2. Kapsam içi / kapsam dışı ayrımı.
3. MVP / V1 / V2 etkisi.
4. Veri, API, yetki ve KVKK etkisi.
5. Test veya kabul kriteri.
6. Kırık iç link olmaması.
7. Başlık yapısının markdown standardına uygun olması.

## Eski dokümanlar

Önceki repo dokümanları aktif ağaçtan silinmiştir. Yeni dokümantasyon; Codex iskeleti ve Claude kalite standardı üzerinden sıfırdan, daha temiz şekilde ilerler. Eski içerik gerekiyorsa Git geçmişinden incelenir.
