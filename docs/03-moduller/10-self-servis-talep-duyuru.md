# Self-Servis, Talep, Onay ve Duyuru Modülü

Bu doküman, çalışan ve yöneticilerin günlük İK işlemlerini tek merkezden başlatmasını, takip etmesini ve onaylamasını sağlayan self-servis katmanını tanımlar.

## 1. Amaç ve karar özeti

Self-servis modülü, IK Platform'un sadece İK ekibinin kullandığı bir kayıt sistemi olmasını engeller. Çalışan ve yönetici ürüne dahil olmazsa İK operasyon yükü gerçek anlamda azalmaz.

Karar özeti:

> MVP'de çalışan portalı, yönetici onay kuyruğu, temel talep durumu, duyuru ve bildirim altyapısı çalışmalıdır. Gelişmiş workflow designer, delegasyon ve SLA yönetimi V1'e bırakılır.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Çalışan ana sayfası | Tam no-code form builder |
| Kendi profil/izin/belge özetleri | Marketplace talep formları |
| Temel talep durumu | Karmaşık paralel onay akışları |
| Yönetici onay kuyruğu | Gelişmiş delegasyon motoru |
| Duyuru okuma | Teams/Slack action button entegrasyonu |
| Basit duyuru yayınlama | Gelişmiş kampanya/iletişim ürünü |
| In-app bildirim | Tam notification preference center |
| Temel audit | Gelişmiş SLA/escalation motoru |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `employee` | Taleplerini başlatır, durumunu takip eder, duyuru okur | Own | Başkasının talebini görmemeli |
| `manager` | Ekip taleplerini/onaylarını yönetir | Team | Bağlamsız onay vermemeli |
| `hr_specialist` | Talep tiplerini ve gelen talepleri izler | Tenant/scope | Her talebi manuel çözmek zorunda kalmamalı |
| `hr_director` | Duyuru, talep yükü ve SLA raporlarını izler | Tenant | Aşırı bildirimle çalışanı boğmamalı |
| `tenant_admin` | Bildirim ve self-servis ayarlarını yönetir | Admin | Yanlış hedefleme veri sızıntısı yaratabilir |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Çalışan self-servis ana sayfası.
- Hızlı izin talebi bağlantısı.
- Belge/profil/duyuru özetleri.
- Talep durum takibi.
- Yönetici onay kuyruğu.
- Basit duyuru yayınlama ve okuma.
- In-app/e-posta bildirimleri.
- Audit eventleri.

### V1

- Delegasyon ve vekalet.
- SLA ve escalation.
- Gelişmiş talep tipleri.
- Dinamik form şeması.
- Mobil push entegrasyonu.
- Bildirim tercihleri.

### V2

- No-code workflow designer.
- Teams/Slack action buttons.
- AI destekli talep sınıflandırma.
- Gelişmiş duyuru hedefleme ve kampanya raporları.

### Enterprise

- Çok kademeli onay zinciri.
- Legal/uyum onayları.
- Gelişmiş audit, SIEM ve retention.

## 5. Ana kullanıcı akışları

### 5.1 Çalışan self-servis girişi

1. Çalışan portal ana sayfasını açar.
2. Sistem izin bakiyesi, bekleyen talepler, duyurular ve hızlı aksiyonları gösterir.
3. Çalışan ihtiyacına göre izin, belge veya profil akışına gider.
4. Talebin durumunu aynı ekrandan takip eder.

### 5.2 Yönetici onay kuyruğu

1. Yönetici onay merkezine girer.
2. Sistem izin, profil değişikliği, belge veya diğer talepleri tek kuyrukta gösterir.
3. Her talepte gerekli bağlam gösterilir.
4. Yönetici onaylar veya gerekçeli reddeder.
5. Sistem talep sahibini bilgilendirir.

### 5.3 Duyuru yayınlama

1. HR duyuru oluşturur.
2. Hedef kitleyi rol/departman/şube bazında seçer.
3. Duyuru yayınlanır.
4. Çalışan portalında ve bildirimde görünür.
5. Kritik duyurularda okundu/onaylandı bilgisi tutulur.

### 5.4 Talep durumu izleme

1. Çalışan geçmiş ve aktif taleplerini görür.
2. Talep durumu `beklemede`, `onaylandı`, `reddedildi`, `iptal edildi` olarak gösterilir.
3. Reddedilen talepte gerekçe görünür.
4. Uygunsa çalışan tekrar düzenleyip gönderebilir.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| Çalışan Ana Sayfa | Hızlı aksiyonlar, duyuru, bekleyen talepler | MVP |
| Taleplerim | Talep listesi ve durum | MVP |
| Onay Merkezi | Yönetici karar kuyruğu | MVP |
| Duyurular | Liste, detay, okundu/onay | MVP |
| Bildirimler | In-app bildirim listesi | MVP |
| Delegasyon | Vekil atama | V1 |
| Workflow Yönetimi | Talep tipi/form/onay | V1/V2 |

