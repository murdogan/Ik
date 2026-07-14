"use client";

import Link from "next/link";
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { EmployeeStatusBadge } from "@/components/employees/employee-status-badge";
import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  approveHrProfileChangeRequest,
  type HrProfileChangeRequestDetail,
  type HrRawProfileChange,
  type ProfileChangeField,
  normalizeProfileChangeText,
  readHrProfileChangeRequest,
  rejectHrProfileChangeRequest,
} from "@/lib/employee-profile-change-requests";
import { isSessionGenerationCurrent } from "@/lib/session";

import { ProfileChangeConfirmationDialog } from "./confirmation-dialog";
import styles from "./profile-change-requests.module.css";

const FIELD_LABELS: Record<ProfileChangeField, string> = {
  preferred_name: "Tercih edilen ad",
  phone: "Telefon",
  birth_date: "Doğum tarihi",
};

const STATUS_LABELS = {
  submitted: "Değerlendirmede",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
} as const;

interface DetailBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  readGranted: boolean;
  updateGranted: boolean;
  requestId: string;
}

interface DecisionError {
  message: string;
  reference: string | null;
  conflict: boolean;
  stale: boolean;
}

interface DetailState {
  boundary: DetailBoundary;
  request: HrProfileChangeRequestDetail | null;
  error: DecisionError | null;
  isLoading: boolean;
}

type PendingDecision =
  | { type: "approve"; request: HrProfileChangeRequestDetail }
  | { type: "reject"; request: HrProfileChangeRequestDetail; reason: string };

function isCurrentBoundary(
  expected: DetailBoundary,
  current: DetailBoundary,
): boolean {
  return (
    isSessionGenerationCurrent(expected.sessionGeneration) &&
    expected.sessionGeneration === current.sessionGeneration &&
    expected.userId === current.userId &&
    expected.membershipId === current.membershipId &&
    expected.tenantId === current.tenantId &&
    expected.permissionVersion === current.permissionVersion &&
    expected.readGranted === current.readGranted &&
    expected.updateGranted === current.updateGranted &&
    expected.requestId === current.requestId
  );
}

function detailError(cause: unknown, action: "read" | "decision"): DecisionError {
  let message =
    action === "read"
      ? "Değişiklik talebi şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : "Talep kararı şu anda tamamlanamıyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;
  let stale = false;
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict, stale };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu talebi değerlendirmek için gerekli İK yetkileriniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Talep bulunamadı veya artık bu tenant içinde erişilebilir değil.";
  } else if (cause.status === 409) {
    conflict = true;
    stale = cause.code === "employee_profile_change_request_stale_profile";
    message = stale
      ? "Çalışanın kişisel profili talep gönderildikten sonra değişti. Hiçbir değer uygulanmadı; güncel karşılaştırmayı yükleyip talebi açıkça reddedin veya yeniden değerlendirin."
      : "Talep başka bir İK kullanıcısı veya çalışan tarafından işlendi. Güncel talep durumunu yükleyin.";
  } else if (cause.status === 422) {
    message = "Beklenen talep sürümünü ve ret açıklamasını kontrol edin.";
  } else if (cause.code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir talep yanıtı alındı. Hiçbir değer ekranda uygulanmadı.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference, conflict, stale };
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function employeeName(request: HrProfileChangeRequestDetail): string {
  return `${request.employee.first_name} ${request.employee.last_name}`.trim();
}

function rawValue(value: string | null): string {
  return value ?? "Belirtilmemiş";
}

function proposedValue(value: string | null): string {
  return value ?? "Temizlenecek";
}

function ComparisonRow({
  field,
  change,
}: {
  field: ProfileChangeField;
  change: HrRawProfileChange;
}) {
  return (
    <article className={styles.comparisonRow}>
      <header>
        <h3>{FIELD_LABELS[field]}</h3>
        <span className={change.current_matches_base ? styles.currentBadge : styles.staleBadge}>
          {change.current_matches_base ? "Başlangıçla aynı" : "Başlangıçtan farklı"}
        </span>
      </header>
      <dl>
        <div><dt>Talep anındaki değer</dt><dd>{rawValue(change.base_value)}</dd></div>
        <div><dt>Şu anki değer</dt><dd>{rawValue(change.current_value)}</dd></div>
        <div><dt>Önerilen değer</dt><dd>{proposedValue(change.proposed_value)}</dd></div>
      </dl>
    </article>
  );
}

