"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { type Department, archiveDepartment } from "@/lib/organization";

import styles from "./organization.module.css";
import {
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
} from "./organization-presentation";

interface ArchiveDepartmentDialogProps {
  department: Department;
  onClose: () => void;
  onArchived: (department: Department) => void;
}

export function ArchiveDepartmentDialog({
  department,
  onClose,
  onArchived,
}: ArchiveDepartmentDialogProps) {
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
      onArchived(await archiveDepartment(department.id));
    } catch (cause) {
      setError(organizationErrorPresentation(cause, "department_archive"));
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
        aria-labelledby="archive-department-title"
        aria-describedby="archive-department-description"
        aria-busy={isArchiving}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>Departman arşivi</span>
            <h2 id="archive-department-title">{department.name} arşivlensin mi?</h2>
          </div>
        </header>
        <div className={styles.dialogBody}>
          <div className={styles.archiveNotice} id="archive-department-description">
            <span aria-hidden="true">!</span>
            <div>
              <strong>Hiyerarşi geçmişi korunacak</strong>
              <p>
                Etkin alt departmanı bulunan kayıtlar arşivlenemez. Kayıt geçmişteki üst
                bağlantısıyla okunmaya devam eder; yeni alt departman veya yapılandırılmış
                atama alamaz. Sabit kodu{" "}
                <strong>{department.code}</strong> rezerve kalır.
              </p>
            </div>
          </div>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>Departman arşivlenemedi</strong>
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
              {isArchiving ? "Arşivleniyor…" : "Departmanı arşivle"}
            </button>
          </footer>
        </div>
      </section>
    </div>
  );
}
