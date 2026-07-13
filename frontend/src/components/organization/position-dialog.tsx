"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  type Position,
  createPosition,
  updatePosition,
} from "@/lib/organization";

import styles from "./organization.module.css";
import {
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

interface PositionDialogProps {
  position: Position | null;
  onClose: () => void;
  onSaved: (position: Position, created: boolean) => void;
}

export function PositionDialog({
  position,
  onClose,
  onSaved,
}: PositionDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const isCreating = position === null;
  const [code, setCode] = useState(position?.code ?? "");
  const [title, setTitle] = useState(position?.title ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<OrganizationErrorPresentation | null>(null);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving) onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSaving, onClose]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("input:not([readonly])")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSaving) onClose();
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])",
      ),
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving || position?.status === "archived") return;

    const normalizedCode = code.trim();
    const normalizedTitle = title.trim();
    if (!isCreating && normalizedTitle === position.title) {
      onClose();
      return;
    }

    setError(null);
    setIsSaving(true);
    try {
      const savedPosition = isCreating
        ? await createPosition({ code: normalizedCode, title: normalizedTitle })
        : await updatePosition(position.id, { title: normalizedTitle });
      onSaved(savedPosition, isCreating);
    } catch (cause) {
      setError(
        organizationErrorPresentation(
          cause,
          isCreating ? "position_create" : "position_update",
        ),
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="position-dialog-title"
        aria-busy={isSaving}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>{isCreating ? "Pozisyon oluştur" : "Pozisyonu düzenle"}</span>
            <h2 id="position-dialog-title">
              {isCreating ? "Yeni pozisyon" : position.title}
            </h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSaving}
            aria-label="Pozisyon penceresini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>
                {isCreating ? "Pozisyon oluşturulamadı" : "Pozisyon güncellenemedi"}
              </strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}

          <form className={styles.branchForm} onSubmit={handleSubmit}>
            <p>
              Pozisyon kataloğu, çalışan atamalarında yeniden kullanılabilen iş
              unvanlarını tanımlar. Kadro ve bütçe planlaması bu kaydın parçası değildir.
            </p>

            <div className={styles.formGrid}>
              <div className={styles.formField}>
                <label htmlFor="position_code">Sabit kod</label>
                <input
                  id="position_code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  readOnly={!isCreating}
                  required
                  minLength={1}
                  maxLength={32}
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                  placeholder="YAZILIM_MUHENDISI"
                  disabled={isSaving}
                />
                <small>
                  {isCreating
                    ? "Harf, sayı, tire ve alt çizgi kullanın."
                    : "Geçmiş atamaların tutarlılığı için değiştirilemez."}
                </small>
              </div>
              <div className={styles.formField}>
                <label htmlFor="position_title">Pozisyon unvanı</label>
                <input
                  id="position_title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  required
                  minLength={1}
                  maxLength={200}
                  disabled={isSaving}
                />
              </div>
            </div>

            <footer className={styles.dialogActions}>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={onClose}
                disabled={isSaving}
              >
                Vazgeç
              </button>
              <button className={styles.primaryButton} type="submit" disabled={isSaving}>
                {isSaving
                  ? "Kaydediliyor…"
                  : isCreating
                    ? "Pozisyon oluştur"
                    : "Değişiklikleri kaydet"}
              </button>
            </footer>
          </form>
        </div>
      </section>
    </div>
  );
}
