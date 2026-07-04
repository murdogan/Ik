# IK Dokümantasyon Devam Planı

> **For Hermes:** Bu plan uygulanırken kod yazılmayacak. Sadece dokümantasyon üretilecek, her parça kalite kontrolünden sonra repoya işlenecek.

**Goal:** `murdogan/Ik` reposunda, Claude ile yarıda kalan yüksek detaylı İK ürün dokümantasyonunu Codex'in temiz iskeleti ve mevcut repo içeriğiyle birleştirerek canlı ürün geliştirmeye temel olacak mükemmel bir dokümantasyon seti oluşturmak.

**Architecture:** Ana iskelet Codex paketinden alınacak; içerik derinliği Claude paketinin standardında olacak; mevcut repodaki 31 doküman üçüncü referans ve yerel bağlam olarak kullanılacak. Kod/proje iskeleti aşamasına geçilmeyecek.

**Tech Stack:** Bu aşamada kod stack'i seçimi yalnızca dokümante edilecek. Uygulama kodu, backend/frontend scaffold, Docker, CI kurulumu yapılmayacak.

---

## 0. Mevcut Durum

### Referans kaynaklar

1. **Claude zip**
   - Path: `/opt/data/gmail_zips/extracted/claude/IK`
   - 20 markdown dosyası
   - Yaklaşık 62.576 kelime
   - Çok detaylı ama yarım kalmış; README'de var görünen bazı dosyalar eksik.
   - Kullanım şekli: kalite/derinlik standardı.

2. **Codex zip**
   - Path: `/opt/data/gmail_zips/extracted/codex/IK 2`
   - 30 markdown dosyası
   - Yaklaşık 19.906 kelime
   - Daha kısa ama iskeleti daha düzenli ve tamam.
   - Kullanım şekli: klasör/dosya omurgası ve kontrol listesi.

3. **Mevcut repo dokümanları**
   - Path: `/opt/data/repos/Ik/docs/_archive/2026-07-03-original`
   - 32 markdown dosyası
   - Yaklaşık 79.054 kelime
   - Bazı modül dosyaları çok dolu; yerel bağlam ve önceki emek olarak kullanılacak.
   - Kullanım şekli: madde madde taşınacak, ama yeni yapıyı belirlemeyecek.

### Dikkat: Yerel çalışma ağacı

Önceki yanlış başlangıçtan dolayı yerelde şu değişiklikler var:

- Branch: `foundation/hrms-platform`
- `README.md` değiştirilmiş.
- Eski `docs/*.md` dosyaları arşive taşınmış.
- `apps/` altında backend başlangıç dosyası oluşmuş.
- Henüz push yok.

**Uygulamaya başlamadan önce ilk iş:** Kodla ilgili `apps/` klasörü kaldırılmalı ve bu aşamada sadece dokümantasyon branch'i kullanılmalı. Ancak bu plan dosyası dışında şu an hiçbir değişiklik yapılmayacak.

---

## 1. Çalışma Prensipleri

1. **Kod yok:** Bu fazda `apps/`, `infra/`, `.github/workflows/` oluşturulmayacak.
2. **Parça parça ilerleme:** Her seferinde 1-3 doküman üretilecek.
3. **Kalite düşmeyecek:** Her doküman Claude seviyesinde detaylı olacak.
4. **Codex kontrol listesi:** Codex'te olan hiçbir ana başlık unutulmayacak.
5. **Mevcut repo boşa gitmeyecek:** Eski repo dokümanları arşivlenip değerli kısımları yeni dokümanlara aktarılacak.
6. **Kırık link yok:** Her teslimatta iç link kontrolü yapılacak.
7. **Tekrarsızlık:** Aynı karar birden fazla yerde uzun uzun tekrar edilmeyecek; kanonik kararlar `00-genel` veya ilgili ana dokümanda tutulacak.
8. **Canlıya alma odağı:** Her strateji/modül/mimari dokümanı sonunda MVP, V1, V2 ayrımı ve geliştirme etkisi olacak.

---

## 2. Hedef Doküman Yapısı

