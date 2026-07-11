import type { ReactNode } from "react";

import styles from "./auth.module.css";

interface AuthShellProps {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}

function Brand() {
  return (
    <div className={styles.brand} aria-label="Wealthy Falcon HR">
      <span className={styles.brandMark} aria-hidden="true">
        WF
      </span>
      <span className={styles.brandName}>Wealthy Falcon HR</span>
    </div>
  );
}

export function AuthShell({ eyebrow, title, description, children }: AuthShellProps) {
  return (
    <main className={styles.page}>
      <section className={styles.shell} aria-labelledby="auth-page-title">
        <aside className={styles.story}>
          <Brand />
          <div className={styles.storyContent}>
            <span className={styles.storyKicker}>
              <span className={styles.statusDot} aria-hidden="true" />
              Modern ve sade İK deneyimi
            </span>
            <div className={styles.storyTitle}>İnsan kaynakları, ekibiniz kadar akıcı.</div>
            <p>
              Çalışan bilgileri ve günlük İK işleri, güvenli ve mobil uyumlu tek bir
              çalışma alanında.
            </p>
          </div>
          <ul className={styles.benefits} aria-label="Ürün özellikleri">
            <li>
              <span aria-hidden="true">✓</span> Kuruma özel güvenli erişim
            </li>
            <li>
              <span aria-hidden="true">✓</span> Her ekranda mobil uyum
            </li>
          </ul>
        </aside>

        <div className={styles.formColumn}>
          <div className={styles.mobileBrand}>
            <Brand />
          </div>
          <div className={styles.card}>
            <span className={styles.eyebrow}>{eyebrow}</span>
            <h1 id="auth-page-title">{title}</h1>
            <p className={styles.description}>{description}</p>
            {children}
          </div>
          <p className={styles.securityNote}>
            Parolanızı veya davet bağlantınızı kimseyle paylaşmayın.
          </p>
        </div>
      </section>
    </main>
  );
}
