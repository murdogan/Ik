"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import type { Employee } from "@/lib/employees";
import { readEmployee } from "@/lib/employees";

import styles from "./employees.module.css";
import {
  type EmployeeErrorPresentation,
  employeeErrorPresentation,
  employeeFullName,
  formatEmployeeDate,
} from "./employee-presentation";
import { EmployeeStatusBadge } from "./employee-status-badge";

interface EmployeeSummaryDialogProps {
  employeeId: string;
  onClose: () => void;
}

export function EmployeeSummaryDialog({
  employeeId,
  onClose,
}: EmployeeSummaryDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<EmployeeErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let isActive = true;
    void readEmployee(employeeId).then(
      (loadedEmployee) => {
        if (!isActive) return;
        setEmployee(loadedEmployee);
        setError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setEmployee(null);
        setError(employeeErrorPresentation(cause, "read"));
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [employeeId, reloadKey]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

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

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) onClose();
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])",
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

  const title = employee ? employeeFullName(employee) : "Çalışan özeti";

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-summary-title"
        aria-busy={isLoading}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>Çalışan özeti</span>
            <h2 id="employee-summary-title">{title}</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            aria-label="Çalışan özetini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.summaryError} role="alert">
              <div>
                <strong>Çalışan özeti yüklenemedi</strong>
                <span>{error.message}</span>
                {error.reference ? <small>Referans: {error.reference}</small> : null}
              </div>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={() => {
                  setIsLoading(true);
                  setError(null);
                  setReloadKey((key) => key + 1);
                }}
              >
                Yeniden dene
              </button>
            </div>
          ) : isLoading ? (
            <div className={styles.dialogLoading} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <strong>Çalışan özeti yükleniyor</strong>
            </div>
          ) : employee ? (
            <div className={styles.summaryContent}>
              <div className={styles.identitySummary}>
                <span className={styles.avatar} aria-hidden="true">
                  {employee.first_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
                </span>
                <div>
                  <strong>{employeeFullName(employee)}</strong>
                  <span>{employee.email || "İş e-postası eklenmemiş"}</span>
                </div>
                <EmployeeStatusBadge status={employee.status} />
              </div>

              <dl className={styles.summaryMetadata}>
                <div>
                  <dt>Çalışan numarası</dt>
                  <dd>{employee.employee_number}</dd>
                </div>
                <div>
                  <dt>İşe başlangıç</dt>
                  <dd>{formatEmployeeDate(employee.employment_start_date)}</dd>
                </div>
                <div>
                  <dt>İşten ayrılış</dt>
                  <dd>{formatEmployeeDate(employee.employment_end_date)}</dd>
                </div>
                <div>
                  <dt>Kayıt sürümü</dt>
                  <dd>{employee.version}</dd>
                </div>
              </dl>

              <section
                className={styles.assignmentSummary}
                aria-labelledby="current-assignment-title"
              >
                <header>
                  <span>Güncel organizasyon</span>
                  <h3 id="current-assignment-title">Yapısal atama</h3>
                </header>
                {employee.current_assignment ? (
                  <dl className={styles.assignmentGrid}>
                    <div>
                      <dt>Tüzel kişilik</dt>
                      <dd>{employee.current_assignment.legal_entity.name}</dd>
                      <small>{employee.current_assignment.legal_entity.code}</small>
                    </div>
                    <div>
                      <dt>Şube</dt>
                      <dd>{employee.current_assignment.branch.name}</dd>
                      <small>{employee.current_assignment.branch.code}</small>
                    </div>
                    <div>
                      <dt>Departman</dt>
                      <dd>{employee.current_assignment.department.name}</dd>
                      <small>{employee.current_assignment.department.code}</small>
                    </div>
                    <div>
                      <dt>Pozisyon</dt>
                      <dd>{employee.current_assignment.position.title}</dd>
                      <small>{employee.current_assignment.position.code}</small>
                    </div>
                    <div>
                      <dt>Yürürlük</dt>
                      <dd>
                        {formatEmployeeDate(employee.current_assignment.effective_from)}
                      </dd>
                    </div>
                  </dl>
                ) : (
                  <div className={styles.assignmentEmpty}>
                    <span aria-hidden="true">O</span>
                    <div>
                      <strong>Henüz yapısal atama yok</strong>
                      <p>
                        Tüzel kişilik, şube, departman ve pozisyon ataması organizasyon
                        çalışma alanından eklenebilir.
                      </p>
                    </div>
                  </div>
                )}
              </section>

              <footer className={styles.dialogActions}>
                <button className={styles.primaryButton} type="button" onClick={onClose}>
                  Kapat
                </button>
              </footer>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
