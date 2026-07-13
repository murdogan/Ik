# Organizasyon, Kadro ve Pozisyon Modülü

Bu doküman, IK Platform'un şirket, şube, departman, pozisyon, yönetici ilişkisi ve kadro planlama temelini tanımlar.

## 1. Amaç ve karar özeti

Organizasyon modülü, çalışan verisini anlamlı hale getiren yapısal katmandır. İzin onayı, manager scope, raporlama, headcount, ileride ATS/kadro talebi ve finans görünürlüğü bu modele dayanır.

Karar özeti:

> MVP'de departman, pozisyon, şube ve yönetici ilişkisi kurulmalıdır. Gelişmiş kadro planlama, bütçe onayı, reorg senaryosu ve workforce planning V1/V2'ye bırakılır.

Current Phase 3 / P3K durumu: P3F–P3J legal entity ve branch/lokasyon yönetimini,
concurrency-safe departman hiyerarşisini, reusable position/job-title katalogunu, effective-dated
employee assignment history'sini, assignment'tan türetilen manager team scope'u ve bounded lazy org
chart'ı backend ile manuel kullanılabilir tek `/organization` workspace'inde tamamlar. P3K bu
ürün modelini güvenlik/migration/query gate'lerinden geçirir; Phase 4 Employee 360, headcount
planning, payroll veya başka modül başlatmaz.

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
| Mevcut assignment'lardan gelecekte headcount raporu üretmeye uygun veri | Headcount plan/bütçe, succession planning ve workforce planning |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `hr_director` | Org yapısını ve structured assignment'ları yönetir | Tenant | Yanlış org modeli sonraki raporları bozar |
| `hr_specialist` | Departman/pozisyon/yönetici ilişkilerini işler | Scope/tenant | Geçmiş ilişkileri ezmemeli |
| `manager` | Structured assignment'tan türetilen direct ekibini görür | Team | Başka ekip assignment'ını görmemeli |
| `tenant_admin` | Org ayarlarını ve katalogları yönetir | Tenant admin | Hatalı silme ilişkileri bozabilir |
| `auditor` | Org değişiklik geçmişini inceler | Read-only | Veri değiştirmemeli |

`finance_user` ve bütçe/FTE authority'si sonraki workforce/payroll fazındadır; mevcut seeded
Phase 3 rol katalogunda yoktur. `auditor` organization read alır fakat update/assignment mutation
almaz. Manager'ın team read yetkisi tenant-wide assignment yönetimi anlamına gelmez.

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Legal entity temel bilgisi.
- Şube/lokasyon.
- Departman hiyerarşisi.
- Pozisyon temel kaydı.
- Çalışan-departman-pozisyon-yönetici ilişkisi.
- Effective-dated immutable assignment history ve legacy string compatibility projection.
- Basit org chart / ekip görünümü.
- Audit eventleri.

### V1

- Kadro talebi.
- Açık/dolu pozisyon takibi.
- Finance onaylı bütçe alanları.
- ATS pozisyon entegrasyonu.
- Headcount plan vs actual ve bütçe/FTE modeli.

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

1. HR/tenant admin aktif legal entity altında stable kod, ad, IANA timezone ve allowlisted
   lokasyon alanlarıyla şube oluşturur.
2. Departman stable kod/ad ve optional aktif parent ile active olarak oluşur; status caller
   tarafından seçilmez, archive ayrı terminal aksiyondur.
3. Sistem hiyerarşi döngüsü olup olmadığını kontrol eder.
4. Değişiklik audit'e yazılır.

### 5.2 Pozisyon oluşturma

1. HR pozisyon kaydı açar.
2. Stable tenant-wide kod ve reusable iş unvanı belirlenir; katalog kaydı departman, lokasyon,
   manager, FTE veya bütçe taşımaz.
3. Aktif pozisyon employee assignment'ta legal entity/branch/department ile birlikte seçilebilir.
4. Unvan güncellenebilir, kod immutable'dır. Archive fiziksel silmez; tarihsel assignment etiketi
   okunur, yeni assignment kapanır.

### 5.3 Çalışanı pozisyona atama

