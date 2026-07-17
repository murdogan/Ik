"use client";

import {
  type ChangeEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import type { AuthUser } from "@/lib/auth-contracts";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  cancelExportJob,
  commitEmployeeImport,
  createExportDownloadIntent,
  createExportJob,
  downloadEmployeeImportTemplate,
  type EmployeeImport,
  type ExportJob,
  type ReportFilters,
  type ReportFormat,
  type ReportPage,
  type ReportType,
  readEmployeeImport,
  readExportJob,
  readReport,
  saveClientFile,
  uploadEmployeeImport,
} from "@/lib/reporting";

import styles from "./reporting.module.css";

const REPORT_LABELS: Record<ReportType, string> = {
  employees: "Çalışanlar",
  leaves: "İzinler",
  missing_documents: "Eksik / süresi yaklaşan belgeler",
};

const FIELD_LABELS: Record<string, string> = {
  employee_number: "Sicil no",
  first_name: "Ad",
  last_name: "Soyad",
  work_email: "İş e-postası",
  employment_status: "Çalışma durumu",
  employment_start_date: "İşe giriş",
  employment_end_date: "İşten ayrılış",
  legal_entity: "Tüzel kişilik",
  branch: "Şube",
  department: "Departman",
  position: "Pozisyon",
  employee_name: "Çalışan",
  leave_type: "İzin türü",
  start_date: "Başlangıç",
  end_date: "Bitiş",
  counted_days: "Gün",
  status: "Durum",
  submitted_at: "Gönderim",
  decided_at: "Karar",
  document_type_code: "Belge kodu",
  document_type_name: "Belge türü",
  checklist_status: "Belge durumu",
  expires_on: "Geçerlilik sonu",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Aktif",
  on_leave: "İzinde",
  terminated: "İşten ayrıldı",
  pending: "Bekliyor",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
  missing: "Eksik",
  expiring: "Süresi yaklaşıyor",
  expired: "Süresi doldu",
  queued: "Sırada",
  processing: "İşleniyor",
  running: "Hazırlanıyor",
  retry: "Yeniden denenecek",
  ready: "Doğrulandı",
  invalid: "Düzeltme gerekli",
  succeeded: "Tamamlandı",
  failed: "Başarısız",
  clean: "Temiz",
  infected: "Güvenli değil",
  error: "Tarama hatası",
};

const ACTIVE_EXPORT_STATUSES = new Set(["queued", "running", "retry"]);
const ACTIVE_IMPORT_STATUSES = new Set(["queued", "processing", "retry"]);

