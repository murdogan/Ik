"use client";

import Link from "next/link";

import { useSession } from "@/components/session/session-provider";

import styles from "./tenant-shell.module.css";

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

export function TenantShell() {
  const { user, isLoggingOut, logoutError, signOut } = useSession();
  const name = displayName(user.full_name, user.email);

  return (
    <div className={styles.application}>
      <aside className={styles.sidebar}>
        <div className={styles.brand} aria-label="Wealthy Falcon HR">
          <span className={styles.brandMark} aria-hidden="true">
            WF
          </span>
          <span>Wealthy Falcon HR</span>
        </div>

        <div className={styles.tenantCard}>
          <span>Çalışma alanı</span>
          <strong>{user.tenant.name}</strong>
          <small>{user.tenant.slug}</small>
        </div>

        <nav className={styles.navigation} aria-label="Ana menü">
          <Link className={styles.activeNavigationItem} href="/dashboard" aria-current="page">
            <span aria-hidden="true">⌂</span>
            Genel bakış
          </Link>
        </nav>

        <p className={styles.sidebarNote}>Güvenli tenant oturumu etkin</p>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <span className={styles.mobileTenant}>{user.tenant.name}</span>
            <strong>{name}</strong>
            <small>{user.email}</small>
          </div>
          <button
            className={styles.logoutButton}
            type="button"
            disabled={isLoggingOut}
            onClick={() => void signOut()}
          >
            {isLoggingOut ? "Çıkış yapılıyor…" : "Çıkış yap"}
          </button>
        </header>

        <section className={styles.content} aria-labelledby="dashboard-title">
          {logoutError ? (
            <div className={styles.errorBanner} role="alert">
              {logoutError}
            </div>
          ) : null}

          <div className={styles.welcome}>
            <span>Tenant çalışma alanı</span>
            <h1 id="dashboard-title">Merhaba, {name}</h1>
            <p>
              {user.tenant.name} çalışma alanına güvenli biçimde giriş yaptınız. Wealthy Falcon
              HR ana ekranınız kullanıma hazır.
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
                <p>Kurum kodunuz: {user.tenant.slug}</p>
              </div>
            </article>
          </div>
        </section>
      </main>
    </div>
  );
}