1. Yetkili HR organization workspace'te employee, legal entity, branch, department, position,
   optional manager ve `effective_from` seçerek ilk structured assignment'ı oluşturur.
2. Değişiklikte açık assignment satırı exclusive boundary'de kapanır; change reason ile immutable
   successor eklenir. Tarihçe overwrite edilmez.
3. Tüm referanslar current tenant'a ve aktif/atanabilir state'e ait olmalıdır. Manager aktif user
   ve `employee:read:team` capability sahibi olmalıdır.
4. `/api/v1/teams/me` doğrudan ekibi yalnız bugün yürürlükteki `manager_user_id` bağından
   türetir; legacy department/position text'i scope genişletmez.

### 5.4 Org chart görüntüleme

1. `organization:read:tenant` sahibi tenant admin/HR/auditor organization workspace'te root
   reporting seviyesini açar.
2. Her node resolved legal entity/branch/department/position etiketleri ve `has_children` ipucu
   taşır; child yalnız kullanıcı expand ettiğinde `parent_id` ile istenir.
3. Her istek tek seviye, bounded `limit` ve o parent'a bağlı opaque cursor kullanır; full tenant
   recursive payload ve node başına lookup yoktur.
4. Manager rolü organization-wide chart authority almaz; kendi derived direct team'i dashboard'da
   `/api/v1/teams/me` ile görür.

### 5.5 Kadro talebi

V1 akışıdır.

1. Manager yeni pozisyon veya replacement talebi açar.
2. HR ve finance onayına gider.
3. Onaylanan talep ATS requisition'a dönüşebilir.
4. Pozisyon planlı/açık statüye geçer.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| Organization Workspace | Tüzel kişilik/şube, departman, pozisyon, assignment ve chart anchor'ları | P3J uygulandı |
| Tüzel Kişilik ve Şubeler | Typed ayarlar, cursor listeleri, create/update/archive | P3F uygulandı |
| Departman Hiyerarşisi | Lazy root/child tree, create/rename/move/archive ve history | P3G uygulandı |
| Pozisyon Katalogu | Stable kod, unvan, active/archive ve bounded search | P3H uygulandı |
| Çalışan Assignment | Server-side employee search, create/change/history pagination | P3I uygulandı |
| Org Chart | Bounded root/direct-report lazy expand, resolved organization labels | P3J uygulandı |
| Manager Team | Dashboard'da authenticated manager'ın direct structured ekibi | P3I uygulandı |
| Headcount Görünümü | Structured assignment'tan rapor/plan/bütçe | V1 planı |
| Kadro Talebi | Yeni/replacement pozisyon talebi | V1 |
| Reorg Designer | Taslak organizasyon değişikliği | V2 |

### 6.1 Local demo organization verisi

Deterministik local/dev seed iki tenant, beş user, sekiz employee ve mevcut leave fixture'larını
korur; buna ek olarak her tenant için organization feature'ı açar, tek aktif default legal entity,
bir aktif demo branch, legacy employee etiketlerinden normalized department/position katalogları ve
employee başına structured assignment oluşturur. Her assignment tenant'ın seeded manager user'ına
bağlıdır; bu nedenle manager team ve lazy chart manuel demoda boş bir mock değil persisted
ilişkiyi gösterir.

