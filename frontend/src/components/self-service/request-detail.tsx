"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  decimalNumber,
  DOCUMENT_REQUEST_TYPE_LABELS,
  readUnifiedRequest,
  type DocumentRequestType,
  type UnifiedRequest,
} from "@/lib/self-service";

import {
  formatDate,
  formatDateTime,
  requestErrorMessage,
  REQUEST_KIND_LABELS,
  statusLabel,
} from "./presentation";
import styles from "./self-service.module.css";

export function RequestDetailScreen({ requestId }: { requestId: string }) {
  const { sessionGeneration, user } = useSession();
  const [request, setRequest] = useState<UnifiedRequest | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void readUnifiedRequest(requestId).then(
      (result) => {
        if (!active) return;
        setRequest(result);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setRequest(null);
        setError(requestErrorMessage(cause, "Talep ayrıntısı yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey, requestId, sessionGeneration, user.tenant_id]);

  if (isLoading) {
    return (
      <section className={styles.loadingState} role="status">
        <span className={styles.spinner} aria-hidden="true" />
        <strong>Talep ayrıntısı yükleniyor</strong>
      </section>
    );
  }

  if (error || !request) {
    return (
      <section className={styles.errorState} role="alert">
        <strong>Talep açılamadı</strong>
        <p>{error ?? "Beklenmeyen bir yanıt alındı."}</p>
        <div className={styles.actions}>
          <Link className={styles.secondaryButton} href="/requests">Taleplere dön</Link>
          <button
            className={styles.primaryButton}
            type="button"
            onClick={() => setReloadKey((value) => value + 1)}
          >
            Yeniden dene
          </button>
        </div>
      </section>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>{REQUEST_KIND_LABELS[request.kind]}</span>
          <h1>{request.title}</h1>
          <p>Talebin durumunu ve güvenli işlem zaman çizelgesini görüntülüyorsunuz.</p>
        </div>
        <Link className={styles.secondaryButton} href="/requests">Taleplere dön</Link>
      </header>

      <article className={styles.detailCard}>
        <div className={styles.badges}>
          <span className={styles.badge}>{REQUEST_KIND_LABELS[request.kind]}</span>
          <span className={styles.unreadBadge}>{statusLabel(request.status)}</span>
        </div>
        <dl className={styles.detailGrid}>
          <div>
            <dt>Gönderim</dt>
            <dd>{formatDateTime(request.submitted_at)}</dd>
          </div>
          <div>
            <dt>Son güncelleme</dt>
            <dd>{formatDateTime(request.updated_at)}</dd>
          </div>
          <div>
            <dt>Sürüm</dt>
            <dd>{request.version}</dd>
          </div>
          {request.start_date && request.end_date ? (
            <div>
              <dt>Tarih aralığı</dt>
              <dd>{formatDate(request.start_date)} – {formatDate(request.end_date)}</dd>
            </div>
          ) : null}
          {request.counted_days !== null ? (
            <div>
              <dt>Çalışma günü</dt>
              <dd>{decimalNumber(request.counted_days).toLocaleString("tr-TR")}</dd>
            </div>
          ) : null}
          {request.document_request_type ? (
            <div>
              <dt>Belge türü</dt>
              <dd>
                {DOCUMENT_REQUEST_TYPE_LABELS[
                  request.document_request_type as DocumentRequestType
                ] ?? "HR belgesi"}
              </dd>
            </div>
          ) : null}
          {request.changed_fields.length > 0 ? (
            <div>
              <dt>Değişen alan sayısı</dt>
              <dd>{request.changed_fields.length}</dd>
            </div>
          ) : null}
        </dl>
      </article>

      <section className={styles.sectionCard} aria-labelledby="request-timeline-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>İşlem geçmişi</span>
            <h2 id="request-timeline-title">Zaman çizelgesi</h2>
            <p>Yalnız durum ve zaman bilgileri gösterilir.</p>
          </div>
        </header>
        {request.timeline.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Zaman çizelgesi henüz hazır değil</strong>
          </div>
        ) : (
          <ol className={`${styles.timeline} ${styles.formCard}`}>
            {request.timeline.map((entry, index) => (
              <li key={`${entry.event_type}:${entry.occurred_at}:${index}`}>
                <strong>{statusLabel(entry.status)}</strong>
                <time dateTime={entry.occurred_at}>{formatDateTime(entry.occurred_at)}</time>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
