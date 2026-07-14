"use client";

import Link from "next/link";
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { formatEmployeeDate } from "@/components/employees/employee-presentation";
import { EmployeeStatusBadge } from "@/components/employees/employee-status-badge";
import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { isSessionGenerationCurrent } from "@/lib/session";
import {
  readTeamMemberProfile,
  type TeamMemberProfile,
} from "@/lib/team-member-profile";

import styles from "./team-member-profile.module.css";

interface TeamProfileRequestBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
  employeeId: string;
}

interface TeamProfileError {
  message: string;
  reference: string | null;
}

interface TeamProfileLoadState {
  boundary: TeamProfileRequestBoundary;
  profile: TeamMemberProfile | null;
  error: TeamProfileError | null;
  isLoading: boolean;
}

const CONTRACT_TYPE_LABELS = {
  indefinite: "Belirsiz süreli",
  fixed_term: "Belirli süreli",
} as const;

const WORK_TYPE_LABELS = {
  full_time: "Tam zamanlı",
  part_time: "Yarı zamanlı",
} as const;

function isCurrentRequest(
  expected: TeamProfileRequestBoundary,
  current: TeamProfileRequestBoundary,
): boolean {
  return (
    isSessionGenerationCurrent(expected.sessionGeneration) &&
    expected.sessionGeneration === current.sessionGeneration &&
    expected.userId === current.userId &&
    expected.membershipId === current.membershipId &&
    expected.tenantId === current.tenantId &&
    expected.permissionVersion === current.permissionVersion &&
    expected.permissionGranted === current.permissionGranted &&
    expected.employeeId === current.employeeId
  );
}

function errorPresentation(cause: unknown): TeamProfileError {
  let message = "Ekip üyesi profili şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  if (!(cause instanceof ApiClientError)) return { message, reference };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403 || cause.status === 404) {
    message =
      "Bu ekip üyesi profili kullanılamıyor. Güncel ekip listenize dönüp yeniden deneyin.";
  } else if (cause.status === 422) {
    message = "Ekip profili bağlantısı geçerli değil. Güncel ekip listenize dönün.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference };
}

function employeeName(profile: TeamMemberProfile): string {
  return `${profile.core.first_name} ${profile.core.last_name}`.trim();
}

