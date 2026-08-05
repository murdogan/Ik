"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import { ApiClientError } from "@/lib/api-client";
import type { AuthUser } from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";
import {
  type DashboardSummary,
  readDashboardSummary,
} from "@/lib/reporting";

import { ManagerTeam } from "./manager-team";
import styles from "./tenant-shell.module.css";

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

function dashboardError(cause: unknown): string {
  if (cause instanceof ApiClientError && cause.code === "invalid_response") {
    return "Genel bakış şu anda güncellenemiyor. Lütfen biraz sonra yeniden deneyin.";
  }
  if (cause instanceof ApiClientError && cause.code === "network_error") {
    return "Özet yüklenemedi. Bağlantınızı kontrol edip yeniden deneyin.";
  }
  return "Genel bakış şu anda yüklenemiyor. Lütfen yeniden deneyin.";
}

const ACTIVITY_LABELS: Record<string, string> = {
  "employee.created": "Çalışan kaydı oluşturuldu",
  "employee.updated": "Çalışan kaydı güncellendi",
  "employee.lifecycle.changed": "Çalışanın durumu güncellendi",
  "leave.requested": "İzin talebi gönderildi",
  "leave.approved": "İzin talebi onaylandı",
  "leave.rejected": "İzin talebi reddedildi",
  "leave.cancelled": "İzin talebi iptal edildi",
};

interface PrimaryMetricCardProps {
  label: string;
  value: number;
  hint: string;
  href?: string | null;
  actionLabel?: string;
  attention?: boolean;
}

function PrimaryMetricCard({
  label,
  value,
  hint,
  href,
  actionLabel,
  attention = false,
}: PrimaryMetricCardProps) {
  const content = (
    <>
      <span className={styles.metricLabel}>{label}</span>
      <strong className={styles.metricValue}>{value}</strong>
      <span className={styles.metricHint}>{hint}</span>
      {href && actionLabel ? (
        <span className={styles.metricAction}>
          {actionLabel} <span aria-hidden="true">→</span>
        </span>
      ) : null}
    </>
  );

  if (href) {
    return (
      <Link
        className={`${styles.primaryMetricCard} ${styles.primaryMetricLink}`}
        data-attention={attention || undefined}
        href={href}
      >
        {content}
      </Link>
    );
  }

  return (
    <article
      className={styles.primaryMetricCard}
      data-attention={attention || undefined}
    >
      {content}
    </article>
  );
}

function SecondaryMetricCard({
  label,
  value,
  hint,
}: Omit<PrimaryMetricCardProps, "href" | "actionLabel" | "attention">) {
  return (
    <article className={styles.secondaryMetricCard}>
      <span className={styles.metricLabel}>{label}</span>
      <strong className={styles.metricValue}>{value}</strong>
      <span className={styles.metricHint}>{hint}</span>
    </article>
  );
}

export function DashboardOverview() {
  const { user } = useSession();
  const authorizationBoundary = [
    user.tenant_id,
    user.id,
    user.membership_id,
    user.permission_version,
  ].join(":");
  return <DashboardOverviewContent key={authorizationBoundary} user={user} />;
}

