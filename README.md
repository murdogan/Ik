# IK — İnsan Kaynakları Yönetim Sistemi Dokümantasyonu

Bu repo, Türkiye pazarı öncelikli ve global pazara açılabilir bir İnsan Kaynakları Yönetim Sistemi için ürün, strateji, modül, mimari, güvenlik, test ve canlıya alma dokümantasyonunu içerir.

Bu aşamanın amacı kod yazmak değil; kod başlamadan önce ürünün ne olduğu, kime satılacağı, hangi modüllerden oluşacağı, MVP kapsamının nerede biteceği ve teknik kararların nasıl alınacağı konusunda net bir ana kaynak oluşturmaktır.

## Çalışma yaklaşımı

Bu dokümantasyon çalışması üç kaynaktan beslenir:

1. **Codex referansı:** Dosya ve modül iskeleti için ana kontrol listesi.
2. **Claude referansı:** Derinlik, detay seviyesi ve uygulanabilirlik standardı.
3. **Mevcut repo geçmişi:** Daha önce hazırlanmış dokümanlar Git geçmişinde korunur; aktif ağaçta yalnızca yeni temiz dokümantasyon tutulur.

Hedef, bu üç kaynağı doğrudan kopyalamak değil; tutarlı, tekrar etmeyen, geliştirilebilir ve canlıya alınabilir bir ürün dokümantasyonu haline getirmektir.

## İlk prensipler

- Önce dokümantasyon, sonra kod.
- Her kararın sahibi ve etkisi belli olmalı.
- Her modül MVP / V1 / V2 ayrımıyla yazılmalı.
- Her modül veri, API, yetki, KVKK, audit ve test etkisiyle birlikte ele alınmalı.
- Kırık link, yarım dosya ve boş vaat bırakılmamalı.
- Eski dokümanlar aktif ağaçta tutulmamalı; repo geçmişinden gerektiğinde geri bakılmalı.

## Doküman yapısı

Ana giriş noktası: [docs/README.md](docs/README.md)

```text
docs/
├── 00-genel/              # Konvansiyonlar, roller, terimler, karar kayıtları
├── 01-strateji-pazar/     # Vizyon, pazar, rakipler, fiyatlandırma
├── 02-urun/               # Personalar, JTBD, MVP/V1/V2 kapsamı, metrikler
├── 03-moduller/           # Tüm ürün modülleri ve ortak modül formatı
├── 04-mimari/             # Teknik mimari, multi-tenancy, teknoloji kararları
├── 05-api-veri/           # Veritabanı, API, webhook, entegrasyon, migrasyon
├── 06-guvenlik-uyum/      # Auth, RBAC, KVKK/GDPR, OWASP, AI güvenliği
├── 07-ui-ux/              # Tasarım sistemi, ekran akışları, mobil deneyim
├── 08-devops-test/        # Ortamlar, release, observability, test stratejisi
├── 09-yurutme/            # Yol haritası, backlog, sprint, maliyet, lansman
```

## Eski dokümanlar

Önceki dokümanlar aktif klasörden kaldırılmıştır. Gerekirse Git geçmişinden incelenir; yeni ana kaynaklar Claude ve Codex zip referanslarıdır.

## Çalışma sırası

1. Genel standartlar ve modül yazım formatı.
2. Strateji, pazar, rakip, fiyatlandırma ve ürün kapsamı.
3. Modül dokümanları.
4. Mimari, API/veri, güvenlik/uyum.
5. UI/UX, DevOps/test ve yürütme planı.
6. Kullanıcı onayından sonra kod/proje iskeleti.

## Durum

Bu repo şu anda **dokümantasyon temel kurulum** aşamasındadır. Kod üretimi, framework seçimi ve canlıya alma altyapısı bu dokümantasyon tamamlanmadan başlatılmayacaktır.
