"use client";

import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type Employee,
  listEmployees,
} from "@/lib/employees";
import {
  approveLeaveRequest,
  cancelLeaveRequest,
  createHolidayCalendar,
  createHolidayEntry,
  createLeaveAdjustment,
  createLeavePolicy,
  createLeaveType,
  type HolidayCalendar,
  type LeaveBalance,
  type LeaveLedgerEntry,
  type LeavePolicy,
  type LeaveRequest,
  type LeaveRequestStatus,
  type LeaveType,
  listHolidayCalendars,
  listHolidayEntries,
  listEmployeeLeaveBalanceHistory,
  listEmployeeLeaveBalances,
  listLeavePolicies,
  listLeaveRequests,
  listLeaveTypes,
  readLeaveRequest,
  rejectLeaveRequest,
  updateHolidayCalendar,
  updateHolidayEntry,
  updateLeaveType,
} from "@/lib/leave";

import { LeaveConfirmationDialog } from "./leave-confirmation-dialog";
import {
  commandKey,
  formatLeaveDate,
  formatLeaveDays,
  formatLeaveLedgerEntry,
  formatLeaveTimestamp,
  leaveErrorPresentation,
  LEAVE_STATUS_LABELS,
  localDateValue,
  type LeaveErrorPresentation,
} from "./leave-presentation";
import styles from "./leave.module.css";

type AdminTab = "requests" | "types" | "policies" | "calendar" | "balances";

interface AdminBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  canRead: boolean;
  canManage: boolean;
  canAdjust: boolean;
}

interface AdminFeedback {
  setError: (error: LeaveErrorPresentation | null) => void;
  setNotice: (notice: string | null) => void;
}

function replaceById<T extends { id: string }>(items: T[], incoming: T): T[] {
  return items.some((item) => item.id === incoming.id)
    ? items.map((item) => (item.id === incoming.id ? incoming : item))
    : [incoming, ...items];
}

function previousCalendarDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

async function listLeaveEligibleEmployees(query = ""): Promise<Employee[]> {
  const [active, onLeave] = await Promise.all([
    listEmployees({ q: query, limit: 25, status: "active" }),
    listEmployees({ q: query, limit: 25, status: "on_leave" }),
  ]);
  const byId = new Map<string, Employee>();
  for (const employee of [...active.data, ...onLeave.data]) {
    byId.set(employee.id, employee);
  }
  return [...byId.values()]
    .sort((left, right) =>
      `${left.last_name} ${left.first_name}`.localeCompare(
        `${right.last_name} ${right.first_name}`,
        "tr-TR",
      ),
    )
    .slice(0, 25);
}

export function LeaveAdminScreen() {
  const { user, sessionGeneration } = useSession();
  const boundary = useMemo<AdminBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      canRead: hasPermission(user, AUTHORIZATION_PERMISSIONS.readTenantLeave),
      canManage: hasPermission(user, AUTHORIZATION_PERMISSIONS.manageTenantLeave),
      canAdjust: hasPermission(user, AUTHORIZATION_PERMISSIONS.adjustTenantLeave),
    }),
    [sessionGeneration, user],
  );
  const key = `${boundary.sessionGeneration}:${boundary.userId}:${boundary.membershipId}:${boundary.tenantId}:${boundary.permissionVersion}:${boundary.canRead}:${boundary.canManage}:${boundary.canAdjust}`;
  return <AdminContent key={key} boundary={boundary} />;
}

function AdminContent({ boundary }: { boundary: AdminBoundary }) {
  const [tab, setTab] = useState<AdminTab>("requests");
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [policies, setPolicies] = useState<LeavePolicy[]>([]);
  const [calendars, setCalendars] = useState<HolidayCalendar[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<LeaveErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!boundary.canRead || !boundary.canManage) return;
    let active = true;
    void Promise.all([
      listLeaveTypes(true),
      listLeavePolicies(),
      listHolidayCalendars(true),
    ]).then(
      ([types, policyRows, calendarRows]) => {
        if (!active) return;
        setLeaveTypes(types);
        setPolicies(policyRows);
        setCalendars(calendarRows);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setError(
          leaveErrorPresentation(
            cause,
            "İzin yönetimi yapılandırması yüklenemedi. Lütfen yeniden deneyin.",
          ),
        );
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [boundary.canManage, boundary.canRead, reloadKey]);

  const feedback = useMemo<AdminFeedback>(
    () => ({ setError, setNotice }),
    [],
  );

  function reload() {
    setIsLoading(true);
    setError(null);
    setNotice(null);
    setReloadKey((key) => key + 1);
  }

  if (!boundary.canRead || !boundary.canManage) return null;

  return (
    <section className={styles.page} aria-labelledby="leave-admin-title">
      <header className={styles.pageHeader}>
        <div>
          <span>İK izin yönetimi</span>
          <h1 id="leave-admin-title">İzin yönetimi</h1>
          <p>İzin türlerini, değişmez politika sürümlerini, çalışma takvimini, tenant taleplerini ve neden zorunlu bakiye düzeltmelerini yönetin.</p>
        </div>
        <button className={styles.secondaryButton} type="button" disabled={isLoading} onClick={reload}>Yapılandırmayı yenile</button>
      </header>

      <div className={styles.adminTabs} role="tablist" aria-label="İzin yönetimi bölümleri">
        {([
          ["requests", "Talepler"],
          ["types", "İzin türleri"],
          ["policies", "Politikalar"],
          ["calendar", "Takvim ve tatiller"],
          ["balances", "Bakiyeler"],
        ] as const).map(([value, label]) => (
          <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => { setTab(value); setError(null); setNotice(null); }}>{label}</button>
        ))}
      </div>

      {error ? <div className={styles.inlineError} role="alert"><div><strong>İşlem tamamlanamadı</strong><span>{error.message}</span>{error.reference ? <small>Referans: {error.reference}</small> : null}</div>{error.conflict ? <button className={styles.secondaryButton} type="button" onClick={reload}>Güncel verileri yükle</button> : null}</div> : null}
      {notice ? <div className={styles.successNotice} role="status">{notice}</div> : null}

      {isLoading ? <div className={styles.pageLoading} role="status"><span className={styles.spinner} aria-hidden="true" /><div><strong>İzin yönetimi hazırlanıyor</strong><span>Politika ve takvim yapılandırması yükleniyor…</span></div></div> : tab === "requests" ? <TenantRequestAdmin feedback={feedback} /> : tab === "types" ? <LeaveTypeAdmin leaveTypes={leaveTypes} setLeaveTypes={setLeaveTypes} feedback={feedback} /> : tab === "policies" ? <PolicyAdmin leaveTypes={leaveTypes} policies={policies} setPolicies={setPolicies} setLeaveTypes={setLeaveTypes} feedback={feedback} /> : tab === "calendar" ? <CalendarAdmin calendars={calendars} setCalendars={setCalendars} feedback={feedback} /> : <AdjustmentAdmin canAdjust={boundary.canAdjust} leaveTypes={leaveTypes} feedback={feedback} />}
    </section>
  );
}