export function ProfileChangeRequestDetailScreen({ requestId }: { requestId: string }) {
  const { user, sessionGeneration } = useSession();
  const canRead = hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantEmployees);
  const canUpdate = hasPermission(user, AUTHORIZATION_PERMISSIONS.updateEmployees);
  const boundary = useMemo<DetailBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      readGranted: canRead,
      updateGranted: canUpdate,
      requestId,
    }),
    [
      canRead,
      canUpdate,
      requestId,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );

  return (
    <ProfileChangeRequestDetailContent
      key={`${boundary.sessionGeneration}:${boundary.userId}:${boundary.membershipId}:${boundary.tenantId}:${boundary.permissionVersion}:${boundary.readGranted}:${boundary.updateGranted}:${boundary.requestId}`}
      boundary={boundary}
    />
  );
}

function ProfileChangeRequestDetailContent({
  boundary,
}: {
  boundary: DetailBoundary;
}) {
  const latestBoundary = useRef(boundary);
  const establishedEmployeeId = useRef<string | null>(null);
  const loadRequest = useRef(0);
  const mutationRequest = useRef(0);
  const mutationLock = useRef(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<DetailState>(() => ({
    boundary,
    request: null,
    error: null,
    isLoading: true,
  }));
  const [decisionErrorState, setDecisionErrorState] = useState<DecisionError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => {
      loadRequest.current += 1;
      mutationRequest.current += 1;
      mutationLock.current = false;
    };
  }, [boundary]);

  useEffect(() => {
    if (!boundary.readGranted || !boundary.updateGranted) return;
    const requestGeneration = ++loadRequest.current;
    const requestBoundary = boundary;
    void readHrProfileChangeRequest(requestBoundary.requestId).then(
      (request) => {
        if (
          requestGeneration !== loadRequest.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        if (
          establishedEmployeeId.current !== null &&
          request.employee.id !== establishedEmployeeId.current
        ) {
          setState({
            boundary: requestBoundary,
            request: null,
            error: detailError(
              new ApiClientError({ status: 200, code: "invalid_response" }),
              "read",
            ),
            isLoading: false,
          });
          setDecisionErrorState(null);
          setNotice(null);
          return;
        }
        establishedEmployeeId.current = request.employee.id;
        setState({
          boundary: requestBoundary,
          request,
          error: null,
          isLoading: false,
        });
        setDecisionErrorState(null);
        setNotice(null);
      },
      (cause) => {
        if (
          requestGeneration !== loadRequest.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          request: null,
          error: detailError(cause, "read"),
          isLoading: false,
        });
        setDecisionErrorState(null);
        setNotice(null);
      },
    );
    return () => {
      loadRequest.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const request = stateIsCurrent ? state.request : null;
  const error = stateIsCurrent ? state.error : null;
  const isLoading = !stateIsCurrent || state.isLoading;

  function reload() {
    setState({
      boundary,
      request: null,
      error: null,
      isLoading: true,
    });
    setPendingDecision(null);
    setDecisionErrorState(null);
    setReasonError(null);
    setReloadKey((key) => key + 1);
  }

  function prepareReject(current: HrProfileChangeRequestDetail) {
    const normalized = normalizeProfileChangeText(reason);
    if (normalized.length < 1 || normalized.length > 500) {
      setReasonError("Ret açıklaması 1-500 karakter arasında olmalıdır.");
      return;
    }
    setReasonError(null);
    setPendingDecision({ type: "reject", request: current, reason: normalized });
  }

  async function applyDecision() {
    const action = pendingDecision;
    if (
      !action ||
      mutationLock.current ||
      !boundary.readGranted ||
      !boundary.updateGranted
    ) {
      return;
    }
    const requestBoundary = boundary;
    const requestGeneration = ++mutationRequest.current;
    mutationLock.current = true;
    setIsDeciding(true);
    setDecisionErrorState(null);
    setNotice(null);
    try {
      const result =
        action.type === "approve"
          ? await approveHrProfileChangeRequest(
              action.request.id,
              action.request.version,
            )
          : await rejectHrProfileChangeRequest(
              action.request.id,
              action.request.version,
              action.reason,
            );
      if (
        result.employee.id !== action.request.employee.id ||
        (establishedEmployeeId.current !== null &&
          result.employee.id !== establishedEmployeeId.current)
      ) {
        throw new ApiClientError({ status: 200, code: "invalid_response" });
      }
      if (
        requestGeneration !== mutationRequest.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setState({
        boundary: requestBoundary,
        request: result,
        error: null,
        isLoading: false,
      });
      establishedEmployeeId.current = result.employee.id;
      setPendingDecision(null);
      setReason("");
      setNotice(
        action.type === "approve"
          ? "Talep onaylandı. Kişisel profil sunucudan atomik olarak güncellendi."
          : "Talep reddedildi. Çalışan profili değiştirilmedi.",
      );
    } catch (cause) {
      if (
        requestGeneration === mutationRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setPendingDecision(null);
        setDecisionErrorState(detailError(cause, "decision"));
      }
    } finally {
      if (
        requestGeneration === mutationRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        mutationLock.current = false;
        setIsDeciding(false);
      }
    }
  }

  if (!boundary.readGranted || !boundary.updateGranted) return null;

  if (isLoading) {
    return (
      <section className={styles.detailPage} aria-busy="true">
        <Link className={styles.backLink} href="/profile-change-requests">← Taleplere dön</Link>
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <strong>Talep ayrıntısı yükleniyor</strong>
        </div>
      </section>
    );
  }

  if (error || !request) {
    return (
      <section className={styles.detailPage}>
        <Link className={styles.backLink} href="/profile-change-requests">← Taleplere dön</Link>
        <div className={styles.errorState} role="alert">
          <strong>Talep ayrıntısı yüklenemedi</strong>
          <span>{error?.message}</span>
          {error?.reference ? <small>Referans: {error.reference}</small> : null}
          <button className={styles.secondaryButton} type="button" onClick={reload}>Yeniden dene</button>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.detailPage} aria-labelledby="profile-change-detail-title">
      <Link className={styles.backLink} href="/profile-change-requests">← Taleplere dön</Link>
      <header className={styles.detailHero}>
        <span className={styles.avatar} aria-hidden="true">
          {request.employee.first_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
        </span>
        <div>
          <span>Profil değişiklik talebi</span>
          <h1 id="profile-change-detail-title">{employeeName(request)}</h1>
          <p>{request.employee.employee_number}{request.employee.email ? ` · ${request.employee.email}` : ""}</p>
        </div>
        <EmployeeStatusBadge status={request.employee.status} />
      </header>

      <dl className={styles.detailMetaGrid}>
        <div><dt>Talep durumu</dt><dd>{STATUS_LABELS[request.status]}</dd></div>
        <div><dt>Gönderim</dt><dd>{formatTimestamp(request.submitted_at)}</dd></div>
        <div><dt>Başlangıç profil sürümü</dt><dd>{request.base_profile_version}</dd></div>
        <div><dt>Güncel profil sürümü</dt><dd>{request.current_profile_version}</dd></div>
      </dl>

      {request.profile_is_stale ? (
        <div className={styles.staleNotice} role="alert">
          <strong>Profil talep gönderildikten sonra değişmiş</strong>
          <p>Karar vermeden önce aşağıdaki güncel değerleri inceleyin. Onay sunucuda tekrar doğrulanır ve uyuşmazlık varsa hiçbir alan uygulanmaz.</p>
        </div>
      ) : null}
      {decisionErrorState ? (
        <div className={styles.errorAlert} role="alert">
          <div>
            <strong>Karar tamamlanamadı</strong>
            <span>{decisionErrorState.message}</span>
            {decisionErrorState.reference ? <small>Referans: {decisionErrorState.reference}</small> : null}
          </div>
          {decisionErrorState.conflict ? (
            <button className={styles.secondaryButton} type="button" onClick={reload}>
              Güncel talebi yükle
            </button>
          ) : null}
        </div>
      ) : null}
      {notice ? <div className={styles.successAlert} role="status">{notice}</div> : null}

      <section className={styles.comparisonSection} aria-labelledby="profile-change-comparison-title">
        <header>
          <span>Güvenli değer karşılaştırması</span>
          <h2 id="profile-change-comparison-title">Mevcut ve önerilen bilgiler</h2>
          <p>Yalnızca bu talepte değişen ve P4E kapsamında izin verilen kişisel alanlar gösterilir.</p>
        </header>
        <div className={styles.comparisonList}>
          {request.changes.preferred_name ? <ComparisonRow field="preferred_name" change={request.changes.preferred_name} /> : null}
          {request.changes.phone ? <ComparisonRow field="phone" change={request.changes.phone} /> : null}
          {request.changes.birth_date ? <ComparisonRow field="birth_date" change={request.changes.birth_date} /> : null}
        </div>
      </section>

      {request.rejection_reason ? (
        <div className={styles.reasonBox}>
          <strong>Ret açıklaması</strong>
          <p>{request.rejection_reason}</p>
        </div>
      ) : null}

      {request.status === "submitted" ? (
        <section className={styles.decisionPanel} aria-labelledby="profile-change-decision-title">
          <header>
            <span>İK kararı</span>
            <h2 id="profile-change-decision-title">Talebi değerlendir</h2>
            <p>Her iki işlem de güncel talep sürümünü kullanır. Onay profili atomik günceller; ret hiçbir profil alanını değiştirmez.</p>
          </header>
          <div className={styles.rejectionField}>
            <label htmlFor="profile_change_rejection_reason">Ret açıklaması</label>
            <textarea
              id="profile_change_rejection_reason"
              value={reason}
              maxLength={500}
              rows={4}
              disabled={isDeciding}
              aria-describedby="profile_change_rejection_help"
              onChange={(event) => setReason(event.target.value)}
            />
            <small id="profile_change_rejection_help">Yalnızca işlemsel ve hassas olmayan kısa bir açıklama yazın. {reason.length}/500</small>
            {reasonError ? <span className={styles.fieldError} role="alert">{reasonError}</span> : null}
          </div>
          <div className={styles.decisionActions}>
            <button
              className={styles.dangerButton}
              type="button"
              disabled={isDeciding}
              onClick={() => prepareReject(request)}
            >
              Reddetmeyi gözden geçir
            </button>
            <button
              className={styles.primaryButton}
              type="button"
              disabled={isDeciding}
              onClick={() => setPendingDecision({ type: "approve", request })}
            >
              Onaylamayı gözden geçir
            </button>
          </div>
        </section>
      ) : request.status === "approved" ? (
        <div className={styles.freshProfileNotice} role="note">
          <strong>Onaylanan değerler ekranda tahmin edilmedi.</strong>
          <span>Çalışan 360 güncel profili sunucudan yeniden yükler.</span>
          <Link href={`/employees/${encodeURIComponent(request.employee.id)}`}>Çalışan 360’ı aç</Link>
        </div>
      ) : null}

      {pendingDecision ? (
        <ProfileChangeConfirmationDialog
          title={pendingDecision.type === "approve" ? "Talep onaylansın mı?" : "Talep reddedilsin mi?"}
          description={
            pendingDecision.type === "approve" ? (
              <>
                <strong>Önerilen değerler çalışanın kişisel profiline uygulanacak.</strong>
                <p>Sunucu profil ve talep sürümlerini yeniden doğrulayacak; çakışmada hiçbir alan değişmeyecek.</p>
              </>
            ) : (
              <>
                <strong>Talep hassas olmayan açıklamanızla reddedilecek.</strong>
                <p>Çalışanın kişisel profili değiştirilmeyecek.</p>
              </>
            )
          }
          confirmLabel={pendingDecision.type === "approve" ? "Talebi onayla" : "Talebi reddet"}
          busyLabel={pendingDecision.type === "approve" ? "Talep onaylanıyor…" : "Talep reddediliyor…"}
          danger={pendingDecision.type === "reject"}
          isBusy={isDeciding}
          onCancel={() => {
            if (!isDeciding) setPendingDecision(null);
          }}
          onConfirm={() => void applyDecision()}
        />
      ) : null}
    </section>
  );
}