```text
docs/
├── README.md
├── 00-genel/
│   ├── 01-konvansiyonlar-ve-standartlar.md
│   └── 02-terimler-roller-ve-karar-kaydi.md
├── 01-strateji-pazar/
│   ├── 01-urun-vizyonu-ve-konumlandirma.md
│   ├── 02-pazar-ve-rakip-analizi.md
│   ├── 03-farklilasma-ve-deger-onermesi.md
│   └── 04-fiyatlandirma-ve-paketleme.md
├── 02-urun/
│   ├── 01-personalar-jtbd-ve-kullanici-yolculuklari.md
│   ├── 02-kanallar-web-mobil-self-servis.md
│   ├── 03-mvp-v1-v2-kapsam-kararlari.md
│   └── 04-urun-metrikleri-ve-basari-kriterleri.md
├── 03-moduller/
│   ├── 00-modul-format-ve-ortak-kararlar.md
│   ├── 01-core-tenant-auth-rbac.md
│   ├── 02-personel-ozluk-dokuman.md
│   ├── 03-izin-devamsizlik-onay.md
│   ├── 04-zaman-vardiya-pdks-puantaj.md
│   ├── 05-bordro-ucret-mevzuat.md
│   ├── 06-ise-alim-ats-aday-portali.md
│   ├── 07-performans-okr-360.md
│   ├── 08-egitim-yetkinlik-kariyer.md
│   ├── 09-organizasyon-kadro-pozisyon.md
│   ├── 10-self-servis-talep-duyuru.md
│   ├── 11-raporlama-people-analytics.md
│   └── 12-ai-ozellikleri-ve-governance.md
├── 04-mimari/
│   ├── 01-teknik-mimari-genel-bakis.md
│   ├── 02-cok-kiracilik-ve-veri-izolasyonu.md
│   ├── 03-teknoloji-kararlari-adr.md
│   └── 04-uygulama-yuzeyleri-web-mobil-api.md
├── 05-api-veri/
│   ├── 01-veritabani-modeli-ve-erd.md
│   ├── 02-api-standartlari-openapi-webhook.md
│   ├── 03-entegrasyonlar-sgk-banka-muhasebe-pdks.md
│   └── 04-veri-migrasyonu-import-export.md
├── 06-guvenlik-uyum/
│   ├── 01-kimlik-dogrulama-yetkilendirme.md
│   ├── 02-kvkk-gdpr-veri-yonetisimi.md
│   ├── 03-guvenlik-mimarisi-owasp-incident.md
│   └── 04-ai-guvenligi-ve-model-yonetisimi.md
├── 07-ui-ux/
│   ├── 01-tasarim-sistemi-ve-bilesenler.md
│   ├── 02-sayfa-akislari-ve-wireframe-notlari.md
│   └── 03-mobil-deneyim-stratejisi.md
├── 08-devops-test/
│   ├── 01-devops-surumleme-ortamlar.md
│   ├── 02-observability-slo-sla.md
│   └── 03-test-stratejisi-kalite-kapilari.md
└── 09-yurutme/
    ├── 01-yol-haritasi.md
    ├── 02-backlog-epic-user-story.md
    ├── 03-sprint-plani.md
    ├── 04-ekip-maliyet-operasyon-plani.md
    └── 05-lansman-pilot-hypercare.md
```

---

## 3. Her Doküman İçin Standart Kalite Formatı

Her ana dokümanda mümkün olduğunca şu bloklar olacak:

1. Amaç ve karar özeti
2. Kapsam içi / kapsam dışı
3. Kullanıcı rolleri ve sorumluluklar
4. MVP / V1 / V2 / Enterprise ayrımı
5. Ana akışlar
6. Ekran veya ürün yüzeyi etkisi
7. Veri modeli etkisi
8. API/entegrasyon etkisi
9. Yetki/RBAC/tenant izolasyonu etkisi
10. KVKK, güvenlik ve audit gereksinimi
11. Bildirim ve operasyon gereksinimi
12. Test senaryoları
13. Kabul kriterleri
14. Açık kararlar / riskler
15. İlgili doküman linkleri

Modül dokümanlarında bu format zorunlu olacak.

---

## 4. Uygulama Fazları

### Faz A — Temizlik ve Hazırlık

**Amaç:** Yanlışlıkla başlayan kod çalışmasını durdurmak, dokümantasyon branch'ini temizlemek.

**İşler:**

1. `apps/` klasörünü sil.
2. README'deki kod odaklı ifadeleri dokümantasyon fazına çevir.
3. Eski repo dokümanlarını arşivde tut.
4. `docs/README.md` ile yeni indeks oluştur.
5. Git status kontrolü yap.

**Kalite kapısı:**

- Repo içinde uygulama kodu olmamalı.
- Sadece docs ve README değişmeli.
- Eski dokümanlar kaybolmamalı, arşivde durmalı.

### Faz B — Temel Kanonik Dokümanlar

**Amaç:** Sonraki tüm dokümanların dilini, kapsamını, rol adlarını ve ürün kararlarını sabitlemek.

