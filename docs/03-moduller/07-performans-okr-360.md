# Performans, OKR ve 360 Değerlendirme Modülü

Bu doküman, IK Platform'un hedef/OKR, performans döngüsü, manager review, 360 feedback, kalibrasyon ve gelişim aksiyonları kapsamını tanımlar.

## 1. Amaç ve karar özeti

Performans modülü kültürel ve süreçsel olgunluk isteyen bir alandır. Bu yüzden MVP çekirdeğine alınmaz; employee/org/manager verisi oturduktan sonra V1'de temel performans akışları başlatılır.

Karar özeti:

> MVP'de performans modülü yoktur. V1'de hedef ve manager review, V2'de 360, kalibrasyon, AI özet ve gelişim önerileri planlanır.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Hedef/OKR tanımı | MVP çekirdek üründe zorunlu değil |
| Manager review | AI'ın performans kararı vermesi |
| Self-review | Otomatik terfi/işten çıkarma önerisi |
| 360 feedback | Gelişmiş psikometrik test |
| Kalibrasyon | Tam compensation planning |
| Performans sonucu yayınlama | Hukuki performans danışmanlığı |
| AI özet V2 | Gizli ayrımcı veriyle skor üretimi |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `employee` | Kendi hedefini ve değerlendirmesini görür/yazar | Own | Başkasının notunu görmemeli |
| `manager` | Ekip hedefi ve review yapar | Team | Hassas yorumlar korunmalı |
| `hr_specialist` | Döngü ve form operasyonunu yürütür | Tenant/scope | Sonuçları izinsiz değiştirmemeli |
| `hr_director` | Performans stratejisini ve kalibrasyonu izler | Tenant | Adalet ve itiraz süreci yönetilmeli |
| `executive` | Aggregate sonuçları görür | Aggregate | Kişisel skorlar varsayılan görünmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Modül aktif değil; employee, org ve manager ilişkileri performansa hazır tutulur.

### V1

- Hedef tanımı.
- Basit OKR/KPI ilerleme.
- Manager review.
- Self-review.
- Döngü başlatma ve kapanış.
- Sonuç yayınlama.

### V2

- 360 feedback.
- Kalibrasyon board.
- AI performans özeti.
- Yetkinlik bazlı değerlendirme.
- LMS/gelişim önerisi entegrasyonu.

### Enterprise

- Çok kademeli performans onayı.
- Gelişmiş anonimlik ve legal hold.
- Gelişmiş analytics ve audit export.

## 5. Ana kullanıcı akışları

### 5.1 Hedef oluşturma

1. HR veya manager dönem hedef şablonunu açar.
2. Çalışan veya manager hedef girer.
3. Hedef ağırlık ve ölçüm tipi belirlenir.
4. Manager onaylar.
5. Dönem içinde ilerleme güncellenir.

### 5.2 Performans döngüsü

1. HR döngü başlatır.
2. Çalışan self-review doldurur.
3. Manager review yapar.
4. HR tamamlanma durumunu izler.
5. Sonuç yayınlanır.
6. Audit eventleri yazılır.

### 5.3 Kalibrasyon

V2 akışıdır.

1. HRBP kalibrasyon oturumu açar.
2. Manager skorları ve dağılım görüntülenir.
3. Değişiklikler gerekçeli yapılır.
4. Kalibre skor final olur.
5. Çalışana yayınlanır.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| Hedeflerim | Hedef, ağırlık, ilerleme | V1 |
| Ekip Hedefleri | Manager görünümü | V1 |
| Review Formu | Self/manager değerlendirme | V1 |
| Döngü Yönetimi | Kapsam, deadline, tamamlanma | V1 |
| 360 Feedback | Katılımcılar ve anonimlik | V2 |
| Kalibrasyon Board | Dağılım, skor, gerekçe | V2 |
| AI Özet | Kaynak veri ve öneri | V2 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `goal_cycles` | Hedef dönemi | `name`, `period`, `status`, `visibility` |
| `goals` | Hedef kaydı | `owner_id`, `metric_type`, `target_value`, `weight` |
| `performance_cycles` | Değerlendirme dönemi | `start_date`, `end_date`, `status`, `form_template_id` |
| `review_forms` | Review formu | `cycle_id`, `employee_id`, `reviewer_id`, `review_type` |
| `review_responses` | Yanıtlar | `rating`, `comment_encrypted`, `question_id` |
| `calibration_sessions` | Kalibrasyon | `cycle_id`, `department_id`, `status` |
| `calibration_results` | Kalibre sonuç | `manager_score`, `calibrated_score`, `reason` |
| `feedback_requests` | 360 talep | `employee_id`, `reviewer_id`, `anonymous`, `status` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| POST | `/api/v1/goals` | Hedef oluşturma | V1 |
| PATCH | `/api/v1/goals/{id}/progress` | İlerleme güncelleme | V1 |
| POST | `/api/v1/performance/cycles` | Döngü oluşturma | V1 |
| POST | `/api/v1/performance/cycles/{id}/launch` | Döngü başlatma | V1 |
| GET | `/api/v1/performance/reviews` | Review listesi | V1 |
| POST | `/api/v1/performance/reviews/{id}/submit` | Form gönderme | V1 |
| POST | `/api/v1/performance/calibrations` | Kalibrasyon | V2 |
| POST | `/api/v1/performance/{employee_id}/ai-summary` | AI özet | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Employee sadece kendi yayınlanmış sonucunu görür.
- Manager team scope değerlendirmesi yapar.
- HR döngü yönetir ama skor değişiklikleri auditlenir.
- Performans notu ve yorumlar hassas HR verisidir.
- AI özet final karar değildir; manager/HR düzenlemeden yayınlanmaz.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `performance.cycle.launched` | Döngü ve kapsam |
| `review.submitted` | Reviewer ve form |
| `performance.score.changed` | Eski/yeni hash, gerekçe |
| `calibration.completed` | Katılımcılar ve dağılım hash |
| `ai.performance_summary.generated` | Model ve kaynak veri |

Performans yorumları kişisel değerlendirme verisidir; saklama, itiraz ve erişim politikası gerektirir.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Döngü başladı | Çalışan/yönetici | In-app/e-posta |
| Review deadline yaklaştı | Reviewer | E-posta/push |
| Feedback talebi | Reviewer | In-app |
| Sonuç yayınlandı | Çalışan | In-app |

Arka plan işler: deadline reminder, autosave cleanup, AI summary generation, calibration snapshot.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Hedef ağırlık toplamı |
| Unit | Rating scale validasyonu |
| Integration | Cycle launch → review submit → publish |
| Security | Başka çalışanın skorunu görememe |
| AI | Yetkisiz alan AI özetine kaynak olmaz |

## 13. Kabul kriterleri

- Hedef oluşturulabilir ve ilerleme güncellenebilir.
- Review döngüsü başlatılıp tamamlanabilir.
- Performans sonucu yetkisiz kullanıcıya görünmez.
- Skor değişikliği gerekçeli auditlenir.
- AI özeti otomatik final karar üretmez.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Performans modülü kültür gerektirdiği için satışta yanlış vaat olur | V1/V2 fazı açık yazılır |
| Risk | AI performans özeti hukuki risk yaratır | Human-in-loop zorunlu |
| Açık soru | İlk review form şablonu nasıl olacak? | Basit self + manager review önerilir |

## 15. İlgili dokümanlar

- [Organizasyon, Kadro ve Pozisyon Modülü](09-organizasyon-kadro-pozisyon.md)
- [Personalar, JTBD ve Kullanıcı Yolculukları](../02-urun/01-personalar-jtbd-ve-kullanici-yolculuklari.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
