# Eğitim, Yetkinlik ve Kariyer Modülü

Bu doküman, IK Platform'un eğitim katalogu, sertifika, yetkinlik matrisi, gelişim planı, kariyer yolu ve succession planning kapsamını tanımlar.

## 1. Amaç ve karar özeti

Eğitim ve gelişim modülü, çekirdek İK operasyonu oturduktan sonra çalışan gelişimi ve yetenek yönetimi katmanını kurar. MVP'de zorunlu değildir; V2 odaklı bir platform derinleşme alanıdır.

Karar özeti:

> MVP'de LMS yoktur; yalnızca belge/sertifika takibi DOC içinde sınırlı tutulabilir. V1'de eğitim katalogu ve gelişim planı, V2'de yetkinlik, kariyer yolu, succession ve AI eğitim önerileri gelir.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Eğitim katalogu | Tam içerik üretim platformu |
| Eğitim atama ve tamamlama | SCORM player ilk sürüm zorunluluğu |
| Sertifika ve geçerlilik | Üniversite LMS alternatifi olmak |
| Yetkinlik matrisi | Psikometrik test ürünü |
| Gelişim planı | Otomatik terfi kararı |
| Kariyer yolu | Tam compensation planning |
| Succession planning | Hukuki performans/terfi danışmanlığı |
| AI eğitim önerisi | AI'ın terfi kararı vermesi |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `employee` | Eğitim alır, sertifika görür, gelişim planını takip eder | Own | Başkasının gelişim verisini görmemeli |
| `manager` | Ekip eğitim ve gelişim durumunu izler | Team | Potansiyel/succession verisi sınırlı olmalı |
| `hr_specialist` | Eğitim katalogu ve atamaları yönetir | Tenant/scope | Yanlış hedefleme operasyon yükü yaratır |
| `hr_director` | Yetkinlik ve succession stratejisini izler | Tenant | Hassas kariyer verisi korunmalı |
| `trainer` | Eğitim oturumu ve katılımı yönetir | Course scope | HR verisine geniş erişmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- LMS yok.
- Sertifika/belge takibi DOC modülü içinde sınırlı tutulabilir.

### V1

- Eğitim katalogu.
- Eğitim atama ve tamamlama.
- Sertifika geçerlilik takibi.
- Gelişim planı temel.

### V2

- Yetkinlik matrisi.
- Rol-yetkinlik gap analizi.
- Kariyer yolu.
- Succession planning.
- AI eğitim önerisi.

### Enterprise

- Harici LMS entegrasyonları.
- SCORM/xAPI.
- Kritik rol yedekleme dashboard'u.
- Gelişmiş audit/field permission.

## 5. Ana kullanıcı akışları

### 5.1 Eğitim atama

1. HR eğitim oluşturur.
2. Hedef kitle rol/departman/şube bazında seçilir.
3. Eğitim çalışanlara atanır.
4. Çalışan tamamlar veya kanıt yükler.
5. Sertifika ve tamamlama durumu kaydedilir.

### 5.2 Sertifika takibi

1. Sertifika çalışan kaydına bağlanır.
2. Geçerlilik tarihi girilir.
3. Süre yaklaşınca çalışan ve manager bilgilendirilir.
4. Yenileme kanıtı yüklenir.

### 5.3 Kariyer ve yetkinlik gap

V2 akışıdır.

1. Çalışan hedef rol seçer.
2. Sistem mevcut yetkinlikleri hedef rol gereksinimiyle karşılaştırır.
3. Gap listesi ve önerilen eğitimler çıkar.
4. Manager gelişim planını onaylar.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| Eğitim Katalogu | Eğitimler, filtre, kayıt | V1 |
| Eğitimlerim | Atanan/tamamlanan eğitimler | V1 |
| Sertifikalar | Geçerlilik, kanıt, yenileme | V1 |
| Gelişim Planı | Aksiyon, hedef tarih, yorum | V1 |
| Yetkinlik Matrisi | Rol gereksinimi ve seviye | V2 |
| Kariyer Yolu | Hedef rol, gap, eğitim önerisi | V2 |
| Succession Board | Kritik pozisyon ve yedek | V2/Enterprise |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `learning_courses` | Eğitim katalogu | `title`, `type`, `provider`, `mandatory` |
| `learning_enrollments` | Eğitim atama | `employee_id`, `course_id`, `status`, `completed_at` |
| `certifications` | Sertifika | `employee_id`, `name`, `issued_at`, `expires_at`, `storage_key` |
| `competencies` | Yetkinlik | `code`, `name`, `category`, `description` |
| `role_competencies` | Rol gereksinimi | `job_id`, `competency_id`, `required_level` |
| `employee_competencies` | Çalışan seviyesi | `employee_id`, `competency_id`, `level`, `evidence` |
| `development_plans` | Gelişim planı | `employee_id`, `goal`, `actions`, `status` |
| `succession_plans` | Yedekleme | `position_id`, `criticality`, `risk_level`, `owner_id` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/learning/courses` | Eğitim katalogu | V1 |
| POST | `/api/v1/learning/courses` | Eğitim oluşturma | V1 |
| POST | `/api/v1/learning/enrollments` | Eğitim atama | V1 |
| POST | `/api/v1/learning/enrollments/{id}/complete` | Tamamlama | V1 |
| GET | `/api/v1/competencies` | Yetkinlik listesi | V2 |
| PATCH | `/api/v1/employees/{id}/competencies` | Yetkinlik güncelleme | V2 |
| POST | `/api/v1/development-plans` | Gelişim planı | V1/V2 |
| POST | `/api/v1/succession/plans` | Succession plan | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Employee kendi eğitim ve sertifikalarını görür.
- Manager team scope eğitim/gelişim durumunu görür.
- Succession ve potansiyel skorları sıkı field permission ister.
- Eğitim skoru kişisel performans verisi gibi korunmalıdır.
- AI önerileri karar değil tavsiye olarak etiketlenmelidir.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `learning.assigned` | Eğitim ve hedef kitle |
| `learning.completed` | Skor, kanıt, zaman |
| `certification.expiring` | Sertifika ve tarih |
| `competency.updated` | Eski/yeni seviye |
| `succession_candidate.added` | Pozisyon ve actor |

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Eğitim atandı | Çalışan | In-app/e-posta/push |
| Sertifika süresi yaklaşıyor | Çalışan/manager | In-app/e-posta |
| Gelişim planı onay bekliyor | Manager | In-app |
| Kritik pozisyon yedeksiz | HR | In-app/e-posta |

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Sertifika expiry hesabı |
| Unit | Yetkinlik gap hesabı |
| Integration | Eğitim atama → tamamlama → sertifika |
| Security | Succession verisine yetkisiz erişim |
| AI | Önerinin yasaklı alan kullanmaması |

## 13. Kabul kriterleri

- Eğitim katalogu oluşturulabilir.
- Çalışana eğitim atanıp tamamlandı işaretlenebilir.
- Sertifika geçerlilik bildirimi üretilebilir.
- Yetkinlik gap analizi hedef rol ile tutarlı çalışır.
- Succession verisi sadece yetkili rollerde görünür.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | LMS erken alınırsa MVP dağılır | V1/V2'ye bırakılır |
| Risk | Succession hassas veridir | Field permission ve audit zorunlu |
| Açık soru | İlk LMS entegrasyonu gerekli mi? | Pilot ihtiyacına göre V2 |

## 15. İlgili dokümanlar

- [Performans, OKR ve 360 Değerlendirme Modülü](07-performans-okr-360.md)
- [AI Özellikleri ve Governance Modülü](12-ai-ozellikleri-ve-governance.md)
- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
