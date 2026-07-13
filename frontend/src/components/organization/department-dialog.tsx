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
  type Department,
  createDepartment,
  updateDepartment,
} from "@/lib/organization";

import styles from "./organization.module.css";
import {
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

interface DepartmentDialogProps {
  department: Department | null;
  parent: Department | null;
  onClose: () => void;
  onSaved: (department: Department, created: boolean) => void;
}

export function DepartmentDialog({
  department,
  parent,
  onClose,
  onSaved,
}: DepartmentDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const isCreating = department === null;
  const [code, setCode] = useState(department?.code ?? "");
  const [name, setName] = useState(department?.name ?? "");
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
    if (isSaving || department?.status === "archived") return;

    const normalizedCode = code.trim();
    const normalizedName = name.trim();
    if (!isCreating && normalizedName === department.name) {
      onClose();
      return;
    }

    setError(null);
    setIsSaving(true);
    try {
      const savedDepartment = isCreating
        ? await createDepartment({
            code: normalizedCode,
            name: normalizedName,
            parent_id: parent?.id ?? null,
          })
        : await updateDepartment(department.id, { name: normalizedName });
      onSaved(savedDepartment, isCreating);
    } catch (cause) {
      setError(
        organizationErrorPresentation(
          cause,
          isCreating ? "department_create" : "department_update",
        ),
      );
    } finally {
      setIsSaving(false);
    }
  }

  const title = isCreating
    ? parent
      ? `${parent.name} altında yeni departman`
      : "Yeni kök departman"
    : department.name;

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="department-dialog-title"
        aria-busy={isSaving}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>{isCreating ? "Departman oluştur" : "Departmanı yeniden adlandır"}</span>
            <h2 id="department-dialog-title">{title}</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSaving}
            aria-label="Departman penceresini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>
                {isCreating ? "Departman oluşturulamadı" : "Departman adı güncellenemedi"}
              </strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}

          <form className={styles.branchForm} onSubmit={handleSubmit}>
            <p>
              {parent ? (
                <>
                  Üst departman: <strong>{parent.name}</strong>. Üst departmanı değiştirmek
                  için hiyerarşideki taşıma işlemini kullanın.
                </>
              ) : (
                "Bu kayıt hiyerarşinin kök düzeyinde yer alır."
              )}
            </p>

            <div className={styles.formGrid}>
              <div className={styles.formField}>
                <label htmlFor="department_code">Sabit kod</label>
                <input
                  id="department_code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  readOnly={!isCreating}
                  required
                  minLength={1}
                  maxLength={32}
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                  placeholder="INSAN_KAYNAKLARI"
                  disabled={isSaving}
                />
                <small>
                  {isCreating
                    ? "Harf, sayı, tire ve alt çizgi kullanın."
                    : "Geçmiş kayıtların tutarlılığı için değiştirilemez."}
                </small>
              </div>
              <div className={styles.formField}>
                <label htmlFor="department_name">Departman adı</label>
                <input
                  id="department_name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
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
                    ? "Departman oluştur"
                    : "Yeni adı kaydet"}
              </button>
            </footer>
          </form>
        </div>
      </section>
    </div>
  );
}
