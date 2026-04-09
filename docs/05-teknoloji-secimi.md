# 05 — Teknoloji Seçimi

> **Hazırlanma Tarihi:** 9 Nisan 2026  
> **Kapsam:** Frontend, mobil, backend, veritabanı, altyapı, entegrasyon ve operasyon teknolojilerinin değerlendirilmesi ve seçimi  
> **Referans:** 01-piyasa-arastirmasi.md, 02-rakip-analizi.md, 03-hedef-kitle-ve-kullanici-personalar.md, 04-gereksinim-analizi.md

---

## 1. Amaç

Bu dokümanın amacı, İnsan Kaynakları Yönetim Sistemi için kullanılacak teknoloji stack'ini netleştirmek ve sonraki dokümanlar olan sistem mimarisi, veritabanı tasarımı, API tasarımı ve entegrasyon haritası için ortak teknik zemini oluşturmaktır.

Teknoloji seçimi yapılırken aşağıdaki ana hedefler esas alınmıştır:

- MVP'nin küçük bir ekiple hızlı geliştirilebilmesi
- 1.000 eşzamanlı kullanıcı ve 100.000+ çalışan kaydı hedefinin desteklenmesi
- KVKK, veri lokalizasyonu ve güvenlik gereksinimlerinin karşılanması
- Web + mobil deneyimin aynı ürün vizyonunda sürdürülebilmesi
- SGK, e-Devlet, muhasebe, SMS, e-posta ve PDKS entegrasyonlarına uygunluk
- Türk iş hukuku ve bordro mevzuatındaki değişikliklere hızlı adapte olunabilmesi

---

## 2. Karar İlkeleri

Teknoloji kararlarında aşağıdaki ilkeler benimsenmiştir:

1. **Hızlı ürünleme:** MVP için geliştirici verimliliği yüksek teknolojiler tercih edilmiştir.
2. **Modülerlik:** Başlangıçta gereksiz dağıtık sistem karmaşıklığına girilmeden, modüler monolith yaklaşımı desteklenmiştir.
3. **Operasyonel sadelik:** Küçük ekip için yönetilebilir altyapı ve gözlemlenebilirlik önceliklendirilmiştir.
4. **Yerelleştirme uyumu:** Türkiye mevzuatı, veri saklama ve yerel entegrasyon ihtiyaçlarına uygun çözümler seçilmiştir.
5. **Genişleyebilirlik:** MVP sonrasında ATS, performans, bordro, vardiya ve analitik modüllerinin eklenmesi hedeflenmiştir.

---

## 3. Değerlendirme Kriterleri

| Kriter | Açıklama | Öncelik |
|----|----|----|
| Geliştirme Hızı | Küçük ekiple hızlı teslim ve iterasyon | Çok Yüksek |
| Performans | < 200ms API, < 2s sayfa yükleme, < 300ms arama | Çok Yüksek |
| Ölçeklenebilirlik | 1.000 eşzamanlı kullanıcı, 100.000+ çalışan kaydı | Yüksek |
| Güvenlik | AES-256, TLS 1.3, RBAC, audit log, OWASP uyumu | Çok Yüksek |
| Entegrasyon Yeteneği | REST API, webhook, SGK, banka, SMS, e-posta, PDKS | Çok Yüksek |
| Mobil Uyum | Çalışan ve yönetici işlemlerinin mobil öncelikli olması | Çok Yüksek |
| Veri Lokalizasyonu | Türkiye'de barındırma veya self-host esnekliği | Çok Yüksek |
| Operasyonel Maliyet | MVP aşamasında düşük operasyonel yük | Yüksek |
| Ekip Uygunluğu | Python, TypeScript ve modern ürün geliştirme akışına uyum | Yüksek |

---

## 4. Nihai Teknoloji Stack'i

