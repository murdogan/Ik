"use client";

import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  type EmployeeDocumentType,
  type OwnEmployeeDocument,
  listOwnEmployeeDocumentUploadTypes,
  readOwnEmployeeDocuments,
  uploadOwnEmployeeDocument,
} from "@/lib/employee-documents";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  cancelLeaveRequest,
  createLeaveRequest,
  type LeaveBalance,
  type LeaveLedgerEntry,
  type LeaveRequest,
  type LeaveType,
  listLeaveRequests,
  listLeaveTypes,
  listOwnLeaveBalanceHistory,
  listOwnLeaveBalances,
  readLeaveRequest,
} from "@/lib/leave";

import { LeaveConfirmationDialog } from "./leave-confirmation-dialog";
import {
  commandKey,
  formatLeaveDate,
  formatLeaveDays,
  formatLeaveLedgerEntry,
  formatLeaveTimelineEvent,
  formatLeaveTimestamp,
  leaveErrorPresentation,
  LEAVE_STATUS_LABELS,
  localDateValue,
  type LeaveErrorPresentation,
} from "./leave-presentation";
import styles from "./leave.module.css";

interface OwnBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  canRead: boolean;
  canCreate: boolean;
  canCancel: boolean;
  canReadDocuments: boolean;
  canUpload: boolean;
}

function appendUnique<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()];
}

function fileError(cause: unknown): LeaveErrorPresentation {
  if (cause instanceof TypeError) {
    return {
      message: "Belge PDF, JPG, JPEG veya PNG biçiminde ve seçilen türün boyut sınırı içinde olmalıdır.",
      reference: null,
      conflict: false,
    };
  }
  return leaveErrorPresentation(cause, "Belge yüklenemedi. Lütfen yeniden deneyin.");
}

export function OwnLeaveScreen() {
  const { user, sessionGeneration } = useSession();
  const boundary = useMemo<OwnBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      canRead: hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnLeave),
      canCreate: hasPermission(user, AUTHORIZATION_PERMISSIONS.createOwnLeave),
      canCancel: hasPermission(user, AUTHORIZATION_PERMISSIONS.cancelOwnLeave),
      canReadDocuments: hasPermission(
        user,
        AUTHORIZATION_PERMISSIONS.readOwnEmployeeDocuments,
      ),
      canUpload: hasPermission(
        user,
        AUTHORIZATION_PERMISSIONS.uploadOwnEmployeeDocuments,
      ),
    }),
    [
      sessionGeneration,
      user,
    ],
  );
  const boundaryKey = `${boundary.sessionGeneration}:${boundary.userId}:${boundary.membershipId}:${boundary.tenantId}:${boundary.permissionVersion}:${boundary.canRead}:${boundary.canCreate}:${boundary.canCancel}:${boundary.canReadDocuments}:${boundary.canUpload}`;
  return <OwnLeaveContent key={boundaryKey} boundary={boundary} />;
}

