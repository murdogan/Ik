"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type RefObject,
  useEffect,
  useRef,
} from "react";

import type { PlatformTenantErrorPresentation } from "@/lib/platform-tenants";

import styles from "./platform-tenant-operations.module.css";

export function PlatformConfirmationDialog({
  title,
  description,
  confirmLabel,
  busyLabel,
  isBusy,
  isConfirmDisabled = false,
  danger = false,
  error = null,
  errorTitle = "İşlem tamamlanamadı",
  fallbackFocusRef,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: ReactNode;
  confirmLabel: string;
  busyLabel: string;
  isBusy: boolean;
  isConfirmDisabled?: boolean;
  danger?: boolean;
  error?: PlatformTenantErrorPresentation | null;
  errorTitle?: string;
  fallbackFocusRef?: RefObject<HTMLElement | null>;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const fallbackFocus = fallbackFocusRef?.current ?? null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current
        ?.querySelector<HTMLElement>("button:not([disabled])")
        ?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      if (
        previouslyFocused?.isConnected &&
        !previouslyFocused.matches(":disabled")
      ) {
        previouslyFocused.focus();
      } else if (fallbackFocus?.isConnected) {
        fallbackFocus.focus();
      }
    };
  }, [fallbackFocusRef]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isBusy) {
        event.preventDefault();
        onCancel();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [isBusy, onCancel]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (isBusy) {
        dialog.focus();
      } else if (document.activeElement === dialog) {
        dialog
          .querySelector<HTMLElement>("button:not([disabled])")
          ?.focus();
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isBusy]);

  useEffect(() => {
    if (!error || isBusy) return;
    const frame = window.requestAnimationFrame(() => {
      errorRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [error, isBusy]);

  function closeFromBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isBusy) onCancel();
  }

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled])",
      ),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      event.currentTarget.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      document.activeElement === event.currentTarget ||
      document.activeElement === errorRef.current
    ) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className={`${styles.dialogBackdrop} ${styles.confirmDialogBackdrop}`}
      onMouseDown={closeFromBackdrop}
    >
      <section
        ref={dialogRef}
        className={styles.confirmDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="platform-confirm-title"
        aria-describedby="platform-confirm-description"
        aria-busy={isBusy}
        tabIndex={-1}
        onKeyDown={keepFocusInside}
      >
        <header className={styles.confirmHeader}>
          <span className={styles.confirmEyebrow}>İşlem onayı</span>
          <h2 id="platform-confirm-title">{title}</h2>
        </header>
        <div className={styles.confirmBody}>
          <div
            className={
              danger ? styles.confirmDanger : styles.confirmInformation
            }
            id="platform-confirm-description"
            data-tone={danger ? "danger" : "information"}
          >
            <span className={styles.confirmIcon} aria-hidden="true">
              {danger ? "!" : "i"}
            </span>
            <div className={styles.confirmCopy}>{description}</div>
          </div>
          {error ? (
            <div
              ref={errorRef}
              className={styles.inlineError}
              role="alert"
              tabIndex={-1}
            >
              <strong>{errorTitle}</strong>
              <span>{error.message}</span>
              {error.reference ? (
                <small>Referans: {error.reference}</small>
              ) : null}
            </div>
          ) : null}
          <footer className={styles.confirmActions}>
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
              disabled={isBusy || isConfirmDisabled}
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