| Katman | Seçilen Teknoloji | Karar |
|----|----|----|
| Web Frontend | Next.js 15 + TypeScript | Seçildi |
| Web UI | Tailwind CSS + shadcn/ui | Seçildi |
| Mobil Uygulama | Flutter + Dart | Seçildi |
| Backend API | FastAPI + Python 3.12 | Seçildi |
| ORM | SQLAlchemy 2.0 + Alembic | Seçildi |
| Veritabanı | PostgreSQL 17 | Seçildi |
| Cache | Redis 7 | Seçildi |
| Arka Plan İşleri | Celery + Redis | Seçildi |
| Dosya Depolama | MinIO (S3 uyumlu) | Seçildi |
| Kimlik Doğrulama | JWT + Refresh Token + MFA altyapısı | Seçildi |
| Arama | PostgreSQL Full-Text Search, gerektiğinde Meilisearch | Faz 1'de PG, Faz 2'de opsiyonel |
| Realtime | WebSocket / SSE | Seçildi |
| PDF Üretimi | WeasyPrint | Seçildi |
| Excel İşleme | openpyxl + pandas | Seçildi |
| AI/ML | LangChain + OpenAI | Kontrollü kullanım ile seçildi |
| Container | Docker + Docker Compose | Seçildi |
| CI/CD | GitHub Actions | Seçildi |
| Monitoring | Grafana + Prometheus + Sentry | Seçildi |

---

## 5. Katman Bazlı Değerlendirme ve Gerekçe

### 5.1 Web Frontend

### Aday Teknolojiler

| Teknoloji | Artılar | Eksiler | Sonuç |
|----|----|----|----|
| Next.js 15 + TypeScript | SSR/ISR, güçlü ekosistem, hızlı ürünleme, SEO ve panel performansı, type safety | React ekosistemi karmaşıklık yaratabilir | **Seçildi** |
| Vue 3 + Nuxt | Öğrenmesi kolay, iyi DX | Ekip ve ekosistem tercihi açısından ikinci sırada | Elendi |
| Angular | Kurumsal yapı ve disiplin güçlü | MVP için fazla ağır ve daha yavaş iterasyon | Elendi |

### Seçim Gerekçesi

Next.js 15, hem yönetim panelleri hem çalışan self-servis arayüzleri için güçlü bir temel sağlar. SSR ve modern routing yapısı sayesinde ilk yükleme performansı hedeflerine ulaşmak kolaylaşır. TypeScript ise hem ekip içi kaliteyi artırır hem de backend sözleşmeleriyle daha güvenli entegrasyon sağlar.

### Frontend Kararları

- App Router kullanılacaktır.
- Server Components, veri okuma ağırlıklı ekranlarda tercih edilecektir.
- Client Components sadece etkileşimli alanlarda kullanılacaktır.
- Veri katmanında TanStack Query tercih edilecektir.
- Yerel UI state için Zustand kullanılacaktır.
- Form validasyonu için Zod tercih edilecektir.
- Bileşen tabanı olarak Tailwind CSS + shadcn/ui kullanılacaktır.

---

### 5.2 Mobil Uygulama

### Aday Teknolojiler

| Teknoloji | Artılar | Eksiler | Sonuç |
|----|----|----|----|
| Flutter + Dart | Tek codebase, yüksek performans, güçlü form ve offline desteği | Web tarafı ile tamamen ortak kod paylaşımı yok | **Seçildi** |
| React Native | JS/TS ekibi için yakın teknoloji | Kompleks native eklentilerde bakım riski | Elendi |
| PWA | Hızlı başlangıç, düşük maliyet | Push, offline ve kurumsal mobil deneyimde sınırlı | Destekleyici, ana çözüm değil |

### Seçim Gerekçesi

Personalar ve gereksinimler mobil önceliği net biçimde işaret etmektedir. Özellikle izin talebi, onay, bildirimler, vardiya görüntüleme ve personel bilgilerine erişim için native hissiyat veren, performanslı ve kararlı bir mobil çözüm gereklidir. Flutter bu noktada tek ekipten iki platforma yüksek kalite sunar.

### Mobil Kararları

- State management için Riverpod kullanılacaktır.
- Yerel saklama için Hive veya SQLite tabanlı yapı kullanılacaktır.
- Push notification için Firebase Cloud Messaging kullanılacaktır.
- Kritik ekranlar offline okunabilir şekilde tasarlanacaktır.

---

### 5.3 Backend

### Aday Teknolojiler

| Teknoloji | Artılar | Eksiler | Sonuç |
|----|----|----|----|
| FastAPI + Python 3.12 | Çok hızlı API geliştirme, async destek, güçlü validasyon, Python ekosistemi, dokümantasyon üretimi | Uzun vadede çok yüksek CPU-bound işlerde dikkat ister | **Seçildi** |
| Node.js + NestJS | Modüler yapı güçlü, TypeScript ile tek dil avantajı | Bordro, veri işleme ve analitik tarafında Python kadar güçlü değil | Elendi |
| Go | Yüksek performans, düşük kaynak kullanımı | MVP geliştirme hızı ve ekip verimliliği açısından daha yavaş | Elendi |

