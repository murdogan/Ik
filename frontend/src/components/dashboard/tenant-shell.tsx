"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/components/session/session-provider";
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import { NotificationBadge } from "@/components/self-service/notification-badge";
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

interface NavigationItem {
  href: string;
  label: string;
  icon: string;
  permissions?: readonly string[];
  anyPermissions?: readonly string[];
  feature: (typeof TENANT_FEATURES)[keyof typeof TENANT_FEATURES] | null;
}

const navigationItems: readonly NavigationItem[] = [
  {
    href: "/home",
    label: "Çalışan ana sayfası",
    icon: "⌂",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnSelfService],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/dashboard",
    label: "Genel bakış",
    icon: "⌂",
    permissions: [],
    feature: null,
  },
  {
    href: "/users",
    label: "Kullanıcılar",
    icon: "K",
    permissions: [AUTHORIZATION_PERMISSIONS.readUsers],
    feature: null,
  },
  {
    href: "/profile",
    label: "Profilim",
    icon: "P",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnEmployee],
    feature: null,
  },
  {
    href: "/employees",
    label: "Çalışanlar",
    icon: "Ç",
    permissions: [AUTHORIZATION_PERMISSIONS.readTenantEmployees],
    feature: null,
  },
  {
    href: "/document-types",
    label: "Belge türleri",
    icon: "B",
    permissions: [AUTHORIZATION_PERMISSIONS.manageDocumentTypes],
    feature: null,
  },
  {
    href: "/reports",
    label: "Raporlar ve aktarımlar",
    icon: "R",
    anyPermissions: [
      AUTHORIZATION_PERMISSIONS.readTenantReports,
      AUTHORIZATION_PERMISSIONS.readTeamReports,
      AUTHORIZATION_PERMISSIONS.manageEmployeeImports,
    ],
    feature: TENANT_FEATURES.reporting,
  },
  {
    href: "/requests",
    label: "Talepler",
    icon: "T",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnRequests],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/leave",
    label: "İzinlerim",
    icon: "İ",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnLeave],
    feature: TENANT_FEATURES.leave,
  },
  {
    href: "/manager",
    label: "Yönetici alanı",
    icon: "E",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTeamEmployees,
      AUTHORIZATION_PERMISSIONS.readTeamLeave,
      AUTHORIZATION_PERMISSIONS.approveTeamLeave,
    ],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/leave/approvals",
    label: "Onay görevleri",
    icon: "✓",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTeamLeave,
      AUTHORIZATION_PERMISSIONS.approveTeamLeave,
    ],
    feature: TENANT_FEATURES.leave,
  },
  {
    href: "/leave/admin",
    label: "İzin yönetimi",
    icon: "Y",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTenantLeave,
      AUTHORIZATION_PERMISSIONS.manageTenantLeave,
    ],
    feature: TENANT_FEATURES.leave,
  },
  {
    href: "/profile-change-requests",
    label: "Değişiklik talepleri",
    icon: "D",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTenantEmployees,
      AUTHORIZATION_PERMISSIONS.updateEmployees,
    ],
    feature: null,
  },
  {
    href: "/hr/requests",
    label: "HR talepleri",
    icon: "H",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTenantRequests,
      AUTHORIZATION_PERMISSIONS.manageTenantDocumentRequests,
    ],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/announcements",
    label: "Duyurular",
    icon: "D",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnAnnouncements],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/announcements/manage",
    label: "Duyuru yönetimi",
    icon: "Y",
    permissions: [AUTHORIZATION_PERMISSIONS.manageTenantAnnouncements],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/notifications",
    label: "Bildirimler",
    icon: "B",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnNotifications],
    feature: TENANT_FEATURES.notifications,
  },
  {
    href: "/organization",
    label: "Organizasyon",
    icon: "O",
    permissions: [AUTHORIZATION_PERMISSIONS.readOrganization],
    feature: TENANT_FEATURES.organization,
  },
  {
    href: "/audit",
    label: "Denetim kayıtları",
    icon: "D",
    permissions: [AUTHORIZATION_PERMISSIONS.readTenantAudit],
    feature: null,
  },
];

function Navigation({ user, mobile = false }: { user: AuthUser; mobile?: boolean }) {
  const pathname = usePathname();
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const selfServiceEnabled =
    featureStatus === "ready" && isEnabled(TENANT_FEATURES.selfService);
  const visibleItems = navigationItems.filter(
    (item) => {
      if (
        item.href === "/manager" &&
        (!selfServiceEnabled || !isEnabled(TENANT_FEATURES.leave))
      ) {
        return false;
      }
      if (
        item.href === "/dashboard" &&
        selfServiceEnabled &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnSelfService) &&
        !hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantDashboard) &&
        !hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamDashboard)
      ) {
        return false;
      }
      if (
        item.href === "/leave/approvals" &&
        selfServiceEnabled &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamEmployees)
      ) {
        return false;
      }
      if (
        item.href === "/profile-change-requests" &&
        selfServiceEnabled &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.manageTenantDocumentRequests)
      ) {
        return false;
      }
      return (
        (item.permissions ?? []).every((permission) => hasPermission(user, permission)) &&
        (item.anyPermissions === undefined ||
          item.anyPermissions.some((permission) => hasPermission(user, permission))) &&
        (item.feature === null ||
          (featureStatus === "ready" && isEnabled(item.feature)))
      );
    },
  );

  return (
    <nav
      className={mobile ? styles.mobileNavigation : styles.navigation}
      aria-label={mobile ? "Mobil ana menü" : "Ana menü"}
    >
      {visibleItems.map((item) => {
        const isActive =
          pathname === item.href ||
          (item.href === "/announcements"
            ? pathname.startsWith("/announcements/") &&
              !pathname.startsWith("/announcements/manage")
            : item.href !== "/leave" && pathname.startsWith(`${item.href}/`));
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
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const name = displayName(user.full_name, user.email);
  const roleNames = user.roles.map((role) => role.name).join(" · ") || "Rol atanmamış";
  const showNotifications =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnNotifications) &&
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.notifications);

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
            {showNotifications ? <NotificationBadge /> : null}
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
