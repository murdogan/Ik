"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  PlatformTenantErrorPresentation,
  PlatformTenantInitialAdminCorrectionRequest,
} from "@/lib/platform-tenants";

import styles from "./platform-tenant-operations.module.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+$/;

export function InitialAdminCorrectionDialog({
  error,
  isBusy,
  isOutcomeUnknown,
  onCancel,
  onConfirm,
}: {
  error: PlatformTenantErrorPresentation | null;
  isBusy: boolean;
  isOutcomeUnknown: boolean;
  onCancel: () => void;
  onConfirm: (
    payload: PlatformTenantInitialAdminCorrectionRequest,
  ) => Promise<void>;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const validationErrorRef = useRef<HTMLDivElement>(null);
  const operationErrorRef = useRef<HTMLDivElement>(null);
  const submitLockRef = useRef(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current
        ?.querySelector<HTMLInputElement>("input:not([disabled])")
        ?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      if (previouslyFocused?.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, []);

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
      } else if (document.activeElement === dialog && !error) {
        dialog
          .querySelector<HTMLElement>(
            "button:not([disabled]), input:not([disabled])",
          )
          ?.focus();
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [error, isBusy]);

  useEffect(() => {
    if (isBusy) return;
    const target = validationError
      ? validationErrorRef.current
      : error
        ? operationErrorRef.current
        : null;
    if (!target) return;
    const frame = window.requestAnimationFrame(() => target.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [error, isBusy, validationError]);

  function closeFromBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isBusy) onCancel();
  }

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled])",
      ),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      event.currentTarget.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const focusedError =
      document.activeElement === validationErrorRef.current ||
      document.activeElement === operationErrorRef.current;
    if (document.activeElement === event.currentTarget || focusedError) {
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isBusy || isOutcomeUnknown || submitLockRef.current) return;

    const form = new FormData(event.currentTarget);
    const fullName = String(form.get("full_name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim().toLowerCase();
    if (
      fullName.length < 1 ||
      fullName.length > 200 ||
      email.length < 3 ||
      email.length > 320 ||
      !EMAIL_PATTERN.test(email)
    ) {
      setValidationError(
        "İlk yönetici tam adı ve e-posta adresini kontrol edin.",
      );
      return;
    }

    setValidationError(null);
    submitLockRef.current = true;
    try {
      await onConfirm({ full_name: fullName, email });
    } finally {
      submitLockRef.current = false;
    }
  }

  return (
    <div
      className={styles.dialogBackdrop}
      onMouseDown={closeFromBackdrop}
    >
      <section
        ref={dialogRef}
        className={`${styles.dialog} ${styles.correctionDialog}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="initial-admin-correction-title"
        aria-describedby="initial-admin-correction-description"
        aria-busy={isBusy}
        tabIndex={-1}
        onKeyDown={keepFocusInside}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span className={styles.dialogEyebrow}>Güvenli davet düzeltmesi</span>
            <h2 id="initial-admin-correction-title">
              İlk yönetici bilgilerini düzelt
            </h2>
            <p id="initial-admin-correction-description">
              Önceki etkinleştirme bağlantısı geçersiz olur ve bu bilgiler için
              yeni bir davet hazırlanır.
            </p>
          </div>
          <button
            className={styles.dialogCloseButton}
            type="button"
            aria-label="İlk yönetici bilgileri penceresini kapat"
            disabled={isBusy}
            onClick={onCancel}
          >
            ×
          </button>
        </header>

        <form
          className={styles.dialogForm}
          autoComplete="off"
          noValidate
          onSubmit={(event) => void submit(event)}
        >
          <div className={styles.dialogBody}>
            {validationError || error ? (
              <div className={styles.dialogFeedback}>
                {validationError ? (
                  <div
                    ref={validationErrorRef}
                    className={styles.inlineError}
                    role="alert"
                    tabIndex={-1}
                  >
                    <strong>İlk yönetici bilgilerini kontrol edin</strong>
                    <span>{validationError}</span>
                  </div>
                ) : null}
                {error ? (
                  <div
                    ref={operationErrorRef}
                    className={styles.inlineError}
                    role="alert"
                    tabIndex={-1}
                  >
                    <strong>
                      {isOutcomeUnknown
                        ? "Sonuç doğrulanamadı"
                        : "İlk yönetici bilgileri düzeltilemedi"}
                    </strong>
                    <span>{error.message}</span>
                    {error.reference ? (
                      <small>Referans: {error.reference}</small>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <fieldset className={styles.formSection} disabled={isBusy}>
              <legend>Yeni ilk yönetici bilgileri</legend>
              <p className={styles.formSectionDescription}>
                Mevcut kimlik bilgileri güvenlik nedeniyle gösterilmez; iki
                alanı da yeniden girin.
              </p>
              <div className={styles.formGrid}>
                <label className={styles.field}>
                  <span>İlk yönetici tam adı</span>
                  <input
                    name="full_name"
                    required
                    minLength={1}
                    maxLength={200}
                    autoComplete="off"
                    disabled={isBusy}
                    onInput={() => setValidationError(null)}
                  />
                </label>
                <label className={styles.field}>
                  <span>İlk yönetici e-posta adresi</span>
                  <input
                    name="email"
                    type="email"
                    inputMode="email"
                    required
                    minLength={3}
                    maxLength={320}
                    autoComplete="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    disabled={isBusy}
                    onInput={() => setValidationError(null)}
                  />
                </label>
              </div>
            </fieldset>
          </div>

          <footer className={styles.dialogActions}>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isBusy}
              onClick={onCancel}
            >
              Vazgeç
            </button>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={isBusy || isOutcomeUnknown}
            >
              {isBusy ? "Davet hazırlanıyor…" : "Bilgileri düzelt"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
