# AI Özellikleri ve Governance Modülü

Bu doküman, IK Platform'daki yapay zekâ özelliklerinin kapsamını, risk sınırlarını, insan onayı gereksinimlerini, veri minimizasyonunu ve AI governance kontrollerini tanımlar.

## 1. Amaç ve karar özeti

AI, IK Platform'da ana değer zincirini destekleyen bir katmandır; kritik İK kararlarını otomatik veren bir motor değildir. AI özellikleri ancak veri modeli, yetki, audit ve KVKK temeli oturduktan sonra açılmalıdır.

Karar özeti:

> MVP'de AI sınırlı ve düşük riskli alanlarda düşünülür. V1'de CV parse, politika asistanı ve özetleme; V2'de match score, attrition risk ve gelişmiş öneriler human-in-the-loop ve audit ile açılır.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Politika/doküman asistanı | Otomatik işe alım/red kararı |
| CV ayrıştırma | Otomatik performans notu verme |
| Aday match açıklaması | İşten çıkarma/terfi otomasyonu |
| Performans özeti taslağı | Yasaklı hassas sinyallerle skor |
| Eğitim önerisi | Model training için müşteri verisini varsayılan kullanma |
| Attrition risk segmenti | Açıklamasız kara kutu karar |
| RAG semantik arama | Yetkisiz dokümanı context'e alma |
| AI audit/governance | AI çıktısını final kayıt sayma |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `employee` | Politika asistanı ve kendi verisiyle sınırlı yanıt alır | Own/tenant policy | Başkasının verisi cevapta çıkmamalı |
| `recruiter` | CV parse ve aday match kullanır | ATS scope | Rıza olmadan AI çalışmamalı |
| `manager` | Performans özeti taslağı ve ekip içgörüleri görür | Team | AI taslak final karar olmamalı |
| `hr_director` | AI feature kullanımını ve çıktıları izler | Tenant | Bias/hukuki risk yönetilmeli |
| `ai_governance_admin` | Model, prompt, risk ve feature flag yönetir | Governance | Yanlış model/veri bölgesi riski |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- AI governance veri modeli hazırlığı.
- Düşük riskli politika arama asistanı opsiyonel pilot.
- AI feature flag ve audit standardı.

### V1

- CV parse.
- Politika/doküman asistanı.
- Performans özeti taslağı.
- Eğitim önerisi.
- Prompt redaction ve RAG ACL.

### V2

- Aday match score + açıklama.
- Attrition risk segmentleri.
- People analytics doğal dil sorgu.
- Model monitoring ve bias eval.
- Tenant-specific AI policies.

### Enterprise

- Private model / private deployment opsiyonu.
- DLP entegrasyonu.
- SIEM AI event export.
- AI risk assessment workflow.

## 5. Ana kullanıcı akışları

### 5.1 Politika asistanı

1. Kullanıcı soru sorar.
2. Sistem kullanıcı scope'unu belirler.
3. RAG sadece yetkili dokümanlardan context alır.
4. Yanıt kaynak linkleri ve güven etiketiyle gösterilir.
5. Kullanıcı feedback verebilir.

### 5.2 CV ayrıştırma

1. Recruiter aday CV'si için parse başlatır.
2. Sistem rıza/yasal dayanak kontrolü yapar.
3. CV metni çıkarılır ve PII sınıflanır.
4. Alan önerileri recruiter review ekranında gösterilir.
5. Recruiter onaylarsa aday alanları güncellenir.

### 5.3 Performans özeti

