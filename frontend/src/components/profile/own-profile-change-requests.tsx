"use client";

import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ProfileChangeConfirmationDialog } from "@/components/profile-change-requests/confirmation-dialog";
import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  cancelOwnProfileChangeRequest,
  containsMaskedDisplay,
  isProfileChangeDate,
  isProfileChangePhone,
  listOwnProfileChangeRequests,
  normalizeProfileChangeText,
  type OwnProfileChangeRequest,
  type ProfileChangeField,
  type ProfileChangeRequestCreate,
  readOwnProfileChangeRequest,
  submitOwnProfileChangeRequest,
} from "@/lib/employee-profile-change-requests";
import type { SelfEmployeeProtectedValue } from "@/lib/self-employee-profile";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "../profile-change-requests/profile-change-requests.module.css";

const PAGE_LIMIT = 10;

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

type FieldMode = "unchanged" | "set" | "clear";
type OwnAction = "list" | "detail" | "submit" | "cancel";

interface OwnRequestBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
  employeeId: string;
}

interface OwnRequestError {
  message: string;
  reference: string | null;
  conflict: boolean;
}

interface OwnRequestListState {
  boundary: OwnRequestBoundary;
  requests: OwnProfileChangeRequest[];
  nextCursor: string | null;
  isLoading: boolean;
  isLoadingMore: boolean;
  error: OwnRequestError | null;
  pageError: OwnRequestError | null;
}

type PendingConfirmation =
  | { type: "submit"; payload: ProfileChangeRequestCreate }
  | { type: "cancel"; request: OwnProfileChangeRequest };