**Üretilecek dosyalar:**

1. `docs/README.md`
2. `docs/00-genel/01-konvansiyonlar-ve-standartlar.md`
3. `docs/00-genel/02-terimler-roller-ve-karar-kaydi.md`
4. `docs/03-moduller/00-modul-format-ve-ortak-kararlar.md`

**Referanslar:**

- Claude: `00-genel/01-konvansiyonlar-ve-standartlar.md`
- Codex: `docs/00-kaynak-ve-varsayimlar.md`, `docs/03-moduller/00-modul-format-ve-ortak-kararlar.md`
- Repo archive: `04-gereksinim-analizi.md`, `YOL_HARITASI.md`

**Kalite kapısı:**

- Her rol kodu tek yerde tanımlanmalı.
- MVP/V1/V2 ayrımı kanonik olmalı.
- Modül doküman formatı net olmalı.

### Faz C — Strateji ve Ürün Planı

**Amaç:** Ürünün ne olduğu, kime satıldığı, neden farklı olduğu, MVP'nin neyi çözdüğü netleşsin.

**Üretilecek dosyalar:**

1. `docs/01-strateji-pazar/01-urun-vizyonu-ve-konumlandirma.md`
2. `docs/01-strateji-pazar/02-pazar-ve-rakip-analizi.md`
3. `docs/01-strateji-pazar/03-farklilasma-ve-deger-onermesi.md`
4. `docs/01-strateji-pazar/04-fiyatlandirma-ve-paketleme.md`
5. `docs/02-urun/01-personalar-jtbd-ve-kullanici-yolculuklari.md`
6. `docs/02-urun/03-mvp-v1-v2-kapsam-kararlari.md`

**Referanslar:**

- Claude strateji dosyaları çok güçlü ana kaynak olacak.
- Codex ürün/persona dosyaları kontrol listesi olacak.
- Repo archive pazar/rakip/persona dosyaları yerel bağlam için taranacak.

**Kalite kapısı:**

- Sadece kurumsal laf değil, satılabilir konumlandırma olmalı.
- MVP gereğinden fazla büyütülmemeli.
- Hedef müşteri segmenti net olmalı: KOBİ, mid-market, enterprise ayrımı.

### Faz D — Modüller

**Amaç:** Her modül geliştiriciye, ürün yöneticisine ve QA'ye iş çıkaracak netlikte yazılsın.

**Sıra:**

1. Core / tenant / auth / RBAC
2. Personel / özlük / doküman
3. İzin / devamsızlık / onay
4. Zaman / vardiya / PDKS / puantaj
5. Bordro / ücret / mevzuat
6. Self-servis / talep / duyuru
7. Raporlama / people analytics
8. ATS
9. Performans
10. Eğitim / yetkinlik / kariyer
11. Organizasyon / kadro / pozisyon
12. AI özellikleri / governance

**Referanslar:**

- Codex modülleri tam kapsam listesi.
- Claude personel modülü kalite standardı.
- Repo archive modül dosyaları detay havuzu.

**Kalite kapısı:**

- Her modülde test senaryosu ve kabul kriteri olacak.
- Her modülde API/veri/yetki/KVKK etkisi olacak.
- Her modül MVP/V1/V2 ayrımına bağlanacak.

### Faz E — Mimari, API, Veri, Güvenlik

**Amaç:** Kod başlamadan teknik kararların gereksiz tartışmasını bitirmek.

**Üretilecek dosyalar:**

- `docs/04-mimari/*`
- `docs/05-api-veri/*`
- `docs/06-guvenlik-uyum/*`

**Kalite kapısı:**

- Teknoloji kararı tek yerde gerekçeli olmalı.
- Multi-tenant izolasyon modeli net olmalı.
- Auth/RBAC/ABAC/RLS ilişkisi net olmalı.
- KVKK, audit, saklama-imha, maskeleme, DSR konuları uygulanabilir olmalı.

### Faz F — UI/UX, DevOps, Test ve Yürütme

**Amaç:** Ürünü gerçekten canlıya götürecek tasarım, kalite, operasyon ve sprint omurgası yazılsın.

**Üretilecek dosyalar:**

- `docs/07-ui-ux/*`
- `docs/08-devops-test/*`
- `docs/09-yurutme/*`

**Kalite kapısı:**

- Sprint planı gerçekçi olmalı.
- Ekip/maliyet planı şişirilmemeli.
- Test stratejisi modül kabul kriterleriyle bağlanmalı.
- Lansman/pilot/hypercare somut olmalı.