Seed ikinci çalıştırmada var olan assignment history'sini overwrite etmez. Aynı normalized demo
department/position'ı case-insensitive yeniden kullanır, stable UUID/kod üretir ve ambiguous
conflict'te fail eder. Shared `admin@wealthyfalcon.demo` identity'si iki tenant membership'i ve
ayrı `super_admin` platform role projection'ı alır; Wealthy Falcon tarafında tenant admin + HR
specialist rolleriyle assignment mutation happy path'ini de kullanabilir. `--auth-demo` yalnız
local/dev hedefte `wf_admin` ve `wf_manager` için iki etiketli tek-kullanımlı activation URL üretir;
plaintext/default parola yazmaz. Admin aktivasyonu multi-org + ayrı platform demo credential'ını,
manager aktivasyonu derived-team demo credential'ını kurar.

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `legal_entities` | Tüzel kişilik | tenant, stable normalized `code`, name/registered name, country/tax/timezone, `active|inactive`, tek default |
| `branches` | Şube/lokasyon ve retained history | composite legal entity FK, stable normalized code, name/timezone/location, `active|archived`, `archived_at` |
| `department_hierarchy_write_fences` | Tenant graph write serialization | tenant PK, monotonic `version` |
| `departments` | Cycle-safe adjacency-list hiyerarşisi | composite `parent_id`, stable normalized code, name, `active|archived`, `archived_at` |
| `positions` | Reusable tenant job-title katalogu | stable normalized `code`, normalized title, `active|archived`; department/manager/FTE FK'si yok |
| `employee_assignments` | Immutable çalışan-org/reporting aralığı | composite employee/legal entity/branch/department/position/manager FKs, `effective_from`, exclusive `effective_to`, supersedes, reason, actor |
| `headcount_requests`, `workforce_plans`, `reorg_scenarios` | Kadro/bütçe/reorg | V1/V2 planı; Phase 3 tablosu değil |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/legal-entities` | Tüzel kişilik listesi | MVP |
| POST | `/api/v1/legal-entities` | Aktif tüzel kişilik oluşturma | MVP |
| GET/PATCH | `/api/v1/legal-entities/{legal_entity_id}` | Detay ve allowlisted ayar güncelleme | MVP |
| GET | `/api/v1/branches` | Şube listesi | MVP |
| POST | `/api/v1/branches` | Aktif tüzel kişilik altında şube oluşturma | MVP |
| GET/PATCH/DELETE | `/api/v1/branches/{branch_id}` | Detay, active-only update, terminal archive | MVP |
| GET | `/api/v1/departments` | Departman listesi | MVP |
| POST | `/api/v1/departments` | Departman oluşturma | MVP |
| GET | `/api/v1/departments/tree` | Tek bounded root/direct-child seviyesi | MVP |
| GET/PATCH/DELETE | `/api/v1/departments/{department_id}` | Detay, safe rename/move, terminal archive | MVP |
| GET | `/api/v1/positions` | Pozisyon listesi | MVP |
| POST | `/api/v1/positions` | Pozisyon oluşturma | MVP |
| GET/PATCH/DELETE | `/api/v1/positions/{position_id}` | Detay, active-only unvan update, terminal archive | MVP |
| GET | `/api/v1/org-chart` | Bounded lazy root/direct-report seviyesi | MVP |
| GET | `/api/v1/employee-assignments` | Current/history assignment cursor listesi | MVP |
| GET | `/api/v1/employee-assignments/options` | Bounded employee/manager form seçenekleri | MVP |
| POST | `/api/v1/employee-assignments` | Çalışan ataması | MVP |
| GET/PATCH | `/api/v1/employee-assignments/{assignment_id}` | Tarihsel detay ve immutable successor change | MVP |
| GET | `/api/v1/teams/me` | Authenticated manager direct team | MVP |
| POST | `/api/v1/headcount-requests` | Kadro talebi | V1 |
| POST | `/api/v1/reorg-scenarios` | Reorg taslağı | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Organization list/detail/chart `organization:read:tenant`; create/update/archive
  `organization:update:tenant` ister. Read permission mutation authority değildir ve manager bu
  permission'ları varsayılan almaz.
- Assignment list/detail `employee:read:tenant`, create/options/change `employee:update:tenant`
  ister. Cross-tenant ve missing ID aynı not-found sınırındadır.
- Manager `/teams/me` için `employee:read:team` ister ve sadece kendi user ID'sine bağlı,
  bugün effective active employee assignment'larını görür. Department/position ad benzerliği,
  legacy string veya caller manager ID'si scope vermez.
- Tenant-owned her organization tablosu composite FK ve PostgreSQL FORCE RLS ile korunur.
  Platform capability'si HR organization tablolarını keyfi okuyup değiştiremez; yalnız tenant
  provisioning için dar default legal-entity INSERT policy'si vardır.
- Inactive legal entity ile archived branch/department/position yeni assignment'ta reddedilir
  fakat tarihsel referans silinmez. Branch/department/position stable code'u archive sonrası yeniden
  kullanılmaz.
- Department cycle service check'ine ek olarak PostgreSQL tenant write fence ve deferred trigger
  ile same-statement/concurrent transaction seviyesinde reddedilir.
- İlk assignment reason optional'dır; her assignment change non-empty reason ister. Assignment ve
  reporting-line audit'i domain write ile aynı transaction'da commit/rollback eder.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `department.created` | Departman oluşturan ve parent |
| `department.updated` / `department.archived` | Rename/move veya terminal archive changed fields |
| `position.created` | Pozisyon detayları |
| `position.updated` / `position.archived` | Unvan veya terminal archive |
| `legal_entity.created` / `legal_entity.updated` | Tüzel kişilik allowlisted değişikliği |
| `branch.created` / `branch.updated` / `branch.archived` | Şube/lokasyon lifecycle |
| `employee.assignment.changed` | Eski/yeni departman, pozisyon, manager |
| `reporting_line.changed` | Yönetici ilişkisi değişimi |
| `headcount_request.approved`, `reorg.published` | V1/V2 planı; Phase 3 event'i değil |

Org verisi doğrudan özel nitelikli veri değildir; ancak çalışan ilişkileri ve yönetici hiyerarşisi kişisel iş verisidir. Scope kontrolü zorunludur.

## 11. Bildirimler ve arka plan işler

Aşağıdaki bildirimler sonraki notification dilimi planıdır; Phase 3 organization command'ları
henüz e-posta/in-app delivery job'ı çalıştırmaz.

| Olay | Alıcı | Kanal |
|---|---|---|
| Yönetici değişti | Etkilenen çalışan/yönetici | In-app/e-posta |
| Kadro talebi açıldı | HR/Finance | In-app |
| Pozisyon boşaldı | HR/Recruiter | In-app |
| Reorg yayınlandı | Etkilenen yöneticiler | E-posta/in-app |

Phase 3 org chart doğrudan bounded sorgu kullanır; cache refresh, headcount snapshot veya
effective-dated activation worker'ı yoktur. Assignment etkinliği request tarihindeki
`effective_from <= today < effective_to` predicate'iyle türetilir. Bu arka plan işleri ihtiyaç ve
ölçüm doğrulanırsa sonraki fazda eklenir.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Departman hiyerarşi döngüsü engeli |
| Integration | Çalışan assignment değişince manager scope güncellenir |
| Integration/PostgreSQL | Same-statement ve concurrent departman cycle trigger/fence ile reddedilir |
| Integration/PostgreSQL | RLS/ACL, composite FK, archived-reference ve immutable assignment history |
| E2E | HR departman/pozisyon oluşturur, çalışan atar |
| Security | Manager başka ekibin org detayını göremez |
| Security | Platform capability HR tablolarını okuyamaz; tenant A, tenant B organization kayıtlarına erişemez |
| Performance | Department tree, position search, assignment/team ve org chart bounded/indexed query planı |

## 13. Kabul kriterleri

- Departman ve pozisyon oluşturulabilir.
- Çalışan departman/pozisyon/yöneticiye atanabilir.
- Manager scope bu atamaya göre çalışır.
- Basit org chart üretilebilir.
- Structured assignment gelecekteki headcount raporuna kaynak olabilir; Phase 3 headcount
  plan/bütçe ürünü iddiasında bulunmaz.
- Org değişiklikleri audit'e düşer.
- Phase 3 response'ları bütçe/maaş/TCKN gibi alanlar içermez; sonraki fazda eklenirse ayrı field
  permission gate'i gerekir.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Org modeli fazla enterprise başlarsa MVP ağırlaşır | Departman/pozisyon/manager ile başla |
| Risk | Geçmiş atamalar ezilirse raporlar bozulur | Phase 3 immutable successor ve exclusive interval ile history'yi korur |
| Risk | Matrix org erken alınırsa karmaşa artar | V2'ye bırakılır |
| Karar | İlk MVP'de legal entity zorunlu mu? | Evet; basit tenant için tek aktif default legal entity backfill/provision edilir |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [Personel, Özlük ve Doküman Yönetimi Modülü](02-personel-ozluk-dokuman.md)
- [İzin, Devamsızlık ve Onay Modülü](03-izin-devamsizlik-onay.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
