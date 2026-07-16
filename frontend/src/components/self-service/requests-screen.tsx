"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import { AUTHORIZATION_PERMISSIONS, hasPermission } from "@/lib/authorization";
import {
  createDocumentRequest,
  DOCUMENT_REQUEST_TYPE_LABELS,
  DOCUMENT_REQUEST_TYPES,
  listUnifiedRequests,
  type DocumentRequestType,
  type UnifiedRequest,
} from "@/lib/self-service";

import {
  formatDateTime,
  requestErrorMessage,
  REQUEST_KIND_LABELS,
  statusLabel,
} from "./presentation";
import styles from "./self-service.module.css";

function appendUnique(current: UnifiedRequest[], incoming: UnifiedRequest[]): UnifiedRequest[] {
  const values = new Map(current.map((item) => [`${item.kind}:${item.id}`, item]));
  for (const item of incoming) values.set(`${item.kind}:${item.id}`, item);
  return [...values.values()];
}

export function RequestsScreen() {
  const { sessionGeneration, user } = useSession();
  const canCreateDocumentRequest = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.createOwnDocumentRequest,
  );
  const [items, setItems] = useState<UnifiedRequest[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [requestType, setRequestType] = useState<DocumentRequestType>(
    "employment_letter",
  );
  const [isCreating, setIsCreating] = useState(false);
  const documentCommand = useRef<{
    requestType: DocumentRequestType;
    tenantId: string;
    key: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void listUnifiedRequests().then(
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
        setError(requestErrorMessage(cause, "Talepleriniz yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey, sessionGeneration, user.membership_id, user.tenant_id]);

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setError(null);
    try {
      const page = await listUnifiedRequests({ cursor: nextCursor });
      setItems((current) => appendUnique(current, page.items));
      setNextCursor(page.nextCursor);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Daha fazla talep yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function submitDocumentRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreateDocumentRequest || isCreating) return;
    setIsCreating(true);
    setError(null);
    setNotice(null);
    const previousCommand = documentCommand.current;
    const command =
      previousCommand?.requestType === requestType &&
      previousCommand.tenantId === user.tenant_id
        ? previousCommand
        : { requestType, tenantId: user.tenant_id, key: crypto.randomUUID() };
    documentCommand.current = command;
    try {
      await createDocumentRequest(requestType, command.key);
      documentCommand.current = null;
      setNotice("Belge talebiniz HR ekibine gönderildi.");
      setReloadKey((value) => value + 1);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Belge talebi gönderilemedi."));
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status >= 400 &&
        cause.status < 500
      ) {
        documentCommand.current = null;
      }
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>Tek talep görünümü</span>
          <h1>Talepler</h1>
          <p>
            Yetki kapsamınızdaki izin, profil değişikliği ve HR tarafından hazırlanacak belge
            taleplerini güvenli bir özetten takip edin.
          </p>
        </div>
        <button
          className={styles.secondaryButton}
          type="button"
          disabled={isLoading || isLoadingMore}
          onClick={() => setReloadKey((value) => value + 1)}
        >
          Yenile
        </button>
      </header>

      {error ? <div className={styles.errorBanner} role="alert">{error}</div> : null}
      {notice ? <div className={styles.successBanner} role="status">{notice}</div> : null}

      {canCreateDocumentRequest ? (
        <form className={styles.formCard} onSubmit={(event) => void submitDocumentRequest(event)}>
          <div>
            <span className={styles.eyebrow}>Yeni HR belge talebi</span>
            <h2>HR ekibinden belge isteyin</h2>
            <p className={styles.muted}>
              Bu talep, eksik belge yükleme kontrolünden ayrıdır; HR ekibinin sizin için yeni
              bir belge hazırlamasını ister.
            </p>
          </div>
          <div className={styles.field}>
            <label htmlFor="document-request-type">Belge türü</label>
            <select
              id="document-request-type"
              value={requestType}
              disabled={isCreating}
              onChange={(event) => setRequestType(event.target.value as DocumentRequestType)}
            >
              {DOCUMENT_REQUEST_TYPES.map((type) => (
                <option key={type} value={type}>
                  {DOCUMENT_REQUEST_TYPE_LABELS[type]}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.actions}>
            <button className={styles.primaryButton} type="submit" disabled={isCreating}>
              {isCreating ? "Talep gönderiliyor…" : "Belge talebi gönder"}
            </button>
          </div>
        </form>
      ) : null}

      <section className={styles.sectionCard} aria-labelledby="own-request-list-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Geçmiş ve açık işler</span>
            <h2 id="own-request-list-title">Talep akışı</h2>
            <p>Kişisel, güncel ekip veya HR kapsamı sunucu tarafından uygulanır.</p>
          </div>
          <strong>{isLoading ? "—" : items.length}</strong>
        </header>
        {isLoading ? (
          <div className={styles.loadingState} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Talepler yükleniyor</strong>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Henüz talep yok</strong>
            <p>Yeni bir izin veya HR belge talebi gönderdiğinizde burada görünür.</p>
          </div>
        ) : (
          <ul className={styles.list}>
            {items.map((item) => (
              <li className={styles.listItem} key={`${item.kind}:${item.id}`}>
                <div>
                  <div className={styles.badges}>
                    <span className={styles.badge}>{REQUEST_KIND_LABELS[item.kind]}</span>
                    <span className={styles.unreadBadge}>{statusLabel(item.status)}</span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{formatDateTime(item.submitted_at)}</p>
                </div>
                <Link href={`/requests/${item.id}`}>Ayrıntıyı aç</Link>
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
    </div>
  );
}