### Seçim Gerekçesi

FastAPI, hem REST API hem webhook hem de entegrasyon servisleri için uygun bir zemindir. Pydantic tabanlı veri doğrulama, otomatik OpenAPI üretimi ve Python ekosistemi sayesinde özellikle bordro, veri işleme, Excel import/export, PDF üretimi ve ileride AI destekli modüller için yüksek verim sağlar.

### Backend Kararları

- Mimari yaklaşım olarak **modüler monolith** ile başlanacaktır.
- Domain bazlı modüller ayrılacaktır: auth, personel, izin, self-servis, bildirim, raporlama, entegrasyon.
- API standardı REST olacaktır.
- Harici sistemler için webhook desteği sağlanacaktır.
- Async endpoint'ler uygun alanlarda kullanılacaktır.
- Arka plan işleri Celery üzerinden ayrıştırılacaktır.

---

### 5.4 Veritabanı

### Aday Teknolojiler

| Teknoloji | Artılar | Eksiler | Sonuç |
|----|----|----|----|
| PostgreSQL 17 | Güçlü ilişkisel model, JSONB, full-text search, transaction güvenliği, RLS | Karmaşık sorgularda tuning ihtiyacı olabilir | **Seçildi** |
| MySQL 8 | Yaygın kullanım, operasyonel tanınırlık | Gelişmiş yetkilendirme ve analitik esneklik PostgreSQL kadar güçlü değil | Elendi |
| MongoDB | Şema esnekliği | İK, bordro, izin, audit ve raporlama için ilişkisel yapı daha uygun | Elendi |

### Seçim Gerekçesi

İK sistemlerinde personel, organizasyon, izin, vardiya, bordro, audit log ve yetkilendirme gibi veriler yoğun ilişkiseldir. PostgreSQL 17, bu ihtiyaçları güçlü biçimde destekler. Ayrıca row-level security, JSONB, view, materialized view ve full-text search özellikleri ileride raporlama ve tenant izolasyonu için avantaj sağlar.

### Veritabanı Kararları

- Başlangıçta shared database + tenant_id yaklaşımı kullanılacaktır.
- Tenant izolasyonu uygulama katmanı ve gerektiğinde PostgreSQL RLS ile desteklenecektir.
- Migration yönetimi Alembic ile yapılacaktır.
- Audit log ve kritik hareketler ayrı tablolarla izlenecektir.
- Hassas alanlar için kolon bazlı şifreleme değerlendirilecektir.

---

### 5.5 Cache ve Kuyruk

### Seçilen Teknolojiler

| Alan | Teknoloji | Gerekçe |
|----|----|----|
| Cache | Redis 7 | Oturum, rate limiting, kısa ömürlü veri, bildirim ve performans optimizasyonu |
| Queue | Celery + Redis | PDF üretimi, toplu içe aktarma, e-posta, bordro hesaplama, rapor işleme |

### Gerekçe

Redis hem basit cache katmanı hem de Celery broker/back-end olarak MVP aşamasında yeterlidir. RabbitMQ gibi ayrı bir sistem operasyonel olarak daha ağır olacağından ilk aşamada tercih edilmemiştir. İleri aşamalarda iş akışları çok karmaşık hale gelirse kuyruk altyapısı yeniden değerlendirilebilir.

---

### 5.6 Dosya Depolama

### Aday Teknolojiler

| Teknoloji | Artılar | Eksiler | Sonuç |
|----|----|----|----|
| MinIO | S3 uyumlu, self-host, veri lokalizasyonu dostu | Operasyon ekibi disiplin ister | **Seçildi** |
| AWS S3 | Çok olgun servis | Veri lokalizasyonu ve regülasyon açısından ek değerlendirme gerekir | Kısmi alternatif |
| Yerel disk | Basit kurulum | Ölçeklenme, yedekleme ve erişim yönetimi zayıf | Elendi |

### Seçim Gerekçesi

Özlük belgeleri, sözleşmeler, raporlar, bordrolar ve aday CV'leri için nesne depolama gereklidir. MinIO, S3 uyumlu yapısı sayesinde uygulama tarafında standardizasyon sağlar ve Türkiye'de self-host edilebildiği için KVKK ve veri lokalizasyonu gereksinimlerine uyumludur.

