"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePlatformSession } from "@/components/session/platform-session-provider";
import type {
  PlatformAuthenticationStrength,
  PlatformAuthUser,
} from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";

import styles from "./platform-shell.module.css";

const platformNavigation = [
  {
    href: "/platform",
    label: "Platform genel bakış",
    icon: "overview",
    permission: null,
    exact: true,
  },
  {
    href: "/platform/tenants",
    label: "Tenant yönetimi",
    icon: "tenants",
    permission: AUTHORIZATION_PERMISSIONS.readPlatformTenants,
    exact: false,
  },
  {
    href: "/platform/audit",
    label: "Denetim kayıtları",
    icon: "audit",
    permission: AUTHORIZATION_PERMISSIONS.readPlatformAudit,
    exact: false,
  },
] as const;

type PlatformNavigationItem = (typeof platformNavigation)[number];

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

function matchesNavigationPath(
  pathname: string,
  item: PlatformNavigationItem,
): boolean {
  return item.exact
    ? pathname === item.href
    : pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavigationIcon({
  name,
}: {
  name: PlatformNavigationItem["icon"];
}) {
  if (name === "overview") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1.5" />
        <rect x="14" y="3.5" width="6.5" height="6.5" rx="1.5" />
        <rect x="3.5" y="14" width="6.5" height="6.5" rx="1.5" />
        <rect x="14" y="14" width="6.5" height="6.5" rx="1.5" />
      </svg>
    );
  }

  if (name === "tenants") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 20.5V6.25a1.75 1.75 0 0 1 1.75-1.75h8.5A1.75 1.75 0 0 1 16 6.25V20.5" />
        <path d="M16 9.5h2.25A1.75 1.75 0 0 1 20 11.25v9.25M8 8h4M8 12h4M8 16h4M2.5 20.5h19" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8.5 5.5h-2A1.5 1.5 0 0 0 5 7v12a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V7a1.5 1.5 0 0 0-1.5-1.5h-2" />
      <path d="M9 3.5h6v4H9zM8.5 12h7M8.5 16h5" />
    </svg>
  );
}

function PlatformBrand({ mobile = false }: { mobile?: boolean }) {
  return (
    <div
      className={`${styles.brand} ${mobile ? styles.mobileBrand : ""}`}
      role="img"
      aria-label="Wealthy Falcon HR Platform"
    >
      <span className={styles.brandMark} aria-hidden="true">
        WF
      </span>
      <span className={styles.brandCopy}>
        <strong>Wealthy Falcon HR</strong>
        <small>Platform</small>
      </span>
    </div>
  );
}

function Navigation({
  user,
  mobile = false,
}: {
  user: PlatformAuthUser;
  mobile?: boolean;
}) {
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
        const isActive = matchesNavigationPath(pathname, item);
        return (
          <Link
            className={`${styles.navigationItem} ${isActive ? styles.activeNavigationItem : ""}`}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            key={item.href}
          >
            <span className={styles.navigationIcon}>
              <NavigationIcon name={item.icon} />
            </span>
            <span className={styles.navigationLabel}>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function authenticationStrengthLabel(
  strength: PlatformAuthenticationStrength,
): string {
  if (strength === "multi_factor") {
    return "Çok faktörlü doğrulama";
  }
  if (strength === "step_up") {
    return "Yükseltilmiş doğrulama";
  }
  return "Tek faktörlü doğrulama";
}

export function PlatformShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, isLoggingOut, logoutError, signOut } = usePlatformSession();
  const name = displayName(user.full_name, user.email);
  const roleNames =
    user.roles.map((role) => role.name).join(" · ") || "Platform yetkisi";
  const authenticationStrength = authenticationStrengthLabel(
    user.authentication_strength,
  );
  const currentSection =
    platformNavigation.find(
      (item) =>
        (item.permission === null || hasPermission(user, item.permission)) &&
        matchesNavigationPath(pathname, item),
    )?.label ?? "Platform yönetimi";

  return (
    <div className={styles.application} data-workspace-shell="platform">
      <aside className={styles.sidebar} aria-label="Platform gezintisi">
        <PlatformBrand />

        <div className={styles.workspaceLabel}>
          <span aria-hidden="true" />
          Platform çalışma alanı
        </div>

        <Navigation user={user} />

        <div className={styles.sidebarSession}>
          <span className={styles.sessionMark} aria-hidden="true">
            ✓
          </span>
          <span>
            <small>Oturum güvenliği</small>
            <strong>{authenticationStrength}</strong>
          </span>
        </div>
      </aside>

      <main className={styles.main} aria-label="Platform çalışma alanı">
        <header
          className={styles.header}
          role="banner"
          aria-label="Platform üst çubuğu"
        >
          <PlatformBrand mobile />

          <div className={styles.workspaceContext}>
            <span>
              <small>Platform çalışma alanı</small>
              <strong>{currentSection}</strong>
            </span>
            <span className={styles.mobileSession}>
              <strong>{name}</strong>
              <small>{authenticationStrength}</small>
            </span>
          </div>

          <div className={styles.headerActions}>
            <div className={styles.identity}>
              <strong>{name}</strong>
              <small>
                {roleNames} · {authenticationStrength}
              </small>
            </div>
            <button
              className={styles.logoutButton}
              type="button"
              disabled={isLoggingOut}
              onClick={() => void signOut()}
            >
              {isLoggingOut ? "Çıkış yapılıyor…" : "Çıkış yap"}
            </button>
          </div>
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
