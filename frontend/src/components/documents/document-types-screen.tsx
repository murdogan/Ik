"use client";

import { type FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type DocumentExpiryMode,
  type DocumentSensitivity,
  type DocumentTypeCreate,
  type DocumentTypeMutation,
  type EmployeeDocumentType,
  createDocumentType,
  listDocumentTypes,
  setDocumentTypeArchived,
  updateDocumentType,
} from "@/lib/employee-documents";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./document-types.module.css";

interface Boundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
}

interface TypeFormProps {
  initial?: EmployeeDocumentType;
  busy: boolean;
  onCancel?: () => void;
  onSubmit: (payload: DocumentTypeCreate | DocumentTypeMutation) => Promise<void>;
}

const SENSITIVITY_LABELS: Record<DocumentSensitivity, string> = {
  standard: "Standart",
  sensitive: "Hassas",
  highly_sensitive: "Çok hassas",
};

const EXPIRY_LABELS: Record<DocumentExpiryMode, string> = {
  none: "Süre sonu yok",
  optional: "Süre sonu isteğe bağlı",
  required: "Süre sonu zorunlu",
};

function isCurrent(expected: Boundary, current: Boundary): boolean {
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

function errorMessage(cause: unknown): { message: string; reference: string | null; conflict: boolean } {
  let message = "Belge türü işlemi tamamlanamadı. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Belge türlerini yönetmek için gerekli İK yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Belge türü artık bulunamıyor.";
  } else if (cause.status === 409) {
    message = "Belge türü siz işlem yaparken değişti. Listeyi yenileyip tekrar deneyin.";
    conflict = true;
  } else if (cause.status === 422) {
    message = "Kod, dosya biçimleri, boyut ve süre politikasını kontrol edin.";
  }
  return { message, reference, conflict };
}

