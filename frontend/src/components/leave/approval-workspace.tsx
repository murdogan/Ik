"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  approveLeaveRequest,
  type ApprovalTask,
  type LeaveRequest,
  type TeamCalendarEntry,
  listApprovalTasks,
  listTeamCalendar,
  readLeaveRequest,
  rejectLeaveRequest,
} from "@/lib/leave";

import { LeaveConfirmationDialog } from "./leave-confirmation-dialog";
import {
  commandKey,
  formatLeaveDate,
  formatLeaveDays,
  formatLeaveTimestamp,
  leaveErrorPresentation,
  LEAVE_STATUS_LABELS,
  type LeaveErrorPresentation,
} from "./leave-presentation";
import styles from "./leave.module.css";

interface ApprovalBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  canRead: boolean;
  canApprove: boolean;
}

type PendingDecision = {
  type: "approve" | "reject";
  request: LeaveRequest;
  note: string | null;
  key: string;
};

interface CalendarDay {
  key: string;
  day: number;
  inMonth: boolean;
  events: TeamCalendarEntry[];
}

function monthRange(month: Date): { start: string; end: string } {
  const start = new Date(month.getFullYear(), month.getMonth(), 1);
  const end = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const local = (value: Date) => {
    const year = value.getFullYear();
    const part = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${part}-${day}`;
  };
  return { start: local(start), end: local(end) };
}

function calendarDays(month: Date, events: TeamCalendarEntry[]): CalendarDay[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first);
  gridStart.setDate(first.getDate() - mondayOffset);
  return Array.from({ length: 42 }, (_, index) => {
    const value = new Date(gridStart);
    value.setDate(gridStart.getDate() + index);
    const key = `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
    return {
      key,
      day: value.getDate(),
      inMonth: value.getMonth() === month.getMonth(),
      events: events.filter((event) => event.start_date <= key && event.end_date >= key),
    };
  });
}

function appendUnique(current: ApprovalTask[], incoming: ApprovalTask[]): ApprovalTask[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return [...byId.values()];
}

export function ApprovalWorkspace() {
  const { user, sessionGeneration } = useSession();
  const boundary = useMemo<ApprovalBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      canRead: hasPermission(user, AUTHORIZATION_PERMISSIONS.readTeamLeave),
      canApprove: hasPermission(user, AUTHORIZATION_PERMISSIONS.approveTeamLeave),
    }),
    [sessionGeneration, user],
  );
  const key = `${boundary.sessionGeneration}:${boundary.userId}:${boundary.membershipId}:${boundary.tenantId}:${boundary.permissionVersion}:${boundary.canRead}:${boundary.canApprove}`;
  return <ApprovalContent key={key} boundary={boundary} />;
}