function OwnLeaveContent({ boundary }: { boundary: OwnBoundary }) {
  const currentYear = new Date().getFullYear();
  const [periodYear, setPeriodYear] = useState(currentYear);
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [requestCursor, setRequestCursor] = useState<string | null>(null);
  const [ledger, setLedger] = useState<LeaveLedgerEntry[]>([]);
  const [ledgerCursor, setLedgerCursor] = useState<string | null>(null);
  const [uploadTypes, setUploadTypes] = useState<EmployeeDocumentType[]>([]);
  const [availableDocuments, setAvailableDocuments] = useState<OwnEmployeeDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMoreRequests, setIsLoadingMoreRequests] = useState(false);
  const [isLoadingMoreLedger, setIsLoadingMoreLedger] = useState(false);
  const [isLoadingUploadTypes, setIsLoadingUploadTypes] = useState(false);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isLoadingPolicy, setIsLoadingPolicy] = useState(true);
  const [error, setError] = useState<LeaveErrorPresentation | null>(null);
  const [pageError, setPageError] = useState<LeaveErrorPresentation | null>(null);
  const [policyError, setPolicyError] = useState<LeaveErrorPresentation | null>(null);
  const [documentError, setDocumentError] = useState<LeaveErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [startDate, setStartDate] = useState(localDateValue());
  const [endDate, setEndDate] = useState(localDateValue());
  const [employeeNote, setEmployeeNote] = useState("");
  const [uploadTypeId, setUploadTypeId] = useState("");
  const [documentExpiresOn, setDocumentExpiresOn] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [pendingDocumentId, setPendingDocumentId] = useState<string | null>(null);
  const [documentReloadKey, setDocumentReloadKey] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<LeaveRequest | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [detail, setDetail] = useState<LeaveRequest | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const requestCommandKey = useRef<string | null>(null);
  const cancelCommandKey = useRef<{ requestId: string; key: string } | null>(null);
  const mutationLock = useRef(false);
  const requestListGeneration = useRef(0);
  const ledgerGeneration = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!boundary.canRead) return;
    let active = true;
    const requestsGeneration = ++requestListGeneration.current;
    const historyGeneration = ++ledgerGeneration.current;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
      setPageError(null);
      void Promise.all([
        listOwnLeaveBalances(periodYear),
        listLeaveRequests({ scope: "own", limit: 25 }),
        listOwnLeaveBalanceHistory(null, 25),
      ]).then(
        ([balanceRows, requestPage, ledgerPage]) => {
          if (
            !active ||
            requestListGeneration.current !== requestsGeneration ||
            ledgerGeneration.current !== historyGeneration
          ) return;
          setBalances(balanceRows);
          setRequests(requestPage.data);
          setRequestCursor(requestPage.nextCursor);
          setLedger(ledgerPage.data);
          setLedgerCursor(ledgerPage.nextCursor);
          setError(null);
          setIsLoading(false);
        },
        (cause) => {
          if (
            !active ||
            requestListGeneration.current !== requestsGeneration ||
            ledgerGeneration.current !== historyGeneration
          ) return;
          setError(
            leaveErrorPresentation(
              cause,
              "İzin çalışma alanınız şu anda yüklenemiyor. Lütfen yeniden deneyin.",
            ),
          );
          setIsLoading(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canRead, periodYear, reloadKey]);

  const selectedType = leaveTypes.find((item) => item.id === leaveTypeId) ?? null;
  const documentRequired = selectedType?.current_policy?.document_required ?? false;
  const selectedUploadType =
    uploadTypes.find((item) => item.id === uploadTypeId) ?? null;
  const attachableDocuments = availableDocuments.filter(
    (document) => !document.expires_on || document.expires_on >= endDate,
  );
  const uploadAccept = selectedUploadType
    ? [
        ...selectedUploadType.allowed_extensions.map((extension) => `.${extension}`),
        ...selectedUploadType.allowed_mime_types,
      ].join(",")
    : undefined;

  useEffect(() => {
    if (!boundary.canRead || !startDate) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoadingPolicy(true);
      void listLeaveTypes(false, startDate).then(
        (types) => {
          if (!active) return;
          setLeaveTypes(types.filter((item) => item.is_active));
          setLeaveTypeId((current) =>
            current && types.some((item) => item.id === current && item.is_active)
              ? current
              : types.find((item) => item.is_active)?.id ?? "",
          );
          setPolicyError(null);
          setIsLoadingPolicy(false);
        },
        (cause) => {
          if (!active) return;
          setLeaveTypes([]);
          setLeaveTypeId("");
          setPolicyError(
            leaveErrorPresentation(
              cause,
              "Seçilen başlangıç tarihindeki izin politikaları yüklenemedi.",
            ),
          );
          setIsLoadingPolicy(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canRead, reloadKey, startDate]);

  useEffect(() => {
    if (!documentRequired || !boundary.canUpload) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoadingUploadTypes(true);
      void listOwnEmployeeDocumentUploadTypes().then(
        (types) => {
          if (!active) return;
          const available = types.filter((item) => item.archived_at === null);
          setUploadTypes(available);
          setUploadTypeId((current) =>
            current && available.some((item) => item.id === current)
              ? current
              : available[0]?.id ?? "",
          );
          setDocumentError(null);
          setIsLoadingUploadTypes(false);
        },
        (cause) => {
          if (!active) return;
          setDocumentError(fileError(cause));
          setIsLoadingUploadTypes(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canUpload, documentRequired, reloadKey]);

  useEffect(() => {
    if (!documentRequired || !boundary.canReadDocuments) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoadingDocuments(true);
      void readOwnEmployeeDocuments().then(
        (workspace) => {
          if (!active) return;
          const documents = workspace.documents;
          const attachable = documents.filter(
            (document) => !document.expires_on || document.expires_on >= endDate,
          );
          const scannedPending = pendingDocumentId
            ? documents.find((item) => item.id === pendingDocumentId) ?? null
            : null;
          const attachablePending = scannedPending
            ? attachable.find((item) => item.id === scannedPending.id) ?? null
            : null;
          setAvailableDocuments(documents);
          setDocumentId((current) =>
            current && attachable.some((item) => item.id === current)
              ? current
              : attachablePending?.id ?? null,
          );
          if (scannedPending) {
            setPendingDocumentId(null);
            setNotice(
              attachablePending
                ? "Belge güvenlik taramasını tamamladı ve talebe bağlanmaya hazır."
                : "Belge taramayı tamamladı ancak geçerlilik tarihi izin bitişini karşılamıyor.",
            );
          }
          setDocumentError(null);
          setIsLoadingDocuments(false);
        },
        (cause) => {
          if (!active) return;
          setDocumentError(
            leaveErrorPresentation(
              cause,
              "Taranmış özlük belgeleriniz yüklenemedi.",
            ),
          );
          setIsLoadingDocuments(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [
    boundary.canReadDocuments,
    documentReloadKey,
    documentRequired,
    endDate,
    pendingDocumentId,
    reloadKey,
  ]);

  function invalidateRequestKey() {
    requestCommandKey.current = null;
    setNotice(null);
  }

  function reload() {
    requestListGeneration.current += 1;
    ledgerGeneration.current += 1;
    setError(null);
    setPageError(null);
    setPolicyError(null);
    setDocumentError(null);
    setDetail(null);
    setReloadKey((key) => key + 1);
  }

  async function loadMoreRequests() {
    if (!requestCursor || isLoadingMoreRequests) return;
    const generation = requestListGeneration.current;
    setIsLoadingMoreRequests(true);
    setPageError(null);
    try {
      const page = await listLeaveRequests({
        scope: "own",
        cursor: requestCursor,
        limit: 25,
      });
      if (requestListGeneration.current !== generation) return;
      setRequests((current) => appendUnique(current, page.data));
      setRequestCursor(page.nextCursor);
    } catch (cause) {
      if (requestListGeneration.current !== generation) return;
      setPageError(leaveErrorPresentation(cause));
    } finally {
      setIsLoadingMoreRequests(false);
    }
  }

  async function loadMoreLedger() {
    if (!ledgerCursor || isLoadingMoreLedger) return;
    const generation = ledgerGeneration.current;
    setIsLoadingMoreLedger(true);
    setPageError(null);
    try {
      const page = await listOwnLeaveBalanceHistory(ledgerCursor, 25);
      if (ledgerGeneration.current !== generation) return;
      setLedger((current) => appendUnique(current, page.data));
      setLedgerCursor(page.nextCursor);
    } catch (cause) {
      if (ledgerGeneration.current !== generation) return;
      setPageError(leaveErrorPresentation(cause));
    } finally {
      setIsLoadingMoreLedger(false);
    }
  }

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutationLock.current || !boundary.canCreate || !selectedType) return;
    if (!selectedType.current_policy) {
      setPageError({
        message: "Seçilen izin türü için yürürlükte bir politika bulunmuyor.",
        reference: null,
        conflict: false,
      });
      return;
    }
    if (endDate < startDate) {
      setPageError({
        message: "Bitiş tarihi başlangıç tarihinden önce olamaz.",
        reference: null,
        conflict: false,
      });
      return;
    }
    if (
      documentRequired &&
      documentId &&
      !attachableDocuments.some((document) => document.id === documentId)
    ) {
      setPageError({
        message: "Seçilen belgenin geçerlilik tarihi izin bitişini karşılamıyor.",
        reference: null,
        conflict: false,
      });
      return;
    }
    if (documentRequired && !documentId && pendingDocumentId) {
      setPageError({
        message: "Yüklenen belgenin güvenlik taraması tamamlanmadan talep gönderilemez.",
        reference: null,
        conflict: false,
      });
      return;
    }
    if (documentRequired && !documentId && (!file || !uploadTypeId)) {
      setPageError({
        message: "Bu izin türü için belge seçip yüklemeniz gerekiyor.",
        reference: null,
        conflict: false,
      });
      return;
    }
    if (
      documentRequired &&
      !documentId &&
      selectedUploadType?.expiry_mode === "required" &&
      !documentExpiresOn
    ) {
      setPageError({
        message: "Seçilen belge türü için son geçerlilik tarihi zorunludur.",
        reference: null,
        conflict: false,
      });
      return;
    }
    if (
      documentRequired &&
      !documentId &&
      documentExpiresOn &&
      documentExpiresOn < endDate
    ) {
      setPageError({
        message: "Belgenin son geçerlilik tarihi izin bitiş tarihinden önce olamaz.",
        reference: null,
        conflict: false,
      });
      return;
    }

    mutationLock.current = true;
    setIsSubmitting(true);
    setPageError(null);
    setNotice(null);
    let phase: "upload" | "request" = documentRequired && !documentId ? "upload" : "request";
    try {
      let attachedDocumentId = documentId;
      if (documentRequired && !attachedDocumentId && file) {
        const uploadType = uploadTypes.find((item) => item.id === uploadTypeId);
        const extension = file.name.split(".").pop()?.toLocaleLowerCase("en-US") ?? "";
        if (
          !uploadType ||
          file.size > uploadType.max_size_bytes ||
          !uploadType.allowed_extensions.includes(
            extension as (typeof uploadType.allowed_extensions)[number],
          ) ||
          (file.type !== "" &&
            !uploadType.allowed_mime_types.includes(
              file.type as (typeof uploadType.allowed_mime_types)[number],
            ))
        ) {
          throw new TypeError("Invalid leave attachment");
        }
        const document = await uploadOwnEmployeeDocument(file, {
          documentTypeId: uploadType.id,
          issuedOn: null,
          expiresOn: uploadType.expiry_mode === "none" ? null : documentExpiresOn || null,
          employeeVisible: true,
        });
        if (document.processing_state !== "available") {
          setPendingDocumentId(document.id);
          setDocumentId(null);
          setFile(null);
          requestCommandKey.current = null;
          if (fileInputRef.current) fileInputRef.current.value = "";
          setNotice(
            "Belge yüklendi ve güvenlik taraması bekliyor. Tarama tamamlandıktan sonra belgeleri yenileyip talebi gönderin.",
          );
          setDocumentReloadKey((value) => value + 1);
          return;
        }
        attachedDocumentId = document.id;
        setDocumentId(document.id);
      }
      phase = "request";
      const key = requestCommandKey.current ?? commandKey();
      requestCommandKey.current = key;
      const created = await createLeaveRequest(
        {
          leave_type_id: selectedType.id,
          start_date: startDate,
          end_date: endDate,
          ...(employeeNote.trim() ? { employee_note: employeeNote.trim() } : {}),
          ...(attachedDocumentId ? { document_id: attachedDocumentId } : {}),
        },
        key,
      );
      setRequests((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      requestListGeneration.current += 1;
      ledgerGeneration.current += 1;
      setNotice(
        `İzin talebiniz oluşturuldu. Sunucu ${formatLeaveDays(created.counted_days)} çalışma günü hesapladı.`,
      );
      setEmployeeNote("");
      setFile(null);
      setDocumentId(null);
      setPendingDocumentId(null);
      setDocumentExpiresOn("");
      requestCommandKey.current = null;
      if (fileInputRef.current) fileInputRef.current.value = "";
      setReloadKey((keyValue) => keyValue + 1);
    } catch (cause) {
      setPageError(phase === "upload" ? fileError(cause) : leaveErrorPresentation(cause));
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status < 500
      ) {
        requestCommandKey.current = null;
      }
    } finally {
      mutationLock.current = false;
      setIsSubmitting(false);
    }
  }

  async function openDetail(request: LeaveRequest) {
    if (isLoadingDetail) return;
    setIsLoadingDetail(true);
    setPageError(null);
    try {
      setDetail(await readLeaveRequest(request.id));
    } catch (cause) {
      setPageError(leaveErrorPresentation(cause));
    } finally {
      setIsLoadingDetail(false);
    }
  }

  async function confirmCancel() {
    const target = cancelTarget;
    if (!target || mutationLock.current || !boundary.canCancel) return;
    mutationLock.current = true;
    setIsCancelling(true);
    setPageError(null);
    const key = cancelCommandKey.current?.requestId === target.id
      ? cancelCommandKey.current.key
      : commandKey();
    cancelCommandKey.current = { requestId: target.id, key };
    try {
      const cancelled = await cancelLeaveRequest(
        target.id,
        target.version,
        null,
        key,
      );
      setRequests((current) =>
        current.map((item) => (item.id === cancelled.id ? cancelled : item)),
      );
      requestListGeneration.current += 1;
      ledgerGeneration.current += 1;
      if (detail?.id === cancelled.id) setDetail(cancelled);
      setCancelTarget(null);
      cancelCommandKey.current = null;
      setNotice("İzin talebi iptal edildi; bakiye ve planlanan kullanım güncellendi.");
      setReloadKey((value) => value + 1);
    } catch (cause) {
      const presentation = leaveErrorPresentation(cause);
      setPageError(presentation);
      setCancelTarget(null);
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status < 500
      ) {
        cancelCommandKey.current = null;
      }
      if (presentation.conflict) reload();
    } finally {
      mutationLock.current = false;
      setIsCancelling(false);
    }
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setDocumentId(null);
    requestCommandKey.current = null;
  }

  const visiblePageError = pageError ?? policyError ?? documentError;

  if (!boundary.canRead) return null;

  return (
    <section className={styles.page} aria-labelledby="own-leave-title">
      <header className={styles.pageHeader}>
        <div>
          <span>Çalışan izin alanı</span>
          <h1 id="own-leave-title">İzinlerim</h1>
          <p>
            Güncel izin bakiyelerinizi görün, çalışma takvimine göre yeni talep oluşturun ve
            geçmiş hareketlerinizi izleyin.
          </p>
        </div>
        <div className={styles.yearControl}>
          <label htmlFor="leave-period-year">Bakiye yılı</label>
          <select
            id="leave-period-year"
            value={periodYear}
            disabled={isLoading}
            onChange={(event) => setPeriodYear(Number(event.target.value))}
          >
            {[currentYear - 1, currentYear, currentYear + 1].map((year) => (
              <option value={year} key={year}>{year}</option>
            ))}
          </select>
        </div>
      </header>

      {error ? (
        <div className={styles.pageError} role="alert">
          <div>
            <strong>İzin alanı yüklenemedi</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button className={styles.secondaryButton} type="button" onClick={reload}>Yeniden dene</button>
        </div>
      ) : isLoading ? (
        <div className={styles.pageLoading} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div><strong>İzin çalışma alanınız hazırlanıyor</strong><span>Bakiyeler ve talepler güvenli biçimde yükleniyor…</span></div>
        </div>
      ) : (
        <>
          {visiblePageError ? (
            <div className={styles.inlineError} role="alert">
              <div><strong>İşlem tamamlanamadı</strong><span>{visiblePageError.message}</span>{visiblePageError.reference ? <small>Referans: {visiblePageError.reference}</small> : null}</div>
              {visiblePageError.conflict ? <button className={styles.secondaryButton} type="button" onClick={reload}>Güncel durumu yükle</button> : null}
            </div>
          ) : null}
          {notice ? <div className={styles.successNotice} role="status">{notice}</div> : null}

          <section className={styles.sectionCard} aria-labelledby="balance-title">
            <header className={styles.sectionHeader}>
              <div><span>Bakiye görünümü</span><h2 id="balance-title">{periodYear} izin bakiyeleri</h2><p>Tutarlar append-only hareketlerden türetilir; kullanılabilir bakiye sunucunun güncel okuma modelidir.</p></div>
              <button className={styles.textButton} type="button" onClick={reload}>Yenile</button>
            </header>
            {balances.length === 0 ? (
              <div className={styles.emptyState}><span aria-hidden="true">B</span><div><strong>Bu yıl için bakiye hareketi yok</strong><p>İK açılış bakiyesi tanımladığında izin türü burada görünür.</p></div></div>
            ) : (
              <div className={styles.balanceGrid}>
                {balances.map((balance) => (
                  <article className={styles.balanceCard} key={`${balance.leave_type_id}:${balance.period_year}`}>
                    <header><div><span>{balance.leave_type_code}</span><h3>{balance.leave_type_name}</h3></div><strong>{formatLeaveDays(balance.available_days)}<small> gün</small></strong></header>
                    <dl>
                      <div><dt>Kazanılan</dt><dd>{formatLeaveDays(balance.earned_days)}</dd></div>
                      <div><dt>Düzeltme</dt><dd>{formatLeaveDays(balance.adjusted_days)}</dd></div>
                      <div><dt>Kullanılan</dt><dd>{formatLeaveDays(balance.used_days)}</dd></div>
                      <div><dt>Planlanan</dt><dd>{formatLeaveDays(balance.planned_days)}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
            )}
          </section>

          {boundary.canCreate ? (
            <section className={styles.sectionCard} aria-labelledby="request-form-title">
              <header className={styles.sectionHeader}><div><span>Yeni izin</span><h2 id="request-form-title">İzin talebi oluştur</h2><p>Kesin çalışma günü, resmi tatil, hafta sonu, çakışma ve bakiye kontrolleri sunucuda yapılır.</p></div></header>
              <form className={styles.leaveForm} onSubmit={submitRequest}>
                <div className={styles.formGrid}>
                  <div className={styles.formField}><label htmlFor="own-leave-type">İzin türü</label><select id="own-leave-type" value={leaveTypeId} disabled={isSubmitting || isLoadingPolicy} required onChange={(event) => { setLeaveTypeId(event.target.value); setFile(null); setDocumentId(null); setPendingDocumentId(null); setDocumentExpiresOn(""); if (fileInputRef.current) fileInputRef.current.value = ""; invalidateRequestKey(); }}><option value="">{isLoadingPolicy ? "Politikalar yükleniyor…" : "İzin türü seçin"}</option>{leaveTypes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></div>
                  <div className={styles.formField}><label htmlFor="own-leave-start">Başlangıç</label><input id="own-leave-start" type="date" value={startDate} disabled={isSubmitting} required onChange={(event) => { setStartDate(event.target.value); setFile(null); setDocumentId(null); setPendingDocumentId(null); setDocumentExpiresOn(""); if (fileInputRef.current) fileInputRef.current.value = ""; invalidateRequestKey(); }} /></div>
                  <div className={styles.formField}><label htmlFor="own-leave-end">Bitiş</label><input id="own-leave-end" type="date" value={endDate} min={startDate} disabled={isSubmitting} required onChange={(event) => { const nextEndDate = event.target.value; setEndDate(nextEndDate); if (documentId && !availableDocuments.some((document) => document.id === documentId && (!document.expires_on || document.expires_on >= nextEndDate))) setDocumentId(null); invalidateRequestKey(); }} /></div>
                  <div className={`${styles.formField} ${styles.wideField}`}><label htmlFor="own-leave-note">Çalışan notu (isteğe bağlı)</label><textarea id="own-leave-note" value={employeeNote} rows={3} maxLength={1000} disabled={isSubmitting} onChange={(event) => { setEmployeeNote(event.target.value); requestCommandKey.current = null; }} placeholder="Yalnız gerekli, kısa ve işlemsel bilgiyi paylaşın." /><small>{employeeNote.length}/1000</small></div>
                </div>

                {selectedType ? (
                  <div className={styles.policySummary}>
                    <strong>{selectedType.current_policy ? "Yürürlükteki politika" : "Politika bulunamadı"}</strong>
                    {selectedType.current_policy ? <span>{selectedType.current_policy.paid ? "Ücretli" : "Ücretsiz"} · {selectedType.current_policy.document_required ? "Belge zorunlu" : "Belge gerekmiyor"} · {selectedType.current_policy.negative_balance_allowed ? "Negatif bakiye açık" : "Negatif bakiye kapalı"}</span> : <span>Bu izin türü politika tanımlanana kadar talep edilemez.</span>}
                  </div>
                ) : null}

                {documentRequired ? (
                  <fieldset className={styles.attachmentPanel} disabled={isSubmitting}>
                    <legend>Zorunlu belge</legend>
                    {boundary.canReadDocuments ? (
                      isLoadingDocuments ? (
                        <p role="status">Taranmış belgeleriniz yükleniyor…</p>
                      ) : availableDocuments.length > 0 ? (
                        <div className={styles.formField}>
                          <label htmlFor="own-available-document">Taraması tamamlanmış belge</label>
                          <select
                            id="own-available-document"
                            value={documentId ?? ""}
                            onChange={(event) => {
                              const nextDocumentId = event.target.value || null;
                              setDocumentId(nextDocumentId);
                              if (nextDocumentId) setPendingDocumentId(null);
                              setFile(null);
                              if (fileInputRef.current) fileInputRef.current.value = "";
                              invalidateRequestKey();
                            }}
                          >
                            <option value="">Yeni belge yükle</option>
                            {availableDocuments.map((document) => (
                              <option
                                value={document.id}
                                disabled={!attachableDocuments.some((item) => item.id === document.id)}
                                key={document.id}
                              >
                                {document.document_type_name} · {document.display_filename} · {document.expires_on ? `${formatLeaveDate(document.expires_on)} tarihine kadar` : "süresiz"}
                              </option>
                            ))}
                          </select>
                          {documentId ? <small>Yalnız seçilen güvenli belge kimliği talebe bağlanır.</small> : null}
                          {attachableDocuments.length === 0 ? <small>Mevcut belgelerin geçerlilik tarihi izin bitişini karşılamıyor; yeni belge yükleyin.</small> : null}
                        </div>
                      ) : (
                        <p>Talebe bağlanabilecek, güvenlik taraması tamamlanmış belgeniz bulunmuyor.</p>
                      )
                    ) : (
                      <p role="alert">Taranmış özlük belgelerini okuma yetkiniz bulunmuyor. İK ile iletişime geçin.</p>
                    )}

                    {pendingDocumentId ? (
                      <div className={styles.pendingDocument} role="status">
                        <div>
                          <strong>Belge güvenlik taraması bekliyor</strong>
                          <p>Tarama tamamlanmadan belge izin talebine bağlanamaz.</p>
                        </div>
                        <div className={styles.inlineActions}>
                          <button className={styles.secondaryButton} type="button" disabled={isLoadingDocuments} onClick={() => setDocumentReloadKey((value) => value + 1)}>Belgeleri yenile</button>
                          <button className={styles.textButton} type="button" onClick={() => { setPendingDocumentId(null); setDocumentError(null); }}>Bekleme durumunu temizle</button>
                        </div>
                      </div>
                    ) : null}

                    {!documentId && !pendingDocumentId && (!boundary.canUpload || !boundary.canReadDocuments) ? (
                      <p role="alert">Yeni belgeyi tarama sonrasında seçebilmek için özlük belgesi okuma ve yükleme yetkileri gereklidir.</p>
                    ) : !documentId && !pendingDocumentId && isLoadingUploadTypes ? (
                      <p role="status">Belge yükleme seçenekleri hazırlanıyor…</p>
                    ) : !documentId && !pendingDocumentId && uploadTypes.length === 0 ? (
                      <p role="alert">Kullanılabilir belge türü bulunmuyor. İK ile iletişime geçin.</p>
                    ) : !documentId && !pendingDocumentId ? (
                      <div className={styles.attachmentGrid}>
                        <div className={styles.formField}>
                          <label htmlFor="own-upload-type">Belge türü</label>
                          <select
                            id="own-upload-type"
                            value={uploadTypeId}
                            required
                            onChange={(event) => {
                              setUploadTypeId(event.target.value);
                              setFile(null);
                              setDocumentExpiresOn("");
                              if (fileInputRef.current) fileInputRef.current.value = "";
                              invalidateRequestKey();
                            }}
                          >
                            {uploadTypes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
                          </select>
                        </div>
                        <div className={styles.formField}>
                          <label htmlFor="own-leave-file">Dosya</label>
                          <input
                            ref={fileInputRef}
                            id="own-leave-file"
                            type="file"
                            accept={uploadAccept}
                            required
                            onChange={selectFile}
                          />
                          {file ? (
                            <small>{file.name} · {(file.size / (1024 * 1024)).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB</small>
                          ) : selectedUploadType ? (
                            <small>En fazla {(selectedUploadType.max_size_bytes / (1024 * 1024)).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB · {selectedUploadType.allowed_extensions.map((item) => item.toLocaleUpperCase("tr-TR")).join(", ")}</small>
                          ) : null}
                        </div>
                        {selectedUploadType && selectedUploadType.expiry_mode !== "none" ? (
                          <div className={styles.formField}>
                            <label htmlFor="own-document-expiry">
                              Son geçerlilik tarihi{selectedUploadType.expiry_mode === "required" ? "" : " (isteğe bağlı)"}
                            </label>
                            <input
                              id="own-document-expiry"
                              type="date"
                              value={documentExpiresOn}
                              min={endDate}
                              required={selectedUploadType.expiry_mode === "required"}
                              onChange={(event) => {
                                setDocumentExpiresOn(event.target.value);
                                invalidateRequestKey();
                              }}
                            />
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    <small>Yeni belge önce güvenli özlük alanına yüklenir. Zararlı yazılım taraması tamamlandıktan sonra taranmış belge listesinden talebe bağlanabilir.</small>
                  </fieldset>
                ) : null}

                <div className={styles.formActions}><button className={styles.primaryButton} type="submit" disabled={isSubmitting || isLoadingPolicy || !selectedType?.current_policy || (documentRequired && (isLoadingDocuments || (!documentId && (pendingDocumentId !== null || isLoadingUploadTypes || !boundary.canReadDocuments || !boundary.canUpload || uploadTypes.length === 0))))}>{isSubmitting ? documentRequired && !documentId ? "Belge yükleniyor…" : "Talep gönderiliyor…" : "İzin talebini gönder"}</button></div>
              </form>
            </section>
          ) : null}

          <section className={styles.sectionCard} aria-labelledby="request-history-title">
            <header className={styles.sectionHeader}><div><span>Talep geçmişi</span><h2 id="request-history-title">İzin taleplerim</h2><p>Kararlar ve iptaller ürün güvenli zaman çizelgesiyle birlikte korunur.</p></div></header>
            {requests.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">T</span><div><strong>Henüz izin talebiniz yok</strong><p>İlk talebiniz oluşturulduğunda burada görünür.</p></div></div> : <div className={styles.cardList}>{requests.map((request) => <article className={styles.requestCard} key={request.id}><header><div><span>{request.leave_type_code}</span><h3>{request.leave_type_name}</h3></div><span className={styles.statusBadge} data-status={request.status}>{LEAVE_STATUS_LABELS[request.status]}</span></header><dl><div><dt>Tarih</dt><dd>{formatLeaveDate(request.start_date)} – {formatLeaveDate(request.end_date)}</dd></div><div><dt>Çalışma günü</dt><dd>{formatLeaveDays(request.counted_days)}</dd></div><div><dt>Oluşturma</dt><dd>{formatLeaveTimestamp(request.created_at)}</dd></div><div><dt>Belge</dt><dd>{request.has_document ? "Bağlı" : "Yok"}</dd></div></dl><footer><button className={styles.textButton} type="button" disabled={isLoadingDetail} onClick={() => void openDetail(request)}>{isLoadingDetail && detail?.id === request.id ? "Yükleniyor…" : "Ayrıntıyı aç"}</button>{boundary.canCancel && (request.status === "pending" || request.status === "approved") ? <button className={styles.dangerTextButton} type="button" disabled={isCancelling} onClick={() => { if (cancelCommandKey.current?.requestId !== request.id) cancelCommandKey.current = { requestId: request.id, key: commandKey() }; setCancelTarget(request); }}>İptal et</button> : null}</footer></article>)}</div>}
            {requestCursor ? <div className={styles.loadMore}><button className={styles.secondaryButton} type="button" disabled={isLoadingMoreRequests} onClick={() => void loadMoreRequests()}>{isLoadingMoreRequests ? "Talepler yükleniyor…" : "Daha fazla talep göster"}</button></div> : null}
          </section>

          {detail ? (
            <section className={styles.detailPanel} aria-labelledby="own-request-detail-title">
              <header><div><span>Talep ayrıntısı</span><h2 id="own-request-detail-title">{detail.leave_type_name}</h2></div><button className={styles.iconButton} type="button" aria-label="Talep ayrıntısını kapat" onClick={() => setDetail(null)}>×</button></header>
              <div className={styles.detailBody}><dl className={styles.detailGrid}><div><dt>Durum</dt><dd>{LEAVE_STATUS_LABELS[detail.status]}</dd></div><div><dt>Tarih aralığı</dt><dd>{formatLeaveDate(detail.start_date)} – {formatLeaveDate(detail.end_date)}</dd></div><div><dt>Çalışma günü</dt><dd>{formatLeaveDays(detail.counted_days)}</dd></div><div><dt>Sürüm</dt><dd>{detail.version}</dd></div></dl>{detail.employee_note ? <div className={styles.noteBox}><strong>Çalışan notu</strong><p>{detail.employee_note}</p></div> : null}{detail.decision_note ? <div className={styles.noteBox}><strong>Karar notu</strong><p>{detail.decision_note}</p></div> : null}<ol className={styles.timeline}>{detail.timeline.map((item) => <li key={item.id}><span aria-hidden="true" /><div><strong>{formatLeaveTimelineEvent(item.event_type)}</strong><time>{formatLeaveTimestamp(item.occurred_at)}</time></div></li>)}</ol></div>
            </section>
          ) : null}

          <section className={styles.sectionCard} aria-labelledby="ledger-title">
            <header className={styles.sectionHeader}><div><span>Append-only geçmiş</span><h2 id="ledger-title">Bakiye hareketlerim</h2><p>Kazanım, düzeltme, kullanım ve planlama hareketleri geçmişten silinmeden gösterilir.</p></div></header>
            {ledger.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">H</span><div><strong>Henüz bakiye hareketi yok</strong><p>Açılış veya izin hareketi oluştuğunda burada görünür.</p></div></div> : <div className={styles.tableScroller}><table className={styles.dataTable}><thead><tr><th scope="col">Tarih</th><th scope="col">İzin türü</th><th scope="col">Hareket</th><th scope="col">Yıl</th><th scope="col">Gün</th></tr></thead><tbody>{ledger.map((entry) => <tr key={entry.id}><td data-label="Tarih">{formatLeaveDate(entry.effective_date)}</td><td data-label="İzin türü"><strong>{entry.leave_type_name ?? entry.leave_type_code ?? "İzin"}</strong></td><td data-label="Hareket">{formatLeaveLedgerEntry(entry.entry_type)}</td><td data-label="Yıl">{entry.period_year}</td><td data-label="Gün"><strong>{entry.amount_days > 0 ? "+" : ""}{formatLeaveDays(entry.amount_days)}</strong></td></tr>)}</tbody></table></div>}
            {ledgerCursor ? <div className={styles.loadMore}><button className={styles.secondaryButton} type="button" disabled={isLoadingMoreLedger} onClick={() => void loadMoreLedger()}>{isLoadingMoreLedger ? "Hareketler yükleniyor…" : "Daha fazla hareket göster"}</button></div> : null}
          </section>
        </>
      )}

      {cancelTarget ? (
        <LeaveConfirmationDialog
          title="İzin talebi iptal edilsin mi?"
          description={<><strong>{cancelTarget.leave_type_name} talebi iptal edilecek.</strong><p>Sunucu güncel sürümü yeniden doğrular ve ilgili planlama veya kullanım hareketini atomik olarak günceller.</p></>}
          confirmLabel="Talebi iptal et"
          busyLabel="Talep iptal ediliyor…"
          danger
          isBusy={isCancelling}
          onCancel={() => { if (!isCancelling) { setCancelTarget(null); cancelCommandKey.current = null; } }}
          onConfirm={() => void confirmCancel()}
        />
      ) : null}
    </section>
  );
}
