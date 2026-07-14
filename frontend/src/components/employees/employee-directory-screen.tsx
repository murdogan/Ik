"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  type Employee,
  type EmployeeStatus,
  EMPLOYEE_STATUSES,
  listEmployees,
} from "@/lib/employees";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type Branch,
  type Department,
  type LegalEntity,
  type Position,
  listBranches,
  listDepartments,
  listLegalEntities,
  listPositions,
} from "@/lib/organization";

import { EmployeeCreateDialog } from "./employee-create-dialog";
import {
  EMPLOYEE_STATUS_LABELS,
  type EmployeeErrorPresentation,
  employeeErrorPresentation,
  employeeFullName,
  formatEmployeeDate,
} from "./employee-presentation";
import { EmployeeStatusBadge } from "./employee-status-badge";
import styles from "./employees.module.css";

const PAGE_LIMIT = 25;
const SELECTOR_LIMIT = 100;

interface EmployeeFilters {
  q: string;
  status: EmployeeStatus | "";
  legalEntityId: string;
  branchId: string;
  departmentId: string;
  positionId: string;
}

const EMPTY_FILTERS: EmployeeFilters = {
  q: "",
  status: "",
  legalEntityId: "",
  branchId: "",
  departmentId: "",
  positionId: "",
};

function employeeInitial(employee: Employee): string {
  return employee.first_name.slice(0, 1).toLocaleUpperCase("tr-TR") || "Ç";
}

function currentDepartment(employee: Employee): string {
  return employee.current_assignment?.department.name || employee.department || "—";
}

function currentPosition(employee: Employee): string {
  return employee.current_assignment?.position.title || employee.position || "Atama yok";
}

