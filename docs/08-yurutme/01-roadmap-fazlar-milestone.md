# Roadmap, Fazlar ve Milestone Planı

Bu doküman, IK Platform'un MVP, V1, V2, Enterprise ve AI Edition fazlarını; milestone hedeflerini, bağımlılıkları ve çıkış kriterlerini tanımlar.

## 1. Faz özeti

| Faz | Süre | Amaç | Ana çıktılar |
|---|---:|---|---|
| MVP | 0-4 ay | Core HR ve self-servis ile pilot değer | Tenant, auth, employee, özlük, izin, doküman, basit rapor |
| V1 | 5-9 ay | Türkiye mid-market operasyon derinliği | PDKS, puantaj, ATS, performans, API/webhook, SSO |
| V2 | 10-15 ay | Enterprise HCM derinliği | Bordro motoru, BI, org/kadro, LMS, gelişmiş raporlama |
| Enterprise | 16-21 ay | Büyük kurum/regüle sektör | SCIM, SIEM, dedicated tenant, DR/SLA, advanced audit |
| AI Edition | 12-24 ay | AI destekli İK karar asistanı | CV parsing, match, HR assistant, attrition, governance |

## 2. MVP kapsamı

Dahil:

- Tenant yönetimi.
- Temel RBAC ve login.
- Çalışan profili ve özlük dosyası.
- Doküman yönetimi.
- İzin ve onay akışı.
- Self-servis talep/duyuru.
- Basit raporlar ve export.
- Veri import/migrasyon araçları.
- Temel observability ve audit.

Hariç:

- Native bordro hesaplama.
- Gelişmiş ATS.
- Full BI semantic layer.
- SCIM/SIEM.
- AI risk modeli.
- Çok ülkeli payroll.

## 3. V1 kapsamı

- PDKS ve vardiya derinliği.
- Puantaj kilidi ve bordro hazırlık zinciri.
- ATS, aday portalı ve kariyer sitesi.
- Performans/OKR temel döngüsü.
- Public API ve webhook.
- Enterprise SSO başlangıcı.
- E-imza ve takvim entegrasyonları.
- AI Gateway ve CV parse pilotu.

## 4. V2 kapsamı

- Yerleşik bordro motoru veya derin bordro opsiyonu.
- People analytics ve dashboard builder.
- LMS, yetkinlik ve kariyer yolu.
- 360 değerlendirme ve kalibrasyon.
- Norm kadro ve workforce planning.
- AI Edition genişleme.
- Çoklu dil/ülke altyapısı.

## 5. Epic listesi

| Epic ID | Epic | Öncelik | Bağımlılık |
|---|---|---:|---|
| E-001 | Tenant, kullanıcı, auth, rol ve izin | P0 | Yok |
| E-002 | Employee master data ve Employee 360 | P0 | E-001 |
| E-003 | Özlük doküman yönetimi | P0 | E-002 |
| E-004 | İzin ve onay motoru | P0 | E-001, E-002 |
| E-005 | Bildirim ve duyuru merkezi | P1 | E-001 |
| E-006 | Mobil/PWA temel | P1 | E-001, E-004 |
| E-007 | PDKS/vardiya/puantaj | P1 | E-002, E-004 |
| E-008 | ATS ve aday portalı | P1 | E-001 |
| E-009 | Performans/OKR | P2 | E-002 |
| E-010 | Bordro ve mevzuat motoru | P1 | E-007 |
| E-011 | Analytics ve özel rapor | P2 | Core veriler |
| E-012 | AI özellikleri ve governance | P2 | E-008, E-009, E-011 |
| E-013 | Enterprise SSO/SCIM/SIEM | P1 | E-001 |

## 6. İlk 8 sprint planı

| Sprint | Hedef | Çıktı |
|---|---|---|
| S1 | Proje iskeleti ve auth temeli | Repo, CI, DB migration, tenant/users, login |
| S2 | RBAC ve employee temel | Role/permission, employee CRUD, audit |
| S3 | Employee 360 ve doküman | Profil sekmeleri, upload, field masking |
| S4 | İzin politikası ve talep | Leave types, balances, request, approval |
| S5 | Bildirim ve yönetici portalı | Onay kuyruğu, e-posta/push altyapı |
| S6 | Mobil/PWA MVP | Login, izin talebi, onay, profil |
| S7 | Rapor ve import | CSV import, dashboard, export |
| S8 | Pilot hardening | Security tests, tenant isolation, pilot migration |

## 7. Faz çıkış kriterleri

MVP çıkış:

- Core tenant/auth/employee/leave akışları çalışır.
- Pilot veri migrasyonu yapılabilir.
- P1/P2 açık hata yok.
- Cross-tenant testler geçer.
- Basit rapor/export çalışır.
- Kullanıcı onboarding tamamlanabilir.

V1 çıkış:

- PDKS/puantaj gerçek pilotta doğrulanır.
- ATS ve performance temel akışları canlıdır.
- API/webhook dokümante edilmiştir.
- SSO pilotu çalışır.
- Operasyonel SLO'lar izlenir.

V2 çıkış:

- Analytics/AI/LMS özellikleri gerçek veriyle doğrulanır.
- Enterprise gereksinimleri güvenlik ve operasyon açısından tamamlanır.
- Satış ve müşteri başarı süreçleri tekrarlanabilir hale gelir.

## 8. Roadmap riskleri

| Risk | Azaltım |
|---|---|
| MVP kapsam şişmesi | Must/Should/Could kesme çizgisi |
| Bordro mevzuat karmaşıklığı | MVP'de export modu, V1/V2 motor |
| Pilot veri kalitesi | Import dry-run ve veri kalite raporu |
| Yetki modeli gecikmesi | AUTH/RBAC ilk sprintlerde çözülür |
| PDKS format çeşitliliği | CSV + mapping yaklaşımı |
| AI uyum riski | Human-in-loop ve gateway zorunlu |

## 9. İlgili dokümanlar

- [Ekip, Roller ve Delivery Operating Model](02-ekip-roller-delivery-model.md)
- [GTM, Pilot ve Müşteri Başarı](03-gtm-pilot-musteri-basari.md)
- [MVP, V1 ve V2 Kapsam Kararları](../02-urun/03-mvp-v1-v2-kapsam-kararlari.md)