1. Manager review verileri için özet ister.
2. Sistem yalnız yetkili kaynakları toplar.
3. AI taslak özet üretir.
4. Manager düzenler ve final yoruma dönüştürür.
5. Taslak/final farkı auditlenir.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| AI Assistant | Chat, kaynaklar, güven skoru | MVP/V1 |
| CV Parse Review | Çıkarılan alan, confidence, düzeltme | V1 |
| Match Explanation | Skor, gerekçe, dışlanan sinyaller | V2 |
| Performance Summary Draft | Taslak, edit, final farkı | V1/V2 |
| AI Governance Console | Model, prompt, feature, audit | V1/V2 |
| Risk Dashboard | Segment ve aksiyon önerisi | V2 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `ai_features` | AI özellik katalogu | `code`, `risk_tier`, `enabled`, `hitl_required` |
| `ai_model_registry` | Model kayıtları | `provider`, `model_name`, `version`, `data_region` |
| `ai_prompt_templates` | Prompt versiyonları | `feature_code`, `version`, `pii_policy`, `status` |
| `ai_requests` | AI çağrı kaydı | `feature_code`, `actor_id`, `subject_type`, `model_version` |
| `ai_outputs` | Çıktı | `request_id`, `output_encrypted`, `confidence`, `review_status` |
| `ai_feedback` | İnsan feedback'i | `output_id`, `reviewer_id`, `decision`, `correction` |
| `embeddings_index` | RAG index | `tenant_id`, `source_type`, `source_id`, `acl_hash` |
| `model_risk_assessments` | Risk değerlendirme | `feature_code`, `risk`, `mitigations`, `approved_by` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| POST | `/api/v1/ai/assistant/chat` | İK asistanı | MVP/V1 |
| POST | `/api/v1/ai/cv/parse` | CV ayrıştırma | V1 |
| POST | `/api/v1/ai/performance/summary` | Performans özeti | V1 |
| POST | `/api/v1/ai/learning/recommendations` | Eğitim önerisi | V1/V2 |
| POST | `/api/v1/ai/candidates/match` | Aday match | V2 |
| POST | `/api/v1/ai/search` | Semantik arama | V1/V2 |
| POST | `/api/v1/ai/outputs/{id}/review` | İnsan onayı/red | V1 |
| GET | `/api/v1/ai/governance/requests` | AI audit listesi | V1/V2 |

## 9. Yetki, scope ve güvenlik kuralları

- AI çağrısı öncesi normal RBAC/ABAC değerlendirilir.
- Kullanıcının erişemediği veri prompt'a veya RAG context'e girmez.
- Prompt minimizasyonu ve PII masking uygulanır.
- AI output kritik kayıt alanına insan onayı olmadan yazılmaz.
- Model/provider ve veri bölgesi tenant policy'ye bağlanabilir.
- Yasaklı hassas sinyaller skorlamada kullanılmaz.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `ai.request.created` | Feature, actor, model |
| `ai.output.generated` | Confidence, prompt version, token usage |
| `ai.output.reviewed` | Accepted/edited/rejected |
| `ai.rag.source_used` | Source IDs ve ACL hash |
| `ai.model.approved` | Risk assessment |
| `ai.feature.disabled` | Reason ve actor |

Varsayılan karar: Müşteri verisi model training için kullanılmaz. AI sağlayıcı sözleşmesi/DPA ayrı değerlendirilmeli.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| AI çıktısı review bekliyor | Reviewer | In-app |
| Model/prompt değişikliği onay bekliyor | Governance admin | E-posta/in-app |
| Risk batch tamamlandı | HRBP | In-app |
| Düşük güvenli yanıt feedback aldı | Content owner | In-app |

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Prompt redaction ve forbidden attributes |
| Integration | RAG ACL filter |
| E2E | CV parse → recruiter review → aday güncelleme |
| Security | Prompt injection ve cross-tenant embedding engeli |
| AI quality | Hallucination, bias ve confidence eval |

## 13. Kabul kriterleri

- AI çağrıları model, prompt ve veri sınıfıyla audit edilir.
- Yetkisiz doküman RAG bağlamına girmez.
- Aday match tek başına red/hire kararı üretmez.
- Hassas alanlar prompt öncesi maskelenir veya dışlanır.
- AI çıktısı reviewer kararı olmadan kritik kayda yazılmaz.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | AI pazarlaması ürün odağını bozar | AI destekleyici katman olarak konumlanır |
| Risk | Profiling hukuki risk yaratır | HITL, açıklama, rıza ve audit zorunlu |
| Açık soru | İlk AI provider hangisi olacak? | Maliyet, veri bölgesi ve kaliteye göre karar verilecek |

## 15. İlgili dokümanlar

- [Raporlama ve People Analytics Modülü](11-raporlama-people-analytics.md)
- [İşe Alım, ATS ve Aday Portalı Modülü](06-ise-alim-ats-aday-portali.md)
- [Performans, OKR ve 360 Değerlendirme Modülü](07-performans-okr-360.md)
- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
