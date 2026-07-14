"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/components/session/session-provider";
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import type { AuthUser } from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

import styles from "./tenant-shell.module.css";

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

const navigationItems = [
  {
    href: "/dashboard",
    label: "Genel bakış",
    icon: "⌂",
    permission: null,
    feature: null,
  },
  {
    href: "/users",
    label: "Kullanıcılar",
    icon: "K",
    permission: AUTHORIZATION_PERMISSIONS.readUsers,
    feature: null,
  },
  {
    href: "/profile",
    label: "Profilim",
    icon: "P",
    permission: AUTHORIZATION_PERMISSIONS.readOwnEmployee,
    feature: null,
  },
  {
    href: "/employees",
    label: "Çalışanlar",
    icon: "Ç",
    permission: AUTHORIZATION_PERMISSIONS.readTenantEmployees,
    feature: null,
  },
  {
    href: "/organization",
    label: "Organizasyon",
    icon: "O",
    permission: AUTHORIZATION_PERMISSIONS.readOrganization,
    feature: TENANT_FEATURES.organization,
  },
  {
    href: "/audit",
    label: "Denetim kayıtları",
    icon: "D",
    permission: AUTHORIZATION_PERMISSIONS.readTenantAudit,
    feature: null,
  },
] as const;

function Navigation({ user, mobile = false }: { user: AuthUser; mobile?: boolean }) {
  const pathname = usePathname();
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const visibleItems = navigationItems.filter(
    (item) =>
      (item.permission === null || hasPermission(user, item.permission)) &&
      (item.feature === null ||
        (featureStatus === "ready" && isEnabled(item.feature))),
  );

  return (
    <nav
      className={mobile ? styles.mobileNavigation : styles.navigation}
      aria-label={mobile ? "Mobil ana menü" : "Ana menü"}
    >
      {visibleItems.map((item) => {
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
  const {
    user,
    isLoggingOut,
    isSwitchingOrganization,
    logoutError,
    organizationSwitchError,
    signOut,
    switchOrganization,
  } = useSession();
  const name = displayName(user.full_name, user.email);
  const roleNames = user.roles.map((role) => role.name).join(" · ") || "Rol atanmamış";

  return (
    <div className={styles.application} data-workspace-shell="tenant">
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
          <small className={styles.roleSummary}>{roleNames}</small>
          <button
            className={styles.tenantSwitchButton}
            type="button"
            disabled={isLoggingOut || isSwitchingOrganization}
            onClick={() => void switchOrganization()}
          >
            {isSwitchingOrganization ? "Kurumlar hazırlanıyor…" : "Kurum değiştir"}
          </button>
        </div>

        <Navigation user={user} />

        <p className={styles.sidebarNote}>Güvenli tenant oturumu etkin</p>
      </aside>

      <main className={styles.main}>
        <header className={styles.header}>
          <div>
            <span className={styles.mobileTenant}>{user.tenant.name}</span>
            <strong>{name}</strong>
            <small>{user.email}</small>
          </div>
          <div className={styles.headerActions}>
            <button
              className={styles.mobileSwitchButton}
              type="button"
              disabled={isLoggingOut || isSwitchingOrganization}
              onClick={() => void switchOrganization()}
            >
              {isSwitchingOrganization ? "Hazırlanıyor…" : "Kurum değiştir"}
            </button>
            <button
              className={styles.logoutButton}
              type="button"
              disabled={isLoggingOut || isSwitchingOrganization}
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
          {organizationSwitchError ? (
            <div className={styles.errorBanner} role="alert">
              {organizationSwitchError}
            </div>
          ) : null}
          {children}
        </div>
      </main>
    </div>
  );
}
