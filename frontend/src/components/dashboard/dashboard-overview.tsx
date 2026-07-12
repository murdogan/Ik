"use client";

import { useSession } from "@/components/session/session-provider";

import styles from "./tenant-shell.module.css";

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

export function DashboardOverview() {
  const { user } = useSession();
  const name = displayName(user.full_name, user.email);

  return (
    <section aria-labelledby="dashboard-title">
      <div className={styles.welcome}>
        <span>Tenant çalışma alanı</span>
        <h1 id="dashboard-title">Merhaba, {name}</h1>
        <p>
          {user.tenant.name} çalışma alanına güvenli biçimde giriş yaptınız. Wealthy Falcon HR
          ana ekranınız kullanıma hazır.
        </p>
      </div>

      <div className={styles.cards}>
        <article className={styles.card}>
          <span className={styles.cardIcon} aria-hidden="true">
            ✓
          </span>
          <div>
            <small>Oturum durumu</small>
            <h2>Güvenli oturum etkin</h2>
            <p>Kısa ömürlü erişim ve yenilenen güvenli oturum ile bağlısınız.</p>
          </div>
        </article>

        <article className={styles.card}>
          <span className={`${styles.cardIcon} ${styles.blueIcon}`} aria-hidden="true">
            W
          </span>
          <div>
            <small>Kurum</small>
            <h2>{user.tenant.name}</h2>
            <p>Çalışma alanınız: {user.tenant.name}</p>
          </div>
        </article>
      </div>
    </section>
  );
}
