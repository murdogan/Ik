"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  listOrganizationChart,
  type OrganizationChartEmployeeStatus,
  type OrganizationChartNode,
  type OrganizationChartReference,
  type OrganizationChartUserStatus,
} from "@/lib/organization";

import styles from "./organization.module.css";
import {
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

const PAGE_LIMIT = 25;
const ROOT_PAGE_KEY = "__organization_chart_roots__";

interface OrganizationChartPageState {
  items: OrganizationChartNode[];
  nextCursor: string | null;
  isLoading: boolean;
  initialized: boolean;
  error: OrganizationErrorPresentation | null;
  failedRequest: { cursor: string | null; append: boolean } | null;
}

interface OrganizationChartLevelProps {
  nodes: OrganizationChartNode[];
  pages: Record<string, OrganizationChartPageState>;
  expandedIds: ReadonlySet<string>;
  onToggle: (node: OrganizationChartNode) => void;
  onLoadMore: (parentId: string, cursor: string) => void;
  onRetry: (
    parentId: string | null,
    page: OrganizationChartPageState,
  ) => void;
}

const EMPLOYEE_STATUS_LABELS: Record<OrganizationChartEmployeeStatus, string> = {
  active: "Aktif çalışan",
  on_leave: "İzinli",
  terminated: "İşten ayrıldı",
};

const USER_STATUS_LABELS: Record<OrganizationChartUserStatus, string> = {
  invited: "Davet edildi",
  active: "Aktif kullanıcı",
  locked: "Kilitli kullanıcı",
  disabled: "Devre dışı kullanıcı",
};

function emptyPage(isLoading = false): OrganizationChartPageState {
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

function appendUniqueNodes(
  current: OrganizationChartNode[],
  incoming: OrganizationChartNode[],
): OrganizationChartNode[] {
  const byKey = new Map(current.map((node) => [nodeKey(node), node]));
  for (const node of incoming) byKey.set(nodeKey(node), node);
  return [...byKey.values()];
}

function nodeKey(node: OrganizationChartNode): string {
  return `${node.node_type}:${node.id}`;
}

function initial(value: string): string {
  return value.trim().charAt(0).toLocaleUpperCase("tr-TR") || "O";
}

function personStatus(node: OrganizationChartNode): {
  label: string;
  value: OrganizationChartEmployeeStatus | OrganizationChartUserStatus;
} | null {
  if (node.employee_status) {
    return {
      label: EMPLOYEE_STATUS_LABELS[node.employee_status],
      value: node.employee_status,
    };
  }
  if (node.user_status) {
    return {
      label: USER_STATUS_LABELS[node.user_status],
      value: node.user_status,
    };
  }
  return null;
}

function positionLabel(node: OrganizationChartNode): string {
  if (!node.position) {
    return node.node_type === "manager"
      ? "Ataması olmayan yönetici"
      : "Pozisyon ataması yok";
  }
  return node.position.status === "archived"
    ? `${node.position.title} · Arşiv`
    : node.position.title;
}

function referenceLabel(reference: OrganizationChartReference | null): string {
  if (!reference) return "—";
  if (reference.status === "archived") return `${reference.name} · Arşiv`;
  if (reference.status === "inactive") return `${reference.name} · Pasif`;
  return reference.name;
}

function OrganizationChartLevel({
  nodes,
  pages,
  expandedIds,
  onToggle,
  onLoadMore,
  onRetry,
}: OrganizationChartLevelProps) {
  return nodes.map((node) => {
    const canExpand = node.has_children && node.user_id !== null;
    const key = nodeKey(node);
    const isExpanded = expandedIds.has(key);
    const childPage = node.user_id ? pages[pageKey(node.user_id)] : undefined;
    const status = personStatus(node);

    return (
      <li
        className={styles.organizationChartItem}
        data-node-type={node.node_type}
        data-archived-reference={node.has_archived_reference || undefined}
        key={key}
      >
        <div className={styles.organizationChartNode}>
          {canExpand ? (
            <button
              className={styles.chartToggle}
              type="button"
              onClick={() => onToggle(node)}
              aria-expanded={isExpanded}
              aria-label={
                isExpanded
                  ? `${node.full_name} doğrudan ekibini gizle`
                  : `${node.full_name} doğrudan ekibini göster`
              }
            >
              <span aria-hidden="true">{isExpanded ? "⌄" : "›"}</span>
            </button>
          ) : (
            <span className={styles.chartTogglePlaceholder} aria-hidden="true" />
          )}

          <span className={styles.organizationChartAvatar} aria-hidden="true">
            {initial(node.full_name)}
          </span>

          <div className={styles.organizationChartIdentity}>
            <strong>{node.full_name}</strong>
            <span>{positionLabel(node)}</span>
            <small>
              {node.employee_number ?? node.email ?? "Yönetici kullanıcı kaydı"}
            </small>
          </div>

          <div className={styles.organizationChartStructure}>
            <span>
              <small>Departman</small>
              <strong>{referenceLabel(node.department)}</strong>
            </span>
            <span>
              <small>Şube</small>
              <strong>{referenceLabel(node.branch)}</strong>
            </span>
            <span>
              <small>Tüzel kişilik</small>
              <strong>{referenceLabel(node.legal_entity)}</strong>
            </span>
          </div>

          <div className={styles.organizationChartBadges}>
            {status ? (
              <span className={styles.statusBadge} data-status={status.value}>
                <span aria-hidden="true" />
                {status.label}
              </span>
            ) : null}
            {node.node_type === "manager" && node.assignment_id === null ? (
              <span className={styles.chartManagerBadge}>Yönetici kökü</span>
            ) : null}
            {node.has_archived_reference ? (
              <span className={styles.chartArchiveBadge}>Arşiv referansı</span>
            ) : null}
          </div>
        </div>

        {canExpand && isExpanded ? (
          <div className={styles.organizationChartChildren}>
            {childPage?.isLoading && childPage.items.length === 0 ? (
              <div className={styles.chartInlineStatus} role="status">
                <span className={styles.spinner} aria-hidden="true" />
                Doğrudan ekip yükleniyor…
              </div>
            ) : childPage?.error && childPage.items.length === 0 ? (
              <div className={styles.chartInlineError} role="alert">
                <div>
                  <strong>Doğrudan ekip yüklenemedi</strong>
                  <span>{childPage.error.message}</span>
                  {childPage.error.reference ? (
                    <small>Referans: {childPage.error.reference}</small>
                  ) : null}
                </div>
                <button
                  className={styles.compactButton}
                  type="button"
                  onClick={() => onRetry(node.user_id, childPage)}
                >
                  Yeniden dene
                </button>
              </div>
            ) : childPage?.initialized && childPage.items.length === 0 ? (
              <div className={styles.chartInlineStatus} role="status">
                Güncel doğrudan raporlama kaydı bulunamadı.
              </div>
            ) : childPage ? (
              <ul className={styles.organizationChartGroup}>
                <OrganizationChartLevel
                  nodes={childPage.items}
                  pages={pages}
                  expandedIds={expandedIds}
                  onToggle={onToggle}
                  onLoadMore={onLoadMore}
                  onRetry={onRetry}
                />
                {childPage.error ? (
                  <li className={styles.chartPageAction}>
                    <div className={styles.chartInlineError} role="alert">
                      <div>
                        <strong>Daha fazla ekip üyesi yüklenemedi</strong>
                        <span>{childPage.error.message}</span>
                      </div>
                      <button
                        className={styles.compactButton}
                        type="button"
                        onClick={() => onRetry(node.user_id, childPage)}
                      >
                        Yeniden dene
                      </button>
                    </div>
                  </li>
                ) : childPage.nextCursor ? (
                  <li className={styles.chartPageAction}>
                    <button
                      className={styles.compactButton}
                      type="button"
                      onClick={() =>
                        onLoadMore(
                          node.user_id as string,
                          childPage.nextCursor as string,
                        )
                      }
                      disabled={childPage.isLoading}
                    >
                      {childPage.isLoading
                        ? "Ekip yükleniyor…"
                        : "Bu yöneticinin daha fazla ekip üyesini göster"}
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

export function OrganizationChart() {
  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const inFlightRequestsRef = useRef<Set<string>>(new Set());
  const [pages, setPages] = useState<Record<string, OrganizationChartPageState>>(
    () => ({ [ROOT_PAGE_KEY]: emptyPage(true) }),
  );
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadPage = useCallback(
    async (
      parentId: string | null,
      cursor: string | null = null,
      append = false,
    ) => {
      const key = pageKey(parentId);
      const generation = generationRef.current;
      const requestKey = `${generation}:${key}`;
      if (inFlightRequestsRef.current.has(requestKey)) return;
      inFlightRequestsRef.current.add(requestKey);
      setPages((current) => {
        const existing = current[key] ?? emptyPage();
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
        const page = await listOrganizationChart({
          limit: PAGE_LIMIT,
          parentId,
          cursor,
        });
        if (!mountedRef.current || generation !== generationRef.current) return;
        setPages((current) => {
          const existing = current[key] ?? emptyPage();
          return {
            ...current,
            [key]: {
              items: append
                ? appendUniqueNodes(existing.items, page.data)
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
        if (!mountedRef.current || generation !== generationRef.current) return;
        setPages((current) => {
          const existing = current[key] ?? emptyPage();
          return {
            ...current,
            [key]: {
              ...existing,
              isLoading: false,
              initialized: true,
              error: organizationErrorPresentation(cause, "org_chart_read"),
              failedRequest: { cursor, append },
            },
          };
        });
      } finally {
        inFlightRequestsRef.current.delete(requestKey);
      }
    },
    [],
  );

  useEffect(() => {
    void loadPage(null);
  }, [loadPage]);

  const rootPage = pages[ROOT_PAGE_KEY] ?? emptyPage(true);
  const isLoading = useMemo(
    () => Object.values(pages).some((page) => page.isLoading),
    [pages],
  );

  function toggleNode(node: OrganizationChartNode) {
    if (!node.user_id || !node.has_children) return;
    const key = nodeKey(node);
    const shouldExpand = !expandedIds.has(key);
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
    if (shouldExpand && !pages[pageKey(node.user_id)]?.initialized) {
      void loadPage(node.user_id);
    }
  }

  function retryPage(
    parentId: string | null,
    page: OrganizationChartPageState,
  ) {
    const failedRequest = page.failedRequest ?? {
      cursor: null,
      append: false,
    };
    void loadPage(parentId, failedRequest.cursor, failedRequest.append);
  }

  function refreshChart() {
    generationRef.current += 1;
    setExpandedIds(new Set());
    setPages({ [ROOT_PAGE_KEY]: emptyPage(true) });
    void loadPage(null);
  }

  return (
    <article
      id="organization-chart"
      className={styles.organizationChartCard}
      aria-labelledby="organization-chart-title"
      aria-busy={isLoading}
    >
      <header className={styles.departmentHeader}>
        <div>
          <h2 id="organization-chart-title">Organizasyon şeması</h2>
          <span>
            Yalnızca açtığınız yönetici düzeyi ve her istekte en fazla {PAGE_LIMIT}
            kayıt yüklenir.
          </span>
        </div>
        <button
          className={styles.refreshButton}
          type="button"
          onClick={refreshChart}
          disabled={isLoading}
        >
          Şemayı yenile
        </button>
      </header>

      <div className={styles.organizationChartPanel}>
        {rootPage.isLoading && rootPage.items.length === 0 ? (
          <div className={styles.listLoading} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Organizasyon kökleri yükleniyor</strong>
            <span>Alt ekipler siz açana kadar indirilmez.</span>
          </div>
        ) : rootPage.error && rootPage.items.length === 0 ? (
          <div className={styles.listError} role="alert">
            <div>
              <strong>Organizasyon şeması yüklenemedi</strong>
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
            <div aria-hidden="true">Ş</div>
            <h3>Organizasyon şeması henüz oluşmadı</h3>
            <p>
              Güncel çalışan atamaları ve raporlama yöneticileri tanımlandığında
              kök ekipler burada görünür.
            </p>
          </div>
        ) : (
          <>
            <ul
              className={styles.organizationChartTree}
              aria-label="Güncel çalışan raporlama hiyerarşisi"
            >
              <OrganizationChartLevel
                nodes={rootPage.items}
                pages={pages}
                expandedIds={expandedIds}
                onToggle={toggleNode}
                onLoadMore={(parentId, cursor) =>
                  void loadPage(parentId, cursor, true)
                }
                onRetry={retryPage}
              />
              {rootPage.error ? (
                <li className={styles.chartPageAction}>
                  <div className={styles.chartInlineError} role="alert">
                    <div>
                      <strong>Daha fazla organizasyon kökü yüklenemedi</strong>
                      <span>{rootPage.error.message}</span>
                    </div>
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
                <li className={styles.chartPageAction}>
                  <button
                    className={styles.compactButton}
                    type="button"
                    onClick={() =>
                      void loadPage(null, rootPage.nextCursor, true)
                    }
                    disabled={rootPage.isLoading}
                  >
                    {rootPage.isLoading
                      ? "Kökler yükleniyor…"
                      : "Daha fazla organizasyon kökü göster"}
                  </button>
                </li>
              ) : null}
            </ul>
            <div className={styles.organizationChartSemantics}>
              <strong>Güncel raporlama hattı</strong>
              <span>
                Şema güncel yapısal atamalardan üretilir. “Arşiv referansı” etiketi,
                çalışanın korunan geçmiş bir organizasyon kaydına bağlı olduğunu
                gösterir; yeni atama yapılabildiği anlamına gelmez.
              </span>
            </div>
          </>
        )}
      </div>
    </article>
  );
}
