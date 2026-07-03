# İzin, Devamsızlık ve Onay Modülü

Bu doküman, IK Platform'un izin türleri, izin bakiyesi, çalışan izin talebi, yönetici onayı, devamsızlık kaydı ve ileride puantaj/bordro etkisi yaratacak zaman verisi temelini tanımlar.

## 1. Amaç ve karar özeti

İzin modülü MVP'nin en hızlı değer üreten self-servis akışıdır. Çalışan izin bakiyesini görür, talep açar; yönetici bağlamlı şekilde onaylar; İK ise manuel Excel ve mesaj trafiğinden çıkar.

Karar özeti:

> MVP'de izin türleri, bakiye, talep, yönetici onayı, resmi tatil/hafta sonu hesabı, temel takvim ve audit çalışmalıdır. Vardiya, PDKS, puantaj ve bordro export V1'e bırakılır.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| İzin türü katalogu | Gelişmiş vardiya optimizasyonu |
| İzin bakiyesi | PDKS cihaz entegrasyonu |
| İzin talebi oluşturma | Native bordro hesaplaması |
| Yönetici onayı/red | Fazla mesai motoru |
| Resmi tatil ve hafta sonu etkisi | Geofence clock-in |
| Ekip izin takvimi | Komple puantaj mutabakat ekranı |
| Talep iptali | Karmaşık denkleştirme kuralları |
| Audit ve bildirim | Otomatik SGK/bordro bildirimi |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `employee` | Kendi izin bakiyesini görür, talep açar, iptal ister | Own | Başkasının izin detayını görmemeli |
| `manager` | Ekip izin taleplerini onaylar/reddeder | Team | Ekip takvimi dışında hassas veri görmemeli |
| `hr_specialist` | İzin türleri, bakiyeler ve istisnaları yönetir | Tenant/scope | Manuel düzeltmeler auditlenmeli |
| `hr_director` | İzin politikası ve raporlarını izler | Tenant | Politika değişimi kontrolsüz olmamalı |
| `payroll_specialist` | V1'de puantaj/bordro etkisini okur | Payroll scope | Kilitli döneme izinsiz değişiklik olmamalı |
| `tenant_admin` | Sistem ayarlarını ve takvimleri yönetir | Tenant admin | Politika hatası tüm çalışanları etkiler |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- İzin türleri.
- İzin bakiyesi.
- İzin talebi oluşturma.
- Yönetici onayı/red.
- Resmi tatil ve hafta sonu hesabı.
- Ekip takvimi sade görünüm.
- İzin geçmişi ve durum takibi.
- Temel bildirimler.
- Audit eventleri.

### V1

- Vardiya etkisi.
- PDKS/puantaj bağlantısı.
- Fazla mesai talepleri.
- Delegasyon/vekaletli onay.
- Bordro export için onaylı zaman verisi.
- Gelişmiş izin politika motoru.

### V2

- Gelişmiş denkleştirme.
- Kapasite planlama.
- Geofence/mobile clock-in opsiyonu.
- AI destekli devamsızlık/anomali sinyalleri.

### Enterprise

- Çok kademeli onay hiyerarşileri.
- Ülke/şirket/şube bazlı politika setleri.
- Gelişmiş audit ve SIEM eventleri.

## 5. Ana kullanıcı akışları

### 5.1 İzin talebi

1. Çalışan self-serviste izin türünü seçer.
2. Başlangıç/bitiş tarihini girer.
3. Sistem bakiye, resmi tatil ve hafta sonu etkisini hesaplar.
4. Gerekiyorsa belge veya açıklama ister.
5. Talep doğru yöneticiye düşer.
6. Çalışan talep durumunu takip eder.

### 5.2 Yönetici onayı

1. Yönetici onay kuyruğunda talebi görür.
2. Sistem çalışan bakiyesi ve ekip takvimi bağlamını gösterir.
3. Yönetici onaylar veya gerekçeli reddeder.
4. Çalışana bildirim gider.
5. Bakiye ve takvim güncellenir.
6. Audit event yazılır.

### 5.3 Talep iptali

1. Çalışan bekleyen veya onaylı talep için iptal ister.
2. Talep durumuna göre otomatik iptal veya yönetici/İK onayı gerekir.
3. İptal sonrası bakiye geri yazılır.
4. Audit ve bildirimler üretilir.

### 5.4 İK manuel düzeltme

1. HR yetkili kullanıcı bakiye düzeltmesi açar.
2. Sistem gerekçe ister.
3. Kritik düzeltme ikinci onay gerektirebilir.
4. Önce/sonra değeri audit'e yazılır.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | MVP durumu |
|---|---|---|
| İzin Talebi | Tür, tarih, bakiye, açıklama, belge | MVP |
| İzinlerim | Bakiye, geçmiş, bekleyen talepler | MVP |
| Yönetici Onay Kuyruğu | Talep, bakiye, ekip takvimi, karar | MVP |
| Ekip Takvimi | Ekip izinleri ve çakışma görünümü | MVP sade |
| İzin Yönetimi | Talep listesi, filtre, manuel düzeltme | MVP |
| İzin Politikası | Hak ediş/devreden/negatif bakiye ayarı | V1 |
| Puantaj Etkisi | İzinlerin zaman/bordro etkisi | V1 |

