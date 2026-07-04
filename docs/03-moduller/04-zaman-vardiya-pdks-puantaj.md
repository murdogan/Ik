# Zaman, Vardiya, PDKS ve Puantaj Modülü

Bu doküman, IK Platform'un çalışma zamanı, vardiya planı, PDKS verisi, puantaj mutabakatı ve bordro hazırlığına veri sağlayan TIME modülünü tanımlar.

## 1. Amaç ve karar özeti

TIME modülü, izin modülünün ötesinde vardiyalı/çok şubeli şirketlerin çalışma zamanı gerçekliğini yönetir. MVP'de sadece temel çalışma takvimi hazırlığı bulunur; asıl PDKS, vardiya ve puantaj kapsamı V1'e alınır.

Karar özeti:

> MVP'de TIME modülü LEAVE için temel takvim ve çalışma günü bilgisini sağlar. V1'de vardiya, PDKS import, puantaj mutabakatı ve bordro export zinciri kurulmalıdır.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Çalışma takvimi | Vardiya optimizasyon algoritması |
| Resmi tatil/yarım gün etkisi | Native bordro motoru |
| Vardiya şablonu | Donanım üreticisi olmak |
| Vardiya atama | Biometrik cihaz yönetimi |
| PDKS CSV/API import | Geofence zorunlu clock-in |
| Kart/cihaz/employee mapping | Yüz tanıma |
| Puantaj günü ve dönem kilidi | Hukuki vardiya danışmanlığı |
| Eksik giriş/çıkış anomalisi | Tam workforce management suite |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `employee` | Vardiyasını ve zaman bilgisini görür | Own | Başkasının vardiyasını görmemeli |
| `manager` | Ekip vardiya/mesai durumunu izler ve onaylar | Team | Puantajı keyfi değiştirmemeli |
| `hr_specialist` | Vardiya, devamsızlık ve istisnaları yönetir | Scope/tenant | Kilitli döneme izinsiz yazmamalı |
| `payroll_specialist` | Puantajı bordro öncesi mutabık eder | Tenant/payroll | Hatalı veri bordroya gitmemeli |
| `tenant_admin` | PDKS bağlantı/mapping ayarlarını yapar | Admin | Yanlış mapping tüm puantajı bozar |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Temel çalışma takvimi.
- Resmi tatil ve hafta sonu etkisi.
- LEAVE modülü için çalışma günü hesap altyapısı.
- Zaman verisi event standardı hazırlığı.

### V1

- Vardiya şablonları.
- Vardiya atama ve çalışan görüntüleme.
- PDKS CSV/API import.
- Kart/cihaz/employee mapping.
- Eksik giriş/çıkış ve anomali listesi.
- Puantaj mutabakatı.
- Bordro export için dönem kilidi.

### V2

- Gelişmiş vardiya planlama.
- Geofence veya mobil clock-in opsiyonu.
- Kapasite planlama.
- AI destekli devamsızlık/anomali sinyalleri.

### Enterprise

- Çok lokasyonlu cihaz bağlantıları.
- Dedicated import worker.
- SIEM/audit export.
- Büyük hacimli puantaj performans optimizasyonları.

## 5. Ana kullanıcı akışları

### 5.1 Vardiya planı

1. HR veya manager vardiya şablonu oluşturur.
2. Çalışan veya ekip için tarih aralığına atama yapılır.
3. Çalışan vardiyasını self-servisten görür.
4. Değişiklik olduğunda bildirim gider.

### 5.2 PDKS import

1. Yetkili kullanıcı PDKS dosyasını yükler veya API import başlatır.
2. Sistem cihaz/kart/employee mapping yapar.
3. Eşleşmeyen kayıtlar staging hata listesine düşer.
4. Temiz kayıtlar time clock event olarak kaydedilir.
5. `timeclock.imported` audit eventi yazılır.

### 5.3 Puantaj mutabakatı