function ApprovalContent({ boundary }: { boundary: ApprovalBoundary }) {
  const [view, setView] = useState<"tasks" | "calendar">("tasks");
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<LeaveErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [detail, setDetail] = useState<LeaveRequest | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [decisionNote, setDecisionNote] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [calendarEntries, setCalendarEntries] = useState<TeamCalendarEntry[]>([]);
  const [calendarError, setCalendarError] = useState<LeaveErrorPresentation | null>(null);
  const [isLoadingCalendar, setIsLoadingCalendar] = useState(false);
  const mutationLock = useRef(false);
  const queueGeneration = useRef(0);
  const decisionCommand = useRef<{ fingerprint: string; key: string } | null>(null);

  useEffect(() => {
    if (!boundary.canRead || !boundary.canApprove) return;
    let active = true;
    const generation = ++queueGeneration.current;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
      void listApprovalTasks({ limit: 25 }).then(
        (page) => {
          if (!active || queueGeneration.current !== generation) return;
          setTasks(page.data);
          setNextCursor(page.nextCursor);
          setIsLoading(false);
        },
        (cause) => {
          if (!active || queueGeneration.current !== generation) return;
          setError(leaveErrorPresentation(cause, "Onay görevleri yüklenemedi."));
          setIsLoading(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canApprove, boundary.canRead, reloadKey]);

  useEffect(() => {
    if (view !== "calendar" || !boundary.canRead) return;
    let active = true;
    const range = monthRange(month);
    queueMicrotask(() => {
      if (!active) return;
      setIsLoadingCalendar(true);
      setCalendarError(null);
      void listTeamCalendar(range.start, range.end).then(
        (entries) => {
          if (!active) return;
          setCalendarEntries(entries);
          setIsLoadingCalendar(false);
        },
        (cause) => {
          if (!active) return;
          setCalendarError(leaveErrorPresentation(cause, "Ekip takvimi yüklenemedi."));
          setIsLoadingCalendar(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canRead, month, reloadKey, view]);

  function reload() {
    queueGeneration.current += 1;
    setError(null);
    setNotice(null);
    setDetail(null);
    setReloadKey((key) => key + 1);
  }

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    const generation = queueGeneration.current;
    setIsLoadingMore(true);
    setError(null);
    try {
      const page = await listApprovalTasks({ cursor: nextCursor, limit: 25 });
      if (queueGeneration.current !== generation) return;
      setTasks((current) => appendUnique(current, page.data));
      setNextCursor(page.nextCursor);
    } catch (cause) {
      if (queueGeneration.current !== generation) return;
      setError(leaveErrorPresentation(cause, "Ek onay görevleri yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function openDetail(task: ApprovalTask) {
    if (isLoadingDetail) return;
    setIsLoadingDetail(true);
    setError(null);
    setNotice(null);
    try {
      setDetail(await readLeaveRequest(task.request.id));
      setDecisionNote("");
      setFieldError(null);
    } catch (cause) {
      setError(leaveErrorPresentation(cause, "İzin talebi ayrıntısı yüklenemedi."));
    } finally {
      setIsLoadingDetail(false);
    }
  }

  function prepareDecision(type: "approve" | "reject") {
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
    setPendingDecision({
      type,
      request: detail,
      note: note || null,
      key,
    });
  }

  async function applyDecision() {
    const action = pendingDecision;
    if (!action || mutationLock.current || !boundary.canApprove) return;
    mutationLock.current = true;
    setIsDeciding(true);
    setError(null);
    setNotice(null);
    try {
      const result = action.type === "approve"
        ? await approveLeaveRequest(
            action.request.id,
            action.request.version,
            action.note,
            action.key,
          )
        : await rejectLeaveRequest(
            action.request.id,
            action.request.version,
            action.note ?? "Talep uygun bulunmadı.",
            action.key,
          );
      queueGeneration.current += 1;
      setTasks((current) => current.filter((task) => task.request.id !== result.id));
      setReloadKey((key) => key + 1);
      setDetail(result);
      setDecisionNote("");
      setPendingDecision(null);
      decisionCommand.current = null;
      setNotice(
        action.type === "approve"
          ? "İzin talebi onaylandı; bakiye, zaman çizelgesi ve planlama atomik olarak güncellendi."
          : "İzin talebi reddedildi; bakiye kullanımı oluşturulmadı.",
      );
    } catch (cause) {
      const presentation = leaveErrorPresentation(cause, "Karar tamamlanamadı.");
      setPendingDecision(null);
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status < 500
      ) {
        decisionCommand.current = null;
      }
      setError(presentation);
      if (presentation.conflict) reload();
    } finally {
      mutationLock.current = false;
      setIsDeciding(false);
    }
  }

  const days = useMemo(
    () => calendarDays(month, calendarEntries),
    [calendarEntries, month],
  );

  if (!boundary.canRead || !boundary.canApprove) return null;

  return (
    <section className={styles.page} aria-labelledby="approval-title">
      <header className={styles.pageHeader}>
        <div>
          <span>Yönetici çalışma alanı</span>
          <h1 id="approval-title">İzin onayları</h1>
          <p>Yalnızca güncel etkin atamada doğrudan size bağlı çalışanların taleplerini değerlendirin ve ekip izinlerini takvimde görün.</p>
        </div>
        <button className={styles.secondaryButton} type="button" disabled={isLoading || isLoadingMore} onClick={reload}>Kuyruğu yenile</button>
      </header>

      <div className={styles.segmentedTabs} role="tablist" aria-label="Yönetici izin görünümleri">
        <button type="button" role="tab" aria-selected={view === "tasks"} onClick={() => setView("tasks")}>Onay görevleri</button>
        <button type="button" role="tab" aria-selected={view === "calendar"} onClick={() => setView("calendar")}>Ekip takvimi</button>
      </div>

      {error ? <div className={styles.inlineError} role="alert"><div><strong>İşlem tamamlanamadı</strong><span>{error.message}</span>{error.reference ? <small>Referans: {error.reference}</small> : null}</div><button className={styles.secondaryButton} type="button" onClick={reload}>{error.conflict ? "Güncel kuyruğu yükle" : "Yeniden dene"}</button></div> : null}
      {notice ? <div className={styles.successNotice} role="status">{notice}</div> : null}

      {view === "tasks" ? (
        <section className={styles.sectionCard} aria-labelledby="approval-queue-title">
          <header className={styles.sectionHeader}><div><span>Güncel yönetici kapsamı</span><h2 id="approval-queue-title">Bekleyen görevler</h2><p>Görev kapsamı çalışan seçimine değil, sunucudaki güncel yönetici atamasına dayanır.</p></div><strong>{isLoading ? "—" : tasks.length}</strong></header>
          {isLoading ? <div className={styles.loadingState} role="status"><span className={styles.spinner} aria-hidden="true" /><strong>Onay görevleri yükleniyor</strong></div> : tasks.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">✓</span><div><strong>Bekleyen onay görevi yok</strong><p>Ekibiniz yeni izin talebi gönderdiğinde burada görünür.</p></div></div> : <div className={styles.tableScroller}><table className={styles.dataTable}><thead><tr><th scope="col">Çalışan</th><th scope="col">İzin türü</th><th scope="col">Tarih</th><th scope="col">Gün</th><th scope="col">Gönderim</th><th scope="col">İşlem</th></tr></thead><tbody>{tasks.map((task) => <tr key={task.id}><td data-label="Çalışan"><strong>{task.request.employee_name ?? "Ekip çalışanı"}</strong>{task.manager_context ? <small>{task.manager_context}</small> : null}<small>Kullanılabilir: {formatLeaveDays(task.available_days)} gün</small></td><td data-label="İzin türü">{task.request.leave_type_name}</td><td data-label="Tarih">{formatLeaveDate(task.request.start_date)} – {formatLeaveDate(task.request.end_date)}</td><td data-label="Gün">{formatLeaveDays(task.request.counted_days)}</td><td data-label="Gönderim">{formatLeaveTimestamp(task.request.created_at)}</td><td data-label="İşlem"><button className={styles.textButton} type="button" disabled={isLoadingDetail} onClick={() => void openDetail(task)}>Talebi aç</button></td></tr>)}</tbody></table></div>}
          {nextCursor ? <div className={styles.loadMore}><button className={styles.secondaryButton} type="button" disabled={isLoadingMore} onClick={() => void loadMore()}>{isLoadingMore ? "Görevler yükleniyor…" : "Daha fazla görev göster"}</button></div> : null}
        </section>
      ) : (
        <section className={styles.sectionCard} aria-labelledby="team-calendar-title">
          <header className={styles.calendarHeader}><div><span>Ürün güvenli görünüm</span><h2 id="team-calendar-title">Ekip takvimi</h2><p>Takvim gerekçe ve belge içeriği göstermez; yalnız onaylı ekip izinlerinin gerekli özetini sunar.</p></div><div className={styles.monthActions}><button className={styles.iconButton} type="button" aria-label="Önceki ay" onClick={() => setMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}>←</button><strong>{new Intl.DateTimeFormat("tr-TR", { month: "long", year: "numeric" }).format(month)}</strong><button className={styles.iconButton} type="button" aria-label="Sonraki ay" onClick={() => setMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}>→</button></div></header>
          {calendarError ? <div className={styles.errorState} role="alert"><strong>Takvim yüklenemedi</strong><span>{calendarError.message}</span></div> : isLoadingCalendar ? <div className={styles.loadingState} role="status"><span className={styles.spinner} aria-hidden="true" /><strong>Ekip takvimi yükleniyor</strong></div> : calendarEntries.length === 0 ? <div className={styles.emptyState}><span aria-hidden="true">T</span><div><strong>Bu ay onaylı ekip izni yok</strong><p>Onaylanan izinler tarih aralığına göre burada görünür.</p></div></div> : <><div className={styles.calendarWeekdays} aria-hidden="true">{["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"].map((day) => <span key={day}>{day}</span>)}</div><div className={styles.calendarGrid}>{days.map((day) => <article className={styles.calendarDay} data-outside={!day.inMonth} key={day.key}><header><time dateTime={day.key}>{formatLeaveDate(day.key)}</time><strong>{day.day}</strong></header>{day.events.length > 0 ? <ul>{day.events.map((event) => <li key={event.id}><strong>{event.employee_name}</strong><span>{event.leave_type_name}</span></li>)}</ul> : <span className={styles.noEvent}>İzin yok</span>}</article>)}</div></>}
        </section>
      )}

      {detail ? (
        <section className={styles.detailPanel} aria-labelledby="approval-detail-title">
          <header><div><span>Onay görevi</span><h2 id="approval-detail-title">{detail.employee_name ?? "Ekip çalışanı"}</h2><p>{detail.leave_type_name} · {formatLeaveDate(detail.start_date)} – {formatLeaveDate(detail.end_date)}</p></div><button className={styles.iconButton} type="button" aria-label="Talep ayrıntısını kapat" onClick={() => setDetail(null)}>×</button></header>
          <div className={styles.detailBody}>
            <dl className={styles.detailGrid}><div><dt>Durum</dt><dd>{LEAVE_STATUS_LABELS[detail.status]}</dd></div><div><dt>Çalışma günü</dt><dd>{formatLeaveDays(detail.counted_days)}</dd></div><div><dt>Belge</dt><dd>{detail.has_document ? "Bağlı" : "Yok"}</dd></div><div><dt>Sürüm</dt><dd>{detail.version}</dd></div></dl>
            {detail.employee_note ? <div className={styles.noteBox}><strong>Çalışan notu</strong><p>{detail.employee_note}</p></div> : null}
            {detail.status === "pending" ? <div className={styles.decisionArea}><div className={styles.formField}><label htmlFor="manager-decision-note">Karar notu</label><textarea id="manager-decision-note" rows={3} maxLength={1000} value={decisionNote} disabled={isDeciding} onChange={(event) => setDecisionNote(event.target.value)} placeholder="Ret için zorunlu; onay için isteğe bağlı kısa ve işlemsel not." /><small>{decisionNote.length}/1000</small>{fieldError ? <span className={styles.fieldError} role="alert">{fieldError}</span> : null}</div><div className={styles.decisionActions}><button className={styles.dangerButton} type="button" disabled={isDeciding} onClick={() => prepareDecision("reject")}>Reddetmeyi gözden geçir</button><button className={styles.primaryButton} type="button" disabled={isDeciding} onClick={() => prepareDecision("approve")}>Onaylamayı gözden geçir</button></div></div> : <div className={styles.readOnlyNotice}>Bu görev {LEAVE_STATUS_LABELS[detail.status].toLocaleLowerCase("tr-TR")}; yeni karar verilemez.</div>}
          </div>
        </section>
      ) : null}

      {pendingDecision ? <LeaveConfirmationDialog title={pendingDecision.type === "approve" ? "İzin talebi onaylansın mı?" : "İzin talebi reddedilsin mi?"} description={pendingDecision.type === "approve" ? <><strong>{pendingDecision.request.employee_name ?? "Çalışanın"} izni onaylanacak.</strong><p>Sunucu yönetici kapsamını ve güncel talep sürümünü yeniden doğrulayacak.</p></> : <><strong>Talep karar notuyla reddedilecek.</strong><p>Bakiye kullanımı oluşturulmayacak ve çalışan talep zaman çizelgesinde kararı görecek.</p></>} confirmLabel={pendingDecision.type === "approve" ? "Talebi onayla" : "Talebi reddet"} busyLabel={pendingDecision.type === "approve" ? "Talep onaylanıyor…" : "Talep reddediliyor…"} danger={pendingDecision.type === "reject"} isBusy={isDeciding} onCancel={() => { if (!isDeciding) { setPendingDecision(null); decisionCommand.current = null; } }} onConfirm={() => void applyDecision()} /> : null}
    </section>
  );
}
