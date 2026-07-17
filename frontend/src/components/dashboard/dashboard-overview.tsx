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
    return "Özet yanıtı güvenli biçimde doğrulanamadı.";
  }
  if (cause instanceof ApiClientError && cause.code === "network_error") {
    return "Özet yüklenemedi. Bağlantınızı kontrol edip yeniden deneyin.";
  }
  return "Rol kapsamındaki özet şu anda yüklenemiyor.";
}

const ACTIVITY_LABELS: Record<string, string> = {
  "employee.created": "Çalışan kaydı oluşturuldu",
  "employee.updated": "Çalışan kaydı güncellendi",
  "employee.lifecycle.changed": "Çalışan yaşam döngüsü güncellendi",
  "leave.requested": "İzin talebi gönderildi",
  "leave.approved": "İzin talebi onaylandı",
  "leave.rejected": "İzin talebi reddedildi",
  "leave.cancelled": "İzin talebi iptal edildi",
};

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
  const canOpenOrganization =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOrganization) &&
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.organization);
  const canOpenReports =
    (hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantReports) ||
      hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamReports)) &&
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.reporting);

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
    <section aria-labelledby="dashboard-title">
      <div className={styles.welcome}>
        <span>Tenant çalışma alanı</span>
        <h1 id="dashboard-title">Merhaba, {name}</h1>
        <p>
          {user.tenant.name} çalışma alanındaki görünümünüz güncel rol ve kapsamınıza göre
          hazırlanır.
        </p>
      </div>

      {isLoading ? (
        <div className={styles.dashboardLoading} role="status" aria-live="polite">
          <span className={styles.teamSpinner} aria-hidden="true" />
          Yetkili özet hazırlanıyor…
        </div>
      ) : error ? (
        <div className={styles.dashboardError} role="alert">
          <strong>Genel bakış yüklenemedi</strong>
          <span>{error}</span>
        </div>
      ) : summary?.scope === "tenant" || summary?.scope === "team" ? (
        <>
          <div className={styles.dashboardScopeLine}>
            <span>{summary.scope === "team" ? "Doğrudan ekip kapsamı" : "Kurum kapsamı"}</span>
            {canOpenReports ? <Link href="/reports">Ayrıntılı raporları aç →</Link> : null}
          </div>
          <div className={styles.metricGrid}>
            <article><span>Toplam çalışan</span><strong>{summary.employee_count}</strong><small>Aktif ve izinde</small></article>
            <article><span>Aktif çalışan</span><strong>{summary.active_employee_count}</strong><small>Güncel iş gücü</small></article>
            <article><span>Bekleyen izin</span><strong>{summary.pending_leave_requests}</strong><small>Karar bekliyor</small></article>
            <article><span>Yeni başlayan</span><strong>{summary.new_starters_this_month}</strong><small>Bu ay</small></article>
            <article><span>İşten ayrılan</span><strong>{summary.terminated_this_month}</strong><small>Bu ay</small></article>
            <article><span>Eksik belge</span><strong>{summary.missing_document_count}</strong><small>Zorunlu kontroller</small></article>
            <article><span>Süresi yaklaşan</span><strong>{summary.expiring_document_count}</strong><small>Önümüzdeki 30 gün</small></article>
          </div>
          <div className={styles.dashboardDetails}>
            <article>
              <header><span>Dağılım</span><h2>Departmanlara göre çalışanlar</h2></header>
              {summary.department_distribution.length ? (
                <ul className={styles.distributionList}>
                  {summary.department_distribution.map((item) => (
                    <li key={item.department}>
                      <span>{item.department}</span><strong>{item.count}</strong>
                    </li>
                  ))}
                </ul>
              ) : <p className={styles.dashboardEmpty}>Bu kapsamda dağılım verisi yok.</p>}
            </article>
            <article>
              <header><span>Son hareketler</span><h2>Güvenli etkinlik özeti</h2></header>
              {summary.recent_activity.length ? (
                <ul className={styles.activityList}>
                  {summary.recent_activity.map((activity) => (
                    <li key={`${activity.entity_id}-${activity.occurred_at}`}>
                      <span aria-hidden="true">•</span>
                      <div>
                        <strong>{ACTIVITY_LABELS[activity.activity_type] ?? activity.title}</strong>
                        <small>{new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(activity.occurred_at))}</small>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <p className={styles.dashboardEmpty}>Bu kapsamda yakın tarihli hareket yok.</p>}
            </article>
          </div>
        </>
      ) : (
        <div className={styles.ownScopeNotice}>
          <span aria-hidden="true">✓</span>
          <div>
            <strong>Kişisel çalışma alanı</strong>
            <p>HR metrikleri yalnızca açık tenant veya ekip kapsamı yetkisiyle gösterilir.</p>
          </div>
        </div>
      )}

      <div className={styles.cards}>
        <article className={styles.card}>
          <span className={styles.cardIcon} aria-hidden="true">✓</span>
          <div><small>Oturum durumu</small><h2>Güvenli oturum etkin</h2><p>Kısa ömürlü erişim ve yenilenen güvenli oturum ile bağlısınız.</p></div>
        </article>
        <article className={styles.card}>
          <span className={`${styles.cardIcon} ${styles.blueIcon}`} aria-hidden="true">W</span>
          <div><small>Kurum</small><h2>{user.tenant.name}</h2><p>Çalışma alanınız: {user.tenant.name}</p></div>
        </article>
        {canOpenOrganization ? (
          <Link className={`${styles.card} ${styles.cardLink}`} href="/organization">
            <span className={styles.cardIcon} aria-hidden="true">O</span>
            <div><small>Organizasyon</small><h2>Organizasyon çalışma alanını aç</h2><p>Şemayı, tüzel kişilikleri, şubeleri, departmanları ve pozisyonları inceleyin.</p></div>
            <span className={styles.cardArrow} aria-hidden="true">→</span>
          </Link>
        ) : null}
      </div>

      {canReadTeam ? <ManagerTeam /> : null}
    </section>
  );
}