function isCurrentBoundary(
  expected: OwnRequestBoundary,
  current: OwnRequestBoundary,
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

function requestError(cause: unknown, action: OwnAction): OwnRequestError {
  let message =
    action === "list" || action === "detail"
      ? "Değişiklik talepleriniz şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : action === "submit"
        ? "Değişiklik talebiniz şu anda gönderilemiyor. Lütfen yeniden deneyin."
        : "Değişiklik talebiniz şu anda iptal edilemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Profil değişiklik talepleri mevcut rolleriniz için kullanılamıyor.";
  } else if (cause.status === 404) {
    message = "Talep bulunamadı veya artık erişilebilir değil.";
  } else if (cause.status === 409) {
    conflict = true;
    message =
      action === "submit"
        ? "Zaten değerlendirmede olan bir talebiniz var. Güncel talep geçmişini yükleyin."
        : "Talep siz işlem yaparken değişti. Güncel durumu yükleyip yeniden deneyin.";
  } else if (cause.status === 422 || cause.code === "invalid_response") {
    message =
      cause.code === "invalid_response"
        ? "Sunucudan beklenmeyen bir talep yanıtı alındı. Lütfen yeniden yükleyin."
        : "Gönderilecek alanları ve değer biçimlerini kontrol edin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference, conflict };
}

function appendUnique(
  current: OwnProfileChangeRequest[],
  incoming: OwnProfileChangeRequest[],
): OwnProfileChangeRequest[] {
  const requests = new Map(current.map((request) => [request.id, request]));
  for (const request of incoming) requests.set(request.id, request);
  return [...requests.values()];
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function protectedDisplay(
  value: SelfEmployeeProtectedValue,
  unavailableLabel = "Belirtilmemiş",
): string {
  return value.visibility === "masked" ? value.display_value : unavailableLabel;
}

function currentProtectedDisplay(value: SelfEmployeeProtectedValue): string {
  return value.visibility === "masked"
    ? `${value.display_value} · Maskeli`
    : "Belirtilmemiş";
}

function requestFields(request: OwnProfileChangeRequest): string {
  return request.changed_fields.map((field) => FIELD_LABELS[field]).join(", ");
}

function OwnRequestDetail({ request }: { request: OwnProfileChangeRequest }) {
  return (
    <div className={styles.ownDetail}>
      <dl className={styles.detailMetaGrid}>
        <div><dt>Durum</dt><dd>{STATUS_LABELS[request.status]}</dd></div>
        <div><dt>Gönderim</dt><dd>{formatTimestamp(request.submitted_at)}</dd></div>
        <div><dt>Değişen alanlar</dt><dd>{requestFields(request)}</dd></div>
        <div><dt>Talep sürümü</dt><dd>{request.version}</dd></div>
      </dl>
      <div className={styles.ownChangeList}>
        {request.changes.preferred_name ? (
          <div>
            <strong>Tercih edilen ad</strong>
            <span>{request.changes.preferred_name.previous_value ?? "Belirtilmemiş"}</span>
            <span aria-hidden="true">→</span>
            <span>{request.changes.preferred_name.proposed_value ?? "Temizlenecek"}</span>
          </div>
        ) : null}
        {request.changes.phone ? (
          <div>
            <strong>Telefon</strong>
            <span>{protectedDisplay(request.changes.phone.previous_value)}</span>
            <span aria-hidden="true">→</span>
            <span>{protectedDisplay(request.changes.phone.proposed_value, "Temizlenecek")}</span>
          </div>
        ) : null}
        {request.changes.birth_date ? (
          <div>
            <strong>Doğum tarihi</strong>
            <span>{protectedDisplay(request.changes.birth_date.previous_value)}</span>
            <span aria-hidden="true">→</span>
            <span>{protectedDisplay(request.changes.birth_date.proposed_value, "Temizlenecek")}</span>
          </div>
        ) : null}
      </div>
      {request.rejection_reason ? (
        <div className={styles.reasonBox}>
          <strong>Ret açıklaması</strong>
          <p>{request.rejection_reason}</p>
        </div>
      ) : null}
    </div>
  );
}

export function OwnProfileChangeRequests({
  employeeId,
  currentPreferredName,
  currentPhone,
  currentBirthDate,
}: {
  employeeId: string;
  currentPreferredName: string | null;
  currentPhone: SelfEmployeeProtectedValue;
  currentBirthDate: SelfEmployeeProtectedValue;
}) {
  const { user, sessionGeneration } = useSession();
  const canReadOwn = hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnEmployee);
  const boundary = useMemo<OwnRequestBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canReadOwn,
      employeeId,
    }),
    [
      canReadOwn,
      employeeId,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const latestBoundary = useRef(boundary);
  const listRequest = useRef(0);
  const pageRequest = useRef(0);
  const detailRequest = useRef(0);
  const mutationRequest = useRef(0);
  const mutationLock = useRef(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [state, setState] = useState<OwnRequestListState>(() => ({
    boundary,
    requests: [],
    nextCursor: null,
    isLoading: true,
    isLoadingMore: false,
    error: null,
    pageError: null,
  }));
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [preferredMode, setPreferredMode] = useState<FieldMode>("unchanged");
  const [phoneMode, setPhoneMode] = useState<FieldMode>("unchanged");
  const [birthDateMode, setBirthDateMode] = useState<FieldMode>("unchanged");
  const [preferredName, setPreferredName] = useState("");
  const [phone, setPhone] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [formError, setFormError] = useState<OwnRequestError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingConfirmation | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OwnProfileChangeRequest | null>(null);
  const [detailError, setDetailError] = useState<OwnRequestError | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => {
      listRequest.current += 1;
      pageRequest.current += 1;
      detailRequest.current += 1;
      mutationRequest.current += 1;
      mutationLock.current = false;
    };
  }, [boundary]);

  useEffect(() => {
    if (!boundary.permissionGranted) return;
    const requestId = ++listRequest.current;
    const requestBoundary = boundary;
    pageRequest.current += 1;
    void listOwnProfileChangeRequests({ limit: PAGE_LIMIT }, boundary.employeeId).then(
      (page) => {
        if (
          requestId !== listRequest.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          requests: page.data,
          nextCursor: page.meta.next_cursor,
          isLoading: false,
          isLoadingMore: false,
          error: null,
          pageError: null,
        });
      },
      (cause) => {
        if (
          requestId !== listRequest.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          requests: [],
          nextCursor: null,
          isLoading: false,
          isLoadingMore: false,
          error: requestError(cause, "list"),
          pageError: null,
        });
      },
    );
    return () => {
      listRequest.current += 1;
    };
  }, [boundary, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const requests = stateIsCurrent ? state.requests : [];
  const nextCursor = stateIsCurrent ? state.nextCursor : null;
  const error = stateIsCurrent ? state.error : null;
  const pageError = stateIsCurrent ? state.pageError : null;
  const isLoading = !stateIsCurrent || state.isLoading;
  const isLoadingMore = stateIsCurrent && state.isLoadingMore;
  const activeRequest = requests.find((request) => request.status === "submitted") ?? null;

  function reload() {
    detailRequest.current += 1;
    setState({
      boundary,
      requests: [],
      nextCursor: null,
      isLoading: true,
      isLoadingMore: false,
      error: null,
      pageError: null,
    });
    setSelectedRequestId(null);
    setDetail(null);
    setDetailError(null);
    setFormError(null);
    setNotice(null);
    setReloadKey((key) => key + 1);
  }

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    const requestBoundary = boundary;
    const requestId = ++pageRequest.current;
    setState((current) =>
      isCurrentBoundary(current.boundary, requestBoundary)
        ? { ...current, isLoadingMore: true, pageError: null }
        : current,
    );
    try {
      const page = await listOwnProfileChangeRequests({
        limit: PAGE_LIMIT,
        cursor: nextCursor,
      }, requestBoundary.employeeId);
      if (
        requestId !== pageRequest.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setState((current) =>
        isCurrentBoundary(current.boundary, requestBoundary)
          ? {
              ...current,
              requests: appendUnique(current.requests, page.data),
              nextCursor: page.meta.next_cursor,
              pageError: null,
            }
          : current,
      );
    } catch (cause) {
      if (
        requestId === pageRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setState((current) =>
          isCurrentBoundary(current.boundary, requestBoundary)
            ? { ...current, pageError: requestError(cause, "list") }
            : current,
        );
      }
    } finally {
      if (
        requestId === pageRequest.current &&
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

  async function openDetail(requestIdValue: string) {
    const requestBoundary = boundary;
    const requestId = ++detailRequest.current;
    setSelectedRequestId(requestIdValue);
    setDetail(null);
    setDetailError(null);
    setIsDetailLoading(true);
    try {
      const loaded = await readOwnProfileChangeRequest(
        requestIdValue,
        requestBoundary.employeeId,
      );
      if (
        requestId !== detailRequest.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setDetail(loaded);
    } catch (cause) {
      if (
        requestId === detailRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setDetailError(requestError(cause, "detail"));
      }
    } finally {
      if (
        requestId === detailRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setIsDetailLoading(false);
      }
    }
  }

  function resetForm() {
    setPreferredMode("unchanged");
    setPhoneMode("unchanged");
    setBirthDateMode("unchanged");
    setPreferredName("");
    setPhone("");
    setBirthDate("");
    setFormError(null);
  }

  function prepareSubmission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: ProfileChangeRequestCreate = {};
    let validationMessage: string | null = null;
    if (preferredMode === "set") {
      const value = normalizeProfileChangeText(preferredName);
      if (
        value.length < 1 ||
        value.length > 200 ||
        containsMaskedDisplay(value)
      ) {
        validationMessage = "Tercih edilen ad 1-200 karakter olmalı ve maskeli değer içermemelidir.";
      } else if (
        currentPreferredName !== null &&
        value === normalizeProfileChangeText(currentPreferredName)
      ) {
        validationMessage = "Tercih edilen ad mevcut değerle aynı. Bu alanı değiştirmeden bırakın.";
      } else {
        payload.preferred_name = value;
      }
    } else if (preferredMode === "clear") {
      if (currentPreferredName === null) {
        validationMessage = "Tercih edilen ad zaten boş. Bu alanı değiştirmeden bırakın.";
      } else {
        payload.preferred_name = null;
      }
    }

    if (!validationMessage && phoneMode === "set") {
      const value = phone.trim();
      if (!isProfileChangePhone(value)) {
        validationMessage = "Telefon numarasını geçerli bir uluslararası biçimde girin.";
      } else {
        payload.phone = value;
      }
    } else if (!validationMessage && phoneMode === "clear") {
      if (currentPhone.visibility === "unavailable") {
        validationMessage = "Telefon alanı zaten boş. Bu alanı değiştirmeden bırakın.";
      } else {
        payload.phone = null;
      }
    }

    if (!validationMessage && birthDateMode === "set") {
      if (!isProfileChangeDate(birthDate)) {
        validationMessage = "Doğum tarihini geçerli bir tarih olarak girin.";
      } else {
        payload.birth_date = birthDate;
      }
    } else if (!validationMessage && birthDateMode === "clear") {
      if (currentBirthDate.visibility === "unavailable") {
        validationMessage = "Doğum tarihi zaten boş. Bu alanı değiştirmeden bırakın.";
      } else {
        payload.birth_date = null;
      }
    }

    if (!validationMessage && Object.keys(payload).length === 0) {
      validationMessage = "Talep göndermek için en az bir alan seçin.";
    }
    if (validationMessage) {
      setFormError({ message: validationMessage, reference: null, conflict: false });
      return;
    }
    setFormError(null);
    setPendingConfirmation({ type: "submit", payload });
  }

  async function applyConfirmation() {
    const action = pendingConfirmation;
    if (!action || mutationLock.current || !boundary.permissionGranted) return;
    const requestBoundary = boundary;
    const requestId = ++mutationRequest.current;
    mutationLock.current = true;
    setIsMutating(true);
    setFormError(null);
    setNotice(null);
    try {
      const result =
        action.type === "submit"
          ? await submitOwnProfileChangeRequest(
              action.payload,
              requestBoundary.employeeId,
            )
          : await cancelOwnProfileChangeRequest(
              action.request.id,
              action.request.version,
              requestBoundary.employeeId,
            );
      if (
        requestId !== mutationRequest.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setState((current) => {
        if (!isCurrentBoundary(current.boundary, requestBoundary)) return current;
        const withoutResult = current.requests.filter(
          (request) => request.id !== result.id,
        );
        return { ...current, requests: [result, ...withoutResult] };
      });
      setDetail((current) => (current?.id === result.id ? result : current));
      setPendingConfirmation(null);
      if (action.type === "submit") {
        resetForm();
        setIsFormOpen(false);
        setNotice("Değişiklik talebiniz İK onayına gönderildi.");
      } else {
        setNotice("Değişiklik talebiniz iptal edildi.");
      }
    } catch (cause) {
      if (
        requestId === mutationRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setPendingConfirmation(null);
        setFormError(
          requestError(cause, action.type === "submit" ? "submit" : "cancel"),
        );
      }
    } finally {
      if (
        requestId === mutationRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        mutationLock.current = false;
        setIsMutating(false);
      }
    }
  }

  if (!boundary.permissionGranted) return null;

  return (
    <section className={styles.ownPanel} aria-labelledby="own-change-requests-title">
      <header className={styles.panelHeader}>
        <div>
          <span>İK onaylı self servis</span>
          <h2 id="own-change-requests-title">Profil değişiklik taleplerim</h2>
          <p>
            Yalnızca tercih edilen ad, telefon ve doğum tarihi için talep oluşturabilirsiniz.
            Değişiklikler İK onayı verilene kadar profilinize uygulanmaz.
          </p>
        </div>
        {!activeRequest && !isLoading ? (
          <button
            className={styles.primaryButton}
            type="button"
            onClick={() => {
              setNotice(null);
              setIsFormOpen((open) => !open);
            }}
          >
            {isFormOpen ? "Formu kapat" : "Değişiklik talebi oluştur"}
          </button>
        ) : null}
      </header>

      {notice ? <div className={styles.successAlert} role="status">{notice}</div> : null}
      {formError ? (
        <div className={styles.errorAlert} role="alert">
          <div>
            <strong>İşlem tamamlanamadı</strong>
            <span>{formError.message}</span>
            {formError.reference ? <small>Referans: {formError.reference}</small> : null}
          </div>
          {formError.conflict ? (
            <button className={styles.secondaryButton} type="button" onClick={reload}>
              Güncel talepleri yükle
            </button>
          ) : null}
        </div>
      ) : null}

      {activeRequest ? (
        <div className={styles.activeNotice} role="status">
          <div>
            <strong>Bir talebiniz değerlendirmede</strong>
            <span>{requestFields(activeRequest)} · {formatTimestamp(activeRequest.submitted_at)}</span>
          </div>
          <button
            className={styles.dangerTextButton}
            type="button"
            onClick={() => setPendingConfirmation({ type: "cancel", request: activeRequest })}
          >
            Talebi iptal et
          </button>
        </div>
      ) : null}

      {isFormOpen && !activeRequest ? (
        <form className={styles.requestForm} onSubmit={prepareSubmission}>
          <div className={styles.formGuidance} role="note">
            <strong>Değişmeyen alanları “Değiştirme” olarak bırakın.</strong>
            <span>Maskeli değerler düzenleme alanına taşınmaz. Temizleme işlemi ayrıca seçilmelidir.</span>
          </div>
          <div className={styles.requestFieldGrid}>
            <fieldset className={styles.requestField}>
              <legend>Tercih edilen ad</legend>
              <span>Mevcut: {currentPreferredName ?? "Belirtilmemiş"}</span>
              <label htmlFor="preferred_name_action">İşlem</label>
              <select
                id="preferred_name_action"
                value={preferredMode}
                disabled={isMutating}
                onChange={(event) => setPreferredMode(event.target.value as FieldMode)}
              >
                <option value="unchanged">Değiştirme</option>
                <option value="set">Yeni değer gir</option>
                <option value="clear">Alanı temizle</option>
              </select>
              {preferredMode === "set" ? (
                <>
                  <label htmlFor="preferred_name_value">Yeni tercih edilen ad</label>
                  <input
                    id="preferred_name_value"
                    value={preferredName}
                    minLength={1}
                    maxLength={200}
                    autoComplete="nickname"
                    disabled={isMutating}
                    onChange={(event) => setPreferredName(event.target.value)}
                  />
                </>
              ) : null}
            </fieldset>

            <fieldset className={styles.requestField}>
              <legend>Telefon</legend>
              <span>Mevcut: {currentProtectedDisplay(currentPhone)}</span>
              <label htmlFor="phone_action">İşlem</label>
              <select
                id="phone_action"
                value={phoneMode}
                disabled={isMutating}
                onChange={(event) => setPhoneMode(event.target.value as FieldMode)}
              >
                <option value="unchanged">Değiştirme</option>
                <option value="set">Yeni değer gir</option>
                <option value="clear">Alanı temizle</option>
              </select>
              {phoneMode === "set" ? (
                <>
                  <label htmlFor="phone_value">Yeni telefon</label>
                  <input
                    id="phone_value"
                    type="tel"
                    value={phone}
                    minLength={7}
                    maxLength={32}
                    autoComplete="tel"
                    placeholder="+90 555 111 22 33"
                    disabled={isMutating}
                    onChange={(event) => setPhone(event.target.value)}
                  />
                </>
              ) : null}
            </fieldset>

            <fieldset className={styles.requestField}>
              <legend>Doğum tarihi</legend>
              <span>Mevcut: {currentProtectedDisplay(currentBirthDate)}</span>
              <label htmlFor="birth_date_action">İşlem</label>
              <select
                id="birth_date_action"
                value={birthDateMode}
                disabled={isMutating}
                onChange={(event) => setBirthDateMode(event.target.value as FieldMode)}
              >
                <option value="unchanged">Değiştirme</option>
                <option value="set">Yeni değer gir</option>
                <option value="clear">Alanı temizle</option>
              </select>
              {birthDateMode === "set" ? (
                <>
                  <label htmlFor="birth_date_value">Yeni doğum tarihi</label>
                  <input
                    id="birth_date_value"
                    type="date"
                    value={birthDate}
                    disabled={isMutating}
                    onChange={(event) => setBirthDate(event.target.value)}
                  />
                </>
              ) : null}
            </fieldset>
          </div>
          <div className={styles.formActions}>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isMutating}
              onClick={() => {
                resetForm();
                setIsFormOpen(false);
              }}
            >
              Vazgeç
            </button>
            <button className={styles.primaryButton} type="submit" disabled={isMutating}>
              Talebi gözden geçir
            </button>
          </div>
        </form>
      ) : null}

      <section className={styles.historySection} aria-labelledby="own-change-history-title">
        <header>
          <div>
            <span>Durum ve geçmiş</span>
            <h3 id="own-change-history-title">Talep geçmişi</h3>
          </div>
          <button className={styles.secondaryButton} type="button" disabled={isLoading} onClick={reload}>
            Yenile
          </button>
        </header>
        {error ? (
          <div className={styles.errorState} role="alert">
            <strong>Talep geçmişi yüklenemedi</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
            <button className={styles.secondaryButton} type="button" onClick={reload}>Yeniden dene</button>
          </div>
        ) : isLoading ? (
          <div className={styles.loadingState} role="status" aria-live="polite">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Talep geçmişiniz yükleniyor</strong>
          </div>
        ) : requests.length === 0 ? (
          <div className={styles.emptyState} role="status">
            <strong>Henüz değişiklik talebiniz yok</strong>
            <p>İlk talebinizi oluşturduğunuzda değerlendirme durumu burada görünür.</p>
          </div>
        ) : (
          <div className={styles.ownHistoryList}>
            {requests.map((request) => (
              <article key={request.id}>
                <div>
                  <span className={`${styles.statusBadge} ${styles[`status_${request.status}`]}`}>
                    {STATUS_LABELS[request.status]}
                  </span>
                  <strong>{requestFields(request)}</strong>
                  <small>{formatTimestamp(request.submitted_at)}</small>
                </div>
                <div className={styles.historyActions}>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={() => void openDetail(request.id)}
                  >
                    Ayrıntıları göster
                  </button>
                  {request.status === "submitted" ? (
                    <button
                      className={styles.dangerTextButton}
                      type="button"
                      onClick={() => setPendingConfirmation({ type: "cancel", request })}
                    >
                      İptal et
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
        {pageError ? (
          <div className={styles.compactError} role="alert">
            <span>{pageError.message}</span>
            <button className={styles.secondaryButton} type="button" onClick={() => void loadMore()}>
              Yeniden dene
            </button>
          </div>
        ) : null}
        {nextCursor && !error ? (
          <button
            className={styles.loadMoreButton}
            type="button"
            disabled={isLoadingMore}
            onClick={() => void loadMore()}
          >
            {isLoadingMore ? "Daha fazla talep yükleniyor…" : "Daha fazla göster"}
          </button>
        ) : null}
      </section>

      {selectedRequestId ? (
        <section className={styles.detailDrawer} aria-labelledby="own-request-detail-title">
          <header>
            <div>
              <span>Talep ayrıntısı</span>
              <h3 id="own-request-detail-title">Değişiklik karşılaştırması</h3>
            </div>
            <button
              className={styles.iconButton}
              type="button"
              aria-label="Talep ayrıntısını kapat"
              onClick={() => {
                detailRequest.current += 1;
                setSelectedRequestId(null);
                setDetail(null);
                setDetailError(null);
              }}
            >
              ×
            </button>
          </header>
          {isDetailLoading ? (
            <div className={styles.loadingState} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <strong>Talep ayrıntısı yükleniyor</strong>
            </div>
          ) : detailError || !detail ? (
            <div className={styles.errorState} role="alert">
              <strong>Talep ayrıntısı yüklenemedi</strong>
              <span>{detailError?.message}</span>
              <button className={styles.secondaryButton} type="button" onClick={() => void openDetail(selectedRequestId)}>
                Yeniden dene
              </button>
            </div>
          ) : (
            <OwnRequestDetail request={detail} />
          )}
        </section>
      ) : null}

      {pendingConfirmation ? (
        <ProfileChangeConfirmationDialog
          title={
            pendingConfirmation.type === "submit"
              ? "Değişiklik talebi gönderilsin mi?"
              : "Değişiklik talebi iptal edilsin mi?"
          }
          description={
            pendingConfirmation.type === "submit" ? (
              <>
                <strong>Seçtiğiniz bilgiler İK değerlendirmesine gönderilecek.</strong>
                <p>Profiliniz onay verilene kadar değişmeyecek.</p>
              </>
            ) : (
              <>
                <strong>Değerlendirmedeki talep iptal edilecek.</strong>
                <p>Bu işlem profil bilgilerinizi değiştirmez.</p>
              </>
            )
          }
          confirmLabel={pendingConfirmation.type === "submit" ? "Talebi gönder" : "Talebi iptal et"}
          busyLabel={pendingConfirmation.type === "submit" ? "Talep gönderiliyor…" : "Talep iptal ediliyor…"}
          danger={pendingConfirmation.type === "cancel"}
          isBusy={isMutating}
          onCancel={() => {
            if (!isMutating) setPendingConfirmation(null);
          }}
          onConfirm={() => void applyConfirmation()}
        />
      ) : null}
    </section>
  );
}
