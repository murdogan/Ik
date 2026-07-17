"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  acknowledgeOwnPrivacyNotice,
  type ConsentAction,
  type ConsentPurposeState,
  type OwnConsentState,
  type OwnPrivacyNoticeState,
  readOwnConsentState,
  readOwnPrivacyNotice,
  transitionOwnConsent,
} from "@/lib/privacy";

import { PrivacyConfirmationDialog } from "./privacy-confirmation-dialog";
import styles from "./privacy.module.css";

interface PrivacyBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  canRead: boolean;
  canAcknowledge: boolean;
  canManageConsent: boolean;
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

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
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
    message = "Bu gizlilik işlemi için güncel yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Kayıt bulunamadı veya artık erişim kapsamınızda değil.";
  } else if (cause.status === 409) {
    conflict = true;
    message = "Gizlilik kaydı siz işlem yaparken değişti. Güncel durumu yükleyin.";
  } else if (cause.status === 422) {
    message = "İşlem verileri güncel kayıtla eşleşmiyor. Sayfayı yenileyip yeniden deneyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  } else if (code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir yanıt alındı. Ekrandaki durum değiştirilmedi.";
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

function purposeWithUpdate(
  current: ConsentPurposeState[],
  incoming: ConsentPurposeState,
): ConsentPurposeState[] {
  return current.map((purpose) =>
    purpose.id === incoming.id ? incoming : purpose,
  );
}

export function PrivacyCenter() {
  const { user, sessionGeneration } = useSession();
  const boundary = useMemo<PrivacyBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      canRead: hasPermission(
        user,
        AUTHORIZATION_PERMISSIONS.readOwnPrivacyNotice,
      ),
      canAcknowledge: hasPermission(
        user,
        AUTHORIZATION_PERMISSIONS.acknowledgeOwnPrivacyNotice,
      ),
      canManageConsent: hasPermission(
        user,
        AUTHORIZATION_PERMISSIONS.manageOwnPrivacyConsent,
      ),
    }),
    [sessionGeneration, user],
  );
  const boundaryKey = [
    boundary.sessionGeneration,
    boundary.userId,
    boundary.membershipId,
    boundary.tenantId,
    boundary.permissionVersion,
    boundary.canRead,
    boundary.canAcknowledge,
    boundary.canManageConsent,
  ].join(":");
  return <PrivacyCenterContent key={boundaryKey} boundary={boundary} />;
}

