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
  type PlatformResponseMeta,
  type PlatformTenant,
  type PlatformTenantErrorPresentation,
  type PlatformTenantStatus,
  PLATFORM_TENANT_STATUSES,
  platformTenantErrorPresentation,
} from "@/lib/platform-tenants";

import { CreateTenantDialog } from "./create-tenant-dialog";
import styles from "./platform-tenant-operations.module.css";
import {
  formatPlatformDate,
  PLATFORM_PLAN_LABELS,
  PLATFORM_REGION_LABELS,
  PLATFORM_STATUS_LABELS,
} from "./platform-tenant-presentation";

const VIEW_PAGE_SIZE = 20;

interface SuccessState {
  tenant: PlatformTenant;
  meta: PlatformResponseMeta;
}

export function TenantManagementScreen() {
  const { user } = usePlatformSession();
  const canCreate = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.createPlatformTenants,
  );
  const [tenants, setTenants] = useState<PlatformTenant[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] =
    useState<PlatformTenantErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<PlatformTenantStatus | "">("");
  const [page, setPage] = useState(1);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [success, setSuccess] = useState<SuccessState | null>(null);

  useEffect(() => {
    let isActive = true;
    void listAllPlatformTenants().then(
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
            "Tenant listesi şu anda yüklenemiyor. Yeniden deneyin.",
          ),
        );
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [reloadKey]);

  const filteredTenants = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("tr-TR");
    return [...tenants]
      .filter(
        (tenant) =>
          (!normalizedSearch ||
            tenant.name
              .toLocaleLowerCase("tr-TR")
              .includes(normalizedSearch) ||
            tenant.slug
              .toLocaleLowerCase("tr-TR")
              .includes(normalizedSearch)) &&
          (!status || tenant.status === status),
      )
      .sort(
        (left, right) =>
          Date.parse(right.updated_at) - Date.parse(left.updated_at),
      );
  }, [search, status, tenants]);

  const pageCount = Math.max(
    1,
    Math.ceil(filteredTenants.length / VIEW_PAGE_SIZE),
  );
  const visiblePage = Math.min(page, pageCount);
  const visibleTenants = filteredTenants.slice(
    (visiblePage - 1) * VIEW_PAGE_SIZE,
    visiblePage * VIEW_PAGE_SIZE,
  );
  const hasFilters = Boolean(search.trim() || status);

  function resetPage() {
    setPage(1);
  }

  function retry() {
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  function handleCreated(
    tenant: PlatformTenant,
    meta: PlatformResponseMeta,
  ) {
    setIsCreateOpen(false);
    setSuccess({ tenant, meta });
    setSearch("");
    setStatus("");
    setPage(1);
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  return (
    <section
      className={styles.page}
      aria-labelledby="tenant-management-title"
      aria-busy={isLoading}
    >
      <header className={styles.pageHeader}>
        <div>
          <span>Platform operasyonları</span>
          <h1 id="tenant-management-title">Tenant yönetimi</h1>
          <p>
            Tenant kimliği, planı ve yaşam döngüsünü yönetin. Bu görünümde
            müşteri çalışan veya HR kayıtları bulunmaz.
          </p>
        </div>
        {canCreate ? (
          <button
            className={styles.primaryButton}
            type="button"
            onClick={() => setIsCreateOpen(true)}
          >
            Yeni tenant oluştur
          </button>
        ) : null}
      </header>

      {success ? (
        <div className={styles.successNotice} role="status" aria-live="polite">
          <div>
            <strong>{success.tenant.name} oluşturuldu</strong>
            <p>
              Tenant hazırlama durumunda açıldı. Ayrıntı ekranından güvenli
              metadata ve modül ayarlarını tamamlayabilirsiniz.
            </p>
            <small>Referans: {success.meta.correlation_id}</small>
          </div>
          <div>
            <Link
              href={`/platform/tenants/${encodeURIComponent(success.tenant.id)}`}
            >
              Tenantı aç
            </Link>
            <button
              type="button"
              aria-label="Başarı bildirimini kapat"
              onClick={() => setSuccess(null)}
            >
              ×
            </button>
          </div>
        </div>
      ) : null}

      <form
        className={styles.filterBar}
        role="search"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className={styles.filterField}>
          <span>Tenant ara</span>
          <input
            type="search"
            value={search}
            maxLength={200}
            placeholder="Ad veya tenant kodu"
            onChange={(event) => {
              setSearch(event.target.value);
              resetPage();
            }}
          />
        </label>
        <label className={styles.filterField}>
          <span>Yaşam döngüsü durumu</span>
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as PlatformTenantStatus | "");
              resetPage();
            }}
          >
            <option value="">Tüm durumlar</option>
            {PLATFORM_TENANT_STATUSES.map((tenantStatus) => (
              <option value={tenantStatus} key={tenantStatus}>
                {PLATFORM_STATUS_LABELS[tenantStatus]}
              </option>
            ))}
          </select>
        </label>
        {hasFilters ? (
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={() => {
              setSearch("");
              setStatus("");
              resetPage();
            }}
          >
            Filtreleri temizle
          </button>
        ) : null}
        <button
          className={styles.refreshButton}
          type="button"
          disabled={isLoading}
          onClick={retry}
        >
          {isLoading ? "Yükleniyor…" : "Yenile"}
        </button>
      </form>

      <div className={styles.listCard}>
        <div className={styles.listHeader}>
          <div>
            <span>Güvenli tenant metadata’sı</span>
            <h2>Tenant listesi</h2>
          </div>
          {!isLoading && !error ? (
            <p aria-live="polite">
              {filteredTenants.length.toLocaleString("tr-TR")} gösteriliyor ·
              toplam {tenants.length.toLocaleString("tr-TR")}
            </p>
          ) : null}
        </div>

        {error ? (
          <div className={styles.embeddedState} role="alert">
            <strong>Tenant listesi yüklenemedi</strong>
            <p>{error.message}</p>
            {error.reference ? (
              <small>Referans: {error.reference}</small>
            ) : null}
            <button className={styles.secondaryButton} type="button" onClick={retry}>
              Yeniden dene
            </button>
          </div>
        ) : isLoading ? (
          <div className={styles.embeddedState} role="status" aria-live="polite">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Tenant listesi yükleniyor</strong>
            <p>Cursor sayfalarındaki platform metadata’sı doğrulanıyor…</p>
          </div>
        ) : visibleTenants.length === 0 ? (
          <div className={styles.emptyState}>
            <span aria-hidden="true">T</span>
            <h3>
              {hasFilters ? "Eşleşen tenant bulunamadı" : "Henüz tenant yok"}
            </h3>
            <p>
              {hasFilters
                ? "Arama ifadesini veya yaşam döngüsü filtresini değiştirin."
                : "Yeni bir tenant oluşturulduğunda güvenli metadata burada görünecek."}
            </p>
            {hasFilters ? (
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={() => {
                  setSearch("");
                  setStatus("");
                  resetPage();
                }}
              >
                Filtreleri temizle
              </button>
            ) : canCreate ? (
              <button
                className={styles.primaryButton}
                type="button"
                onClick={() => setIsCreateOpen(true)}
              >
                İlk tenantı oluştur
              </button>
            ) : null}
          </div>
        ) : (
          <>
            <div className={styles.tableScroller}>
              <table className={styles.tenantTable}>
                <thead>
                  <tr>
                    <th scope="col">Tenant</th>
                    <th scope="col">Durum</th>
                    <th scope="col">Plan</th>
                    <th scope="col">Bölge</th>
                    <th scope="col">Güncellendi</th>
                    <th scope="col">
                      <span className={styles.visuallyHidden}>İşlemler</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTenants.map((tenant) => (
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
                      <td data-label="Bölge">
                        {PLATFORM_REGION_LABELS[tenant.data_region]}
                      </td>
                      <td data-label="Güncellendi">
                        <time dateTime={tenant.updated_at}>
                          {formatPlatformDate(tenant.updated_at)}
                        </time>
                      </td>
                      <td className={styles.actionCell}>
                        <Link
                          href={`/platform/tenants/${encodeURIComponent(tenant.id)}`}
                          aria-label={`${tenant.name} tenantını yönet`}
                        >
                          Yönet
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <footer className={styles.pagination}>
              <span>
                Sayfa {visiblePage} / {pageCount}
              </span>
              <div>
                <button
                  type="button"
                  disabled={visiblePage <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Önceki
                </button>
                <button
                  type="button"
                  disabled={visiblePage >= pageCount}
                  onClick={() =>
                    setPage((current) => Math.min(pageCount, current + 1))
                  }
                >
                  Sonraki
                </button>
              </div>
            </footer>
          </>
        )}
      </div>

      {isCreateOpen && canCreate ? (
        <CreateTenantDialog
          onClose={() => setIsCreateOpen(false)}
          onCreated={handleCreated}
        />
      ) : null}
    </section>
  );
}