---

### 5.7 Kimlik Doğrulama ve Yetkilendirme

Bu ürünün güvenlik gereksinimleri yüksek olduğu için kimlik ve yetki tasarımı teknoloji seçiminin merkezindedir.

### Kararlar

- Backend tarafında JWT access token + refresh token modeli kullanılacaktır.
- MFA desteği mimarinin ilk sürümünden itibaren düşünülerek tasarlanacaktır.
- Rol bazlı erişim kontrolü zorunlu olacaktır.
- Audit log altyapısı MVP'de yer alacaktır.
- Rate limiting Redis tabanlı uygulanacaktır.
- Web ve mobil istemciler aynı auth servis mantığını kullanacaktır.

### Not

Kurumsal müşteriler için SSO / LDAP entegrasyonu MVP kapsamı dışında tutulur; ancak mimari buna genişleyebilir tasarlanacaktır.

---

### 5.8 Arama ve Raporlama

### Arama Kararı

MVP aşamasında çalışan arama, filtreleme ve temel arama ihtiyaçları için PostgreSQL full-text search kullanılacaktır. Bu tercih operasyonel sadelik sağlar ve ek servis maliyetini azaltır.

### Meilisearch Ne Zaman Gerekir?

Aşağıdaki durumlarda ayrı arama motoru devreye alınacaktır:

- 100.000+ kayıt üzerinde gelişmiş typo-tolerant arama ihtiyacı oluşursa
- Aday havuzu ve CV araması semantik/çok alanlı hale gelirse
- Kullanıcı deneyimi açısından anlık önerili arama beklenirse

---

### 5.9 AI/ML Katmanı

### Seçim

| Teknoloji | Kullanım Alanı | Karar |
|----|----|----|
| LangChain + OpenAI | CV özetleme, aday eşleştirme, doküman sınıflandırma, destek asistanı | Kontrollü kullanım ile seçildi |

### Sınırlar

- AI özellikleri MVP'nin çekirdek fonksiyonlarından bağımsız olacaktır.
- Hassas çalışan verileri doğrudan dış modele gönderilmeyecektir.
- KVKK etkisi olan alanlarda anonimleştirme veya maskeleme uygulanacaktır.
- Gerekirse yerel LLM seçeneği sonraki fazlarda değerlendirilecektir.

Bu karar, AI'yı ürünün farklılaştırıcı bir özelliği olarak konumlandırır; ancak çekirdek İK süreçlerinin AI'a bağımlı hale gelmesini engeller.

---

### 5.10 PDF ve Doküman Üretimi

### Seçim

| Teknoloji | Kullanım | Karar |
|----|----|----|
| WeasyPrint | Bordro, sözleşme, resmi çıktı ve rapor PDF üretimi | Seçildi |

### Gerekçe

HTML/CSS tabanlı şablonlardan profesyonel PDF üretmek için uygun ve Python ekosistemi ile doğal uyumlu bir çözümdür. Toplu bordro üretimi gibi yüksek hacimli işlemler Celery üzerinden arka planda çalıştırılacaktır.

---

### 5.11 DevOps ve Operasyon

### Seçilen Teknolojiler

| Alan | Teknoloji | Karar |
|----|----|----|
| Container | Docker | Seçildi |
| Lokal orkestrasyon | Docker Compose | Seçildi |
| CI/CD | GitHub Actions | Seçildi |
| Hata izleme | Sentry | Seçildi |
| Metrik toplama | Prometheus | Seçildi |
| Gözlemleme panelleri | Grafana | Seçildi |

### Gerekçe

MVP aşamasında Kubernetes gibi ağır bir orkestrasyon çözümüne ihtiyaç yoktur. Docker Compose, geliştirme ve ilk dağıtım senaryoları için yeterlidir. GitHub Actions, repo tabanlı otomasyon ve hızlı kurulum sunar. Sentry ve Prometheus/Grafana kombinasyonu ise hem uygulama hatalarını hem de performans ölçümlerini takip etmeye uygundur.

---

## 6. Seçilmeyen Teknolojiler ve Nedenleri