1. Sistem gün bazlı çalışma, izin, devamsızlık ve mesai verisini toplar.
2. Eksik giriş/çıkış ve çakışmalar exception olarak gösterilir.
3. HR/payroll düzeltme talebi veya onay girer.
4. Dönem tamamlanınca kilitlenir.
5. Bordro export üretilebilir.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| Çalışma Takvimi | Tatil, hafta sonu, çalışma günü | MVP |
| Vardiya Planlayıcı | Şablon, atama, çalışan görünümü | V1 |
| PDKS Import Merkezi | Dosya/API log, mapping, hata | V1 |
| Puantaj Mutabakat | Eksik giriş/çıkış, mesai, izin etkisi | V1 |
| Dönem Kilidi | Bordro öncesi kapanış | V1 |
| Mobil Vardiyam | Çalışan vardiya görünümü | V1 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `work_calendars` | Çalışma takvimi | `tenant_id`, `country`, `branch_id`, `timezone` |
| `holiday_calendars` | Tatil günleri | `date`, `duration`, `region`, `source` |
| `shift_templates` | Vardiya şablonu | `start_time`, `end_time`, `break_minutes`, `timezone` |
| `shift_assignments` | Çalışan vardiyası | `employee_id`, `shift_template_id`, `date`, `status` |
| `time_clock_events` | PDKS kayıtları | `employee_id`, `device_id`, `event_at`, `direction`, `source` |
| `time_device_mappings` | Cihaz/kart eşleşmesi | `device_id`, `card_id`, `employee_id`, `valid_from` |
| `timesheet_days` | Günlük puantaj | `worked_minutes`, `overtime_minutes`, `absence_minutes`, `lock_status` |
| `attendance_adjustments` | Düzeltmeler | `type`, `minutes`, `reason`, `approved_by` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/work-calendars` | Takvim listesi | MVP |
| GET | `/api/v1/shifts` | Vardiya planı | V1 |
| POST | `/api/v1/shifts/bulk-assign` | Toplu vardiya atama | V1 |
| POST | `/api/v1/time-clock/imports` | PDKS import | V1 |
| GET | `/api/v1/time-clock/imports/{id}` | Import sonucu | V1 |
| GET | `/api/v1/timesheets` | Puantaj listesi | V1 |
| POST | `/api/v1/timesheets/{period}/lock` | Dönem kilidi | V1 |
| POST | `/api/v1/timesheets/{period}/export-payroll` | Bordro export | V1 |

## 9. Yetki, scope ve güvenlik kuralları

- Employee sadece kendi vardiya ve zaman özetini görür.
- Manager team scope içinde vardiya/puantaj özetini görür.
- PDKS import tenant admin, HR veya payroll yetkisi ister.
- Kilitli dönemde değişiklik adjustment olarak kaydedilir.
- Geofence/konum verisi V2'de ayrıca açık policy ister.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `shift.assigned` | Çalışan, tarih, şablon |
| `timeclock.imported` | Kaynak, satır sayısı, hata sayısı |
| `timesheet.adjusted` | Önce/sonra dakika, gerekçe |
| `timesheet.locked` | Dönem ve actor |
| `payroll_export.generated` | Dosya hash ve kapsam |

PDKS verisi davranışsal çalışma verisidir; amaç sınırlaması ve retention politikası gerektirir.

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Vardiya değişti | Çalışan | Push/in-app |
| PDKS import hatası | HR/payroll | In-app/e-posta |
| Eksik giriş/çıkış | Manager/HR | In-app |
| Dönem kilitlendi | Payroll/HR | In-app |

Arka plan işler: import processing, anomaly detection, timesheet calculation, export generation.

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | Gece vardiyası gün kırılımı |
| Unit | Tatil/izin/mesai çakışması |
| Integration | PDKS import → mapping → timesheet |
| Integration | Puantaj kilidi sonrası adjustment |
| Security | Başka tenant cihaz kaydı import edilemez |
| Performance | Büyük PDKS import async tamamlanır |

## 13. Kabul kriterleri

- Çalışma takvimi izin hesabını besler.
- Vardiya şablonu ve atama yapılabilir.
- PDKS import staging ve hata raporu üretir.
- Puantaj günü hesaplanır ve exception gösterir.
- Dönem kilidi sonrası değişiklik adjustment olur.
- Bordro export için onaylı veri üretilebilir.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Her PDKS cihazına özel entegrasyon erken yük getirir | V1'de CSV/import + sınırlı adapter |
| Risk | Konum verisi KVKK riskini artırır | V2 ve açık policy |
| Açık soru | İlk hedef PDKS formatı hangisi? | Pilot müşteriyle seçilecek |

## 15. İlgili dokümanlar

- [İzin, Devamsızlık ve Onay Modülü](03-izin-devamsizlik-onay.md)
- [Bordro, Ücret ve Mevzuat Modülü](05-bordro-ucret-mevzuat.md)
- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
