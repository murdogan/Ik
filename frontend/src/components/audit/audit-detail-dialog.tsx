"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
} from "react";

import type { AuditEvent, AuditScope } from "@/lib/audit-events";

import styles from "./audit.module.css";
import {
  type AuditErrorPresentation,
  auditActorLabel,
  auditCategoryLabel,
  auditEventLabel,
  auditResultLabel,
  auditScopeLabel,
  formatAuditDate,
  humanizeIdentifier,
  metadataValueLabel,
  shortIdentifier,
} from "./audit-presentation";

interface AuditDetailDialogProps {
  event: AuditEvent;
  scope: AuditScope;
  isLoading: boolean;
  error: AuditErrorPresentation | null;
  onClose: () => void;
}

export function AuditDetailDialog({
  event,
  scope,
  isLoading,
  error,
  onClose,
}: AuditDetailDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const metadataEntries = Object.entries(event.metadata);

  useEffect(() => {
    function closeOnEscape(keyboardEvent: KeyboardEvent) {
      if (keyboardEvent.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("button")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function closeFromBackdrop(mouseEvent: MouseEvent<HTMLDivElement>) {
    if (mouseEvent.target === mouseEvent.currentTarget) {
      onClose();
    }
  }

  function keepFocusInDialog(keyboardEvent: ReactKeyboardEvent<HTMLElement>) {
    if (keyboardEvent.key !== "Tab") {
      return;
    }
    const focusable = Array.from(
      keyboardEvent.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), summary, a[href], [tabindex]:not([tabindex='-1'])",
      ),
    );
    if (focusable.length === 0) {
      keyboardEvent.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (keyboardEvent.shiftKey && document.activeElement === first) {
      keyboardEvent.preventDefault();
      last.focus();
    } else if (!keyboardEvent.shiftKey && document.activeElement === last) {
      keyboardEvent.preventDefault();
      first.focus();
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={closeFromBackdrop}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-detail-title"
        onKeyDown={keepFocusInDialog}
        data-audit-detail-scope={scope}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>{auditScopeLabel(scope)}</span>
            <h2 id="audit-detail-title">{auditEventLabel(event.event_type)}</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            aria-label="Denetim kaydı ayrıntısını kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody} aria-busy={isLoading}>
          {isLoading ? (
            <div className={styles.detailLoading} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <div>
                <strong>Güvenli ayrıntılar yükleniyor</strong>
                <span>Olay görünürlüğü yeniden doğrulanıyor…</span>
              </div>
            </div>
          ) : null}

          {error ? (
            <div className={styles.detailError} role="alert">
              <strong>Ayrıntılar yüklenemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}

          {!isLoading ? (
            <>
              <div className={styles.detailSummary}>
                <div>
                  <span>Gerçekleşme zamanı</span>
                  <strong>{formatAuditDate(event.occurred_at)}</strong>
                </div>
                <div>
                  <span>Sonuç</span>
                  <strong>
                    <span className={styles.resultBadge} data-result={event.result}>
                      {auditResultLabel(event.result)}
                    </span>
                  </strong>
                </div>
                <div>
                  <span>Kategori</span>
                  <strong>{auditCategoryLabel(event.category)}</strong>
                </div>
                <div>
                  <span>Önem</span>
                  <strong>{humanizeIdentifier(event.severity)}</strong>
                </div>
              </div>

              <section className={styles.detailSection} aria-labelledby="event-context-title">
                <div className={styles.sectionHeading}>
                  <span>Olay bağlamı</span>
                  <h3 id="event-context-title">Kim, ne yaptı?</h3>
                </div>
                <dl className={styles.detailList}>
                  <div>
                    <dt>Olay türü</dt>
                    <dd className={styles.monospace}>{event.event_type}</dd>
                  </div>
                  <div>
                    <dt>İşlem</dt>
                    <dd>{humanizeIdentifier(event.action)}</dd>
                  </div>
                  <div>
                    <dt>Aktör</dt>
                    <dd>
                      {auditActorLabel(event.actor_type)}
                      {event.actor_user_id
                        ? ` · ${shortIdentifier(event.actor_user_id)}`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Kaynak</dt>
                    <dd>
                      {event.resource_type
                        ? `${humanizeIdentifier(event.resource_type)} · ${shortIdentifier(event.resource_id)}`
                        : "—"}
                    </dd>
                  </div>
                </dl>
              </section>

              <section className={styles.detailSection} aria-labelledby="safe-data-title">
                <div className={styles.sectionHeading}>
                  <span>Güvenli değişiklik özeti</span>
                  <h3 id="safe-data-title">Kaydedilen alanlar</h3>
                </div>
                {event.changed_fields.length > 0 ? (
                  <div className={styles.fieldChips} aria-label="Değişen alanlar">
                    {event.changed_fields.map((field) => (
                      <span key={field}>{humanizeIdentifier(field)}</span>
                    ))}
                  </div>
                ) : (
                  <p className={styles.sectionEmpty}>Bu olay için değişen alan kaydı yok.</p>
                )}

                {metadataEntries.length > 0 ? (
                  <dl className={styles.metadataList}>
                    {metadataEntries.map(([key, value]) => (
                      <div key={key}>
                        <dt>{humanizeIdentifier(key)}</dt>
                        <dd>{metadataValueLabel(value)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className={styles.sectionEmpty}>Güvenli ek metadata bulunmuyor.</p>
                )}
              </section>

              <details className={styles.technicalDetails}>
                <summary>Teknik iz bilgileri</summary>
                <dl className={styles.technicalList}>
                  <div>
                    <dt>Kayıt kimliği</dt>
                    <dd>{event.id}</dd>
                  </div>
                  <div>
                    <dt>İstek kimliği</dt>
                    <dd>{event.request_id}</dd>
                  </div>
                  <div>
                    <dt>Trace kimliği</dt>
                    <dd>{event.trace_id}</dd>
                  </div>
                  <div>
                    <dt>Oturum kimliği</dt>
                    <dd>{event.session_id ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>IP adresi</dt>
                    <dd>{event.ip_address ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Tarayıcı bilgisi</dt>
                    <dd>{event.user_agent ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Veri sınıfı</dt>
                    <dd>{humanizeIdentifier(event.data_classification)}</dd>
                  </div>
                  <div>
                    <dt>Görünürlük</dt>
                    <dd>{humanizeIdentifier(event.visibility_class)}</dd>
                  </div>
                </dl>
              </details>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}
