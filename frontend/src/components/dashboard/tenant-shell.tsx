"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/components/session/session-provider";

import styles from "./tenant-shell.module.css";

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

const navigationItems = [
  { href: "/dashboard", label: "Genel bakış", icon: "⌂" },
  { href: "/users", label: "Kullanıcılar", icon: "K" },
] as const;

function Navigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();

  return (
    <nav
      className={mobile ? styles.mobileNavigation : styles.navigation}
      aria-label={mobile ? "Mobil ana menü" : "Ana menü"}
    >
      {navigationItems.map((item) => {
        const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
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

export function TenantShell({ children }: { children: ReactNode }) {
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

        <Navigation />

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

        <Navigation mobile />

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
