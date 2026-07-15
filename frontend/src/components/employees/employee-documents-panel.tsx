"use client";

import Link from "next/link";
import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
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
  type DocumentChecklistStatus,
  type DocumentProcessingState,
  type EmployeeDocument,
  type EmployeeDocumentType,
  type EmployeeDocumentWorkspace,
  issueEmployeeDocumentDownload,
  readEmployeeDocuments,
  setEmployeeDocumentArchived,
  updateEmployeeDocumentMetadata,
  uploadEmployeeDocument,
} from "@/lib/employee-documents";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./employee-documents.module.css";

interface DocumentsBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
  employeeId: string;
}

interface LoadState {
  boundary: DocumentsBoundary;
  workspace: EmployeeDocumentWorkspace | null;
  error: DocumentError | null;
  isLoading: boolean;
}

interface DocumentError {
  message: string;
  reference: string | null;
  conflict: boolean;
}

const PROCESSING_LABELS: Record<DocumentProcessingState, string> = {
  pending_upload: "Yükleme bekleniyor",
  pending_scan: "Güvenlik taramasında",
  available: "Kullanılabilir",
  infected: "Karantinada",
  scan_error: "Tarama hatası",
  rejected: "Reddedildi",
};

const CHECKLIST_LABELS: Record<DocumentChecklistStatus, string> = {
  missing: "Eksik",
  available: "Mevcut",
  expiring: "Süresi yaklaşıyor",
  expired: "Süresi doldu",
};

function isCurrentBoundary(
  expected: DocumentsBoundary,
  current: DocumentsBoundary,
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

function errorPresentation(cause: unknown): DocumentError {
  let message = "Belge işlemi şu anda tamamlanamıyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;
  if (cause instanceof TypeError) {
    return { message: cause.message, reference, conflict };
  }
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir belge yanıtı alındı.";
  } else if (
    cause.status === null ||
    cause.code === "network_error" ||
    cause.code === "object_upload_failed"
  ) {
    message = "Belge aktarımı sırasında sunucuya ulaşılamadı. Bağlantınızı kontrol edin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Çalışan belgelerini yönetmek için gerekli İK yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Belge, belge türü veya çalışan kaydı artık bulunamıyor.";
  } else if (cause.status === 409) {
    message = "Belge siz işlem yaparken değişti. Güncel listeyi yükleyip yeniden deneyin.";
    conflict = true;
  } else if (cause.status === 422) {
    message = "Dosya türü, boyutu, tarihleri ve görünürlük ayarlarını kontrol edin.";
  } else if (cause.status === 503) {
    message = "Güvenli belge depolaması şu anda kullanılamıyor. Daha sonra yeniden deneyin.";
  }
  return { message, reference, conflict };
}