export function EmployeeDirectoryScreen() {
  const router = useRouter();
  const { user: actor } = useSession();
  const canCreateEmployees = hasPermission(
    actor,
    AUTHORIZATION_PERMISSIONS.updateEmployees,
  );
  const canReadOrganization = hasPermission(
    actor,
    AUTHORIZATION_PERMISSIONS.readOrganization,
  );
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [filters, setFilters] = useState<EmployeeFilters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<EmployeeFilters>(EMPTY_FILTERS);
  const [currentCursor, setCurrentCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<EmployeeErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const [legalEntities, setLegalEntities] = useState<LegalEntity[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [isLoadingCatalogs, setIsLoadingCatalogs] = useState(canReadOrganization);
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;
    void listEmployees({
      q: filters.q,
      status: filters.status,
      legalEntityId: filters.legalEntityId,
      branchId: filters.branchId,
      departmentId: filters.departmentId,
      positionId: filters.positionId,
      limit: PAGE_LIMIT,
      cursor: currentCursor,
    }).then(
      (page) => {
        if (!isActive) return;
        setEmployees(page.data);
        setNextCursor(page.meta.next_cursor);
        setError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setEmployees([]);
        setNextCursor(null);
        setError(employeeErrorPresentation(cause, "list"));
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [currentCursor, filters, reloadKey]);

  useEffect(() => {
    if (!canReadOrganization) {
      return;
    }

    let isActive = true;
    void Promise.allSettled([
      listLegalEntities({ limit: SELECTOR_LIMIT }),
      listDepartments({ limit: SELECTOR_LIMIT, status: "active" }),
      listPositions({ limit: SELECTOR_LIMIT, status: "active" }),
    ]).then((results) => {
      if (!isActive) return;
      const [legalEntityResult, departmentResult, positionResult] = results;
      setLegalEntities(
        legalEntityResult.status === "fulfilled"
          ? legalEntityResult.value.data.filter((item) => item.status === "active")
          : [],
      );
      setDepartments(
        departmentResult.status === "fulfilled"
          ? departmentResult.value.data.filter((item) => item.status === "active")
          : [],
      );
      setPositions(
        positionResult.status === "fulfilled"
          ? positionResult.value.data.filter((item) => item.status === "active")
          : [],
      );
      setCatalogNotice(
        results.some((result) => result.status === "rejected")
          ? "Bazı organizasyon filtreleri yüklenemedi. Arama ve durum filtresini kullanmaya devam edebilirsiniz."
          : null,
      );
      setIsLoadingCatalogs(false);
    });
    return () => {
      isActive = false;
    };
  }, [canReadOrganization]);

  useEffect(() => {
    if (!canReadOrganization || !draftFilters.legalEntityId) {
      return;
    }

    let isActive = true;
    void listBranches({
      legalEntityId: draftFilters.legalEntityId,
      status: "active",
      limit: SELECTOR_LIMIT,
    }).then(
      (page) => {
        if (!isActive) return;
        setBranches(page.data.filter((item) => item.status === "active"));
        setIsLoadingBranches(false);
      },
      () => {
        if (!isActive) return;
        setBranches([]);
        setCatalogNotice(
          "Şube seçenekleri yüklenemedi. Diğer filtreleri kullanmaya devam edebilirsiniz.",
        );
        setIsLoadingBranches(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [canReadOrganization, draftFilters.legalEntityId]);

  function resetPagination() {
    setCurrentCursor(null);
    setCursorHistory([]);
    setNextCursor(null);
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    resetPagination();
    setFilters({ ...draftFilters, q: draftFilters.q.trim() });
    setReloadKey((key) => key + 1);
  }

  function clearFilters() {
    setIsLoading(true);
    setError(null);
    setDraftFilters(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setBranches([]);
    setIsLoadingBranches(false);
    resetPagination();
    setReloadKey((key) => key + 1);
  }

  function reload() {
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  function showNextPage() {
    if (!nextCursor || isLoading) return;
    setIsLoading(true);
    setError(null);
    setCursorHistory((history) => [...history, currentCursor]);
    setCurrentCursor(nextCursor);
  }

  function showPreviousPage() {
    if (cursorHistory.length === 0 || isLoading) return;
    setIsLoading(true);
    setError(null);
    const previousCursor = cursorHistory[cursorHistory.length - 1] ?? null;
    setCursorHistory((history) => history.slice(0, -1));
    setCurrentCursor(previousCursor);
  }

  function handleCreated(employee: Employee) {
    setIsCreateOpen(false);
    setIsLoading(true);
    setError(null);
    resetPagination();
    setReloadKey((key) => key + 1);
    router.push(`/employees/${encodeURIComponent(employee.id)}`);
  }

  const hasFilters = Object.values(filters).some(Boolean);
  const hasDraftFilters = Object.values(draftFilters).some(Boolean);

  return (
    <section className={styles.page} aria-labelledby="employees-title">
      <header className={styles.pageHeader}>
        <div>
          <span>Çalışan ana verisi</span>
          <h1 id="employees-title">Çalışanlar</h1>
          <p>
            Çalışanları güvenli tenant dizininde bulun, güncel organizasyonlarını görün ve
            temel bir çalışan kaydı oluşturun.
          </p>
        </div>
        {canCreateEmployees ? (
          <button
            className={styles.primaryButton}
            type="button"
            onClick={() => setIsCreateOpen(true)}
          >
            <span aria-hidden="true">＋</span>
            Yeni çalışan
          </button>
        ) : null}
      </header>

      <form className={styles.filterBar} role="search" onSubmit={applyFilters}>
        <div className={`${styles.filterField} ${styles.searchField}`}>
          <label htmlFor="employee_search">Çalışan ara</label>
          <div>
            <span aria-hidden="true">⌕</span>
            <input
              id="employee_search"
              type="search"
              value={draftFilters.q}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, q: event.target.value }))
              }
              placeholder="Ad, çalışan numarası veya iş e-postası"
              maxLength={320}
            />
          </div>
        </div>

        <div className={styles.filterField}>
          <label htmlFor="employee_status_filter">Durum</label>
          <select
            id="employee_status_filter"
            value={draftFilters.status}
            onChange={(event) =>
              setDraftFilters((current) => ({
                ...current,
                status: event.target.value as EmployeeStatus | "",
              }))
            }
          >
            <option value="">Tüm durumlar</option>
            {EMPLOYEE_STATUSES.map((status) => (
              <option value={status} key={status}>
                {EMPLOYEE_STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>

        {canReadOrganization ? (
          <>
            <div className={styles.filterField}>
              <label htmlFor="legal_entity_filter">Tüzel kişilik</label>
              <select
                id="legal_entity_filter"
                value={draftFilters.legalEntityId}
                disabled={isLoadingCatalogs}
                onChange={(event) => {
                  const legalEntityId = event.target.value;
                  setBranches([]);
                  setIsLoadingBranches(Boolean(legalEntityId));
                  setDraftFilters((current) => ({
                    ...current,
                    legalEntityId,
                    branchId: "",
                  }));
                }}
              >
                <option value="">
                  {isLoadingCatalogs ? "Seçenekler yükleniyor…" : "Tüm tüzel kişilikler"}
                </option>
                {legalEntities.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.filterField}>
              <label htmlFor="branch_filter">Şube</label>
              <select
                id="branch_filter"
                value={draftFilters.branchId}
                disabled={!draftFilters.legalEntityId || isLoadingBranches}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    branchId: event.target.value,
                  }))
                }
              >
                <option value="">
                  {isLoadingBranches
                    ? "Şubeler yükleniyor…"
                    : draftFilters.legalEntityId
                      ? "Tüm şubeler"
                      : "Önce tüzel kişilik seçin"}
                </option>
                {branches.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.filterField}>
              <label htmlFor="department_filter">Departman</label>
              <select
                id="department_filter"
                value={draftFilters.departmentId}
                disabled={isLoadingCatalogs}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    departmentId: event.target.value,
                  }))
                }
              >
                <option value="">Tüm departmanlar</option>
                {departments.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>

            <div className={styles.filterField}>
              <label htmlFor="position_filter">Pozisyon</label>
              <select
                id="position_filter"
                value={draftFilters.positionId}
                disabled={isLoadingCatalogs}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    positionId: event.target.value,
                  }))
                }
              >
                <option value="">Tüm pozisyonlar</option>
                {positions.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </div>
          </>
        ) : null}

        <div className={styles.filterActions}>
          <button className={styles.filterButton} type="submit" disabled={isLoading}>
            Filtrele
          </button>
          {(hasFilters || hasDraftFilters) && (
            <button className={styles.clearButton} type="button" onClick={clearFilters}>
              Temizle
            </button>
          )}
        </div>
      </form>

      {catalogNotice ? (
        <div className={styles.filterNotice} role="status">
          {catalogNotice}
        </div>
      ) : null}

      <div className={styles.listCard} aria-busy={isLoading}>
        <div className={styles.listHeader}>
          <div>
            <h2>Çalışan dizini</h2>
            <span>
              {isLoading
                ? "Liste güncelleniyor…"
                : `${employees.length} çalışan bu sayfada gösteriliyor`}
            </span>
          </div>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={reload}
            disabled={isLoading}
          >
            Yenile
          </button>
        </div>

        {error ? (
          <div className={styles.listError} role="alert">
            <div>
              <strong>Çalışanlar yüklenemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
            <button className={styles.secondaryButton} type="button" onClick={reload}>
              Yeniden dene
            </button>
          </div>
        ) : isLoading && employees.length === 0 ? (
          <div className={styles.listLoading} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Çalışanlar yükleniyor</strong>
            <span>Tenant çalışan dizini hazırlanıyor…</span>
          </div>
        ) : employees.length === 0 ? (
          <div className={styles.emptyState}>
            <div aria-hidden="true">Ç</div>
            <h3>{hasFilters ? "Eşleşen çalışan bulunamadı" : "Henüz çalışan yok"}</h3>
            <p>
              {hasFilters
                ? "Arama ifadenizi veya organizasyon filtrelerinizi değiştirin."
                : canCreateEmployees
                  ? "İlk temel çalışan kaydını oluşturarak başlayın."
                  : "Çalışan kaydı oluşturulduğunda burada görünecek."}
            </p>
            {hasFilters ? (
              <button className={styles.secondaryButton} type="button" onClick={clearFilters}>
                Filtreleri temizle
              </button>
            ) : canCreateEmployees ? (
              <button
                className={styles.primaryButton}
                type="button"
                onClick={() => setIsCreateOpen(true)}
              >
                Yeni çalışan
              </button>
            ) : null}
          </div>
        ) : (
          <div className={styles.tableScroller}>
            <table className={styles.employeeTable}>
              <thead>
                <tr>
                  <th scope="col">Çalışan</th>
                  <th scope="col">Durum</th>
                  <th scope="col">Organizasyon</th>
                  <th scope="col">İşe başlangıç</th>
                  <th scope="col">
                    <span className={styles.visuallyHidden}>İşlemler</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {employees.map((employee) => (
                  <tr key={employee.id}>
                    <td data-label="Çalışan">
                      <Link
                        className={styles.employeeIdentity}
                        href={`/employees/${encodeURIComponent(employee.id)}`}
                      >
                        <span className={styles.tableAvatar} aria-hidden="true">
                          {employeeInitial(employee)}
                        </span>
                        <span>
                          <strong>{employeeFullName(employee)}</strong>
                          <small>
                            {employee.employee_number}
                            {employee.email ? ` · ${employee.email}` : ""}
                          </small>
                        </span>
                      </Link>
                    </td>
                    <td data-label="Durum">
                      <EmployeeStatusBadge status={employee.status} />
                    </td>
                    <td data-label="Organizasyon">
                      <span className={styles.organizationCell}>
                        <strong>{currentDepartment(employee)}</strong>
                        <small>{currentPosition(employee)}</small>
                      </span>
                    </td>
                    <td data-label="İşe başlangıç">
                      {formatEmployeeDate(employee.employment_start_date)}
                    </td>
                    <td className={styles.actionCell}>
                      <Link
                        className={styles.inspectButton}
                        href={`/employees/${encodeURIComponent(employee.id)}`}
                        aria-label={`${employeeFullName(employee)} çalışanını incele`}
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

        {!error && (employees.length > 0 || cursorHistory.length > 0) ? (
          <footer className={styles.pagination}>
            <span>Sayfa {cursorHistory.length + 1}</span>
            <div>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={showPreviousPage}
                disabled={isLoading || cursorHistory.length === 0}
              >
                Önceki
              </button>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={showNextPage}
                disabled={isLoading || !nextCursor}
              >
                Sonraki
              </button>
            </div>
          </footer>
        ) : null}
      </div>

      {isCreateOpen && canCreateEmployees ? (
        <EmployeeCreateDialog
          onClose={() => setIsCreateOpen(false)}
          onCreated={handleCreated}
        />
      ) : null}

    </section>
  );
}