Mobilde izin talebi 3-4 adımdan uzun olmamalıdır.

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `leave_types` | İzin türleri | `code`, `name`, `paid`, `requires_document`, `active` |
| `leave_policies` | Hak ediş ve kullanım kuralları | `tenant_id`, `leave_type_id`, `accrual_rule`, `carryover_rule` |
| `leave_balances` | Çalışan bakiyesi | `employee_id`, `leave_type_id`, `period`, `earned`, `used`, `planned` |
| `leave_requests` | Talep kaydı | `employee_id`, `type_id`, `start_date`, `end_date`, `duration`, `status` |
| `leave_request_days` | Gün bazlı kırılım | `date`, `duration`, `is_holiday`, `counts_as_leave` |
| `holiday_calendars` | Resmi tatil | `country`, `region`, `branch_id`, `date`, `duration` |
| `leave_adjustments` | Manuel düzeltme | `employee_id`, `amount`, `reason`, `approved_by` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/leave-types` | İzin türleri | MVP |
| GET | `/api/v1/me/leave-balances` | Kendi bakiye bilgisi | MVP |
| GET | `/api/v1/employees/{id}/leave-balances` | Yetkili çalışanın bakiyesi | MVP |
| POST | `/api/v1/leave-requests` | İzin talebi oluşturma | MVP |
| GET | `/api/v1/leave-requests` | Talep listesi | MVP |
| POST | `/api/v1/leave-requests/{id}/approve` | Onay | MVP |
| POST | `/api/v1/leave-requests/{id}/reject` | Red | MVP |
| POST | `/api/v1/leave-requests/{id}/cancel` | İptal | MVP |
| GET | `/api/v1/team-calendar` | Ekip takvimi | MVP |
| POST | `/api/v1/leave-adjustments` | Bakiye düzeltme | MVP/V1 |

## 9. Yetki, scope ve güvenlik kuralları

- Employee sadece kendi izinlerini görür ve talep açar.
- Manager sadece team scope içindeki talepleri onaylar.
- HR tenant veya atanmış scope dahilinde izin kayıtlarını görür.
- Manuel bakiye düzeltmesi ayrı permission ve gerekçe ister.
- Export ayrı permission ister.
- Sağlık raporu gibi belge gerektiren izinlerde belge görünürlüğü DOC sensitivity kurallarına bağlıdır.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `leave.requested` | Talep tarihi, tür, süre |
| `leave.approved` | Onaylayan, zaman, scope |
| `leave.rejected` | Red gerekçesi |
| `leave.cancelled` | İptal eden ve neden |
| `leave.balance_adjusted` | Önce/sonra, gerekçe, onaylayan |

İzin verisi çalışma hayatı verisidir. Sağlık veya özel durum içeren belgeler ayrı hassasiyetle saklanmalıdır.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Yeni izin talebi | Yönetici | In-app, push/e-posta |
| Talep sonucu | Çalışan | In-app, push |
| Onay gecikti | Yönetici/HR | In-app/e-posta |
| Bakiye düzeltildi | Çalışan/HR | In-app |

Arka plan işler: bakiye hak ediş hesaplama, resmi tatil güncelleme, geciken onay hatırlatma, periyodik izin raporu snapshot.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Resmi tatil/hafta sonu süre hesabı |
| Unit | Negatif bakiye policy kontrolü |
| Integration | İzin talebi → onay → bakiye güncelleme |
| Integration | Red/iptal sonrası bakiye davranışı |
| E2E | Mobil çalışan talep açar, yönetici onaylar |
| Security | Manager başka ekibin talebini göremez |

## 13. Kabul kriterleri

- Çalışan izin talebi açabilir.
- Sistem izin süresini doğru hesaplar.
- Talep doğru yöneticiye düşer.
- Yönetici bağlamlı onay ekranından karar verebilir.
- Onay/red sonrası çalışan bilgilendirilir.
- Bakiye ve takvim güncellenir.
- Kritik işlemler audit'e düşer.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | İzin motoru fazla karmaşık yapılırsa MVP gecikir | Basit ama genişletilebilir policy ile başlanır |
| Risk | Vardiya/PDKS MVP'ye çekilirse kapsam şişer | V1'e bırakılır |
| Açık soru | İlk pilotta hangi izin türleri seed edilecek? | Yıllık, mazeret, ücretsiz, rapor başlangıç seti önerilir |
| Açık soru | Negatif bakiye desteklenecek mi? | Tenant policy ile kapalı başlamak güvenli |

## 15. İlgili dokümanlar

- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
- [Personel, Özlük ve Doküman Yönetimi Modülü](02-personel-ozluk-dokuman.md)
- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
