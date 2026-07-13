# Wireframe ve Ekran Akış Planı

Bu doküman, MVP için Figma veya benzeri tasarım aracına geçmeden önce ekran akışlarını metin seviyesinde netleştirir. Amaç, tasarımcı ve frontend geliştiricinin aynı kullanıcı yolculuğunu görmesidir.

## 1. Tasarım ilkeleri

- Mobil uyumlu web öncelikli.
- İK operasyon ekranlarında tablo + detay drawer modeli.
- Çalışan portalında sade kart ve hızlı aksiyonlar.
- Hassas alanlar maskeli ve gerekirse step-up ile görünür.
- Hata, boş durum ve loading state her ekranda planlanır.
- Tenant ve platform yönetim shell'leri görsel ve session olarak ayrıdır; biri diğerinin token'ıyla
  sessizce açılmaz.
- Cursor/lazy API kullanan organization ekranları full tenant verisini önden indirmez; her seviye
  loading/error/retry ve next-page state'i taşır.

## 2. MVP ekran listesi

| Durum | Alan | Ekran | Kullanıcı |
|---|---|---|---|
| Uygulandı | Auth | Email/password tenant login | Tenant kullanıcıları |
| Uygulandı | Auth | Post-auth kurum seçimi | Multi-membership kullanıcılar |
| Uygulandı | Auth | Davet aktivasyonu ve global parola recovery | Tenant kullanıcıları |
| Uygulandı | Platform | Ayrı platform login, tenant metadata shell ve platform audit | `super_admin` |
| Uygulandı | Dashboard | Rol-aware tenant özet ve manager direct-team kartı | Tenant rollerine göre |
| Uygulandı | Admin | Kullanıcı daveti/durum/rol yönetimi | Tenant admin |
| Uygulandı | Audit | Tenant category-filtered audit explorer | Yetkili tenant rolleri |
| Uygulandı | Organization | Tek organization workspace: chart, legal entity/branch, department, position, assignment | Tenant admin/HR/auditor permission'a göre |
| Phase 4+ planı | Employee | Çalışan listesi ve Employee 360 | HR/manager/employee |
| Sonraki faz planı | Document/Leave/Self-servis | Belge UI, izin formu/onay/takvim, talepler | Role göre |
| Sonraki faz planı | Import/Announcement | Import dry-run ve duyurular | HR/admin/tüm kullanıcılar |

## 3. Login akışı

Tenant login adımları:

1. Kullanıcı genel `/login` sayfasına gelir. Tenant subdomain, kurum kodu, slug veya tenant ID
   alanı yoktur.
2. Yalnız e-posta ve parola girer. Hatalı credential, inactive identity ve uygun membership
   bulunmaması aynı genel hata mesajını kullanır; kurum adı/sayısı sızmaz.
3. Tek aktif membership varsa tenant-bound session açılır ve rol-aware home'a gidilir.
4. Birden fazla membership varsa credential doğrulandıktan sonra `/select-organization` açılır.
   Kartlar yalnız safe display name taşır; browser'a tenant/membership ID yerine opaque
   `selection_key` verilir.
5. Seçim başarılıysa ilgili tenant session'ı açılır. Expired/replayed/forged seçim terminal
   genel hata verir ve email/parola login'e döndürür.

Aktif oturumdan kurum değiştirme aynı selection ekranını kullanır; server identity'yi mevcut
session'dan türetir, kaynak session'ı revoke eder ve caller tenant selector'ı kabul etmez.

Platform login adımları:

1. Landing'deki ikincil giriş `/platform/login` sayfasını açar.
2. E-posta/parola global credential'ı doğrular; aktif platform rolü yoksa tenant membership
   metadata'sı göstermeden reddeder.
3. Başarı ayrı platform cookie/audience ile `/platform` shell'ine gider; organization selector
   gösterilmez.
4. Tenant session platform shell'i, platform session tenant shell'i açamaz. Her shell kendi
   refresh/logout endpointini kullanır.

Boş/hata state:

- Genel credential hatası; tenant/membership enumeration yok.
- Rate limit ve retry mesajı.
- Kurum seçimi expired/consumed/invalid; yeniden login aksiyonu.
- Network/server hatası ve correlation referansı.
- Platform rolü olmayan hesap için standart tenant login'e yönlendiren ayrı hata.

MFA enrollment/challenge güncel Phase 3 ekranı değildir; auth-strength/step-up hazırlığı
sonraki güvenlik diliminde UI'ya dönüşür.

Local review yolu `scripts/seed_demo_data.py --auth-demo` tarafından iki etiketli activation URL ile
hazırlanır. `wf_admin` aktivasyonu aynı email identity'sinin iki tenant'ını seçme, Wealthy
Falcon'da organization admin/assignment ve ayrı platform-login yüzeylerini açar. `wf_manager`
aktivasyonu kendi persisted structured direct team kartını açar. Script default/plaintext parola
basmaz; activation sonrası kullanıcının belirlediği credential kullanılır.

## 4. İK dashboard

Kartlar:

- Toplam çalışan.
- Yeni işe başlayanlar.
- Ayrılanlar.
- Bekleyen izin talepleri.
- Eksik belge sayısı.
- Yaklaşan belge geçerlilik uyarıları.

Aksiyonlar:

- Yeni çalışan ekle.
- Çalışan import başlat.
- Rapor indir.

Güncel Phase 3 dashboard bu planın foundation özetini ve role-aware navigasyonu sunar. Manager
için ayrı direct-team kartı `/api/v1/teams/me` sonucunu gösterir; ekip legacy departman metninden
değil current structured assignment manager bağından türetilir. Yeni çalışan, import ve export
aksiyonları ilgili sonraki ürün dilimleri gelene kadar aktif Phase 3 taahhüdü değildir.

## 5. Organization workspace

`/organization` tek uzun, anchor-navigation kullanan role-aware çalışma alanıdır:

1. **Organizasyon şeması:** Root reporting page bounded olarak yüklenir. `has_children` node'u
   expand edildiğinde yalnız o manager'ın direct reports sayfası istenir. Her level için loading,
   inline retry ve next-page state'i vardır; resolved legal entity/branch/department/position
   etiketleri node ile gelir.
2. **Tüzel kişilik ve şubeler:** Cursor ile legal entity seçilir; typed settings formu ve status/
   legal-entity filtreli branch tablosu gösterilir. Update permission sahibi legal-entity
   create/edit ile branch create/edit/archive dialoglarını görür. Branch archive sonrası tarihçenin
   korunduğu ve yeni assignment'ın kapandığı açıklanır.
3. **Departmanlar:** Bir seferde root veya tek direct-child seviye lazy yüklenir. Stable code,
   parent, active/archive ve `has_children` görünür. Create/rename/move/archive dialogları cycle,
   active-child ve concurrency conflict'lerini veri kaybetmeden inline sunar.
4. **Pozisyonlar:** Status filtresi, bounded indexable search ve cursor pagination vardır. Create/
   title-update/archive dialogu pozisyonu reusable tenant job title olarak anlatır; departman/FTE/
   bütçe alanı göstermez.
5. **Çalışan atamaları:** Yalnız `employee:update:tenant` sahibi yetkili HR rollerine görünür.
   Server-side employee search ve bounded manager options ile ilk assignment oluşturulur. Change
   dialogu yeni effective date ve zorunlu reason alır; history tablosu eski satırı overwrite etmez.

Read-only auditor organization ayarlarını/chart'ı okuyabilir fakat mutation kontrollerini görmez.
Manager organization-wide workspace authority almaz; dashboard direct-team kartıyla sınırlıdır.
Organization feature kapalıysa navigasyon gizlenir ve backend `404 organization_feature_unavailable`
ile esas fail-closed sınırı uygular.

## 6. Çalışan listesi (Phase 4 planı)

Layout:

- Sol/üst filtre alanı.
- Ana tablo.
- Sağ detay drawer.

Kolonlar:

- Employee number.
- Ad soyad.
- Departman.
- Pozisyon.
- Durum.
- İşe giriş tarihi.

