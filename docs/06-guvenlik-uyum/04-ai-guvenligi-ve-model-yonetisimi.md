# AI Güvenliği ve Model Yönetişimi

Bu doküman, IK Platform'da AI özelliklerinin güvenli, denetlenebilir ve KVKK/GDPR uyumlu şekilde çalışması için gerekli kontrolleri tanımlar.

## 1. Karar özeti

AI özellikleri doğrudan modüllerden model sağlayıcıya çağrı atmaz. Tüm çağrılar merkezi AI Gateway veya AI modülü üzerinden yürür.

AI Gateway sorumlulukları:

- PII masking/redaction.
- Prompt versioning.
- Model/provider routing.
- Kota ve maliyet takibi.
- Output schema validation.
- Human review workflow.
- Audit ve governance kaydı.

## 2. AI risk sınıfları

| Risk | Örnek özellik | Zorunlu kontrol |
|---|---|---|
| Low | Metin taslağı, duyuru önerisi | Kullanıcı düzenler, audit optional |
| Medium | Politika asistanı, eğitim önerisi | Kaynak gösterimi, RAG ACL, feedback |
| High | CV eşleştirme, performans özeti | Human-in-loop, explanation, bias review |
| Critical | Otomatik işe alma/işten çıkarma kararı | Ürün kapsamı dışında; yasak |

## 3. Yasaklı kullanım alanları

- AI çıktısıyla tek başına işe alma/eleme kararı vermek.
- AI çıktısıyla tek başına işten çıkarma veya disiplin kararı vermek.
- Korunan özellikleri doğrudan veya proxy olarak skorlamada kullanmak.
- Çalışanları gizli bireysel gözetim/skorlama ile hedeflemek.
- Rıza veya hukuki dayanak olmadan CV/aday verisi işlemek.

## 4. Veri minimizasyonu ve maskeleme

Prompt'a gönderilecek veri minimum olmalıdır.

| Veri | Yaklaşım |
|---|---|
| TCKN/YKN | Gönderilmez veya redacted |
| IBAN/maaş | Varsayılan gönderilmez; yüksek güvenlikli izin ister |
| Sağlık verisi | AI prompt kapsamı dışında, özel onay olmadan yasak |
| Aday CV | Rıza ve amaç kaydıyla işlenir |
| Performans notu | Manager review ve source link gerekir |
| Doküman içeriği | RAG ACL ve chunk-level permission ile |

## 5. RAG güvenliği

RAG tabanlı asistanlar için:

- Her doküman chunk'ı `tenant_id` taşır.
- ACL hash veya permission metadata tutulur.
- Retrieval tenant + permission filtresi olmadan çalışmaz.
- Yanıt kaynak gösterir.
- Yetkisiz kaynak asla cevapta kullanılmaz.
- Prompt injection içeren dokümanlar riskli işaretlenir.

## 6. Prompt injection savunması

Kontroller:

- Sistem talimatları kullanıcı/doküman içeriğinden ayrılır.
- RAG içeriği güvenilmeyen veri olarak işaretlenir.
- Tool/action çağrıları allowlist ile sınırlanır.
- Model çıktısı schema validation'dan geçer.
- Riskli output human review'a düşer.
- Prompt injection sinyalleri security event üretir.

## 7. Human-in-the-loop

AI çıktısı karar değil, öneri olmalıdır.

| Alan | İnsan kontrolü |
|---|---|
| CV parse | Kullanıcı alanları onaylar/düzeltir |
| Aday eşleştirme | Recruiter açıklamayı görür, karar kendisinde kalır |
| Performans özeti | Manager edit/onay yapar |
| Eğitim önerisi | Çalışan/yönetici kabul eder veya reddeder |
| Attrition risk | Varsayılan aggregate; bireysel kullanım ayrı governance ister |

## 8. Model registry

Her model ve prompt sürümü kayıt altında olmalıdır.

| Alan | Açıklama |
|---|---|
| `model_provider` | OpenAI/Anthropic/local vb. |
| `model_name` | Kullanılan model |
| `prompt_version` | Prompt şablon versiyonu |
| `risk_tier` | Low/Medium/High/Critical |
| `allowed_features` | Hangi modüllerde kullanılabilir |
| `data_sent` | Gönderilen veri kategorileri |
| `retention_policy` | Prompt/output saklama |
| `approval_status` | Security/privacy/product onayı |

## 9. Bias ve açıklanabilirlik

High-risk AI özellikleri için:

- Korunan özellikler model input'undan çıkarılır.
- Proxy sinyal riski değerlendirilir.
- Output açıklama taşır.
- Aday/çalışan itiraz süreci vardır.
- Periyodik bias/drift kontrolü yapılır.
- Skor tek başına karar kriteri değildir.

## 10. AI audit modeli

| Kayıt | Amaç |
|---|---|
| `ai_requests` | Kim, ne zaman, hangi feature ile çağrı yaptı |
| `ai_outputs` | Output, schema status, review status |
| `ai_prompt_versions` | Prompt şablon geçmişi |
| `ai_model_registry` | Model/provider governance |
| `ai_feedback` | Kullanıcı düzeltmesi ve kalite sinyali |
| `ai_incidents` | Prompt injection, leakage, unsafe output |

## 11. Provider ve veri aktarımı

Model sağlayıcı seçimi için zorunlu kontroller:

- Müşteri verisiyle training kapalı olmalı.
- DPA ve veri işleyen kaydı olmalı.
- Region/yurt dışı aktarım kaydı tutulmalı.
- Log retention ve deletion policy bilinmeli.
- Enterprise tenant için AI disable/enable ayarı olmalı.
- Hassas özellikler tenant bazında kapatılabilir olmalı.

## 12. AI feature rollout

Yeni AI özelliği için gate:

1. Use-case ve risk tier belirlenir.
2. Veri kategorileri listelenir.
3. Hukuki sebep/rıza değerlendirilir.
4. Prompt ve output schema review edilir.
5. Security/privacy approval alınır.
6. Pilot tenant feature flag ile açılır.
7. Feedback, hata ve bias sinyalleri izlenir.
8. GA öncesi kabul kriterleri tamamlanır.

## 13. Kabul kriterleri

- AI çağrıları merkezi gateway/modül üzerinden geçer.
- Prompt'a gereksiz PII gönderilmez.
- RAG yetkisiz dokümanı kullanmaz.
- High-risk output human review olmadan final karara dönüşmez.
- Prompt/model sürümleri auditlenir.
- Provider no-training ve DPA kaydı olmadan aktif edilmez.
- AI feature tenant bazında kapatılabilir.

## 14. İlgili dokümanlar

- [AI Özellikleri ve Governance Modülü](../03-moduller/12-ai-ozellikleri-ve-governance.md)
- [KVKK, GDPR ve Veri Yönetişimi](02-kvkk-gdpr-veri-yonetisimi.md)
- [Teknoloji Kararları ADR](../04-mimari/03-teknoloji-kararlari-adr.md)
