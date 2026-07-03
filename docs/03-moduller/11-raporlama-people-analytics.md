# Raporlama ve People Analytics Modülü

Bu doküman, IK Platform'un operasyonel rapor, dashboard, export, KPI katalogu, özel rapor oluşturucu ve people analytics kapsamını tanımlar.

## 1. Amaç ve karar özeti

Raporlama modülü, ürünün yönetim değerini görünür kılar. MVP'de çalışan, izin ve belge gibi temel operasyon raporları gerekir; gelişmiş people analytics ve doğal dil sorgu V2'ye bırakılır.

Karar özeti:

> MVP'de headcount, çalışan listesi, izin ve eksik belge raporları çalışmalıdır. V1'de report builder ve scheduled reports, V2'de semantic layer, NLQ ve predictive analytics gelir.

## 2. Kapsam içi / kapsam dışı

| Kapsam içi | Kapsam dışı |
|---|---|
| Headcount dashboard | MVP'de tam BI ürünü |
| Çalışan listesi/export | Raw SQL sorgu aracı |
| İzin raporu | Yetkisiz hassas alan export'u |
| Eksik belge raporu | Predictive attrition MVP |
| Temel audit/export log | Data warehouse zorunluluğu |
| V1 report builder | Power BI/Tableau ilk sürüm |
| KPI katalogu | Sınırsız ad-hoc veri madenciliği |

## 3. Kullanıcı rolleri ve sorumluluklar

| Rol | Modüldeki işi | Yetki seviyesi | Kritik risk |
|---|---|---|---|
| `hr_specialist` | Operasyon raporlarını alır | Scope/tenant | Hassas alan export etmemeli |
| `hr_director` | Dashboard ve trendleri izler | Tenant | KPI tanımları tutarlı olmalı |
| `manager` | Ekip raporlarını görür | Team | Başka ekip verisini görmemeli |
| `finance_user` | İşgücü maliyet raporlarını izler | Finance scope | Kişisel maaş verisi korunmalı |
| `auditor` | Audit ve uyum raporlarını inceler | Read-only | Veri değiştirmemeli |
| `executive` | Aggregate dashboard görür | Aggregate | Küçük gruplarda anonimlik korunmalı |

## 4. MVP / V1 / V2 / Enterprise ayrımı

### MVP

- Headcount dashboard.
- Çalışan listesi.
- İzin raporu.
- Eksik belge raporu.
- CSV/XLSX export.
- Export audit.

### V1

- Report builder.
- KPI katalogu.
- Scheduled reports.
- Dashboard widget ayarları.
- Gelişmiş filtreler.

### V2

- People analytics semantic layer.
- Doğal dil sorgu.
- Predictive metrics.
- BI connector.
- Küçük grup anonimlik eşikleri.

### Enterprise

- Data warehouse export.
- SIEM export.
- Advanced governance.
- Dedicated analytics pipeline.

## 5. Ana kullanıcı akışları

### 5.1 Temel rapor alma

1. HR rapor ekranını açar.
2. Sistem yetkili olduğu veri kapsamını gösterir.
3. Filtreler uygulanır.
4. Rapor görüntülenir.
5. Export istenirse ayrı permission ve audit çalışır.

### 5.2 Dashboard görüntüleme

1. Kullanıcı rolüne uygun dashboard açılır.
2. KPI kartları hesaplanır veya cache'den gelir.
3. Hassas metriklerde küçük grup eşiği uygulanır.
4. Kullanıcı drill-down yaparsa scope tekrar kontrol edilir.

### 5.3 Report builder

V1 akışıdır.

1. Kullanıcı veri alanlarını seçer.
2. Sistem yetkisiz alanları gizler.
3. Filtre/grup ayarlanır.
4. Rapor kaydedilir veya async çalıştırılır.
5. Sonuç auditlenir.

## 6. Ekranlar ve deneyim notları

| Ekran | İçerik | Faz |
|---|---|---|
| HR Dashboard | Headcount, izin, belge, bekleyen işler | MVP |
| Çalışan Raporu | Liste, filtre, export | MVP |
| İzin Raporu | Kullanılan/bekleyen izinler | MVP |
| Eksik Belge Raporu | Çalışan-belge tamamlık | MVP |
| Report Builder | Alan, filtre, grup, chart | V1 |
| KPI Catalog | Tanım, owner, veri kaynağı | V1 |
| People Analytics | Turnover, hiring, performance trend | V2 |