function LeaveTypeAdmin({
  leaveTypes,
  setLeaveTypes,
  feedback,
}: {
  leaveTypes: LeaveType[];
  setLeaveTypes: (updater: (current: LeaveType[]) => LeaveType[]) => void;
  feedback: AdminFeedback;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<LeaveType | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [archiveTarget, setArchiveTarget] = useState<LeaveType | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving) return;
    setIsSaving(true);
    feedback.setError(null);
    feedback.setNotice(null);
    try {
      const created = await createLeaveType(
        { code: code.trim(), name: name.trim(), description: description.trim() || null },
        commandKey(),
      );
      setLeaveTypes((current) => replaceById(current, created));
      setCode("");
      setName("");
      setDescription("");
      feedback.setNotice("İzin türü oluşturuldu. Tarihsel kullanım için sabit kod korunur.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "İzin türü oluşturulamadı."));
    } finally {
      setIsSaving(false);
    }
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing || isSaving) return;
    setIsSaving(true);
    feedback.setError(null);
    try {
      const updated = await updateLeaveType(
        editing.id,
        { expected_version: editing.version, name: editName.trim(), description: editDescription.trim() || null },
        commandKey(),
      );
      setLeaveTypes((current) => replaceById(current, updated));
      setEditing(null);
      feedback.setNotice("İzin türü güncellendi; geçmiş talepler aynı tür kimliğiyle korunur.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "İzin türü güncellenemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  async function setActive(target: LeaveType, active: boolean) {
    if (isSaving) return;
    setIsSaving(true);
    feedback.setError(null);
    try {
      const updated = await updateLeaveType(
        target.id,
        { expected_version: target.version, is_active: active },
        commandKey(),
      );
      setLeaveTypes((current) => replaceById(current, updated));
      setArchiveTarget(null);
      feedback.setNotice(active ? "İzin türü yeniden etkinleştirildi." : "İzin türü pasifleştirildi; geçmiş kayıtlar korundu.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "İzin türü durumu değiştirilemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.adminGrid}>
      <section className={styles.sectionCard} aria-labelledby="create-leave-type-title">
        <header className={styles.sectionHeader}><div><span>Tenant kataloğu</span><h2 id="create-leave-type-title">Yeni izin türü</h2><p>Kod oluşturulduktan sonra geçmiş kayıtların güvenli anahtarı olarak değişmez.</p></div></header>
        <form className={styles.leaveForm} onSubmit={create}><div className={styles.formGrid}><div className={styles.formField}><label htmlFor="leave-type-code">Sabit kod</label><input id="leave-type-code" value={code} pattern="[a-z][a-z0-9_]{0,63}" maxLength={64} required disabled={isSaving} onChange={(event) => setCode(event.target.value.toLocaleLowerCase("en-US"))} placeholder="annual" /></div><div className={styles.formField}><label htmlFor="leave-type-name">Görünen ad</label><input id="leave-type-name" value={name} maxLength={200} required disabled={isSaving} onChange={(event) => setName(event.target.value)} placeholder="Yıllık izin" /></div><div className={`${styles.formField} ${styles.wideField}`}><label htmlFor="leave-type-description">Açıklama</label><textarea id="leave-type-description" value={description} maxLength={500} rows={3} disabled={isSaving} onChange={(event) => setDescription(event.target.value)} /></div></div><div className={styles.formActions}><button className={styles.primaryButton} type="submit" disabled={isSaving}>{isSaving ? "Oluşturuluyor…" : "İzin türü oluştur"}</button></div></form>
      </section>

      <section className={styles.sectionCard} aria-labelledby="leave-type-list-title">
        <header className={styles.sectionHeader}><div><span>Arşiv güvenli katalog</span><h2 id="leave-type-list-title">Tanımlı izin türleri</h2><p>Pasif türler yeni taleplerde kullanılamaz; politika ve talep geçmişi silinmez.</p></div><strong>{leaveTypes.length}</strong></header>
        {leaveTypes.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">İ</span><div><strong>İzin türü bulunmuyor</strong><p>İlk izin türünü formdan oluşturun.</p></div></div> : <div className={styles.cardList}>{leaveTypes.map((item) => <article className={styles.catalogCard} data-inactive={!item.is_active} key={item.id}><header><div><span>{item.code}</span><h3>{item.name}</h3><p>{item.description ?? "Açıklama eklenmemiş"}</p></div><span className={styles.activeBadge} data-active={item.is_active}>{item.is_active ? "Etkin" : "Pasif"}</span></header>{editing?.id === item.id ? <form className={styles.inlineForm} onSubmit={saveEdit}><div className={styles.formField}><label htmlFor={`edit-type-name-${item.id}`}>Görünen ad</label><input id={`edit-type-name-${item.id}`} value={editName} maxLength={200} required disabled={isSaving} onChange={(event) => setEditName(event.target.value)} /></div><div className={styles.formField}><label htmlFor={`edit-type-description-${item.id}`}>Açıklama</label><textarea id={`edit-type-description-${item.id}`} value={editDescription} maxLength={500} rows={2} disabled={isSaving} onChange={(event) => setEditDescription(event.target.value)} /></div><div className={styles.inlineActions}><button className={styles.secondaryButton} type="button" disabled={isSaving} onClick={() => setEditing(null)}>Vazgeç</button><button className={styles.primaryButton} type="submit" disabled={isSaving}>Kaydet</button></div></form> : <footer><button className={styles.textButton} type="button" disabled={isSaving || !item.is_active} onClick={() => { setEditing(item); setEditName(item.name); setEditDescription(item.description ?? ""); }}>Düzenle</button>{item.is_active ? <button className={styles.dangerTextButton} type="button" disabled={isSaving} onClick={() => setArchiveTarget(item)}>Pasifleştir</button> : <button className={styles.textButton} type="button" disabled={isSaving} onClick={() => void setActive(item, true)}>Etkinleştir</button>}</footer>}</article>)}</div>}
      </section>

      {archiveTarget ? <LeaveConfirmationDialog title="İzin türü pasifleştirilsin mi?" description={<><strong>{archiveTarget.name} yeni taleplere kapatılacak.</strong><p>Geçmiş talepler, politika sürümleri ve bakiye hareketleri korunur.</p></>} confirmLabel="Türü pasifleştir" busyLabel="Tür pasifleştiriliyor…" danger isBusy={isSaving} onCancel={() => { if (!isSaving) setArchiveTarget(null); }} onConfirm={() => void setActive(archiveTarget, false)} /> : null}
    </div>
  );
}

function PolicyAdmin({
  leaveTypes,
  policies,
  setPolicies,
  setLeaveTypes,
  feedback,
}: {
  leaveTypes: LeaveType[];
  policies: LeavePolicy[];
  setPolicies: (updater: (current: LeavePolicy[]) => LeavePolicy[]) => void;
  setLeaveTypes: (updater: (current: LeaveType[]) => LeaveType[]) => void;
  feedback: AdminFeedback;
}) {
  const activeTypes = useMemo(
    () => leaveTypes.filter((item) => item.is_active),
    [leaveTypes],
  );
  const [leaveTypeId, setLeaveTypeId] = useState(activeTypes[0]?.id ?? "");
  const [effectiveFrom, setEffectiveFrom] = useState(localDateValue());
  const [paid, setPaid] = useState(true);
  const [documentRequired, setDocumentRequired] = useState(false);
  const [negativeAllowed, setNegativeAllowed] = useState(false);
  const [accrualEnabled, setAccrualEnabled] = useState(false);
  const [accrualDays, setAccrualDays] = useState("");
  const [carryoverEnabled, setCarryoverEnabled] = useState(false);
  const [carryoverLimit, setCarryoverLimit] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const medicalDocumentRequired =
    leaveTypes.find((item) => item.id === leaveTypeId)?.code === "medical_report";

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving || !leaveTypeId) return;
    setIsSaving(true);
    feedback.setError(null);
    feedback.setNotice(null);
    try {
      const created = await createLeavePolicy(
        {
          leave_type_id: leaveTypeId,
          effective_from: effectiveFrom,
          paid,
          document_required: medicalDocumentRequired || documentRequired,
          negative_balance_allowed: negativeAllowed,
          accrual_enabled: accrualEnabled,
          accrual_days_per_month: accrualEnabled ? Number(accrualDays) : 0,
          carryover_enabled: carryoverEnabled,
          carryover_limit_days: carryoverEnabled ? Number(carryoverLimit) : null,
        },
        commandKey(),
      );
      setPolicies((current) => {
        const predecessor = current
          .filter(
            (item) =>
              item.leave_type_id === created.leave_type_id &&
              item.effective_from < created.effective_from,
          )
          .sort((left, right) => right.effective_from.localeCompare(left.effective_from))[0];
        const reconciled = current
          .filter((item) => item.id !== created.id)
          .map((item) =>
            predecessor && item.id === predecessor.id
              ? { ...item, effective_to: previousCalendarDate(created.effective_from) }
              : item,
          );
        return [created, ...reconciled];
      });
      const today = localDateValue();
      setLeaveTypes((current) => current.map((item) =>
        item.id === created.leave_type_id &&
        created.effective_from <= today &&
        (!created.effective_to || created.effective_to >= today) &&
        (!item.current_policy || item.current_policy.effective_from <= created.effective_from)
          ? { ...item, current_policy: created }
          : item,
      ));
      feedback.setNotice("Yeni izin politikası sürümü oluşturuldu. Önceki sürümler değişmeden korundu.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "İzin politikası oluşturulamadı."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.adminGrid}>
      <section className={styles.sectionCard} aria-labelledby="policy-create-title">
        <header className={styles.sectionHeader}><div><span>Yeni değişmez sürüm</span><h2 id="policy-create-title">İzin politikası oluştur</h2><p>Politikalar düzenlenmez; yürürlük tarihiyle yeni sürüm eklenir.</p></div></header>
        <form className={styles.leaveForm} onSubmit={create}><div className={styles.formGrid}><div className={styles.formField}><label htmlFor="policy-type">İzin türü</label><select id="policy-type" value={leaveTypeId} required disabled={isSaving} onChange={(event) => setLeaveTypeId(event.target.value)}><option value="">Tür seçin</option>{activeTypes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></div><div className={styles.formField}><label htmlFor="policy-effective">Yürürlük tarihi</label><input id="policy-effective" type="date" value={effectiveFrom} required disabled={isSaving} onChange={(event) => setEffectiveFrom(event.target.value)} /></div></div><div className={styles.checkboxGrid}><label><input type="checkbox" checked={paid} disabled={isSaving} onChange={(event) => setPaid(event.target.checked)} /> Ücretli izin</label><label><input type="checkbox" checked={medicalDocumentRequired || documentRequired} disabled={isSaving || medicalDocumentRequired} onChange={(event) => setDocumentRequired(event.target.checked)} /> {medicalDocumentRequired ? "Belge zorunlu · medikal kural" : "Belge zorunlu"}</label><label><input type="checkbox" checked={negativeAllowed} disabled={isSaving} onChange={(event) => setNegativeAllowed(event.target.checked)} /> Negatif bakiye</label><label><input type="checkbox" checked={accrualEnabled} disabled={isSaving} onChange={(event) => setAccrualEnabled(event.target.checked)} /> Otomatik kazanım</label><label><input type="checkbox" checked={carryoverEnabled} disabled={isSaving} onChange={(event) => setCarryoverEnabled(event.target.checked)} /> Devir</label></div>{accrualEnabled || carryoverEnabled ? <div className={styles.formGrid}>{accrualEnabled ? <div className={styles.formField}><label htmlFor="policy-accrual">Aylık kazanım (gün)</label><input id="policy-accrual" type="number" min="0.01" max="31" step="0.01" value={accrualDays} required disabled={isSaving} onChange={(event) => setAccrualDays(event.target.value)} /></div> : null}{carryoverEnabled ? <div className={styles.formField}><label htmlFor="policy-carryover">Devir sınırı (gün)</label><input id="policy-carryover" type="number" min="0" max="366" step="0.01" value={carryoverLimit} required disabled={isSaving} onChange={(event) => setCarryoverLimit(event.target.value)} /></div> : null}</div> : null}<div className={styles.formActions}><button className={styles.primaryButton} type="submit" disabled={isSaving || activeTypes.length === 0}>{isSaving ? "Politika oluşturuluyor…" : "Yeni sürümü oluştur"}</button></div></form>
      </section>

      <section className={styles.sectionCard} aria-labelledby="policy-history-title">
        <header className={styles.sectionHeader}><div><span>Etkin tarih geçmişi</span><h2 id="policy-history-title">Politika sürümleri</h2><p>Geçmiş sürümler yalnız okunur; talepler kendi yürürlük tarihindeki politikayla değerlendirilir.</p></div><strong>{policies.length}</strong></header>
        {policies.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">P</span><div><strong>Politika sürümü bulunmuyor</strong><p>Bir izin türü seçerek ilk yürürlük sürümünü oluşturun.</p></div></div> : <div className={styles.tableScroller}><table className={styles.dataTable}><thead><tr><th scope="col">İzin türü</th><th scope="col">Sürüm</th><th scope="col">Yürürlük</th><th scope="col">Ücret</th><th scope="col">Belge</th><th scope="col">Kazanım / Devir</th></tr></thead><tbody>{[...policies].sort((a, b) => b.effective_from.localeCompare(a.effective_from) || b.version - a.version).map((policy) => <tr key={policy.id}><td data-label="İzin türü"><strong>{policy.leave_type_name ?? leaveTypes.find((item) => item.id === policy.leave_type_id)?.name ?? policy.leave_type_code ?? "İzin"}</strong></td><td data-label="Sürüm">v{policy.version}</td><td data-label="Yürürlük">{formatLeaveDate(policy.effective_from)} – {policy.effective_to ? formatLeaveDate(policy.effective_to) : "devam ediyor"}</td><td data-label="Ücret">{policy.paid ? "Ücretli" : "Ücretsiz"}</td><td data-label="Belge">{policy.document_required ? "Zorunlu" : "Değil"}</td><td data-label="Kazanım / Devir">{policy.accrual_enabled ? `${policy.accrual_days_per_month} gün/ay` : "Kapalı"} · {policy.carryover_enabled ? `${policy.carryover_limit_days ?? 0} gün` : "Devir yok"}</td></tr>)}</tbody></table></div>}
      </section>
    </div>
  );
}

const WEEKDAY_LABELS = [
  "Pazartesi",
  "Salı",
  "Çarşamba",
  "Perşembe",
  "Cuma",
  "Cumartesi",
  "Pazar",
] as const;

function CalendarAdmin({
  calendars,
  setCalendars,
  feedback,
}: {
  calendars: HolidayCalendar[];
  setCalendars: (updater: (current: HolidayCalendar[]) => HolidayCalendar[]) => void;
  feedback: AdminFeedback;
}) {
  const [selectedId, setSelectedId] = useState(
    calendars.find((item) => item.is_default)?.id ?? calendars[0]?.id ?? "",
  );
  const [isCreating, setIsCreating] = useState(calendars.length === 0);
  const selected = isCreating
    ? null
    : calendars.find((item) => item.id === selectedId) ?? null;
  const [calendarName, setCalendarName] = useState(selected?.name ?? "Ana çalışma takvimi");
  const [isDefault, setIsDefault] = useState(selected?.is_default ?? true);
  const [nonWorkingDays, setNonWorkingDays] = useState<number[]>(
    selected?.non_working_weekdays ?? [5, 6],
  );
  const [holidayDate, setHolidayDate] = useState(localDateValue());
  const [holidayName, setHolidayName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [holidayHistoryCursor, setHolidayHistoryCursor] = useState<string | null>(null);
  const [holidayHistoryStarted, setHolidayHistoryStarted] = useState(false);
  const [isLoadingHolidayHistory, setIsLoadingHolidayHistory] = useState(false);
  const holidayHistoryGeneration = useRef(0);

  function resetHolidayHistory() {
    holidayHistoryGeneration.current += 1;
    setHolidayHistoryCursor(null);
    setHolidayHistoryStarted(false);
  }

  function selectCalendar(calendarId: string) {
    const calendar = calendars.find((item) => item.id === calendarId);
    if (!calendar) return;
    resetHolidayHistory();
    setIsCreating(false);
    setSelectedId(calendar.id);
    setCalendarName(calendar.name);
    setIsDefault(calendar.is_default);
    setNonWorkingDays(calendar.non_working_weekdays);
  }

  function startNewCalendar() {
    resetHolidayHistory();
    setIsCreating(true);
    setSelectedId("");
    setCalendarName("");
    setIsDefault(calendars.length === 0);
    setNonWorkingDays([5, 6]);
  }

  async function refreshCalendars(
    selectedCalendarId: string,
    fallback: HolidayCalendar,
  ) {
    resetHolidayHistory();
    setCalendars((current) => replaceById(current, fallback));
    setSelectedId(selectedCalendarId);
    setIsCreating(false);
    setCalendarName(fallback.name);
    setIsDefault(fallback.is_default);
    setNonWorkingDays(fallback.non_working_weekdays);
    try {
      const rows = await listHolidayCalendars(true);
      setCalendars(() => rows);
      const current = rows.find((item) => item.id === selectedCalendarId)
        ?? rows.find((item) => item.is_default)
        ?? rows[0];
      if (current) {
        setSelectedId(current.id);
        setCalendarName(current.name);
        setIsDefault(current.is_default);
        setNonWorkingDays(current.non_working_weekdays);
      }
    } catch (cause) {
      feedback.setError(
        leaveErrorPresentation(
          cause,
          "Takvim kaydedildi ancak güncel takvim listesi yenilenemedi.",
        ),
      );
    }
  }

  async function saveCalendar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving) return;
    setIsSaving(true);
    feedback.setError(null);
    feedback.setNotice(null);
    try {
      const saved = selected
        ? await updateHolidayCalendar(
            selected.id,
            {
              expected_version: selected.version,
              name: calendarName.trim(),
              is_default: isDefault,
              non_working_weekdays: [...nonWorkingDays].sort(),
            },
            commandKey(),
          )
        : await createHolidayCalendar(
            {
              name: calendarName.trim(),
              is_default: isDefault,
              non_working_weekdays: [...nonWorkingDays].sort(),
            },
            commandKey(),
          );
      await refreshCalendars(saved.id, saved);
      feedback.setNotice(selected ? "Çalışma takvimi güncellendi." : "Çalışma takvimi oluşturuldu; resmi tatiller ayrıca eklenebilir.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "Çalışma takvimi kaydedilemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  async function toggleCalendar() {
    if (!selected || isSaving) return;
    setIsSaving(true);
    feedback.setError(null);
    try {
      const updated = await updateHolidayCalendar(
        selected.id,
        { expected_version: selected.version, is_active: !selected.is_active },
        commandKey(),
      );
      await refreshCalendars(updated.id, updated);
      feedback.setNotice(updated.is_active ? "Takvim etkinleştirildi." : "Takvim pasifleştirildi; geçmiş gün hesapları korunur.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "Takvim durumu değiştirilemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  async function addHoliday(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || isSaving) return;
    setIsSaving(true);
    feedback.setError(null);
    try {
      const entry = await createHolidayEntry(
        selected.id,
        { holiday_date: holidayDate, name: holidayName.trim() },
        commandKey(),
      );
      setCalendars((current) => current.map((calendar) => calendar.id === selected.id ? { ...calendar, entries: replaceById(calendar.entries, entry) } : calendar));
      setHolidayName("");
      feedback.setNotice("Resmi tatil günü takvime eklendi. Tarih yalnız bu tenant tarafından yönetilir.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "Tatil günü eklenemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  async function toggleHoliday(entryId: string) {
    if (!selected || isSaving) return;
    const entry = selected.entries.find((item) => item.id === entryId);
    if (!entry) return;
    setIsSaving(true);
    feedback.setError(null);
    try {
      const updated = await updateHolidayEntry(
        selected.id,
        entry.id,
        { expected_version: entry.version, is_active: !entry.is_active },
        commandKey(),
      );
      setCalendars((current) => current.map((calendar) => calendar.id === selected.id ? { ...calendar, entries: replaceById(calendar.entries, updated) } : calendar));
      feedback.setNotice(updated.is_active ? "Tatil günü yeniden etkinleştirildi." : "Tatil günü pasifleştirildi; tarihsel kayıt korundu.");
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "Tatil günü güncellenemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  async function loadHolidayHistory() {
    if (!selected || isLoadingHolidayHistory) return;
    const calendarId = selected.id;
    const cursor = holidayHistoryStarted ? holidayHistoryCursor : null;
    const generation = holidayHistoryGeneration.current;
    setIsLoadingHolidayHistory(true);
    feedback.setError(null);
    try {
      const page = await listHolidayEntries(calendarId, cursor);
      if (holidayHistoryGeneration.current !== generation) return;
      setCalendars((current) => current.map((calendar) => {
        if (calendar.id !== calendarId) return calendar;
        const existing = holidayHistoryStarted ? calendar.entries : [];
        const byId = new Map(existing.map((item) => [item.id, item]));
        for (const item of page.data) byId.set(item.id, item);
        return {
          ...calendar,
          entries: [...byId.values()],
          entries_truncated: page.nextCursor !== null,
        };
      }));
      setHolidayHistoryStarted(true);
      setHolidayHistoryCursor(page.nextCursor);
    } catch (cause) {
      feedback.setError(
        leaveErrorPresentation(cause, "Tatil geçmişi yüklenemedi."),
      );
    } finally {
      setIsLoadingHolidayHistory(false);
    }
  }

  function toggleWeekday(day: number) {
    setNonWorkingDays((current) =>
      current.includes(day) ? current.filter((item) => item !== day) : [...current, day],
    );
  }

  return (
    <div className={styles.adminGrid}>
      <section className={styles.sectionCard} aria-labelledby="calendar-config-title">
        <header className={styles.sectionHeader}><div><span>Çalışma haftası</span><h2 id="calendar-config-title">Takvim yapılandırması</h2><p>Varsayılan çalışma haftası Pazartesi-Cuma’dır; resmi tatiller yalnız İK tarafından eklenir.</p></div>{selected ? <span className={styles.activeBadge} data-active={selected.is_active}>{selected.is_active ? "Etkin" : "Pasif"}</span> : null}</header>
        {calendars.length > 0 ? <div className={styles.compactForm}><div className={styles.formField}><label htmlFor="calendar-selection">Takvim</label><select id="calendar-selection" value={isCreating ? "" : selectedId} disabled={isSaving || isLoadingHolidayHistory} onChange={(event) => { if (!event.target.value) startNewCalendar(); else selectCalendar(event.target.value); }}><option value="">Yeni takvim</option>{calendars.map((calendar) => <option value={calendar.id} key={calendar.id}>{calendar.name}{calendar.is_default ? " · Varsayılan" : ""}{calendar.is_active ? "" : " · Pasif"}</option>)}</select></div><button className={styles.secondaryButton} type="button" disabled={isSaving || isCreating || isLoadingHolidayHistory} onClick={startNewCalendar}>Yeni takvim oluştur</button></div> : null}
        <form className={styles.leaveForm} onSubmit={saveCalendar}><div className={styles.formGrid}><div className={styles.formField}><label htmlFor="calendar-name">Takvim adı</label><input id="calendar-name" value={calendarName} maxLength={200} required disabled={isSaving} onChange={(event) => setCalendarName(event.target.value)} /></div><label className={styles.standaloneCheck}><input type="checkbox" checked={isDefault} disabled={isSaving} onChange={(event) => setIsDefault(event.target.checked)} /> Tenant varsayılan takvimi</label></div><fieldset className={styles.weekdayPicker}><legend>Çalışılmayan hafta günleri</legend>{WEEKDAY_LABELS.map((label, day) => <label key={label}><input type="checkbox" checked={nonWorkingDays.includes(day)} disabled={isSaving} onChange={() => toggleWeekday(day)} /> {label}</label>)}</fieldset><div className={styles.formActions}>{selected ? <button className={selected.is_active ? styles.dangerTextButton : styles.textButton} type="button" disabled={isSaving} onClick={() => void toggleCalendar()}>{selected.is_active ? "Takvimi pasifleştir" : "Takvimi etkinleştir"}</button> : null}<button className={styles.primaryButton} type="submit" disabled={isSaving || nonWorkingDays.length === 7}>{isSaving ? "Kaydediliyor…" : selected ? "Takvimi güncelle" : "Takvim oluştur"}</button></div></form>
      </section>

      <section className={styles.sectionCard} aria-labelledby="holiday-entry-title">
        <header className={styles.sectionHeader}><div><span>Tenant tarafından yönetilir</span><h2 id="holiday-entry-title">Resmi tatil günleri</h2><p>Yasal tarih tahmini yapılmaz; yalnız kurumunuzun doğruladığı günleri ekleyin.</p></div><strong>{selected?.entries.length ?? 0}</strong></header>
        {!selected ? <div className={styles.emptyState}><span aria-hidden="true">T</span><div><strong>Önce çalışma takvimi oluşturun</strong><p>Tatil günleri bir tenant takvimine bağlı olmalıdır.</p></div></div> : <>{!selected.is_active ? <div className={styles.readOnlyNotice}>Bu takvim pasif olduğu için yeni tatil eklenemez. Geçmişi inceleyebilir veya önce takvimi etkinleştirebilirsiniz.</div> : null}<form className={styles.compactForm} onSubmit={addHoliday}><div className={styles.formField}><label htmlFor="holiday-date">Tarih</label><input id="holiday-date" type="date" value={holidayDate} required disabled={isSaving || !selected.is_active} onChange={(event) => setHolidayDate(event.target.value)} /></div><div className={styles.formField}><label htmlFor="holiday-name">Tatil adı</label><input id="holiday-name" value={holidayName} maxLength={200} required disabled={isSaving || !selected.is_active} onChange={(event) => setHolidayName(event.target.value)} placeholder="Kurumca doğrulanan tatil" /></div><button className={styles.primaryButton} type="submit" disabled={isSaving || !selected.is_active}>Tatil ekle</button></form>{selected.entries.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">G</span><div><strong>{selected.entries_truncated ? "Tatil geçmişi özet sınırının dışında" : "Henüz resmi tatil eklenmedi"}</strong><p>{selected.entries_truncated ? "Kayıtları incelemek için tam tatil geçmişini yükleyin." : "Çalışma günü hesabı yalnız hafta düzenini kullanır."}</p></div></div> : <div className={styles.cardList}>{[...selected.entries].sort((a, b) => a.holiday_date.localeCompare(b.holiday_date)).map((entry) => <article className={styles.holidayRow} data-inactive={!entry.is_active} key={entry.id}><div><time dateTime={entry.holiday_date}>{formatLeaveDate(entry.holiday_date)}</time><strong>{entry.name}</strong></div><button className={entry.is_active ? styles.dangerTextButton : styles.textButton} type="button" disabled={isSaving} onClick={() => void toggleHoliday(entry.id)}>{entry.is_active ? "Pasifleştir" : "Etkinleştir"}</button></article>)}</div>}{selected.entries_truncated || (holidayHistoryStarted && holidayHistoryCursor) ? <div className={styles.loadMore}><button className={styles.secondaryButton} type="button" disabled={isLoadingHolidayHistory} onClick={() => void loadHolidayHistory()}>{isLoadingHolidayHistory ? "Tatil geçmişi yükleniyor…" : holidayHistoryStarted ? "Daha eski tatilleri göster" : "Tam tatil geçmişini yükle"}</button></div> : null}</>}
      </section>
    </div>
  );
}

function AdjustmentAdmin({
  canAdjust,
  leaveTypes,
  feedback,
}: {
  canAdjust: boolean;
  leaveTypes: LeaveType[];
  feedback: AdminFeedback;
}) {
  const currentYear = new Date().getFullYear();
  const [query, setQuery] = useState("");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [employeeId, setEmployeeId] = useState("");
  const [leaveTypeId, setLeaveTypeId] = useState(leaveTypes.find((item) => item.is_active)?.id ?? "");
  const [periodYear, setPeriodYear] = useState(currentYear);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [ledger, setLedger] = useState<LeaveLedgerEntry[]>([]);
  const [ledgerCursor, setLedgerCursor] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(localDateValue());
  const [reason, setReason] = useState("");
  const [isSearching, setIsSearching] = useState(true);
  const [isLoadingBalances, setIsLoadingBalances] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [balanceReloadKey, setBalanceReloadKey] = useState(0);
  const adjustmentCommand = useRef<{ fingerprint: string; key: string } | null>(null);
  const balanceGeneration = useRef(0);

  useEffect(() => {
    let active = true;
    void listLeaveEligibleEmployees().then(
      (rows) => {
        if (!active) return;
        const firstEmployeeId = rows[0]?.id ?? "";
        setEmployees(rows);
        setEmployeeId(firstEmployeeId);
        setIsLoadingBalances(Boolean(firstEmployeeId));
        setIsSearching(false);
      },
      (cause) => {
        if (!active) return;
        feedback.setError(leaveErrorPresentation(cause, "Çalışan seçenekleri yüklenemedi."));
        setIsSearching(false);
      },
    );
    return () => { active = false; };
  }, [feedback]);

  useEffect(() => {
    const generation = ++balanceGeneration.current;
    if (!employeeId) return;
    let active = true;
    void Promise.all([
      listEmployeeLeaveBalances(employeeId, periodYear),
      listEmployeeLeaveBalanceHistory(employeeId, {
        limit: 25,
        periodYear,
      }),
    ]).then(
      ([balanceRows, historyPage]) => {
        if (!active || balanceGeneration.current !== generation) return;
        setBalances(balanceRows);
        setLedger(historyPage.data);
        setLedgerCursor(historyPage.nextCursor);
        setIsLoadingBalances(false);
      },
      (cause) => {
        if (!active || balanceGeneration.current !== generation) return;
        feedback.setError(
          leaveErrorPresentation(cause, "Çalışanın izin bakiyesi yüklenemedi."),
        );
        setBalances([]);
        setLedger([]);
        setLedgerCursor(null);
        setIsLoadingBalances(false);
      },
    );
    return () => { active = false; };
  }, [balanceReloadKey, employeeId, feedback, periodYear]);

  function invalidateAdjustmentCommand() {
    adjustmentCommand.current = null;
    feedback.setNotice(null);
  }

  function beginBalanceLoad(nextEmployeeId: string) {
    balanceGeneration.current += 1;
    feedback.setError(null);
    setIsLoadingBalances(Boolean(nextEmployeeId));
    if (!nextEmployeeId) {
      setBalances([]);
      setLedger([]);
      setLedgerCursor(null);
    }
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSearching) return;
    setIsSearching(true);
    feedback.setError(null);
    try {
      const rows = await listLeaveEligibleEmployees(query.trim());
      setEmployees(rows);
      const firstEmployeeId = rows[0]?.id ?? "";
      const employeeChanged = firstEmployeeId !== employeeId;
      setEmployeeId(firstEmployeeId);
      if (employeeChanged) {
        beginBalanceLoad(firstEmployeeId);
      }
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "Çalışan araması tamamlanamadı."));
    } finally {
      setIsSearching(false);
    }
  }

  async function loadMoreHistory() {
    if (!employeeId || !ledgerCursor || isLoadingHistory) return;
    const generation = balanceGeneration.current;
    setIsLoadingHistory(true);
    feedback.setError(null);
    try {
      const page = await listEmployeeLeaveBalanceHistory(employeeId, {
        cursor: ledgerCursor,
        limit: 25,
        periodYear,
      });
      if (balanceGeneration.current !== generation) return;
      setLedger((current) => {
        const byId = new Map(current.map((item) => [item.id, item]));
        for (const item of page.data) byId.set(item.id, item);
        return [...byId.values()];
      });
      setLedgerCursor(page.nextCursor);
    } catch (cause) {
      feedback.setError(
        leaveErrorPresentation(cause, "Ek bakiye hareketleri yüklenemedi."),
      );
    } finally {
      setIsLoadingHistory(false);
    }
  }

  async function adjust(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const numericAmount = Number(amount);
    const normalizedReason = reason.trim();
    if (
      !canAdjust ||
      !employeeId ||
      !leaveTypeId ||
      !Number.isFinite(numericAmount) ||
      numericAmount === 0 ||
      normalizedReason.length < 3 ||
      effectiveDate.slice(0, 4) !== String(periodYear)
    ) return;
    const payload = {
      employee_id: employeeId,
      leave_type_id: leaveTypeId,
      period_year: periodYear,
      amount_days: numericAmount,
      effective_date: effectiveDate,
      reason: normalizedReason,
    };
    const fingerprint = JSON.stringify(payload);
    const key = adjustmentCommand.current?.fingerprint === fingerprint
      ? adjustmentCommand.current.key
      : commandKey();
    adjustmentCommand.current = { fingerprint, key };
    setIsSaving(true);
    feedback.setError(null);
    feedback.setNotice(null);
    try {
      await createLeaveAdjustment(payload, key);
      setAmount("");
      setReason("");
      adjustmentCommand.current = null;
      beginBalanceLoad(employeeId);
      setBalanceReloadKey((value) => value + 1);
      feedback.setNotice("Bakiye düzeltmesi append-only harekete eklendi; önceki hareketler değiştirilmedi.");
    } catch (cause) {
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status < 500
      ) {
        adjustmentCommand.current = null;
      }
      feedback.setError(leaveErrorPresentation(cause, "Bakiye düzeltmesi kaydedilemedi."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.adminGrid}>
      <section className={styles.sectionCard} aria-labelledby="employee-adjustment-search-title">
        <header className={styles.sectionHeader}><div><span>Tenant çalışan kapsamı</span><h2 id="employee-adjustment-search-title">Çalışan seçin</h2><p>Sonuçlar en fazla 25 etkin çalışanla sınırlıdır; çalışan kimliği yalnız bu İK işlemi için gönderilir.</p></div></header>
        <form className={styles.compactForm} role="search" onSubmit={search}><div className={styles.formField}><label htmlFor="adjustment-search">Çalışan ara</label><input id="adjustment-search" type="search" value={query} maxLength={320} disabled={isSearching || isLoadingHistory} onChange={(event) => setQuery(event.target.value)} placeholder="Ad, numara veya iş e-postası" /></div><button className={styles.secondaryButton} type="submit" disabled={isSearching || isLoadingHistory}>{isSearching ? "Aranıyor…" : "Ara"}</button></form>
        <div className={styles.formField}><label htmlFor="adjustment-employee">Hedef çalışan</label><select id="adjustment-employee" value={employeeId} disabled={isSearching || isLoadingHistory || employees.length === 0} onChange={(event) => { const nextEmployeeId = event.target.value; beginBalanceLoad(nextEmployeeId); setEmployeeId(nextEmployeeId); invalidateAdjustmentCommand(); }}><option value="">Çalışan seçin</option>{employees.map((employee) => <option value={employee.id} key={employee.id}>{employee.first_name} {employee.last_name} · {employee.employee_number}</option>)}</select></div>
      </section>

      <section className={styles.sectionCard} aria-labelledby="adjustment-title">
        <header className={styles.sectionHeader}><div><span>Ledger okuma modeli</span><h2 id="adjustment-title">{periodYear} izin bakiyeleri</h2><p>Kazanılan, düzeltme, kullanılan, planlanan ve kullanılabilir günler append-only hareketlerden türetilir.</p></div><div className={styles.yearControl}><label htmlFor="adjustment-year">Dönem</label><select id="adjustment-year" value={periodYear} disabled={isLoadingBalances || isLoadingHistory} onChange={(event) => { const year = Number(event.target.value); beginBalanceLoad(employeeId); setPeriodYear(year); setEffectiveDate(`${year}-01-01`); invalidateAdjustmentCommand(); }}>{[currentYear - 1, currentYear, currentYear + 1].map((year) => <option key={year} value={year}>{year}</option>)}</select></div></header>
        {!employeeId ? <div className={styles.emptyState}><span aria-hidden="true">Ç</span><div><strong>Çalışan seçilmedi</strong><p>Bakiye okuma modeli için arama sonucundan çalışan seçin.</p></div></div> : isLoadingBalances ? <div className={styles.loadingState} role="status"><span className={styles.spinner} aria-hidden="true" /><strong>Bakiyeler yükleniyor</strong></div> : balances.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">B</span><div><strong>Bu dönem için bakiye yok</strong><p>İlk kazanım veya açılış düzeltmesi oluştuğunda burada görünür.</p></div></div> : <div className={styles.balanceGrid}>{balances.map((balance) => <article className={styles.balanceCard} key={balance.id}><header><div><span>{balance.leave_type_code}</span><h3>{balance.leave_type_name}</h3></div><strong>{formatLeaveDays(balance.available_days)}<small> gün</small></strong></header><dl><div><dt>Kazanılan</dt><dd>{formatLeaveDays(balance.earned_days)}</dd></div><div><dt>Düzeltme</dt><dd>{formatLeaveDays(balance.adjusted_days)}</dd></div><div><dt>Kullanılan</dt><dd>{formatLeaveDays(balance.used_days)}</dd></div><div><dt>Planlanan</dt><dd>{formatLeaveDays(balance.planned_days)}</dd></div></dl></article>)}</div>}
      </section>

      <section className={styles.sectionCard} aria-labelledby="employee-ledger-title">
        <header className={styles.sectionHeader}><div><span>Append-only geçmiş</span><h2 id="employee-ledger-title">Bakiye hareketleri</h2><p>Hareketler geriye dönük değiştirilmez; yeni düzeltmeler ayrı satır olarak eklenir.</p></div></header>
        {isLoadingBalances ? <div className={styles.loadingState} role="status"><span className={styles.spinner} aria-hidden="true" /><strong>Hareketler yükleniyor</strong></div> : ledger.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">H</span><div><strong>Bu dönem için hareket yok</strong><p>İlk ledger kaydı oluştuğunda burada görünür.</p></div></div> : <div className={styles.tableScroller}><table className={styles.dataTable}><thead><tr><th scope="col">Etkin tarih</th><th scope="col">İzin türü</th><th scope="col">Hareket</th><th scope="col">Gün</th><th scope="col">Neden</th><th scope="col">Kayıt zamanı</th></tr></thead><tbody>{ledger.map((entry) => <tr key={entry.id}><td data-label="Etkin tarih">{formatLeaveDate(entry.effective_date)}</td><td data-label="İzin türü"><strong>{entry.leave_type_name ?? entry.leave_type_code ?? "İzin"}</strong></td><td data-label="Hareket">{formatLeaveLedgerEntry(entry.entry_type)}</td><td data-label="Gün"><strong>{entry.amount_days > 0 ? "+" : ""}{formatLeaveDays(entry.amount_days)}</strong></td><td data-label="Neden">{entry.reason ?? "Sistem hareketi"}</td><td data-label="Kayıt zamanı">{formatLeaveTimestamp(entry.created_at)}</td></tr>)}</tbody></table></div>}
        {ledgerCursor ? <div className={styles.loadMore}><button className={styles.secondaryButton} type="button" disabled={isLoadingHistory} onClick={() => void loadMoreHistory()}>{isLoadingHistory ? "Hareketler yükleniyor…" : "Daha fazla hareket göster"}</button></div> : null}
      </section>

      {canAdjust ? <section className={styles.sectionCard} aria-labelledby="manual-adjustment-title"><header className={styles.sectionHeader}><div><span>Neden zorunlu append-only işlem</span><h2 id="manual-adjustment-title">Bakiye düzeltmesi</h2><p>Açılış bakiyesi dahil her manuel değişiklik ayrı hareket olur; önceki bakiye satırı düzenlenmez.</p></div></header><form className={styles.leaveForm} onSubmit={adjust}><div className={styles.formGrid}><div className={styles.formField}><label htmlFor="adjustment-type">İzin türü</label><select id="adjustment-type" value={leaveTypeId} required disabled={isSaving} onChange={(event) => { setLeaveTypeId(event.target.value); invalidateAdjustmentCommand(); }}><option value="">Tür seçin</option>{leaveTypes.filter((item) => item.is_active).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></div><div className={styles.formField}><label htmlFor="adjustment-amount">Gün miktarı</label><input id="adjustment-amount" type="number" min="-3660" max="3660" step="0.01" value={amount} required disabled={isSaving} onChange={(event) => { setAmount(event.target.value); invalidateAdjustmentCommand(); }} placeholder="Örn. 14 veya -1" /><small>Pozitif ekler, negatif düşer; sıfır kabul edilmez.</small></div><div className={styles.formField}><label htmlFor="adjustment-effective">Etkin tarih</label><input id="adjustment-effective" type="date" value={effectiveDate} required disabled={isSaving} onChange={(event) => { setEffectiveDate(event.target.value); invalidateAdjustmentCommand(); }} /><small>Tarih {periodYear} döneminde olmalıdır.</small></div><div className={`${styles.formField} ${styles.wideField}`}><label htmlFor="adjustment-reason">İşlemsel neden</label><textarea id="adjustment-reason" rows={3} minLength={3} maxLength={500} value={reason} required disabled={isSaving} onChange={(event) => { setReason(event.target.value); invalidateAdjustmentCommand(); }} placeholder="Kısa, doğrulanabilir ve hassas olmayan gerekçe" /><small>{reason.length}/500</small></div></div><div className={styles.formActions}><button className={styles.primaryButton} type="submit" disabled={isSaving || !employeeId || !leaveTypeId || !amount || reason.trim().length < 3 || effectiveDate.slice(0, 4) !== String(periodYear)}>{isSaving ? "Düzeltme kaydediliyor…" : "Düzeltmeyi kaydet"}</button></div></form></section> : <div className={styles.readOnlyNotice}>Bakiyeleri ve geçmişi görüntüleyebilirsiniz. Manuel düzeltme için ayrı izin yönetimi yetkisi gerekir.</div>}
    </div>
  );
}

type AdminPendingDecision = {
  type: "approve" | "reject" | "cancel";
  request: LeaveRequest;
  note: string | null;
  key: string;
};

function TenantRequestAdmin({ feedback }: { feedback: AdminFeedback }) {
  const [status, setStatus] = useState<LeaveRequestStatus | "">("pending");
  const [draftStatus, setDraftStatus] = useState<LeaveRequestStatus | "">("pending");
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [detail, setDetail] = useState<LeaveRequest | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [decisionNote, setDecisionNote] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<AdminPendingDecision | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);
  const mutationLock = useRef(false);
  const requestGeneration = useRef(0);
  const decisionCommand = useRef<{ fingerprint: string; key: string } | null>(null);

  useEffect(() => {
    let active = true;
    const generation = ++requestGeneration.current;
    void listLeaveRequests({ scope: "tenant", status, limit: 25 }).then(
      (page) => {
        if (!active || requestGeneration.current !== generation) return;
        setRequests(page.data);
        setNextCursor(page.nextCursor);
        setIsLoading(false);
      },
      (cause) => {
        if (!active || requestGeneration.current !== generation) return;
        feedback.setError(leaveErrorPresentation(cause, "Tenant izin talepleri yüklenemedi."));
        setRequests([]);
        setNextCursor(null);
        setIsLoading(false);
      },
    );
    return () => { active = false; };
  }, [feedback, reloadKey, status]);

  function applyFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isLoading || isLoadingMore) return;
    requestGeneration.current += 1;
    setIsLoading(true);
    feedback.setError(null);
    setDetail(null);
    setStatus(draftStatus);
    setReloadKey((key) => key + 1);
  }

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    const generation = requestGeneration.current;
    setIsLoadingMore(true);
    feedback.setError(null);
    try {
      const page = await listLeaveRequests({ scope: "tenant", status, cursor: nextCursor, limit: 25 });
      if (requestGeneration.current !== generation) return;
      setRequests((current) => {
        const byId = new Map(current.map((item) => [item.id, item]));
        for (const item of page.data) byId.set(item.id, item);
        return [...byId.values()];
      });
      setNextCursor(page.nextCursor);
    } catch (cause) {
      if (requestGeneration.current !== generation) return;
      feedback.setError(leaveErrorPresentation(cause, "Ek izin talepleri yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function openDetail(request: LeaveRequest) {
    if (isLoadingDetail) return;
    setIsLoadingDetail(true);
    feedback.setError(null);
    feedback.setNotice(null);
    try {
      setDetail(await readLeaveRequest(request.id));
      setDecisionNote("");
      setFieldError(null);
    } catch (cause) {
      feedback.setError(leaveErrorPresentation(cause, "İzin talebi ayrıntısı yüklenemedi."));
    } finally {
      setIsLoadingDetail(false);
    }
  }

  function prepareDecision(type: "approve" | "reject" | "cancel") {
    if (!detail) return;
    const note = decisionNote.trim();
    if (type === "reject" && (note.length < 1 || note.length > 1000)) {
      setFieldError("Ret notu 1-1000 karakter arasında olmalıdır.");
      return;
    }
    if (note.length > 1000) {
      setFieldError("Karar notu en fazla 1000 karakter olabilir.");
      return;
    }
    setFieldError(null);
    const fingerprint = JSON.stringify({
      type,
      requestId: detail.id,
      version: detail.version,
      note,
    });
    const key = decisionCommand.current?.fingerprint === fingerprint
      ? decisionCommand.current.key
      : commandKey();
    decisionCommand.current = { fingerprint, key };
    setPendingDecision({ type, request: detail, note: note || null, key });
  }

  async function applyDecision() {
    const action = pendingDecision;
    if (!action || mutationLock.current) return;
    mutationLock.current = true;
    setIsDeciding(true);
    feedback.setError(null);
    feedback.setNotice(null);
    try {
      const result = action.type === "approve"
        ? await approveLeaveRequest(action.request.id, action.request.version, action.note, action.key)
        : action.type === "reject"
          ? await rejectLeaveRequest(action.request.id, action.request.version, action.note ?? "Talep uygun bulunmadı.", action.key)
          : await cancelLeaveRequest(action.request.id, action.request.version, action.note, action.key);
      requestGeneration.current += 1;
      setRequests((current) => status && result.status !== status ? current.filter((item) => item.id !== result.id) : current.map((item) => item.id === result.id ? result : item));
      setIsLoading(true);
      setReloadKey((key) => key + 1);
      setDetail(result);
      setPendingDecision(null);
      decisionCommand.current = null;
      setDecisionNote("");
      feedback.setNotice(action.type === "approve" ? "Tenant izin talebi onaylandı ve bakiye hareketleri atomik güncellendi." : action.type === "reject" ? "Tenant izin talebi reddedildi." : "Tenant izin talebi iptal edildi; ilgili bakiye hareketleri atomik güncellendi.");
    } catch (cause) {
      const presentation = leaveErrorPresentation(cause, "İzin kararı tamamlanamadı.");
      setPendingDecision(null);
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status < 500
      ) {
        decisionCommand.current = null;
      }
      feedback.setError(presentation);
      if (presentation.conflict) {
        setDetail(null);
        setIsLoading(true);
        setReloadKey((key) => key + 1);
      }
    } finally {
      mutationLock.current = false;
      setIsDeciding(false);
    }
  }

  return (
    <div className={styles.adminGrid}>
      <section className={styles.sectionCard} aria-labelledby="tenant-request-list-title">
        <header className={styles.sectionHeader}><div><span>Tenant kapsamı</span><h2 id="tenant-request-list-title">İzin talepleri</h2><p>Liste sunucuda tenant kapsamıyla, durum filtresi ve opak cursor ile sınırlandırılır.</p></div><strong>{isLoading ? "—" : requests.length}</strong></header>
        <form className={styles.compactForm} role="search" onSubmit={applyFilter}><div className={styles.formField}><label htmlFor="tenant-request-status">Talep durumu</label><select id="tenant-request-status" value={draftStatus} disabled={isLoading || isLoadingMore} onChange={(event) => setDraftStatus(event.target.value as LeaveRequestStatus | "")}><option value="">Tüm durumlar</option><option value="pending">Değerlendirmede</option><option value="approved">Onaylandı</option><option value="rejected">Reddedildi</option><option value="cancelled">İptal edildi</option></select></div><button className={styles.secondaryButton} type="submit" disabled={isLoading || isLoadingMore}>Filtreyi uygula</button></form>
        {isLoading ? <div className={styles.loadingState} role="status"><span className={styles.spinner} aria-hidden="true" /><strong>Tenant izin talepleri yükleniyor</strong></div> : requests.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">T</span><div><strong>Bu filtrede izin talebi yok</strong><p>Yeni talepler veya farklı durum seçimiyle liste güncellenir.</p></div></div> : <div className={styles.tableScroller}><table className={styles.dataTable}><thead><tr><th scope="col">Çalışan</th><th scope="col">İzin türü</th><th scope="col">Tarih</th><th scope="col">Gün</th><th scope="col">Durum</th><th scope="col">İşlem</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td data-label="Çalışan"><strong>{request.employee_name ?? "Çalışan"}</strong></td><td data-label="İzin türü">{request.leave_type_name}</td><td data-label="Tarih">{formatLeaveDate(request.start_date)} – {formatLeaveDate(request.end_date)}</td><td data-label="Gün">{formatLeaveDays(request.counted_days)}</td><td data-label="Durum"><span className={styles.statusBadge} data-status={request.status}>{LEAVE_STATUS_LABELS[request.status]}</span></td><td data-label="İşlem"><button className={styles.textButton} type="button" disabled={isLoadingDetail} onClick={() => void openDetail(request)}>Talebi aç</button></td></tr>)}</tbody></table></div>}
        {nextCursor ? <div className={styles.loadMore}><button className={styles.secondaryButton} type="button" disabled={isLoadingMore} onClick={() => void loadMore()}>{isLoadingMore ? "Talepler yükleniyor…" : "Daha fazla talep göster"}</button></div> : null}
      </section>

      {detail ? <section className={styles.detailPanel} aria-labelledby="tenant-request-detail-title"><header><div><span>Tenant talep ayrıntısı</span><h2 id="tenant-request-detail-title">{detail.employee_name ?? "Çalışan"}</h2><p>{detail.leave_type_name} · {formatLeaveDate(detail.start_date)} – {formatLeaveDate(detail.end_date)}</p></div><button className={styles.iconButton} type="button" aria-label="Talep ayrıntısını kapat" onClick={() => setDetail(null)}>×</button></header><div className={styles.detailBody}><dl className={styles.detailGrid}><div><dt>Durum</dt><dd>{LEAVE_STATUS_LABELS[detail.status]}</dd></div><div><dt>Çalışma günü</dt><dd>{formatLeaveDays(detail.counted_days)}</dd></div><div><dt>Belge</dt><dd>{detail.has_document ? "Bağlı" : "Yok"}</dd></div><div><dt>Sürüm</dt><dd>{detail.version}</dd></div></dl>{detail.employee_note ? <div className={styles.noteBox}><strong>Çalışan notu</strong><p>{detail.employee_note}</p></div> : null}{detail.decision_note ? <div className={styles.noteBox}><strong>Karar notu</strong><p>{detail.decision_note}</p></div> : null}{detail.status === "pending" ? <div className={styles.decisionArea}><div className={styles.formField}><label htmlFor="tenant-decision-note">Karar notu</label><textarea id="tenant-decision-note" rows={3} maxLength={1000} value={decisionNote} disabled={isDeciding} onChange={(event) => setDecisionNote(event.target.value)} placeholder="Ret için zorunlu; onay ve iptal için isteğe bağlı kısa not." /><small>{decisionNote.length}/1000</small>{fieldError ? <span className={styles.fieldError} role="alert">{fieldError}</span> : null}</div><div className={styles.decisionActions}><button className={styles.dangerTextButton} type="button" disabled={isDeciding} onClick={() => prepareDecision("cancel")}>İptali gözden geçir</button><button className={styles.dangerButton} type="button" disabled={isDeciding} onClick={() => prepareDecision("reject")}>Reddetmeyi gözden geçir</button><button className={styles.primaryButton} type="button" disabled={isDeciding} onClick={() => prepareDecision("approve")}>Onaylamayı gözden geçir</button></div></div> : detail.status === "approved" ? <div className={styles.decisionArea}><p>Onaylı talep iptal edildiğinde kullanılan bakiye hareketi atomik olarak serbest bırakılır.</p><div className={styles.decisionActions}><button className={styles.dangerButton} type="button" disabled={isDeciding} onClick={() => prepareDecision("cancel")}>İptali gözden geçir</button></div></div> : null}</div></section> : null}

      {pendingDecision ? <LeaveConfirmationDialog title={pendingDecision.type === "approve" ? "Tenant izin talebi onaylansın mı?" : pendingDecision.type === "reject" ? "Tenant izin talebi reddedilsin mi?" : "Tenant izin talebi iptal edilsin mi?"} description={<><strong>{pendingDecision.request.employee_name ?? "Çalışanın"} talebi karara bağlanacak.</strong><p>Sunucu tenant kapsamını, talep sürümünü, politikayı ve bakiyeyi yeniden doğrular.</p></>} confirmLabel={pendingDecision.type === "approve" ? "Talebi onayla" : pendingDecision.type === "reject" ? "Talebi reddet" : "Talebi iptal et"} busyLabel="Karar kaydediliyor…" danger={pendingDecision.type !== "approve"} isBusy={isDeciding} onCancel={() => { if (!isDeciding) { setPendingDecision(null); decisionCommand.current = null; } }} onConfirm={() => void applyDecision()} /> : null}
    </div>
  );
}