Filtreler:

- Durum.
- Departman.
- Lokasyon.
- Arama.

## 7. Employee 360 detay (Phase 4 planı)

Sekmeler:

- Özet.
- Kişisel bilgiler.
- İş bilgileri.
- Belgeler.
- İzinler.
- Talepler.
- Audit geçmişi.

Hassas alan davranışı:

- TCKN maskeli.
- IBAN maskeli.
- Maaş alanı permission yoksa gösterilmez.
- Sağlık/özel nitelikli bilgi varsayılan gizli.

## 8. İzin talep akışı (sonraki UI dilimi)

Adımlar:

1. Çalışan izin türü seçer.
2. Tarih aralığı seçer.
3. Sistem gün sayısını ve resmi tatil etkisini gösterir.
4. Bakiye yeterliyse talep gönderilir.
5. Onay zinciri gösterilir.
6. Yöneticiye bildirim gider.

Hatalar:

- Bakiye yetersiz.
- Kilitli dönem.
- Geçmiş tarih policy dışı.
- Aynı tarihte çakışan talep.

## 9. Yönetici onay kuyruğu (sonraki UI dilimi)

Kart/table alanları:

- Talep eden.
- İzin türü.
- Tarih aralığı.
- Gün sayısı.
- Bakiye.
- Ekip çakışması.

Aksiyonlar:

- Onayla.
- Reddet.
- Detaya git.

Onay/red gerekçesi audit'e yazılır.

## 10. Import dry-run ekranı (sonraki UI dilimi)

Adımlar:

1. Şablon indir.
2. Dosya yükle.
3. Kolon mapping kontrol et.
4. Dry-run çalıştır.
5. Hata/uyarı satırlarını gör.
6. Düzelt veya commit et.

Özet paneli:

- Toplam satır.
- Başarılı satır.
- Hatalı satır.
- Uyarılı satır.
- Duplicate kayıt.

## 11. Figma ve implementation frame seti

Phase 3'te review/demo için implementation ile eşleşen frame seti:

1. Email/password-only tenant login.
2. Post-auth multi-org selection ve expired/replayed state.
3. Ayrı platform login ve platform shell.
4. Tenant role-aware dashboard ve manager team card.
5. Kullanıcı/rol yönetimi ve tenant audit.
6. Unified organization workspace genel state'i.
7. Legal entity/branch edit/archive dialogları.
8. Lazy department tree ve move/cycle conflict state'i.
9. Position bounded search ve archive state'i.
10. Assignment create/change/history ve lazy org chart expand state'i.

Çalışan listesi/Employee 360, belge, leave UI, import ve announcement frameleri Phase 4 veya
ilgili sonraki ürün dilimlerinde üretilir; P3K kapsamında başlatılmaz.

## 12. Kabul kriterleri

- Her kritik akışın mutlu yol ve hata state'i vardır.
- Tenant login kurum kodu istemez; membership seçenekleri credential doğrulamasından önce
  görünmez.
- Multi-org selection expired/replayed/invalid state'i login'e güvenli geri dönüş sağlar.
- Platform login/shell tenant auth'tan görsel ve session olarak ayrıdır; cross-realm oturum
  sessizce kabul edilmez.
- Organization workspace permission-aware create/update/archive, loading/empty/error/retry ve
  cursor/lazy pagination state'lerini gösterir.
- Manager team card yalnız derived direct team'i; org chart her istekte tek bounded reporting
  seviyesini gösterir.
- Inactive legal entity ve archived branch/department/position referansları history'de anlaşılır
  kalır ve yeni assignment option'ında görünmez.
- Phase 4+ hassas employee alanları, import ve diğer gelecek frameler plan olarak etiketlenir;
  güncel Phase 3 yüzeyi varmış gibi sunulmaz.

## 13. İlgili dokümanlar

- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [Uygulama Yüzeyleri Web, Mobil ve API](../04-mimari/04-uygulama-yuzeyleri-web-mobil-api.md)
- [OpenAPI Endpoint Taslağı](03-openapi-endpoint-taslagi.md)
