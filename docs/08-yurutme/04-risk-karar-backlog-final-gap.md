# Risk, Karar Backlog ve Final Gap Kontrolü

Bu doküman, IK Platform foundation dokümantasyon setinin açık risklerini, karar backlog'unu ve implementasyona geçmeden önce tamamlanması gereken final kontrol listesini tanımlar.

## 1. Amaç

Bu dosya, strateji/ürün/mimari/güvenlik/operasyon dokümanlarının sonunda tek bir kontrol noktasıdır. Kodlamaya geçmeden önce belirsizliklerin bilinçli şekilde kabul edilmesini veya kapatılmasını sağlar.

## 2. Ana risk kayıtları

| ID | Risk | Etki | Azaltım |
|---|---|---|---|
| R-001 | MVP kapsamı fazla genişler | Teslim gecikir | Must/Should/Could kesme çizgisi |
| R-002 | RBAC/scope modeli geç oturur | Tüm modüller etkilenir | AUTH ilk sprintlerde tamamlanır |
| R-003 | Tenant izolasyonu hatası | Kritik güvenlik riski | RLS/guard + cross-tenant test |
| R-004 | PDKS formatları çeşitlenir | Pilot gecikir | CSV/mapping/staging yaklaşımı |
| R-005 | Bordro beklentisi yanlış satılır | Güven kaybı | MVP export modu net konumlandırılır |
| R-006 | KVKK/AI uyumu eksik kalır | Hukuki risk | Privacy review ve AI Gateway zorunlu |
| R-007 | Veri migrasyonu kalitesiz olur | İlk değer gecikir | Dry-run ve hata raporu |
| R-008 | Test borcu birikir | Regresyon artar | DoD ve QA otomasyon kapıları |
| R-009 | Pilot müşteri özel geliştirme ister | Roadmap sapar | Scope contract ve triage |
| R-010 | Operasyonel izleme yetersiz kalır | Incident geç fark edilir | SLO/dashboard/runbook |

## 3. Karar backlog'u

| Karar | Durum | Ne zaman netleşmeli |
|---|---|---|
| Native mobil mi PWA mı? | MVP için PWA/responsive önerili | Sprint-0/S1 |
| Bordro motoru MVP'de var mı? | Hayır, export modu | Satış mesajı öncesi |
| İlk hedef segment | Üretim/hizmet/perakende aday | GTM hazırlığı |
| SSO MVP'ye girer mi? | Hayır, V1/Enterprise | Enterprise pilot öncesi |
| AI hangi model/provider? | Gateway soyutlar, sağlayıcı değişebilir | AI pilot öncesi |
| PDKS ilk formatlar | CSV + manuel mapping | Pilot müşteri seçimi |
| Pricing PEPM seviyesi | Varsayım; pazar görüşmesiyle doğrulanır | Pilot ücretli geçiş öncesi |
| GitHub Projects/Jira | Tek kaynak seçilmeli | Sprint-0 |

## 4. Kodlamaya geçiş checklist'i

- Repo iskeleti oluşturuldu.
- CI temel pipeline çalışıyor.
- DB migration altyapısı seçildi.
- Tenant model ve RLS/guard kararı uygulandı.
- Auth/session yaklaşımı netleşti.
- İlk UI design system seçildi.
- OpenAPI standardı kabul edildi.
- Test stratejisi DoD'ye bağlandı.
- İlk 3 sprint backlog'u DoR seviyesinde.
- Pilot müşteri veri şablonları hazır.

## 5. Dokümantasyon gap kontrolü

Bu foundation setinde kapsanan alanlar:

- Strateji ve pazar.
- Ürün kapsamı/persona/metrik.
- Modül tanımları.
- Mimari ve teknoloji kararları.
- API/veri/entegrasyon.
- Güvenlik/KVKK/AI governance.
- Operasyon/test/runbook.
- Roadmap/ekip/GTM/risk.

Kalan implementasyon öncesi dokümanlar:

- Sprint-0 teknik task breakdown.
- ERD'nin gerçek migration karşılığı.
- İlk Figma/wireframe seti.
- İlk OpenAPI taslak dosyası.
- Pilot müşteri veri import şablonları.
- Satış demo scripti ve landing page metni.

## 6. İlk uygulanacak teknik sıra

1. Monorepo ve CI.
2. Backend app skeleton.
3. DB migration ve tenant tablosu.
4. Auth login/session.
5. RBAC permission modeli.
6. Employee minimal CRUD.
7. Audit event.
8. Web admin skeleton.
9. Employee list/detail UI.
10. Cross-tenant test suite.

## 7. Yönetim ritmi

| Ritim | Amaç |
|---|---|
| Haftalık roadmap review | Scope ve risk kontrolü |
| Sprint review | Çalışan yazılım gösterimi |
| Security/privacy review | Yeni riskleri kapatma |
| Pilot steering | Müşteri değeri ve blocker kontrolü |
| Monthly cost review | Burn ve cloud/AI maliyet kontrolü |

## 8. Kabul kriterleri

- Kritik riskler sahipli hale gelir.
- Karar backlog'u Sprint-0'a taşınır.
- Kodlamaya geçiş checklist'i görünür olur.
- Foundation doküman seti link ve kalite kontrolünden geçer.
- Repo temiz ve branch pushlanmış durumdadır.

## 9. İlgili dokümanlar

- [Roadmap, Fazlar ve Milestone Planı](01-roadmap-fazlar-milestone.md)
- [DevOps, Ortamlar ve Sürüm Yönetimi](../07-operasyon/01-devops-ortamlar-surum-yonetimi.md)
- [Test Stratejisi ve QA](../07-operasyon/03-test-stratejisi-qa.md)
