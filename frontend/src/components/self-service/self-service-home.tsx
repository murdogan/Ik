"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import { AUTHORIZATION_PERMISSIONS, hasPermission } from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";
import {
  decimalNumber,
  readSelfServiceHome,
  type SelfServiceHome,
} from "@/lib/self-service";

import { formatDateTime, requestErrorMessage, statusLabel } from "./presentation";
import styles from "./self-service.module.css";

export function SelfServiceHomeScreen() {
  const { sessionGeneration, user } = useSession();
  const { isEnabled } = useTenantFeatures();
  const notificationsEnabled =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnNotifications) &&
    isEnabled(TENANT_FEATURES.notifications);
  const [home, setHome] = useState<SelfServiceHome | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void readSelfServiceHome().then(
      (result) => {
        if (!active) return;
        setHome(result);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setHome(null);
        setError(requestErrorMessage(cause, "Çalışan ana sayfası yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey, sessionGeneration, user.membership_id, user.tenant_id]);

  if (isLoading) {
    return (
      <section className={styles.loadingState} role="status" aria-live="polite">
        <span className={styles.spinner} aria-hidden="true" />
        <strong>Çalışma alanınız hazırlanıyor</strong>
        <p>İzin, belge, duyuru ve bildirim özetleriniz güvenli kapsamda yükleniyor.</p>
      </section>
    );
  }

  if (error || !home) {
    return (
      <section className={styles.errorState} role="alert">
        <strong>Çalışan ana sayfası açılamadı</strong>
        <p>{error ?? "Beklenmeyen bir yanıt alındı."}</p>
        <button
          className={styles.secondaryButton}
          type="button"
          onClick={() => setReloadKey((value) => value + 1)}
        >
          Yeniden dene
        </button>
      </section>
    );
  }

  const documentActionCount =
    home.document_summary.missing +
    home.document_summary.expiring +
    home.document_summary.expired;

  return (
    <div className={styles.page}>
      <section className={styles.hero} aria-labelledby="self-service-title">
        <div>
          <span className={styles.eyebrow}>Çalışan alanı</span>
          <h1 id="self-service-title">Merhaba, {home.work.display_name}</h1>
          <p>
            Güncel iş bilgilerinizi görün; izin, belge ve HR taleplerinizde sıradaki işi
            doğrudan tamamlayın.
          </p>
        </div>
        <dl className={styles.workDetails}>
          <div>
            <dt>Pozisyon</dt>
            <dd>{home.work.position_title ?? "Atama bilgisi yok"}</dd>
          </div>
          <div>
            <dt>Departman · Şube</dt>
            <dd>
              {[home.work.department_name, home.work.branch_name]
                .filter(Boolean)
                .join(" · ") || "Atama bilgisi yok"}
            </dd>
          </div>
          <div>
            <dt>Çalışan numarası</dt>
            <dd>{home.work.employee_number}</dd>
          </div>
        </dl>
      </section>

      <section className={styles.quickGrid} aria-label="Hızlı işlemler">
        <Link className={styles.taskCard} href={home.leave_request_path}>
          <span className={styles.eyebrow}>İzin</span>
          <strong>İzin talebi oluştur</strong>
          <p>Bakiyenizi kontrol edin ve tarih aralığını seçerek talebinizi gönderin.</p>
          <span className={styles.taskMeta}>
            {home.leave_balances.length > 0
              ? `${home.leave_balances.length} izin bakiyesi hazır`
              : "İzin alanını aç"}
          </span>
        </Link>
        <Link className={styles.taskCard} href={home.requests_path}>
          <span className={styles.eyebrow}>Talepler</span>
          <strong>HR belgesi iste</strong>
          <p>Çalışma belgesi ve sabit HR belge taleplerinizi tek yerden takip edin.</p>
          <span className={styles.taskMeta}>
            {home.recent_requests.length} yakın tarihli talep
          </span>
        </Link>
      </section>

      <section className={styles.sectionCard} aria-labelledby="balances-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Kullanılabilir izin</span>
            <h2 id="balances-title">Bu yılın bakiyeleri</h2>
            <p>Planlanan ve kullanılan izinler düşüldükten sonraki kullanılabilir günler.</p>
          </div>
          <Link href="/leave">İzin ayrıntıları</Link>
        </header>
        {home.leave_balances.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Henüz izin bakiyesi yok</strong>
            <p>İzin politikası ve bakiye oluştuğunda özet burada görünür.</p>
          </div>
        ) : (
          <div className={styles.summaryGrid}>
            {home.leave_balances.map((balance) => (
              <article className={styles.summaryCard} key={balance.leave_type_id}>
                <strong>{decimalNumber(balance.available_days).toLocaleString("tr-TR")}</strong>
                <span>{balance.leave_type_name} · gün</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className={styles.twoColumn}>
        <section className={styles.sectionCard} aria-labelledby="recent-requests-title">
          <header className={styles.sectionHeader}>
            <div>
              <span className={styles.eyebrow}>Takip</span>
              <h2 id="recent-requests-title">Yakın talepler</h2>
            </div>
            <Link href="/requests">Tümünü gör</Link>
          </header>
          {home.recent_requests.length === 0 ? (
            <div className={styles.emptyState}>
              <strong>Henüz talebiniz yok</strong>
              <p>İzin ve HR belge talepleriniz gönderildikten sonra burada görünür.</p>
            </div>
          ) : (
            <ul className={styles.list}>
              {home.recent_requests.map((request) => (
                <li className={styles.listItem} key={`${request.kind}:${request.id}`}>
                  <div>
                    <strong>{request.title}</strong>
                    <p>{formatDateTime(request.submitted_at)}</p>
                  </div>
                  <div>
                    <span className={styles.badge}>{statusLabel(request.status)}</span>
                    <Link href={`/requests/${request.id}`}>Aç</Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={styles.sectionCard} aria-labelledby="documents-title">
          <header className={styles.sectionHeader}>
            <div>
              <span className={styles.eyebrow}>Belge kontrolü</span>
              <h2 id="documents-title">Çalışan belgelerim</h2>
            </div>
            <Link href="/profile">Belgeleri aç</Link>
          </header>
          <div className={styles.summaryGrid}>
            <article className={styles.summaryCard}>
              <strong>{home.document_summary.available}</strong>
              <span>Hazır</span>
            </article>
            <article className={styles.summaryCard}>
              <strong>{home.document_summary.missing}</strong>
              <span>Eksik</span>
            </article>
            <article className={styles.summaryCard}>
              <strong>{home.document_summary.expiring}</strong>
              <span>Yakında dolacak</span>
            </article>
            <article className={styles.summaryCard}>
              <strong>{home.document_summary.expired}</strong>
              <span>Süresi dolmuş</span>
            </article>
          </div>
          <div className={documentActionCount > 0 ? styles.conflictBanner : styles.successBanner}>
            {documentActionCount > 0
              ? `${documentActionCount} belge maddesi dikkatinizi bekliyor.`
              : "Belge kontrol listenizde açık işlem görünmüyor."}
          </div>
        </section>
      </div>

      <div className={styles.twoColumn}>
        <section className={styles.sectionCard} aria-labelledby="announcements-title">
          <header className={styles.sectionHeader}>
            <div>
              <span className={styles.eyebrow}>Duyurular</span>
              <h2 id="announcements-title">Sizin için yayınlananlar</h2>
            </div>
            <Link href="/announcements">Tümünü gör</Link>
          </header>
          {home.announcements.length === 0 ? (
            <div className={styles.emptyState}>
              <strong>Yeni duyuru yok</strong>
              <p>Hedef kitlesinde olduğunuz yayınlar burada görünür.</p>
            </div>
          ) : (
            <ul className={styles.list}>
              {home.announcements.map((announcement) => (
                <li className={styles.listItem} key={announcement.id}>
                  <div>
                    <strong>{announcement.title}</strong>
                    <div className={styles.badges}>
                      {announcement.is_critical ? (
                        <span className={styles.criticalBadge}>Kritik</span>
                      ) : null}
                      {announcement.read_at ? null : (
                        <span className={styles.unreadBadge}>Okunmadı</span>
                      )}
                    </div>
                  </div>
                  <Link href={`/announcements/${announcement.id}`}>Oku</Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {notificationsEnabled ? (
          <section className={styles.sectionCard} aria-labelledby="notifications-title">
            <header className={styles.sectionHeader}>
              <div>
                <span className={styles.eyebrow}>Bildirimler</span>
                <h2 id="notifications-title">Güncel hareketler</h2>
              </div>
              <Link href="/notifications">{home.unread_notification_count} okunmamış</Link>
            </header>
            {home.notifications.length === 0 ? (
              <div className={styles.emptyState}>
                <strong>Bildirim yok</strong>
                <p>Talep durumu ve işlem bildirimleri burada görünür.</p>
              </div>
            ) : (
              <ul className={styles.list}>
                {home.notifications.map((notification) => (
                  <li className={styles.listItem} key={notification.id}>
                    <div>
                      <strong>{notification.title}</strong>
                      <p>{notification.body}</p>
                    </div>
                    <Link href={notification.portal_path}>Aç</Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : null}
      </div>
    </div>
  );
}
