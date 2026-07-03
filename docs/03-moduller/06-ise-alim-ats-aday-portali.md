# İşe Alım, ATS ve Aday Portalı Modülü

Bu doküman, IK Platform'un işe alım talebi, ilan, aday başvurusu, aday pipeline'ı, mülakat, teklif ve onboarding'e geçiş kapsamını tanımlar.

## 1. Amaç ve karar özeti

ATS modülü ürün için değerlidir fakat MVP çekirdeği değildir. İlk ürün personel, izin, belge ve self-servis değerini ispatladıktan sonra V1'de işe alım akışına genişlemelidir.

Karar özeti:

> ATS MVP kapsamına alınmaz. V1'de requisition, kariyer sitesi, aday başvurusu, pipeline, mülakat ve teklif akışları gelir. AI CV ayrıştırma ve match score ancak rıza, açıklanabilirlik ve insan onayıyla V2'de güçlenir.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| İşe alım talebi | MVP çekirdek üründe zorunlu değil |
| İlan ve kariyer sitesi | Tüm job board marketplace ilk sürüm |
| Aday başvurusu | Otomatik işe alım kararı |
| Aday pipeline | AI'ın tek başına eleme yapması |
| Mülakat planlama | Gelişmiş background check |
| Teklif onayı | Tüm ülkelerde işe alım mevzuatı |
| Aday rıza ve saklama | Sosyal medya scraping |
| Candidate → employee dönüşümü | Otomatik SGK/e-devlet entegrasyonu |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `recruiter` | İlan, aday, pipeline, mülakat ve teklif yönetir | Tenant/scope | Aday verisini gereksiz paylaşmamalı |
| `manager` | Pozisyon talebi ve aday değerlendirmesi yapar | Hiring team | Tüm aday havuzunu görmemeli |
| `hr_director` | Süreç, şablon ve raporları yönetir | Tenant | Yanlış saklama politikası KVKK riski yaratır |
| `finance_user` | Teklif/bütçe onayı verir | Finance scope | Aday özel notlarına erişmemeli |
| `candidate` | Başvuru yapar, rıza verir, durum takip eder | Own | Başka aday verisine erişmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- ATS yok; employee onboarding için veri modeli hazırlığı yapılır.

### V1

- İşe alım talebi.
- Kariyer sitesi ve public ilan listesi.
- Aday başvuru formu.
- Aday pipeline.
- Mülakat planlama.
- Teklif onay akışı.
- Candidate → pre-hire employee dönüşümü.
- Aday rıza ve retention takibi.

### V2

- AI CV ayrıştırma.
- Match score ve açıklama.
- Job board entegrasyonları.
- Aday havuzu önerileri.
- Advanced recruitment analytics.

### Enterprise

- Çok marka/çok ülke kariyer sitesi.
- Background check entegrasyonu.
- Gelişmiş approval ve compliance.

## 5. Ana kullanıcı akışları

### 5.1 İşe alım talebi

1. Manager yeni veya replacement pozisyon talebi açar.
2. HR ve gerekirse finance onayı alır.
3. Onaylanan talep job requisition olur.
4. Recruiter ilan hazırlığına geçer.

### 5.2 Aday başvurusu

1. Aday public kariyer sitesinde ilanı açar.
2. Formu doldurur ve CV yükler.
3. Aydınlatma/rıza akışını tamamlar.
4. Başvuru pipeline'a düşer.
5. Adaya başvuru alındı bildirimi gider.

### 5.3 Mülakat ve teklif