| Teknoloji | Neden Seçilmedi |
|----|----|
| Angular | MVP için fazla ağır ve iterasyon maliyeti daha yüksek |
| React Native | Flutter kadar tutarlı mobil deneyim ve performans beklentisini karşılamıyor |
| NestJS | Tek dil avantajına rağmen Python'un veri işleme ve bordro tarafındaki verimliliği daha uygun |
| Go | Ekibin hız hedefi ve ürünleme önceliği açısından erken aşamada fazla maliyetli |
| MongoDB | İlişkisel ve mevzuat odaklı İK verisi için daha az uygun |
| RabbitMQ | İlk aşamada Redis + Celery yeterli; ek operasyon yükü oluşturur |
| Kubernetes | MVP aşamasında gereksiz operasyonel karmaşıklık |

---

## 7. Gereksinimlerle Uyum Matrisi

| Gereksinim | Teknoloji Karşılığı |
|----|----|
| Web + mobil uyum | Next.js + Flutter |
| < 2s sayfa yükleme | Next.js SSR, cache stratejileri |
| < 200ms API | FastAPI, Redis, optimize SQL |
| < 300ms arama | PostgreSQL index + full-text search |
| 1.000 eşzamanlı kullanıcı | Stateless API, Redis, container bazlı ölçekleme |
| 100.000+ çalışan kaydı | PostgreSQL 17, doğru indeksleme ve partition opsiyonları |
| Dosya depolama | MinIO |
| KVKK ve veri lokalizasyonu | Self-host edilebilir PostgreSQL + MinIO + Docker altyapısı |
| RBAC, audit log, MFA | FastAPI auth katmanı + Redis + denetim kayıtları |
| SGK, banka, muhasebe, PDKS entegrasyonları | REST API, webhook, Python servisleri |
| Excel içe aktarma | openpyxl + pandas |
| Bordro PDF üretimi | WeasyPrint + Celery |
| Bildirim ve async işler | Redis + Celery + push notification servisleri |

---

## 8. Mimari Yönelim

Bu teknoloji seçimlerinin sonucunda önerilen başlangıç mimarisi aşağıdaki gibidir:

- Web ve mobil istemciler ayrı uygulamalar olacaktır.
- Backend, modüler monolith olarak tek deployable servis ile başlayacaktır.
- Auth, personel, izin, self-servis, raporlama ve entegrasyon modülleri kod seviyesinde ayrıştırılacaktır.
- Veritabanı başlangıçta tek PostgreSQL kümesinde tutulacaktır.
- Cache, rate limit, job broker ve geçici veri ihtiyaçları Redis ile çözülecektir.
- Dosya ve doküman saklama MinIO üzerinde olacaktır.
- Ağır işler ve zamanlanmış süreçler Celery worker'larında çalışacaktır.

Bu yönelim, Faz 6 kapsamında altyapı ve deployment dokümanına geçerken düşük karmaşıklıkla yüksek genişleme alanı sunar.

---

## 9. Riskler ve Önlemler

| Risk | Etki | Önlem |
|----|----|----|
| Python worker yükünün artması | Bordro, PDF ve entegrasyon işlerinde yavaşlama | Celery ile ayrıştırma, job queue takibi, yatay worker ölçekleme |
| Flutter + Next.js ile çift frontend ekosistemi | Takım koordinasyonu zorlaşabilir | Ortak tasarım sistemi, ortak API sözleşmeleri, net modül sınırları |
| Redis'in hem cache hem queue olarak kullanılması | Tek noktada darboğaz oluşabilir | İzleme, ayrı instance veya role-based ayrım |
| OpenAI kullanımında KVKK riski | Veri ihlali veya uyum problemi | Veri maskeleme, anonimleştirme, AI kapsamını sınırlama |
| PostgreSQL aramasının zamanla yetersiz kalması | Arama deneyiminde yavaşlama | Meilisearch'e geçiş için mimari hazırlık |

---

## 10. Sonuç

Bu proje için seçilen teknoloji stack'i aşağıdaki temel dengeyi kurmaktadır:

- **Hızlı MVP geliştirme** için Next.js + FastAPI + PostgreSQL
- **Mobil öncelikli deneyim** için Flutter
- **Regülasyon ve veri kontrolü** için self-host edilebilir PostgreSQL + MinIO + Docker
- **Operasyonel sadelik** için modüler monolith + Redis + Celery
- **Gelecek genişleme alanı** için AI, arama, entegrasyon ve gözlemlenebilirlik katmanları

Bu karar seti ile bir sonraki adımda [06-sistem-mimarisi.md](06-sistem-mimarisi.md) dokümanında servis sınırları, bileşenler arası iletişim ve dağıtım topolojisi detaylandırılacaktır.