export function TeamMemberProfileScreen({ employeeId }: { employeeId: string }) {
  const { user, sessionGeneration } = useSession();
  const canReadTeam = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTeamEmployees,
  );
  const boundary = useMemo<TeamProfileRequestBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canReadTeam,
      employeeId,
    }),
    [
      canReadTeam,
      employeeId,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const latestBoundary = useRef(boundary);
  const requestGeneration = useRef(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<TeamProfileLoadState>(() => ({
    boundary,
    profile: null,
    error: null,
    isLoading: true,
  }));

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary]);

  useEffect(() => {
    if (!boundary.permissionGranted) {
      return () => {
        requestGeneration.current += 1;
      };
    }
    const requestId = ++requestGeneration.current;
    const requestBoundary = boundary;
    void readTeamMemberProfile(requestBoundary.employeeId).then(
      (profile) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentRequest(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          profile,
          error: null,
          isLoading: false,
        });
      },
      (cause) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentRequest(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          profile: null,
          error: errorPresentation(cause),
          isLoading: false,
        });
      },
    );
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentRequest(state.boundary, boundary);
  const profile = stateIsCurrent ? state.profile : null;
  const error = stateIsCurrent ? state.error : null;
  const isLoading = !stateIsCurrent || state.isLoading;

  function reload() {
    setState({
      boundary,
      profile: null,
      error: null,
      isLoading: true,
    });
    setReloadKey((key) => key + 1);
  }

  if (!boundary.permissionGranted) return null;

  if (isLoading) {
    return (
      <section className={styles.page} aria-busy="true">
        <Link className={styles.backLink} href="/dashboard#manager-team-title">
          ← Ekibime dön
        </Link>
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Ekip profili hazırlanıyor</strong>
            <span>Güvenli iş ve organizasyon bilgileri yükleniyor…</span>
          </div>
        </div>
      </section>
    );
  }

  if (error || !profile) {
    return (
      <section className={styles.page} aria-labelledby="team-profile-error-title">
        <Link className={styles.backLink} href="/dashboard#manager-team-title">
          ← Ekibime dön
        </Link>
        <div className={styles.errorState} role="alert">
          <span className={styles.stateIcon} aria-hidden="true">!</span>
          <div>
            <h1 id="team-profile-error-title">Ekip profili yüklenemedi</h1>
            <p>{error?.message}</p>
            {error?.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button className={styles.secondaryButton} type="button" onClick={reload}>
            Yeniden dene
          </button>
        </div>
      </section>
    );
  }

  const assignment = profile.organization.current_assignment;
  const preferredName =
    profile.core.preferred_name &&
    profile.core.preferred_name !== profile.core.first_name
      ? profile.core.preferred_name
      : null;

  return (
    <section className={styles.page} aria-labelledby="team-profile-title">
      <Link className={styles.backLink} href="/dashboard#manager-team-title">
        ← Ekibime dön
      </Link>

      <header className={styles.hero}>
        <span className={styles.avatar} aria-hidden="true">
          {profile.core.first_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
        </span>
        <div className={styles.heroIdentity}>
          <span>Doğrudan ekip görünümü</span>
          <h1 id="team-profile-title">{employeeName(profile)}</h1>
          <p>
            {preferredName ? `${preferredName} · ` : ""}
            {profile.core.employee_number}
            {profile.core.email ? ` · ${profile.core.email}` : ""}
          </p>
        </div>
        <EmployeeStatusBadge status={profile.core.status} />
      </header>

      <div className={styles.sectionGrid}>
        <section className={styles.profileSection} aria-labelledby="team-work-title">
          <header>
            <span>Çalışma ilişkisi</span>
            <h2 id="team-work-title">İş bilgileri</h2>
          </header>
          <dl className={styles.metadataGrid}>
            <div><dt>Çalışan numarası</dt><dd>{profile.core.employee_number}</dd></div>
            <div><dt>İş e-postası</dt><dd>{profile.core.email ?? "Eklenmemiş"}</dd></div>
            <div><dt>Tercih edilen ad</dt><dd>{profile.core.preferred_name ?? "Belirtilmemiş"}</dd></div>
            <div><dt>İşe başlangıç</dt><dd>{formatEmployeeDate(profile.employment.employment_start_date)}</dd></div>
            <div>
              <dt>Sözleşme türü</dt>
              <dd>
                {profile.employment.contract_type
                  ? CONTRACT_TYPE_LABELS[profile.employment.contract_type]
                  : "Belirtilmemiş"}
              </dd>
            </div>
            <div>
              <dt>Çalışma türü</dt>
              <dd>
                {profile.employment.work_type
                  ? WORK_TYPE_LABELS[profile.employment.work_type]
                  : "Belirtilmemiş"}
              </dd>
            </div>
          </dl>
        </section>

        <section
          className={styles.profileSection}
          aria-labelledby="team-organization-title"
        >
          <header>
            <span>Güncel ekip yapısı</span>
            <h2 id="team-organization-title">Organizasyon</h2>
          </header>
          {assignment ? (
            <dl className={styles.organizationGrid}>
              <div><dt>Tüzel kişilik</dt><dd>{assignment.legal_entity.name}</dd><small>{assignment.legal_entity.code}</small></div>
              <div><dt>Şube</dt><dd>{assignment.branch.name}</dd><small>{assignment.branch.code}</small></div>
              <div><dt>Departman</dt><dd>{assignment.department.name}</dd><small>{assignment.department.code}</small></div>
              <div><dt>Pozisyon</dt><dd>{assignment.position.title}</dd><small>{assignment.position.code}</small></div>
              <div><dt>Yönetici</dt><dd>{assignment.manager?.full_name ?? "Belirtilmemiş"}</dd></div>
              <div><dt>Atama başlangıcı</dt><dd>{formatEmployeeDate(assignment.effective_from)}</dd></div>
            </dl>
          ) : (
            <div className={styles.emptyState} role="status">
              <span className={styles.stateIcon} aria-hidden="true">O</span>
              <div>
                <strong>Güncel organizasyon ataması bulunmuyor</strong>
                <p>Ekip yapısı güncellendiğinde organizasyon bilgileri burada görünür.</p>
              </div>
            </div>
          )}
        </section>
      </div>

      <p className={styles.policyNote} role="note">
        Bu salt okunur görünüm, yönetici ekip politikasının izin verdiği güncel iş ve
        organizasyon alanlarıyla sınırlıdır.
      </p>
    </section>
  );
}
