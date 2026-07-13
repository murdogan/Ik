"use client";

import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  type EmployeeAssignment,
  type EmployeeAssignmentOptions,
  listEmployeeAssignmentOptions,
  listEmployeeAssignments,
} from "@/lib/employee-assignments";
import {
  EMPLOYEE_STATUS_LABELS,
  type EmployeeAssignmentErrorPresentation,
  employeeAssignmentErrorPresentation,
  formatAssignmentDate,
} from "@/lib/employee-assignment-presentation";
import type { LegalEntity } from "@/lib/organization";

import { EmployeeAssignmentDialog } from "./employee-assignment-dialog";
import styles from "./organization.module.css";

export function EmployeeAssignmentPanel({
  legalEntity,
}: {
  legalEntity: LegalEntity;
}) {
  const noticeRef = useRef<HTMLDivElement>(null);
  const [options, setOptions] = useState<EmployeeAssignmentOptions | null>(null);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [optionsSearch, setOptionsSearch] = useState("");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState("");
  const [assignments, setAssignments] = useState<EmployeeAssignment[]>([]);
  const [historyNextCursor, setHistoryNextCursor] = useState<string | null>(null);
  const [isLoadingOptions, setIsLoadingOptions] = useState(true);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isLoadingMoreHistory, setIsLoadingMoreHistory] = useState(false);
  const [optionsError, setOptionsError] =
    useState<EmployeeAssignmentErrorPresentation | null>(null);
  const [historyError, setHistoryError] =
    useState<EmployeeAssignmentErrorPresentation | null>(null);
  const [historyPageError, setHistoryPageError] =
    useState<EmployeeAssignmentErrorPresentation | null>(null);
  const [optionsReloadKey, setOptionsReloadKey] = useState(0);
  const [historyReloadKey, setHistoryReloadKey] = useState(0);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeFocusRequest, setNoticeFocusRequest] = useState(0);

  useEffect(() => {
    if (noticeFocusRequest === 0) return;
    const frame = window.requestAnimationFrame(() => noticeRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [noticeFocusRequest]);

  useEffect(() => {
    let isActive = true;
    void listEmployeeAssignmentOptions(optionsSearch || undefined).then(
      (loadedOptions) => {
        if (!isActive) return;
        setOptions(loadedOptions);
        if (loadedOptions.employees.length === 0) {
          setAssignments([]);
          setHistoryNextCursor(null);
          setIsLoadingHistory(false);
        } else {
          setIsLoadingHistory(true);
          setHistoryReloadKey((key) => key + 1);
        }
        setSelectedEmployeeId((currentId) =>
          loadedOptions.employees.some((employee) => employee.id === currentId)
            ? currentId
            : (loadedOptions.employees[0]?.id ?? ""),
        );
        setOptionsError(null);
        setIsLoadingOptions(false);
      },
      (cause) => {
        if (!isActive) return;
        setOptions(null);
        setAssignments([]);
        setHistoryNextCursor(null);
        setOptionsError(employeeAssignmentErrorPresentation(cause, "options"));
        setIsLoadingOptions(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [optionsReloadKey, optionsSearch]);

  useEffect(() => {
    if (!selectedEmployeeId) {
      return;
    }

    let isActive = true;
    void listEmployeeAssignments(selectedEmployeeId).then(
      (page) => {
        if (!isActive) return;
        setAssignments(page.data);
        setHistoryNextCursor(page.meta.next_cursor);
        setHistoryError(null);
        setHistoryPageError(null);
        setIsLoadingHistory(false);
      },
      (cause) => {
        if (!isActive) return;
        setAssignments([]);
        setHistoryNextCursor(null);
        setHistoryError(employeeAssignmentErrorPresentation(cause, "history"));
        setIsLoadingHistory(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [historyReloadKey, selectedEmployeeId]);

  const selectedEmployee = useMemo(
    () =>
      options?.employees.find((employee) => employee.id === selectedEmployeeId) ??
      null,
    [options, selectedEmployeeId],
  );
  const currentAssignment =
    assignments.find(
      (assignment) => assignment.id === selectedEmployee?.current_assignment_id,
    ) ?? assignments.find((assignment) => assignment.is_current) ?? null;

  function reloadOptions() {
    setIsLoadingOptions(true);
    setOptionsError(null);
    setNotice(null);
    setOptionsReloadKey((key) => key + 1);
  }

  function reloadHistory() {
    if (!selectedEmployeeId) return;
    setIsLoadingHistory(true);
    setHistoryError(null);
    setHistoryPageError(null);
    setHistoryNextCursor(null);
    setNotice(null);
    setHistoryReloadKey((key) => key + 1);
  }

  function searchEmployees(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = employeeSearch.trim();
    setIsLoadingOptions(true);
    setOptionsError(null);
    setNotice(null);
    if (normalized === optionsSearch) {
      setOptionsReloadKey((key) => key + 1);
    } else {
      setOptionsSearch(normalized);
    }
  }

  async function loadMoreHistory() {
    if (!selectedEmployeeId || !historyNextCursor || isLoadingMoreHistory) return;
    setIsLoadingMoreHistory(true);
    setHistoryPageError(null);
    try {
      const page = await listEmployeeAssignments(
        selectedEmployeeId,
        historyNextCursor,
      );
      setAssignments((current) => [...current, ...page.data]);
      setHistoryNextCursor(page.meta.next_cursor);
    } catch (cause) {
      setHistoryPageError(employeeAssignmentErrorPresentation(cause, "history"));
    } finally {
      setIsLoadingMoreHistory(false);
    }
  }

  function handleSaved(saved: EmployeeAssignment, created: boolean) {
    setIsEditorOpen(false);
    setNotice(
      created
        ? "Yapısal çalışan ataması oluşturuldu."
        : "Atama ve raporlama hattı yürürlük tarihine göre değiştirildi.",
    );
    setNoticeFocusRequest((request) => request + 1);
    setOptions((currentOptions) =>
      currentOptions
        ? {
            ...currentOptions,
            employees: currentOptions.employees.map((employee) =>
              employee.id === saved.employee.id
                ? { ...employee, current_assignment_id: saved.id }
                : employee,
            ),
          }
        : currentOptions,
    );
    setIsLoadingHistory(true);
    setHistoryNextCursor(null);
    setHistoryPageError(null);
    setHistoryReloadKey((key) => key + 1);
  }

  const canOpenEditor =
    selectedEmployee !== null &&
    legalEntity.status === "active" &&
    !isLoadingHistory &&
    !historyError;

  return (
    <>
      <article
        className={styles.departmentCard}
        aria-labelledby="employee-assignments-title"
        aria-busy={isLoadingOptions || isLoadingHistory}
      >
        <header className={styles.departmentHeader}>
          <div>
            <h2 id="employee-assignments-title">Çalışan atamaları</h2>
            <span>
              Tüzel kişilik, şube, departman, pozisyon ve raporlama hattını yönetin.
            </span>
          </div>
          <div className={styles.departmentTools}>
            <button
              className={styles.refreshButton}
              type="button"
              onClick={reloadOptions}
              disabled={isLoadingOptions || isLoadingHistory}
            >
              Seçenekleri yenile
            </button>
            <button
              className={styles.primaryButton}
              type="button"
              onClick={() => {
                setNotice(null);
                setIsEditorOpen(true);
              }}
              disabled={!canOpenEditor}
              title={
                legalEntity.status === "active"
                  ? undefined
                  : "Pasif tüzel kişiliğe yeni atama yapılamaz."
              }
            >
              <span aria-hidden="true">＋</span>
              {currentAssignment ? "Atamayı değiştir" : "Atama oluştur"}
            </button>
          </div>
        </header>

        {notice ? (
          <div
            ref={noticeRef}
            className={styles.departmentNotice}
            role="status"
            tabIndex={-1}
          >
            <span aria-hidden="true">✓</span>
            <span>{notice}</span>
            <button type="button" onClick={() => setNotice(null)} aria-label="Bildirimi kapat">
              ×
            </button>
          </div>
        ) : null}

        <form className={styles.assignmentSearch} onSubmit={searchEmployees} role="search">
          <div className={styles.selectorField}>
            <label htmlFor="assignment_employee_search">Çalışan ara</label>
            <input
              id="assignment_employee_search"
              type="search"
              value={employeeSearch}
              onChange={(event) => setEmployeeSearch(event.target.value)}
              maxLength={100}
              placeholder="Ad, çalışan numarası veya e-posta"
              disabled={isLoadingOptions}
            />
          </div>
          <button
            className={styles.secondaryButton}
            type="submit"
            disabled={isLoadingOptions}
          >
            Ara
          </button>
        </form>

        {optionsError ? (
          <div className={styles.listError} role="alert">
            <div>
              <strong>Çalışan seçenekleri yüklenemedi</strong>
              <span>{optionsError.message}</span>
              {optionsError.reference ? (
                <small>Referans: {optionsError.reference}</small>
              ) : null}
            </div>
            <button className={styles.secondaryButton} type="button" onClick={reloadOptions}>
              Yeniden dene
            </button>
          </div>
        ) : isLoadingOptions ? (
          <div className={styles.listLoading} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Çalışanlar hazırlanıyor</strong>
            <span>Atama seçenekleri güvenli tenant kapsamından yükleniyor…</span>
          </div>
        ) : !options || options.employees.length === 0 ? (
          <div className={styles.emptyState}>
            <div aria-hidden="true">Ç</div>
            <h3>Atanabilecek çalışan bulunamadı</h3>
            <p>Çalışan kaydı oluşturulduğunda yapısal ataması burada yönetilebilir.</p>
          </div>
        ) : (
          <>
            <div className={styles.assignmentSelector}>
              <div className={styles.selectorField}>
                <label htmlFor="assignment_employee_selector">Çalışan</label>
                <select
                  id="assignment_employee_selector"
                  value={selectedEmployeeId}
                  onChange={(event) => {
                    setSelectedEmployeeId(event.target.value);
                    setAssignments([]);
                    setHistoryNextCursor(null);
                    setIsLoadingHistory(true);
                    setHistoryError(null);
                    setHistoryPageError(null);
                    setNotice(null);
                    setIsEditorOpen(false);
                  }}
                  disabled={isLoadingHistory}
                >
                  {options.employees.map((employee) => (
                    <option value={employee.id} key={employee.id}>
                      {employee.full_name} · {employee.employee_number}
                      {employee.current_assignment_id ? " · Atanmış" : " · Atama bekliyor"}
                    </option>
                  ))}
                </select>
              </div>
              {selectedEmployee ? (
                <div className={styles.selectedEmployeeSummary}>
                  <span
                    className={styles.statusBadge}
                    data-status={selectedEmployee.status}
                  >
                    <span aria-hidden="true" />
                    {EMPLOYEE_STATUS_LABELS[selectedEmployee.status]}
                  </span>
                  <strong>{selectedEmployee.email ?? "E-posta belirtilmedi"}</strong>
                </div>
              ) : null}
            </div>

            {historyError ? (
              <div className={styles.listError} role="alert">
                <div>
                  <strong>Atama geçmişi yüklenemedi</strong>
                  <span>{historyError.message}</span>
                  {historyError.reference ? (
                    <small>Referans: {historyError.reference}</small>
                  ) : null}
                </div>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={reloadHistory}
                >
                  Yeniden dene
                </button>
              </div>
            ) : isLoadingHistory ? (
              <div className={styles.assignmentHistoryLoading} role="status">
                <span className={styles.spinner} aria-hidden="true" />
                <strong>Atama geçmişi yükleniyor</strong>
              </div>
            ) : assignments.length === 0 ? (
              <div className={styles.assignmentEmptyState}>
                <div>
                  <strong>Henüz yapısal atama yok</strong>
                  <span>
                    Eski departman ve pozisyon metinleri uyumluluk için korunur; yeni atama
                    yapılandırılmış kaydı başlatır.
                  </span>
                </div>
                <button
                  className={styles.primaryButton}
                  type="button"
                  onClick={() => setIsEditorOpen(true)}
                  disabled={!canOpenEditor}
                >
                  İlk atamayı oluştur
                </button>
              </div>
            ) : (
              <>
                <div className={styles.tableScroller}>
                  <table className={`${styles.branchTable} ${styles.assignmentTable}`}>
                    <thead>
                      <tr>
                        <th scope="col">Yapı</th>
                        <th scope="col">Pozisyon</th>
                        <th scope="col">Yönetici</th>
                        <th scope="col">Yürürlük</th>
                        <th scope="col">Değişiklik nedeni</th>
                        <th scope="col">Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignments.map((assignment) => (
                      <tr key={assignment.id}>
                        <td data-label="Yapı">
                          <div className={styles.branchIdentity}>
                            <strong>{assignment.department.name}</strong>
                            <small>
                              {assignment.legal_entity.code} · {assignment.branch.name}
                            </small>
                          </div>
                        </td>
                        <td data-label="Pozisyon">
                          <div className={styles.locationText}>
                            <span>{assignment.position.title}</span>
                            <small>{assignment.position.code}</small>
                          </div>
                        </td>
                        <td data-label="Yönetici">
                          <div className={styles.locationText}>
                            <span>{assignment.manager?.full_name ?? "Yönetici yok"}</span>
                            <small>{assignment.manager?.email ?? "—"}</small>
                          </div>
                        </td>
                        <td data-label="Yürürlük">
                          <div className={styles.locationText}>
                            <span>{formatAssignmentDate(assignment.effective_from)}</span>
                            <small>{formatAssignmentDate(assignment.effective_to)}</small>
                          </div>
                        </td>
                        <td data-label="Değişiklik nedeni">
                          {assignment.change_reason ?? "İlk atama"}
                        </td>
                        <td data-label="Durum">
                          <span
                            className={styles.statusBadge}
                            data-status={
                              assignment.is_current || assignment.id === currentAssignment?.id
                                ? "active"
                                : "archived"
                            }
                          >
                            <span aria-hidden="true" />
                            {assignment.is_current
                              ? "Güncel"
                              : assignment.id === currentAssignment?.id
                                ? "Planlandı"
                                : "Geçmiş"}
                          </span>
                        </td>
                      </tr>
                    ))}
                    </tbody>
                  </table>
                </div>
                {historyPageError ? (
                  <div className={styles.assignmentPageError} role="alert">
                    <span>{historyPageError.message}</span>
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      onClick={loadMoreHistory}
                    >
                      Yeniden dene
                    </button>
                  </div>
                ) : null}
                {historyNextCursor && !historyPageError ? (
                  <div className={styles.assignmentPagination}>
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      onClick={loadMoreHistory}
                      disabled={isLoadingMoreHistory}
                    >
                      {isLoadingMoreHistory
                        ? "Geçmiş yükleniyor…"
                        : "Daha eski atamaları göster"}
                    </button>
                  </div>
                ) : null}
              </>
            )}
          </>
        )}
      </article>

      {isEditorOpen && selectedEmployee ? (
        <EmployeeAssignmentDialog
          key={`${selectedEmployee.id}-${currentAssignment?.id ?? "new"}-${legalEntity.id}`}
          employee={selectedEmployee}
          legalEntity={legalEntity}
          assignment={currentAssignment}
          managers={options?.managers ?? []}
          onClose={() => setIsEditorOpen(false)}
          onSaved={handleSaved}
        />
      ) : null}
    </>
  );
}
