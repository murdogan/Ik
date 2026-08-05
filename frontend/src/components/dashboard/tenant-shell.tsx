"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import { NotificationBadge } from "@/components/self-service/notification-badge";
import type { AuthUser } from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

import { ProfileMenu } from "./profile-menu";
import { TenantIcon, type TenantIconName } from "./tenant-icons";
import styles from "./tenant-shell.module.css";

function tenantInitial(name: string): string {
  return name.trim().charAt(0).toLocaleUpperCase("tr-TR") || "K";
}

interface NavigationItem {
  href: string;
  label: string;
  icon: TenantIconName;
  permissions?: readonly string[];
  anyPermissions?: readonly string[];
  feature: (typeof TENANT_FEATURES)[keyof typeof TENANT_FEATURES] | null;
}

const navigationItems: readonly NavigationItem[] = [
  {
    href: "/home",
    label: "Çalışan ana sayfası",
    icon: "home",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnSelfService],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/dashboard",
    label: "Genel bakış",
    icon: "dashboard",
    permissions: [],
    feature: null,
  },
  {
    href: "/setup",
    label: "Kurulum hazırlığı",
    icon: "setup",
    permissions: [AUTHORIZATION_PERMISSIONS.updateOrganization],
    feature: null,
  },
  {
    href: "/users",
    label: "Kullanıcılar",
    icon: "users",
    permissions: [AUTHORIZATION_PERMISSIONS.readUsers],
    feature: null,
  },
  {
    href: "/profile",
    label: "Profilim",
    icon: "profile",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnEmployee],
    feature: null,
  },
  {
    href: "/privacy",
    label: "Gizlilik merkezi",
    icon: "privacy",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnPrivacyNotice],
    feature: null,
  },
  {
    href: "/employees",
    label: "Çalışanlar",
    icon: "employees",
    permissions: [AUTHORIZATION_PERMISSIONS.readTenantEmployees],
    feature: null,
  },
  {
    href: "/document-types",
    label: "Belge türleri",
    icon: "document-types",
    permissions: [AUTHORIZATION_PERMISSIONS.manageDocumentTypes],
    feature: null,
  },
  {
    href: "/reports",
    label: "Raporlar ve aktarımlar",
    icon: "reports",
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
    icon: "requests",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnRequests],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/leave",
    label: "İzinlerim",
    icon: "leave",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnLeave],
    feature: TENANT_FEATURES.leave,
  },
  {
    href: "/manager",
    label: "Yönetici alanı",
    icon: "manager",
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
    icon: "leave-approvals",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTeamLeave,
      AUTHORIZATION_PERMISSIONS.approveTeamLeave,
    ],
    feature: TENANT_FEATURES.leave,
  },
  {
    href: "/leave/admin",
    label: "İzin yönetimi",
    icon: "leave-admin",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTenantLeave,
      AUTHORIZATION_PERMISSIONS.manageTenantLeave,
    ],
    feature: TENANT_FEATURES.leave,
  },
  {
    href: "/profile-change-requests",
    label: "Değişiklik talepleri",
    icon: "profile-change-requests",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTenantEmployees,
      AUTHORIZATION_PERMISSIONS.updateEmployees,
    ],
    feature: null,
  },
  {
    href: "/hr/requests",
    label: "HR talepleri",
    icon: "hr-requests",
    permissions: [
      AUTHORIZATION_PERMISSIONS.readTenantRequests,
      AUTHORIZATION_PERMISSIONS.manageTenantDocumentRequests,
    ],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/announcements",
    label: "Duyurular",
    icon: "announcements",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnAnnouncements],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/announcements/manage",
    label: "Duyuru yönetimi",
    icon: "announcement-management",
    permissions: [AUTHORIZATION_PERMISSIONS.manageTenantAnnouncements],
    feature: TENANT_FEATURES.selfService,
  },
  {
    href: "/notifications",
    label: "Bildirimler",
    icon: "notifications",
    permissions: [AUTHORIZATION_PERMISSIONS.readOwnNotifications],
    feature: TENANT_FEATURES.notifications,
  },
  {
    href: "/organization",
    label: "Organizasyon",
    icon: "organization",
    permissions: [AUTHORIZATION_PERMISSIONS.readOrganization],
    feature: TENANT_FEATURES.organization,
  },
  {
    href: "/audit",
    label: "Denetim kayıtları",
    icon: "audit",
    permissions: [AUTHORIZATION_PERMISSIONS.readTenantAudit],
    feature: null,
  },
  {
    href: "/privacy/manage",
    label: "Gizlilik uyumu",
    icon: "privacy-management",
    anyPermissions: [
      AUTHORIZATION_PERMISSIONS.readTenantPrivacyCompliance,
      AUTHORIZATION_PERMISSIONS.manageTenantPrivacyNotices,
      AUTHORIZATION_PERMISSIONS.manageTenantRetentionPolicies,
    ],
    feature: null,
  },
];