Deneyim ilkesi: Çalışan self-servis ekranı yoğun İK paneli gibi olmamalıdır; sade, görev odaklı ve mobil uyumlu olmalıdır.

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `request_types` | Talep türleri | `code`, `name`, `form_schema`, `approval_policy_id`, `active` |
| `requests` | Talep kaydı | `requester_id`, `type_id`, `status`, `payload`, `due_at` |
| `approval_tasks` | Onay adımları | `request_id`, `approver_id`, `status`, `decided_at` |
| `announcements` | Duyuru | `title`, `body`, `targeting`, `requires_ack` |
| `announcement_reads` | Okundu/onay bilgisi | `announcement_id`, `employee_id`, `read_at`, `ack_at` |
| `notifications` | Bildirim kayıtları | `recipient_id`, `channel`, `template`, `status` |
| `delegations` | Vekalet/delegasyon | `delegator_id`, `delegate_id`, `scope`, `start_at`, `end_at` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/self-service/home` | Çalışan ana sayfa özeti | MVP |
| GET | `/api/v1/requests` | Taleplerim / yetkili talepler | MVP |
| POST | `/api/v1/requests` | Talep oluşturma | MVP |
| GET | `/api/v1/approval-tasks` | Onay kuyruğu | MVP |
| POST | `/api/v1/approval-tasks/{id}/approve` | Onay | MVP |
| POST | `/api/v1/approval-tasks/{id}/reject` | Red | MVP |
| GET | `/api/v1/announcements` | Duyuru listesi | MVP |
| POST | `/api/v1/announcements` | Duyuru yayınlama | MVP |
| POST | `/api/v1/announcements/{id}/ack` | Okundu/onay | MVP |
| POST | `/api/v1/delegations` | Delegasyon oluşturma | V1 |

## 9. Yetki, scope ve güvenlik kuralları

- Çalışan yalnız kendi taleplerini görür.
- Yönetici yalnız kendisine atanmış veya team scope içindeki onayları görür.
- Duyuru hedeflemesi tenant içinde scope ve role göre filtrelenir.
- Delegasyon süreli ve kapsamlı olmalıdır.
- Hassas talep payload'ları şifreleme ve field classification ile yönetilmelidir.
- Onay task'ı başkasına aitse işlem yapılamamalıdır.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `request.created` | Talep tipi ve talep sahibi |
| `request.cancelled` | İptal eden ve neden |
| `approval.approved` | Onaylayan, zaman, delegation flag |
| `approval.rejected` | Red gerekçesi |
| `announcement.published` | Hedef kitle ve yayınlayan |
| `announcement.acknowledged` | Okundu/onay zamanı |
| `delegation.created` | Kapsam ve süre |

Talep payload'ları talep türüne göre kişisel veya hassas veri içerebilir; form schema veri sınıflandırması desteklemelidir.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Talep onay bekliyor | Approver | In-app/e-posta/push |
| Talep sonucu | Requester | In-app/e-posta/push |
| Yeni duyuru | Hedef kitle | In-app/push |
| Kritik duyuru okunmadı | Çalışan/HR | Hatırlatma |
| Onay gecikti | Approver/HR | In-app/e-posta |

Arka plan işler: geciken onay hatırlatma, duyuru okundu raporu, notification retry, delegasyon süre bitimi.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Talep statü geçişleri |
| Unit | Duyuru hedefleme kuralı |
| Integration | Talep → onay → bildirim |
| Integration | Duyuru yayınlama → okundu kaydı |
| E2E | Mobil yönetici onay verir |
| Security | Başka kullanıcının onay task'ına erişim engellenir |

## 13. Kabul kriterleri

- Çalışan self-servis ana sayfası çalışır.
- Çalışan kendi taleplerini ve durumlarını görür.
- Yönetici onay kuyruğunda doğru talepleri görür.
- Onay/red sonrası talep sahibi bilgilendirilir.
- Duyuru hedef kitleye görünür.
- Kritik duyuruda okundu/onay kaydı alınır.
- Tüm kritik işlemler audit'e düşer.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Workflow designer MVP'yi şişirir | MVP'de sabit talep tipleri ve basit onay |
| Risk | Bildirimler kullanıcıyı boğar | Önem seviyeleri ve kanal tercihleri V1'de genişler |
| Risk | Delegasyon hassas erişimi büyütür | V1'de scope ve süre sınırı zorunlu |
| Açık soru | İlk MVP talep tipleri neler olacak? | İzin, belge, profil değişikliği ilk set |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [İzin, Devamsızlık ve Onay Modülü](03-izin-devamsizlik-onay.md)
- [Personalar, JTBD ve Kullanıcı Yolculukları](../02-urun/01-personalar-jtbd-ve-kullanici-yolculuklari.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
