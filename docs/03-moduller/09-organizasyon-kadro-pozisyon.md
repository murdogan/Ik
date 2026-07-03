# Organizasyon, Kadro ve Pozisyon Modülü

Bu doküman, IK Platform'un şirket, şube, departman, pozisyon, yönetici ilişkisi ve kadro planlama temelini tanımlar.

## 1. Amaç ve karar özeti

Organizasyon modülü, çalışan verisini anlamlı hale getiren yapısal katmandır. İzin onayı, manager scope, raporlama, headcount, ileride ATS/kadro talebi ve finans görünürlüğü bu modele dayanır.

Karar özeti:

> MVP'de departman, pozisyon, şube ve yönetici ilişkisi kurulmalıdır. Gelişmiş kadro planlama, bütçe onayı, reorg senaryosu ve workforce planning V1/V2'ye bırakılır.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Legal entity temel kaydı | Çok ülkeli karmaşık grup yapısı |
| Şube/lokasyon | Gelişmiş lokasyon maliyet modeli |
| Departman hiyerarşisi | Reorg simülasyon motoru |
| Pozisyon katalogu | Job architecture tam modeli |
| Yönetici ilişkisi | Matrix org derin model |
| Basit org chart | Büyük ölçekli interaktif workforce planning |
| Employee assignment bağlantısı | Otomatik bütçe optimizasyonu |
| Headcount temel rapor girdisi | Gelişmiş succession planning |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `hr_director` | Org yapısını ve headcount'u izler | Tenant | Yanlış org modeli tüm raporları bozar |
| `hr_specialist` | Departman/pozisyon/yönetici ilişkilerini işler | Scope/tenant | Geçmiş ilişkileri ezmemeli |
| `manager` | Ekibini ve açık pozisyonlarını görür | Team | Diğer ekip bütçesini görmemeli |
| `finance_user` | V1'de kadro bütçe onaylarını izler | Finance scope | Maaş/bütçe alanları korunmalı |
| `tenant_admin` | Org ayarlarını ve katalogları yönetir | Tenant admin | Hatalı silme ilişkileri bozabilir |
| `auditor` | Org değişiklik geçmişini inceler | Read-only | Veri değiştirmemeli |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Legal entity temel bilgisi.
- Şube/lokasyon.
- Departman hiyerarşisi.
- Pozisyon temel kaydı.
- Çalışan-departman-pozisyon-yönetici ilişkisi.
- Basit org chart / ekip görünümü.
- Headcount raporuna veri sağlama.
- Audit eventleri.

### V1

- Kadro talebi.
- Açık/dolu pozisyon takibi.
- Headcount plan vs actual.
- Finance onaylı bütçe alanları.
- ATS pozisyon entegrasyonu.
- Effective-dated org değişiklikleri.

### V2

- Reorg scenario ve publish.
- Matrix org / dotted-line manager.
- Workforce planning analytics.
- Job family, grade ve kariyer mimarisi.

### Enterprise

- Çok şirketli holding yapısı.
- Gelişmiş onay hiyerarşileri.
- Büyük org chart optimizasyonu.
- SIEM/audit export.

## 5. Ana kullanıcı akışları

### 5.1 Departman ve şube oluşturma

1. HR/tenant admin legal entity altında şube oluşturur.
2. Departman adı, üst departman ve statü belirlenir.
3. Sistem hiyerarşi döngüsü olup olmadığını kontrol eder.
4. Değişiklik audit'e yazılır.

### 5.2 Pozisyon oluşturma

1. HR pozisyon kaydı açar.
2. Departman, lokasyon, unvan ve manager ilişkisi belirlenir.
3. V1'de FTE ve bütçe alanları eklenir.
4. Pozisyon employee assignment için kullanılabilir hale gelir.

### 5.3 Çalışanı pozisyona atama

1. HR çalışan kartında pozisyon/departman/yönetici atar.
2. Sistem manager chain'i günceller.
3. İzin onayı ve team scope bu ilişkiye göre çalışır.
4. Headcount raporu güncellenir.

### 5.4 Org chart görüntüleme

1. Kullanıcı yetkisine göre org chart açar.
2. Manager sadece kendi ekibini, HR tenant/scope'u görür.
3. Hassas alanlar gösterilmez.
4. Büyük yapılarda lazy expand kullanılır.

### 5.5 Kadro talebi

V1 akışıdır.

