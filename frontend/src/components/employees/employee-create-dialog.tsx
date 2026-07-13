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
  type Employee,
  type EmployeeCreateStatus,
  EMPLOYEE_CREATE_STATUSES,
  createEmployee,
} from "@/lib/employees";

import styles from "./employees.module.css";
import {
  EMPLOYEE_STATUS_LABELS,
  type EmployeeErrorPresentation,
  employeeErrorPresentation,
} from "./employee-presentation";

interface EmployeeCreateDialogProps {
  onClose: () => void;
  onCreated: (employee: Employee) => void;
}

function localToday(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function EmployeeCreateDialog({
  onClose,
  onCreated,
}: EmployeeCreateDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<EmployeeErrorPresentation | null>(null);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSubmitting) onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSubmitting, onClose]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("input:not([disabled])")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSubmitting) onClose();
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), " +
          "[tabindex]:not([tabindex='-1'])",
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
    if (isSubmitting) return;

    const formData = new FormData(event.currentTarget);
    const email = String(formData.get("email") ?? "")
      .trim()
      .toLowerCase();
    setError(null);
    setIsSubmitting(true);
    try {
      const employee = await createEmployee({
        employee_number: String(formData.get("employee_number") ?? "").trim(),
        first_name: String(formData.get("first_name") ?? "").trim(),
        last_name: String(formData.get("last_name") ?? "").trim(),
        email: email || null,
        status: String(formData.get("status")) as EmployeeCreateStatus,
        employment_start_date: String(formData.get("employment_start_date") ?? ""),
      });
      onCreated(employee);
    } catch (cause) {
      setError(employeeErrorPresentation(cause, "create"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={`${styles.detailDialog} ${styles.createDialog}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-create-title"
        aria-busy={isSubmitting}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>İK çalışan kaydı</span>
            <h2 id="employee-create-title">Yeni çalışan</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Yeni çalışan penceresini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>Çalışan oluşturulamadı</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}

          <form className={styles.createForm} onSubmit={handleSubmit}>
            <p>
              Temel çalışan kaydını oluşturun. Organizasyon ataması daha sonra mevcut
              atama çalışma alanından güvenli geçmiş kaydıyla yapılabilir.
            </p>

            <div className={styles.formGrid}>
              <div className={styles.formField}>
                <label htmlFor="employee_number">Çalışan numarası</label>
                <input
                  id="employee_number"
                  name="employee_number"
                  type="text"
                  required
                  minLength={1}
                  maxLength={64}
                  autoCapitalize="characters"
                  spellCheck={false}
                  placeholder="Örn. WF-099"
                  disabled={isSubmitting}
                />
              </div>

              <div className={styles.formField}>
                <label htmlFor="employee_status">Çalışma durumu</label>
                <select
                  id="employee_status"
                  name="status"
                  defaultValue="active"
                  disabled={isSubmitting}
                >
                  {EMPLOYEE_CREATE_STATUSES.map((status) => (
                    <option value={status} key={status}>
                      {EMPLOYEE_STATUS_LABELS[status]}
                    </option>
                  ))}
                </select>
              </div>

              <div className={styles.formField}>
                <label htmlFor="employee_first_name">Ad</label>
                <input
                  id="employee_first_name"
                  name="first_name"
                  type="text"
                  autoComplete="given-name"
                  required
                  minLength={1}
                  maxLength={200}
                  disabled={isSubmitting}
                />
              </div>

              <div className={styles.formField}>
                <label htmlFor="employee_last_name">Soyad</label>
                <input
                  id="employee_last_name"
                  name="last_name"
                  type="text"
                  autoComplete="family-name"
                  required
                  minLength={1}
                  maxLength={200}
                  disabled={isSubmitting}
                />
              </div>

              <div className={`${styles.formField} ${styles.wideField}`}>
                <label htmlFor="employee_email">İş e-postası (isteğe bağlı)</label>
                <input
                  id="employee_email"
                  name="email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  maxLength={320}
                  placeholder="selin@ornek.com"
                  disabled={isSubmitting}
                />
              </div>

              <div className={`${styles.formField} ${styles.wideField}`}>
                <label htmlFor="employment_start_date">İşe başlangıç tarihi</label>
                <input
                  id="employment_start_date"
                  name="employment_start_date"
                  type="date"
                  defaultValue={localToday()}
                  required
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <footer className={styles.dialogActions}>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={onClose}
                disabled={isSubmitting}
              >
                Vazgeç
              </button>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Çalışan oluşturuluyor…" : "Çalışanı oluştur"}
              </button>
            </footer>
          </form>
        </div>
      </section>
    </div>
  );
}
