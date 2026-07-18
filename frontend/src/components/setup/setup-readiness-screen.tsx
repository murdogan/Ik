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
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import { ApiClientError } from "@/lib/api-client";
import type { AuthUser } from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";
import { isSessionGenerationCurrent } from "@/lib/session";
import {
  readTenantReadiness,
  type TenantReadiness,
  type TenantReadinessItemKey,
  type TenantReadinessItemState,
  type TenantReadinessRemediationRoute,
} from "@/lib/tenant-readiness";

import styles from "./setup-readiness.module.css";

interface ReadinessRequestBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
}

interface ReadinessError {
  message: string;
  reference: string | null;
  authorizationDenied: boolean;
}

interface ReadinessLoadState {
  boundary: ReadinessRequestBoundary;
  readiness: TenantReadiness | null;
  error: ReadinessError | null;
  isLoading: boolean;
}

interface ItemPresentation {
  title: string;
  description: string;
  countLabel?: (count: number) => string;
}

interface RemediationFeatureAccess {
  organizationEnabled: boolean;
  leaveEnabled: boolean;
}

const ITEM_PRESENTATIONS: Record<TenantReadinessItemKey, ItemPresentation> = {
  default_legal_entity: {
    title: "Varsayılan tüzel kişilik",
    description: "Etkin varsayılan tüzel kişilik yapılandırmasını denetler.",
    countLabel: (count) => `${formatCount(count)} etkin varsayılan tüzel kişilik`,
  },
  organization_structure: {
    title: "Organizasyon yapısı",
    description: "Etkin departman ve pozisyon temelini birlikte denetler.",
  },
  active_tenant_administrator: {
    title: "Etkin tenant yöneticisi",
    description: "Tenant yönetimini sürdürebilecek etkin üyeliği denetler.",
    countLabel: (count) => `${formatCount(count)} etkin tenant yöneticisi`,
  },
  employee_master_data: {
    title: "Çalışan ana verisi",
    description: "Kullanıma hazır etkin çalışan kaydı bulunmasını denetler.",
    countLabel: (count) => `${formatCount(count)} etkin çalışan`,
  },
  leave_configuration: {
    title: "İzin yapılandırması",
    description: "İzin türü, tatil takvimi ve geçerli politika temelini denetler.",
  },
  document_configuration: {
    title: "Belge yapılandırması",
    description: "Belge türü ve güvenli çalışma zamanı uygunluğunu denetler.",
    countLabel: (count) => `${formatCount(count)} etkin belge türü`,
  },
  privacy_notice: {
    title: "Gizlilik bildirimi",
    description: "Güncel, etkin ve yayında olan bildirimi denetler.",
    countLabel: (count) => `${formatCount(count)} etkin yayında bildirim`,
  },
  feature_dependencies: {
    title: "Özellik bağımlılıkları",
    description: "Etkin özelliklerin gerekli ön koşullarını denetler.",
  },
  notification_delivery: {
    title: "Bildirim teslimatı",
    description: "Pilot kullanıma uygun teslimat durumunu güvenli biçimde denetler.",
  },
};

const STATE_LABELS: Record<TenantReadinessItemState, string> = {
  ready: "Hazır",
  action_required: "İşlem gerekli",
  not_applicable: "Geçerli değil",
};

const STATE_ICONS: Record<TenantReadinessItemState, string> = {
  ready: "✓",
  action_required: "!",
  not_applicable: "–",
};

function formatCount(value: number): string {
  return value.toLocaleString("tr-TR");
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function isCurrentBoundary(
  expected: ReadinessRequestBoundary,
  current: ReadinessRequestBoundary,
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

function readinessError(cause: unknown): ReadinessError {
  let message = "Kurulum hazırlığı şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let authorizationDenied = false;
  if (!(cause instanceof ApiClientError)) {
    return { message, reference, authorizationDenied };
  }

  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Kurulum hazırlığını görüntülemek için güncel tenant yönetimi yetkiniz bulunmuyor.";
    authorizationDenied = true;
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  } else if (cause.code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir hazırlık yanıtı alındı. Lütfen yeniden deneyin.";
  }
  return { message, reference, authorizationDenied };
}

function canOpenRemediationRoute(
  route: TenantReadinessRemediationRoute,
  user: AuthUser,
  featureAccess: RemediationFeatureAccess,
): boolean {
  switch (route) {
    case "/organization":
      return (
        featureAccess.organizationEnabled &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.readOrganization)
      );
    case "/users":
      return hasPermission(user, AUTHORIZATION_PERMISSIONS.readUsers);
    case "/employees":
      return hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantEmployees);
    case "/leave/admin":
      return (
        featureAccess.leaveEnabled &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantLeave) &&
        hasPermission(user, AUTHORIZATION_PERMISSIONS.manageTenantLeave)
      );
    case "/document-types":
      return hasPermission(user, AUTHORIZATION_PERMISSIONS.manageDocumentTypes);
    case "/privacy/manage":
      return [
        AUTHORIZATION_PERMISSIONS.readTenantPrivacyCompliance,
        AUTHORIZATION_PERMISSIONS.manageTenantPrivacyNotices,
        AUTHORIZATION_PERMISSIONS.manageTenantRetentionPolicies,
      ].some((permission) => hasPermission(user, permission));
  }
}

