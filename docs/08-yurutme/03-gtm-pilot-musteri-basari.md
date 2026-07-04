# GTM, Pilot ve Müşteri Başarı

Bu doküman, IK Platform'un pilot müşteri seçimi, onboarding, hypercare, go-to-market ve müşteri başarı yaklaşımını tanımlar.

## 1. GTM ilkesi

Ürün önce geniş pazara değil, iyi seçilmiş pilot segmentlere doğrulanmalıdır. Amaç ilk aşamada çok müşteri almak değil; tekrar edilebilir değer, onboarding ve kullanım kanıtı üretmektir.

## 2. İdeal pilot müşteri profili

| Kriter | Hedef |
|---|---|
| Çalışan sayısı | 100-1000 |
| İK olgunluğu | Excel/dağınık araçlardan sıkılmış ama SAP/Workday seviyesinde değil |
| Karar verici | Kurucu/Genel Müdür + İK lideri erişilebilir |
| Acı noktası | Özlük, izin, PDKS, rapor, belge karmaşası |
| Veri durumu | Excel/CSV aktarılabilir |
| Risk | Bordro canlı hesaplama kritik bağımlılık olmamalı |
| Referans potansiyeli | Başarı hikayesi yayınlanabilir |

## 3. Pilot segmentleri

| Segment | Neden uygun |
|---|---|
| Üretim/KOBİ+ | PDKS, vardiya, özlük ihtiyacı güçlü |
| Hizmet/çağrı merkezi | Turnover, izin, vardiya, rapor ihtiyacı |
| Perakende zinciri | Şube, çalışan değişimi, duyuru/onay akışı |
| Teknoloji/ajans | Hızlı self-servis ve performans beklentisi |
| Lojistik | Lokasyon, vardiya, belge ve operasyon yoğunluğu |

## 4. Pilot başarı kriterleri

| Alan | Kriter |
|---|---|
| Aktivasyon | İlk 2 haftada çalışan verisi ve org yapısı yüklendi |
| Kullanım | İK ekibi haftalık aktif kullanıyor |
| Self-servis | Çalışanların en az %50'si login yaptı |
| İzin | İzin taleplerinin çoğu sistemden geçti |
| Belge | Özlük belge süreçlerinden en az biri canlı |
| Rapor | Yönetim raporu sistemden üretildi |
| Memnuniyet | İK lideri referans olmaya açık |
| Stabilite | Açık P1/P2 yok |

## 5. Pilot onboarding planı

| Hafta | Aksiyon |
|---|---|
| 0 | Kickoff, veri şablonları, başarı kriterleri |
| 1 | Tenant kurulum, admin eğitimi, veri dry-run |
| 2 | Çalışan/org/import commit, rol ayarları |
| 3 | İzin ve belge süreçleri canlı |
| 4 | Rapor ve duyuru kullanımı |
| 5 | PDKS/puantaj varsa pilot entegrasyon |
| 6 | Geri bildirim ve iyileştirme sprinti |
| 7 | Başarı ölçümü ve referans görüşmesi |
| 8 | Go/No-Go ve ücretli plana geçiş kararı |

## 6. Hypercare modeli

Pilot/GA ilk 4 hafta:

- Günlük kontrol: hata, login, import, izin talepleri.
- Haftalık müşteri görüşmesi.
- Kritik destek kanalı.
- P1 aynı gün, P2 48 saat içinde çözüm hedefi.
- Kullanım metrikleri CSM tarafından izlenir.
- Feature request'ler roadmap'e doğrudan alınmaz; tema olarak gruplanır.

## 7. Satış mesajı

Ana değer önerileri:

- Excel ve dağınık İK süreçlerini tek yerde toplar.
- Türkiye mevzuatı ve pratik İK ihtiyaçlarına odaklıdır.
- Çalışan self-servis ile İK yükünü azaltır.
- İzin, belge, duyuru, rapor ve onay akışlarını hızlandırır.
- Enterprise karmaşıklığı olmadan modern SaaS deneyimi sunar.

Kaçınılacak vaatler:

- MVP'de tam bordro motoru vaadi.
- AI ile otomatik karar vaadi.
- Her PDKS cihazına hazır entegrasyon vaadi.
- SAP/Workday alternatifi iddiası.

## 8. Fiyatlandırma yaklaşımı

İlk öneri PEPM + modül paketleri şeklindedir.

| Paket | Hedef |
|---|---|
| Core | Özlük, izin, belge, self-servis |
| Professional | PDKS/puantaj, rapor, ATS/performance temel |
| Enterprise | SSO, SCIM, dedicated, gelişmiş audit/SLA |
| AI Add-on | CV parse, asistan, öneriler, governance |

Pilotlar için indirim olabilir; ancak ücretsiz sonsuz pilot yapılmamalıdır. Başarı kriteri ve ücretli geçiş tarihi baştan yazılmalıdır.

## 9. Müşteri başarı metrikleri

| Metrik | Amaç |
|---|---|
| Time-to-first-value | Kurulumdan ilk aktif sürece kadar süre |
| Weekly active HR users | İK kullanım sürekliliği |
| Employee activation | Çalışan self-servis benimseme |
| Leave digitalization rate | İzinlerin sistemden geçme oranı |
| Document completion | Eksik belge oranı |
| Support tickets by severity | Operasyon sağlığı |
| NPS / referans niyeti | Pazara çıkış kalitesi |
| Expansion signal | Yeni modül talebi |

## 10. GTM riskleri

| Risk | Azaltım |
|---|---|
| Pilot müşteri çok özel istek yapar | Scope contract ve feature request triage |
| Bordro beklentisi yanlış oluşur | MVP mesajında export modu net söylenir |
| Veri migrasyonu uzar | Dry-run + şablon + CSM kontrolü |
| Kullanıcılar login olmaz | Eğitim, kısa video, duyuru, yönetici desteği |
| Satış erken ölçeklenir | 3-5 başarılı pilot sonrası ölçek |

## 11. İlgili dokümanlar

- [Roadmap, Fazlar ve Milestone Planı](01-roadmap-fazlar-milestone.md)
- [Ürün Vizyonu ve Konumlandırma](../01-strateji-pazar/01-urun-vizyonu-ve-konumlandirma.md)
- [Fiyatlandırma ve Paketleme](../01-strateji-pazar/04-fiyatlandirma-ve-paketleme.md)