function PrivacyCenterContent({ boundary }: { boundary: PrivacyBoundary }) {
  const [noticeState, setNoticeState] = useState<OwnPrivacyNoticeState | null>(null);
  const [consentState, setConsentState] = useState<OwnConsentState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<PrivacyError | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const [pendingPurposeId, setPendingPurposeId] = useState<string | null>(null);
  const [grantTarget, setGrantTarget] = useState<ConsentPurposeState | null>(null);
  const [withdrawTarget, setWithdrawTarget] = useState<ConsentPurposeState | null>(
    null,
  );
  const acknowledgeCommand = useRef<CommandIdentity | null>(null);
  const consentCommand = useRef<CommandIdentity | null>(null);

  useEffect(() => {
    if (!boundary.canRead) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
      const consents = boundary.canManageConsent
        ? readOwnConsentState()
        : Promise.resolve<OwnConsentState>({ purposes: [] });
      void Promise.all([readOwnPrivacyNotice(), consents]).then(
        ([nextNotice, nextConsents]) => {
          if (!active) return;
          setNoticeState(nextNotice);
          setConsentState(nextConsents);
          setIsLoading(false);
        },
        (cause) => {
          if (!active) return;
          setNoticeState(null);
          setConsentState(null);
          setError(
            privacyError(
              cause,
              "Gizlilik merkeziniz şu anda yüklenemiyor. Lütfen yeniden deneyin.",
            ),
          );
          setIsLoading(false);
        },
      );
    });
    return () => {
      active = false;
    };
  }, [boundary.canManageConsent, boundary.canRead, reloadKey]);

  function reload() {
    setSuccess(null);
    setError(null);
    setIsLoading(true);
    setReloadKey((value) => value + 1);
  }

  async function acknowledgeNotice() {
    const notice = noticeState?.notice;
    if (
      !notice ||
      noticeState.acknowledged_at ||
      !boundary.canAcknowledge ||
      isAcknowledging
    ) {
      return;
    }
    const fingerprint = JSON.stringify({
      tenantId: boundary.tenantId,
      membershipId: boundary.membershipId,
      noticeId: notice.id,
      contentHash: notice.content_hash,
    });
    const previous = acknowledgeCommand.current;
    const command =
      previous?.fingerprint === fingerprint
        ? previous
        : { fingerprint, key: crypto.randomUUID() };
    acknowledgeCommand.current = command;
    setIsAcknowledging(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await acknowledgeOwnPrivacyNotice(
        notice.id,
        notice.content_hash,
        command.key,
      );
      acknowledgeCommand.current = null;
      setNoticeState(result);
      setSuccess("Okuma kaydınız bu bildirim sürümü ve içerik özetiyle oluşturuldu.");
      setIsLoading(true);
      setReloadKey((value) => value + 1);
    } catch (cause) {
      const presentation = privacyError(
        cause,
        "Bildirim okuma kaydı oluşturulamadı. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (shouldForgetCommand(cause)) acknowledgeCommand.current = null;
      if (presentation.conflict) reload();
    } finally {
      setIsAcknowledging(false);
    }
  }

  async function transitionConsent(
    purpose: ConsentPurposeState,
    action: ConsentAction,
  ) {
    if (!boundary.canManageConsent || pendingPurposeId !== null) return;
    const fingerprint = JSON.stringify({
      tenantId: boundary.tenantId,
      membershipId: boundary.membershipId,
      purposeId: purpose.id,
      purposeVersion: purpose.version,
      stateVersion: purpose.state_version,
      action,
    });
    const previous = consentCommand.current;
    const command =
      previous?.fingerprint === fingerprint
        ? previous
        : { fingerprint, key: crypto.randomUUID() };
    consentCommand.current = command;
    setPendingPurposeId(purpose.id);
    setError(null);
    setSuccess(null);
    try {
      const updated = await transitionOwnConsent(purpose.id, action, command.key);
      consentCommand.current = null;
      setConsentState((current) =>
        current
          ? { purposes: purposeWithUpdate(current.purposes, updated) }
          : current,
      );
      setGrantTarget(null);
      setWithdrawTarget(null);
      setSuccess(
        action === "grant"
          ? `${purpose.title} amacı için isteğe bağlı onayınız kaydedildi.`
          : `${purpose.title} amacı için isteğe bağlı onayınız geri çekildi.`,
      );
    } catch (cause) {
      const presentation = privacyError(
        cause,
        action === "grant"
          ? "İsteğe bağlı onay verilemedi. Lütfen yeniden deneyin."
          : "İsteğe bağlı onay geri çekilemedi. Lütfen yeniden deneyin.",
      );
      setError(presentation);
      if (shouldForgetCommand(cause)) consentCommand.current = null;
      if (presentation.conflict) reload();
    } finally {
      setPendingPurposeId(null);
    }
  }

  if (!boundary.canRead) return null;

  if (isLoading) {
    return (
      <section className={styles.page} aria-busy="true">
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Gizlilik merkeziniz hazırlanıyor</strong>
            <p>
              {boundary.canManageConsent
                ? "Güncel bildirim ve isteğe bağlı onay durumunuz yükleniyor…"
                : "Güncel çalışan gizlilik bildiriminiz yükleniyor…"}
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (error && (!noticeState || !consentState)) {
    return (
      <section className={styles.page}>
        <div className={styles.errorState} role="alert">
          <span className={styles.stateIcon} aria-hidden="true">!</span>
          <div>
            <h1>Gizlilik merkezi yüklenemedi</h1>
            <p>{error.message}</p>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          <button className={styles.secondaryButton} type="button" onClick={reload}>
            Yeniden dene
          </button>
        </div>
      </section>
    );
  }

  const notice = noticeState?.notice ?? null;
  const purposes = consentState?.purposes ?? [];

  return (
    <section className={styles.page} aria-labelledby="privacy-center-title">
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>Çalışan gizlilik merkezi</span>
          <h1 id="privacy-center-title">Gizlilik ve isteğe bağlı onaylar</h1>
          <p>
            Güncel çalışan gizlilik bildirimini okuyun ve yalnız isteğe bağlı amaçlar
            için verdiğiniz onayları yönetin.
          </p>
        </div>
        <button className={styles.secondaryButton} type="button" onClick={reload}>
          Güncel durumu yükle
        </button>
      </header>

      {error ? (
        <div className={styles.errorBanner} role="alert">
          <div>
            <strong>İşlem tamamlanamadı</strong>
            <span>{error.message}</span>
            {error.reference ? <small>Referans: {error.reference}</small> : null}
          </div>
          {error.conflict ? (
            <button className={styles.secondaryButton} type="button" onClick={reload}>
              Güncel durumu yükle
            </button>
          ) : null}
        </div>
      ) : null}
      {success ? (
        <div className={styles.successBanner} role="status" aria-live="polite">
          {success}
        </div>
      ) : null}

      <section className={styles.noticeSection} aria-labelledby="privacy-notice-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Çalışan bildirimi</span>
            <h2 id="privacy-notice-title">Güncel gizlilik bildirimi</h2>
          </div>
          {notice ? (
            <span className={styles.statusBadge} data-status="published">
              Sürüm {notice.notice_version}
            </span>
          ) : null}
        </header>
        {notice ? (
          <div className={styles.noticeContent}>
            <div className={styles.noticeHeading}>
              <div>
                <span>{notice.locale}</span>
                <h3>{notice.title}</h3>
              </div>
              <span
                className={
                  noticeState?.acknowledged_at
                    ? styles.acknowledgedBadge
                    : styles.pendingBadge
                }
              >
                {noticeState?.acknowledged_at
                  ? "Okundu kaydedildi"
                  : "Okuma kaydı bekliyor"}
              </span>
            </div>
            <div className={styles.noticeBody}>{notice.body}</div>
            <dl className={styles.metadataGrid}>
              <div>
                <dt>Yayın zamanı</dt>
                <dd>{formatDateTime(notice.published_at)}</dd>
              </div>
              <div>
                <dt>Bildirim sürümü</dt>
                <dd>{notice.notice_version}</dd>
              </div>
              <div className={styles.hashField}>
                <dt>İçerik özeti (SHA-256)</dt>
                <dd><code>{notice.content_hash}</code></dd>
              </div>
              <div>
                <dt>Kayıt zamanı</dt>
                <dd>{formatDateTime(noticeState?.acknowledged_at ?? null)}</dd>
              </div>
            </dl>
            <div className={styles.noticeAction}>
              {noticeState?.acknowledged_at ? (
                <p>
                  Okuma kaydınız bu değişmez bildirim sürümü ve içerik özetiyle bağlıdır.
                </p>
              ) : boundary.canAcknowledge ? (
                <>
                  <p>
                    Bu işlem yalnız bildirimi okuduğunuzu kaydeder; isteğe bağlı amaçlara
                    ayrıca onay vermez.
                  </p>
                  <button
                    className={styles.primaryButton}
                    type="button"
                    disabled={isAcknowledging}
                    onClick={() => void acknowledgeNotice()}
                  >
                    {isAcknowledging ? "Okuma kaydediliyor…" : "Okuduğumu kaydet"}
                  </button>
                </>
              ) : (
                <p>Bu bildirim için okuma kaydı oluşturma işlemi mevcut rolleriniz için kullanılamıyor.</p>
              )}
            </div>
          </div>
        ) : (
          <div className={styles.emptyState}>
            <span className={styles.stateIcon} aria-hidden="true">B</span>
            <div>
              <strong>Yayınlanmış bildirim bulunmuyor</strong>
              <p>Yeni bir çalışan gizlilik bildirimi yayınlandığında burada görünür.</p>
            </div>
          </div>
        )}
      </section>

      {boundary.canManageConsent ? (
        <section className={styles.sectionCard} aria-labelledby="consent-title">
          <header className={styles.sectionHeader}>
            <div>
              <span className={styles.eyebrow}>İsteğe bağlı amaçlar</span>
              <h2 id="consent-title">Onay durumunuz ve geçmişiniz</h2>
              <p>
                Bu onaylar çalışma ilişkisindeki zorunlu veri işleme süreçlerinin yerine
                geçmez ve her amaç için ayrı yönetilir.
              </p>
            </div>
          </header>
          {purposes.length === 0 ? (
            <div className={styles.emptyState}>
              <span className={styles.stateIcon} aria-hidden="true">0</span>
              <div>
                <strong>Tanımlı isteğe bağlı amaç yok</strong>
                <p>Kurumunuz bir amaç tanımladığında durumu ve geçmişi burada görünür.</p>
              </div>
            </div>
          ) : (
            <div className={styles.consentList}>
              {purposes.map((purpose) => (
                <article className={styles.consentCard} key={purpose.id}>
                  <header>
                    <div>
                      <span>{purpose.code} · sürüm {purpose.version}</span>
                      <h3>{purpose.title}</h3>
                    </div>
                    <span
                      className={purpose.granted ? styles.grantedBadge : styles.neutralBadge}
                    >
                      {purpose.granted ? "Onay verildi" : "Onay verilmedi"}
                    </span>
                  </header>
                  <p>{purpose.description}</p>
                  {!purpose.is_active ? (
                    <p className={styles.inactiveNote}>Bu amaç yeni onaylar için aktif değil.</p>
                  ) : null}
                  <div className={styles.consentActions}>
                    <span>
                      Son değişiklik: {formatDateTime(purpose.updated_at)} · durum sürümü {purpose.state_version}
                    </span>
                    {purpose.granted ? (
                      <button
                        className={styles.dangerButton}
                        type="button"
                        disabled={pendingPurposeId !== null}
                        onClick={() => setWithdrawTarget(purpose)}
                      >
                        Onayı geri çek
                      </button>
                    ) : purpose.is_active ? (
                      <button
                        className={styles.primaryButton}
                        type="button"
                        disabled={pendingPurposeId !== null}
                        onClick={() => setGrantTarget(purpose)}
                      >
                        {pendingPurposeId === purpose.id
                          ? "Onay kaydediliyor…"
                          : "Bu amaç için onay ver"}
                      </button>
                    ) : null}
                </div>
                <details className={styles.historyDisclosure}>
                  <summary>
                    Son onay hareketleri ({purpose.history.length}, en fazla 50)
                  </summary>
                    {purpose.history.length === 0 ? (
                      <p>Bu amaç için henüz onay hareketi yok.</p>
                    ) : (
                      <ol className={styles.historyList}>
                        {purpose.history.map((event) => (
                          <li key={event.id}>
                            <span aria-hidden="true" />
                            <strong>
                              {event.action === "grant" ? "Onay verildi" : "Onay geri çekildi"}
                            </strong>
                            <small>Amaç sürümü {event.purpose_version}</small>
                            <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time>
                          </li>
                        ))}
                      </ol>
                    )}
                  </details>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {grantTarget ? (
        <PrivacyConfirmationDialog
          title="İsteğe bağlı onay ver"
          description={
            <div>
              <strong>{grantTarget.title} · sürüm {grantTarget.version}</strong>
              <p>
                Bu amaç zorunlu değildir. Onayınız ayrı bir hareket olarak kaydedilecek ve
                daha sonra dilediğiniz zaman geri çekilebilecektir.
              </p>
            </div>
          }
          confirmLabel="Bu amaç için onay ver"
          busyLabel="Onay kaydediliyor…"
          isBusy={pendingPurposeId === grantTarget.id}
          onCancel={() => setGrantTarget(null)}
          onConfirm={() => void transitionConsent(grantTarget, "grant")}
        />
      ) : null}

      {withdrawTarget ? (
        <PrivacyConfirmationDialog
          title="İsteğe bağlı onayı geri çek"
          description={
            <div>
              <strong>{withdrawTarget.title}</strong>
              <p>
                Bu amaç için mevcut onayınız geri çekilecek ve hareket geçmişe yeni bir
                kayıt olarak eklenecek.
              </p>
            </div>
          }
          confirmLabel="Onayı geri çek"
          busyLabel="Geri çekiliyor…"
          isBusy={pendingPurposeId === withdrawTarget.id}
          danger
          onCancel={() => setWithdrawTarget(null)}
          onConfirm={() => void transitionConsent(withdrawTarget, "withdraw")}
        />
      ) : null}
    </section>
  );
}
