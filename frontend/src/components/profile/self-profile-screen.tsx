"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { EmployeeStatusBadge } from "@/components/employees/employee-status-badge";
import { formatEmployeeDate } from "@/components/employees/employee-presentation";
import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  invalidSelfEmployeeProfileResponse,
  readOwnEmployeeProfile,
  type SelfEmployeeProfileResult,
} from "@/lib/self-employee-profile";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./self-profile.module.css";

interface SelfProfileBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
}

interface SelfProfileLoadState {
  boundary: SelfProfileBoundary;
  result: SelfEmployeeProfileResult | null;
  error: SelfProfileError | null;
  isLoading: boolean;
}

interface SelfProfileError {
  message: string;
  reference: string | null;
}

const CONTRACT_TYPE_LABELS = {
  indefinite: "Belirsiz süreli",
  fixed_term: "Belirli süreli",
} as const;

const WORK_TYPE_LABELS = {
  full_time: "Tam zamanlı",
  part_time: "Yarı zamanlı",
} as const;

function isCurrentBoundary(
  expected: SelfProfileBoundary,
  current: SelfProfileBoundary,
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

function errorPresentation(cause: unknown): SelfProfileError {
  let message = "Profiliniz şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  if (!(cause instanceof ApiClientError)) return { message, reference };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Profilim alanı mevcut rolleriniz için kullanılamıyor.";
  } else if (cause.status === 404) {
    message = "Profiliniz şu anda kullanıma hazır değil.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference };
}

export function SelfProfileScreen() {
  const { user, sessionGeneration } = useSession();
  const canReadOwn = hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnEmployee);
  const boundary = useMemo<SelfProfileBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canReadOwn,
    }),
    [
      canReadOwn,
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
  const [state, setState] = useState<SelfProfileLoadState>(() => ({
    boundary,
    result: null,
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

    void readOwnEmployeeProfile().then(
      (result) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        if (
          result.availability === "available" &&
          result.membership_id !== requestBoundary.membershipId
        ) {
          setState({
            boundary: requestBoundary,
            result: null,
            error: errorPresentation(invalidSelfEmployeeProfileResponse()),
            isLoading: false,
          });
          return;
        }
        setState({
          boundary: requestBoundary,
          result,
          error: null,
          isLoading: false,
        });
      },
      (cause) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          result: null,
          error: errorPresentation(cause),
          isLoading: false,
        });
      },
    );
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const result = stateIsCurrent ? state.result : null;
  const error = stateIsCurrent ? state.error : null;
  const isLoading = !stateIsCurrent || state.isLoading;

  function reload() {
    setState({
      boundary,
      result: null,
      error: null,
      isLoading: true,
    });
    setReloadKey((key) => key + 1);
  }

  if (isLoading) {
    return (
      <section className={styles.page} aria-busy="true">
        <div className={styles.loadingState} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Profiliniz hazırlanıyor</strong>
            <span>Güvenli çalışan bilgileriniz yükleniyor…</span>
          </div>
        </div>
      </section>
    );
  }

  if (error || !result) {
    return (
      <section className={styles.page} aria-labelledby="self-profile-error-title">
        <div className={styles.errorState} role="alert">
          <span className={styles.stateIcon} aria-hidden="true">!</span>
          <div>
            <h1 id="self-profile-error-title">Profiliniz yüklenemedi</h1>
            <p>{error?.message}</p>
            {error?.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={reload}
          >
            Yeniden dene
          </button>
        </div>
      </section>
    );
  }

  if (result.availability === "unavailable") {
    return (
      <section className={styles.page} aria-labelledby="self-profile-unavailable-title">
        <header className={styles.pageIntro}>
          <span>Çalışan self servisi</span>
          <h1 id="self-profile-unavailable-title">Profilim</h1>
        </header>
        <div className={styles.unavailableState} role="status">
          <span className={styles.stateIcon} aria-hidden="true">P</span>
          <div>
            <h2>Profiliniz henüz kullanıma hazır değil</h2>
            <p>
              İK ekibinizden hesabınız ile çalışan kaydınızın bağlantısını kontrol etmesini
              isteyin. Kayıt hazır olduğunda Profilim alanı burada otomatik olarak açılır.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const { profile } = result;
  const assignment = profile.organization.current_assignment;
  const name = `${profile.core.first_name} ${profile.core.last_name}`.trim();

  return (
    <section className={styles.page} aria-labelledby="self-profile-title">
      <header className={styles.hero}>
        <span className={styles.avatar} aria-hidden="true">
          {profile.core.first_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
        </span>
        <div className={styles.heroIdentity}>
          <span>Çalışan self servisi</span>
          <h1 id="self-profile-title">Profilim</h1>
          <strong>{name}</strong>
          <p>
            {profile.core.employee_number}
            {profile.core.email ? ` · ${profile.core.email}` : ""}
          </p>
        </div>
        <EmployeeStatusBadge status={profile.core.status} />
      </header>

      <div className={styles.sectionGrid}>
        <section className={styles.profileSection} aria-labelledby="self-personal-title">
          <header>
            <span>Kişisel bilgiler</span>
            <h2 id="self-personal-title">Bana ait bilgiler</h2>
          </header>
          <dl className={styles.metadataGrid}>
            <div><dt>Ad</dt><dd>{profile.core.first_name}</dd></div>
            <div><dt>Soyad</dt><dd>{profile.core.last_name}</dd></div>
            <div><dt>Tercih edilen ad</dt><dd>{profile.personal.preferred_name ?? "Belirtilmemiş"}</dd></div>
            <div><dt>Doğum tarihi</dt><dd>{formatEmployeeDate(profile.personal.birth_date)}</dd></div>
            <div><dt>Telefon</dt><dd>{profile.personal.phone ?? "Belirtilmemiş"}</dd></div>
            <div><dt>İş e-postası</dt><dd>{profile.core.email ?? "Eklenmemiş"}</dd></div>
          </dl>
        </section>

        <section className={styles.profileSection} aria-labelledby="self-employment-title">
          <header>
            <span>Çalışma ilişkisi</span>
            <h2 id="self-employment-title">İstihdam bilgilerim</h2>
          </header>
          <dl className={styles.metadataGrid}>
            <div>
              <dt>İşe başlangıç</dt>
              <dd>{formatEmployeeDate(profile.employment.employment_start_date)}</dd>
            </div>
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
          className={`${styles.profileSection} ${styles.organizationSection}`}
          aria-labelledby="self-organization-title"
        >
          <header>
            <span>Güncel organizasyon</span>
            <h2 id="self-organization-title">Organizasyondaki yerim</h2>
          </header>
          {assignment ? (
            <dl className={styles.organizationGrid}>
              <div><dt>Tüzel kişilik</dt><dd>{assignment.legal_entity.name}</dd><small>{assignment.legal_entity.code}</small></div>
              <div><dt>Şube</dt><dd>{assignment.branch.name}</dd><small>{assignment.branch.code}</small></div>
              <div><dt>Departman</dt><dd>{assignment.department.name}</dd><small>{assignment.department.code}</small></div>
              <div><dt>Pozisyon</dt><dd>{assignment.position.title}</dd><small>{assignment.position.code}</small></div>
              <div><dt>Yönetici</dt><dd>{assignment.manager?.full_name ?? "Belirtilmemiş"}</dd></div>
            </dl>
          ) : (
            <div className={styles.organizationEmpty}>
              <span aria-hidden="true">O</span>
              <div>
                <strong>Güncel organizasyon ataması bulunmuyor</strong>
                <p>Atamanız tamamlandığında organizasyon bilgileriniz burada görünür.</p>
              </div>
            </div>
          )}
        </section>
      </div>

      <p className={styles.readOnlyNote}>
        Bu görünüm salt okunurdur. Bilgilerinizde bir düzeltme gerekiyorsa İK ekibinizle iletişime
        geçin.
      </p>
    </section>
  );
}
