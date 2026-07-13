"use client";

import { useEffect, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type Branch,
  type BranchStatus,
  type LegalEntity,
  listBranches,
  listLegalEntities,
  readLegalEntity,
} from "@/lib/organization";

import { ArchiveBranchDialog } from "./archive-branch-dialog";
import { BranchDialog } from "./branch-dialog";
import { DepartmentHierarchy } from "./department-hierarchy";
import { LegalEntityForm } from "./legal-entity-form";
import styles from "./organization.module.css";
import {
  BRANCH_STATUS_LABELS,
  formatOrganizationDate,
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

const PAGE_LIMIT = 25;

export function OrganizationScreen() {
  const { user } = useSession();
  const canUpdate = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.updateOrganization,
  );

  const [legalEntities, setLegalEntities] = useState<LegalEntity[]>([]);
  const [legalEntity, setLegalEntity] = useState<LegalEntity | null>(null);
  const [selectedLegalEntityId, setSelectedLegalEntityId] = useState<string | null>(
    null,
  );
  const [legalCursor, setLegalCursor] = useState<string | null>(null);
  const [legalCursorHistory, setLegalCursorHistory] = useState<(string | null)[]>([]);
  const [legalNextCursor, setLegalNextCursor] = useState<string | null>(null);
  const [isLoadingLegalList, setIsLoadingLegalList] = useState(true);
  const [isLoadingLegalEntity, setIsLoadingLegalEntity] = useState(false);
  const [legalListError, setLegalListError] =
    useState<OrganizationErrorPresentation | null>(null);
  const [legalEntityError, setLegalEntityError] =
    useState<OrganizationErrorPresentation | null>(null);
  const [legalReloadKey, setLegalReloadKey] = useState(0);
  const [legalDetailReloadKey, setLegalDetailReloadKey] = useState(0);

  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchStatus, setBranchStatus] = useState<BranchStatus | "">("");
  const [branchCursor, setBranchCursor] = useState<string | null>(null);
  const [branchCursorHistory, setBranchCursorHistory] = useState<(string | null)[]>([]);
  const [branchNextCursor, setBranchNextCursor] = useState<string | null>(null);
  const [isLoadingBranches, setIsLoadingBranches] = useState(false);
  const [branchError, setBranchError] =
    useState<OrganizationErrorPresentation | null>(null);
  const [branchReloadKey, setBranchReloadKey] = useState(0);
  const [editingBranch, setEditingBranch] = useState<Branch | null | undefined>(
    undefined,
  );
  const [archiveTarget, setArchiveTarget] = useState<Branch | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const archiveNoticeRef = useRef<HTMLDivElement>(null);
  const [archiveFocusRequest, setArchiveFocusRequest] = useState(0);

  useEffect(() => {
    if (archiveFocusRequest === 0) return;
    const frame = window.requestAnimationFrame(() => archiveNoticeRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [archiveFocusRequest]);

  useEffect(() => {
    let isActive = true;
    void listLegalEntities({ limit: PAGE_LIMIT, cursor: legalCursor }).then(
      (page) => {
        if (!isActive) return;
        setLegalEntities(page.data);
        setLegalNextCursor(page.meta.next_cursor);
        setLegalListError(null);
        setIsLoadingLegalList(false);
        setIsLoadingLegalEntity(page.data.length > 0);
        setIsLoadingBranches(page.data.length > 0);
        if (page.data.length === 0) {
          setLegalEntity(null);
          setBranches([]);
          setBranchNextCursor(null);
        }
        setSelectedLegalEntityId((currentId) => {
          if (currentId && page.data.some((entity) => entity.id === currentId)) {
            return currentId;
          }
          return page.data.find((entity) => entity.is_default)?.id ?? page.data[0]?.id ?? null;
        });
      },
      (cause) => {
        if (!isActive) return;
        setLegalEntities([]);
        setLegalNextCursor(null);
        setLegalListError(organizationErrorPresentation(cause, "legal_list"));
        setIsLoadingLegalList(false);
        setIsLoadingLegalEntity(false);
        setIsLoadingBranches(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [legalCursor, legalReloadKey]);

  useEffect(() => {
    if (!selectedLegalEntityId) {
      return;
    }

    let isActive = true;
    void readLegalEntity(selectedLegalEntityId).then(
      (entity) => {
        if (!isActive) return;
        setLegalEntity(entity);
        setIsLoadingLegalEntity(false);
      },
      (cause) => {
        if (!isActive) return;
        setLegalEntity(null);
        setLegalEntityError(organizationErrorPresentation(cause, "legal_read"));
        setIsLoadingLegalEntity(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [legalDetailReloadKey, selectedLegalEntityId]);

  useEffect(() => {
    if (!selectedLegalEntityId) {
      return;
    }

    let isActive = true;
    void listBranches({
      legalEntityId: selectedLegalEntityId,
      status: branchStatus,
      limit: PAGE_LIMIT,
      cursor: branchCursor,
    }).then(
      (page) => {
        if (!isActive) return;
        setBranches(page.data);
        setBranchNextCursor(page.meta.next_cursor);
        setBranchError(null);
        setIsLoadingBranches(false);
      },
      (cause) => {
        if (!isActive) return;
        setBranches([]);
        setBranchNextCursor(null);
        setBranchError(organizationErrorPresentation(cause, "branch_list"));
        setIsLoadingBranches(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [branchCursor, branchReloadKey, branchStatus, selectedLegalEntityId]);

  function resetBranchPage() {
    setBranchCursor(null);
    setBranchCursorHistory([]);
    setBranchNextCursor(null);
    setEditingBranch(undefined);
    setArchiveTarget(null);
  }

  function selectLegalEntity(entityId: string) {
    if (entityId === selectedLegalEntityId) return;
    setSelectedLegalEntityId(entityId);
    setLegalEntity(null);
    setIsLoadingLegalEntity(true);
    setIsLoadingBranches(true);
    setLegalEntityError(null);
    setBranches([]);
    setBranchError(null);
    setNotice(null);
    resetBranchPage();
  }

  function showNextLegalPage() {
    if (!legalNextCursor || isLoadingLegalList) return;
    setIsLoadingLegalList(true);
    setLegalListError(null);
    setLegalCursorHistory((history) => [...history, legalCursor]);
    setLegalCursor(legalNextCursor);
    setSelectedLegalEntityId(null);
    setLegalEntity(null);
    setBranches([]);
    resetBranchPage();
  }

  function showPreviousLegalPage() {
    if (legalCursorHistory.length === 0 || isLoadingLegalList) return;
    const previousCursor = legalCursorHistory[legalCursorHistory.length - 1] ?? null;
    setIsLoadingLegalList(true);
    setLegalListError(null);
    setLegalCursorHistory((history) => history.slice(0, -1));
    setLegalCursor(previousCursor);
    setSelectedLegalEntityId(null);
    setLegalEntity(null);
    setBranches([]);
    resetBranchPage();
  }

  function updateSelectedLegalEntity(updatedEntity: LegalEntity) {
    setLegalEntity(updatedEntity);
    setLegalEntities((entities) =>
      entities.map((entity) =>
        entity.id === updatedEntity.id ? updatedEntity : entity,
      ),
    );
  }

  function showNextBranchPage() {
    if (!branchNextCursor || isLoadingBranches) return;
    setIsLoadingBranches(true);
    setBranchError(null);
    setBranchCursorHistory((history) => [...history, branchCursor]);
    setBranchCursor(branchNextCursor);
    setEditingBranch(undefined);
    setArchiveTarget(null);
  }

  function showPreviousBranchPage() {
    if (branchCursorHistory.length === 0 || isLoadingBranches) return;
    const previousCursor = branchCursorHistory[branchCursorHistory.length - 1] ?? null;
    setIsLoadingBranches(true);
    setBranchError(null);
    setBranchCursorHistory((history) => history.slice(0, -1));
    setBranchCursor(previousCursor);
    setEditingBranch(undefined);
    setArchiveTarget(null);
  }

  function handleBranchSaved(savedBranch: Branch, created: boolean) {
    setEditingBranch(undefined);
    setNotice(created ? "Şube oluşturuldu." : "Şube bilgileri güncellendi.");
    if (created) {
      setBranchStatus("");
      resetBranchPage();
      setIsLoadingBranches(true);
      setBranchReloadKey((key) => key + 1);
      return;
    }
    setBranches((currentBranches) =>
      currentBranches.map((branch) =>
        branch.id === savedBranch.id ? savedBranch : branch,
      ),
    );
  }

  function handleBranchArchived(archivedBranch: Branch) {
    setArchiveTarget(null);
    setNotice(
      "Şube arşivlendi. Geçmiş kaydı korunur ve yeni çalışan atamalarında kullanılamaz.",
    );
    setArchiveFocusRequest((request) => request + 1);
    setBranches((currentBranches) =>
      branchStatus === "active"
        ? currentBranches.filter((branch) => branch.id !== archivedBranch.id)
        : currentBranches.map((branch) =>
            branch.id === archivedBranch.id ? archivedBranch : branch,
          ),
    );
  }

  const legalEntityReady =
    legalEntity !== null && legalEntity.id === selectedLegalEntityId;

  return (
    <section className={styles.page} aria-labelledby="organization-title">
      <header className={styles.pageHeader}>
        <div>
          <span>Tenant organizasyonu</span>
          <h1 id="organization-title">Organizasyon</h1>
          <p>
            Tüzel kişilik ayarlarını, şube ve lokasyonları ve departman
            hiyerarşisini tek çalışma alanında güncel tutun.
          </p>
        </div>
        {canUpdate && legalEntityReady ? (
          <button
            className={styles.primaryButton}
            type="button"
            onClick={() => {
              setNotice(null);
              setEditingBranch(null);
            }}
            disabled={legalEntity.status !== "active"}
            title={
              legalEntity.status === "active"
                ? undefined
                : "Pasif tüzel kişilik altında yeni şube oluşturulamaz."
            }
          >
            <span aria-hidden="true">＋</span>
            Yeni şube
          </button>
        ) : null}
      </header>

      <div className={styles.entitySelector} aria-busy={isLoadingLegalList}>
        <div className={styles.selectorField}>
          <label htmlFor="legal_entity_selector">Tüzel kişilik</label>
          <select
            id="legal_entity_selector"
            value={selectedLegalEntityId ?? ""}
            onChange={(event) => selectLegalEntity(event.target.value)}
            disabled={isLoadingLegalList || legalEntities.length === 0}
          >
            {legalEntities.length === 0 ? (
              <option value="">Tüzel kişilik bulunamadı</option>
            ) : null}
            {legalEntities.map((entity) => (
              <option value={entity.id} key={entity.id}>
                {entity.name}{entity.is_default ? " · Varsayılan" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.selectorPage}>
          <span>Tüzel kişilik sayfası {legalCursorHistory.length + 1}</span>
          <button
            className={styles.compactButton}
            type="button"
            onClick={showPreviousLegalPage}
            disabled={isLoadingLegalList || legalCursorHistory.length === 0}
          >
            Önceki
          </button>
          <button
            className={styles.compactButton}
            type="button"
            onClick={showNextLegalPage}
            disabled={isLoadingLegalList || !legalNextCursor}
          >
            Sonraki
          </button>
        </div>
      </div>

      {legalListError ? (
        <div className={styles.sectionError} role="alert">
          <div>
            <strong>Tüzel kişilikler yüklenemedi</strong>
            <span>{legalListError.message}</span>
            {legalListError.reference ? (
              <small>Referans: {legalListError.reference}</small>
            ) : null}
          </div>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={() => {
              setIsLoadingLegalList(true);
              setLegalListError(null);
              setLegalReloadKey((key) => key + 1);
            }}
          >
            Yeniden dene
          </button>
        </div>
      ) : isLoadingLegalList || isLoadingLegalEntity ? (
        <div className={styles.sectionLoading} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          <strong>Organizasyon ayarları yükleniyor</strong>
        </div>
      ) : legalEntityError ? (
        <div className={styles.sectionError} role="alert">
          <div>
            <strong>Tüzel kişilik yüklenemedi</strong>
            <span>{legalEntityError.message}</span>
            {legalEntityError.reference ? (
              <small>Referans: {legalEntityError.reference}</small>
            ) : null}
          </div>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={() => {
              if (!selectedLegalEntityId) return;
              setIsLoadingLegalEntity(true);
              setLegalEntityError(null);
              setLegalDetailReloadKey((key) => key + 1);
            }}
          >
            Yeniden dene
          </button>
        </div>
      ) : legalEntityReady ? (
        <>
          <LegalEntityForm
            key={legalEntity.id}
            entity={legalEntity}
            canEdit={canUpdate}
            onUpdated={updateSelectedLegalEntity}
          />

          {notice ? (
            <div
              ref={archiveNoticeRef}
              className={styles.pageNotice}
              role="status"
              tabIndex={-1}
            >
              <span aria-hidden="true">✓</span>
              <span>{notice}</span>
              <button type="button" onClick={() => setNotice(null)} aria-label="Bildirimi kapat">
                ×
              </button>
            </div>
          ) : null}

          <article className={styles.branchCard} aria-labelledby="branches-title">
            <header className={styles.branchHeader}>
              <div>
                <h2 id="branches-title">Şubeler ve lokasyonlar</h2>
                <span>
                  {isLoadingBranches
                    ? "Liste güncelleniyor…"
                    : `${branches.length} şube bu sayfada gösteriliyor`}
                </span>
              </div>
              <div className={styles.branchTools}>
                <div className={styles.statusFilter}>
                  <label htmlFor="branch_status_filter">Şube durumu</label>
                  <select
                    id="branch_status_filter"
                    value={branchStatus}
                    onChange={(event) => {
                      setIsLoadingBranches(true);
                      setBranchStatus(event.target.value as BranchStatus | "");
                      resetBranchPage();
                      setBranchError(null);
                      setNotice(null);
                    }}
                    disabled={isLoadingBranches}
                  >
                    <option value="">Tüm durumlar</option>
                    <option value="active">Aktif şubeler</option>
                    <option value="archived">Arşiv geçmişi</option>
                  </select>
                </div>
                <button
                  className={styles.refreshButton}
                  type="button"
                  onClick={() => {
                    setIsLoadingBranches(true);
                    setBranchError(null);
                    setBranchReloadKey((key) => key + 1);
                  }}
                  disabled={isLoadingBranches}
                >
                  Yenile
                </button>
              </div>
            </header>

            {branchError ? (
              <div className={styles.listError} role="alert">
                <div>
                  <strong>Şubeler yüklenemedi</strong>
                  <span>{branchError.message}</span>
                  {branchError.reference ? (
                    <small>Referans: {branchError.reference}</small>
                  ) : null}
                </div>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={() => {
                    setIsLoadingBranches(true);
                    setBranchError(null);
                    setBranchReloadKey((key) => key + 1);
                  }}
                >
                  Yeniden dene
                </button>
              </div>
            ) : isLoadingBranches && branches.length === 0 ? (
              <div className={styles.listLoading} role="status">
                <span className={styles.spinner} aria-hidden="true" />
                <strong>Şubeler yükleniyor</strong>
                <span>Lokasyon kayıtları hazırlanıyor…</span>
              </div>
            ) : branches.length === 0 ? (
              <div className={styles.emptyState}>
                <div aria-hidden="true">O</div>
                <h3>
                  {branchStatus === "archived"
                    ? "Arşivlenmiş şube yok"
                    : branchStatus === "active"
                      ? "Aktif şube yok"
                      : "Henüz şube yok"}
                </h3>
                <p>
                  {branchStatus
                    ? "Başka bir durum seçerek şube geçmişini inceleyin."
                    : "İlk şubeyi oluşturarak organizasyon lokasyonlarını tanımlayın."}
                </p>
                {!branchStatus && canUpdate && legalEntity.status === "active" ? (
                  <button
                    className={styles.primaryButton}
                    type="button"
                    onClick={() => setEditingBranch(null)}
                  >
                    Yeni şube
                  </button>
                ) : null}
              </div>
            ) : (
              <div className={styles.tableScroller}>
                <table className={styles.branchTable}>
                  <thead>
                    <tr>
                      <th scope="col">Şube</th>
                      <th scope="col">Lokasyon</th>
                      <th scope="col">Saat dilimi</th>
                      <th scope="col">Durum</th>
                      <th scope="col">Atama</th>
                      <th scope="col"><span className={styles.visuallyHidden}>İşlemler</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {branches.map((branch) => (
                      <tr key={branch.id} data-branch-status={branch.status}>
                        <td data-label="Şube">
                          <div className={styles.branchIdentity}>
                            <strong>{branch.name}</strong>
                            <small>{branch.code}</small>
                          </div>
                        </td>
                        <td data-label="Lokasyon">
                          <div className={styles.locationText}>
                            <span>{branch.city ?? "—"}</span>
                            <small>{branch.country_code ?? "Ülke belirtilmedi"}</small>
                          </div>
                        </td>
                        <td data-label="Saat dilimi">{branch.timezone}</td>
                        <td data-label="Durum">
                          <span className={styles.statusBadge} data-status={branch.status}>
                            <span aria-hidden="true" />
                            {BRANCH_STATUS_LABELS[branch.status]}
                          </span>
                          {branch.archived_at ? (
                            <small className={styles.archiveDate}>
                              {formatOrganizationDate(branch.archived_at)}
                            </small>
                          ) : null}
                        </td>
                        <td data-label="Atama">
                          <span
                            className={styles.assignmentBadge}
                            data-accepts-assignments={branch.accepts_new_assignments}
                          >
                            {branch.accepts_new_assignments
                              ? "Yeni atamaya açık"
                              : "Yeni atamaya kapalı"}
                          </span>
                        </td>
                        <td className={styles.actionCell}>
                          {canUpdate && branch.status === "active" ? (
                            <div className={styles.rowActions}>
                              <button
                                className={styles.inspectButton}
                                type="button"
                                onClick={() => setEditingBranch(branch)}
                                aria-label={`${branch.name} şubesini düzenle`}
                              >
                                Düzenle
                              </button>
                              <button
                                className={styles.archiveButton}
                                type="button"
                                onClick={() => setArchiveTarget(branch)}
                                aria-label={`${branch.name} şubesini arşivle`}
                              >
                                Arşivle
                              </button>
                            </div>
                          ) : (
                            <span className={styles.historyLabel}>
                              {branch.status === "archived" ? "Geçmiş kayıt" : "Salt okunur"}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!branchError && (branches.length > 0 || branchCursorHistory.length > 0) ? (
              <footer className={styles.pagination}>
                <span>Sayfa {branchCursorHistory.length + 1}</span>
                <div>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={showPreviousBranchPage}
                    disabled={isLoadingBranches || branchCursorHistory.length === 0}
                  >
                    Önceki
                  </button>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={showNextBranchPage}
                    disabled={isLoadingBranches || !branchNextCursor}
                  >
                    Sonraki
                  </button>
                </div>
              </footer>
            ) : null}
          </article>

          <DepartmentHierarchy canUpdate={canUpdate} />
        </>
      ) : (
        <div className={styles.emptyState}>
          <div aria-hidden="true">O</div>
          <h3>Tüzel kişilik bulunamadı</h3>
          <p>Organizasyon ayarlarını gösterecek bir tüzel kişilik kaydı yok.</p>
        </div>
      )}

      {editingBranch !== undefined && legalEntityReady && canUpdate ? (
        <BranchDialog
          key={editingBranch?.id ?? "new"}
          legalEntity={legalEntity}
          branch={editingBranch}
          onClose={() => setEditingBranch(undefined)}
          onSaved={handleBranchSaved}
        />
      ) : null}

      {archiveTarget && canUpdate ? (
        <ArchiveBranchDialog
          branch={archiveTarget}
          onClose={() => setArchiveTarget(null)}
          onArchived={handleBranchArchived}
        />
      ) : null}
    </section>
  );
}
