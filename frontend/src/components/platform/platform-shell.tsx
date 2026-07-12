"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/components/session/session-provider";
import type { AuthUser } from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";

import styles from "./platform-shell.module.css";

const platformNavigation = [
  {
    href: "/platform",
    label: "Platform genel bakış",
    icon: "P",
    permission: null,
    exact: true,
  },
  {
    href: "/platform/audit",
    label: "Denetim kayıtları",
    icon: "D",
    permission: AUTHORIZATION_PERMISSIONS.readPlatformAudit,
    exact: false,
  },
] as const;

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

function Navigation({ user, mobile = false }: { user: AuthUser; mobile?: boolean }) {
  const pathname = usePathname();
  const visibleItems = platformNavigation.filter(
    (item) => item.permission === null || hasPermission(user, item.permission),
  );

  return (
    <nav
      className={mobile ? styles.mobileNavigation : styles.navigation}
      aria-label={mobile ? "Mobil platform menüsü" : "Platform menüsü"}
    >
      {visibleItems.map((item) => {
        const isActive = item.exact
          ? pathname === item.href
          : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            className={`${styles.navigationItem} ${isActive ? styles.activeNavigationItem : ""}`}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            key={item.href}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function PlatformShell({ children }: { children: ReactNode }) {
  const { user, isLoggingOut, logoutError, signOut } = useSession();
  const name = displayName(user.full_name, user.email);
  const roleNames = user.roles.map((role) => role.name).join(" · ") || "Platform yetkisi";

  return (
    <div className={styles.application} data-workspace-shell="platform">
      <aside className={styles.sidebar}>
        <div className={styles.brand} aria-label="Wealthy Falcon HR Platform">
          <span className={styles.brandMark} aria-hidden="true">
            WF
          </span>
          <span>Wealthy Falcon HR</span>
        </div>

        <div className={styles.platformCard}>
          <span>Platform çalışma alanı</span>
          <strong>Operasyon merkezi</strong>
          <small>Müşteri HR alanlarından ayrılmış yönetim kabuğu</small>
        </div>

        <Navigation user={user} />

        <p className={styles.sidebarNote}>Platform oturumu · varsayılan erişim kapalı</p>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <div className={styles.identity}>
            <span>Platform yönetimi</span>
            <strong>{name}</strong>
            <small>{roleNames}</small>
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

        <Navigation user={user} mobile />

        <div className={styles.content}>
          {logoutError ? (
            <div className={styles.errorBanner} role="alert">
              {logoutError}
            </div>
          ) : null}
          {children}
        </div>
      </main>
    </div>
  );
}

export function PlatformOverview() {
  return (
    <section aria-labelledby="platform-title">
      <div className={styles.welcome}>
        <span>Platform operasyonları</span>
        <h1 id="platform-title">Platform operasyonları</h1>
        <p>
          Tenant yaşam döngüsü ve güvenli platform metadata operasyonları için ayrılmış çalışma
          alanındasınız. Müşteri çalışan verileri bu kabukta gösterilmez.
        </p>
      </div>

      <div className={styles.cards}>
        <article className={styles.card}>
          <span className={styles.cardIcon} aria-hidden="true">
            P
          </span>
          <div>
            <small>Çalışma alanı</small>
            <h2>Platform sınırı etkin</h2>
            <p>Tenant uygulama menüleri ve müşteri çalışma alanları bu kabuktan ayrıdır.</p>
          </div>
        </article>

        <article className={styles.card}>
          <span className={`${styles.cardIcon} ${styles.lockIcon}`} aria-hidden="true">
            ✓
          </span>
          <div>
            <small>Yetkilendirme</small>
            <h2>Varsayılan olarak reddet</h2>
            <p>Yalnız açıkça tanımlanmış platform izinleri navigasyona ve API’lere erişir.</p>
          </div>
        </article>
      </div>
    </section>
  );
}