---

## 5. Her Parça İçin İş Akışı

Her parça için bu sıra izlenecek:

1. İlgili Claude dosyaları okunur.
2. İlgili Codex dosyaları okunur.
3. İlgili repo archive dosyaları okunur.
4. Yeni doküman yazılır.
5. İç linkler ve dosya yolları kontrol edilir.
6. Kelime/başlık yoğunluğu kontrol edilir.
7. Eksik zorunlu bloklar kontrol edilir.
8. Kullanıcıya kısa özet verilir.
9. Kullanıcı onayı sonrası sonraki parçaya geçilir.

---

## 6. Otomatik Kalite Kontrol Listesi

Her üretim turundan sonra şu kontroller çalıştırılmalı:

```bash
cd /opt/data/repos/Ik
python - <<'PY'
from pathlib import Path
import re
root = Path('docs')
for p in sorted(root.rglob('*.md')):
    text = p.read_text(errors='ignore')
    if '_archive' in p.parts:
        continue
    headings = len(re.findall(r'^#{1,6}\\s+', text, re.M))
    words = len(re.findall(r'\\w+', text, re.U))
    if words < 500:
        print('LOW_WORDS', p, words)
    if headings < 5 and p.name != 'README.md':
        print('LOW_HEADINGS', p, headings)
PY
```

İç link kontrolü:

```bash
cd /opt/data/repos/Ik
python - <<'PY'
from pathlib import Path
import re
root = Path('docs')
broken = []
for p in root.rglob('*.md'):
    if '_archive' in p.parts:
        continue
    text = p.read_text(errors='ignore')
    for m in re.finditer(r'\[[^\]]+\]\(([^)]+)\)', text):
        href = m.group(1).split('#')[0]
        if not href or href.startswith(('http://', 'https://', 'mailto:')):
            continue
        target = (p.parent / href).resolve()
        if not target.exists():
            broken.append((str(p), href))
for item in broken:
    print('BROKEN_LINK', item[0], '->', item[1])
raise SystemExit(1 if broken else 0)
PY
```

---

## 7. İlk Uygulama Paketi Önerisi

İlk turda sadece şu 4 dosya yapılmalı:

1. `README.md` — kod/proje değil, dokümantasyon fazı açıklaması.
2. `docs/README.md` — yeni doküman indeksi.
3. `docs/00-genel/01-konvansiyonlar-ve-standartlar.md` — kanonik kararlar.
4. `docs/03-moduller/00-modul-format-ve-ortak-kararlar.md` — modül yazım standardı.

Bu 4 dosya bitmeden modül detaylarına geçilmemeli.

---

## 8. Riskler

1. **Aşırı detay riski:** Her şeyi ilk dokümanda çözmeye çalışırsak doküman şişer. Çözüm: kanonik karar + linkleme.
2. **Claude yarım kaldı riski:** Eksik Claude dosyaları Codex ve repo archive ile tamamlanacak.
3. **Tekrar riski:** Fiyatlandırma, persona, MVP kapsamı birçok dosyada tekrar edebilir. Çözüm: ana karar dokümanına link.
4. **Kod aşamasına erken geçme riski:** Kullanıcı onayı olmadan `apps/`, `infra/`, CI oluşturulmayacak.
5. **Kalite düşmesi riski:** Her parça zorunlu kalite formatından geçirilecek.

---

## 9. Kullanıcı Onayı Gereken Noktalar

1. Ürün çalışma adı ne olsun?
   - Öneri: geçici olarak `PeopleCore HRMS`
   - Alternatif: `IK`, `IK Core`, `HRX`, başka marka.

2. İlk hedef müşteri segmenti ne olsun?
   - Öneri: Türkiye KOBİ + mid-market; enterprise daha sonra.

3. MVP modülleri kesin mi?
   - Öneri: Tenant/Auth + Personel/Özlük + İzin/Onay + Self-servis + Temel rapor + KVKK/Audit.

4. Eski repo dokümanları arşivde kalsın mı?
   - Öneri: Evet, `docs/_archive/2026-07-03-original` içinde kalsın.

---

## 10. Sonraki Adım

Kullanıcı onay verirse ilk uygulama turu:

- Yanlışlıkla açılan kod iskeleti kaldırılır.
- İlk 4 doküman oluşturulur.
- Kalite kontrolleri çalıştırılır.
- Commit hazırlanır ama push öncesi kullanıcıya özet verilir.

Commit mesajı önerisi:

```bash
git commit -m "docs: establish HRMS documentation foundation"
```
