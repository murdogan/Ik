"use client";

import Link from "next/link";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import type { EmployeeAssignment } from "@/lib/employee-assignments";
import {
  type EmployeeActivityKind,
  type EmployeeProfileChangeStatus,
  type EmployeeProfileInsights,
  readEmployeeProfileInsights,
} from "@/lib/employee-profile-insights";
import {
  archiveEmployee,
  EMPLOYEE_TERMINATION_REASONS,
  transitionEmployeeLifecycle,
  type EmployeeLifecycleTransitionRequest,
  type EmployeeTerminationReason,
} from "@/lib/employee-lifecycle";
import {
  type EmployeeEmploymentProfile,
  type EmployeeEmploymentProfileUpdate,
  type EmployeeEmploymentProfileUpdateResult,
  type EmployeeContractType,
  type EmployeePersonalProfile,
  type EmployeePersonalProfileUpdate,
  type EmployeePersonalProfileUpdateResult,
  type EmployeeProfile,
  type EmployeeProfileCore,
  type EmployeeWorkType,
  readEmployeeProfile,
  updateEmployeeEmploymentProfile,
  updateEmployeePersonalProfile,
} from "@/lib/employee-profile";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { isSessionGenerationCurrent } from "@/lib/session";

import { formatEmployeeDate } from "./employee-presentation";
import { EmployeeAccountLinkCard } from "./employee-account-link-card";
import { EmployeeStatusBadge } from "./employee-status-badge";
import styles from "./employees.module.css";

type ProfileTab = "summary" | "personal" | "employment" | "organization";
type ProfileAction = "read" | "personal" | "employment";
type LifecycleDialogAction = "active" | "on_leave" | "terminated" | "archive";

interface ProfileErrorPresentation {
  message: string;
  reference: string | null;
  conflict: boolean;
}

interface ProfileRequestBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
  employeeId: string;
}

interface ProfileLoadState {
  boundary: ProfileRequestBoundary;
  profile: EmployeeProfile | null;
  error: ProfileErrorPresentation | null;
  isLoading: boolean;
}

interface InsightsErrorPresentation {
  message: string;
  reference: string | null;
}

interface InsightsLoadState {
  boundary: ProfileRequestBoundary;
  insights: EmployeeProfileInsights | null;
  error: InsightsErrorPresentation | null;
  loadMoreError: InsightsErrorPresentation | null;
  isLoading: boolean;
  isLoadingMore: boolean;
}

const PROFILE_TABS: ReadonlyArray<{ id: ProfileTab; label: string }> = [
  { id: "summary", label: "Özet" },
  { id: "personal", label: "Kişisel" },
  { id: "employment", label: "İstihdam" },
  { id: "organization", label: "Organizasyon" },
];

const CONTRACT_TYPE_LABELS = {
  indefinite: "Belirsiz süreli",
  fixed_term: "Belirli süreli",
} as const;

const WORK_TYPE_LABELS = {
  full_time: "Tam zamanlı",
  part_time: "Yarı zamanlı",
} as const;

const TERMINATION_REASON_LABELS: Record<EmployeeTerminationReason, string> = {
  resignation: "İstifa",
  dismissal: "İşveren feshi",
  retirement: "Emeklilik",
  contract_end: "Sözleşme sonu",
  other: "Diğer",
};

const INSIGHTS_PAGE_LIMIT = 20;

const PROFILE_CHANGE_STATUS_LABELS: Record<
  EmployeeProfileChangeStatus,
  string
> = {
  submitted: "Gönderildi",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
};

const ACTIVITY_KIND_LABELS: Record<EmployeeActivityKind, string> = {
  "employee.created": "Çalışan kaydı oluşturuldu",
  "employee.updated": "Çalışan ana bilgileri güncellendi",
  "employee.lifecycle.changed": "Çalışma durumu değiştirildi",
  "employee.archived": "Çalışan kaydı arşivlendi",
  "employee.personal_profile.updated": "Kişisel bilgiler güncellendi",
  "employee.employment_profile.updated": "İstihdam bilgileri güncellendi",
  "employee.account_link.changed": "Çalışan hesabı bağlantısı değiştirildi",
  "employee.profile_change_request.submitted":
    "Profil değişikliği talebi gönderildi",
  "employee.profile_change_request.approved":
    "Profil değişikliği talebi onaylandı",
  "employee.profile_change_request.rejected":
    "Profil değişikliği talebi reddedildi",
  "employee.profile_change_request.cancelled":
    "Profil değişikliği talebi iptal edildi",
  "employee.assignment.changed": "Yapısal atama değiştirildi",
  "reporting_line.changed": "Yönetici ilişkisi değiştirildi",
};

const INSIGHT_NUMBER_FORMAT = new Intl.NumberFormat("tr-TR", {
  maximumFractionDigits: 2,
});

const ACTIVITY_DATE_TIME_FORMAT = new Intl.DateTimeFormat("tr-TR", {
  dateStyle: "medium",
  timeStyle: "short",
});

