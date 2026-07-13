"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type Position,
  type PositionStatus,
  listPositions,
} from "@/lib/organization";

import { ArchivePositionDialog } from "./archive-position-dialog";
import styles from "./organization.module.css";
import {
  POSITION_STATUS_LABELS,
  formatOrganizationDate,
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";
import { PositionDialog } from "./position-dialog";

const PAGE_LIMIT = 25;
const INDEXABLE_SEARCH_PATTERN = /[\p{L}\p{N}]{3}/u;
const EXACT_POSITION_CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]?$/;

export function PositionCatalog({ canUpdate }: { canUpdate: boolean }) {
  const noticeRef = useRef<HTMLDivElement>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [positionStatus, setPositionStatus] = useState<PositionStatus | "">("");
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] =
    useState<OrganizationErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [editorPosition, setEditorPosition] =
    useState<Position | null | undefined>(undefined);
  const [archiveTarget, setArchiveTarget] = useState<Position | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeFocusRequest, setNoticeFocusRequest] = useState(0);

  useEffect(() => {
    if (noticeFocusRequest === 0) return;
    const frame = window.requestAnimationFrame(() => noticeRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [noticeFocusRequest]);

  useEffect(() => {
    let isActive = true;
    void listPositions({
      limit: PAGE_LIMIT,
      cursor,
      status: positionStatus,
      search: search || undefined,
    }).then(
      (page) => {
        if (!isActive) return;
        setPositions(page.data);
        setNextCursor(page.meta.next_cursor);
        setError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setPositions([]);
        setNextCursor(null);
        setError(organizationErrorPresentation(cause, "position_list"));
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [cursor, positionStatus, reloadKey, search]);

  function resetPage() {
    setCursor(null);
    setCursorHistory([]);
    setNextCursor(null);
    setEditorPosition(undefined);
    setArchiveTarget(null);
  }

  function reloadFirstPage() {
    resetPage();
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedSearch = searchDraft.trim();
    const searchInput = event.currentTarget.elements.namedItem("position_search");
    if (
      searchInput instanceof HTMLInputElement &&
      normalizedSearch.length > 0 &&
      !INDEXABLE_SEARCH_PATTERN.test(normalizedSearch) &&
      !EXACT_POSITION_CODE_PATTERN.test(normalizedSearch)
    ) {
      searchInput.setCustomValidity(
        "1–2 karakterli aramalar tam kod olmalı; diğer aramalar en az 3 ardışık harf veya rakam içermelidir.",
      );
      searchInput.reportValidity();
      return;
    }
    if (searchInput instanceof HTMLInputElement) searchInput.setCustomValidity("");
    setNotice(null);
    setSearch(normalizedSearch);
    reloadFirstPage();
  }

  function clearSearch() {
    setSearchDraft("");
    setSearch("");
    setNotice(null);
    reloadFirstPage();
  }

  function showNextPage() {
    if (!nextCursor || isLoading) return;
    setIsLoading(true);
    setError(null);
    setCursorHistory((history) => [...history, cursor]);
    setCursor(nextCursor);
    setEditorPosition(undefined);
    setArchiveTarget(null);
  }

  function showPreviousPage() {
    if (cursorHistory.length === 0 || isLoading) return;
    const previousCursor = cursorHistory[cursorHistory.length - 1] ?? null;
    setIsLoading(true);
    setError(null);
    setCursorHistory((history) => history.slice(0, -1));
    setCursor(previousCursor);
    setEditorPosition(undefined);
    setArchiveTarget(null);
  }

  function handlePositionSaved(savedPosition: Position, created: boolean) {
    setEditorPosition(undefined);
    setNotice(created ? "Pozisyon oluşturuldu." : "Pozisyon unvanı güncellendi.");
    setNoticeFocusRequest((request) => request + 1);

    if (created) {
      setPositionStatus("");
      setSearchDraft("");
      setSearch("");
      reloadFirstPage();
      return;
    }

    setPositions((currentPositions) =>
      currentPositions.map((position) =>
        position.id === savedPosition.id ? savedPosition : position,
      ),
    );
    if (search) reloadFirstPage();
  }

  function handlePositionArchived(archivedPosition: Position) {
    setArchiveTarget(null);
    setNotice(
      "Pozisyon arşivlendi. Geçmiş atamalar korunur ve yeni atamalarda kullanılamaz.",
    );
    setNoticeFocusRequest((request) => request + 1);
    setPositions((currentPositions) =>
      positionStatus === "active"
        ? currentPositions.filter((position) => position.id !== archivedPosition.id)
        : currentPositions.map((position) =>
            position.id === archivedPosition.id ? archivedPosition : position,
          ),
    );
  }

  const searchIsApplied = search.length > 0;

  return (
    <>
      <article
        className={styles.departmentCard}
        aria-labelledby="positions-title"
        aria-busy={isLoading}
      >
        <header className={styles.departmentHeader}>
          <div>
            <h2 id="positions-title">Pozisyon kataloğu</h2>
            <span>
              {isLoading
                ? "Katalog güncelleniyor…"
                : `${positions.length} pozisyon bu sayfada gösteriliyor`}
            </span>
          </div>
          <div className={styles.departmentTools}>
            <form className={styles.positionSearch} onSubmit={applySearch} role="search">
              <label htmlFor="position_search">Pozisyon ara</label>
              <div>
                <input
                  id="position_search"
                  name="position_search"
                  type="search"
                  value={searchDraft}
                  onChange={(event) => {
                    event.currentTarget.setCustomValidity("");
                    setSearchDraft(event.target.value);
                  }}
                  minLength={1}
                  maxLength={100}
                  placeholder="Kod veya unvan"
                />
                <button
                  className={styles.compactButton}
                  type="submit"
                  disabled={isLoading}
                >
                  Ara
                </button>
                {searchIsApplied ? (
                  <button
                    className={styles.compactButton}
                    type="button"
                    onClick={clearSearch}
                    disabled={isLoading}
                  >
                    Temizle
                  </button>
                ) : null}
              </div>
              <small>1–2 karakter tam kod; diğer aramalar en az 3 ardışık harf veya rakam.</small>
            </form>
            <div className={styles.statusFilter}>
              <label htmlFor="position_status_filter">Pozisyon durumu</label>
              <select
                id="position_status_filter"
                value={positionStatus}
                onChange={(event) => {
                  setPositionStatus(event.target.value as PositionStatus | "");
                  setNotice(null);
                  reloadFirstPage();
                }}
                disabled={isLoading}
              >
                <option value="">Tüm durumlar</option>
                <option value="active">Aktif pozisyonlar</option>
                <option value="archived">Arşiv geçmişi</option>
              </select>
            </div>
            <button
              className={styles.refreshButton}
              type="button"
              onClick={() => {
                setNotice(null);
                reloadFirstPage();
              }}
              disabled={isLoading}
            >
              Yenile
            </button>
            {canUpdate ? (
              <button
                className={styles.primaryButton}
                type="button"
                disabled={isLoading}
                onClick={() => {
                  setNotice(null);
                  setEditorPosition(null);
                }}
              >
                <span aria-hidden="true">＋</span>
                Yeni pozisyon
              </button>
            ) : null}
          </div>
        </header>

        {notice ? (
          <div
            ref={noticeRef}
            className={styles.departmentNotice}
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

        {error ? (
          <div className={styles.listError} role="alert">
            <div>
              <strong>Pozisyon kataloğu yüklenemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={reloadFirstPage}
            >
              Yeniden dene
            </button>
          </div>
        ) : isLoading && positions.length === 0 ? (
          <div className={styles.listLoading} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Pozisyonlar yükleniyor</strong>
            <span>Yeniden kullanılabilir unvanlar hazırlanıyor…</span>
          </div>
        ) : positions.length === 0 ? (
          <div className={styles.emptyState}>
            <div aria-hidden="true">P</div>
            <h3>
              {searchIsApplied
                ? "Aramayla eşleşen pozisyon yok"
                : positionStatus === "archived"
                  ? "Arşivlenmiş pozisyon yok"
                  : positionStatus === "active"
                    ? "Aktif pozisyon yok"
                    : "Henüz pozisyon yok"}
            </h3>
            <p>
              {searchIsApplied
                ? "Başka bir kod veya unvanla arayın ya da aramayı temizleyin."
                : "İlk pozisyonu oluşturarak çalışan atamalarında kullanılacak unvanları tanımlayın."}
            </p>
            {!searchIsApplied && !positionStatus && canUpdate ? (
              <button
                className={styles.primaryButton}
                type="button"
                onClick={() => setEditorPosition(null)}
              >
                Yeni pozisyon
              </button>
            ) : null}
          </div>
        ) : (
          <div className={styles.tableScroller}>
            <table className={`${styles.branchTable} ${styles.positionTable}`}>
              <thead>
                <tr>
                  <th scope="col">Pozisyon</th>
                  <th scope="col">Durum</th>
                  <th scope="col">Atama</th>
                  <th scope="col">Güncellendi</th>
                  <th scope="col">
                    <span className={styles.visuallyHidden}>İşlemler</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.id} data-position-status={position.status}>
                    <td data-label="Pozisyon">
                      <div className={styles.branchIdentity}>
                        <strong>{position.title}</strong>
                        <small>{position.code}</small>
                      </div>
                    </td>
                    <td data-label="Durum">
                      <span className={styles.statusBadge} data-status={position.status}>
                        <span aria-hidden="true" />
                        {POSITION_STATUS_LABELS[position.status]}
                      </span>
                      {position.archived_at ? (
                        <small className={styles.archiveDate}>
                          {formatOrganizationDate(position.archived_at)}
                        </small>
                      ) : null}
                    </td>
                    <td data-label="Atama">
                      <span
                        className={styles.assignmentBadge}
                        data-accepts-assignments={position.accepts_new_assignments}
                      >
                        {position.accepts_new_assignments
                          ? "Yeni atamaya açık"
                          : "Yeni atamaya kapalı"}
                      </span>
                    </td>
                    <td data-label="Güncellendi">
                      {formatOrganizationDate(position.updated_at)}
                    </td>
                    <td className={styles.actionCell}>
                      {canUpdate && position.status === "active" ? (
                        <div className={styles.rowActions}>
                          <button
                            className={styles.inspectButton}
                            type="button"
                            disabled={isLoading}
                            onClick={() => setEditorPosition(position)}
                            aria-label={`${position.title} pozisyonunu düzenle`}
                          >
                            Düzenle
                          </button>
                          <button
                            className={styles.archiveButton}
                            type="button"
                            disabled={isLoading}
                            onClick={() => setArchiveTarget(position)}
                            aria-label={`${position.title} pozisyonunu arşivle`}
                          >
                            Arşivle
                          </button>
                        </div>
                      ) : (
                        <span className={styles.historyLabel}>
                          {position.status === "archived" ? "Geçmiş kayıt" : "Salt okunur"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!error && (positions.length > 0 || cursorHistory.length > 0) ? (
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
      </article>

      {editorPosition !== undefined && canUpdate ? (
        <PositionDialog
          key={editorPosition?.id ?? "new"}
          position={editorPosition}
          onClose={() => setEditorPosition(undefined)}
          onSaved={handlePositionSaved}
        />
      ) : null}

      {archiveTarget && canUpdate ? (
        <ArchivePositionDialog
          position={archiveTarget}
          onClose={() => setArchiveTarget(null)}
          onArchived={handlePositionArchived}
        />
      ) : null}
    </>
  );
}
