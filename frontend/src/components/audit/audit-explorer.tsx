"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  type AuditEvent,
  type AuditScope,
  listPlatformAuditEvents,
  listTenantAuditEvents,
  readTenantAuditEvent,
} from "@/lib/audit-events";

import { AuditDetailDialog } from "./audit-detail-dialog";
import styles from "./audit.module.css";
import {
  type AuditErrorPresentation,
  auditActorLabel,
  auditCategoryLabel,
  auditErrorPresentation,
  auditEventLabel,
  auditResultLabel,
  formatAuditDate,
  humanizeIdentifier,
  shortIdentifier,
} from "./audit-presentation";

const PAGE_LIMIT = 25;

interface AuditFilters {
  category: string;
  eventType: string;
  result: string;
}

const EMPTY_FILTERS: AuditFilters = { category: "", eventType: "", result: "" };

function resourceLabel(event: AuditEvent): string {
  if (!event.resource_type) {
    return "—";
  }
  const identifier = shortIdentifier(event.resource_id);
  return identifier === "—"
    ? humanizeIdentifier(event.resource_type)
    : `${humanizeIdentifier(event.resource_type)} · ${identifier}`;
}

export function AuditExplorer({ scope }: { scope: AuditScope }) {
  const { user } = useSession();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS);
  const [draftCategory, setDraftCategory] = useState("");
  const [draftEventType, setDraftEventType] = useState("");
  const [draftResult, setDraftResult] = useState("");
  const [currentCursor, setCurrentCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<AuditErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [detailEvent, setDetailEvent] = useState<AuditEvent | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<AuditErrorPresentation | null>(null);

  const selectedListEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? null,
    [events, selectedEventId],
  );
  const selectedEvent = detailEvent ?? selectedListEvent;

  useEffect(() => {
    let isActive = true;
    const listEvents =
      scope === "tenant" ? listTenantAuditEvents : listPlatformAuditEvents;

    void listEvents({
      category: filters.category,
      eventType: filters.eventType,
      result: filters.result,
      limit: PAGE_LIMIT,
      cursor: currentCursor,
    }).then(
      (page) => {
        if (!isActive) {
          return;
        }
        setEvents(page.data);
        setNextCursor(page.meta.next_cursor);
        setError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) {
          return;
        }
        setEvents([]);
        setNextCursor(null);
        setError(auditErrorPresentation(cause, "list"));
        setIsLoading(false);
      },
    );

    return () => {
      isActive = false;
    };
  }, [currentCursor, filters, reloadKey, scope]);

  useEffect(() => {
    if (scope !== "tenant" || !selectedEventId) {
      return;
    }

    let isActive = true;
    void readTenantAuditEvent(selectedEventId).then(
      (event) => {
        if (!isActive) {
          return;
        }
        setDetailEvent(event);
        setIsLoadingDetail(false);
      },
      (cause) => {
        if (!isActive) {
          return;
        }
        setDetailError(auditErrorPresentation(cause, "detail"));
        setIsLoadingDetail(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [scope, selectedEventId]);

  function resetPageState() {
    setIsLoading(true);
    setError(null);
    setCurrentCursor(null);
    setCursorHistory([]);
    closeDetail();
  }

  function applyFilters(formEvent: FormEvent<HTMLFormElement>) {
    formEvent.preventDefault();
    resetPageState();
    setFilters({
      category: draftCategory.trim(),
      eventType: draftEventType.trim(),
      result: draftResult,
    });
    setReloadKey((key) => key + 1);
  }

  function clearFilters() {
    resetPageState();
    setDraftCategory("");
    setDraftEventType("");
    setDraftResult("");
    setFilters(EMPTY_FILTERS);
    setReloadKey((key) => key + 1);
  }

  function showNextPage() {
    if (!nextCursor || isLoading) {
      return;
    }
    setIsLoading(true);
    setError(null);
    setCursorHistory((history) => [...history, currentCursor]);
    setCurrentCursor(nextCursor);
    closeDetail();
  }

  function showPreviousPage() {
    if (cursorHistory.length === 0 || isLoading) {
      return;
    }
    setIsLoading(true);
    setError(null);
    const previousCursor = cursorHistory[cursorHistory.length - 1] ?? null;
    setCursorHistory((history) => history.slice(0, -1));
    setCurrentCursor(previousCursor);
    closeDetail();
  }

  function inspectEvent(event: AuditEvent) {
    setDetailEvent(scope === "platform" ? event : null);
    setDetailError(null);
    setIsLoadingDetail(scope === "tenant");
    setSelectedEventId(event.id);
  }

  function closeDetail() {
    setSelectedEventId(null);
    setDetailEvent(null);
    setDetailError(null);
    setIsLoadingDetail(false);
  }

  const isTenant = scope === "tenant";
  const hasFilters = Boolean(filters.category || filters.eventType || filters.result);

  return (
    <section
      className={`${styles.page} ${isTenant ? styles.tenantTheme : styles.platformTheme}`}
      aria-labelledby="audit-title"
      data-audit-scope={scope}
    >
      <header className={styles.pageHeader}>
        <div>
          <span>{isTenant ? "Tenant güvenliği" : "Platform operasyonları"}</span>
          <h1 id="audit-title">
            {isTenant ? "Denetim kayıtları" : "Platform denetim kayıtları"}
          </h1>
          <p>
            {isTenant
              ? `${user.tenant.name} çalışma alanındaki izinli giriş, davet, rol ve oturum olaylarını inceleyin.`
              : "Yalnız platform operasyonlarını ve güvenlik olaylarını inceleyin; müşteri HR verileri bu görünümde yer almaz."}
          </p>
        </div>
      </header>

      <aside className={styles.safetyNotice} aria-label="Denetim kaydı güvenliği">
        <span aria-hidden="true">✓</span>
        <div>
          <strong>Salt okunur ve hassas veriden arındırılmış</strong>
          <p>
            Bu kayıtlar bu ekrandan değiştirilemez veya silinemez. Parola, token, cookie,
            hash ve hassas HR içerikleri metadata içinde saklanmaz.
          </p>
        </div>
      </aside>

      <form className={styles.filterBar} role="search" onSubmit={applyFilters}>
        <div className={styles.filterField}>
          <label htmlFor={`${scope}_audit_category`}>Kategori</label>
          <input
            id={`${scope}_audit_category`}
            value={draftCategory}
            onChange={(event) => setDraftCategory(event.target.value)}
            placeholder={isTenant ? "Örn. tenant_security" : "Örn. platform_operations"}
            maxLength={80}
          />
        </div>
        <div className={styles.filterField}>
          <label htmlFor={`${scope}_audit_event_type`}>Olay türü</label>
          <input
            id={`${scope}_audit_event_type`}
            value={draftEventType}
            onChange={(event) => setDraftEventType(event.target.value)}
            placeholder="Örn. auth.login.succeeded"
            maxLength={160}
          />
        </div>
        <div className={styles.filterField}>
          <label htmlFor={`${scope}_audit_result`}>Sonuç</label>
          <select
            id={`${scope}_audit_result`}
            value={draftResult}
            onChange={(event) => setDraftResult(event.target.value)}
          >
            <option value="">Tüm sonuçlar</option>
            <option value="success">Başarılı</option>
            <option value="failure">Başarısız</option>
            <option value="denied">Reddedildi</option>
          </select>
        </div>
        <button className={styles.filterButton} type="submit" disabled={isLoading}>
          Filtrele
        </button>
        {(hasFilters || draftCategory || draftEventType || draftResult) && (
          <button className={styles.clearButton} type="button" onClick={clearFilters}>
            Temizle
          </button>
        )}
      </form>

      <div className={styles.listCard} aria-busy={isLoading}>
        <div className={styles.listHeader}>
          <div>
            <h2>{isTenant ? "Tenant olayları" : "Platform olayları"}</h2>
            <span>
              {isLoading
                ? "Kayıtlar güncelleniyor…"
                : `${events.length} olay bu sayfada gösteriliyor`}
            </span>
          </div>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={() => {
              setIsLoading(true);
              setError(null);
              closeDetail();
              setReloadKey((key) => key + 1);
            }}
            disabled={isLoading}
          >
            Yenile
          </button>
        </div>

        {error ? (
          <div className={styles.listError} role="alert">
            <div>
              <strong>Denetim kayıtları yüklenemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={() => {
                setIsLoading(true);
                setError(null);
                setReloadKey((key) => key + 1);
              }}
            >
              Yeniden dene
            </button>
          </div>
        ) : isLoading && events.length === 0 ? (
          <div className={styles.listLoading} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Denetim kayıtları yükleniyor</strong>
            <span>İzinli ve redakte edilmiş olaylar hazırlanıyor…</span>
          </div>
        ) : events.length === 0 ? (
          <div className={styles.emptyState}>
            <div aria-hidden="true">D</div>
            <h3>{hasFilters ? "Eşleşen olay bulunamadı" : "Henüz denetim kaydı yok"}</h3>
            <p>
              {hasFilters
                ? "Kategori, olay türü veya sonuç filtresini değiştirin."
                : "İzinli güvenlik ve yönetim olayları oluştukça burada görünecek."}
            </p>
            {hasFilters ? (
              <button className={styles.secondaryButton} type="button" onClick={clearFilters}>
                Filtreleri temizle
              </button>
            ) : null}
          </div>
        ) : (
          <div className={styles.tableScroller}>
            <table className={styles.auditTable}>
              <thead>
                <tr>
                  <th scope="col">Zaman</th>
                  <th scope="col">Olay</th>
                  <th scope="col">Aktör</th>
                  <th scope="col">Kaynak</th>
                  <th scope="col">Sonuç</th>
                  <th scope="col">
                    <span className={styles.visuallyHidden}>İşlemler</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td data-label="Zaman">
                      <time dateTime={event.occurred_at}>{formatAuditDate(event.occurred_at)}</time>
                    </td>
                    <td data-label="Olay">
                      <div className={styles.eventIdentity}>
                        <strong>{auditEventLabel(event.event_type)}</strong>
                        <span>{auditCategoryLabel(event.category)}</span>
                        <small>{event.event_type}</small>
                      </div>
                    </td>
                    <td data-label="Aktör">
                      <div className={styles.actorIdentity}>
                        <span>{auditActorLabel(event.actor_type)}</span>
                        {event.actor_user_id ? (
                          <small>{shortIdentifier(event.actor_user_id)}</small>
                        ) : null}
                      </div>
                    </td>
                    <td data-label="Kaynak">{resourceLabel(event)}</td>
                    <td data-label="Sonuç">
                      <span className={styles.resultBadge} data-result={event.result}>
                        {auditResultLabel(event.result)}
                      </span>
                    </td>
                    <td className={styles.actionCell}>
                      <button
                        className={styles.inspectButton}
                        type="button"
                        onClick={() => inspectEvent(event)}
                        aria-label={`${auditEventLabel(event.event_type)} olayını incele`}
                      >
                        İncele
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!error && (events.length > 0 || cursorHistory.length > 0) ? (
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

      {selectedEvent ? (
        <AuditDetailDialog
          key={`${scope}-${selectedEvent.id}`}
          event={selectedEvent}
          scope={scope}
          isLoading={isLoadingDetail}
          error={detailError}
          onClose={closeDetail}
        />
      ) : null}
    </section>
  );
}
