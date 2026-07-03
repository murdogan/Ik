# KVKK, GDPR ve Veri Yönetişimi

Bu doküman, IK Platform'un kişisel veri işleme, aydınlatma/rıza, veri sınıflandırma, saklama/imha, veri sahibi talepleri ve VERBİS çıktısı yaklaşımını tanımlar.

## 1. Uyum prensipleri

| İlke | Ürün kararı |
|---|---|
| Hukuka uygunluk | Her veri kategorisi için amaç ve hukuki sebep metadata olarak tutulur |
| Veri minimizasyonu | Formlar sadece gerekli alanları ister |
| Şeffaflık | Aydınlatma metni sürümü ve gösterim/kabul kaydı tutulur |
| Amaç sınırlaması | Veri modül amacı dışında kullanılmaz; AI için ayrıca amaç gerekir |
| Saklama sınırlaması | Retention policy ve imha/anonimleştirme job'ları |
| Güvenlik | Encryption, masking, RLS, audit |
| Hesap verebilirlik | DSAR workflow, audit export, VERBİS envanter çıktısı |

## 2. Veri sınıflandırması

| Sınıf | Örnek | Kontrol |
|---|---|---|
| Public | Kariyer sitesi ilanı | CDN/cache |
| Internal | Departman, pozisyon adı | RBAC |
| Confidential PII | Adres, telefon, e-posta | Encryption/masking |
| Sensitive financial | Maaş, IBAN, bordro | Field permission, step-up |
| Special category | Sağlık raporu, engellilik bilgisi | Ayrı hukuki sebep, sıkı erişim |
| Profiling/AI | Aday skoru, attrition risk | Human-in-loop, itiraz, governance |

## 3. Aydınlatma ve rıza

| Süreç | Gereksinim |
|---|---|
| Çalışan aydınlatma | İşe girişte veya ilk login'de gösterilir |
| Aday aydınlatma | Başvuru öncesi public portalda gösterilir |
| Açık rıza | Aday havuzu, CV AI işleme, pazarlama gibi ayrı amaçlarla alınır |
| Rıza geri çekme | Portal üzerinden geri çekilebilir olmalıdır |
| Metin versiyonu | Hash, sürüm, yayın tarihi tutulur |
| Kanıt | IP, timestamp, user agent, metin hash |

## 4. Saklama ve imha

| Veri kategorisi | Yaklaşım |
|---|---|
| Aday başvurusu | Rıza/policy süresi sonunda silme veya anonimleştirme |
| Çalışan özlük | İş ilişkisi ve yasal saklama boyunca restricted archive |
| Bordro | Yasal saklama, şifreli arşiv, sınırlı erişim |
| PDKS | Amaç ve uyuşmazlık ihtiyacına göre süreli saklama |
| Audit log | Güvenlik ve uyum için değişmez saklama |
| AI request/output | Risk tier'a göre kısa saklama ve redaction |

Kesin süreler hukuk/bordro uzmanı ve müşteri sektörüyle parametre olarak doğrulanmalıdır.

## 5. Veri sahibi talepleri

| Talep | Workflow |
|---|---|
| Erişim | Kimlik doğrulama, veri kaynakları tarama, export paketi |
| Düzeltme | Talep, HR onayı, alan güncelleme audit |
| Silme | Yasal saklama kontrolü, silinebilir veri listesi |
| İşlemeyi kısıtlama | Restricted flag ve erişim sınırı |
| Taşınabilirlik | JSON/CSV export |
| İtiraz | Profiling/AI süreçleri için inceleme |
| Otomatik karar itirazı | AI output ve insan karar geçmişiyle değerlendirme |

## 6. Privacy veri modeli

| Tablo | Amaç |
|---|---|
| `privacy_requests` | Veri sahibi talepleri |
| `privacy_request_tasks` | Modül bazlı görevler |
| `privacy_notices` | Aydınlatma metinleri |
| `privacy_acknowledgements` | Okundu/kabul kayıtları |
| `consents` | Rıza kayıtları |
| `retention_policies` | Saklama politikaları |
| `retention_jobs` | İmha/anonimleştirme işleri |
| `data_categories` | Veri envanteri |
| `processors` | Tedarikçi/alıcı kayıtları |

## 7. VERBİS çıktısı

| VERBİS alanı | Kaynak |
|---|---|
| Veri kategorisi | Data catalog |
| İşleme amacı | Module/field purpose metadata |
| Hukuki sebep | `legal_basis` |
| Alıcı grubu | Integration/processor registry |
| Veri konusu kişi grubu | Employee, candidate, dependent |
| Saklama süresi | `retention_policies` |
| Teknik/idari tedbirler | Security controls catalog |
| Yurt dışı aktarım | Processor region ve AI provider config |

## 8. AI uyum kuralları

| AI özelliği | Risk | Kontrol |
|---|---|---|
| Politika asistanı | Orta | RAG ACL, kaynak gösterimi |
| CV ayrıştırma | Orta | Aday rızası, insan doğrulama |
| Aday eşleştirme | Yüksek | Yasaklı sinyal dışlama, açıklama, insan kararı |
| Performans özeti | Yüksek | Manager edit/onay |
| Eğitim önerisi | Orta | Öneri niteliği, opt-out |
| Attrition risk | Yüksek | Aggregate varsayılan, bireysel skor sıkı onay |

## 9. Privacy by design kabul kriterleri

- Yeni veri alanı classification olmadan eklenmez.
- Hassas alanlar varsayılan maskelidir.
- Export audit + expiry ile üretilir.
- Rıza geri çekilince bağlı işlem durur.
- RAG yetkisiz dokümanı kaynak olarak kullanmaz.
- DSAR talebi due date ve escalation üretir.
- Vendor/processor eklenmeden DPA/region kaydı yapılır.

## 10. İlgili dokümanlar

- [AI Güvenliği ve Model Yönetişimi](04-ai-guvenligi-ve-model-yonetisimi.md)
- [Güvenlik Mimarisi, OWASP ve Incident](03-guvenlik-mimarisi-owasp-incident.md)
- [AI Özellikleri ve Governance Modülü](../03-moduller/12-ai-ozellikleri-ve-governance.md)
