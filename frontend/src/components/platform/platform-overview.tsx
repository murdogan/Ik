"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { usePlatformSession } from "@/components/session/platform-session-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  listAllPlatformTenants,
  type PlatformTenant,
  type PlatformTenantErrorPresentation,
  PLATFORM_TENANT_STATUSES,
  platformTenantErrorPresentation,
} from "@/lib/platform-tenants";

import styles from "./platform-tenant-operations.module.css";
import {
  formatPlatformDate,
  PLATFORM_PLAN_LABELS,
  PLATFORM_STATUS_LABELS,
} from "./platform-tenant-presentation";

export function PlatformOverview() {
  const { user } = usePlatformSession();
  const canReadTenants = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readPlatformTenants,
  );
  const [tenants, setTenants] = useState<PlatformTenant[]>([]);
  const [isLoading, setIsLoading] = useState(canReadTenants);
  const [error, setError] =
    useState<PlatformTenantErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!canReadTenants) {
      return;
    }

    let isActive = true;
    void Promise.resolve().then(() => {
      if (isActive) {
        setIsLoading(true);
        setError(null);
      }
      return listAllPlatformTenants();
    }).then(
      (collection) => {
        if (!isActive) return;
        setTenants(collection.tenants);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setTenants([]);
        setError(
          platformTenantErrorPresentation(
            cause,
            "Tenant operasyon özeti şu anda yüklenemiyor. Yeniden deneyin.",
          ),
        );
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [canReadTenants, reloadKey]);

  const statusCounts = useMemo(
    () =>
      Object.fromEntries(
        PLATFORM_TENANT_STATUSES.map((status) => [
          status,
          tenants.filter((tenant) => tenant.status === status).length,
        ]),
      ) as Record<(typeof PLATFORM_TENANT_STATUSES)[number], number>,
    [tenants],
  );

  const recentTenants = useMemo(
    () =>
      [...tenants]
        .sort(
          (left, right) =>
            Date.parse(right.updated_at) - Date.parse(left.updated_at),
        )
        .slice(0, 6),
    [tenants],
  );

  function retry() {
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  return (
    <section
      className={styles.page}
      aria-labelledby="platform-title"
      aria-busy={isLoading}
    >
      <header className={styles.pageHeader}>
        <div>
          <span>Platform operasyonları</span>
          <h1 id="platform-title">Platform operasyonları</h1>
          <p>
            Tenant yaşam döngüsünü, plan metadata’sını ve güvenli modül
            dağıtımlarını tek çalışma alanından yönetin.
          </p>
        </div>
        {canReadTenants ? (
          <Link className={styles.primaryLink} href="/platform/tenants">
            Tenant yönetimine git
          </Link>
        ) : null}
      </header>

      {!canReadTenants ? (
        <div className={styles.permissionNotice} role="status">
          <span aria-hidden="true">i</span>
          <div>
            <strong>Tenant görünümü yetkiniz kapsamında değil</strong>
            <p>
              Operasyon özeti ve tenant yönetimi yalnız platform tenant okuma
              iznine sahip rollere açılır.
            </p>
          </div>
        </div>
      ) : error ? (
        <div className={styles.errorState} role="alert">
          <div>
            <strong>Operasyon özeti yüklenemedi</strong>
            <p>{error.message}</p>
            {error.reference ? (
              <small>Referans: {error.reference}</small>
            ) : null}
          </div>
          <button type="button" onClick={retry}>
            Yeniden dene
          </button>
        </div>
      ) : isLoading ? (
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <strong>Tenant operasyonları yükleniyor</strong>
          <p>Güvenli platform metadata sayfaları hazırlanıyor…</p>
        </div>
      ) : (
        <>
          <div className={styles.overviewMetrics}>
            <article className={styles.totalMetric}>
              <span>Toplam tenant</span>
              <strong data-testid="platform-total-tenants">
                {tenants.length.toLocaleString("tr-TR")}
              </strong>
              <p>Platform metadata kataloğundaki tüm tenantlar</p>
            </article>

            <section
              className={styles.statusBreakdown}
              aria-labelledby="status-breakdown-title"
            >
              <div className={styles.sectionTitle}>
                <div>
                  <span>Yaşam döngüsü</span>
                  <h2 id="status-breakdown-title">Durum dağılımı</h2>
                </div>
              </div>
              <dl>
                {PLATFORM_TENANT_STATUSES.map((status) => (
                  <div key={status}>
                    <dt>
                      <span
                        className={styles.statusDot}
                        data-status={status}
                        aria-hidden="true"
                      />
                      {PLATFORM_STATUS_LABELS[status]}
                    </dt>
                    <dd>{statusCounts[status].toLocaleString("tr-TR")}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>

          <section
            className={styles.listCard}
            aria-labelledby="recent-tenants-title"
          >
            <div className={styles.listHeader}>
              <div>
                <span>Güncel görünüm</span>
                <h2 id="recent-tenants-title">Son güncellenen tenantlar</h2>
              </div>
              <Link href="/platform/tenants">Tümünü görüntüle</Link>
            </div>

            {recentTenants.length === 0 ? (
              <div className={styles.emptyState}>
                <span aria-hidden="true">T</span>
                <h3>Henüz tenant yok</h3>
                <p>
                  Tenant oluşturma yetkiniz varsa yönetim ekranından ilk tenantı
                  hazırlayabilirsiniz.
                </p>
                <Link className={styles.secondaryLink} href="/platform/tenants">
                  Tenant yönetimini aç
                </Link>
              </div>
            ) : (
              <div className={styles.tableScroller}>
                <table className={styles.tenantTable}>
                  <thead>
                    <tr>
                      <th scope="col">Tenant</th>
                      <th scope="col">Durum</th>
                      <th scope="col">Plan</th>
                      <th scope="col">Son güncelleme</th>
                      <th scope="col">
                        <span className={styles.visuallyHidden}>İşlemler</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentTenants.map((tenant) => (
                      <tr key={tenant.id}>
                        <td data-label="Tenant">
                          <div className={styles.tenantIdentity}>
                            <strong>{tenant.name}</strong>
                            <span>{tenant.slug}</span>
                          </div>
                        </td>
                        <td data-label="Durum">
                          <span
                            className={styles.statusBadge}
                            data-status={tenant.status}
                          >
                            {PLATFORM_STATUS_LABELS[tenant.status]}
                          </span>
                        </td>
                        <td data-label="Plan">
                          {PLATFORM_PLAN_LABELS[tenant.plan_code]}
                        </td>
                        <td data-label="Son güncelleme">
                          <time dateTime={tenant.updated_at}>
                            {formatPlatformDate(tenant.updated_at)}
                          </time>
                        </td>
                        <td className={styles.actionCell}>
                          <Link
                            href={`/platform/tenants/${encodeURIComponent(tenant.id)}`}
                            aria-label={`${tenant.name} tenantını incele`}
                          >
                            İncele
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      <aside className={styles.securityBoundary} aria-label="Güvenlik sınırı">
        <span aria-hidden="true">✓</span>
        <div>
          <strong>Platform sınırı etkin</strong>
          <p>
            Bu ekran yalnız tenant kimliği, yaşam döngüsü, plan, bölge, yerel
            ayarlar, tanımlı limit ve feature metadata’sını kullanır. Çalışan,
            izin, doküman veya müşteri HR kayıtları platform kabuğuna taşınmaz.
          </p>
        </div>
      </aside>
    </section>
  );
}
