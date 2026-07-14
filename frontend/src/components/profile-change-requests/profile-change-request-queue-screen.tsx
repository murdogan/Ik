"use client";

import Link from "next/link";
import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  listHrProfileChangeRequests,
  type HrProfileChangeRequestSummary,
  type ProfileChangeField,
  type ProfileChangeRequestStatus,
} from "@/lib/employee-profile-change-requests";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./profile-change-requests.module.css";

const PAGE_LIMIT = 25;
const STATUS_LABELS: Record<ProfileChangeRequestStatus, string> = {
  submitted: "Değerlendirmede",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
};

const FIELD_LABELS: Record<ProfileChangeField, string> = {
  preferred_name: "Tercih edilen ad",
  phone: "Telefon",
  birth_date: "Doğum tarihi",
};

interface QueueBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  readGranted: boolean;
  updateGranted: boolean;
  status: ProfileChangeRequestStatus;
  cursor: string | null;
}

interface QueueError {
  message: string;
  reference: string | null;
}

interface QueueState {
  boundary: QueueBoundary;
  requests: HrProfileChangeRequestSummary[];
  nextCursor: string | null;
  error: QueueError | null;
  isLoading: boolean;
}

function isCurrentBoundary(expected: QueueBoundary, current: QueueBoundary): boolean {
  return (
    isSessionGenerationCurrent(expected.sessionGeneration) &&
    expected.sessionGeneration === current.sessionGeneration &&
    expected.userId === current.userId &&
    expected.membershipId === current.membershipId &&
    expected.tenantId === current.tenantId &&
    expected.permissionVersion === current.permissionVersion &&
    expected.readGranted === current.readGranted &&
    expected.updateGranted === current.updateGranted &&
    expected.status === current.status &&
    expected.cursor === current.cursor
  );
}

function queueError(cause: unknown): QueueError {
  let message = "Değişiklik talebi kuyruğu şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  if (!(cause instanceof ApiClientError)) return { message, reference };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Değişiklik taleplerini değerlendirmek için gerekli İK yetkileriniz bulunmuyor.";
  } else if (cause.status === 422) {
    message = "Kuyruk filtresi veya sayfa bağlantısı geçerli değil. Filtreleri temizleyin.";
  } else if (cause.code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir kuyruk yanıtı alındı. Lütfen yeniden yükleyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference };
}