export function SetupReadinessScreen() {
  const { user, sessionGeneration } = useSession();
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const permissionGranted = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.updateOrganization,
  );
  const boundary = useMemo<ReadinessRequestBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted,
    }),
    [
      permissionGranted,
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
  const [state, setState] = useState<ReadinessLoadState>(() => ({
    boundary,
    readiness: null,
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
    void readTenantReadiness().then(
      (readiness) => {
        if (
          requestId !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          readiness,
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
          readiness: null,
          error: readinessError(cause),
          isLoading: false,
        });
      },
    );

    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const readiness = stateIsCurrent ? state.readiness : null;
  const error = stateIsCurrent ? state.error : null;
  const isLoading = !stateIsCurrent || state.isLoading;
  const featureAccess: RemediationFeatureAccess = {
    organizationEnabled:
      featureStatus === "ready" && isEnabled(TENANT_FEATURES.organization),
    leaveEnabled:
      featureStatus === "ready" && isEnabled(TENANT_FEATURES.leave),
  };

  function reload() {
    requestGeneration.current += 1;
    setState({
      boundary,
      readiness: null,
      error: null,
      isLoading: true,
    });
    setReloadKey((key) => key + 1);
  }

  if (!boundary.permissionGranted) {
    return null;
  }

  return (
    <section
      className={styles.page}
      aria-labelledby="setup-readiness-title"
      aria-busy={isLoading}
    >
      <header className={styles.hero}>
        <div>
          <span>Tenant kurulumu</span>
          <h1 id="setup-readiness-title">Kurulum hazırlığı</h1>
          <p>
            Pilot kullanıma geçmeden önce temel tenant yapılandırmasını güvenli,
            sınırlı kontrollerle izleyin.
          </p>
        </div>
        {readiness ? (
          <div className={styles.overallState} data-state={readiness.overall_state}>
            <span aria-hidden="true">
              {readiness.overall_state === "ready" ? "✓" : "!"}
            </span>
            <div>
              <strong>
                {readiness.overall_state === "ready"
                  ? "Kurulum kontrolleri hazır"
                  : "Tamamlanması gereken adımlar var"}
              </strong>
              <small>
                Son değerlendirme: {" "}
                <time dateTime={readiness.evaluated_at}>
                  {formatTimestamp(readiness.evaluated_at)}
                </time>
              </small>
            </div>
          </div>
        ) : null}
      </header>

      {isLoading ? (
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Kurulum kontrolleri değerlendiriliyor</strong>
            <p>Tenant kapsamındaki güvenli hazırlık özeti yükleniyor…</p>
          </div>
        </div>
      ) : error || !readiness ? (
        <div className={styles.errorState} role="alert">
          <span className={styles.errorIcon} aria-hidden="true">!</span>
          <div>
            <strong>
              {error?.authorizationDenied
                ? "Kurulum alanına erişilemiyor"
                : "Kurulum hazırlığı yüklenemedi"}
            </strong>
            <p>{error?.message ?? "Beklenmeyen bir yanıt alındı."}</p>
            {error?.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button className={styles.retryButton} type="button" onClick={reload}>
            Yeniden dene
          </button>
        </div>
      ) : (
        <section className={styles.checklistPanel} aria-labelledby="setup-checklist-title">
          <header>
            <div>
              <span>Hazırlık görünümü</span>
              <h2 id="setup-checklist-title">Kurulum kontrol listesi</h2>
              <p>
                Kontroller bu tenant için tek değerlendirme anındaki toplu durumu
                gösterir.
              </p>
            </div>
            <div className={styles.itemSummary} aria-label="Kontrol listesi özeti">
              <strong>{readiness.items.filter((item) => item.state === "action_required").length}</strong>
              <span>işlem gerektiren kontrol</span>
            </div>
          </header>

          <ul className={styles.checklist}>
            {readiness.items.map((item) => {
              const presentation = ITEM_PRESENTATIONS[item.key];
              const canOpenRoute =
                item.remediation_route !== null &&
                canOpenRemediationRoute(
                  item.remediation_route,
                  user,
                  featureAccess,
                );
              return (
                <li data-state={item.state} key={item.key}>
                  <span className={styles.stateIcon} aria-hidden="true">
                    {STATE_ICONS[item.state]}
                  </span>
                  <div className={styles.itemContent}>
                    <div className={styles.itemHeading}>
                      <h3>{presentation.title}</h3>
                      <span className={styles.stateBadge}>
                        {STATE_LABELS[item.state]}
                      </span>
                    </div>
                    <p>{presentation.description}</p>
                    {item.count !== null && presentation.countLabel ? (
                      <small>{presentation.countLabel(item.count)}</small>
                    ) : null}
                  </div>
                  {canOpenRoute && item.remediation_route ? (
                    <Link className={styles.remediationLink} href={item.remediation_route}>
                      İlgili alanı aç
                      <span aria-hidden="true">→</span>
                    </Link>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </section>
  );
}
