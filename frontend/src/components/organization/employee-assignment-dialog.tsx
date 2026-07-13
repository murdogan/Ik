"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  type AssignmentEmployeeOption,
  type AssignmentManagerOption,
  type EmployeeAssignment,
  changeEmployeeAssignment,
  createEmployeeAssignment,
} from "@/lib/employee-assignments";
import {
  type EmployeeAssignmentErrorPresentation,
  employeeAssignmentErrorPresentation,
} from "@/lib/employee-assignment-presentation";
import {
  type Branch,
  type Department,
  type LegalEntity,
  type Position,
  listBranches,
  listDepartments,
  listPositions,
} from "@/lib/organization";

import styles from "./organization.module.css";

const SELECTOR_LIMIT = 100;

interface EmployeeAssignmentDialogProps {
  employee: AssignmentEmployeeOption;
  legalEntity: LegalEntity;
  assignment: EmployeeAssignment | null;
  managers: AssignmentManagerOption[];
  onClose: () => void;
  onSaved: (assignment: EmployeeAssignment, created: boolean) => void;
}

function localToday(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function EmployeeAssignmentDialog({
  employee,
  legalEntity,
  assignment,
  managers,
  onClose,
  onSaved,
}: EmployeeAssignmentDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const isCreating = assignment === null;
  const [branches, setBranches] = useState<Branch[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [branchId, setBranchId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [positionId, setPositionId] = useState("");
  const [managerId, setManagerId] = useState(assignment?.manager?.id ?? "");
  const [effectiveFrom, setEffectiveFrom] = useState(localToday);
  const [changeReason, setChangeReason] = useState("");
  const [isLoadingOptions, setIsLoadingOptions] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] =
    useState<EmployeeAssignmentErrorPresentation | null>(null);
  const availableManagers = useMemo(
    () => managers.filter((manager) => manager.email !== employee.email),
    [employee.email, managers],
  );

  useEffect(() => {
    let isActive = true;
    void Promise.all([
      listBranches({
        legalEntityId: legalEntity.id,
        status: "active",
        limit: SELECTOR_LIMIT,
      }),
      listDepartments({ status: "active", limit: SELECTOR_LIMIT }),
      listPositions({ status: "active", limit: SELECTOR_LIMIT }),
    ]).then(
      ([branchPage, departmentPage, positionPage]) => {
        if (!isActive) return;
        const activeBranches = branchPage.data.filter(
          (branch) => branch.accepts_new_assignments,
        );
        const activeDepartments = departmentPage.data.filter(
          (department) => department.accepts_new_assignments,
        );
        const activePositions = positionPage.data.filter(
          (position) => position.accepts_new_assignments,
        );
        setBranches(activeBranches);
        setDepartments(activeDepartments);
        setPositions(activePositions);
        setBranchId(
          activeBranches.some((branch) => branch.id === assignment?.branch.id)
            ? (assignment?.branch.id ?? "")
            : (activeBranches[0]?.id ?? ""),
        );
        setDepartmentId(
          activeDepartments.some(
            (department) => department.id === assignment?.department.id,
          )
            ? (assignment?.department.id ?? "")
            : (activeDepartments[0]?.id ?? ""),
        );
        setPositionId(
          activePositions.some((position) => position.id === assignment?.position.id)
            ? (assignment?.position.id ?? "")
            : (activePositions[0]?.id ?? ""),
        );
        setError(null);
        setIsLoadingOptions(false);
      },
      (cause) => {
        if (!isActive) return;
        setError(employeeAssignmentErrorPresentation(cause, "options"));
        setIsLoadingOptions(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [assignment, legalEntity.id]);

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
      dialogRef.current?.querySelector<HTMLElement>("select:not([disabled])")?.focus();
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
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), " +
          "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
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
    if (
      isSaving ||
      isLoadingOptions ||
      !branchId ||
      !departmentId ||
      !positionId
    ) {
      return;
    }

    setError(null);
    setIsSaving(true);
    try {
      const normalizedReason = changeReason.trim();
      const saved = isCreating
        ? await createEmployeeAssignment({
            employee_id: employee.id,
            legal_entity_id: legalEntity.id,
            branch_id: branchId,
            department_id: departmentId,
            position_id: positionId,
            manager_id: managerId || null,
            effective_from: effectiveFrom,
            change_reason: normalizedReason || null,
          })
        : await changeEmployeeAssignment(assignment.id, {
            legal_entity_id: legalEntity.id,
            branch_id: branchId,
            department_id: departmentId,
            position_id: positionId,
            manager_id: managerId || null,
            effective_from: effectiveFrom,
            change_reason: normalizedReason,
          });
      onSaved(saved, isCreating);
    } catch (cause) {
      setError(
        employeeAssignmentErrorPresentation(
          cause,
          isCreating ? "create" : "change",
        ),
      );
    } finally {
      setIsSaving(false);
    }
  }

  const hasRequiredStructure =
    branches.length > 0 && departments.length > 0 && positions.length > 0;

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-assignment-dialog-title"
        aria-busy={isLoadingOptions || isSaving}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>{isCreating ? "Yapısal atama" : "Atama değişikliği"}</span>
            <h2 id="employee-assignment-dialog-title">{employee.full_name}</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSaving}
            aria-label="Çalışan ataması penceresini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>
                {isCreating ? "Atama oluşturulamadı" : "Atama değiştirilemedi"}
              </strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}

          <form className={styles.branchForm} onSubmit={handleSubmit}>
            <p>
              <strong>{employee.employee_number}</strong> numaralı çalışanı {" "}
              <strong>{legalEntity.name}</strong> yapısına bağlayın. Değişiklikler eski
              atamayı silmez; yürürlük tarihine göre yeni bir geçmiş kaydı oluşturur.
            </p>

            {isLoadingOptions ? (
              <div className={styles.dialogLoading} role="status">
                <span className={styles.spinner} aria-hidden="true" />
                <strong>Aktif organizasyon seçenekleri yükleniyor</strong>
              </div>
            ) : (
              <div className={styles.formGrid}>
                <div className={styles.formField}>
                  <label htmlFor="assignment_legal_entity">Tüzel kişilik</label>
                  <input
                    id="assignment_legal_entity"
                    value={legalEntity.name}
                    readOnly
                  />
                </div>
                <div className={styles.formField}>
                  <label htmlFor="assignment_branch">Şube</label>
                  <select
                    id="assignment_branch"
                    value={branchId}
                    onChange={(event) => setBranchId(event.target.value)}
                    required
                    disabled={isSaving || branches.length === 0}
                  >
                    {branches.length === 0 ? (
                      <option value="">Aktif şube bulunamadı</option>
                    ) : null}
                    {branches.map((branch) => (
                      <option value={branch.id} key={branch.id}>
                        {branch.name} · {branch.code}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={styles.formField}>
                  <label htmlFor="assignment_department">Departman</label>
                  <select
                    id="assignment_department"
                    value={departmentId}
                    onChange={(event) => setDepartmentId(event.target.value)}
                    required
                    disabled={isSaving || departments.length === 0}
                  >
                    {departments.length === 0 ? (
                      <option value="">Aktif departman bulunamadı</option>
                    ) : null}
                    {departments.map((department) => (
                      <option value={department.id} key={department.id}>
                        {department.name} · {department.code}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={styles.formField}>
                  <label htmlFor="assignment_position">Pozisyon</label>
                  <select
                    id="assignment_position"
                    value={positionId}
                    onChange={(event) => setPositionId(event.target.value)}
                    required
                    disabled={isSaving || positions.length === 0}
                  >
                    {positions.length === 0 ? (
                      <option value="">Aktif pozisyon bulunamadı</option>
                    ) : null}
                    {positions.map((position) => (
                      <option value={position.id} key={position.id}>
                        {position.title} · {position.code}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={styles.formField}>
                  <label htmlFor="assignment_manager">Yönetici</label>
                  <select
                    id="assignment_manager"
                    value={managerId}
                    onChange={(event) => setManagerId(event.target.value)}
                    disabled={isSaving}
                  >
                    <option value="">Yönetici yok</option>
                    {availableManagers.map((manager) => (
                      <option value={manager.id} key={manager.id}>
                        {manager.full_name}
                        {manager.email ? ` · ${manager.email}` : ""}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={styles.formField}>
                  <label htmlFor="assignment_effective_from">Yürürlük tarihi</label>
                  <input
                    id="assignment_effective_from"
                    type="date"
                    value={effectiveFrom}
                    onChange={(event) => setEffectiveFrom(event.target.value)}
                    required
                    disabled={isSaving}
                  />
                </div>
                <div className={`${styles.formField} ${styles.wideField}`}>
                  <label htmlFor="assignment_change_reason">
                    {isCreating ? "Atama notu (isteğe bağlı)" : "Değişiklik nedeni"}
                  </label>
                  <textarea
                    id="assignment_change_reason"
                    value={changeReason}
                    onChange={(event) => setChangeReason(event.target.value)}
                    required={!isCreating}
                    minLength={isCreating ? undefined : 1}
                    maxLength={500}
                    disabled={isSaving}
                    placeholder={
                      isCreating
                        ? "İlk atamayla ilgili isteğe bağlı açıklama"
                        : "Raporlama hattı veya yapı neden değişti?"
                    }
                  />
                </div>
              </div>
            )}

            {!isLoadingOptions && !hasRequiredStructure ? (
              <div className={styles.inlineWarning} role="alert">
                Atama yapabilmek için bu tüzel kişilikte aktif bir şube ile en az bir
                aktif departman ve pozisyon bulunmalıdır.
              </div>
            ) : null}

            <footer className={styles.dialogActions}>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={onClose}
                disabled={isSaving}
              >
                Vazgeç
              </button>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={isSaving || isLoadingOptions || !hasRequiredStructure}
              >
                {isSaving
                  ? "Kaydediliyor…"
                  : isCreating
                    ? "Atamayı oluştur"
                    : "Değişikliği kaydet"}
              </button>
            </footer>
          </form>
        </div>
      </section>
    </div>
  );
}
