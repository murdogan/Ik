"use client";

import { useEffect, useRef, useState } from "react";

import { ProfileChangeRequestQueueScreen } from "@/components/profile-change-requests/profile-change-request-queue-screen";
import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  decideDocumentRequest,
  DOCUMENT_REQUEST_TYPE_LABELS,
  listDocumentRequests,
  type DocumentRequest,
  type DocumentRequestStatus,
} from "@/lib/self-service";

import {
  formatDateTime,
  isConflict,
  requestErrorMessage,
  statusLabel,
} from "./presentation";
import styles from "./self-service.module.css";

function appendUnique(current: DocumentRequest[], incoming: DocumentRequest[]): DocumentRequest[] {
  const values = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) values.set(item.id, item);
  return [...values.values()];
}

export function HrRequestWorkspace() {
  const { sessionGeneration, user } = useSession();
  const [items, setItems] = useState<DocumentRequest[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<DocumentRequestStatus | "all">(
    "submitted",
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selected, setSelected] = useState<DocumentRequest | null>(null);
  const [reason, setReason] = useState("");
  const [pendingAction, setPendingAction] = useState<"resolve" | "reject" | null>(null);
  const decisionCommand = useRef<{ fingerprint: string; key: string } | null>(null);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
      setSelected(null);
      setReason("");
    });
    void listDocumentRequests({
      scope: "hr",
      status: statusFilter === "all" ? undefined : statusFilter,
    }).then(
      (page) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.nextCursor);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setItems([]);
        setNextCursor(null);
        setError(requestErrorMessage(cause, "HR belge talepleri yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey, sessionGeneration, statusFilter, user.tenant_id]);

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setError(null);
    try {
      const page = await listDocumentRequests({
        scope: "hr",
        status: statusFilter === "all" ? undefined : statusFilter,
        cursor: nextCursor,
      });
      setItems((current) => appendUnique(current, page.items));
      setNextCursor(page.nextCursor);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Daha fazla belge talebi yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function decide(action: "resolve" | "reject") {
    if (!selected || pendingAction || reason.trim() === "") return;
    const normalizedReason = reason.trim();
    const fingerprint = JSON.stringify({
      tenantId: user.tenant_id,
      requestId: selected.id,
      version: selected.version,
      action,
      reason: normalizedReason,
    });
    const previousCommand = decisionCommand.current;
    const command =
      previousCommand?.fingerprint === fingerprint
        ? previousCommand
        : { fingerprint, key: crypto.randomUUID() };
    decisionCommand.current = command;
    setPendingAction(action);
    setError(null);
    setNotice(null);
    try {
      const updated = await decideDocumentRequest(
        selected.id,
        action,
        selected.version,
        normalizedReason,
        command.key,
      );
      decisionCommand.current = null;
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelected(null);
      setReason("");
      setNotice(
        action === "resolve"
          ? "Belge talebi çözüldü olarak kaydedildi."
          : "Belge talebi gerekçesiyle reddedildi.",
      );
      setReloadKey((value) => value + 1);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Belge talebi güncellenemedi."));
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status >= 400 &&
        cause.status < 500
      ) {
        decisionCommand.current = null;
      }
      if (isConflict(cause)) setReloadKey((value) => value + 1);
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <div className={styles.managerStack}>
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <div>
            <span className={styles.eyebrow}>HR talepleri</span>
            <h1>Profil ve belge talepleri</h1>
            <p>
              Çalışan profil değişikliklerini mevcut iş akışında, HR tarafından hazırlanacak
              belge taleplerini ayrı sabit kuyrukta yönetin.
            </p>
          </div>
        </header>

        {error ? <div className={styles.errorBanner} role="alert">{error}</div> : null}
        {notice ? <div className={styles.successBanner} role="status">{notice}</div> : null}

        <section className={styles.sectionCard} aria-labelledby="hr-document-queue-title">
          <header className={styles.sectionHeader}>
            <div>
              <span className={styles.eyebrow}>HR tarafından üretilecek belgeler</span>
              <h2 id="hr-document-queue-title">Belge talebi kuyruğu</h2>
              <p>Bu kuyruk çalışan belge yükleme ve eksik belge kontrolünden ayrıdır.</p>
            </div>
            <div className={styles.field}>
              <label htmlFor="document-request-status">Durum</label>
              <select
                id="document-request-status"
                value={statusFilter}
                disabled={isLoading || pendingAction !== null}
                onChange={(event) =>
                  setStatusFilter(event.target.value as DocumentRequestStatus | "all")
                }
              >
                <option value="submitted">Bekleyen</option>
                <option value="resolved">Çözülen</option>
                <option value="rejected">Reddedilen</option>
                <option value="all">Tümü</option>
              </select>
            </div>
          </header>
          {isLoading ? (
            <div className={styles.loadingState} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <strong>Belge talepleri yükleniyor</strong>
            </div>
          ) : items.length === 0 ? (
            <div className={styles.emptyState}>
              <strong>Bu durumda belge talebi yok</strong>
              <p>Çalışanların yeni talepleri gönderildiğinde kuyrukta görünür.</p>
            </div>
          ) : (
            <ul className={styles.list}>
              {items.map((item) => (
                <li className={styles.listItem} key={item.id}>
                  <div>
                    <div className={styles.badges}>
                      <span className={styles.badge}>{statusLabel(item.status)}</span>
                    </div>
                    <h3>{item.employee_name ?? "Çalışan"}</h3>
                    <p>{DOCUMENT_REQUEST_TYPE_LABELS[item.request_type]}</p>
                    <p>{formatDateTime(item.created_at)}</p>
                  </div>
                  {item.status === "submitted" ? (
                    <button
                      className={styles.textButton}
                      type="button"
                      disabled={pendingAction !== null}
                      onClick={() => {
                        setSelected(item);
                        setReason("");
                      }}
                    >
                      Karar ver
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {nextCursor ? (
            <div className={styles.loadMore}>
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={isLoadingMore}
                onClick={() => void loadMore()}
              >
                {isLoadingMore ? "Talepler yükleniyor…" : "Daha fazla göster"}
              </button>
            </div>
          ) : null}
        </section>

        {selected ? (
          <section className={styles.formCard} aria-labelledby="document-decision-title">
            <div>
              <span className={styles.eyebrow}>Karar</span>
              <h2 id="document-decision-title">{selected.employee_name ?? "Çalışan"} · {DOCUMENT_REQUEST_TYPE_LABELS[selected.request_type]}</h2>
              <p className={styles.muted}>
                Karar gerekçesi çalışanın talep ayrıntısında görülebilir. Kısa ve işlemsel yazın.
              </p>
            </div>
            <div className={styles.field}>
              <label htmlFor="document-decision-reason">Gerekçe</label>
              <textarea
                id="document-decision-reason"
                rows={4}
                maxLength={500}
                value={reason}
                disabled={pendingAction !== null}
                onChange={(event) => setReason(event.target.value)}
              />
              <span className={styles.muted}>{reason.length}/500</span>
            </div>
            <div className={styles.actions}>
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={pendingAction !== null}
                onClick={() => setSelected(null)}
              >
                Vazgeç
              </button>
              <button
                className={styles.dangerButton}
                type="button"
                disabled={pendingAction !== null || reason.trim() === ""}
                onClick={() => void decide("reject")}
              >
                {pendingAction === "reject" ? "Reddediliyor…" : "Reddet"}
              </button>
              <button
                className={styles.primaryButton}
                type="button"
                disabled={pendingAction !== null || reason.trim() === ""}
                onClick={() => void decide("resolve")}
              >
                {pendingAction === "resolve" ? "Çözülüyor…" : "Çözüldü olarak işaretle"}
              </button>
            </div>
          </section>
        ) : null}
      </div>

      <ProfileChangeRequestQueueScreen />
    </div>
  );
}