1. Recruiter adayı mülakata taşır.
2. Manager/hiring team değerlendirme yapar.
3. Teklif taslağı hazırlanır.
4. Bütçe dışı teklif finance onayına gider.
5. Aday kabul ederse pre-hire employee kaydı oluşur.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| Requisition Board | Talep, onay, pozisyon, bütçe | V1 |
| Kariyer Sitesi | Public ilanlar ve başvuru | V1 |
| Aday Pipeline | Kanban, stage, filtre, source | V1 |
| Aday Profili | CV, rıza, notlar, mülakat | V1 |
| Mülakat Planlama | Takvim ve feedback | V1 |
| Teklif Merkezi | Maaş bandı, onay, aday durumu | V1 |
| AI Match | Skor ve açıklama | V2 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `job_requisitions` | İşe alım talebi | `position_id`, `department_id`, `budget_range`, `status` |
| `job_postings` | Public ilan | `slug`, `language`, `published_at`, `expires_at` |
| `candidates` | Aday ana kaydı | `name`, `email_encrypted`, `phone_encrypted`, `consent_status` |
| `candidate_applications` | Başvuru | `candidate_id`, `posting_id`, `stage`, `status` |
| `candidate_documents` | CV ve ek belge | `storage_key`, `sha256`, `parsed_json` |
| `interviews` | Mülakat | `application_id`, `interviewer_id`, `scheduled_at`, `status` |
| `offers` | Teklif | `salary_offer_encrypted`, `status`, `expires_at` |
| `candidate_consents` | Rıza kayıtları | `purpose`, `version`, `given_at`, `expires_at` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| POST | `/api/v1/requisitions` | İşe alım talebi | V1 |
| POST | `/api/v1/requisitions/{id}/approve` | Talep onayı | V1 |
| POST | `/api/v1/job-postings` | İlan oluşturma | V1 |
| GET | `/api/v1/careers/{tenant_slug}/jobs` | Public ilan listesi | V1 |
| POST | `/api/v1/careers/{tenant_slug}/jobs/{id}/apply` | Başvuru | V1 |
| GET | `/api/v1/candidates` | Aday arama | V1 |
| POST | `/api/v1/interviews` | Mülakat planlama | V1 |
| POST | `/api/v1/offers` | Teklif oluşturma | V1 |
| POST | `/api/v1/applications/{id}/hire` | Employee dönüşümü | V1/V2 |
| POST | `/api/v1/candidates/{id}/parse-cv` | AI/parser | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Candidate sadece kendi portal verisini görür.
- Hiring manager yalnız ilgili requisition adaylarını görür.
- Teklif maaşı field-level permission ister.
- AI parse/match rıza olmadan çalışmaz.
- Aday notları ve mülakat değerlendirmeleri sınırlı erişim ister.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `candidate.created` | Kaynak ve rıza durumu |
| `candidate.consent.given` | Purpose ve versiyon |
| `application.stage_changed` | Eski/yeni stage |
| `interview.feedback_submitted` | Reviewer ve zaman |
| `offer.approved` | Onaylayan ve hash |
| `candidate.cv_parsed` | Model/parser versiyonu |

Aday verisi retention politikasına bağlı silinmeli veya anonimleştirilmelidir.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Yeni başvuru | Recruiter | In-app/e-posta |
| Mülakat daveti | Aday/interviewer | E-posta/takvim |
| Feedback bekliyor | Interviewer | In-app/e-posta |
| Teklif gönderildi | Aday | E-posta/portal |
| Rıza süresi doluyor | HR | In-app |

Arka plan işler: retention job, CV parse job, reminder job, duplicate candidate detection.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Stage transition ve consent expiry |
| Integration | Başvuru → pipeline → mülakat |
| E2E | Requisition → ilan → aday → teklif → hire |
| Security | Public career endpoint tenant isolation |
| AI | Rıza yokken AI çağrısı engellenir |

## 13. Kabul kriterleri

- Public ilan listesi tenant bazlı çalışır.
- Aday rızası kaydedilmeden AI işleme yapılmaz.
- Aday pipeline stage değişiklikleri auditlenir.
- Teklif maaşı yetkisiz kullanıcıya görünmez.
- Candidate employee'ye dönüşürken duplicate oluşmaz.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | ATS erken alınırsa MVP odağı dağılır | V1'e bırakılır |
| Risk | AI skor ayrımcılık riski yaratır | Human-in-loop ve açıklama zorunlu |
| Açık soru | İlk kariyer sitesi özelleştirme seviyesi ne olacak? | Basit tema + ilan listesi önerilir |

## 15. İlgili dokümanlar

- [Organizasyon, Kadro ve Pozisyon Modülü](09-organizasyon-kadro-pozisyon.md)
- [Personel, Özlük ve Doküman Yönetimi Modülü](02-personel-ozluk-dokuman.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