function DashboardOverviewContent({ user }: { user: AuthUser }) {
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const name = displayName(user.full_name, user.email);
  const canReadTenantDashboard = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTenantDashboard,
  );
  const canReadTeamDashboard = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTeamDashboard,
  );
  const canReadTeam = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTeamEmployees,
  );
  const canReadDashboard = [
    AUTHORIZATION_PERMISSIONS.readTenantDashboard,
    AUTHORIZATION_PERMISSIONS.readTeamDashboard,
    AUTHORIZATION_PERMISSIONS.readOwnDashboard,
  ].some((permission) => hasPermission(user, permission));
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [isLoading, setIsLoading] = useState(canReadDashboard);
  const [error, setError] = useState<string | null>(null);
  const leaveEnabled =
    featureStatus === "ready" && isEnabled(TENANT_FEATURES.leave);
  const selfServiceEnabled =
    featureStatus === "ready" && isEnabled(TENANT_FEATURES.selfService);
  const canOpenOrganization =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOrganization) &&
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.organization);
  const canOpenReports =
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.reporting) &&
    ((summary?.scope === "tenant" &&
      hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantReports)) ||
      (summary?.scope === "team" &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamReports)));
  const canManageTenantLeave =
    leaveEnabled &&
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantLeave) &&
    hasPermission(user, AUTHORIZATION_PERMISSIONS.manageTenantLeave);
  const canApproveTeamLeave =
    leaveEnabled &&
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamLeave) &&
    hasPermission(user, AUTHORIZATION_PERMISSIONS.approveTeamLeave);
  const canOpenManager =
    canApproveTeamLeave && canReadTeam && selfServiceEnabled;
  const canOpenSelfServiceHome =
    selfServiceEnabled &&
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnSelfService);
  const pendingLeaveHref =
    summary?.scope === "tenant" && canManageTenantLeave
      ? "/leave/admin"
      : summary?.scope === "team" && canOpenManager
        ? "/manager"
        : summary?.scope === "team" && canApproveTeamLeave
          ? "/leave/approvals"
          : null;
  const dashboardPerspective = canReadTenantDashboard
    ? "tenant"
    : canReadTeamDashboard
      ? "team"
      : "own";
  const introduction =
    dashboardPerspective === "team"
      ? `${user.tenant.name} ekibinizde bugün öne çıkanları ve bekleyen işleri bir arada görebilirsiniz.`
      : dashboardPerspective === "own"
        ? `${user.tenant.name} içindeki kişisel işlemlerinize kolayca ulaşabilirsiniz.`
        : `${user.tenant.name} için çalışanlarla ilgili güncel durumu ve bekleyen işleri bir arada görebilirsiniz.`;

  useEffect(() => {
    if (!canReadDashboard) return;
    let active = true;
    void readDashboardSummary().then(
      (data) => {
        if (active) {
          setSummary(data);
          setIsLoading(false);
        }
      },
      (cause) => {
        if (active) {
          setSummary(null);
          setError(dashboardError(cause));
          setIsLoading(false);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [canReadDashboard, user.permission_version, user.tenant_id]);

  return (
    <section
      className={styles.dashboardOverview}
      aria-labelledby="dashboard-title"
    >
      <div className={`${styles.welcome} ${styles.dashboardWelcome}`}>
        <span className={styles.dashboardEyebrow}>Günün özeti</span>
        <h1 id="dashboard-title">Merhaba, {name}</h1>
        <p className={styles.dashboardIntro}>{introduction}</p>
      </div>

      {isLoading ? (
        <div className={styles.dashboardLoading} role="status" aria-live="polite">
          <span className={styles.teamSpinner} aria-hidden="true" />
          Genel bakış hazırlanıyor…
        </div>
      ) : error ? (
        <div className={styles.dashboardError} role="alert">
          <strong>Genel bakış yüklenemedi</strong>
          <span>{error}</span>
        </div>
      ) : summary?.scope === "tenant" || summary?.scope === "team" ? (
        <>
          <section
            className={styles.dashboardMetrics}
            aria-labelledby="dashboard-metrics-title"
          >
            <header className={styles.dashboardSectionHeading}>
              <span>{summary.scope === "team" ? "Ekibiniz" : "Kurumunuz"}</span>
              <h2 id="dashboard-metrics-title">Genel görünüm</h2>
            </header>

            <div className={styles.primaryMetricGrid}>
              <PrimaryMetricCard
                label="Toplam çalışan"
                value={summary.employee_count}
                hint="Aktif ve izinde"
              />
              <PrimaryMetricCard
                label="Aktif çalışan"
                value={summary.active_employee_count}
                hint="Güncel ekip"
              />
              <PrimaryMetricCard
                label="Bekleyen izin"
                value={summary.pending_leave_requests}
                hint="Karar bekleyen talepler"
                href={pendingLeaveHref}
                actionLabel={
                  pendingLeaveHref === "/manager"
                    ? "Yönetici alanını aç"
                    : "Talepleri incele"
                }
                attention={summary.pending_leave_requests > 0}
              />
              <PrimaryMetricCard
                label="Eksik belge"
                value={summary.missing_document_count}
                hint="Tamamlanması gereken kayıtlar"
                href={canOpenReports ? "/reports" : null}
                actionLabel="Raporlarda incele"
                attention={summary.missing_document_count > 0}
              />
            </div>

            <div className={styles.secondaryMetricGrid}>
              <SecondaryMetricCard
                label="Bu ay başlayan"
                value={summary.new_starters_this_month}
                hint="Yeni ekip arkadaşları"
              />
              <SecondaryMetricCard
                label="Bu ay ayrılan"
                value={summary.terminated_this_month}
                hint="Tamamlanan iş ilişkileri"
              />
              <SecondaryMetricCard
                label="Süresi yaklaşan belge"
                value={summary.expiring_document_count}
                hint="Önümüzdeki 30 gün"
              />
            </div>
          </section>

          <div className={styles.dashboardDetails}>
            <article className={styles.dashboardDetailCard}>
              <header className={styles.dashboardDetailHeader}>
                <span>Ekip yapısı</span>
                <h2>Departman dağılımı</h2>
              </header>
              {summary.department_distribution.length ? (
                <ul className={styles.distributionList}>
                  {summary.department_distribution.map((item) => (
                    <li key={item.department}>
                      <span>
                        {item.department === "Unassigned"
                          ? "Atanmamış"
                          : item.department}
                      </span>
                      <strong>{item.count}</strong>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={styles.dashboardEmpty}>
                  Henüz departman dağılımı bulunmuyor.
                </p>
              )}
            </article>
            <article className={styles.dashboardDetailCard}>
              <header className={styles.dashboardDetailHeader}>
                <span>Yakın zamanda</span>
                <h2>Son hareketler</h2>
              </header>
              {summary.recent_activity.length ? (
                <ul className={styles.activityList}>
                  {summary.recent_activity.map((activity) => (
                    <li key={`${activity.entity_id}-${activity.occurred_at}`}>
                      <span aria-hidden="true">•</span>
                      <div>
                        <strong>{ACTIVITY_LABELS[activity.activity_type] ?? activity.title}</strong>
                        <small>
                          {new Intl.DateTimeFormat("tr-TR", {
                            dateStyle: "medium",
                            timeStyle: "short",
                          }).format(new Date(activity.occurred_at))}
                        </small>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={styles.dashboardEmpty}>
                  Henüz yakın tarihli bir hareket yok.
                </p>
              )}
            </article>
          </div>
        </>
      ) : (
        <div className={`${styles.ownScopeNotice} ${styles.ownDashboardCard}`}>
          <span className={styles.ownDashboardIcon} aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M16 20v-1.5A3.5 3.5 0 0 0 12.5 15h-5A3.5 3.5 0 0 0 4 18.5V20M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm7-1v6m3-3h-6"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.8"
              />
            </svg>
          </span>
          <div className={styles.ownDashboardContent}>
            <strong>Kişisel alanınız</strong>
            <p>
              {canOpenSelfServiceHome
                ? "İzin, belge ve diğer çalışan işlemlerinize ana sayfanızdan devam edebilirsiniz."
                : `${user.tenant.name} için kullanabildiğiniz bölümlere menüden ulaşabilirsiniz.`}
            </p>
          </div>
          {canOpenSelfServiceHome ? (
            <Link className={styles.ownDashboardLink} href="/home">
              Çalışan ana sayfasına git <span aria-hidden="true">→</span>
            </Link>
          ) : null}
        </div>
      )}

      {canOpenOrganization ? (
        <div className={styles.dashboardShortcuts}>
          <Link className={styles.dashboardShortcut} href="/organization">
            <span className={styles.dashboardShortcutIcon} aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 4v5m0 0H6v4m6-4h6v4M6 17v3m12-3v3m-6-7v7M3.5 13h5v4h-5v-4Zm6 7h5v-4h-5v4Zm6-7h5v4h-5v-4Z"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.7"
                />
              </svg>
            </span>
            <span className={styles.dashboardShortcutContent}>
              <small>Organizasyon</small>
              <strong>Ekibinizin yapısını görüntüleyin</strong>
              <span>Departmanları, şubeleri ve pozisyonları gözden geçirin.</span>
            </span>
            <span className={styles.dashboardShortcutArrow} aria-hidden="true">
              →
            </span>
          </Link>
        </div>
      ) : null}

      {canReadTeam ? <ManagerTeam /> : null}
    </section>
  );
}