function Navigation({
  user,
  variant = "desktop",
  onNavigate,
}: {
  user: AuthUser;
  variant?: "desktop" | "drawer";
  onNavigate?: () => void;
}) {
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
      className={variant === "drawer" ? styles.drawerNavigation : styles.navigation}
      aria-label={variant === "drawer" ? "Mobil ana menü" : "Ana menü"}
    >
      {visibleItems.map((item) => {
        const isActive =
          pathname === item.href ||
          (item.href === "/announcements"
            ? pathname.startsWith("/announcements/") &&
              !pathname.startsWith("/announcements/manage")
            : item.href === "/privacy"
              ? pathname.startsWith("/privacy/") &&
                !pathname.startsWith("/privacy/manage")
              : item.href !== "/leave" && pathname.startsWith(`${item.href}/`));
        return (
          <Link
            className={`${styles.navigationItem} ${isActive ? styles.activeNavigationItem : ""}`}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            title={item.label}
            onClick={onNavigate}
            key={item.href}
          >
            <TenantIcon name={item.icon} />
            <span className={styles.navigationLabel}>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function TenantShell({ children }: { children: ReactNode }) {
  const { user, logoutError, organizationSwitchError } = useSession();
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const [isNavigationOpen, setIsNavigationOpen] = useState(false);
  const mobileMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const desktopSidebarRef = useRef<HTMLElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const drawerId = useId();
  const showNotifications =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnNotifications) &&
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.notifications);

  const closeNavigation = useCallback((returnFocus: boolean) => {
    setIsNavigationOpen(false);
    if (returnFocus) {
      window.requestAnimationFrame(() => mobileMenuTriggerRef.current?.focus());
    }
  }, []);

  useEffect(() => {
    if (!isNavigationOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => {
      drawerRef.current?.querySelector<HTMLElement>("a[href]")?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeNavigation(true);
        return;
      }
      if (event.key !== "Tab") return;

      const drawer = drawerRef.current;
      if (!drawer) return;
      const focusable = Array.from(
        drawer.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'),
      );
      if (focusable.length === 0) {
        event.preventDefault();
        drawer.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeNavigation, isNavigationOpen]);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 1024px)");
    const handleDesktopChange = (event: MediaQueryListEvent) => {
      if (!event.matches || !drawerRef.current) return;
      setIsNavigationOpen(false);
      window.requestAnimationFrame(() => {
        const destination =
          desktopSidebarRef.current?.querySelector<HTMLElement>(
            'a[aria-current="page"]',
          ) ?? desktopSidebarRef.current?.querySelector<HTMLElement>("a[href]");
        destination?.focus();
      });
    };
    desktopQuery.addEventListener("change", handleDesktopChange);
    return () => desktopQuery.removeEventListener("change", handleDesktopChange);
  }, []);

  return (
    <div className={styles.application} data-workspace-shell="tenant">
      <aside ref={desktopSidebarRef} className={styles.sidebar}>
        <div className={styles.brand} aria-label="Wealthy Falcon HR">
          <span className={styles.brandMark} aria-hidden="true">
            WF
          </span>
          <span className={styles.brandName}>Wealthy Falcon HR</span>
        </div>

        <div className={styles.tenantCard} title={user.tenant.name}>
          <span className={styles.tenantCompactMark} aria-hidden="true">
            {tenantInitial(user.tenant.name)}
          </span>
          <div className={styles.tenantDetails}>
            <span>Çalışma alanı</span>
            <strong>{user.tenant.name}</strong>
          </div>
        </div>

        <Navigation user={user} />
      </aside>

      {isNavigationOpen ? (
        <div className={styles.mobileDrawerLayer}>
          <div
            className={styles.mobileDrawerBackdrop}
            aria-hidden="true"
            onMouseDown={() => closeNavigation(true)}
          />
          <aside
            ref={drawerRef}
            id={drawerId}
            className={styles.mobileDrawer}
            role="dialog"
            aria-modal="true"
            aria-label="Ana menü"
            tabIndex={-1}
          >
            <div className={styles.drawerHeader}>
              <div className={styles.brand} aria-label="Wealthy Falcon HR">
                <span className={styles.brandMark} aria-hidden="true">WF</span>
                <span className={styles.brandName}>Wealthy Falcon HR</span>
              </div>
              <button
                className={styles.drawerCloseButton}
                type="button"
                aria-label="Menüyü kapat"
                onClick={() => closeNavigation(true)}
              >
                <TenantIcon name="close" />
              </button>
            </div>
            <div className={styles.drawerTenant}>
              <span>Çalışma alanı</span>
              <strong>{user.tenant.name}</strong>
            </div>
            <Navigation
              user={user}
              variant="drawer"
              onNavigate={() => closeNavigation(false)}
            />
          </aside>
        </div>
      ) : null}

      <main className={styles.main}>
        <header className={styles.header}>
          <div className={styles.mobileHeaderContext}>
            <button
              ref={mobileMenuTriggerRef}
              className={styles.mobileMenuButton}
              type="button"
              aria-label="Ana menüyü aç"
              aria-expanded={isNavigationOpen}
              aria-controls={drawerId}
              onClick={() => setIsNavigationOpen(true)}
            >
              <TenantIcon name="menu" />
            </button>
            <span className={styles.mobileTenant}>{user.tenant.name}</span>
          </div>
          <div className={styles.headerActions}>
            {showNotifications ? <NotificationBadge /> : null}
            <ProfileMenu />
          </div>
        </header>

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