function employeeName(request: HrProfileChangeRequestSummary): string {
  return `${request.employee.first_name} ${request.employee.last_name}`.trim();
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function ProfileChangeRequestQueueScreen() {
  const { user, sessionGeneration } = useSession();
  const canRead = hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantEmployees);
  const canUpdate = hasPermission(user, AUTHORIZATION_PERMISSIONS.updateEmployees);
  const [status, setStatus] = useState<ProfileChangeRequestStatus>("submitted");
  const [draftStatus, setDraftStatus] = useState<ProfileChangeRequestStatus>("submitted");
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const boundary = useMemo<QueueBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      readGranted: canRead,
      updateGranted: canUpdate,
      status,
      cursor,
    }),
    [
      canRead,
      canUpdate,
      cursor,
      sessionGeneration,
      status,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const latestBoundary = useRef(boundary);
  const requestGeneration = useRef(0);
  const [state, setState] = useState<QueueState>(() => ({
    boundary,
    requests: [],
    nextCursor: null,
    error: null,
    isLoading: true,
  }));

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary]);

  useEffect(() => {
    if (!boundary.readGranted || !boundary.updateGranted) return;
    const requestId = ++requestGeneration.current;
    const requestBoundary = boundary;
    void listHrProfileChangeRequests({
      status: requestBoundary.status,
      limit: PAGE_LIMIT,
      cursor: requestBoundary.cursor,
    }).then(
      (page) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          requests: page.data,
          nextCursor: page.meta.next_cursor,
          error: null,
          isLoading: false,
        });
      },
      (cause) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          requests: [],
          nextCursor: null,
          error: queueError(cause),
          isLoading: false,
        });
      },
    );
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const requests = stateIsCurrent ? state.requests : [];
  const nextCursor = stateIsCurrent ? state.nextCursor : null;
  const error = stateIsCurrent ? state.error : null;
  const isLoading = !stateIsCurrent || state.isLoading;

  function resetPagination() {
    setCursor(null);
    setCursorHistory([]);
  }

  function reloadQueue() {
    setState({
      boundary,
      requests: [],
      nextCursor: null,
      error: null,
      isLoading: true,
    });
    setReloadKey((key) => key + 1);
  }

  function applyFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({
      boundary,
      requests: [],
      nextCursor: null,
      error: null,
      isLoading: true,
    });
    resetPagination();
    setStatus(draftStatus);
    setReloadKey((key) => key + 1);
  }

  function showNextPage() {
    if (!nextCursor || isLoading) return;
    setCursorHistory((history) => [...history, cursor]);
    setCursor(nextCursor);
  }

  function showPreviousPage() {
    if (cursorHistory.length === 0 || isLoading) return;
    const previousCursor = cursorHistory[cursorHistory.length - 1] ?? null;
    setCursorHistory((history) => history.slice(0, -1));
    setCursor(previousCursor);
  }

  if (!boundary.readGranted || !boundary.updateGranted) return null;

  return (
    <section className={styles.queuePage} aria-labelledby="profile-change-queue-title">
      <header className={styles.pageHeader}>
        <div>
          <span>İK karar alanı</span>
          <h1 id="profile-change-queue-title">Değişiklik talepleri</h1>
          <p>
            Çalışanların izin verilen kişisel alan taleplerini güvenli karşılaştırmayla inceleyin,
            onaylayın veya gerekçeyle reddedin.
          </p>
        </div>
        <button
          className={styles.secondaryButton}
          type="button"
          disabled={isLoading}
          onClick={reloadQueue}
        >
          Kuyruğu yenile
        </button>
      </header>

      <form className={styles.queueFilters} role="search" onSubmit={applyFilter}>
        <div>
          <label htmlFor="change_request_status">Talep durumu</label>
          <select
            id="change_request_status"
            value={draftStatus}
            disabled={isLoading}
            onChange={(event) =>
              setDraftStatus(event.target.value as ProfileChangeRequestStatus)
            }
          >
            <option value="submitted">Değerlendirmede</option>
            <option value="approved">Onaylandı</option>
            <option value="rejected">Reddedildi</option>
            <option value="cancelled">İptal edildi</option>
          </select>
        </div>
        <button className={styles.primaryButton} type="submit" disabled={isLoading}>
          Filtreyi uygula
        </button>
      </form>

      <section className={styles.queueCard} aria-labelledby="profile-change-list-title">
        <header>
          <div>
            <span>Tenant karar kuyruğu</span>
            <h2 id="profile-change-list-title">{STATUS_LABELS[status]} talepler</h2>
          </div>
          <strong>Sayfa {cursorHistory.length + 1}</strong>
        </header>

        {error ? (
          <div className={styles.errorState} role="alert">
            <strong>Kuyruk yüklenemedi</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
            <button className={styles.secondaryButton} type="button" onClick={reloadQueue}>
              Yeniden dene
            </button>
          </div>
        ) : isLoading ? (
          <div className={styles.loadingState} role="status" aria-live="polite">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Değişiklik talepleri yükleniyor</strong>
          </div>
        ) : requests.length === 0 ? (
          <div className={styles.emptyState} role="status">
            <strong>Bu durumda talep bulunmuyor</strong>
            <p>Yeni talepler geldiğinde en eski gönderimden başlayarak burada sıralanır.</p>
          </div>
        ) : (
          <div className={styles.queueTableScroller}>
            <table className={styles.queueTable} aria-label={`${STATUS_LABELS[status]} profil değişiklik talepleri`}>
              <thead>
                <tr>
                  <th scope="col">Çalışan</th>
                  <th scope="col">Değişen alanlar</th>
                  <th scope="col">Gönderim</th>
                  <th scope="col">Profil durumu</th>
                  <th scope="col">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((request) => (
                  <tr key={request.id}>
                    <td data-label="Çalışan">
                      <strong>{employeeName(request)}</strong>
                      <small>{request.employee.employee_number}</small>
                    </td>
                    <td data-label="Değişen alanlar">
                      {request.changed_fields.map((field) => FIELD_LABELS[field]).join(", ")}
                    </td>
                    <td data-label="Gönderim">{formatTimestamp(request.submitted_at)}</td>
                    <td data-label="Profil durumu">
                      <span className={request.profile_is_stale ? styles.staleBadge : styles.currentBadge}>
                        {request.profile_is_stale ? "Profil değişmiş" : "Güncel"}
                      </span>
                    </td>
                    <td data-label="İşlem">
                      <Link
                        className={styles.detailLink}
                        href={`/profile-change-requests/${encodeURIComponent(request.id)}`}
                        aria-label={`${employeeName(request)} değişiklik talebini aç`}
                      >
                        Talebi aç <span aria-hidden="true">→</span>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!error && (requests.length > 0 || cursorHistory.length > 0) ? (
          <footer className={styles.pagination}>
            <span>Sayfa {cursorHistory.length + 1}</span>
            <div>
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={isLoading || cursorHistory.length === 0}
                onClick={showPreviousPage}
              >
                Önceki
              </button>
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={isLoading || !nextCursor}
                onClick={showNextPage}
              >
                Sonraki
              </button>
            </div>
          </footer>
        ) : null}
      </section>
    </section>
  );
}
