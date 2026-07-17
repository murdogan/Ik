"use client";

import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  createPrivacyNoticeDraft,
  createRetentionPolicy,
  listManagedPrivacyNotices,
  listRetentionPolicies,
  type PrivacyNoticeDetail,
  type PrivacyNoticeDraftInput,
  type PrivacyNoticeStatus,
  type PrivacyNoticeSummary,
  publishPrivacyNotice,
  readManagedPrivacyNotice,
  type RetentionAction,
  type RetentionAnchor,
  type RetentionDataCategory,
  type RetentionDryRunResult,
  type RetentionPolicy,
  type RetentionPolicyInput,
  type RetentionPolicyStatus,
  runRetentionDryRun,
  updatePrivacyNoticeDraft,
  updateRetentionPolicy,
} from "@/lib/privacy";

import { PrivacyConfirmationDialog } from "./privacy-confirmation-dialog";
import styles from "./privacy.module.css";

interface ComplianceBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  canReadCompliance: boolean;
  canManageNotices: boolean;
  canManageRetention: boolean;
  canReadNotices: boolean;
  canReadRetention: boolean;
}

interface PrivacyError {
  message: string;
  reference: string | null;
  conflict: boolean;
}

interface CommandIdentity {
  fingerprint: string;
  key: string;
}

const NOTICE_STATUS_LABELS: Record<PrivacyNoticeStatus, string> = {
  draft: "Taslak",
  published: "Yayında",
  superseded: "Önceki sürüm",
};

const CATEGORY_LABELS: Record<RetentionDataCategory, string> = {
  employee_records: "Çalışan kayıtları",
  employee_documents: "Çalışan belgeleri",
  leave_requests: "İzin talepleri",
  audit_events: "Denetim olayları",
};

const ANCHOR_LABELS: Record<RetentionAnchor, string> = {
  employment_end_date: "İşten ayrılma tarihi",
  archived_at: "Arşivlenme zamanı",
  created_at: "Oluşturulma zamanı",
  occurred_at: "Olay zamanı",
};

const CATEGORY_ANCHORS: Record<RetentionDataCategory, RetentionAnchor> = {
  employee_records: "employment_end_date",
  employee_documents: "archived_at",
  leave_requests: "created_at",
  audit_events: "occurred_at",
};

const ACTION_LABELS: Record<RetentionAction, string> = {
  review: "İnceleme",
  delete: "Silme değerlendirmesi",
  anonymize: "Anonimleştirme değerlendirmesi",
};

const POLICY_STATUS_LABELS: Record<RetentionPolicyStatus, string> = {
  draft: "Taslak",
  active: "Aktif",
  inactive: "Pasif",
};

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function count(value: number): string {
  return new Intl.NumberFormat("tr-TR").format(value);
}