function isCurrentProfileRequest(
  expected: ProfileRequestBoundary,
  current: ProfileRequestBoundary,
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

function profileRequestBoundaryKey(boundary: ProfileRequestBoundary): string {
  return JSON.stringify(boundary);
}

function fullName(core: EmployeeProfileCore): string {
  return `${core.first_name} ${core.last_name}`.trim();
}

function optionalText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function profileErrorPresentation(
  cause: unknown,
  action: ProfileAction,
): ProfileErrorPresentation {
  let message =
    action === "read"
      ? "Çalışan profili şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : action === "personal"
        ? "Kişisel bilgiler şu anda kaydedilemiyor. Lütfen yeniden deneyin."
        : "İstihdam bilgileri şu anda kaydedilemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;

  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message =
      action === "read"
        ? "Tenant çalışan kayıtlarını görüntüleme yetkiniz bulunmuyor."
        : "Bu çalışan profilini güncellemek için gerekli İK yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Çalışan bulunamadı veya artık bu çalışma alanında değil.";
  } else if (cause.status === 409 && cause.code === "concurrent_write_conflict") {
    message =
      "Bu bölüm siz düzenlerken değişti. Güncel veriyi yükleyip değişikliklerinizi yeniden uygulayın.";
    conflict = true;
  } else if (
    cause.status === 409 &&
    (cause.code === "employee_email_conflict" ||
      cause.code === "employee_work_email_conflict")
  ) {
    message = "Bu iş e-postası çalışma alanında başka bir çalışanda kullanılıyor.";
  } else if (cause.status === 409) {
    message = "Çalışan kaydı mevcut verilerle çakışıyor. Güncel veriyi yükleyin.";
    conflict = true;
  } else if (cause.status === 422) {
    message =
      action === "personal"
        ? "Ad, soyad, iş e-postası, doğum tarihi ve telefon alanlarını kontrol edin."
        : action === "employment"
          ? "Başlangıç tarihi, sözleşme türü ve çalışma türünü kontrol edin."
          : "Çalışan bağlantısı geçerli değil. Dizine dönüp kaydı yeniden açın.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference, conflict };
}

function insightsErrorPresentation(
  cause: unknown,
  action: "initial" | "load_more",
): InsightsErrorPresentation {
  let message =
    action === "initial"
      ? "Güncel özet ve etkinlikler şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : "Daha eski etkinlikler şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;

  if (!(cause instanceof ApiClientError)) return { message, reference };
  reference = cause.correlationId;
  if (cause.code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir yanıt alındı. Lütfen yeniden deneyin.";
  } else if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu çalışan özetini görüntüleme yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Çalışan bulunamadı veya artık bu çalışma alanında değil.";
  } else if (cause.status === 422 && action === "load_more") {
    message = "Etkinlik devam bağlantısı artık geçerli değil. Lütfen yeniden deneyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference };
}

function formatInsightNumber(value: number): string {
  return INSIGHT_NUMBER_FORMAT.format(Object.is(value, -0) ? 0 : value);
}

function formatActivityDateTime(value: string): string {
  return ACTIVITY_DATE_TIME_FORMAT.format(new Date(value));
}

function lifecycleErrorPresentation(cause: unknown): ProfileErrorPresentation {
  let message = "Yaşam döngüsü işlemi tamamlanamadı. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu yaşam döngüsü işlemi için gerekli İK yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Çalışan bulunamadı veya bu çalışma alanında değil.";
  } else if (cause.code === "employee_open_process_conflict") {
    message =
      "Gönderilmiş profil değişikliği talebi sonuçlandırılmadan çalışan sonlandırılamaz veya arşivlenemez.";
    conflict = true;
  } else if (cause.code === "concurrent_write_conflict") {
    message = "Çalışan kaydı değişti. Güncel veriyi yükleyip işlemi yeniden başlatın.";
    conflict = true;
  } else if (cause.status === 409) {
    message = "Bu işlem çalışanın güncel yaşam döngüsü durumunda uygulanamaz.";
    conflict = true;
  } else if (cause.status === 422) {
    message = "Yürürlük tarihi ve sonlandırma nedenini kontrol edin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference, conflict };
}

function localToday(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function LifecycleCard({
  profile,
  editable,
  requestBoundary,
  onReload,
}: {
  profile: EmployeeProfile;
  editable: boolean;
  requestBoundary: ProfileRequestBoundary;
  onReload: () => void;
}) {
  const requestGeneration = useRef(0);
  const latestRequestBoundary = useRef(requestBoundary);
  const savingLock = useRef(false);
  const [action, setAction] = useState<LifecycleDialogAction | null>(null);
  const [effectiveDate, setEffectiveDate] = useState(
    profile.employment.employment_end_date ?? localToday(),
  );
  const [terminationReason, setTerminationReason] =
    useState<EmployeeTerminationReason>("resignation");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ProfileErrorPresentation | null>(null);

  useLayoutEffect(() => {
    latestRequestBoundary.current = requestBoundary;
    return () => {
      requestGeneration.current += 1;
      savingLock.current = false;
    };
  }, [requestBoundary]);

  useEffect(() => {
    if (action === null) return;
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape" && !savingLock.current) setAction(null);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [action]);

  function openAction(nextAction: LifecycleDialogAction) {
    if (!editable) return;
    setError(null);
    if (nextAction === "terminated") {
      setEffectiveDate(profile.employment.employment_end_date ?? localToday());
      setTerminationReason(profile.employment.termination_reason ?? "resignation");
    }
    setAction(nextAction);
  }

  function closeAction() {
    if (!savingLock.current) {
      setError(null);
      setAction(null);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const currentAction = action;
    const boundary = requestBoundary;
    if (
      currentAction === null ||
      !editable ||
      !boundary.permissionGranted ||
      savingLock.current
    ) {
      return;
    }
    if (
      currentAction === "terminated" &&
      effectiveDate < profile.employment.employment_start_date
    ) {
      setError({
        message: "Son çalışma tarihi işe başlangıç tarihinden önce olamaz.",
        reference: null,
        conflict: false,
      });
      return;
    }

    savingLock.current = true;
    const generation = ++requestGeneration.current;
    setIsSaving(true);
    setError(null);
    try {
      if (currentAction === "archive") {
        await archiveEmployee(boundary.employeeId, profile.core.employee_version);
      } else {
        const payload: EmployeeLifecycleTransitionRequest =
          currentAction === "terminated"
            ? {
                target_status: "terminated",
                expected_version: profile.core.employee_version,
                effective_date: effectiveDate,
                termination_reason: terminationReason,
              }
            : {
                target_status: currentAction,
                expected_version: profile.core.employee_version,
              };
        await transitionEmployeeLifecycle(boundary.employeeId, payload);
      }
      if (
        generation !== requestGeneration.current ||
        !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        return;
      }
      setAction(null);
      onReload();
    } catch (cause) {
      if (
        generation === requestGeneration.current &&
        isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        setError(lifecycleErrorPresentation(cause));
      }
    } finally {
      if (
        generation === requestGeneration.current &&
        isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        savingLock.current = false;
        setIsSaving(false);
      }
    }
  }

  const archived = profile.core.archived_at !== null;
  const terminated = profile.core.status === "terminated";
  const dialogTitle =
    action === "archive"
      ? "Çalışanı arşivle"
      : action === "terminated"
        ? "Çalışmayı sonlandır"
        : action === "on_leave"
          ? "İzin durumuna geçir"
          : "Aktif duruma döndür";

  return (
    <>
      <section className={styles.lifecycleCard} aria-labelledby="employee-lifecycle-title">
        <header>
          <div>
            <span>Yaşam döngüsü</span>
            <h2 id="employee-lifecycle-title">Çalışma durumu</h2>
            <p>Durum geçişleri, sonlandırma ve arşiv işlemleri bu kontrollü alandan yürütülür.</p>
          </div>
          <EmployeeStatusBadge status={profile.core.status} />
        </header>
        <dl className={styles.lifecycleMetadata}>
          <div><dt>İşe başlangıç</dt><dd>{formatEmployeeDate(profile.employment.employment_start_date)}</dd></div>
          <div><dt>Çalışma sonu</dt><dd>{formatEmployeeDate(profile.employment.employment_end_date)}</dd></div>
          <div><dt>Sonlandırma nedeni</dt><dd>{profile.employment.termination_reason ? TERMINATION_REASON_LABELS[profile.employment.termination_reason] : "—"}</dd></div>
          <div><dt>Kayıt durumu</dt><dd>{archived ? `Arşivlendi · ${formatEmployeeDate(profile.core.archived_at)}` : "Dizinde"}</dd></div>
        </dl>
        {editable ? (
          <div className={styles.lifecycleActions}>
            {profile.core.status === "active" ? (
              <button className={styles.secondaryButton} type="button" onClick={() => openAction("on_leave")}>İzne ayır</button>
            ) : null}
            {profile.core.status === "on_leave" ? (
              <button className={styles.secondaryButton} type="button" onClick={() => openAction("active")}>Aktife döndür</button>
            ) : null}
            {!terminated ? (
              <button className={styles.dangerButton} type="button" onClick={() => openAction("terminated")}>Çalışmayı sonlandır</button>
            ) : null}
            {terminated && !archived ? (
              <button className={styles.dangerButton} type="button" onClick={() => openAction("archive")}>Arşivle</button>
            ) : null}
          </div>
        ) : (
          <div className={styles.lifecycleReadOnly}>Bu kayıt yaşam döngüsü işlemleri için salt okunur.</div>
        )}
      </section>

      {action !== null ? (
        <div className={styles.dialogBackdrop} role="presentation">
          <div className={`${styles.detailDialog} ${styles.lifecycleDialog}`} role="dialog" aria-modal="true" aria-labelledby="lifecycle-dialog-title">
            <header className={styles.dialogHeader}>
              <div><span>Onay gerekli</span><h2 id="lifecycle-dialog-title">{dialogTitle}</h2></div>
              <button className={styles.iconButton} type="button" onClick={closeAction} disabled={isSaving} aria-label="Pencereyi kapat">×</button>
            </header>
            <form className={styles.dialogBody} onSubmit={submit}>
              <div className={styles.lifecycleConfirmation}>
                {action === "terminated" ? (
                  <>
                    <p>Bu işlem açık atamayı seçilen sınırda kapatır, bağlı tenant üyeliğini devre dışı bırakır ve aktif oturumlarını iptal eder.</p>
                    <div className={styles.formGrid}>
                      <div className={styles.formField}>
                        <label htmlFor="termination_effective_date">Son çalışma tarihi</label>
                        <input id="termination_effective_date" type="date" min={profile.employment.employment_start_date} value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} required disabled={isSaving} autoFocus />
                      </div>
                      <div className={styles.formField}>
                        <label htmlFor="termination_reason">Sonlandırma nedeni</label>
                        <select id="termination_reason" value={terminationReason} onChange={(event) => setTerminationReason(event.target.value as EmployeeTerminationReason)} required disabled={isSaving}>
                          {EMPLOYEE_TERMINATION_REASONS.map((reason) => <option value={reason} key={reason}>{TERMINATION_REASON_LABELS[reason]}</option>)}
                        </select>
                      </div>
                    </div>
                  </>
                ) : action === "archive" ? (
                  <p>Çalışan normal dizinden kaldırılır. Profil, hesap bağlantısı, atama ve denetim geçmişi korunur; doğrudan Employee 360 görünümü salt okunur kalır.</p>
                ) : action === "on_leave" ? (
                  <p>Çalışanın durumu izinli olarak değiştirilecek. Hesap bağlantısı ve atama geçmişi korunur.</p>
                ) : (
                  <p>Çalışan aktif duruma döndürülecek. Sonlandırma alanları bu geçişte boş tutulur.</p>
                )}
                {error ? (
                  <div className={styles.profileErrorAlert} role="alert">
                    <div><strong>İşlem tamamlanamadı</strong><span>{error.message}</span>{error.reference ? <small>Referans: {error.reference}</small> : null}</div>
                    {error.conflict ? <button className={styles.secondaryButton} type="button" onClick={onReload}>Güncel veriyi yükle</button> : null}
                  </div>
                ) : null}
                <div className={styles.dialogActions}>
                  <button className={styles.secondaryButton} type="button" onClick={closeAction} disabled={isSaving}>Vazgeç</button>
                  <button className={action === "active" || action === "on_leave" ? styles.primaryButton : styles.dangerButton} type="submit" disabled={isSaving} autoFocus={action !== "terminated"}>
                    {isSaving ? "İşlem uygulanıyor…" : dialogTitle}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}

function EmployeeInsightsOverview({
  requestBoundary,
}: {
  requestBoundary: ProfileRequestBoundary;
}) {
  const latestRequestBoundary = useRef(requestBoundary);
  const initialRequestGeneration = useRef(0);
  const pageRequestGeneration = useRef(0);
  const loadMoreLock = useRef(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<InsightsLoadState>(() => ({
    boundary: requestBoundary,
    insights: null,
    error: null,
    loadMoreError: null,
    isLoading: true,
    isLoadingMore: false,
  }));

  useLayoutEffect(() => {
    latestRequestBoundary.current = requestBoundary;
    return () => {
      initialRequestGeneration.current += 1;
      pageRequestGeneration.current += 1;
      loadMoreLock.current = false;
    };
  }, [requestBoundary]);

  useEffect(() => {
    const generation = ++initialRequestGeneration.current;
    pageRequestGeneration.current += 1;
    loadMoreLock.current = false;
    const boundary = requestBoundary;
    if (!boundary.permissionGranted) {
      return () => {
        initialRequestGeneration.current += 1;
        pageRequestGeneration.current += 1;
      };
    }

    void readEmployeeProfileInsights(boundary.employeeId, {
      limit: INSIGHTS_PAGE_LIMIT,
    }).then(
      (insights) => {
        if (
          generation !== initialRequestGeneration.current ||
          !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary,
          insights,
          error: null,
          loadMoreError: null,
          isLoading: false,
          isLoadingMore: false,
        });
      },
      (cause) => {
        if (
          generation !== initialRequestGeneration.current ||
          !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary,
          insights: null,
          error: insightsErrorPresentation(cause, "initial"),
          loadMoreError: null,
          isLoading: false,
          isLoadingMore: false,
        });
      },
    );

    return () => {
      initialRequestGeneration.current += 1;
      pageRequestGeneration.current += 1;
      loadMoreLock.current = false;
    };
  }, [reloadKey, requestBoundary]);

  const stateIsCurrent = isCurrentProfileRequest(
    state.boundary,
    requestBoundary,
  );
  const insights = stateIsCurrent ? state.insights : null;
  const error = stateIsCurrent ? state.error : null;
  const loadMoreError = stateIsCurrent ? state.loadMoreError : null;
  const isLoading = !stateIsCurrent || state.isLoading;
  const isLoadingMore = stateIsCurrent && state.isLoadingMore;

  function retryInitialLoad() {
    initialRequestGeneration.current += 1;
    pageRequestGeneration.current += 1;
    loadMoreLock.current = false;
    setState({
      boundary: requestBoundary,
      insights: null,
      error: null,
      loadMoreError: null,
      isLoading: true,
      isLoadingMore: false,
    });
    setReloadKey((key) => key + 1);
  }

  function loadMore() {
    const cursor = insights?.activity.next_cursor ?? null;
    if (!insights || cursor === null || loadMoreLock.current) return;

    const generation = ++pageRequestGeneration.current;
    const parentGeneration = initialRequestGeneration.current;
    const boundary = requestBoundary;
    const existingItems = insights.activity.items;
    loadMoreLock.current = true;
    setState((current) => {
      if (!isCurrentProfileRequest(current.boundary, boundary)) return current;
      return {
        ...current,
        loadMoreError: null,
        isLoadingMore: true,
      };
    });

    void readEmployeeProfileInsights(boundary.employeeId, {
      limit: INSIGHTS_PAGE_LIMIT,
      cursor,
    }).then(
      (nextPage) => {
        if (
          generation !== pageRequestGeneration.current ||
          parentGeneration !== initialRequestGeneration.current ||
          !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
        ) {
          return;
        }

        const existingIds = new Set(existingItems.map((item) => item.id));
        const repeatedItem = nextPage.activity.items.some((item) =>
          existingIds.has(item.id),
        );
        const repeatedCursor = nextPage.activity.next_cursor === cursor;
        loadMoreLock.current = false;
        if (repeatedItem || repeatedCursor) {
          setState((current) => {
            if (
              !isCurrentProfileRequest(current.boundary, boundary) ||
              current.insights?.activity.next_cursor !== cursor
            ) {
              return current;
            }
            return {
              ...current,
              loadMoreError: insightsErrorPresentation(
                new ApiClientError({ status: 200, code: "invalid_response" }),
                "load_more",
              ),
              isLoadingMore: false,
            };
          });
          return;
        }

        setState((current) => {
          if (
            !isCurrentProfileRequest(current.boundary, boundary) ||
            current.insights?.activity.next_cursor !== cursor
          ) {
            return current;
          }
          return {
            boundary,
            insights: {
              ...nextPage,
              activity: {
                ...nextPage.activity,
                items: [...existingItems, ...nextPage.activity.items],
              },
            },
            error: null,
            loadMoreError: null,
            isLoading: false,
            isLoadingMore: false,
          };
        });
      },
      (cause) => {
        if (
          generation !== pageRequestGeneration.current ||
          parentGeneration !== initialRequestGeneration.current ||
          !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
        ) {
          return;
        }
        loadMoreLock.current = false;
        setState((current) => {
          if (
            !isCurrentProfileRequest(current.boundary, boundary) ||
            current.insights?.activity.next_cursor !== cursor
          ) {
            return current;
          }
          return {
            ...current,
            loadMoreError: insightsErrorPresentation(cause, "load_more"),
            isLoadingMore: false,
          };
        });
      },
    );
  }

  return (
    <section
      className={styles.insightsSection}
      aria-labelledby="employee-insights-title"
      aria-busy={isLoading || isLoadingMore}
    >
      <header className={styles.insightsHeader}>
        <div>
          <span>Güncel İK özeti</span>
          <h3 id="employee-insights-title">Durum ve etkinlikler</h3>
          <p>Mevcut bakiyeler, talepler ve güvenli çalışan etkinliği görünümü.</p>
        </div>
      </header>

      {isLoading ? (
        <div className={styles.insightsLoading} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Güncel özet hazırlanıyor</strong>
            <span>Özet kartları ve son etkinlikler yükleniyor…</span>
          </div>
        </div>
      ) : error || !insights ? (
        <div className={styles.profileErrorAlert} role="alert">
          <div>
            <strong>Güncel özet yüklenemedi</strong>
            <span>{error?.message}</span>
            {error?.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={retryInitialLoad}
          >
            Yeniden dene
          </button>
        </div>
      ) : (
        <>
          <div className={styles.insightCards} aria-label="Çalışan güncel özetleri">
            <article
              className={`${styles.insightCard} ${styles.insightCardUnavailable}`}
            >
              <header>
                <span className={styles.insightCardIcon} aria-hidden="true">B</span>
                <div><h4>Belgeler</h4><p>Çalışan belgeleri</p></div>
              </header>
              <strong className={styles.insightUnavailableMetric}>Faz 5</strong>
              <p className={styles.insightCardDescription}>
                Belge özeti henüz kullanılamıyor.
              </p>
              <div className={styles.insightCardDetail}>
                <span>Durum</span><b>Kullanılamıyor</b>
              </div>
            </article>

            <article className={styles.insightCard}>
              <header>
                <span className={styles.insightCardIcon} aria-hidden="true">İ</span>
                <div><h4>İzin</h4><p>{insights.leave.period_year} yılı</p></div>
              </header>
              <strong className={styles.insightMetric}>
                {formatInsightNumber(insights.leave.remaining_balance_days)}
                <small> gün</small>
              </strong>
              <p className={styles.insightCardDescription}>Toplam kalan bakiye</p>
              <div className={styles.insightCardDetail}>
                <span>Bekleyen izin talebi</span>
                <b>{INSIGHT_NUMBER_FORMAT.format(insights.leave.pending_request_count)}</b>
              </div>
            </article>

            <article className={styles.insightCard}>
              <header>
                <span className={styles.insightCardIcon} aria-hidden="true">P</span>
                <div><h4>Profil değişiklikleri</h4><p>Çalışan talepleri</p></div>
              </header>
              <strong className={styles.insightMetric}>
                {INSIGHT_NUMBER_FORMAT.format(
                  insights.profile_changes.submitted_request_count,
                )}
                <small> talep</small>
              </strong>
              <p className={styles.insightCardDescription}>Gönderilen toplam talep</p>
              <div className={styles.insightCardDetail}>
                {insights.profile_changes.latest_status &&
                insights.profile_changes.latest_submitted_at ? (
                  <>
                    <span>
                      Son talep · {formatActivityDateTime(
                        insights.profile_changes.latest_submitted_at,
                      )}
                    </span>
                    <b>
                      {PROFILE_CHANGE_STATUS_LABELS[
                        insights.profile_changes.latest_status
                      ]}
                    </b>
                  </>
                ) : (
                  <span className={styles.insightEmptyDetail}>
                    Henüz profil değişikliği talebi yok
                  </span>
                )}
              </div>
            </article>
          </div>

          <section
            className={styles.activitySection}
            aria-labelledby="employee-activity-title"
          >
            <header className={styles.activityHeader}>
              <div>
                <span>Güvenli etkinlik</span>
                <h3 id="employee-activity-title">Son etkinlikler</h3>
                <p>İzin verilen çalışan olayları en yeniden eskiye gösterilir.</p>
              </div>
            </header>

            {insights.activity.items.length === 0 ? (
              <div className={styles.activityEmpty} role="status">
                <span aria-hidden="true">E</span>
                <div>
                  <strong>Henüz etkinlik yok</strong>
                  <p>Bu çalışan için gösterilebilecek bir etkinlik bulunmuyor.</p>
                </div>
              </div>
            ) : (
              <ol
                className={styles.activityList}
                id="employee-insights-activity-list"
              >
                {insights.activity.items.map((item) => (
                  <li key={item.id}>
                    <span className={styles.activityMarker} aria-hidden="true" />
                    <div>
                      <strong>{ACTIVITY_KIND_LABELS[item.kind]}</strong>
                      <time dateTime={item.occurred_at}>
                        {formatActivityDateTime(item.occurred_at)}
                      </time>
                    </div>
                  </li>
                ))}
              </ol>
            )}

            <footer className={styles.activityFooter}>
              {loadMoreError ? (
                <div className={styles.activityLoadError} role="alert">
                  <div>
                    <strong>Daha eski etkinlikler yüklenemedi</strong>
                    <span>{loadMoreError.message}</span>
                    {loadMoreError.reference ? (
                      <small>Referans: {loadMoreError.reference}</small>
                    ) : null}
                  </div>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={loadMore}
                  >
                    Yeniden dene
                  </button>
                </div>
              ) : insights.activity.next_cursor ? (
                <button
                  className={styles.secondaryButton}
                  type="button"
                  aria-controls="employee-insights-activity-list"
                  disabled={isLoadingMore}
                  onClick={loadMore}
                >
                  {isLoadingMore ? "Daha eski etkinlikler yükleniyor…" : "Daha fazla yükle"}
                </button>
              ) : insights.activity.items.length > 0 ? (
                <span role="status">Gösterilebilecek tüm etkinlikler yüklendi.</span>
              ) : null}
            </footer>
          </section>
        </>
      )}
    </section>
  );
}

function SummaryPanel({
  profile,
  requestBoundary,
}: {
  profile: EmployeeProfile;
  requestBoundary: ProfileRequestBoundary;
}) {
  const assignment = profile.organization.current_assignment;
  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Çalışan ana verisi</span>
          <h2>Genel bakış</h2>
          <p>Güncel İK özetleri, güvenli etkinlikler ve çalışan ana bilgileri.</p>
        </div>
      </header>

      <EmployeeInsightsOverview requestBoundary={requestBoundary} />

      <dl className={styles.profileMetadataGrid}>
        <div>
          <dt>Çalışan numarası</dt>
          <dd>{profile.core.employee_number}</dd>
        </div>
        <div>
          <dt>İş e-postası</dt>
          <dd>{profile.core.email ?? "Eklenmemiş"}</dd>
        </div>
        <div>
          <dt>Tercih edilen ad</dt>
          <dd>{profile.personal.preferred_name ?? "Belirtilmemiş"}</dd>
        </div>
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
        <div>
          <dt>Çalışma sonu</dt>
          <dd>{formatEmployeeDate(profile.employment.employment_end_date)}</dd>
        </div>
        <div>
          <dt>Sonlandırma nedeni</dt>
          <dd>{profile.employment.termination_reason ? TERMINATION_REASON_LABELS[profile.employment.termination_reason] : "—"}</dd>
        </div>
      </dl>

      <section className={styles.profileAssignmentSummary} aria-labelledby="profile-summary-org">
        <header>
          <span>Güncel organizasyon</span>
          <h3 id="profile-summary-org">Yapısal atama</h3>
        </header>
        {assignment ? (
          <dl className={styles.profileOrganizationGrid}>
            <div>
              <dt>Tüzel kişilik</dt>
              <dd>{assignment.legal_entity.name}</dd>
              <small>{assignment.legal_entity.code}</small>
            </div>
            <div>
              <dt>Şube</dt>
              <dd>{assignment.branch.name}</dd>
              <small>{assignment.branch.code}</small>
            </div>
            <div>
              <dt>Departman</dt>
              <dd>{assignment.department.name}</dd>
              <small>{assignment.department.code}</small>
            </div>
            <div>
              <dt>Pozisyon</dt>
              <dd>{assignment.position.title}</dd>
              <small>{assignment.position.code}</small>
            </div>
          </dl>
        ) : (
          <div className={styles.profileEmptyState}>
            <span aria-hidden="true">O</span>
            <div>
              <strong>Henüz yapısal atama yok</strong>
              <p>Organizasyon bilgileri mevcut atama çalışma alanında yönetilir.</p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ReadOnlyPersonal({
  core,
  personal,
}: {
  core: EmployeeProfileCore;
  personal: EmployeePersonalProfile;
}) {
  return (
    <dl className={styles.profileMetadataGrid}>
      <div><dt>Ad</dt><dd>{core.first_name}</dd></div>
      <div><dt>Soyad</dt><dd>{core.last_name}</dd></div>
      <div><dt>İş e-postası</dt><dd>{core.email ?? "Eklenmemiş"}</dd></div>
      <div><dt>Tercih edilen ad</dt><dd>{personal.preferred_name ?? "Belirtilmemiş"}</dd></div>
      <div><dt>Doğum tarihi</dt><dd>{formatEmployeeDate(personal.birth_date)}</dd></div>
      <div><dt>Telefon</dt><dd>{personal.phone ?? "Belirtilmemiş"}</dd></div>
    </dl>
  );
}

function PersonalPanel({
  core,
  personal,
  editable,
  requestBoundary,
  onSaved,
  onReload,
}: {
  core: EmployeeProfileCore;
  personal: EmployeePersonalProfile;
  editable: boolean;
  requestBoundary: ProfileRequestBoundary;
  onSaved: (result: EmployeePersonalProfileUpdateResult) => void;
  onReload: () => void;
}) {
  const requestGeneration = useRef(0);
  const latestRequestBoundary = useRef(requestBoundary);
  const savingLock = useRef(false);
  const [firstName, setFirstName] = useState(core.first_name);
  const [lastName, setLastName] = useState(core.last_name);
  const [email, setEmail] = useState(core.email ?? "");
  const [preferredName, setPreferredName] = useState(personal.preferred_name ?? "");
  const [birthDate, setBirthDate] = useState(personal.birth_date ?? "");
  const [phone, setPhone] = useState(personal.phone ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ProfileErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useLayoutEffect(() => {
    latestRequestBoundary.current = requestBoundary;
    return () => {
      requestGeneration.current += 1;
      savingLock.current = false;
    };
  }, [requestBoundary]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const boundary = requestBoundary;
    if (!boundary.permissionGranted || savingLock.current) return;
    const payload: EmployeePersonalProfileUpdate = {
      expected_version: personal.version,
    };
    const normalizedFirstName = firstName.trim();
    const normalizedLastName = lastName.trim();
    const normalizedEmail = optionalText(email);
    const normalizedPreferredName = optionalText(preferredName);
    const normalizedBirthDate = optionalText(birthDate);
    const normalizedPhone = optionalText(phone);
    let coreChanged = false;
    let sectionChanged = false;
    if (normalizedFirstName !== core.first_name) {
      payload.first_name = normalizedFirstName;
      coreChanged = true;
    }
    if (normalizedLastName !== core.last_name) {
      payload.last_name = normalizedLastName;
      coreChanged = true;
    }
    if (normalizedEmail !== core.email) {
      payload.email = normalizedEmail;
      coreChanged = true;
    }
    if (normalizedPreferredName !== personal.preferred_name) {
      payload.preferred_name = normalizedPreferredName;
      sectionChanged = true;
    }
    if (normalizedBirthDate !== personal.birth_date) {
      payload.birth_date = normalizedBirthDate;
      sectionChanged = true;
    }
    if (normalizedPhone !== personal.phone) {
      payload.phone = normalizedPhone;
      sectionChanged = true;
    }
    if (!coreChanged && !sectionChanged) {
      setError(null);
      setNotice("Kaydedilecek değişiklik yok.");
      return;
    }
    if (coreChanged) payload.expected_employee_version = core.employee_version;
    savingLock.current = true;
    const generation = ++requestGeneration.current;
    setIsSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await updateEmployeePersonalProfile(boundary.employeeId, payload);
      if (
        generation !== requestGeneration.current ||
        !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        return;
      }
      setFirstName(result.core.first_name);
      setLastName(result.core.last_name);
      setEmail(result.core.email ?? "");
      setPreferredName(result.personal.preferred_name ?? "");
      setBirthDate(result.personal.birth_date ?? "");
      setPhone(result.personal.phone ?? "");
      onSaved(result);
      setNotice("Kişisel bilgiler güncellendi.");
    } catch (cause) {
      if (
        generation === requestGeneration.current &&
        isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        setError(profileErrorPresentation(cause, "personal"));
      }
    } finally {
      if (
        generation === requestGeneration.current &&
        isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        savingLock.current = false;
        setIsSaving(false);
      }
    }
  }

  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Onaylı MVP alanları</span>
          <h2>Kişisel bilgiler</h2>
          <p>Temel iletişim ve tercih bilgilerini güvenli çalışan kaydında tutun.</p>
        </div>
      </header>

      {!editable ? (
        <ReadOnlyPersonal core={core} personal={personal} />
      ) : (
        <form className={styles.profileForm} onSubmit={submit}>
          {error ? (
            <div className={styles.profileErrorAlert} role="alert">
              <div>
                <strong>Kişisel bilgiler kaydedilemedi</strong>
                <span>{error.message}</span>
                {error.reference ? <small>Referans: {error.reference}</small> : null}
              </div>
              {error.conflict ? (
                <button className={styles.secondaryButton} type="button" onClick={onReload}>
                  Güncel veriyi yükle
                </button>
              ) : null}
            </div>
          ) : null}
          {notice ? <div className={styles.profileSuccess} role="status">{notice}</div> : null}

          <div className={styles.formGrid}>
            <div className={styles.formField}>
              <label htmlFor="profile_first_name">Ad</label>
              <input id="profile_first_name" value={firstName} onChange={(event) => setFirstName(event.target.value)} required minLength={1} maxLength={200} autoComplete="given-name" disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_last_name">Soyad</label>
              <input id="profile_last_name" value={lastName} onChange={(event) => setLastName(event.target.value)} required minLength={1} maxLength={200} autoComplete="family-name" disabled={isSaving} />
            </div>
            <div className={`${styles.formField} ${styles.wideField}`}>
              <label htmlFor="profile_work_email">İş e-postası</label>
              <input id="profile_work_email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" inputMode="email" maxLength={320} autoComplete="email" autoCapitalize="none" spellCheck={false} disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_preferred_name">Tercih edilen ad</label>
              <input id="profile_preferred_name" value={preferredName} onChange={(event) => setPreferredName(event.target.value)} maxLength={200} autoComplete="nickname" disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_birth_date">Doğum tarihi</label>
              <input id="profile_birth_date" value={birthDate} onChange={(event) => setBirthDate(event.target.value)} type="date" autoComplete="bday" disabled={isSaving} />
            </div>
            <div className={`${styles.formField} ${styles.wideField}`}>
              <label htmlFor="profile_phone">Telefon</label>
              <input id="profile_phone" value={phone} onChange={(event) => setPhone(event.target.value)} type="tel" inputMode="tel" maxLength={32} autoComplete="tel" disabled={isSaving} />
            </div>
          </div>
          <div className={styles.profileFormActions}>
            <button className={styles.primaryButton} type="submit" disabled={isSaving}>
              {isSaving ? "Kişisel bilgiler kaydediliyor…" : "Kişisel bilgileri kaydet"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function ReadOnlyEmployment({ employment }: { employment: EmployeeEmploymentProfile }) {
  return (
    <dl className={styles.profileMetadataGrid}>
      <div><dt>İşe başlangıç tarihi</dt><dd>{formatEmployeeDate(employment.employment_start_date)}</dd></div>
      <div><dt>Çalışma sonu</dt><dd>{formatEmployeeDate(employment.employment_end_date)}</dd></div>
      <div><dt>Sonlandırma nedeni</dt><dd>{employment.termination_reason ? TERMINATION_REASON_LABELS[employment.termination_reason] : "—"}</dd></div>
      <div><dt>Sözleşme türü</dt><dd>{employment.contract_type ? CONTRACT_TYPE_LABELS[employment.contract_type] : "Belirtilmemiş"}</dd></div>
      <div><dt>Çalışma türü</dt><dd>{employment.work_type ? WORK_TYPE_LABELS[employment.work_type] : "Belirtilmemiş"}</dd></div>
    </dl>
  );
}

function EmploymentPanel({
  core,
  employment,
  editable,
  requestBoundary,
  onSaved,
  onReload,
}: {
  core: EmployeeProfileCore;
  employment: EmployeeEmploymentProfile;
  editable: boolean;
  requestBoundary: ProfileRequestBoundary;
  onSaved: (result: EmployeeEmploymentProfileUpdateResult) => void;
  onReload: () => void;
}) {
  const requestGeneration = useRef(0);
  const latestRequestBoundary = useRef(requestBoundary);
  const savingLock = useRef(false);
  const [startDate, setStartDate] = useState(employment.employment_start_date);
  const [contractType, setContractType] = useState<EmployeeContractType | "">(
    employment.contract_type ?? "",
  );
  const [workType, setWorkType] = useState<EmployeeWorkType | "">(
    employment.work_type ?? "",
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ProfileErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useLayoutEffect(() => {
    latestRequestBoundary.current = requestBoundary;
    return () => {
      requestGeneration.current += 1;
      savingLock.current = false;
    };
  }, [requestBoundary]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const boundary = requestBoundary;
    if (!boundary.permissionGranted || savingLock.current) return;
    const payload: EmployeeEmploymentProfileUpdate = {
      expected_version: employment.version,
    };
    const normalizedContractType = contractType || null;
    const normalizedWorkType = workType || null;
    let coreChanged = false;
    let sectionChanged = false;
    if (startDate !== employment.employment_start_date) {
      payload.employment_start_date = startDate;
      coreChanged = true;
    }
    if (normalizedContractType !== employment.contract_type) {
      payload.contract_type = normalizedContractType;
      sectionChanged = true;
    }
    if (normalizedWorkType !== employment.work_type) {
      payload.work_type = normalizedWorkType;
      sectionChanged = true;
    }
    if (!coreChanged && !sectionChanged) {
      setError(null);
      setNotice("Kaydedilecek değişiklik yok.");
      return;
    }
    if (coreChanged) payload.expected_employee_version = core.employee_version;
    savingLock.current = true;
    const generation = ++requestGeneration.current;
    setIsSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await updateEmployeeEmploymentProfile(boundary.employeeId, payload);
      if (
        generation !== requestGeneration.current ||
        !isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        return;
      }
      setStartDate(result.employment.employment_start_date);
      setContractType(result.employment.contract_type ?? "");
      setWorkType(result.employment.work_type ?? "");
      onSaved(result);
      setNotice("İstihdam bilgileri güncellendi.");
    } catch (cause) {
      if (
        generation === requestGeneration.current &&
        isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        setError(profileErrorPresentation(cause, "employment"));
      }
    } finally {
      if (
        generation === requestGeneration.current &&
        isCurrentProfileRequest(boundary, latestRequestBoundary.current)
      ) {
        savingLock.current = false;
        setIsSaving(false);
      }
    }
  }

  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Çalışma ilişkisi</span>
          <h2>İstihdam bilgileri</h2>
          <p>Başlangıç, sözleşme ve çalışma türünü yaşam döngüsü aksiyonu açmadan yönetin.</p>
        </div>
      </header>

      {!editable ? (
        <ReadOnlyEmployment employment={employment} />
      ) : (
        <form className={styles.profileForm} onSubmit={submit}>
          {error ? (
            <div className={styles.profileErrorAlert} role="alert">
              <div>
                <strong>İstihdam bilgileri kaydedilemedi</strong>
                <span>{error.message}</span>
                {error.reference ? <small>Referans: {error.reference}</small> : null}
              </div>
              {error.conflict ? (
                <button className={styles.secondaryButton} type="button" onClick={onReload}>
                  Güncel veriyi yükle
                </button>
              ) : null}
            </div>
          ) : null}
          {notice ? <div className={styles.profileSuccess} role="status">{notice}</div> : null}

          <div className={styles.formGrid}>
            <div className={`${styles.formField} ${styles.wideField}`}>
              <label htmlFor="profile_employment_start">İşe başlangıç tarihi</label>
              <input id="profile_employment_start" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_contract_type">Sözleşme türü</label>
              <select id="profile_contract_type" value={contractType} onChange={(event) => setContractType(event.target.value as typeof contractType)} disabled={isSaving}>
                <option value="">Belirtilmedi</option>
                <option value="indefinite">Belirsiz süreli</option>
                <option value="fixed_term">Belirli süreli</option>
              </select>
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_work_type">Çalışma türü</label>
              <select id="profile_work_type" value={workType} onChange={(event) => setWorkType(event.target.value as typeof workType)} disabled={isSaving}>
                <option value="">Belirtilmedi</option>
                <option value="full_time">Tam zamanlı</option>
                <option value="part_time">Yarı zamanlı</option>
              </select>
            </div>
          </div>
          <div className={styles.profileFormActions}>
            <button className={styles.primaryButton} type="submit" disabled={isSaving}>
              {isSaving ? "İstihdam bilgileri kaydediliyor…" : "İstihdam bilgilerini kaydet"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function assignmentStatus(assignment: EmployeeAssignment): string {
  return assignment.is_current ? "Güncel" : "Geçmiş";
}

function OrganizationPanel({ profile }: { profile: EmployeeProfile }) {
  const { current_assignment: current, history, history_limit: limit } = profile.organization;
  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Phase 3 kaynak verisi</span>
          <h2>Organizasyon</h2>
          <p>Güncel atama ve korunmuş geçmiş burada salt okunur sunulur.</p>
        </div>
        <span className={styles.readOnlyBadge}>Salt okunur</span>
      </header>

      {current ? (
        <section className={styles.currentAssignmentCard} aria-labelledby="current-profile-assignment">
          <header>
            <div>
              <span>Güncel atama</span>
              <h3 id="current-profile-assignment">{current.position.title}</h3>
            </div>
            <span className={styles.currentBadge}>Güncel</span>
          </header>
          <dl className={styles.profileOrganizationGrid}>
            <div><dt>Tüzel kişilik</dt><dd>{current.legal_entity.name}</dd><small>{current.legal_entity.code}</small></div>
            <div><dt>Şube</dt><dd>{current.branch.name}</dd><small>{current.branch.code}</small></div>
            <div><dt>Departman</dt><dd>{current.department.name}</dd><small>{current.department.code}</small></div>
            <div><dt>Yönetici</dt><dd>{current.manager?.full_name ?? "Yönetici yok"}</dd><small>{current.manager?.email ?? "—"}</small></div>
          </dl>
        </section>
      ) : (
        <div className={styles.profileEmptyState}>
          <span aria-hidden="true">O</span>
          <div><strong>Henüz yapısal atama yok</strong><p>Atamalar organizasyon çalışma alanında yönetilir.</p></div>
        </div>
      )}

      <section className={styles.assignmentHistorySection} aria-labelledby="profile-assignment-history">
        <header>
          <div>
            <h3 id="profile-assignment-history">Atama geçmişi</h3>
            <p>En fazla {limit} korunmuş atama, en yeniden eskiye gösterilir.</p>
          </div>
        </header>
        {history.length === 0 ? (
          <div className={styles.profileHistoryEmpty}>Gösterilecek atama geçmişi bulunmuyor.</div>
        ) : (
          <div className={styles.profileTableScroller}>
            <table className={styles.profileHistoryTable} aria-label="Atama geçmişi">
              <thead><tr><th scope="col">Yapı</th><th scope="col">Pozisyon</th><th scope="col">Yönetici</th><th scope="col">Yürürlük</th><th scope="col">Neden</th><th scope="col">Durum</th></tr></thead>
              <tbody>
                {history.map((assignment) => (
                  <tr key={assignment.id}>
                    <td data-label="Yapı"><strong>{assignment.department.name}</strong><small>{assignment.legal_entity.code} · {assignment.branch.name}</small></td>
                    <td data-label="Pozisyon"><strong>{assignment.position.title}</strong><small>{assignment.position.code}</small></td>
                    <td data-label="Yönetici"><strong>{assignment.manager?.full_name ?? "Yönetici yok"}</strong><small>{assignment.manager?.email ?? "—"}</small></td>
                    <td data-label="Yürürlük"><strong>{formatEmployeeDate(assignment.effective_from)}</strong><small>{assignment.effective_to ? formatEmployeeDate(assignment.effective_to) : "Devam ediyor"}</small></td>
                    <td data-label="Neden">{assignment.change_reason ?? "İlk atama"}</td>
                    <td data-label="Durum"><span className={assignment.is_current ? styles.currentBadge : styles.historyBadge}>{assignmentStatus(assignment)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {profile.organization.history_truncated ? (
          <div className={styles.historyTruncationNotice} role="note">
            İlk {limit} atama kaydı gösteriliyor. Daha eski kayıtlar bu görünümde sınırlandırıldı.
          </div>
        ) : null}
      </section>
    </div>
  );
}

export function Employee360Screen({ employeeId }: { employeeId: string }) {
  const { user, sessionGeneration } = useSession();
  const canRead = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTenantEmployees,
  );
  const canUpdate = hasPermission(user, AUTHORIZATION_PERMISSIONS.updateEmployees);
  const readBoundary = useMemo<ProfileRequestBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canRead,
      employeeId,
    }),
    [
      canRead,
      employeeId,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const updateBoundary = useMemo<ProfileRequestBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canUpdate,
      employeeId,
    }),
    [
      canUpdate,
      employeeId,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const latestReadBoundary = useRef(readBoundary);
  const readRequestGeneration = useRef(0);
  const [profileState, setProfileState] = useState<ProfileLoadState>(() => ({
    boundary: readBoundary,
    profile: null,
    error: null,
    isLoading: true,
  }));
  const [reloadKey, setReloadKey] = useState(0);
  const [activeTab, setActiveTab] = useState<ProfileTab>("summary");
  const tabRefs = useRef<Partial<Record<ProfileTab, HTMLButtonElement>>>({});

  useLayoutEffect(() => {
    latestReadBoundary.current = readBoundary;
    return () => {
      readRequestGeneration.current += 1;
    };
  }, [readBoundary]);

  useEffect(() => {
    const generation = ++readRequestGeneration.current;
    const boundary = readBoundary;
    if (!boundary.permissionGranted) {
      return () => {
        readRequestGeneration.current += 1;
      };
    }

    void readEmployeeProfile(boundary.employeeId).then(
      (loadedProfile) => {
        if (
          generation !== readRequestGeneration.current ||
          !isCurrentProfileRequest(boundary, latestReadBoundary.current)
        ) {
          return;
        }
        setProfileState({
          boundary,
          profile: loadedProfile,
          error: null,
          isLoading: false,
        });
      },
      (cause) => {
        if (
          generation !== readRequestGeneration.current ||
          !isCurrentProfileRequest(boundary, latestReadBoundary.current)
        ) {
          return;
        }
        setProfileState({
          boundary,
          profile: null,
          error: profileErrorPresentation(cause, "read"),
          isLoading: false,
        });
      },
    );
    return () => {
      readRequestGeneration.current += 1;
    };
  }, [readBoundary, reloadKey]);

  const profileStateIsCurrent = isCurrentProfileRequest(
    profileState.boundary,
    readBoundary,
  );
  const profile = profileStateIsCurrent ? profileState.profile : null;
  const error = profileStateIsCurrent ? profileState.error : null;
  const isLoading = !profileStateIsCurrent || profileState.isLoading;

  function reload() {
    setProfileState({
      boundary: readBoundary,
      profile: null,
      error: null,
      isLoading: true,
    });
    setReloadKey((key) => key + 1);
  }

  function mergePersonalProfile(result: EmployeePersonalProfileUpdateResult) {
    setProfileState((current) => {
      if (
        !current.profile ||
        result.core.id !== readBoundary.employeeId ||
        !isCurrentProfileRequest(current.boundary, readBoundary)
      ) {
        return current;
      }
      return {
        ...current,
        profile: {
          ...current.profile,
          core: result.core,
          personal: result.personal,
        },
      };
    });
  }

  function mergeEmploymentProfile(result: EmployeeEmploymentProfileUpdateResult) {
    setProfileState((current) => {
      if (
        !current.profile ||
        result.core.id !== readBoundary.employeeId ||
        !isCurrentProfileRequest(current.boundary, readBoundary)
      ) {
        return current;
      }
      return {
        ...current,
        profile: {
          ...current.profile,
          core: result.core,
          employment: result.employment,
        },
      };
    });
  }

  function activateTab(tab: ProfileTab, focus = false) {
    setActiveTab(tab);
    if (focus) {
      window.requestAnimationFrame(() => tabRefs.current[tab]?.focus());
    }
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, tab: ProfileTab) {
    const currentIndex = PROFILE_TABS.findIndex((item) => item.id === tab);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % PROFILE_TABS.length;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + PROFILE_TABS.length) % PROFILE_TABS.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = PROFILE_TABS.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    activateTab(PROFILE_TABS[nextIndex].id, true);
  }

  if (isLoading) {
    return (
      <section className={styles.profilePage} aria-busy="true">
        <Link className={styles.profileBackLink} href="/employees">← Çalışanlara dön</Link>
        <div className={styles.profilePageLoading} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          <div><strong>Çalışan profili yükleniyor</strong><span>Employee 360 bölümleri hazırlanıyor…</span></div>
        </div>
      </section>
    );
  }

  if (error || !profile) {
    return (
      <section className={styles.profilePage}>
        <Link className={styles.profileBackLink} href="/employees">← Çalışanlara dön</Link>
        <div className={styles.profilePageError} role="alert">
          <div><strong>Çalışan profili yüklenemedi</strong><span>{error?.message}</span>{error?.reference ? <small>Referans: {error.reference}</small> : null}</div>
          <button className={styles.secondaryButton} type="button" onClick={reload}>Yeniden dene</button>
        </div>
      </section>
    );
  }

  const isArchived = profile.core.archived_at !== null;
  const profileEditable = canUpdate && !isArchived;

  return (
    <section className={styles.profilePage} aria-labelledby="employee-profile-title">
      <Link className={styles.profileBackLink} href="/employees">← Çalışanlara dön</Link>
      <header className={styles.profileHero}>
        <span className={styles.profileHeroAvatar} aria-hidden="true">{profile.core.first_name.slice(0, 1).toLocaleUpperCase("tr-TR")}</span>
        <div className={styles.profileHeroIdentity}>
          <span>Çalışan 360</span>
          <h1 id="employee-profile-title">{fullName(profile.core)}</h1>
          <p>{profile.personal.preferred_name && profile.personal.preferred_name !== profile.core.first_name ? `${profile.personal.preferred_name} · ` : ""}{profile.core.employee_number}{profile.core.email ? ` · ${profile.core.email}` : ""}</p>
        </div>
        <div className={styles.profileHeroBadges}>
          <EmployeeStatusBadge status={profile.core.status} />
          {isArchived ? <span className={styles.archivedBadge}>Arşivlendi</span> : null}
        </div>
      </header>

      {isArchived ? (
        <div className={styles.archivedBanner} role="status">
          <strong>Arşivlenmiş çalışan kaydı</strong>
          <span>Korunan Employee 360 geçmişi salt okunur gösteriliyor.</span>
        </div>
      ) : null}

      <LifecycleCard
        key={`lifecycle-${profileRequestBoundaryKey(updateBoundary)}-${profile.core.employee_version}`}
        profile={profile}
        editable={profileEditable}
        requestBoundary={updateBoundary}
        onReload={reload}
      />

      {profileEditable && profile.core.status !== "terminated" ? (
        <EmployeeAccountLinkCard
          key={`account-link-${profileRequestBoundaryKey(updateBoundary)}`}
          employeeId={employeeId}
        />
      ) : null}

      <div className={styles.profileWorkspace}>
        <div className={styles.profileTabs} role="tablist" aria-label="Çalışan profil bölümleri">
          {PROFILE_TABS.map((tab) => (
            <button
              ref={(node) => { tabRefs.current[tab.id] = node ?? undefined; }}
              className={styles.profileTab}
              id={`employee-profile-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`employee-profile-panel-${tab.id}`}
              tabIndex={activeTab === tab.id ? 0 : -1}
              onClick={() => activateTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, tab.id)}
              key={tab.id}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <section
          className={styles.profilePanel}
          id={`employee-profile-panel-${activeTab}`}
          role="tabpanel"
          aria-labelledby={`employee-profile-tab-${activeTab}`}
          tabIndex={0}
        >
          {activeTab === "summary" ? (
            <SummaryPanel
              key={profileRequestBoundaryKey(readBoundary)}
              profile={profile}
              requestBoundary={readBoundary}
            />
          ) : null}
          {activeTab === "personal" ? (
            <PersonalPanel
              key={profileRequestBoundaryKey(updateBoundary)}
              core={profile.core}
              personal={profile.personal}
              editable={profileEditable}
              requestBoundary={updateBoundary}
              onReload={reload}
              onSaved={mergePersonalProfile}
            />
          ) : null}
          {activeTab === "employment" ? (
            <EmploymentPanel
              key={profileRequestBoundaryKey(updateBoundary)}
              core={profile.core}
              employment={profile.employment}
              editable={profileEditable}
              requestBoundary={updateBoundary}
              onReload={reload}
              onSaved={mergeEmploymentProfile}
            />
          ) : null}
          {activeTab === "organization" ? <OrganizationPanel profile={profile} /> : null}
        </section>
      </div>
    </section>
  );
}
