import type { Metadata } from "next";
import Link from "next/link";

import styles from "./landing.module.css";

export const metadata: Metadata = {
  title: "Modern insan operasyonları",
  description:
    "Wealthy Falcon HR ile çalışan, izin, yetki ve denetim süreçlerini güvenli bir merkezden yönetin.",
};

const capabilities = [
  {
    label: "İnsan yönetimi",
    title: "Ekibiniz tek, anlaşılır bir çalışma alanında",
    description:
      "Çalışan kayıtlarını, hesap davetlerini ve organizasyon görünümünü tenant izolasyonuyla yönetin.",
  },
  {
    label: "Yetki kontrolü",
    title: "Doğru kişiye yalnız doğru erişim",
    description:
      "Rol tabanlı erişim, güvenli oturumlar ve varsayılan ret politikasıyla kritik verileri koruyun.",
  },
  {
    label: "Denetlenebilirlik",
    title: "Her önemli hareket izlenebilir",
    description:
      "Değiştirilemez audit kayıtlarıyla giriş, davet, rol ve yönetim işlemlerini takip edin.",
  },
] as const;

const metrics = [
  ["39", "Canlı API operasyonu"],
  ["7", "Hazır ürün ekranı"],
  ["7/7", "Tarayıcı akışı geçti"],
] as const;

export default function HomePage() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav} aria-label="Ana navigasyon">
        <Link className={styles.brand} href="/">
          <span className={styles.mark} aria-hidden="true">WF</span>
          <span>
            <strong>Wealthy Falcon</strong>
            <small>Human Resources</small>
          </span>
        </Link>
        <div className={styles.navActions}>
          <a
            className={styles.statusLink}
            href="https://capability-firefox-following-cookie.trycloudflare.com/health"
            rel="noreferrer"
            target="_blank"
          >
            <span aria-hidden="true" /> Sistem durumu
          </a>
          <Link className={styles.platformLink} href="/platform/login">
            Platform yönetimi
          </Link>
          <Link className={styles.loginLink} href="/login">Giriş yap</Link>
        </div>
      </nav>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>İnsan operasyonlarında güvenli sadelik</p>
          <h1>Ekibiniz büyürken<br />operasyonunuz hafiflesin.</h1>
          <p className={styles.lead}>
            Çalışan yönetimi, güvenli erişim ve denetim süreçleri tek bir modern İK çalışma
            alanında. Daha az operasyon yükü, daha görünür bir organizasyon.
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.primaryButton} href="/login">
              Çalışma alanına gir <span aria-hidden="true">→</span>
            </Link>
            <a
              className={styles.secondaryButton}
              href="https://capability-firefox-following-cookie.trycloudflare.com/docs"
              rel="noreferrer"
              target="_blank"
            >
              API&apos;yi incele
            </a>
          </div>
          <p className={styles.securityNote}>
            <span aria-hidden="true">✓</span> Tenant izolasyonu · RBAC · Append-only audit
          </p>
        </div>

        <div className={styles.preview} aria-label="Ürün paneli önizlemesi">
          <div className={styles.previewTop}>
            <div className={styles.previewBrand}><span>WF</span> Yönetim Merkezi</div>
            <span className={styles.livePill}>● Canlı</span>
          </div>
          <div className={styles.previewBody}>
            <aside className={styles.previewSidebar}>
              <span className={styles.activeItem}>Genel görünüm</span>
              <span>Çalışanlar</span>
              <span>İzin yönetimi</span>
              <span>Kullanıcılar</span>
              <span>Audit kayıtları</span>
            </aside>
            <div className={styles.previewContent}>
              <div className={styles.previewHeading}>
                <div><small>12 Temmuz</small><strong>Günaydın, İK ekibi</strong></div>
                <span>Yeni davet +</span>
              </div>
              <div className={styles.statGrid}>
                <article><small>Aktif çalışan</small><strong>128</strong><em>↑ %8 büyüme</em></article>
                <article><small>Bekleyen talepler</small><strong>12</strong><em>4 yeni</em></article>
                <article><small>Aktif kullanıcı</small><strong>42</strong><em>Güvenli</em></article>
              </div>
              <div className={styles.chartCard}>
                <div><strong>Organizasyon görünümü</strong><small>Son 6 ay</small></div>
                <div className={styles.chart} aria-hidden="true">
                  {[42, 55, 49, 68, 74, 89, 82, 95, 104, 112, 108, 126].map((height, index) => (
                    <span key={index} style={{ height: `${height / 1.35}px` }} />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className={styles.metrics} aria-label="Platform metrikleri">
        {metrics.map(([value, label]) => (
          <div key={label}><strong>{value}</strong><span>{label}</span></div>
        ))}
      </section>

      <section className={styles.capabilities}>
        <div className={styles.sectionHeading}>
          <p>Temelden güvenli</p>
          <h2>İK ekibinin ihtiyacı olan çekirdek akışlar hazır.</h2>
        </div>
        <div className={styles.cardGrid}>
          {capabilities.map((item, index) => (
            <article key={item.label}>
              <span className={styles.cardNumber}>0{index + 1}</span>
              <small>{item.label}</small>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.brand}><span className={styles.mark}>WF</span><strong>Wealthy Falcon HR</strong></div>
        <p>Güvenli, tenant-aware insan operasyonları platformu.</p>
        <div className={styles.footerLinks}>
          <Link href="/platform/login">Platform yönetimi</Link>
          <Link href="/login">Giriş yap →</Link>
        </div>
      </footer>
    </main>
  );
}
