"use client";

import { useEffect, useState } from "react";

import type { TeamMember } from "@/lib/employee-assignments";
import { listMyTeam } from "@/lib/employee-assignments";
import {
  EMPLOYEE_STATUS_LABELS,
  type EmployeeAssignmentErrorPresentation,
  employeeAssignmentErrorPresentation,
  formatAssignmentDate,
} from "@/lib/employee-assignment-presentation";

import styles from "./tenant-shell.module.css";

function employeeName(member: TeamMember): string {
  return `${member.employee.first_name} ${member.employee.last_name}`.trim();
}

export function ManagerTeam() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] =
    useState<EmployeeAssignmentErrorPresentation | null>(null);
  const [pageError, setPageError] =
    useState<EmployeeAssignmentErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let isActive = true;
    void listMyTeam().then(
      (page) => {
        if (!isActive) return;
        setMembers(page.data);
        setNextCursor(page.meta.next_cursor);
        setError(null);
        setPageError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setMembers([]);
        setNextCursor(null);
        setError(employeeAssignmentErrorPresentation(cause, "team"));
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [reloadKey]);

  function reload() {
    setMembers([]);
    setNextCursor(null);
    setIsLoading(true);
    setError(null);
    setPageError(null);
    setReloadKey((key) => key + 1);
  }

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setPageError(null);
    try {
      const page = await listMyTeam(nextCursor);
      setMembers((current) => [...current, ...page.data]);
      setNextCursor(page.meta.next_cursor);
    } catch (cause) {
      setPageError(employeeAssignmentErrorPresentation(cause, "team"));
    } finally {
      setIsLoadingMore(false);
    }
  }

  return (
    <article className={styles.teamCard} aria-labelledby="manager-team-title">
      <header className={styles.teamHeader}>
        <div>
          <span>Yapısal raporlama hattı</span>
          <h2 id="manager-team-title">Ekibim</h2>
          <p>
            Bu liste güncel çalışan atamalarında doğrudan size bağlı ekipten türetilir.
          </p>
        </div>
        <button type="button" onClick={reload} disabled={isLoading}>
          Yenile
        </button>
      </header>

      {error ? (
        <div className={styles.teamError} role="alert">
          <div>
            <strong>Ekip listesi yüklenemedi</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button type="button" onClick={reload}>Yeniden dene</button>
        </div>
      ) : isLoading ? (
        <div className={styles.teamLoading} role="status">
          <span className={styles.teamSpinner} aria-hidden="true" />
          <strong>Ekip atamaları yükleniyor</strong>
        </div>
      ) : members.length === 0 ? (
        <div className={styles.teamEmpty}>
          <span aria-hidden="true">E</span>
          <div>
            <strong>Güncel ekip üyesi yok</strong>
            <p>Size bağlı etkin bir çalışan ataması olduğunda burada görünür.</p>
          </div>
        </div>
      ) : (
        <>
          <div className={styles.teamTableScroller}>
            <table className={styles.teamTable}>
              <thead>
                <tr>
                  <th scope="col">Çalışan</th>
                  <th scope="col">Departman</th>
                  <th scope="col">Pozisyon</th>
                  <th scope="col">Şube</th>
                  <th scope="col">Yürürlük</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.assignment.id}>
                    <td data-label="Çalışan">
                      <strong>{employeeName(member)}</strong>
                      <small>
                        {member.employee.employee_number} · {EMPLOYEE_STATUS_LABELS[member.employee.status]}
                      </small>
                    </td>
                    <td data-label="Departman">
                      <strong>{member.assignment.department.name}</strong>
                      <small>{member.assignment.department.code}</small>
                    </td>
                    <td data-label="Pozisyon">
                      <strong>{member.assignment.position.title}</strong>
                      <small>{member.assignment.position.code}</small>
                    </td>
                    <td data-label="Şube">
                      <strong>{member.assignment.branch.name}</strong>
                      <small>{member.assignment.legal_entity.name}</small>
                    </td>
                    <td data-label="Yürürlük">
                      <strong>{formatAssignmentDate(member.assignment.effective_from)}</strong>
                      <small>Güncel atama</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pageError ? (
            <div className={styles.teamPageError} role="alert">
              <span>{pageError.message}</span>
              <button type="button" onClick={loadMore}>Yeniden dene</button>
            </div>
          ) : null}
          {nextCursor && !pageError ? (
            <div className={styles.teamPagination}>
              <button type="button" onClick={loadMore} disabled={isLoadingMore}>
                {isLoadingMore ? "Ek ekip yükleniyor…" : "Daha fazla ekip üyesi göster"}
              </button>
            </div>
          ) : null}
        </>
      )}
    </article>
  );
}
