"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { type Position, archivePosition } from "@/lib/organization";

import styles from "./organization.module.css";
import {
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

interface ArchivePositionDialogProps {
  position: Position;
  onClose: () => void;
  onArchived: (position: Position) => void;
}

export function ArchivePositionDialog({
  position,
  onClose,
  onArchived,
}: ArchivePositionDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const [isArchiving, setIsArchiving] = useState(false);
  const [error, setError] = useState<OrganizationErrorPresentation | null>(null);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isArchiving) onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isArchiving, onClose]);

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

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isArchiving) onClose();
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("button:not([disabled])"),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function confirmArchive() {
    if (isArchiving) return;
    setError(null);
    setIsArchiving(true);
    try {
      onArchived(await archivePosition(position.id));
    } catch (cause) {
      setError(organizationErrorPresentation(cause, "position_archive"));
    } finally {
      setIsArchiving(false);
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={`${styles.detailDialog} ${styles.confirmDialog}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="archive-position-title"
        aria-describedby="archive-position-description"
        aria-busy={isArchiving}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>Pozisyon arşivi</span>
            <h2 id="archive-position-title">{position.title} arşivlensin mi?</h2>
          </div>
        </header>
        <div className={styles.dialogBody}>
          <div className={styles.archiveNotice} id="archive-position-description">
            <span aria-hidden="true">!</span>
            <div>
              <strong>Yeni atamalar durdurulacak</strong>
              <p>
                Pozisyon geçmiş çalışan atamalarında görünmeye devam eder ancak yeni
                atamalarda seçilemez. Sabit kodu <strong>{position.code}</strong> rezerve
                kalır.
              </p>
            </div>
          </div>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>Pozisyon arşivlenemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}
          <footer className={styles.dialogActions}>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={onClose}
              disabled={isArchiving}
            >
              Vazgeç
            </button>
            <button
              className={styles.dangerButton}
              type="button"
              onClick={() => void confirmArchive()}
              disabled={isArchiving}
            >
              {isArchiving ? "Arşivleniyor…" : "Pozisyonu arşivle"}
            </button>
          </footer>
        </div>
      </section>
    </div>
  );
}