## 7. Veri modeli etkisi

| Varlık | Amaç | Kritik alanlar |
|---|---|---|
| `metric_definitions` | KPI tanımı | `code`, `formula`, `grain`, `version` |
| `report_definitions` | Rapor tanımı | `query_json`, `visibility`, `owner_id` |
| `report_runs` | Çalıştırma kaydı | `status`, `row_count`, `storage_key` |
| `dashboard_widgets` | Dashboard kartları | `metric_code`, `visual_type`, `config_json` |
| `analytics_snapshots` | Zaman serisi | `snapshot_date`, `metric_code`, `dimensions_json` |
| `export_jobs` | Export kaydı | `requested_by`, `expires_at`, `download_count` |
| `nlq_queries` | Doğal dil sorgu | `question`, `semantic_intent`, `status` |

## 8. API ve entegrasyon ihtiyaçları

| Method | Endpoint | Açıklama | Faz |
|---|---|---|---|
| GET | `/api/v1/analytics/dashboards` | Dashboard listesi | MVP |
| GET | `/api/v1/reports/employees` | Çalışan raporu | MVP |
| GET | `/api/v1/reports/leaves` | İzin raporu | MVP |
| GET | `/api/v1/reports/documents/missing` | Eksik belge raporu | MVP |
| POST | `/api/v1/report-runs/{id}/export` | Export | MVP/V1 |
| POST | `/api/v1/reports` | Özel rapor | V1 |
| POST | `/api/v1/reports/{id}/schedule` | Zamanlama | V1 |
| POST | `/api/v1/analytics/nlq` | Doğal dil sorgu | V2 |

## 9. Yetki, scope ve güvenlik kuralları

- Rapor satırları kullanıcı scope'una göre filtrelenir.
- Export görüntüleme yetkisinden ayrı permission ister.
- Hassas alanlar report builder'da permission olmadan seçilemez.
- Küçük gruplarda aggregate anonimlik eşiği uygulanır.
- Scheduled report gönderim anında alıcı yetkisi tekrar kontrol edilir.

## 10. KVKK, audit ve saklama gereksinimleri

| Event | Açıklama |
|---|---|
| `report.viewed` | Rapor ve filtre hash |
| `report.exported` | Alan sınıfları, row count |
| `sensitive_report.downloaded` | Actor, IP, amaç |
| `metric_definition.changed` | Eski/yeni formül |
| `nlq.executed` | Intent ve denied fields |

## 11. Bildirimler ve arka plan işler

| Olay | Alıcı | Kanal |
|---|---|---|
| Rapor hazır | Talep eden | In-app/e-posta |
| Scheduled report başarısız | Owner | E-posta |
| KPI eşiği aşıldı | İlgili owner | In-app |
| Hassas export indirildi | Güvenlik/owner | Audit/opsiyonel bildirim |

## 12. Test senaryoları

| Tür | Senaryo |
|---|---|
| Unit | KPI formülü ve aggregation threshold |
| Integration | Report builder field permission |
| E2E | Dashboard → rapor → export |
| Security | Hassas alan export engeli |
| Performance | Büyük export async job |

## 13. Kabul kriterleri

- Headcount, izin ve eksik belge raporları çalışır.
- Tenant/scope dışı veri raporda görünmez.
- Export audit ve expiry ile üretilir.
- Hassas alanlar yetkisiz seçilemez.
- KPI tanımları versiyonlanabilir.

## 14. Riskler, açık sorular ve kararlar

| Tip | Madde | Karar / Not |
|---|---|---|
| Risk | Report builder raw SQL'e dönüşürse güvenlik riski doğar | Semantic/query JSON yaklaşımı |
| Risk | Küçük grup raporları kişileri ifşa eder | Aggregation threshold V2'de zorunlu |
| Açık soru | İlk export formatları neler? | CSV/XLSX başlangıç |

## 15. İlgili dokümanlar

- [Ürün Metrikleri ve Başarı Kriterleri](../02-urun/04-urun-metrikleri-ve-basari-kriterleri.md)
- [CORE, AUTH ve RBAC Modülleri](01-core-auth-rbac.md)
- [Modül Formatı ve Ortak Kararlar](00-modul-format-ve-ortak-kararlar.md)