function TypeForm({ initial, busy, onCancel, onSubmit }: TypeFormProps) {
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [required, setRequired] = useState(initial?.required ?? true);
  const [employeeVisible, setEmployeeVisible] = useState(initial?.employee_visible ?? false);
  const [sensitivity, setSensitivity] = useState<DocumentSensitivity>(
    initial?.sensitivity ?? "sensitive",
  );
  const [expiryMode, setExpiryMode] = useState<DocumentExpiryMode>(
    initial?.expiry_mode ?? "optional",
  );
  const [allowPdf, setAllowPdf] = useState(
    initial ? initial.allowed_mime_types.includes("application/pdf") : true,
  );
  const [allowJpeg, setAllowJpeg] = useState(
    initial ? initial.allowed_mime_types.includes("image/jpeg") : true,
  );
  const [allowPng, setAllowPng] = useState(
    initial ? initial.allowed_mime_types.includes("image/png") : true,
  );
  const [maxSizeMb, setMaxSizeMb] = useState(
    initial ? String(initial.max_size_bytes / (1024 * 1024)) : "20",
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const allowedMimeTypes: DocumentTypeMutation["allowed_mime_types"] = [];
    const allowedExtensions: DocumentTypeMutation["allowed_extensions"] = [];
    if (allowPdf) {
      allowedMimeTypes.push("application/pdf");
      allowedExtensions.push("pdf");
    }
    if (allowJpeg) {
      allowedMimeTypes.push("image/jpeg");
      allowedExtensions.push("jpg", "jpeg");
    }
    if (allowPng) {
      allowedMimeTypes.push("image/png");
      allowedExtensions.push("png");
    }
    const payload: DocumentTypeMutation = {
      name: name.trim(),
      description: description.trim() || null,
      required,
      employee_visible: employeeVisible,
      sensitivity,
      expiry_mode: expiryMode,
      allowed_mime_types: allowedMimeTypes,
      allowed_extensions: allowedExtensions,
      max_size_bytes: Math.round(Number(maxSizeMb) * 1024 * 1024),
    };
    void onSubmit(initial ? payload : { code: code.trim(), ...payload });
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <label>
        <span>Sabit kod</span>
        <input
          value={code}
          onChange={(event) => setCode(event.target.value.toLocaleLowerCase("en-US"))}
          pattern="[a-z][a-z0-9_]{0,63}"
          maxLength={64}
          required
          disabled={busy || initial !== undefined}
        />
      </label>
      <label>
        <span>Belge türü adı</span>
        <input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required disabled={busy} />
      </label>
      <label className={styles.wideField}>
        <span>Açıklama</span>
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={500} rows={2} disabled={busy} />
      </label>
      <label>
        <span>Hassasiyet</span>
        <select value={sensitivity} onChange={(event) => setSensitivity(event.target.value as DocumentSensitivity)} disabled={busy}>
          {Object.entries(SENSITIVITY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select>
      </label>
      <label>
        <span>Süre politikası</span>
        <select value={expiryMode} onChange={(event) => setExpiryMode(event.target.value as DocumentExpiryMode)} disabled={busy}>
          {Object.entries(EXPIRY_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select>
      </label>
      <fieldset className={styles.wideField}>
        <legend>İzin verilen dosyalar</legend>
        <label><input type="checkbox" checked={allowPdf} onChange={(event) => setAllowPdf(event.target.checked)} disabled={busy} /> PDF</label>
        <label><input type="checkbox" checked={allowJpeg} onChange={(event) => setAllowJpeg(event.target.checked)} disabled={busy} /> JPG / JPEG</label>
        <label><input type="checkbox" checked={allowPng} onChange={(event) => setAllowPng(event.target.checked)} disabled={busy} /> PNG</label>
      </fieldset>
      <label>
        <span>En fazla dosya boyutu (MB)</span>
        <input type="number" value={maxSizeMb} onChange={(event) => setMaxSizeMb(event.target.value)} min="0.1" max="50" step="0.1" required disabled={busy} />
      </label>
      <div className={styles.switches}>
        <label><input type="checkbox" checked={required} onChange={(event) => setRequired(event.target.checked)} disabled={busy} /> Zorunlu belge</label>
        <label><input type="checkbox" checked={employeeVisible} onChange={(event) => setEmployeeVisible(event.target.checked)} disabled={busy} /> Çalışana görünür olabilir</label>
      </div>
      <div className={styles.formActions}>
        {onCancel ? <button type="button" onClick={onCancel} disabled={busy}>Vazgeç</button> : null}
        <button className={styles.primaryButton} type="submit" disabled={busy || (!allowPdf && !allowJpeg && !allowPng)}>
          {busy ? "Kaydediliyor…" : initial ? "Değişiklikleri kaydet" : "Belge türü oluştur"}
        </button>
      </div>
    </form>
  );
}

export function DocumentTypesScreen() {
  const { user, sessionGeneration } = useSession();
  const canManage = hasPermission(user, AUTHORIZATION_PERMISSIONS.manageDocumentTypes);
  const boundary = useMemo<Boundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canManage,
    }),
    [canManage, sessionGeneration, user.id, user.membership_id, user.permission_version, user.tenant_id],
  );
  const latestBoundary = useRef(boundary);
  const generation = useRef(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [types, setTypes] = useState<EmployeeDocumentType[] | null>(null);
  const [stateBoundary, setStateBoundary] = useState(boundary);
  const [error, setError] = useState<{ message: string; reference: string | null } | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => { generation.current += 1; };
  }, [boundary]);

  useEffect(() => {
    if (!boundary.permissionGranted) return () => { generation.current += 1; };
    const requestId = ++generation.current;
    const requestBoundary = boundary;
    void listDocumentTypes().then(
      (records) => {
        if (requestId !== generation.current || !isCurrent(requestBoundary, latestBoundary.current)) return;
        setStateBoundary(requestBoundary);
        setTypes(records);
        setError(null);
      },
      (cause) => {
        if (requestId !== generation.current || !isCurrent(requestBoundary, latestBoundary.current)) return;
        const presentation = errorMessage(cause);
        setStateBoundary(requestBoundary);
        setTypes(null);
        setError({ message: presentation.message, reference: presentation.reference });
      },
    );
    return () => { generation.current += 1; };
  }, [boundary, reloadKey]);

  const current = isCurrent(stateBoundary, boundary);
  const visibleTypes = current ? types : null;
  const visibleError = current ? error : null;

  function reload() {
    setStateBoundary(boundary);
    setTypes(null);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  async function runAction(key: string, operation: () => Promise<unknown>, success: string) {
    if (busyKey !== null || !boundary.permissionGranted) return;
    const requestBoundary = boundary;
    setBusyKey(key);
    setError(null);
    setNotice(null);
    try {
      await operation();
      if (!isCurrent(requestBoundary, latestBoundary.current)) return;
      setEditingId(null);
      setNotice(success);
      reload();
    } catch (cause) {
      if (!isCurrent(requestBoundary, latestBoundary.current)) return;
      const presentation = errorMessage(cause);
      setError({ message: presentation.message, reference: presentation.reference });
      if (presentation.conflict) reload();
    } finally {
      if (isCurrent(requestBoundary, latestBoundary.current)) setBusyKey(null);
    }
  }

  if (!canManage) {
    return <section className={styles.page}><div className={styles.errorState} role="alert"><strong>Erişim yok</strong><span>Belge türleri yalnız özel İK belge yetkisiyle yönetilebilir.</span></div></section>;
  }

  return (
    <section className={styles.page} aria-labelledby="document-types-title">
      <header className={styles.hero}>
        <span>Özlük politikası</span>
        <h1 id="document-types-title">Belge türleri</h1>
        <p>Zorunluluk, çalışan görünürlüğü, hassasiyet, süre ve dosya kurallarını tenant genelinde tanımlayın.</p>
      </header>

      {visibleError ? <div className={styles.errorState} role="alert"><div><strong>İşlem tamamlanamadı</strong><span>{visibleError.message}</span>{visibleError.reference ? <small>Referans: {visibleError.reference}</small> : null}</div><button type="button" onClick={reload}>Yeniden dene</button></div> : null}
      {notice ? <div className={styles.notice} role="status">{notice}</div> : null}

      <section className={styles.createCard} aria-labelledby="create-document-type-title">
        <header><h2 id="create-document-type-title">Yeni belge türü</h2><p>Kod oluşturulduktan sonra değişmez.</p></header>
        <TypeForm
          busy={busyKey === "create"}
          onSubmit={(payload) => runAction("create", () => createDocumentType(payload as DocumentTypeCreate), "Belge türü oluşturuldu.")}
        />
      </section>

      <section className={styles.listSection} aria-labelledby="document-type-list-title">
        <header><h2 id="document-type-list-title">Tanımlı türler</h2><p>Arşivlenen türler yeni yüklemelerde kullanılamaz; geçmiş belgeler korunur.</p></header>
        {visibleTypes === null ? (
          <div className={styles.loadingState} role="status">Belge türleri yükleniyor…</div>
        ) : visibleTypes.length === 0 ? (
          <div className={styles.loadingState}>Henüz belge türü tanımlanmadı.</div>
        ) : (
          <div className={styles.typeList}>
            {visibleTypes.map((item) => (
              <article className={item.archived_at ? styles.archived : undefined} key={item.id}>
                <header>
                  <div><span>{item.code}</span><h3>{item.name}</h3><p>{item.description ?? "Açıklama eklenmemiş"}</p></div>
                  <div className={styles.badges}><span>{item.required ? "Zorunlu" : "İsteğe bağlı"}</span><span>{SENSITIVITY_LABELS[item.sensitivity]}</span>{item.archived_at ? <span>Arşivli</span> : null}</div>
                </header>
                <dl><div><dt>Dosyalar</dt><dd>{item.allowed_extensions.map((value) => value.toLocaleUpperCase("tr-TR")).join(", ")}</dd></div><div><dt>Boyut</dt><dd>{(item.max_size_bytes / (1024 * 1024)).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB</dd></div><div><dt>Süre</dt><dd>{EXPIRY_LABELS[item.expiry_mode]}</dd></div><div><dt>Çalışan</dt><dd>{item.employee_visible ? "Görünür yapılabilir" : "Yalnız İK"}</dd></div></dl>
                {editingId === item.id ? (
                  <TypeForm
                    initial={item}
                    busy={busyKey === item.id}
                    onCancel={() => setEditingId(null)}
                    onSubmit={(payload) => runAction(item.id, () => updateDocumentType(item.id, item.version, payload), "Belge türü güncellendi.")}
                  />
                ) : (
                  <footer><button type="button" disabled={busyKey !== null || item.archived_at !== null} onClick={() => setEditingId(item.id)}>Düzenle</button><button type="button" disabled={busyKey !== null} onClick={() => void runAction(item.id, () => setDocumentTypeArchived(item.id, item.version, item.archived_at === null), item.archived_at === null ? "Belge türü arşivlendi." : "Belge türü arşivden çıkarıldı.")}>{busyKey === item.id ? "İşleniyor…" : item.archived_at === null ? "Arşivle" : "Arşivden çıkar"}</button></footer>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