1. Manager yeni pozisyon veya replacement talebi açar.
2. HR ve finance onayına gider.
3. Onaylanan talep ATS requisition'a dönüşebilir.
4. Pozisyon planlı/açık statüye geçer.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| Organizasyon Ayarları | Legal entity, şube, departman | MVP |
| Pozisyon Listesi | Unvan, departman, statü, doluluk | MVP sade |
| Çalışan Assignment | Departman, pozisyon, yönetici | MVP |
| Org Chart | Basit hiyerarşi ve ekip görünümü | MVP |
| Headcount Görünümü | Departman/şube bazlı çalışan sayısı | MVP/V1 |
| Kadro Talebi | Yeni/replacement pozisyon talebi | V1 |
| Reorg Designer | Taslak organizasyon değişikliği | V2 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `legal_entities` | Tüzel kişilik | `name`, `tax_number`, `country`, `status` |
| `branches` | Şube/lokasyon | `legal_entity_id`, `name`, `address`, `timezone` |
| `departments` | Departman hiyerarşisi | `parent_id`, `name`, `code`, `status` |
| `positions` | Pozisyon kaydı | `department_id`, `title`, `manager_position_id`, `status` |
| `employee_assignments` | Çalışan-org ilişkisi | `employee_id`, `department_id`, `position_id`, `manager_id`, `valid_from` |
| `headcount_requests` | Kadro talebi | `requester_id`, `position_id`, `reason`, `status` |
| `workforce_plans` | Kadro planı | `period`, `department_id`, `planned_fte`, `budget` |
| `reorg_scenarios` | Reorg taslağı | `name`, `status`, `created_by`, `published_at` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/legal-entities` | Tüzel kişilik listesi | MVP |
| GET | `/api/v1/branches` | Şube listesi | MVP |
| GET | `/api/v1/departments` | Departman listesi | MVP |
| POST | `/api/v1/departments` | Departman oluşturma | MVP |
| GET | `/api/v1/positions` | Pozisyon listesi | MVP |
| POST | `/api/v1/positions` | Pozisyon oluşturma | MVP |
| GET | `/api/v1/org-chart` | Org chart | MVP |
| POST | `/api/v1/employee-assignments` | Çalışan ataması | MVP |
| POST | `/api/v1/headcount-requests` | Kadro talebi | V1 |
| POST | `/api/v1/reorg-scenarios` | Reorg taslağı | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Manager team scope dışındaki employee assignment detaylarını görmez.
- Finance budget alanlarını görür; kişisel hassas alanları görmez.
- HR kendi scope'undaki org yapısını yönetebilir.
- Org değişiklikleri izin/onay akışlarını etkilediği için audit zorunludur.
- Geçmiş tarihli assignment değişikliği gerekçe istemelidir.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `department.created` | Departman oluşturan ve parent |
| `position.created` | Pozisyon detayları |
| `employee.assignment.changed` | Eski/yeni departman, pozisyon, manager |
| `reporting_line.changed` | Yönetici ilişkisi değişimi |
| `headcount_request.approved` | Onaylayan ve budget bilgisi |
| `reorg.published` | Senaryo diff özeti |

Org verisi doğrudan özel nitelikli veri değildir; ancak çalışan ilişkileri ve yönetici hiyerarşisi kişisel iş verisidir. Scope kontrolü zorunludur.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Yönetici değişti | Etkilenen çalışan/yönetici | In-app/e-posta |
| Kadro talebi açıldı | HR/Finance | In-app |
| Pozisyon boşaldı | HR/Recruiter | In-app |
| Reorg yayınlandı | Etkilenen yöneticiler | E-posta/in-app |

Arka plan işler: org chart cache yenileme, headcount snapshot, effective-dated assignment aktivasyonu.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Departman hiyerarşi döngüsü engeli |
| Unit | FTE kapasite validasyonu |
| Integration | Çalışan assignment değişince manager scope güncellenir |
| Integration | Pozisyon → ATS requisition V1 entegrasyonu |
| E2E | HR departman/pozisyon oluşturur, çalışan atar |
| Security | Manager başka ekibin org detayını göremez |
| Performance | Büyük org chart lazy loading |

## 13. Kabul kriterleri

- Departman ve pozisyon oluşturulabilir.
- Çalışan departman/pozisyon/yöneticiye atanabilir.
- Manager scope bu atamaya göre çalışır.
- Basit org chart üretilebilir.
- Headcount departman/şube bazında raporlanabilir.
- Org değişiklikleri audit'e düşer.
- Yetkisiz kullanıcı budget/hassas alanları göremez.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Org modeli fazla enterprise başlarsa MVP ağırlaşır | Departman/pozisyon/manager ile başla |
| Risk | Geçmiş atamalar ezilirse raporlar bozulur | V1'de effective dating güçlendirilmeli |
| Risk | Matrix org erken alınırsa karmaşa artar | V2'ye bırakılır |
| Açık soru | İlk MVP'de legal entity zorunlu mu? | Tek default legal entity ile başlanabilir |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [Personel, Özlük ve Doküman Yönetimi Modülü](02-personel-ozluk-dokuman.md)
- [İzin, Devamsızlık ve Onay Modülü](03-izin-devamsizlik-onay.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
