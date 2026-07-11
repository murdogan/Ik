# Implementation Readiness Checklist

> **Arşiv notu — 2026-07-11:** Bu belge uygulama öncesi planlama kapısını tarihsel olarak
> korur; artık aktif yürütme otoritesi değildir. Kodlama yetkisi
> [MVP First Release Master Development Plan](../../.hermes/plans/2026-07-10_122125-mvp-first-release-master-development-plan.md)
> ile verilmiş, P0A–P0G'nin enumerated Faz 0 kapısı yerelde yeşil olmuştur. Güncel durum ve
> açık review sapmaları [API Implementation Status Report](11-api-implementation-status.md)
> içindedir. Aktif checkpoint `STOP — awaiting Murat review`; Faz 1 başlatılmamıştır.

Bu doküman, planın gerçekten tamam sayılması için son kontrol listesidir. Kodlamaya tekrar geçmeden önce bu listedeki maddeler ya tamamlanmalı ya da bilinçli istisna olarak işaretlenmelidir.

## 1. Plan tamam tanımı

Plan tamam demek:

- Ürün ne yapacak belli.
- MVP sınırı belli.
- Modüller belli.
- Teknik mimari belli.
- API/veri/güvenlik yaklaşımı belli.
- İlk sprintlerde hangi işlerin yapılacağı belli.
- Demo, pilot ve satış anlatısı belli.
- Uygulama başlamadan önce geliştiriciye verilecek tasklar belli.

## 2. Foundation doküman kontrolü

| Alan | Durum | Not |
|---|---|---|
| Strateji ve pazar | Hazır | Konumlandırma, rakip, fiyatlama |
| Ürün kapsamı | Hazır | MVP/V1/V2 ayrımı var |
| Modül dokümanları | Hazır | 12 ana modül yazıldı |
| Mimari | Hazır | Teknik mimari, multi-tenancy, ADR |
| API/veri | Hazır | DB, API, entegrasyon, migrasyon |
| Güvenlik/KVKK | Hazır | Auth, KVKK, OWASP, AI güvenliği |
| Operasyon/test | Hazır | DevOps, observability, QA, runbook |
| Yürütme | Hazır | Roadmap, ekip, GTM, risk |
| Uygulama planı | Bu paketle tamamlanıyor | Sprint, OpenAPI, ERD, wireframe, import, demo |

## 3. Kodlamaya geçiş kapısı

Kodlamaya geçmeden önce:

- Bu doküman seti kullanıcı tarafından yön olarak onaylanır.
- Sprint-0/Sprint-1 backlog'u GitHub/Jira'ya taşınır.
- İlk Figma frame'leri bu wireframe planına göre hazırlanır.
- OpenAPI taslağı backend/frontend tarafından kabul edilir.
- ERD migration sırası kabul edilir.
- Pilot import şablonları hazırlanır.
- Demo mesajı satış/ürün tarafından onaylanır.

## 4. Açık kararlar

| Karar | Öneri | Sahip |
|---|---|---|
| PWA mı native mobil mi? | MVP PWA/responsive | Product |
| İlk pilot segment | Üretim/hizmet/perakende | GTM |
| Bordro MVP kapsamı | Export/hazırlık, hesaplama değil | Product |
| SSO MVP kapsamı | V1/Enterprise | Product/Tech |
| AI MVP kapsamı | Yok, V1 pilot | Product/Security |
| Task takip aracı | GitHub Projects yeterli | PM/Tech |

## 5. Uygulama başlamadan önce silinmeyecek ama durdurulacak kod notu

Mevcut repoda küçük bir backend scaffold oluştu. Kullanıcının tercihi planın önce tamamlanması olduğu için bu noktadan sonra:

- Yeni kod eklenmemeli.
- CI/infra/uygulama genişletilmemeli.
- Sadece plan/doküman tamamlanmalı.
- Kod tarafı, plan onayı sonrası ayrıca ele alınmalı.

## 6. Plan eksiksizlik kriterleri

Aşağıdaki sorulara evet deniyorsa plan uygulamaya hazırdır:

- Hangi müşteri için yapıyoruz?
- İlk 8 hafta neyi doğrulayacağız?
- MVP'de ne var/ne yok?
- İlk sprintte hangi endpointler var?
- İlk tablolarda hangi alanlar var?
- İlk ekran akışları hangileri?
- Veri importu nasıl olacak?
- Demo nasıl anlatılacak?
- Hangi riskler bilinçli kabul edildi?
- Kodlamaya geçiş kapısı ne?

## 7. Son kullanıcı onay formatı

Plan onayı şu şekilde alınmalıdır:

```text
Plan yönünü onaylıyorum.
Kodlamaya geçmeden önce sadece şu değişiklikleri istiyorum: ...
```

veya:

```text
Planı onaylıyorum, artık Sprint-0 kod uygulamasına geç.
```

Bu onay olmadan yeni kod genişletmesi yapılmamalıdır.

## 8. Kabul kriterleri

- Plan setinde uygulama öncesi boşluk kalmaz.
- Kodlama kapısı açıkça tanımlıdır.
- Mevcut kod scaffold'u büyütülmez.
- Plan onay formatı nettir.
- README indeksleri günceldir.

## 9. Planın tamam sayılmadığı durumlar

Aşağıdaki durumlardan biri varsa plan hâlâ eksik kabul edilir:

- MVP kapsamı satış anlatısıyla çelişiyorsa.
- İlk sprint backlog'u geliştiriciye task olarak verilemeyecek kadar belirsizse.
- OpenAPI taslağı ekran akışlarını desteklemiyorsa.
- Import şablonları pilot müşterinin gerçek veri hazırlığını yönlendirmiyorsa.
- ERD/migration sırası hassas veri kararlarını atlıyorsa.
- Demo anlatısı üründe olmayan özellikleri vaat ediyorsa.
- Kodlamaya geçiş için açık kullanıcı onayı tanımlanmamışsa.

Bu maddeler, planın sadece “çok doküman var” seviyesinde değil, uygulanabilir ürün planı seviyesinde tamamlanmasını sağlar.

## 10. İlgili dokümanlar

- [Sprint-0 / Sprint-1 Backlog ve Task Planı](02-sprint-0-1-backlog-ve-task-plani.md)
- [OpenAPI Endpoint Taslağı](03-openapi-endpoint-taslagi.md)
- [ERD ve Migration Uygulama Planı](04-erd-migration-uygulama-plani.md)
- [Demo, Landing ve Satış Anlatısı Planı](07-demo-landing-satis-anlatisi-plani.md)
