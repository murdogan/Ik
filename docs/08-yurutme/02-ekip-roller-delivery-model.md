# Ekip, Roller ve Delivery Operating Model

Bu doküman, IK Platform için ürün geliştirme ekibi, roller, çalışma ritmi, RACI, DoR/DoD ve maliyet varsayımlarını tanımlar.

## 1. Ekip ilkesi

MVP için hedef, küçük ama uçtan uca teslim yapabilen çapraz fonksiyonel ekip kurmaktır. Çok ekipli organizasyona ürün-pazar doğrulaması sonrası geçilmelidir.

## 2. MVP ekip yapısı

| Rol | FTE | Sorumluluk |
|---|---:|---|
| Product Owner / PM | 1 | Backlog, öncelik, pilot müşteri |
| UX/UI Designer | 1 | Tasarım sistemi, akışlar, usability |
| Tech Lead / Architect | 1 | Mimari, kalite, kritik PR |
| Backend Developer | 3-4 | FastAPI, domain modülleri, API |
| Frontend Developer | 2-3 | Next.js admin/portal |
| QA Engineer | 1-2 | Test otomasyonu, regresyon, UAT |
| DevOps/SRE | 1 | CI/CD, ortam, observability |
| Domain Expert | 0.5 | İK/bordro/mevzuat doğrulama |
| Security/KVKK Advisor | 0.5 | Güvenlik ve uyum review |

Native mobil ayrı ekip gerektiriyorsa V1'e ertelenebilir; MVP'de responsive/PWA daha kontrollüdür.

## 3. V1 eklemeleri

| Rol | Gerekçe |
|---|---|
| Backend +1/+2 | PDKS, payroll, ATS paralel geliştirme |
| Data/AI engineer | AI Gateway, RAG, analytics |
| Customer Success | Pilot/GA onboarding ve hypercare |
| Sales/BD | Referans satış ve pipeline |
| Support specialist | L1 destek ve helpdesk |

## 4. Çalışma modeli

- Sprint uzunluğu: 2 hafta.
- Haftalık backlog refinement.
- Sprint review'da çalışan yazılım demosu.
- Kritik kararlar ADR olarak yazılır.
- Her modül için owner atanır.
- GitHub Issues/Projects veya Jira kullanılabilir; tek kaynak olmalıdır.

## 5. Definition of Ready

Bir story sprint'e girmeden önce:

- Kullanıcı rolü ve değeri net.
- Kabul kriterleri yazılmış.
- UI gerekiyorsa wireframe hazır.
- API/data etkisi belli.
- Güvenlik/KVKK etkisi işaretli.
- Test yaklaşımı belirli.
- 13 SP üstüyse bölünmüş.

## 6. Definition of Done

Bir story bitmiş sayılmak için:

- PR merge edildi.
- Unit/integration testleri geçti.
- API değiştiyse OpenAPI güncellendi.
- Permission/scope testleri eklendi.
- UI responsive ve temel accessibility kontrolünden geçti.
- Audit/log/metric etkisi değerlendirildi.
- İlgili doküman güncellendi.
- Staging veya preview ortamında PO kabulü alındı.

## 7. RACI özeti

| Süreç | PO | Tech Lead | Dev | QA | SRE | Security/KVKK | Domain |
|---|---|---|---|---|---|---|---|
| Backlog | A/R | C | C | C | I | C | C |
| Mimari | C | A/R | R | C | C | C | I |
| Sprint teslimi | A | R | R | R | C | I | I |
| Release | A | C | C | R | R | C | I |
| Security review | I | A | C | C | C | R | I |
| KVKK review | A | C | C | C | I | R | C |
| Bordro/mevzuat | A | C | R | C | I | I | R |
| Pilot | A/R | C | C | C | C | C | C |

## 8. Kalite kapıları

- PR review zorunlu.
- Security-critical PR için Tech Lead/Security onayı.
- Migration PR için rollback notu.
- Feature flag gerektiren işler flag olmadan merge edilmez.
- Test kırmızıysa merge yok.
- Doküman değişmesi gereken davranış docs olmadan merge edilmez.

## 9. Maliyet varsayımları

Personel en büyük maliyet kalemidir. İlk aşamada maliyet azaltmak için:

- Native mobil ertelenebilir.
- AI özellikleri pilotla sınırlanabilir.
- Enterprise/on-prem kapsamı V1 sonrası alınabilir.
- Hazır bordro motoru yerine MVP'de export modu kullanılabilir.
- Tasarım sistemi ile UI hızlandırılır.

## 10. Delivery riskleri

| Risk | Azaltım |
|---|---|
| Kapsam dağılması | Roadmap faz sınırları ve DoR/DoD |
| Yetki modeli geç çözülür | AUTH/RBAC ilk sprintlerde |
| Test borcu büyür | DoD test zorunluluğu ve QA otomasyon |
| Pilot veri gecikir | Veri migrasyon araçları erken |
| Tek kişiye bağımlılık | Modül ownership + dokümantasyon |
| Domain hatası | İK/bordro uzmanı review |

## 11. İlgili dokümanlar

- [Roadmap, Fazlar ve Milestone Planı](01-roadmap-fazlar-milestone.md)
- [Test Stratejisi ve QA](../07-operasyon/03-test-stratejisi-qa.md)
- [Teknoloji Kararları ADR](../04-mimari/03-teknoloji-kararlari-adr.md)
