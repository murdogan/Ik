"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
} from "react";

import styles from "./privacy.module.css";

export function PrivacyConfirmationDialog({
  title,
  description,
  confirmLabel,
  busyLabel,
  isBusy,
  danger = false,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: ReactNode;
  confirmLabel: string;
  busyLabel: string;
  isBusy: boolean;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isBusy) onCancel();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isBusy, onCancel]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("button:not([disabled])")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function closeFromBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isBusy) onCancel();
  }

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
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

  return (
    <div className={styles.dialogBackdrop} onMouseDown={closeFromBackdrop}>
      <section
        ref={dialogRef}
        className={styles.confirmDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={isBusy}
        onKeyDown={keepFocusInside}
      >
        <header>
          <span>İşlem onayı</span>
          <h2 id={titleId}>{title}</h2>
        </header>
        <div className={styles.confirmBody}>
          <div
            className={danger ? styles.dangerNotice : styles.confirmNotice}
            id={descriptionId}
          >
            <span aria-hidden="true">!</span>
            <div>{description}</div>
          </div>
          <footer>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isBusy}
              onClick={onCancel}
            >
              Vazgeç
            </button>
            <button
              className={danger ? styles.dangerButton : styles.primaryButton}
              type="button"
              disabled={isBusy}
              onClick={onConfirm}
            >
              {isBusy ? busyLabel : confirmLabel}
            </button>
          </footer>
        </div>
      </section>
    </div>
  );
}
