import type { ReactNode } from "react";

import styles from "./auth.module.css";

interface AuthShellProps {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  surface?: "tenant" | "platform";
}

function Brand({ platform = false }: { platform?: boolean }) {
  return (
    <div
      className={styles.brand}
      aria-label={platform ? "Wealthy Falcon HR Platform" : "Wealthy Falcon HR"}
    >
      <span className={styles.brandMark} aria-hidden="true">
        WF
      </span>
      <span className={styles.brandName}>
        Wealthy Falcon HR{platform ? " Platform" : ""}
      </span>
    </div>
  );
}

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
  surface = "tenant",
}: AuthShellProps) {
  const isPlatform = surface === "platform";
  return (
    <main
      className={`${styles.page} ${isPlatform ? styles.platformPage : ""}`}
      data-auth-surface={surface}
    >
      <section className={styles.shell} aria-labelledby="auth-page-title">
        <aside className={`${styles.story} ${isPlatform ? styles.platformStory : ""}`}>
          <Brand platform={isPlatform} />
          <div className={styles.storyContent}>
            <span className={styles.storyKicker}>
              <span className={styles.statusDot} aria-hidden="true" />
              {isPlatform
                ? "İzole platform yönetim alanı"
                : "Modern ve sade İK deneyimi"}
            </span>
            <div className={styles.storyTitle}>
              {isPlatform
                ? "Platform operasyonları için ayrı güvenlik sınırı."
                : "İnsan kaynakları, ekibiniz kadar akıcı."}
            </div>
            <p>
              {isPlatform
                ? "Platform rolleri, oturumları ve denetim izi müşteri çalışma alanlarından bağımsız doğrulanır."
                : "Çalışan bilgileri ve günlük İK işleri, güvenli ve mobil uyumlu tek bir çalışma alanında."}
            </p>
          </div>
          <ul className={styles.benefits} aria-label="Ürün özellikleri">
            <li>
              <span aria-hidden="true">✓</span>{" "}
              {isPlatform ? "Platform rolü zorunlu" : "Kuruma özel güvenli erişim"}
            </li>
            <li>
              <span aria-hidden="true">✓</span>{" "}
              {isPlatform ? "MFA ve step-up hazırlığı" : "Her ekranda mobil uyum"}
            </li>
          </ul>
        </aside>

        <div className={styles.formColumn}>
          <div className={styles.mobileBrand}>
            <Brand platform={isPlatform} />
          </div>
          <div className={styles.card}>
            <span className={styles.eyebrow}>{eyebrow}</span>
            <h1 id="auth-page-title">{title}</h1>
            <p className={styles.description}>{description}</p>
            {children}
          </div>
          <p className={styles.securityNote}>
            {isPlatform
              ? "Platform parolanızı veya doğrulama bilgilerinizi kimseyle paylaşmayın."
              : "Parolanızı veya davet bağlantınızı kimseyle paylaşmayın."}
          </p>
        </div>
      </section>
    </main>
  );
}
