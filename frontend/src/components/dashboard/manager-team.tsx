"use client";

import Link from "next/link";
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import type { TeamMember } from "@/lib/employee-assignments";
import { listMyTeam } from "@/lib/employee-assignments";
import {
  EMPLOYEE_STATUS_LABELS,
  type EmployeeAssignmentErrorPresentation,
  employeeAssignmentErrorPresentation,
  formatAssignmentDate,
} from "@/lib/employee-assignment-presentation";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./tenant-shell.module.css";

interface TeamRequestBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
}

interface TeamLoadState {
  boundary: TeamRequestBoundary;
  members: TeamMember[];
  nextCursor: string | null;
  isLoading: boolean;
  isLoadingMore: boolean;
  error: EmployeeAssignmentErrorPresentation | null;
  pageError: EmployeeAssignmentErrorPresentation | null;
}

function isCurrentBoundary(
  expected: TeamRequestBoundary,
  current: TeamRequestBoundary,
): boolean {
  return (
    isSessionGenerationCurrent(expected.sessionGeneration) &&
    expected.sessionGeneration === current.sessionGeneration &&
    expected.userId === current.userId &&
    expected.membershipId === current.membershipId &&
    expected.tenantId === current.tenantId &&
    expected.permissionVersion === current.permissionVersion &&
    expected.permissionGranted === current.permissionGranted
  );
}

function appendUniqueMembers(
  current: TeamMember[],
  incoming: TeamMember[],
): TeamMember[] {
  const membersByEmployee = new Map(
    current.map((member) => [member.employee.id, member]),
  );
  for (const member of incoming) {
    membersByEmployee.set(member.employee.id, member);
  }
  return [...membersByEmployee.values()];
}

function employeeName(member: TeamMember): string {
  return `${member.employee.first_name} ${member.employee.last_name}`.trim();
}

export function ManagerTeam() {
  const { user, sessionGeneration } = useSession();
  const canReadTeam = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTeamEmployees,
  );
  const boundary = useMemo<TeamRequestBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canReadTeam,
    }),
    [
      canReadTeam,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const latestBoundary = useRef(boundary);
  const initialRequestGeneration = useRef(0);
  const pageRequestGeneration = useRef(0);
  const [state, setState] = useState<TeamLoadState>(() => ({
    boundary,
    members: [],
    nextCursor: null,
    isLoading: true,
    isLoadingMore: false,
    error: null,
    pageError: null,
  }));
  const [reloadKey, setReloadKey] = useState(0);

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => {
      initialRequestGeneration.current += 1;
      pageRequestGeneration.current += 1;
    };
  }, [boundary]);

  useEffect(() => {
    if (!boundary.permissionGranted) {
      return () => {
        initialRequestGeneration.current += 1;
        pageRequestGeneration.current += 1;
      };
    }
    const requestId = ++initialRequestGeneration.current;
    const requestBoundary = boundary;
    pageRequestGeneration.current += 1;
    setState({
      boundary: requestBoundary,
      members: [],
      nextCursor: null,
      isLoading: true,
      isLoadingMore: false,
      error: null,
      pageError: null,
    });
    void listMyTeam().then(
      (page) => {
        if (
          requestId !== initialRequestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          members: page.data,
          nextCursor: page.meta.next_cursor,
          isLoading: false,
          isLoadingMore: false,
          error: null,
          pageError: null,
        });
      },
      (cause) => {
        if (
          requestId !== initialRequestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          members: [],
          nextCursor: null,
          isLoading: false,
          isLoadingMore: false,
          error: employeeAssignmentErrorPresentation(cause, "team"),
          pageError: null,
        });
      },
    );
    return () => {
      initialRequestGeneration.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const members = stateIsCurrent ? state.members : [];
  const nextCursor = stateIsCurrent ? state.nextCursor : null;
  const error = stateIsCurrent ? state.error : null;
  const pageError = stateIsCurrent ? state.pageError : null;
  const isLoading = !stateIsCurrent || state.isLoading;
  const isLoadingMore = stateIsCurrent && state.isLoadingMore;

  function reload() {
    pageRequestGeneration.current += 1;
    setState({
      boundary,
      members: [],
      nextCursor: null,
      isLoading: true,
      isLoadingMore: false,
      error: null,
      pageError: null,
    });
    setReloadKey((key) => key + 1);
  }

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    const requestBoundary = boundary;
    const requestCursor = nextCursor;
    const requestId = ++pageRequestGeneration.current;
    setState((current) =>
      isCurrentBoundary(current.boundary, requestBoundary)
        ? { ...current, isLoadingMore: true, pageError: null }
        : current,
    );
    try {
      const page = await listMyTeam(requestCursor);
      if (
        requestId !== pageRequestGeneration.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setState((current) =>
        isCurrentBoundary(current.boundary, requestBoundary)
          ? {
              ...current,
              members: appendUniqueMembers(current.members, page.data),
              nextCursor: page.meta.next_cursor,
              pageError: null,
            }
          : current,
      );
    } catch (cause) {
      if (
        requestId === pageRequestGeneration.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setState((current) =>
          isCurrentBoundary(current.boundary, requestBoundary)
            ? {
                ...current,
                pageError: employeeAssignmentErrorPresentation(cause, "team"),
              }
            : current,
        );
      }
    } finally {
      if (
        requestId === pageRequestGeneration.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setState((current) =>
          isCurrentBoundary(current.boundary, requestBoundary)
            ? { ...current, isLoadingMore: false }
            : current,
        );
      }
    }
  }

  if (!boundary.permissionGranted) return null;

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
            <table className={styles.teamTable} aria-label="Güncel doğrudan ekip">
              <thead>
                <tr>
                  <th scope="col">Çalışan</th>
                  <th scope="col">Departman</th>
                  <th scope="col">Pozisyon</th>
                  <th scope="col">Şube</th>
                  <th scope="col">Yürürlük</th>
                  <th scope="col">Profil</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.employee.id}>
                    <td data-label="Çalışan">
                      <strong>{employeeName(member)}</strong>
                      <small>
                        {member.employee.preferred_name &&
                        member.employee.preferred_name !== member.employee.first_name
                          ? `${member.employee.preferred_name} · `
                          : ""}
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
                    <td data-label="Profil">
                      <Link
                        className={styles.teamProfileLink}
                        href={`/team/${encodeURIComponent(member.employee.id)}`}
                        aria-label={`${employeeName(member)} güvenli ekip profilini aç`}
                      >
                        Profili aç <span aria-hidden="true">→</span>
                      </Link>
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