function coverage(item: PrivacyNoticeSummary): string {
  if (item.eligible_count === 0) return "%0";
  return new Intl.NumberFormat("tr-TR", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(item.acknowledged_count / item.eligible_count);
}

function privacyError(cause: unknown, fallback: string): PrivacyError {
  let message = fallback;
  let reference: string | null = null;
  let conflict = false;
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  const code = cause.code.toLocaleLowerCase("en-US");
  if (cause.status === null || code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu uyum işlemi için gerekli güncel yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Kayıt bulunamadı veya artık erişim kapsamınızda değil.";
  } else if (cause.status === 409) {
    conflict = true;
    message = "Kayıt siz işlem yaparken değişti. Güncel verileri yükleyip yeniden deneyin.";
  } else if (cause.status === 422) {
    message = "Form alanlarını ve seçilen politika değerlerini kontrol edin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  } else if (code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir yanıt alındı. Ekrandaki veriler değiştirilmedi.";
  }
  return { message, reference, conflict };
}

function shouldForgetCommand(cause: unknown): boolean {
  return (
    cause instanceof ApiClientError &&
    cause.status !== null &&
    cause.status >= 400 &&
    cause.status < 500
  );
}

function commandFor(
  current: CommandIdentity | null,
  fingerprint: string,
): CommandIdentity {
  return current?.fingerprint === fingerprint
    ? current
    : { fingerprint, key: crypto.randomUUID() };
}

export function PrivacyManagementWorkspace() {
  const { user, sessionGeneration } = useSession();
  const boundary = useMemo<ComplianceBoundary>(() => {
    const canReadCompliance = hasPermission(
      user,
      AUTHORIZATION_PERMISSIONS.readTenantPrivacyCompliance,
    );
    const canManageNotices = hasPermission(
      user,
      AUTHORIZATION_PERMISSIONS.manageTenantPrivacyNotices,
    );
    const canManageRetention = hasPermission(
      user,
      AUTHORIZATION_PERMISSIONS.manageTenantRetentionPolicies,
    );
    return {
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      canReadCompliance,
      canManageNotices,
      canManageRetention,
      canReadNotices: canReadCompliance || canManageNotices,
      canReadRetention: canReadCompliance || canManageRetention,
    };
  }, [sessionGeneration, user]);
  const boundaryKey = [
    boundary.sessionGeneration,
    boundary.userId,
    boundary.membershipId,
    boundary.tenantId,
    boundary.permissionVersion,
    boundary.canReadCompliance,
    boundary.canManageNotices,
    boundary.canManageRetention,
  ].join(":");
  return <ManagementContent key={boundaryKey} boundary={boundary} />;
}

function ManagementContent({ boundary }: { boundary: ComplianceBoundary }) {
  const [section, setSection] = useState<"notices" | "retention">(
    boundary.canReadNotices ? "notices" : "retention",
  );

  return (
    <section className={styles.page} aria-labelledby="privacy-management-title">
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>Tenant gizlilik çalışma alanı</span>
          <h1 id="privacy-management-title">Gizlilik uyumu</h1>
          <p>
            Bildirim sürümlerini, toplu okuma kaydı kapsamını ve saklama politikası
            metadatasını tenant sınırları içinde yönetin.
          </p>
        </div>
      </header>

      {boundary.canReadNotices && boundary.canReadRetention ? (
        <div className={styles.tabs} role="tablist" aria-label="Gizlilik uyumu bölümleri">
          <button
            id="privacy-notices-tab"
            type="button"
            role="tab"
            aria-selected={section === "notices"}
            aria-controls="privacy-notices-panel"
            onClick={() => setSection("notices")}
          >
            Bildirimler ve kapsam
          </button>
          <button
            id="privacy-retention-tab"
            type="button"
            role="tab"
            aria-selected={section === "retention"}
            aria-controls="privacy-retention-panel"
            onClick={() => setSection("retention")}
          >
            Saklama politikaları
          </button>
        </div>
      ) : null}

      {section === "notices" && boundary.canReadNotices ? (
        <NoticeManagement boundary={boundary} />
      ) : section === "retention" && boundary.canReadRetention ? (
        <RetentionManagement boundary={boundary} />
      ) : null}
    </section>
  );
}

function NoticeManagement({ boundary }: { boundary: ComplianceBoundary }) {
  const [items, setItems] = useState<PrivacyNoticeSummary[] | null>(null);
  const [error, setError] = useState<PrivacyError | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [editing, setEditing] = useState<PrivacyNoticeDetail | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [locale, setLocale] = useState("tr-TR");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [publishTarget, setPublishTarget] = useState<PrivacyNoticeSummary | null>(
    null,
  );
  const saveCommand = useRef<CommandIdentity | null>(null);
  const publishCommand = useRef<CommandIdentity | null>(null);

  useEffect(() => {
    if (!boundary.canReadNotices) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setItems(null);
      setError(null);
      void listManagedPrivacyNotices().then(
        (records) => {
          if (!active) return;
          setItems(records);
        },
        (cause) => {
          if (!active) return;
          setItems([]);
          setError(
            privacyError(
              cause,
              "Gizlilik bildirimi kayıtları yüklenemedi. Lütfen yeniden deneyin.",
            ),
          );
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canReadNotices, reloadKey]);

  function reload() {
    setError(null);
    setSuccess(null);
    setItems(null);
    setReloadKey((value) => value + 1);
  }

  function resetForm() {
    setEditing(null);
    setTitle("");
    setBody("");
    setLocale("tr-TR");
  }

  async function edit(item: PrivacyNoticeSummary) {
    if (!boundary.canManageNotices || item.status !== "draft" || busyKey) return;
    setBusyKey(`edit:${item.id}`);
    setError(null);
    setSuccess(null);
    try {
      const detail = await readManagedPrivacyNotice(item.id);
      if (detail.status !== "draft") {
        setError({
          message: "Yalnız taslak bildirimler düzenlenebilir. Güncel listeyi yükleyin.",
          reference: null,
          conflict: true,
        });
        return;
      }
      setEditing(detail);
      setTitle(detail.title);
      setBody(detail.body);
      setLocale(detail.locale);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (cause) {
      const presentation = privacyError(
        cause,
        "Bildirim taslağı yüklenemedi. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (presentation.conflict) reload();
    } finally {
      setBusyKey(null);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !boundary.canManageNotices ||
      busyKey ||
      title.trim() === "" ||
      body.trim() === "" ||
      locale.trim() === ""
    ) {
      return;
    }
    const input: PrivacyNoticeDraftInput = {
      title: title.trim(),
      body: body.trim(),
      locale: locale.trim(),
    };
    const fingerprint = JSON.stringify({
      tenantId: boundary.tenantId,
      noticeId: editing?.id ?? null,
      expectedRevision: editing?.revision ?? null,
      input,
    });
    const command = commandFor(saveCommand.current, fingerprint);
    saveCommand.current = command;
    setBusyKey("save");
    setError(null);
    setSuccess(null);
    try {
      if (editing) {
        await updatePrivacyNoticeDraft(
          editing.id,
          editing.revision,
          input,
          command.key,
        );
        setSuccess("Gizlilik bildirimi taslağı güncellendi.");
      } else {
        await createPrivacyNoticeDraft(input, command.key);
        setSuccess("Gizlilik bildirimi taslağı oluşturuldu.");
      }
      saveCommand.current = null;
      resetForm();
      setReloadKey((value) => value + 1);
    } catch (cause) {
      const presentation = privacyError(
        cause,
        "Gizlilik bildirimi taslağı kaydedilemedi. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (shouldForgetCommand(cause)) saveCommand.current = null;
      if (presentation.conflict) {
        resetForm();
        setReloadKey((value) => value + 1);
      }
    } finally {
      setBusyKey(null);
    }
  }

  async function publish() {
    const target = publishTarget;
    if (!boundary.canManageNotices || !target || busyKey) return;
    const fingerprint = JSON.stringify({
      tenantId: boundary.tenantId,
      noticeId: target.id,
      expectedRevision: target.revision,
      action: "publish",
    });
    const command = commandFor(publishCommand.current, fingerprint);
    publishCommand.current = command;
    setBusyKey(`publish:${target.id}`);
    setError(null);
    setSuccess(null);
    try {
      await publishPrivacyNotice(target.id, target.revision, command.key);
      publishCommand.current = null;
      setPublishTarget(null);
      if (editing?.id === target.id) resetForm();
      setSuccess(
        "Bildirim için değişmez sürüm yayınlama işlemi tamamlandı. Güncel yaşam döngüsü listede gösteriliyor.",
      );
      setReloadKey((value) => value + 1);
    } catch (cause) {
      const presentation = privacyError(
        cause,
        "Gizlilik bildirimi yayınlanamadı. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (shouldForgetCommand(cause)) publishCommand.current = null;
      if (presentation.conflict) {
        setPublishTarget(null);
        resetForm();
        setReloadKey((value) => value + 1);
      }
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div
      className={styles.managementStack}
      id="privacy-notices-panel"
      role="tabpanel"
      aria-label="Bildirimler ve kapsam"
    >
      {error ? (
        <div className={styles.errorBanner} role="alert">
          <div>
            <strong>Bildirim işlemi tamamlanamadı</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          {error.conflict ? (
            <button className={styles.secondaryButton} type="button" onClick={reload}>
              Güncel listeyi yükle
            </button>
          ) : null}
        </div>
      ) : null}
      {success ? (
        <div className={styles.successBanner} role="status" aria-live="polite">
          {success}
        </div>
      ) : null}

      {boundary.canManageNotices ? (
        <form className={styles.formCard} onSubmit={(event) => void save(event)}>
          <header>
            <div>
              <span className={styles.eyebrow}>
                {editing ? "Taslağı düzenle" : "Yeni bildirim taslağı"}
              </span>
              <h2>{editing ? editing.title : "Çalışan gizlilik bildirimi hazırlayın"}</h2>
              <p>
                Bildirim düz metin olarak saklanır. Yayınlanan sürümün metni ve içerik
                özeti sonradan değiştirilemez.
              </p>
            </div>
          </header>
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>Başlık</span>
              <input
                value={title}
                maxLength={200}
                required
                disabled={busyKey !== null}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>Dil / yerel ayar</span>
              <input
                value={locale}
                maxLength={16}
                pattern="[A-Za-z]{2,3}(-[A-Za-z]{2}|-[A-Za-z]{4})?"
                placeholder="tr-TR"
                required
                disabled={busyKey !== null}
                onChange={(event) => setLocale(event.target.value)}
              />
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span>Bildirim metni</span>
              <textarea
                value={body}
                maxLength={20_000}
                required
                disabled={busyKey !== null}
                onChange={(event) => setBody(event.target.value)}
              />
              <small>{body.length}/20000 · yalnız düz metin</small>
            </label>
          </div>
          <div className={styles.formActions}>
            {editing ? (
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={busyKey !== null}
                onClick={resetForm}
              >
                Düzenlemeyi kapat
              </button>
            ) : null}
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={
                busyKey !== null ||
                title.trim() === "" ||
                body.trim() === "" ||
                locale.trim() === ""
              }
            >
              {busyKey === "save"
                ? "Taslak kaydediliyor…"
                : editing
                  ? "Taslağı güncelle"
                  : "Taslak oluştur"}
            </button>
          </div>
        </form>
      ) : (
        <div className={styles.readOnlyNotice}>
          Bildirimleri ve toplu kapsam sayılarını görüntülüyorsunuz. Taslak oluşturma ve
          yayınlama için ayrıca bildirim yönetimi yetkisi gerekir.
        </div>
      )}

      <section className={styles.sectionCard} aria-labelledby="managed-notices-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Sürüm yaşam döngüsü</span>
            <h2 id="managed-notices-title">Bildirim kayıtları ve toplu kapsam</h2>
            <p>
              Yalnız tenant kapsamındaki uygun üyelik ve okuma kaydı sayılarını gösterir;
              çalışan bazlı izleme verisi içermez.
            </p>
          </div>
          <button
            className={styles.secondaryButton}
            type="button"
            disabled={items === null}
            onClick={reload}
          >
            Listeyi yenile
          </button>
        </header>
        {items === null ? (
          <div className={styles.loadingState} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <div>
              <strong>Bildirim kayıtları yükleniyor</strong>
              <p>En fazla 50 sürüm ve toplu kapsam sayıları hazırlanıyor…</p>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.emptyState}>
            <span className={styles.stateIcon} aria-hidden="true">0</span>
            <div>
              <strong>Henüz bildirim kaydı yok</strong>
              <p>Yetkiniz varsa ilk taslağı yukarıdaki formdan oluşturabilirsiniz.</p>
            </div>
          </div>
        ) : (
          <div className={styles.noticeList}>
            {items.map((item) => (
              <article className={styles.managedNoticeCard} key={item.id}>
                <header>
                  <div>
                    <span>{item.locale} · sürüm {item.notice_version}</span>
                    <h3>{item.title}</h3>
                    <small>
                      {item.published_at
                        ? `Yayın: ${formatDateTime(item.published_at)}`
                        : `Güncelleme: ${formatDateTime(item.updated_at)}`}
                    </small>
                  </div>
                  <span className={styles.statusBadge} data-status={item.status}>
                    {NOTICE_STATUS_LABELS[item.status]}
                  </span>
                </header>
                <div className={styles.coverageGrid}>
                  <div>
                    <span>Kapsamdaki hesap</span>
                    <strong>{count(item.eligible_count)}</strong>
                  </div>
                  <div>
                    <span>Okuma kaydı</span>
                    <strong>{count(item.acknowledged_count)}</strong>
                  </div>
                  <div>
                    <span>Kapsam</span>
                    <strong>{coverage(item)}</strong>
                  </div>
                  <div>
                    <span>Revizyon</span>
                    <strong>{item.revision}</strong>
                  </div>
                </div>
                <div className={styles.hashLine}>
                  <span>SHA-256</span>
                  <code>{item.content_hash}</code>
                </div>
                {boundary.canManageNotices && item.status === "draft" ? (
                  <footer className={styles.cardActions}>
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      disabled={busyKey !== null}
                      onClick={() => void edit(item)}
                    >
                      {busyKey === `edit:${item.id}` ? "Taslak yükleniyor…" : "Düzenle"}
                    </button>
                    <button
                      className={styles.primaryButton}
                      type="button"
                      disabled={busyKey !== null}
                      onClick={() => setPublishTarget(item)}
                    >
                      Yayınla
                    </button>
                  </footer>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      {publishTarget ? (
        <PrivacyConfirmationDialog
          title="Gizlilik bildirimini yayınla"
          description={
            <div>
              <strong>{publishTarget.title}</strong>
              <p>
                Taslak yeni ve değişmez bir bildirim sürümüne dönüşecek. Metin, sürüm ve
                içerik özeti yayınlandıktan sonra düzenlenemez.
              </p>
            </div>
          }
          confirmLabel="Değişmez sürümü yayınla"
          busyLabel="Yayınlanıyor…"
          isBusy={busyKey === `publish:${publishTarget.id}`}
          onCancel={() => setPublishTarget(null)}
          onConfirm={() => void publish()}
        />
      ) : null}
    </div>
  );
}

function RetentionManagement({ boundary }: { boundary: ComplianceBoundary }) {
  const [policies, setPolicies] = useState<RetentionPolicy[] | null>(null);
  const [error, setError] = useState<PrivacyError | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [editing, setEditing] = useState<RetentionPolicy | null>(null);
  const [dataCategory, setDataCategory] =
    useState<RetentionDataCategory>("employee_records");
  const [legalBasisNote, setLegalBasisNote] = useState("");
  const [retentionDays, setRetentionDays] = useState("365");
  const [anchor, setAnchor] = useState<RetentionAnchor>("employment_end_date");
  const [action, setAction] = useState<RetentionAction>("review");
  const [status, setStatus] = useState<RetentionPolicyStatus>("draft");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [selectedPolicyIds, setSelectedPolicyIds] = useState<string[]>([]);
  const [dryRun, setDryRun] = useState<RetentionDryRunResult | null>(null);
  const saveCommand = useRef<CommandIdentity | null>(null);

  useEffect(() => {
    if (!boundary.canReadRetention) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setPolicies(null);
      setError(null);
      void listRetentionPolicies().then(
        (records) => {
          if (!active) return;
          setPolicies(records);
          setSelectedPolicyIds((current) =>
            current.filter((id) => records.some((policy) => policy.id === id)),
          );
        },
        (cause) => {
          if (!active) return;
          setPolicies([]);
          setError(
            privacyError(
              cause,
              "Saklama politikası metadatası yüklenemedi. Lütfen yeniden deneyin.",
            ),
          );
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canReadRetention, reloadKey]);

  function reload() {
    setError(null);
    setSuccess(null);
    setPolicies(null);
    setDryRun(null);
    setReloadKey((value) => value + 1);
  }

  function resetForm() {
    setEditing(null);
    setDataCategory("employee_records");
    setLegalBasisNote("");
    setRetentionDays("365");
    setAnchor("employment_end_date");
    setAction("review");
    setStatus("draft");
  }

  function edit(policy: RetentionPolicy) {
    if (!boundary.canManageRetention || busyKey) return;
    setEditing(policy);
    setDataCategory(policy.data_category);
    setLegalBasisNote(policy.legal_basis_note);
    setRetentionDays(String(policy.retention_days));
    setAnchor(CATEGORY_ANCHORS[policy.data_category]);
    setAction(policy.action);
    setStatus(policy.status);
    setError(null);
    setSuccess(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedDays = Number(retentionDays);
    if (
      !boundary.canManageRetention ||
      busyKey ||
      legalBasisNote.trim() === "" ||
      !Number.isSafeInteger(parsedDays) ||
      parsedDays < 1 ||
      parsedDays > 36_500
    ) {
      return;
    }
    const input: RetentionPolicyInput = {
      data_category: dataCategory,
      legal_basis_note: legalBasisNote.trim(),
      retention_days: parsedDays,
      anchor,
      action,
      status,
    };
    const fingerprint = JSON.stringify({
      tenantId: boundary.tenantId,
      policyId: editing?.id ?? null,
      expectedVersion: editing?.version ?? null,
      input,
    });
    const command = commandFor(saveCommand.current, fingerprint);
    saveCommand.current = command;
    setBusyKey("save-policy");
    setError(null);
    setSuccess(null);
    try {
      if (editing) {
        await updateRetentionPolicy(editing.id, editing.version, input, command.key);
        setSuccess("Saklama politikası metadatası güncellendi.");
      } else {
        await createRetentionPolicy(input, command.key);
        setSuccess("Saklama politikası metadatası oluşturuldu.");
      }
      saveCommand.current = null;
      resetForm();
      setDryRun(null);
      setReloadKey((value) => value + 1);
    } catch (cause) {
      const presentation = privacyError(
        cause,
        "Saklama politikası kaydedilemedi. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (shouldForgetCommand(cause)) saveCommand.current = null;
      if (presentation.conflict) {
        resetForm();
        setReloadKey((value) => value + 1);
      }
    } finally {
      setBusyKey(null);
    }
  }

  async function runDryRun() {
    if (!boundary.canManageRetention || busyKey) return;
    const selected = [...selectedPolicyIds].sort();
    setBusyKey("dry-run");
    setError(null);
    setSuccess(null);
    try {
      const result = await runRetentionDryRun(selected);
      setDryRun(result);
      setSuccess("Sayım envanteri hazırlandı. Kaynak veri kayıtları değiştirilmedi.");
    } catch (cause) {
      const presentation = privacyError(
        cause,
        "Saklama envanteri hazırlanamadı. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (presentation.conflict) reload();
    } finally {
      setBusyKey(null);
    }
  }

  const totalDryRunCount =
    dryRun?.items.reduce((total, item) => total + item.count, 0) ?? 0;

  return (
    <div
      className={styles.managementStack}
      id="privacy-retention-panel"
      role="tabpanel"
      aria-label="Saklama politikaları"
    >
      <div className={styles.scopeNotice}>
        <span aria-hidden="true">i</span>
        <div>
          <strong>Yalnız metadata ve sayım envanteri</strong>
          <p>
            Bu çalışma alanı otomatik silme veya anonimleştirme çalıştırmaz. Sonuçlar hukuki
            uygunluk garantisi değil, politika değerlendirmesi için tenant kapsamlı sayımlardır.
          </p>
        </div>
      </div>

      {error ? (
        <div className={styles.errorBanner} role="alert">
          <div>
            <strong>Saklama işlemi tamamlanamadı</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          {error.conflict ? (
            <button className={styles.secondaryButton} type="button" onClick={reload}>
              Güncel listeyi yükle
            </button>
          ) : null}
        </div>
      ) : null}
      {success ? (
        <div className={styles.successBanner} role="status" aria-live="polite">
          {success}
        </div>
      ) : null}

      {boundary.canManageRetention ? (
        <form className={styles.formCard} onSubmit={(event) => void save(event)}>
          <header>
            <div>
              <span className={styles.eyebrow}>
                {editing ? "Politikayı düzenle" : "Yeni politika metadatası"}
              </span>
              <h2>{editing ? CATEGORY_LABELS[editing.data_category] : "Saklama politikası tanımlayın"}</h2>
              <p>
                Süre, başlangıç noktası ve öngörülen işlem yalnız değerlendirme metadatasıdır;
                fiziksel veri işlemi başlatmaz.
              </p>
            </div>
          </header>
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>Veri kategorisi</span>
              <select
                value={dataCategory}
                disabled={busyKey !== null}
                onChange={(event) => {
                  const category = event.target.value as RetentionDataCategory;
                  setDataCategory(category);
                  setAnchor(CATEGORY_ANCHORS[category]);
                }}
              >
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>Saklama süresi (gün)</span>
              <input
                type="number"
                min={1}
                max={36_500}
                step={1}
                value={retentionDays}
                required
                disabled={busyKey !== null}
                onChange={(event) => setRetentionDays(event.target.value)}
              />
            </label>
            <label className={styles.field}>
              <span>Süre başlangıç noktası</span>
              <select
                value={anchor}
                disabled
                aria-describedby="retention-anchor-note"
              >
                <option value={anchor}>{ANCHOR_LABELS[anchor]}</option>
              </select>
              <small id="retention-anchor-note">Veri kategorisine göre sabittir.</small>
            </label>
            <label className={styles.field}>
              <span>Politika işlemi</span>
              <select
                value={action}
                disabled={busyKey !== null}
                onChange={(event) => setAction(event.target.value as RetentionAction)}
              >
                {Object.entries(ACTION_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>Durum</span>
              <select
                value={status}
                disabled={busyKey !== null}
                onChange={(event) => setStatus(event.target.value as RetentionPolicyStatus)}
              >
                {Object.entries(POLICY_STATUS_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className={`${styles.field} ${styles.fieldFull}`}>
              <span>Hukuki / politika dayanağı notu</span>
              <textarea
                className={styles.compactTextarea}
                value={legalBasisNote}
                maxLength={1_000}
                required
                disabled={busyKey !== null}
                onChange={(event) => setLegalBasisNote(event.target.value)}
              />
              <small>{legalBasisNote.length}/1000</small>
            </label>
          </div>
          <div className={styles.formActions}>
            {editing ? (
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={busyKey !== null}
                onClick={resetForm}
              >
                Düzenlemeyi kapat
              </button>
            ) : null}
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={
                busyKey !== null ||
                legalBasisNote.trim() === "" ||
                !Number.isSafeInteger(Number(retentionDays)) ||
                Number(retentionDays) < 1
              }
            >
              {busyKey === "save-policy"
                ? "Politika kaydediliyor…"
                : editing
                  ? "Politikayı güncelle"
                  : "Politika oluştur"}
            </button>
          </div>
        </form>
      ) : (
        <div className={styles.readOnlyNotice}>
          Politika metadatasını salt okunur görüntülüyorsunuz. Değişiklik ve sayım
          envanteri için ayrıca saklama politikası yönetimi yetkisi gerekir.
        </div>
      )}

      <section className={styles.sectionCard} aria-labelledby="retention-policy-list-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Tenant politikaları</span>
            <h2 id="retention-policy-list-title">Saklama politikası metadatası</h2>
            <p>
              Envantere dahil etmek istediğiniz politikaları seçin. Seçim yapılmazsa tüm
              erişilebilir politikalar sayılır.
            </p>
          </div>
          <button
            className={styles.secondaryButton}
            type="button"
            disabled={policies === null}
            onClick={reload}
          >
            Listeyi yenile
          </button>
        </header>
        {policies === null ? (
          <div className={styles.loadingState} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <div>
              <strong>Politika metadatası yükleniyor</strong>
              <p>Tenant kapsamındaki kayıtlar hazırlanıyor…</p>
            </div>
          </div>
        ) : policies.length === 0 ? (
          <div className={styles.emptyState}>
            <span className={styles.stateIcon} aria-hidden="true">0</span>
            <div>
              <strong>Henüz saklama politikası yok</strong>
              <p>Yetkiniz varsa ilk politika metadatasını yukarıdaki formdan oluşturabilirsiniz.</p>
            </div>
          </div>
        ) : (
          <div className={styles.policyList}>
            {policies.map((policy) => (
              <article
                className={`${styles.policyCard} ${
                  boundary.canManageRetention ? "" : styles.policyCardReadOnly
                }`}
                key={policy.id}
              >
                {boundary.canManageRetention ? (
                  <label className={styles.policySelection}>
                    <input
                      type="checkbox"
                      checked={selectedPolicyIds.includes(policy.id)}
                      disabled={busyKey !== null}
                      onChange={(event) =>
                        setSelectedPolicyIds((current) =>
                          event.target.checked
                            ? [...current, policy.id]
                            : current.filter((id) => id !== policy.id),
                        )
                      }
                    />
                    <span>Envantere seç</span>
                  </label>
                ) : null}
                <header>
                  <div>
                    <span>{policy.data_category}</span>
                    <h3>{CATEGORY_LABELS[policy.data_category]}</h3>
                  </div>
                  <span className={styles.statusBadge} data-status={policy.status}>
                    {POLICY_STATUS_LABELS[policy.status]}
                  </span>
                </header>
                <p>{policy.legal_basis_note}</p>
                <dl className={styles.policyMetadata}>
                  <div><dt>Süre</dt><dd>{count(policy.retention_days)} gün</dd></div>
                  <div><dt>Başlangıç</dt><dd>{ANCHOR_LABELS[policy.anchor]}</dd></div>
                  <div><dt>İşlem</dt><dd>{ACTION_LABELS[policy.action]}</dd></div>
                  <div><dt>Sürüm</dt><dd>{policy.version}</dd></div>
                </dl>
                <footer>
                  <span>Güncelleme: {formatDateTime(policy.updated_at)}</span>
                  {boundary.canManageRetention ? (
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      disabled={busyKey !== null}
                      onClick={() => edit(policy)}
                    >
                      Düzenle
                    </button>
                  ) : null}
                </footer>
              </article>
            ))}
          </div>
        )}
        {boundary.canManageRetention && policies && policies.length > 0 ? (
          <div className={styles.inventoryAction}>
            <div>
              <strong>Sayım envanteri</strong>
              <p>
                {selectedPolicyIds.length === 0
                  ? "Tüm erişilebilir politikalar sayılacak."
                  : `${selectedPolicyIds.length} politika sayılacak.`}
              </p>
            </div>
            <button
              className={styles.primaryButton}
              type="button"
              disabled={busyKey !== null}
              onClick={() => void runDryRun()}
            >
              {busyKey === "dry-run" ? "Sayım hazırlanıyor…" : "Sayım envanterini çalıştır"}
            </button>
          </div>
        ) : null}
      </section>

      {dryRun ? (
        <section className={styles.sectionCard} aria-labelledby="dry-run-result-title">
          <header className={styles.sectionHeader}>
            <div>
              <span className={styles.eyebrow}>Salt sayım sonucu</span>
              <h2 id="dry-run-result-title">Saklama envanteri</h2>
              <p>
                {formatDateTime(dryRun.as_of)} itibarıyla {count(totalDryRunCount)} kayıt.
                Çalışan veya belge satırı gösterilmez ve değiştirilmez.
              </p>
            </div>
          </header>
          {dryRun.items.length === 0 ? (
            <div className={styles.emptyState}>
              <span className={styles.stateIcon} aria-hidden="true">0</span>
              <div>
                <strong>Sayılacak kayıt bulunmadı</strong>
                <p>Seçilen politikalar için eşik öncesi tenant kaydı yok.</p>
              </div>
            </div>
          ) : (
            <div className={styles.tableScroller}>
              <table className={styles.inventoryTable}>
                <thead>
                  <tr>
                    <th>Kategori</th>
                    <th>Politika</th>
                    <th>Eşik zamanı</th>
                    <th>İşlem</th>
                    <th>Durum</th>
                    <th>Sayım</th>
                  </tr>
                </thead>
                <tbody>
                  {dryRun.items.map((item) => (
                    <tr key={item.policy_id}>
                      <td>{CATEGORY_LABELS[item.data_category]}</td>
                      <td>{count(item.retention_days)} gün · sürüm {item.policy_version}</td>
                      <td>{formatDateTime(item.cutoff_at)}</td>
                      <td>{ACTION_LABELS[item.action]}</td>
                      <td>{POLICY_STATUS_LABELS[item.status]}</td>
                      <td><strong>{count(item.count)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
