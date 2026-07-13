"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  type Department,
  listDepartments,
  listDepartmentTree,
  updateDepartment,
} from "@/lib/organization";

import { ArchiveDepartmentDialog } from "./archive-department-dialog";
import { DepartmentDialog } from "./department-dialog";
import styles from "./organization.module.css";
import {
  DEPARTMENT_STATUS_LABELS,
  formatOrganizationDate,
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

const PAGE_LIMIT = 25;
const ROOT_PAGE_KEY = "__department_roots__";

type DepartmentView = "active" | "archived";

interface DepartmentPageState {
  items: Department[];
  nextCursor: string | null;
  isLoading: boolean;
  initialized: boolean;
  error: OrganizationErrorPresentation | null;
  failedRequest: { cursor: string | null; append: boolean } | null;
}

type DepartmentEditor =
  | { mode: "create"; parent: Department | null }
  | { mode: "rename"; department: Department; parent: Department | null };

interface DepartmentTreeLevelProps {
  departments: Department[];
  pages: Record<string, DepartmentPageState>;
  expandedIds: ReadonlySet<string>;
  departmentById: ReadonlyMap<string, Department>;
  canUpdate: boolean;
  moveSource: Department | null;
  isMoving: boolean;
  onToggle: (department: Department) => void;
  onLoadMore: (parentId: string, cursor: string) => void;
  onRetry: (parentId: string, page: DepartmentPageState) => void;
  onCreateChild: (parent: Department) => void;
  onRename: (department: Department) => void;
  onBeginMove: (department: Department) => void;
  onMoveTo: (parent: Department) => void;
  onArchive: (department: Department) => void;
}

function emptyDepartmentPage(isLoading = false): DepartmentPageState {
  return {
    items: [],
    nextCursor: null,
    isLoading,
    initialized: isLoading,
    error: null,
    failedRequest: null,
  };
}

function pageKey(parentId: string | null): string {
  return parentId ?? ROOT_PAGE_KEY;
}

function appendUniqueDepartments(
  current: Department[],
  incoming: Department[],
): Department[] {
  const byId = new Map(current.map((department) => [department.id, department]));
  for (const department of incoming) byId.set(department.id, department);
  return [...byId.values()];
}

function isKnownDescendant(
  candidate: Department,
  source: Department,
  departmentById: ReadonlyMap<string, Department>,
): boolean {
  const visited = new Set<string>();
  let parentId = candidate.parent_id;
  while (parentId && !visited.has(parentId)) {
    if (parentId === source.id) return true;
    visited.add(parentId);
    parentId = departmentById.get(parentId)?.parent_id ?? null;
  }
  return false;
}

function DepartmentTreeLevel({
  departments,
  pages,
  expandedIds,
  departmentById,
  canUpdate,
  moveSource,
  isMoving,
  onToggle,
  onLoadMore,
  onRetry,
  onCreateChild,
  onRename,
  onBeginMove,
  onMoveTo,
  onArchive,
}: DepartmentTreeLevelProps) {
  return departments.map((department) => {
    const isExpanded = expandedIds.has(department.id);
    const childPage = pages[pageKey(department.id)];
    const isMoveSource = moveSource?.id === department.id;
    const isCurrentParent = moveSource?.parent_id === department.id;
    const wouldCreateKnownCycle =
      moveSource !== null &&
      isKnownDescendant(department, moveSource, departmentById);
    const cannotReceiveMove =
      isMoveSource || isCurrentParent || wouldCreateKnownCycle;

    return (
      <li
        className={styles.departmentTreeItem}
        data-moving={isMoveSource || undefined}
        key={department.id}
      >
        <div className={styles.departmentNode}>
          {department.has_children ? (
            <button
              className={styles.treeToggle}
              type="button"
              onClick={() => onToggle(department)}
              aria-expanded={isExpanded}
              aria-label={
                isExpanded
                  ? `${department.name} alt departmanlarını gizle`
                  : `${department.name} alt departmanlarını göster`
              }
            >
              <span aria-hidden="true">{isExpanded ? "⌄" : "›"}</span>
            </button>
          ) : (
            <span className={styles.treeTogglePlaceholder} aria-hidden="true" />
          )}

          <div className={styles.departmentIdentity}>
            <strong>{department.name}</strong>
            <small>{department.code}</small>
          </div>

          <span className={styles.statusBadge} data-status={department.status}>
            <span aria-hidden="true" />
            {DEPARTMENT_STATUS_LABELS[department.status]}
          </span>

          {moveSource ? (
            <div className={styles.departmentNodeActions}>
              {isMoveSource ? (
                <span className={styles.moveSourceLabel}>Taşınacak departman</span>
              ) : (
                <button
                  className={styles.moveTargetButton}
                  type="button"
                  onClick={() => onMoveTo(department)}
                  disabled={cannotReceiveMove || isMoving}
                  title={
                    isCurrentParent
                      ? "Departman zaten bu üst departmana bağlı."
                      : wouldCreateKnownCycle
                        ? "Bir departman kendi altına taşınamaz."
                        : undefined
                  }
                  aria-label={`${moveSource.name} departmanını ${department.name} altına taşı`}
                >
                  Buraya taşı
                </button>
              )}
            </div>
          ) : canUpdate ? (
            <div className={styles.departmentNodeActions}>
              <button
                className={styles.inspectButton}
                type="button"
                onClick={() => onCreateChild(department)}
                aria-label={`${department.name} altında departman oluştur`}
              >
                Alt ekle
              </button>
              <button
                className={styles.inspectButton}
                type="button"
                onClick={() => onRename(department)}
                aria-label={`${department.name} departmanını yeniden adlandır`}
              >
                Adlandır
              </button>
              <button
                className={styles.inspectButton}
                type="button"
                onClick={() => onBeginMove(department)}
                aria-label={`${department.name} departmanını taşı`}
              >
                Taşı
              </button>
              <button
                className={styles.archiveButton}
                type="button"
                onClick={() => onArchive(department)}
                disabled={department.has_children}
                title={
                  department.has_children
                    ? "Önce etkin alt departmanları taşıyın veya arşivleyin."
                    : undefined
                }
                aria-label={`${department.name} departmanını arşivle`}
              >
                Arşivle
              </button>
            </div>
          ) : (
            <span className={styles.historyLabel}>Salt okunur</span>
          )}
        </div>

        {department.has_children && isExpanded ? (
          <div className={styles.departmentChildren}>
            {childPage?.isLoading && childPage.items.length === 0 ? (
              <div className={styles.treeInlineStatus} role="status">
                <span className={styles.spinner} aria-hidden="true" />
                Alt departmanlar yükleniyor…
              </div>
            ) : childPage?.error && childPage.items.length === 0 ? (
              <div className={styles.treeInlineError} role="alert">
                <span>{childPage.error.message}</span>
                <button
                  className={styles.compactButton}
                  type="button"
                  onClick={() => onRetry(department.id, childPage)}
                >
                  Yeniden dene
                </button>
              </div>
            ) : childPage?.initialized && childPage.items.length === 0 ? (
              <div className={styles.treeInlineStatus}>Etkin alt departman bulunamadı.</div>
            ) : childPage ? (
              <ul className={styles.departmentTreeGroup}>
                <DepartmentTreeLevel
                  departments={childPage.items}
                  pages={pages}
                  expandedIds={expandedIds}
                  departmentById={departmentById}
                  canUpdate={canUpdate}
                  moveSource={moveSource}
                  isMoving={isMoving}
                  onToggle={onToggle}
                  onLoadMore={onLoadMore}
                  onRetry={onRetry}
                  onCreateChild={onCreateChild}
                  onRename={onRename}
                  onBeginMove={onBeginMove}
                  onMoveTo={onMoveTo}
                  onArchive={onArchive}
                />
                {childPage.error ? (
                  <li className={styles.treePageAction}>
                    <div className={styles.treeInlineError} role="alert">
                      <span>{childPage.error.message}</span>
                      <button
                        className={styles.compactButton}
                        type="button"
                        onClick={() => onRetry(department.id, childPage)}
                      >
                        Yeniden dene
                      </button>
                    </div>
                  </li>
                ) : childPage.nextCursor ? (
                  <li className={styles.treePageAction}>
                    <button
                      className={styles.compactButton}
                      type="button"
                      onClick={() =>
                        onLoadMore(department.id, childPage.nextCursor as string)
                      }
                      disabled={childPage.isLoading}
                    >
                      {childPage.isLoading
                        ? "Yükleniyor…"
                        : "Bu düzeyde daha fazla göster"}
                    </button>
                  </li>
                ) : null}
              </ul>
            ) : null}
          </div>
        ) : null}
      </li>
    );
  });
}

export function DepartmentHierarchy({ canUpdate }: { canUpdate: boolean }) {
  const mountedRef = useRef(true);
  const treeGenerationRef = useRef(0);
  const noticeRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<DepartmentView>("active");
  const [pages, setPages] = useState<Record<string, DepartmentPageState>>(() => ({
    [ROOT_PAGE_KEY]: emptyDepartmentPage(true),
  }));
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<DepartmentEditor | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Department | null>(null);
  const [moveSource, setMoveSource] = useState<Department | null>(null);
  const [isMoving, setIsMoving] = useState(false);
  const [moveError, setMoveError] =
    useState<OrganizationErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeFocusRequest, setNoticeFocusRequest] = useState(0);

  const [history, setHistory] = useState<Department[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [historyCursorStack, setHistoryCursorStack] = useState<(string | null)[]>([]);
  const [historyNextCursor, setHistoryNextCursor] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] =
    useState<OrganizationErrorPresentation | null>(null);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (noticeFocusRequest === 0) return;
    const frame = window.requestAnimationFrame(() => noticeRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [noticeFocusRequest]);

  useEffect(() => {
    if (canUpdate) return;
    setEditor(null);
    setArchiveTarget(null);
    setMoveSource(null);
    setMoveError(null);
  }, [canUpdate]);

  const loadChildren = useCallback(
    async (
      parentId: string | null,
      cursor: string | null = null,
      append = false,
    ) => {
      const key = pageKey(parentId);
      const generation = treeGenerationRef.current;
      setPages((current) => {
        const existing = current[key] ?? emptyDepartmentPage();
        return {
          ...current,
          [key]: {
            ...existing,
            isLoading: true,
            initialized: true,
            error: null,
            failedRequest: null,
          },
        };
      });

      try {
        const page = await listDepartmentTree({
          limit: PAGE_LIMIT,
          parentId,
          cursor,
          includeArchived: false,
        });
        if (!mountedRef.current || generation !== treeGenerationRef.current) return;
        setPages((current) => {
          const existing = current[key] ?? emptyDepartmentPage();
          return {
            ...current,
            [key]: {
              items: append
                ? appendUniqueDepartments(existing.items, page.data)
                : page.data,
              nextCursor: page.meta.next_cursor,
              isLoading: false,
              initialized: true,
              error: null,
              failedRequest: null,
            },
          };
        });
      } catch (cause) {
        if (!mountedRef.current || generation !== treeGenerationRef.current) return;
        setPages((current) => {
          const existing = current[key] ?? emptyDepartmentPage();
          return {
            ...current,
            [key]: {
              ...existing,
              isLoading: false,
              initialized: true,
              error: organizationErrorPresentation(cause, "department_tree"),
              failedRequest: { cursor, append },
            },
          };
        });
      }
    },
    [],
  );

  useEffect(() => {
    void loadChildren(null);
  }, [loadChildren]);

  useEffect(() => {
    if (view !== "archived") return;
    let isActive = true;
    setIsLoadingHistory(true);
    setHistoryError(null);
    void listDepartments({
      status: "archived",
      limit: PAGE_LIMIT,
      cursor: historyCursor,
    }).then(
      (page) => {
        if (!isActive) return;
        setHistory(page.data);
        setHistoryNextCursor(page.meta.next_cursor);
        setIsLoadingHistory(false);
      },
      (cause) => {
        if (!isActive) return;
        setHistory([]);
        setHistoryNextCursor(null);
        setHistoryError(organizationErrorPresentation(cause, "department_history"));
        setIsLoadingHistory(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [historyCursor, historyReloadKey, view]);

  const rootPage = pages[ROOT_PAGE_KEY] ?? emptyDepartmentPage(true);
  const departmentById = useMemo(() => {
    const result = new Map<string, Department>();
    for (const page of Object.values(pages)) {
      for (const department of page.items) result.set(department.id, department);
    }
    return result;
  }, [pages]);

  function showNotice(message: string) {
    setNotice(message);
    setNoticeFocusRequest((request) => request + 1);
  }

  function resetAndReloadTree() {
    treeGenerationRef.current += 1;
    setExpandedIds(new Set());
    setPages({ [ROOT_PAGE_KEY]: emptyDepartmentPage(true) });
    void loadChildren(null);
  }

  function updateCachedDepartment(
    updatedDepartment: Department,
    hasChildrenOverride?: boolean,
  ) {
    setPages((current) =>
      Object.fromEntries(
        Object.entries(current).map(([key, page]) => [
          key,
          {
            ...page,
            items: page.items.map((department) =>
              department.id === updatedDepartment.id
                ? {
                    ...updatedDepartment,
                    // Tree pages scope this flag to active children. A resource response may
                    // also count archived historical children, which must not block archival.
                    // Callers may override it when they know the active-child state changed.
                    has_children: hasChildrenOverride ?? department.has_children,
                  }
                : department,
            ),
          },
        ]),
      ),
    );
  }

  function toggleDepartment(department: Department) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(department.id)) {
        next.delete(department.id);
      } else {
        next.add(department.id);
        if (!pages[pageKey(department.id)]?.initialized) {
          void loadChildren(department.id);
        }
      }
      return next;
    });
  }

  function retryPage(parentId: string | null, page: DepartmentPageState) {
    const failedRequest = page.failedRequest ?? { cursor: null, append: false };
    void loadChildren(parentId, failedRequest.cursor, failedRequest.append);
  }

  function handleDepartmentSaved(savedDepartment: Department, created: boolean) {
    const activeEditor = editor;
    setEditor(null);
    if (!created) {
      updateCachedDepartment(savedDepartment);
      showNotice("Departman adı güncellendi. Sabit kod ve hiyerarşi geçmişi korundu.");
      return;
    }

    const parent = activeEditor?.mode === "create" ? activeEditor.parent : null;
    showNotice(
      parent
        ? `${savedDepartment.name}, ${parent.name} altında oluşturuldu.`
        : `${savedDepartment.name} kök departman olarak oluşturuldu.`,
    );
    if (parent) {
      updateCachedDepartment(parent, true);
      setExpandedIds((current) => new Set(current).add(parent.id));
      void loadChildren(parent.id);
    } else {
      void loadChildren(null);
    }
  }

  async function moveSelectedDepartment(parent: Department | null) {
    if (!moveSource || isMoving) return;
    if (parent?.id === moveSource.id || parent?.id === moveSource.parent_id) return;

    setMoveError(null);
    setIsMoving(true);
    try {
      const movedDepartment = await updateDepartment(moveSource.id, {
        parent_id: parent?.id ?? null,
      });
      setMoveSource(null);
      showNotice(
        parent
          ? `${movedDepartment.name}, ${parent.name} altına taşındı.`
          : `${movedDepartment.name} kök düzeye taşındı.`,
      );
      resetAndReloadTree();
    } catch (cause) {
      setMoveError(organizationErrorPresentation(cause, "department_move"));
    } finally {
      setIsMoving(false);
    }
  }

  function handleDepartmentArchived(archivedDepartment: Department) {
    setArchiveTarget(null);
    showNotice(
      `${archivedDepartment.name} arşivlendi. Üst bağlantısı ve sabit kodu geçmiş için korundu.`,
    );
    setHistoryReloadKey((key) => key + 1);
    resetAndReloadTree();
  }

  function showNextHistoryPage() {
    if (!historyNextCursor || isLoadingHistory) return;
    setIsLoadingHistory(true);
    setHistoryError(null);
    setHistoryCursorStack((stack) => [...stack, historyCursor]);
    setHistoryCursor(historyNextCursor);
  }

  function showPreviousHistoryPage() {
    if (historyCursorStack.length === 0 || isLoadingHistory) return;
    setIsLoadingHistory(true);
    setHistoryError(null);
    setHistoryCursor(historyCursorStack[historyCursorStack.length - 1] ?? null);
    setHistoryCursorStack((stack) => stack.slice(0, -1));
  }

  return (
    <article className={styles.departmentCard} aria-labelledby="departments-title">
      <header className={styles.departmentHeader}>
        <div>
          <h2 id="departments-title">Departman hiyerarşisi</h2>
          <span>Her düzey yalnızca açıldığında ve en fazla {PAGE_LIMIT} kayıtla yüklenir.</span>
        </div>
        <div className={styles.departmentTools}>
          <div className={styles.viewTabs} role="group" aria-label="Departman görünümü">
            <button
              type="button"
              aria-pressed={view === "active"}
              onClick={() => setView("active")}
            >
              Aktif hiyerarşi
            </button>
            <button
              type="button"
              aria-pressed={view === "archived"}
              onClick={() => setView("archived")}
            >
              Arşiv geçmişi
            </button>
          </div>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={() => {
              setNotice(null);
              if (view === "active") {
                setMoveSource(null);
                setMoveError(null);
                resetAndReloadTree();
              } else {
                setIsLoadingHistory(true);
                setHistoryError(null);
                setHistoryReloadKey((key) => key + 1);
              }
            }}
            disabled={view === "active" ? rootPage.isLoading : isLoadingHistory}
          >
            Yenile
          </button>
          {canUpdate && view === "active" ? (
            <button
              className={styles.primaryButton}
              type="button"
              onClick={() => {
                setNotice(null);
                setEditor({ mode: "create", parent: null });
              }}
            >
              <span aria-hidden="true">＋</span>
              Yeni kök departman
            </button>
          ) : null}
        </div>
      </header>

      {notice ? (
        <div ref={noticeRef} className={styles.departmentNotice} role="status" tabIndex={-1}>
          <span aria-hidden="true">✓</span>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Bildirimi kapat">
            ×
          </button>
        </div>
      ) : null}

      {view === "active" ? (
        <div className={styles.departmentTreePanel}>
          {moveSource && canUpdate ? (
            <div className={styles.moveBanner} role="status">
              <div>
                <strong>{moveSource.name} için yeni üst departmanı seçin</strong>
                <span>
                  Dalları açmaya devam edebilir, bir satırdaki “Buraya taşı” seçeneğini
                  veya kök düzeyi kullanabilirsiniz.
                </span>
                {moveError ? (
                  <span className={styles.moveError} role="alert">
                    {moveError.message}
                    {moveError.reference ? ` Referans: ${moveError.reference}` : ""}
                  </span>
                ) : null}
              </div>
              <div>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={() => void moveSelectedDepartment(null)}
                  disabled={moveSource.parent_id === null || isMoving}
                >
                  {isMoving ? "Taşınıyor…" : "Kök düzeye taşı"}
                </button>
                <button
                  className={styles.compactButton}
                  type="button"
                  onClick={() => {
                    setMoveSource(null);
                    setMoveError(null);
                  }}
                  disabled={isMoving}
                >
                  Vazgeç
                </button>
              </div>
            </div>
          ) : null}

          {rootPage.isLoading && rootPage.items.length === 0 ? (
            <div className={styles.listLoading} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <strong>Departman kökleri yükleniyor</strong>
              <span>Alt düzeyler siz açana kadar yüklenmeyecek.</span>
            </div>
          ) : rootPage.error && rootPage.items.length === 0 ? (
            <div className={styles.listError} role="alert">
              <div>
                <strong>Departman hiyerarşisi yüklenemedi</strong>
                <span>{rootPage.error.message}</span>
                {rootPage.error.reference ? (
                  <small>Referans: {rootPage.error.reference}</small>
                ) : null}
              </div>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={() => retryPage(null, rootPage)}
              >
                Yeniden dene
              </button>
            </div>
          ) : rootPage.items.length === 0 ? (
            <div className={styles.emptyState}>
              <div aria-hidden="true">D</div>
              <h3>Henüz departman yok</h3>
              <p>
                İlk kök departmanı oluşturun; ekipleri daha sonra alt departmanlarla
                genişletin.
              </p>
              {canUpdate ? (
                <button
                  className={styles.primaryButton}
                  type="button"
                  onClick={() => setEditor({ mode: "create", parent: null })}
                >
                  Yeni kök departman
                </button>
              ) : null}
            </div>
          ) : (
            <>
              <ul
                className={styles.departmentTree}
                aria-label="Aktif departman hiyerarşisi"
              >
                <DepartmentTreeLevel
                  departments={rootPage.items}
                  pages={pages}
                  expandedIds={expandedIds}
                  departmentById={departmentById}
                  canUpdate={canUpdate}
                  moveSource={canUpdate ? moveSource : null}
                  isMoving={isMoving}
                  onToggle={toggleDepartment}
                  onLoadMore={(parentId, cursor) =>
                    void loadChildren(parentId, cursor, true)
                  }
                  onRetry={retryPage}
                  onCreateChild={(parent) => {
                    setNotice(null);
                    setEditor({ mode: "create", parent });
                  }}
                  onRename={(department) => {
                    setNotice(null);
                    setEditor({
                      mode: "rename",
                      department,
                      parent: department.parent_id
                        ? departmentById.get(department.parent_id) ?? null
                        : null,
                    });
                  }}
                  onBeginMove={(department) => {
                    setNotice(null);
                    setMoveError(null);
                    setMoveSource(department);
                  }}
                  onMoveTo={(parent) => void moveSelectedDepartment(parent)}
                  onArchive={setArchiveTarget}
                />
                {rootPage.error ? (
                  <li className={styles.treePageAction}>
                    <div className={styles.treeInlineError} role="alert">
                      <span>{rootPage.error.message}</span>
                      <button
                        className={styles.compactButton}
                        type="button"
                        onClick={() => retryPage(null, rootPage)}
                      >
                        Yeniden dene
                      </button>
                    </div>
                  </li>
                ) : rootPage.nextCursor ? (
                  <li className={styles.treePageAction}>
                    <button
                      className={styles.compactButton}
                      type="button"
                      onClick={() =>
                        void loadChildren(null, rootPage.nextCursor, true)
                      }
                      disabled={rootPage.isLoading}
                    >
                      {rootPage.isLoading
                        ? "Yükleniyor…"
                        : "Daha fazla kök departman göster"}
                    </button>
                  </li>
                ) : null}
              </ul>
              <div className={styles.departmentSemantics}>
                <strong>Aktif yapı</strong>
                <span>
                  Yeni alt departmanlar ve çalışan atamaları yalnızca aktif departmanlara
                  bağlanabilir. Taşımalar sunucuda yeniden doğrulanır; döngü oluşturan bir
                  değişiklik kaydedilmez.
                </span>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className={styles.departmentHistoryPanel}>
          {historyError ? (
            <div className={styles.listError} role="alert">
              <div>
                <strong>Departman geçmişi yüklenemedi</strong>
                <span>{historyError.message}</span>
                {historyError.reference ? (
                  <small>Referans: {historyError.reference}</small>
                ) : null}
              </div>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={() => setHistoryReloadKey((key) => key + 1)}
              >
                Yeniden dene
              </button>
            </div>
          ) : isLoadingHistory && history.length === 0 ? (
            <div className={styles.listLoading} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <strong>Departman geçmişi yükleniyor</strong>
            </div>
          ) : history.length === 0 ? (
            <div className={styles.emptyState}>
              <div aria-hidden="true">D</div>
              <h3>Arşivlenmiş departman yok</h3>
              <p>Arşivlenen departmanlar sabit kodları ve üst bağlantılarıyla burada görünür.</p>
            </div>
          ) : (
            <>
              <ul className={styles.departmentHistoryList} aria-label="Arşivlenmiş departmanlar">
                {history.map((department) => (
                  <li key={department.id} data-department-status={department.status}>
                    <div className={styles.departmentIdentity}>
                      <strong>{department.name}</strong>
                      <small>{department.code}</small>
                    </div>
                    <span className={styles.statusBadge} data-status={department.status}>
                      <span aria-hidden="true" />
                      {DEPARTMENT_STATUS_LABELS[department.status]}
                    </span>
                    <div className={styles.historySemantics}>
                      <strong>
                        {department.parent_id
                          ? "Geçmiş üst bağlantısı korunuyor"
                          : "Kök departman olarak arşivlendi"}
                      </strong>
                      <span>{formatOrganizationDate(department.archived_at)}</span>
                    </div>
                    <span
                      className={styles.assignmentBadge}
                      data-accepts-assignments={department.accepts_new_assignments}
                    >
                      Yeni atamaya kapalı
                    </span>
                  </li>
                ))}
              </ul>
              <footer className={styles.pagination}>
                <span>Arşiv sayfası {historyCursorStack.length + 1}</span>
                <div>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={showPreviousHistoryPage}
                    disabled={isLoadingHistory || historyCursorStack.length === 0}
                  >
                    Önceki
                  </button>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={showNextHistoryPage}
                    disabled={isLoadingHistory || !historyNextCursor}
                  >
                    Sonraki
                  </button>
                </div>
              </footer>
              <div className={styles.departmentSemantics}>
                <strong>Terminal arşiv</strong>
                <span>
                  Arşivlenen departman yeniden etkinleştirilmez, yeni alt departman veya
                  çalışan ataması alamaz. Sabit kod ve son üst bağlantısı geçmiş kayıtları
                  için saklanır.
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {editor && canUpdate ? (
        <DepartmentDialog
          key={
            editor.mode === "rename"
              ? `rename-${editor.department.id}`
              : `create-${editor.parent?.id ?? "root"}`
          }
          department={editor.mode === "rename" ? editor.department : null}
          parent={editor.parent}
          onClose={() => setEditor(null)}
          onSaved={handleDepartmentSaved}
        />
      ) : null}

      {archiveTarget && canUpdate ? (
        <ArchiveDepartmentDialog
          department={archiveTarget}
          onClose={() => setArchiveTarget(null)}
          onArchived={handleDepartmentArchived}
        />
      ) : null}
    </article>
  );
}