function errorMessage(cause: unknown): string {
  if (!(cause instanceof ApiClientError)) {
    return "İşlem tamamlanamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  }
  const messages: Record<string, string> = {
    reporting_validation_error: "Gönderilen filtre veya dosya geçerli değil.",
    reporting_conflict: "Bu işlem kaydın mevcut durumunda tamamlanamaz.",
    reporting_resource_not_found: "Kayıt bulunamadı veya artık erişilebilir değil.",
    reporting_feature_unavailable: "Raporlama bu çalışma alanında etkin değil.",
    reporting_storage_unavailable: "Özel dosya alanı geçici olarak kullanılamıyor.",
    authorization_denied: "Bu işlem için gerekli yetkiniz bulunmuyor.",
    idempotency_key_invalid: "İşlem anahtarı geçerli değil; yeniden deneyin.",
    idempotency_key_mismatch: "İstek değiştiği için işlem güvenli biçimde yenilenecek.",
    invalid_response: "Sunucu yanıtı güvenli biçimde doğrulanamadı.",
    network_error: "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin.",
  };
  return messages[cause.code] ?? "İşlem güvenli biçimde tamamlanamadı.";
}

function formatValue(field: string, value: string | number | null): string {
  if (value === null || value === "") return "—";
  if (typeof value === "number") return new Intl.NumberFormat("tr-TR").format(value);
  if (field.endsWith("_at") && Number.isFinite(Date.parse(value))) {
    return new Intl.DateTimeFormat("tr-TR", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }
  if ((field.endsWith("_date") || field === "expires_on") && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium", timeZone: "UTC" }).format(
      new Date(`${value}T00:00:00Z`),
    );
  }
  return STATUS_LABELS[value] ?? value;
}

function statusText(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function failureText(code: string | null): string | null {
  if (code === null) return null;
  const labels: Record<string, string> = {
    authorization_revoked: "Güncel rapor yetkisi artık bu aktarımı kapsamıyor.",
    file_too_large: "Oluşturulan dosya güvenli boyut sınırını aştı.",
    infected_file: "Dosya kötü amaçlı yazılım taramasını geçemedi.",
    invalid_file: "Dosya güvenli biçimde çözümlenemedi.",
    row_limit_exceeded: "Dosya veya rapor 10.000 satır sınırını aştı.",
    scanner_unavailable: "Dosya tarayıcısı geçici olarak kullanılamıyor.",
    storage_unavailable: "Özel dosya alanı geçici olarak kullanılamıyor.",
    worker_failure: "Arka plan işlemi güvenli biçimde tamamlanamadı.",
  };
  return labels[code] ?? "Arka plan işlemi tamamlanamadı.";
}

function reportFilters(
  reportType: ReportType,
  text: string,
  code: string,
  status: string,
  dateFrom: string,
  dateTo: string,
): ReportFilters {
  const normalizedText = text.trim();
  const normalizedCode = code.trim();
  if (reportType === "employees") {
    return {
      q: normalizedText || undefined,
      department_code: normalizedCode || undefined,
      status: status || undefined,
      employment_start_from: dateFrom || undefined,
      employment_start_to: dateTo || undefined,
    };
  }
  if (reportType === "leaves") {
    return {
      leave_type_code: normalizedCode || undefined,
      status: status || undefined,
      start_from: dateFrom || undefined,
      start_to: dateTo || undefined,
    };
  }
  return {
    document_type_code: normalizedCode || undefined,
    statuses: status ? [status] : ["missing", "expiring", "expired"],
    expires_before: dateTo || undefined,
  };
}

function ReportTable({ page }: { page: ReportPage }) {
  if (page.data.length === 0) {
    return (
      <div className={styles.emptyState}>
        <span aria-hidden="true">0</span>
        <div>
          <strong>Eşleşen kayıt bulunamadı</strong>
          <p>Filtreleri değiştirerek yeniden arayabilirsiniz.</p>
        </div>
      </div>
    );
  }
  return (
    <div className={styles.tableScroller}>
      <table className={styles.reportTable}>
        <thead>
          <tr>
            {page.meta.fields.map((field) => (
              <th key={field}>{FIELD_LABELS[field] ?? field}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {page.data.map((row, index) => (
            <tr key={`${index}-${String(row.values.employee_number ?? "row")}`}>
              {page.meta.fields.map((field) => (
                <td key={field}>{formatValue(field, row.values[field] ?? null)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReportingWorkspace() {
  const { user } = useSession();
  const authorizationBoundary = [
    user.tenant_id,
    user.id,
    user.membership_id,
    user.permission_version,
  ].join(":");
  return <ReportingWorkspaceContent key={authorizationBoundary} user={user} />;
}

function ReportingWorkspaceContent({ user }: { user: AuthUser }) {
  const canReadReports =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantReports) ||
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamReports);
  const canExport =
    canReadReports &&
    (hasPermission(user, AUTHORIZATION_PERMISSIONS.exportTenantReports) ||
      hasPermission(user, AUTHORIZATION_PERMISSIONS.exportTeamReports));
  const canImport = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.manageEmployeeImports,
  );
  const [section, setSection] = useState<"reports" | "imports">(
    canReadReports ? "reports" : "imports",
  );
  const [reportType, setReportType] = useState<ReportType>("employees");
  const [page, setPage] = useState<ReportPage | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [textFilter, setTextFilter] = useState("");
  const [codeFilter, setCodeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<ReportFilters>({});
  const [currentCursor, setCurrentCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const reportRequest = useRef(0);
  const exportCommand = useRef<{ fingerprint: string; key: string } | null>(null);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [exportFormat, setExportFormat] = useState<ReportFormat>("xlsx");
  const [exportJob, setExportJob] = useState<ExportJob | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [importJob, setImportJob] = useState<EmployeeImport | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [commitConfirmed, setCommitConfirmed] = useState(false);
  const [issueCursor, setIssueCursor] = useState<string | null>(null);
  const [issueHistory, setIssueHistory] = useState<(string | null)[]>([]);
  const commitKey = useRef<string | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);

  const loadReportPage = useCallback(
    async (cursor: string | null, filters: ReportFilters) => {
      if (!canReadReports) return;
      const requestId = ++reportRequest.current;
      setReportLoading(true);
      setReportError(null);
      try {
        const result = await readReport(reportType, filters, cursor, 50);
        if (requestId === reportRequest.current) {
          setPage(result);
          setSelectedFields([...result.meta.fields]);
        }
      } catch (cause) {
        if (requestId === reportRequest.current) {
          setPage(null);
          setReportError(errorMessage(cause));
        }
      } finally {
        if (requestId === reportRequest.current) setReportLoading(false);
      }
    },
    [canReadReports, reportType],
  );

  useEffect(() => {
    if (!canReadReports) return;
    let active = true;
    const initialFilters = reportFilters(reportType, "", "", "", "", "");
    queueMicrotask(() => {
      if (active) void loadReportPage(null, initialFilters);
    });
    return () => {
      active = false;
    };
  }, [
    canReadReports,
    loadReportPage,
    reportType,
    user.permission_version,
    user.tenant_id,
  ]);

  const exportPollId = exportJob?.id ?? null;
  const exportPollStatus = exportJob?.status ?? null;
  useEffect(() => {
    if (
      !canExport ||
      exportPollId === null ||
      exportPollStatus === null ||
      !ACTIVE_EXPORT_STATUSES.has(exportPollStatus)
    ) return;
    let active = true;
    let timer: number | null = null;
    const jobId = exportPollId;
    const poll = async () => {
      try {
        const job = await readExportJob(jobId);
        if (active) {
          setExportJob(job);
          setExportError(null);
        }
      } catch (cause) {
        if (active) setExportError(errorMessage(cause));
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 2_500);
      }
    };
    timer = window.setTimeout(() => void poll(), 2_500);
    return () => {
      active = false;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [canExport, exportPollId, exportPollStatus]);

  const importPollId = importJob?.id ?? null;
  const importPollStatus = importJob?.status ?? null;
  useEffect(() => {
    if (
      !canImport ||
      importPollId === null ||
      importPollStatus === null ||
      !ACTIVE_IMPORT_STATUSES.has(importPollStatus)
    ) return;
    let active = true;
    let timer: number | null = null;
    const importId = importPollId;
    const poll = async () => {
      try {
        const record = await readEmployeeImport(importId);
        if (active) {
          setImportJob(record);
          setImportError(null);
          setIssueCursor(null);
          setIssueHistory([]);
        }
      } catch (cause) {
        if (active) setImportError(errorMessage(cause));
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 2_500);
      }
    };
    timer = window.setTimeout(() => void poll(), 2_500);
    return () => {
      active = false;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [canImport, importPollId, importPollStatus]);

  const scopeLabel = page?.meta.scope === "team" ? "Doğrudan ekibiniz" : "Tüm kurum";
  const codeLabel =
    reportType === "employees"
      ? "Departman kodu"
      : reportType === "leaves"
        ? "İzin türü kodu"
        : "Belge türü kodu";
  const statusOptions = useMemo(() => {
    if (reportType === "employees") return ["active", "on_leave", "terminated"];
    if (reportType === "leaves") return ["pending", "approved", "rejected", "cancelled"];
    return ["missing", "expiring", "expired"];
  }, [reportType]);

  function applyReportFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const filters = reportFilters(
      reportType,
      textFilter,
      codeFilter,
      statusFilter,
      dateFrom,
      dateTo,
    );
    setAppliedFilters(filters);
    setCurrentCursor(null);
    setCursorHistory([]);
    void loadReportPage(null, filters);
  }

  function selectReportType(type: ReportType) {
    if (type === reportType) return;
    const initialFilters = reportFilters(type, "", "", "", "", "");
    reportRequest.current += 1;
    setPage(null);
    setSelectedFields([]);
    setTextFilter("");
    setCodeFilter("");
    setStatusFilter("");
    setDateFrom("");
    setDateTo("");
    setAppliedFilters(initialFilters);
    setCurrentCursor(null);
    setCursorHistory([]);
    setExportJob(null);
    setExportError(null);
    setReportType(type);
  }

  function openNextReportPage() {
    const next = page?.meta.next_cursor;
    if (!next || reportLoading) return;
    setCursorHistory((history) => [...history, currentCursor]);
    setCurrentCursor(next);
    void loadReportPage(next, appliedFilters);
  }

  function openPreviousReportPage() {
    if (cursorHistory.length === 0 || reportLoading) return;
    const previous = cursorHistory[cursorHistory.length - 1] ?? null;
    setCursorHistory((history) => history.slice(0, -1));
    setCurrentCursor(previous);
    void loadReportPage(previous, appliedFilters);
  }

  async function requestExport() {
    if (!canExport || selectedFields.length === 0 || exportBusy) return;
    setExportBusy(true);
    setExportError(null);
    const fingerprint = JSON.stringify({
      reportType,
      exportFormat,
      fields: selectedFields,
      filters: appliedFilters,
    });
    const command =
      exportCommand.current?.fingerprint === fingerprint
        ? exportCommand.current
        : { fingerprint, key: crypto.randomUUID() };
    exportCommand.current = command;
    const idempotencyKey = command.key;
    try {
      setExportJob(
        await createExportJob(
          reportType,
          exportFormat,
          selectedFields,
          appliedFilters,
          idempotencyKey,
        ),
      );
      exportCommand.current = null;
    } catch (cause) {
      if (cause instanceof ApiClientError && cause.code.includes("idempotency")) {
        exportCommand.current = null;
      }
      setExportError(errorMessage(cause));
    } finally {
      setExportBusy(false);
    }
  }

  async function cancelExport() {
    if (!canExport || !exportJob || exportBusy) return;
    setExportBusy(true);
    setExportError(null);
    try {
      setExportJob(await cancelExportJob(exportJob.id));
    } catch (cause) {
      setExportError(errorMessage(cause));
    } finally {
      setExportBusy(false);
    }
  }

  async function downloadExport() {
    if (!canExport || !exportJob || exportBusy) return;
    setExportBusy(true);
    setExportError(null);
    try {
      const intent = await createExportDownloadIntent(exportJob.id);
      const anchor = document.createElement("a");
      anchor.href = intent.url;
      anchor.rel = "noopener noreferrer";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setExportJob(await readExportJob(exportJob.id));
    } catch (cause) {
      setExportError(errorMessage(cause));
    } finally {
      setExportBusy(false);
    }
  }

  async function downloadTemplate(format: ReportFormat) {
    if (!canImport || importBusy) return;
    setImportBusy(true);
    setImportError(null);
    try {
      const file = await downloadEmployeeImportTemplate(format);
      saveClientFile(file, `employee-import-v1.${format}`);
    } catch (cause) {
      setImportError(errorMessage(cause));
    } finally {
      setImportBusy(false);
    }
  }

  async function uploadImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!canImport || !file || importBusy) return;
    setImportBusy(true);
    setImportError(null);
    setImportJob(null);
    setCommitConfirmed(false);
    commitKey.current = null;
    try {
      setImportJob(await uploadEmployeeImport(file));
      setIssueCursor(null);
      setIssueHistory([]);
    } catch (cause) {
      setImportError(errorMessage(cause));
    } finally {
      setImportBusy(false);
      if (uploadInput.current) uploadInput.current.value = "";
    }
  }

  async function commitImport() {
    if (!canImport || !importJob || importJob.status !== "ready" || !commitConfirmed || importBusy) {
      return;
    }
    setImportBusy(true);
    setImportError(null);
    commitKey.current ??= crypto.randomUUID();
    try {
      await commitEmployeeImport(importJob.id, commitKey.current);
      setImportJob(await readEmployeeImport(importJob.id));
    } catch (cause) {
      setImportError(errorMessage(cause));
    } finally {
      setImportBusy(false);
    }
  }

  async function openIssuePage(nextCursor: string | null, direction: "next" | "previous") {
    if (!canImport || !importJob || importBusy) return;
    setImportBusy(true);
    setImportError(null);
    try {
      const nextRecord = await readEmployeeImport(importJob.id, nextCursor);
      if (direction === "next") {
        setIssueHistory((history) => [...history, issueCursor]);
      } else {
        setIssueHistory((history) => history.slice(0, -1));
      }
      setIssueCursor(nextCursor);
      setImportJob(nextRecord);
    } catch (cause) {
      setImportError(errorMessage(cause));
    } finally {
      setImportBusy(false);
    }
  }

  return (
    <section className={styles.workspace} aria-labelledby="reporting-title">
      <header className={styles.hero}>
        <div>
          <span>Kontrollü veri çalışma alanı</span>
          <h1 id="reporting-title">Raporlar ve aktarımlar</h1>
          <p>
            Yetkinize göre daraltılmış kayıtları inceleyin, özel dosya aktarımları
            oluşturun ve çalışan içe aktarımlarını doğrulayın.
          </p>
        </div>
        <div className={styles.heroLimit}>
          <strong>10.000</strong>
          <span>dosya başına azami satır</span>
        </div>
      </header>

      {canReadReports && canImport ? (
        <div className={styles.sectionTabs} role="tablist" aria-label="Raporlama alanları">
          <button
            type="button"
            role="tab"
            aria-selected={section === "reports"}
            className={section === "reports" ? styles.activeTab : ""}
            onClick={() => setSection("reports")}
          >
            Raporlar ve dışa aktarma
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={section === "imports"}
            className={section === "imports" ? styles.activeTab : ""}
            onClick={() => setSection("imports")}
          >
            Çalışan içe aktarma
          </button>
        </div>
      ) : null}

      {section === "reports" && canReadReports ? (
        <div className={styles.reportArea} role="tabpanel">
          <div className={styles.reportTabs} role="tablist" aria-label="Rapor türü">
            {(Object.keys(REPORT_LABELS) as ReportType[]).map((type) => (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={reportType === type}
                className={reportType === type ? styles.activeReportTab : ""}
                onClick={() => selectReportType(type)}
              >
                {REPORT_LABELS[type]}
              </button>
            ))}
          </div>

          <form className={styles.filters} onSubmit={applyReportFilters}>
            {reportType === "employees" ? (
              <label>
                Çalışan ara
                <input
                  value={textFilter}
                  maxLength={200}
                  placeholder="Sicil no veya ad soyad"
                  onChange={(event) => setTextFilter(event.target.value)}
                />
              </label>
            ) : null}
            <label>
              {codeLabel}
              <input
                value={codeFilter}
                maxLength={64}
                placeholder="Kod"
                onChange={(event) => setCodeFilter(event.target.value)}
              />
            </label>
            <label>
              Durum
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">Tümü</option>
                {statusOptions.map((status) => (
                  <option value={status} key={status}>
                    {statusText(status)}
                  </option>
                ))}
              </select>
            </label>
            {reportType !== "missing_documents" ? (
              <label>
                Başlangıç tarihi
                <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
              </label>
            ) : null}
            <label>
              {reportType === "missing_documents" ? "En geç geçerlilik tarihi" : "Bitiş tarihi"}
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
            <button type="submit" disabled={reportLoading}>
              {reportLoading ? "Yükleniyor…" : "Filtreleri uygula"}
            </button>
          </form>

          <article className={styles.panel} aria-busy={reportLoading}>
            <div className={styles.panelHeader}>
              <div>
                <span>{scopeLabel}</span>
                <h2>{REPORT_LABELS[reportType]} raporu</h2>
              </div>
              {page ? <small>Sayfada {page.data.length} kayıt</small> : null}
            </div>
            {reportError ? (
              <div className={styles.errorState} role="alert">
                <strong>Rapor yüklenemedi</strong>
                <span>{reportError}</span>
                <button type="button" onClick={() => void loadReportPage(currentCursor, appliedFilters)}>
                  Yeniden dene
                </button>
              </div>
            ) : reportLoading && !page ? (
              <div className={styles.loadingState} role="status">
                <span className={styles.spinner} aria-hidden="true" /> Rapor hazırlanıyor…
              </div>
            ) : page ? (
              <ReportTable page={page} />
            ) : null}
            {page ? (
              <div className={styles.pagination}>
                <button type="button" disabled={cursorHistory.length === 0 || reportLoading} onClick={openPreviousReportPage}>
                  Önceki
                </button>
                <span>{cursorHistory.length + 1}. sayfa</span>
                <button type="button" disabled={!page.meta.next_cursor || reportLoading} onClick={openNextReportPage}>
                  Sonraki
                </button>
              </div>
            ) : null}
          </article>

          {canExport && page ? (
            <article className={styles.exportPanel}>
              <div className={styles.panelHeader}>
                <div>
                  <span>Asenkron özel dosya</span>
                  <h2>Dışa aktarma oluştur</h2>
                </div>
              </div>
              <div className={styles.exportGrid}>
                <fieldset>
                  <legend>Dosyaya eklenecek alanlar</legend>
                  <div className={styles.fieldChoices}>
                    {page.meta.fields.map((field) => (
                      <label key={field}>
                        <input
                          type="checkbox"
                          checked={selectedFields.includes(field)}
                          onChange={(event) =>
                            setSelectedFields((fields) =>
                              event.target.checked
                                ? [...fields, field]
                                : fields.filter((item) => item !== field),
                            )
                          }
                        />
                        {FIELD_LABELS[field] ?? field}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className={styles.exportActions}>
                  <label>
                    Dosya biçimi
                    <select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as ReportFormat)}>
                      <option value="xlsx">Excel (.xlsx)</option>
                      <option value="csv">CSV (.csv)</option>
                    </select>
                  </label>
                  <button type="button" disabled={exportBusy || selectedFields.length === 0} onClick={() => void requestExport()}>
                    {exportBusy ? "İşleniyor…" : "Dışa aktarmayı başlat"}
                  </button>
                  <small>Yetki ve alan kapsamı oluşturma ve indirme anında yeniden denetlenir.</small>
                </div>
              </div>
              {exportError ? <div className={styles.inlineError} role="alert">{exportError}</div> : null}
              {failureText(exportJob?.failure_code ?? null) ? (
                <div className={styles.inlineError} role="alert">
                  {failureText(exportJob?.failure_code ?? null)}
                </div>
              ) : null}
              {exportJob ? (
                <div className={styles.jobCard} aria-live="polite">
                  <div>
                    <span className={`${styles.statusBadge} ${styles[`status_${exportJob.status}`] ?? ""}`}>
                      {statusText(exportJob.status)}
                    </span>
                    <strong>{REPORT_LABELS[exportJob.report_type]} · {exportJob.format.toUpperCase()}</strong>
                    <small>
                      {exportJob.row_count !== null ? `${exportJob.row_count} satır` : "Dosya hazırlanıyor"}
                      {exportJob.size_bytes !== null ? ` · ${new Intl.NumberFormat("tr-TR").format(exportJob.size_bytes)} bayt` : ""}
                    </small>
                  </div>
                  <div className={styles.jobActions}>
                    {ACTIVE_EXPORT_STATUSES.has(exportJob.status) ? (
                      <button type="button" disabled={exportBusy} onClick={() => void cancelExport()}>İptal et</button>
                    ) : null}
                    {exportJob.status === "succeeded" && exportJob.download_intents_remaining > 0 ? (
                      <button type="button" disabled={exportBusy} onClick={() => void downloadExport()}>
                        Güvenli indirme oluştur
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </article>
          ) : null}
        </div>
      ) : null}

      {section === "imports" && canImport ? (
        <div className={styles.importArea} role="tabpanel">
          <article className={styles.importGuide}>
            <div>
              <span>Şablon v1</span>
              <h2>Önce güncel şablonu indirin</h2>
              <p>
                CSV veya XLSX dosyasını azami 10 MiB ve 10.000 veri satırıyla hazırlayın.
                Dosya temiz tarama sonucu alınmadan çözümlenmez. Şablon v1’de durum
                active veya on_leave olmalı ve employment_end_date boş bırakılmalıdır.
              </p>
            </div>
            <div className={styles.templateActions}>
              <button type="button" disabled={importBusy} onClick={() => void downloadTemplate("xlsx")}>XLSX şablonu</button>
              <button type="button" disabled={importBusy} onClick={() => void downloadTemplate("csv")}>CSV şablonu</button>
            </div>
          </article>

          <article className={styles.uploadPanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>Özel yükleme</span>
                <h2>Dosyayı doğrulamaya gönder</h2>
              </div>
            </div>
            <label className={styles.filePicker}>
              <strong>{importBusy ? "Dosya işleniyor…" : "CSV veya XLSX seçin"}</strong>
              <span>Dosya içeriği özel nesne alanında tutulur ve virüs taramasından geçirilir.</span>
              <input
                ref={uploadInput}
                type="file"
                accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                disabled={importBusy}
                onChange={(event) => void uploadImport(event)}
              />
            </label>
            {importError ? <div className={styles.inlineError} role="alert">{importError}</div> : null}
            {failureText(importJob?.failure_code ?? null) ? (
              <div className={styles.inlineError} role="alert">
                {failureText(importJob?.failure_code ?? null)}
              </div>
            ) : null}
          </article>

          {importJob ? (
            <article className={styles.importResult} aria-live="polite">
              <div className={styles.panelHeader}>
                <div>
                  <span>Doğrulama sonucu</span>
                  <h2>Çalışan içe aktarma</h2>
                </div>
                <span className={`${styles.statusBadge} ${styles[`status_${importJob.status}`] ?? ""}`}>
                  {statusText(importJob.status)}
                </span>
              </div>
              <div className={styles.importMetrics}>
                <div><span>Tarama</span><strong>{statusText(importJob.scan_result)}</strong></div>
                <div><span>Satır</span><strong>{importJob.row_count}</strong></div>
                <div><span>Hata</span><strong>{importJob.error_count}</strong></div>
                <div><span>Uyarı</span><strong>{importJob.warning_count}</strong></div>
                <div><span>Oluşturulan</span><strong>{importJob.committed_count}</strong></div>
              </div>

              {ACTIVE_IMPORT_STATUSES.has(importJob.status) ? (
                <div className={styles.loadingState} role="status">
                  <span className={styles.spinner} aria-hidden="true" /> Tarama ve kuru çalıştırma sürüyor…
                </div>
              ) : null}

              {importJob.issues.length > 0 ? (
                <div className={styles.issueBlock}>
                  <h3>Deterministik doğrulama sorunları</h3>
                  <div className={styles.tableScroller}>
                    <table className={styles.issueTable}>
                      <thead><tr><th>Satır</th><th>Düzey</th><th>Kod</th><th>Alan</th><th>Açıklama</th></tr></thead>
                      <tbody>
                        {importJob.issues.map((issue) => (
                          <tr key={`${issue.row_number}-${issue.code}-${issue.field ?? "_"}`}>
                            <td>{issue.row_number}</td>
                            <td>{issue.severity === "error" ? "Hata" : "Uyarı"}</td>
                            <td><code>{issue.code}</code></td>
                            <td>{issue.field ? FIELD_LABELS[issue.field] ?? issue.field : "—"}</td>
                            <td>{issue.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className={styles.pagination}>
                    <button
                      type="button"
                      disabled={issueHistory.length === 0 || importBusy}
                      onClick={() => void openIssuePage(issueHistory[issueHistory.length - 1] ?? null, "previous")}
                    >Önceki sorunlar</button>
                    <span>{issueHistory.length + 1}. sayfa</span>
                    <button
                      type="button"
                      disabled={!importJob.issues_next_cursor || importBusy}
                      onClick={() => void openIssuePage(importJob.issues_next_cursor, "next")}
                    >Sonraki sorunlar</button>
                  </div>
                </div>
              ) : importJob.status === "invalid" ? (
                <div className={styles.inlineError}>Dosya doğrulanamadı; güvenli bir şablonla yeniden yükleyin.</div>
              ) : null}

              {importJob.status === "ready" ? (
                <div className={styles.commitBox}>
                  <label>
                    <input type="checkbox" checked={commitConfirmed} onChange={(event) => setCommitConfirmed(event.target.checked)} />
                    {importJob.row_count} doğrulanmış çalışanın tek işlemde oluşturulacağını onaylıyorum.
                  </label>
                  <p>Kullanıcı hesabı veya davet otomatik oluşturulmaz.</p>
                  <button type="button" disabled={!commitConfirmed || importBusy} onClick={() => void commitImport()}>
                    {importBusy ? "Kaydediliyor…" : "İçe aktarmayı kesinleştir"}
                  </button>
                </div>
              ) : null}
            </article>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
