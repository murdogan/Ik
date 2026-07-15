"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type OwnEmployeeDocumentWorkspace,
  issueOwnEmployeeDocumentDownload,
  readOwnEmployeeDocuments,
} from "@/lib/employee-documents";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./own-documents.module.css";

interface OwnDocumentsBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
  employeeId: string;
}

function isCurrentBoundary(
  expected: OwnDocumentsBoundary,
  current: OwnDocumentsBoundary,
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

function messageForError(cause: unknown): string {
  if (!(cause instanceof ApiClientError)) {
    return "Belgeleriniz şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  }
  if (cause.status === null || cause.code === "network_error") {
    return "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  }
  if (cause.status === 401) return "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  if (cause.status === 403) return "Kendi belgelerinizi görüntüleme yetkiniz bulunmuyor.";
  if (cause.status === 404) return "Çalışan hesabı bağlantınız artık kullanılamıyor.";
  if (cause.status === 409) return "Belge şu anda indirilmeye hazır değil.";
  if (cause.status === 503) return "Güvenli belge depolaması geçici olarak kullanılamıyor.";
  return "Belgeleriniz şu anda yüklenemiyor. Lütfen yeniden deneyin.";
}

function formatDate(value: string | null): string {
  if (value === null) return "Süresiz";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" }).format(
    new Date(`${value}T00:00:00`),
  );
}

function formatBytes(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toLocaleString("tr-TR", {
    maximumFractionDigits: 1,
  })} MB`;
}

export function OwnDocuments({ employeeId }: { employeeId: string }) {
  const { user, sessionGeneration } = useSession();
  const canRead = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readOwnEmployeeDocuments,
  );
  const boundary = useMemo<OwnDocumentsBoundary>(
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
  const latestBoundary = useRef(boundary);
  const requestGeneration = useRef(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [workspace, setWorkspace] = useState<OwnEmployeeDocumentWorkspace | null>(null);
  const [stateBoundary, setStateBoundary] = useState(boundary);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

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
    void readOwnEmployeeDocuments(employeeId).then(
      (result) => {
        if (
          generation !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) return;
        setStateBoundary(requestBoundary);
        setWorkspace(result);
        setError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (
          generation !== requestGeneration.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) return;
        setStateBoundary(requestBoundary);
        setWorkspace(null);
        setError(messageForError(cause));
        setIsLoading(false);
      },
    );
    return () => {
      requestGeneration.current += 1;
    };
  }, [boundary, employeeId, reloadKey]);

  if (!canRead) return null;
  const current = isCurrentBoundary(stateBoundary, boundary);
  const visibleWorkspace = current ? workspace : null;
  const visibleError = current ? error : null;
  const loading = !current || isLoading;

  function reload() {
    setStateBoundary(boundary);
    setWorkspace(null);
    setError(null);
    setIsLoading(true);
    setReloadKey((key) => key + 1);
  }

  async function download(documentId: string) {
    if (downloadingId !== null) return;
    const requestBoundary = boundary;
    setDownloadingId(documentId);
    setError(null);
    try {
      const url = await issueOwnEmployeeDocumentDownload(documentId);
      if (!isCurrentBoundary(requestBoundary, latestBoundary.current)) return;
      window.location.assign(url);
    } catch (cause) {
      if (isCurrentBoundary(requestBoundary, latestBoundary.current)) {
        setError(messageForError(cause));
      }
    } finally {
      if (isCurrentBoundary(requestBoundary, latestBoundary.current)) {
        setDownloadingId(null);
      }
    }
  }

  return (
    <section className={styles.section} aria-labelledby="own-documents-title" aria-busy={loading}>
      <header>
        <div>
          <span>Özlük belgeleri</span>
          <h2 id="own-documents-title">Belgelerim</h2>
          <p>Yalnız İK tarafından size görünür yapılan ve temiz taramadan geçen belgeler.</p>
        </div>
        {visibleWorkspace ? (
          <div className={styles.summary} aria-label="Belge özeti">
            <strong>{visibleWorkspace.summary.available}</strong>
            <span>mevcut</span>
          </div>
        ) : null}
      </header>

      {loading ? (
        <div className={styles.state} role="status">Belgeleriniz yükleniyor…</div>
      ) : visibleError || !visibleWorkspace ? (
        <div className={`${styles.state} ${styles.error}`} role="alert">
          <span>{visibleError}</span>
          <button type="button" onClick={reload}>Yeniden dene</button>
        </div>
      ) : (
        <>
          {error ? <div className={`${styles.state} ${styles.error}`} role="alert">{error}</div> : null}
          {visibleWorkspace.checklist.length > 0 ? (
            <ul className={styles.checklist} aria-label="Bana görünür belge kontrol listesi">
              {visibleWorkspace.checklist.map((item) => (
                <li key={item.document_type_id}>
                  <div><strong>{item.name}</strong><span>{item.required ? "Zorunlu" : "İsteğe bağlı"}</span></div>
                  <span data-status={item.status}>
                    {item.status === "missing" ? "Eksik" : item.status === "available" ? "Mevcut" : item.status === "expiring" ? "Süresi yaklaşıyor" : "Süresi doldu"}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          {visibleWorkspace.documents.length === 0 ? (
            <div className={styles.state} role="status">
              Şu anda size görünür, indirilebilir bir belge bulunmuyor.
            </div>
          ) : (
            <ul className={styles.documents}>
              {visibleWorkspace.documents.map((document) => (
                <li key={document.id}>
                  <div>
                    <span>{document.document_type_name}</span>
                    <strong>{document.display_filename}</strong>
                    <small>
                      {formatBytes(document.size_bytes)} · {document.expires_on ? `son gün ${formatDate(document.expires_on)}` : "süresiz"}
                    </small>
                  </div>
                  <button
                    type="button"
                    disabled={downloadingId !== null}
                    onClick={() => void download(document.id)}
                  >
                    {downloadingId === document.id ? "Hazırlanıyor…" : "İndir"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