function formatBytes(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toLocaleString("tr-TR", {
    maximumFractionDigits: 1,
  })} MB`;
}

function formatDate(value: string | null): string {
  if (value === null) return "Belirtilmemiş";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" }).format(
    new Date(`${value}T00:00:00`),
  );
}

function DocumentMetadataEditor({
  document,
  documentType,
  busy,
  onSave,
  onCancel,
}: {
  document: EmployeeDocument;
  documentType: EmployeeDocumentType | undefined;
  busy: boolean;
  onSave: (payload: {
    expected_version: number;
    display_filename: string;
    issued_on: string | null;
    expires_on: string | null;
    employee_visible: boolean;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [filename, setFilename] = useState(document.display_filename);
  const [issuedOn, setIssuedOn] = useState(document.issued_on ?? "");
  const [expiresOn, setExpiresOn] = useState(document.expires_on ?? "");
  const [employeeVisible, setEmployeeVisible] = useState(document.employee_visible);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSave({
      expected_version: document.version,
      display_filename: filename.trim(),
      issued_on: issuedOn || null,
      expires_on: expiresOn || null,
      employee_visible: employeeVisible,
    });
  }

  return (
    <form className={styles.metadataForm} onSubmit={submit}>
      <label>
        <span>Görünen dosya adı</span>
        <input
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          required
          maxLength={255}
          disabled={busy}
        />
      </label>
      <label>
        <span>Düzenlenme tarihi</span>
        <input
          type="date"
          value={issuedOn}
          onChange={(event) => setIssuedOn(event.target.value)}
          disabled={busy}
        />
      </label>
      <label>
        <span>Geçerlilik sonu</span>
        <input
          type="date"
          value={expiresOn}
          min={issuedOn || undefined}
          onChange={(event) => setExpiresOn(event.target.value)}
          required={documentType?.expiry_mode === "required"}
          disabled={busy || documentType?.expiry_mode === "none"}
        />
      </label>
      <label className={styles.checkboxLabel}>
        <input
          type="checkbox"
          checked={employeeVisible}
          onChange={(event) => setEmployeeVisible(event.target.checked)}
          disabled={busy || !documentType?.employee_visible}
        />
        <span>Çalışan kendi profilinden görebilsin</span>
      </label>
      <div className={styles.formActions}>
        <button type="button" onClick={onCancel} disabled={busy}>
          Vazgeç
        </button>
        <button className={styles.primaryButton} type="submit" disabled={busy}>
          {busy ? "Kaydediliyor…" : "Kaydet"}
        </button>
      </div>
    </form>
  );
}

export function EmployeeDocumentsPanel({
  employeeId,
  employeeArchived,
}: {
  employeeId: string;
  employeeArchived: boolean;
}) {
  const { user, sessionGeneration } = useSession();
  const canManage = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.manageEmployeeDocuments,
  );
  const boundary = useMemo<DocumentsBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canManage,
      employeeId,
    }),
    [
      canManage,
      employeeId,
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
  const [state, setState] = useState<LoadState>(() => ({
    boundary,
    workspace: null,
    error: null,
    isLoading: true,
  }));
  const [selectedTypeId, setSelectedTypeId] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [issuedOn, setIssuedOn] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [employeeVisible, setEmployeeVisible] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<DocumentError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    const generation = ++requestGeneration.current;
    const requestBoundary = boundary;
    void readEmployeeDocuments(employeeId).then(
      (workspace) => {
        if (
          generation !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          workspace,
          error: null,
          isLoading: false,
        });
        const firstType = workspace.document_types[0];
        setSelectedTypeId(firstType?.id ?? "");
        setEmployeeVisible(firstType?.employee_visible ?? false);
        if (firstType?.expiry_mode === "none") setExpiresOn("");
      },
      (cause) => {
        if (
          generation !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setState({
          boundary: requestBoundary,
          workspace: null,
          error: errorPresentation(cause),
          isLoading: false,
        });
      },
    );
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary, employeeId, reloadKey]);

  const stateIsCurrent = isCurrentBoundary(state.boundary, boundary);
  const workspace = stateIsCurrent ? state.workspace : null;
  const loadError = stateIsCurrent ? state.error : null;
  const isLoading = !stateIsCurrent || state.isLoading;
  const selectedType = workspace?.document_types.find(
    (item) => item.id === selectedTypeId,
  );

  function reload() {
    setState({ boundary, workspace: null, error: null, isLoading: true });
    setReloadKey((key) => key + 1);
  }

  async function runAction(
    actionKey: string,
    operation: () => Promise<unknown>,
    successMessage: string,
  ) {
    if (busyAction !== null || !boundary.permissionGranted) return;
    const requestBoundary = boundary;
    setBusyAction(actionKey);
    setActionError(null);
    setNotice(null);
    try {
      await operation();
      if (!isCurrentBoundary(requestBoundary, latestBoundary.current)) return;
      setNotice(successMessage);
      setEditingDocumentId(null);
      reload();
    } catch (cause) {
      if (!isCurrentBoundary(requestBoundary, latestBoundary.current)) return;
      const presentation = errorPresentation(cause);
      setActionError(presentation);
      if (presentation.conflict) reload();
    } finally {
      if (isCurrentBoundary(requestBoundary, latestBoundary.current)) {
        setBusyAction(null);
      }
    }
  }

  function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile || !selectedType) return;
    void runAction(
      "upload",
      async () => {
        if (selectedFile.size > selectedType.max_size_bytes) {
          throw new TypeError(
            `Dosya bu tür için ${formatBytes(selectedType.max_size_bytes)} sınırını aşıyor.`,
          );
        }
        const document = await uploadEmployeeDocument(employeeId, selectedFile, {
          documentTypeId: selectedType.id,
          issuedOn: issuedOn || null,
          expiresOn: expiresOn || null,
          employeeVisible,
        });
        if (document.processing_state === "infected") {
          reload();
          throw new TypeError("Dosya güvenlik taramasında karantinaya alındı ve indirilemez.");
        }
        if (document.processing_state === "scan_error") {
          reload();
          throw new TypeError("Dosya yüklendi ancak güvenlik taraması tamamlanamadı.");
        }
        setSelectedFile(null);
        setIssuedOn("");
        setExpiresOn("");
        if (fileInputRef.current) fileInputRef.current.value = "";
      },
      "Belge güvenle yüklendi ve kullanıma hazırlandı.",
    );
  }

  if (!canManage) return null;

  return (
    <div className={styles.panel} aria-busy={isLoading || busyAction !== null}>
      <header className={styles.panelHeader}>
        <div>
          <span>Özlük dosyası</span>
          <h2>Belgeler ve kontrol listesi</h2>
          <p>
            Zorunlu belge durumlarını izleyin; PDF, JPEG veya PNG belgeleri güvenli taramadan
            geçirerek yönetin.
          </p>
        </div>
        <Link href="/document-types">Belge türlerini yönet</Link>
      </header>

      {isLoading ? (
        <div className={styles.loadingState} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          Belge kontrol listesi yükleniyor…
        </div>
      ) : loadError || !workspace ? (
        <div className={styles.errorState} role="alert">
          <div>
            <strong>Belgeler yüklenemedi</strong>
            <span>{loadError?.message}</span>
            {loadError?.reference ? <small>Referans: {loadError.reference}</small> : null}
          </div>
          <button type="button" onClick={reload}>Yeniden dene</button>
        </div>
      ) : (
        <>
          <section className={styles.summaryGrid} aria-label="Belge durumu özeti">
            <div><span>Eksik zorunlu</span><strong>{workspace.summary.missing}</strong></div>
            <div><span>Mevcut</span><strong>{workspace.summary.available}</strong></div>
            <div><span>Süresi yaklaşan</span><strong>{workspace.summary.expiring}</strong></div>
            <div><span>Süresi dolan</span><strong>{workspace.summary.expired}</strong></div>
          </section>

          {actionError ? (
            <div className={styles.errorState} role="alert">
              <div>
                <strong>İşlem tamamlanamadı</strong>
                <span>{actionError.message}</span>
                {actionError.reference ? <small>Referans: {actionError.reference}</small> : null}
              </div>
            </div>
          ) : null}
          {notice ? <div className={styles.notice} role="status">{notice}</div> : null}

          <section className={styles.checklistSection} aria-labelledby="document-checklist-title">
            <header>
              <h3 id="document-checklist-title">Özlük kontrol listesi</h3>
              <p>Arşivli ve taraması tamamlanmamış belgeler gerekliliği karşılamaz.</p>
            </header>
            {workspace.checklist.length === 0 ? (
              <div className={styles.emptyState}>Henüz aktif belge türü tanımlanmadı.</div>
            ) : (
              <ul className={styles.checklist}>
                {workspace.checklist.map((item) => (
                  <li key={item.document_type_id}>
                    <div>
                      <strong>{item.name}</strong>
                      <span>{item.required ? "Zorunlu" : "İsteğe bağlı"}</span>
                    </div>
                    <span className={styles[`status_${item.status}`]}>
                      {CHECKLIST_LABELS[item.status]}
                    </span>
                    <small>{item.expires_on ? `Son gün ${formatDate(item.expires_on)}` : "Süresiz"}</small>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {!employeeArchived ? (
            <section className={styles.uploadSection} aria-labelledby="document-upload-title">
              <header>
                <h3 id="document-upload-title">Yeni belge yükle</h3>
                <p>Dosya yalnız temiz güvenlik taramasından sonra indirilebilir olur.</p>
              </header>
              {workspace.document_types.length === 0 ? (
                <div className={styles.emptyState}>
                  Yükleme için önce aktif bir <Link href="/document-types">belge türü</Link> tanımlayın.
                </div>
              ) : (
                <form className={styles.uploadForm} onSubmit={submitUpload}>
                  <label>
                    <span>Belge türü</span>
                    <select
                      value={selectedTypeId}
                      onChange={(event) => {
                        const nextType = workspace.document_types.find(
                          (item) => item.id === event.target.value,
                        );
                        setSelectedTypeId(event.target.value);
                        setEmployeeVisible(nextType?.employee_visible ?? false);
                        if (nextType?.expiry_mode === "none") setExpiresOn("");
                      }}
                      required
                      disabled={busyAction !== null}
                    >
                      {workspace.document_types.map((item) => (
                        <option value={item.id} key={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Dosya</span>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                      onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                      required
                      disabled={busyAction !== null}
                    />
                    <small>
                      {selectedType
                        ? `${selectedType.allowed_extensions.map((item) => item.toLocaleUpperCase("tr-TR")).join(", ")} · en fazla ${formatBytes(selectedType.max_size_bytes)}`
                        : "PDF, JPEG veya PNG"}
                    </small>
                  </label>
                  <label>
                    <span>Düzenlenme tarihi</span>
                    <input
                      type="date"
                      value={issuedOn}
                      onChange={(event) => setIssuedOn(event.target.value)}
                      disabled={busyAction !== null}
                    />
                  </label>
                  <label>
                    <span>Geçerlilik sonu</span>
                    <input
                      type="date"
                      value={expiresOn}
                      min={issuedOn || undefined}
                      onChange={(event) => setExpiresOn(event.target.value)}
                      required={selectedType?.expiry_mode === "required"}
                      disabled={busyAction !== null || selectedType?.expiry_mode === "none"}
                    />
                  </label>
                  <label className={styles.checkboxLabel}>
                    <input
                      type="checkbox"
                      checked={employeeVisible}
                      onChange={(event) => setEmployeeVisible(event.target.checked)}
                      disabled={busyAction !== null || !selectedType?.employee_visible}
                    />
                    <span>Çalışan kendi profilinden görebilsin</span>
                  </label>
                  <button
                    className={styles.primaryButton}
                    type="submit"
                    disabled={busyAction !== null || selectedFile === null || !selectedType}
                  >
                    {busyAction === "upload" ? "Yükleniyor ve taranıyor…" : "Güvenli yüklemeyi başlat"}
                  </button>
                </form>
              )}
            </section>
          ) : (
            <div className={styles.archivedNote} role="note">
              Arşivlenmiş çalışan kaydına yeni belge yüklenemez; korunan belgeler indirilebilir ve
              arşiv durumu yönetilebilir.
            </div>
          )}

          <section className={styles.documentSection} aria-labelledby="employee-document-list-title">
            <header>
              <h3 id="employee-document-list-title">Çalışan belgeleri</h3>
              <p>Dosya içeriği yalnız kısa süreli, yetkili indirme bağlantısıyla açılır.</p>
            </header>
            {workspace.documents.length === 0 ? (
              <div className={styles.emptyState}>Bu çalışan için henüz belge bulunmuyor.</div>
            ) : (
              <div className={styles.documentList}>
                {workspace.documents.map((document) => {
                  const documentType = workspace.document_types.find(
                    (item) => item.id === document.document_type_id,
                  );
                  const busy = busyAction === document.id;
                  return (
                    <article
                      className={document.archived_at ? styles.archivedDocument : undefined}
                      key={document.id}
                    >
                      <header>
                        <div>
                          <span>{document.document_type_name}</span>
                          <h4>{document.display_filename}</h4>
                          <p>
                            {formatBytes(document.size_bytes)} · {formatDate(document.issued_on)}
                            {document.expires_on ? ` · son gün ${formatDate(document.expires_on)}` : ""}
                          </p>
                        </div>
                        <span className={styles[`processing_${document.processing_state}`]}>
                          {PROCESSING_LABELS[document.processing_state]}
                        </span>
                      </header>
                      <div className={styles.documentFlags}>
                        <span>{document.employee_visible ? "Çalışana görünür" : "Yalnız İK"}</span>
                        {document.archived_at ? <span>Arşivli</span> : null}
                      </div>

                      {editingDocumentId === document.id ? (
                        <DocumentMetadataEditor
                          document={document}
                          documentType={documentType}
                          busy={busy}
                          onCancel={() => setEditingDocumentId(null)}
                          onSave={(payload) =>
                            runAction(
                              document.id,
                              () => updateEmployeeDocumentMetadata(employeeId, document.id, payload),
                              "Belge bilgileri güncellendi.",
                            )
                          }
                        />
                      ) : (
                        <footer className={styles.documentActions}>
                          <button
                            type="button"
                            disabled={!document.downloadable || busyAction !== null}
                            onClick={() =>
                              void runAction(
                                document.id,
                                async () => {
                                  const url = await issueEmployeeDocumentDownload(employeeId, document.id);
                                  window.location.assign(url);
                                },
                                "İndirme bağlantısı hazırlandı.",
                              )
                            }
                          >
                            İndir
                          </button>
                          {document.archived_at === null ? (
                            <button
                              type="button"
                              disabled={busyAction !== null}
                              onClick={() => setEditingDocumentId(document.id)}
                            >
                              Bilgileri düzenle
                            </button>
                          ) : null}
                          <button
                            type="button"
                            disabled={busyAction !== null}
                            onClick={() =>
                              void runAction(
                                document.id,
                                () =>
                                  setEmployeeDocumentArchived(
                                    employeeId,
                                    document.id,
                                    document.version,
                                    document.archived_at === null,
                                  ),
                                document.archived_at === null
                                  ? "Belge arşivlendi."
                                  : "Belge arşivden çıkarıldı.",
                              )
                            }
                          >
                            {busy ? "İşleniyor…" : document.archived_at === null ? "Arşivle" : "Arşivden çıkar"}
                          </button>
                        </footer>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
