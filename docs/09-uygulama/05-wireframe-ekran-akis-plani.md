# Wireframe ve Ekran Akış Planı

Bu doküman, MVP için Figma veya benzeri tasarım aracına geçmeden önce ekran akışlarını metin seviyesinde netleştirir. Amaç, tasarımcı ve frontend geliştiricinin aynı kullanıcı yolculuğunu görmesidir.

## 1. Tasarım ilkeleri

- Mobil uyumlu web öncelikli.
- İK operasyon ekranlarında tablo + detay drawer modeli.
- Çalışan portalında sade kart ve hızlı aksiyonlar.
- Hassas alanlar maskeli ve gerekirse step-up ile görünür.
- Hata, boş durum ve loading state her ekranda planlanır.

## 2. MVP ekran listesi

| Alan | Ekran | Kullanıcı |
|---|---|---|
| Auth | Login | Tüm kullanıcılar |
| Auth | Şifre sıfırlama | Tüm kullanıcılar |
| Dashboard | İK özet dashboard | HR |
| Employee | Çalışan listesi | HR/manager |
| Employee | Çalışan detay / Employee 360 | HR/manager/employee |
| Document | Belge listesi ve yükleme | HR |
| Leave | İzin talep formu | Employee |
| Leave | Onay kuyruğu | Manager |
| Leave | Ekip izin takvimi | Manager/HR |
| Self-servis | Taleplerim | Employee |
| Announcement | Duyurular | Tüm kullanıcılar |
| Admin | Kullanıcı/rol yönetimi | Tenant admin |
| Import | Çalışan import dry-run | HR/admin |

## 3. Login akışı

Adımlar:

1. Kullanıcı tenant subdomain veya kurum koduyla login sayfasına gelir.
2. E-posta/şifre girer.
3. Hatalı girişte genel hata mesajı döner; hangi alanın hatalı olduğu söylenmez.
4. Admin rolü veya riskli cihaz ise MFA step-up gösterilir.
5. Başarılı login sonrası role göre dashboard'a gider.

Boş/hata state:

- Tenant bulunamadı.
- Hesap kilitli.
- Şifre süresi dolmuş.
- MFA kodu hatalı.

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

## 5. Çalışan listesi

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

## 6. Employee 360 detay

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

## 7. İzin talep akışı

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

## 8. Yönetici onay kuyruğu

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

## 9. Import dry-run ekranı

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

## 10. Figma üretim notları

Figma'da ilk üretilecek frame seti:

1. Login.
2. HR dashboard.
3. Çalışan listesi.
4. Employee 360.
5. İzin talep.
6. Yönetici onay kuyruğu.
7. Import dry-run.
8. Kullanıcı/rol yönetimi.

## 11. Kabul kriterleri

- Her kritik akışın mutlu yol ve hata state'i vardır.
- Hassas alan davranışı UI seviyesinde planlanmıştır.
- Import ekranı satır bazlı hataları gösterecek şekilde planlıdır.
- Frontend başlamadan önce Figma frame listesi nettir.

## 12. İlgili dokümanlar

- [Kanallar, Web, Mobil ve Self-Servis Deneyimi](../02-urun/02-kanallar-web-mobil-self-servis.md)
- [Uygulama Yüzeyleri Web, Mobil ve API](../04-mimari/04-uygulama-yuzeyleri-web-mobil-api.md)
- [OpenAPI Endpoint Taslağı](03-openapi-endpoint-taslagi.md)
