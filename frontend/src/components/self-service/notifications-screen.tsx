"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from "@/lib/self-service";

import { formatDateTime, requestErrorMessage } from "./presentation";
import styles from "./self-service.module.css";

function appendUnique(
  current: NotificationItem[],
  incoming: NotificationItem[],
): NotificationItem[] {
  const values = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) values.set(item.id, item);
  return [...values.values()];
}

export function NotificationsScreen() {
  const router = useRouter();
  const { sessionGeneration, user } = useSession();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [isReadingAll, setIsReadingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void listNotifications().then(
      (page) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
        setUnreadCount(page.unread_count);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setItems([]);
        setNextCursor(null);
        setUnreadCount(0);
        setError(requestErrorMessage(cause, "Bildirimler yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey, sessionGeneration, user.tenant_id]);

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setError(null);
    try {
      const page = await listNotifications({ cursor: nextCursor });
      setItems((current) => appendUnique(current, page.items));
      setNextCursor(page.next_cursor);
      setUnreadCount(page.unread_count);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Daha fazla bildirim yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function openNotification(item: NotificationItem) {
    if (pendingId) return;
    setPendingId(item.id);
    setError(null);
    try {
      if (item.read_at === null) {
        const updated = await markNotificationRead(item.id, item.version);
        setItems((current) => current.map((value) => (value.id === item.id ? updated : value)));
        setUnreadCount((value) => Math.max(0, value - 1));
      }
      router.push(item.portal_path);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Bildirim açılamadı."));
    } finally {
      setPendingId(null);
    }
  }

  async function readAll() {
    if (isReadingAll || unreadCount === 0) return;
    setIsReadingAll(true);
    setError(null);
    setNotice(null);
    try {
      const result = await markAllNotificationsRead();
      setNotice(
        result.has_more
          ? `${result.updated_count} bildirim okundu. Kalanlar için işlemi yeniden çalıştırın.`
          : `${result.updated_count} bildirim okundu olarak işaretlendi.`,
      );
      setReloadKey((value) => value + 1);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Bildirimler güncellenemedi."));
    } finally {
      setIsReadingAll(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>Kişisel gelen kutusu</span>
          <h1>Bildirimler</h1>
          <p>Talep ve duyuru hareketleri yalnız mevcut kullanıcı hesabınız için gösterilir.</p>
        </div>
        <button
          className={styles.primaryButton}
          type="button"
          disabled={isReadingAll || unreadCount === 0}
          onClick={() => void readAll()}
        >
          {isReadingAll ? "Güncelleniyor…" : "Tümünü okundu işaretle"}
        </button>
      </header>

      {error ? <div className={styles.errorBanner} role="alert">{error}</div> : null}
      {notice ? <div className={styles.successBanner} role="status">{notice}</div> : null}

      <section className={styles.sectionCard} aria-labelledby="notification-list-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Güncel hareketler</span>
            <h2 id="notification-list-title">Bildirim merkezi</h2>
          </div>
          <strong>{unreadCount} okunmamış</strong>
        </header>
        {isLoading ? (
          <div className={styles.loadingState} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Bildirimler yükleniyor</strong>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Bildirim yok</strong>
            <p>Yeni talep veya duyuru hareketleri olduğunda burada görünür.</p>
          </div>
        ) : (
          <ul className={styles.list}>
            {items.map((item) => (
              <li className={styles.listItem} key={item.id}>
                <div>
                  <div className={styles.badges}>
                    {item.read_at === null ? (
                      <span className={styles.unreadBadge}>Okunmadı</span>
                    ) : (
                      <span className={styles.badge}>Okundu</span>
                    )}
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                  <p>{formatDateTime(item.created_at)}</p>
                </div>
                <button
                  className={styles.textButton}
                  type="button"
                  disabled={pendingId !== null}
                  onClick={() => void openNotification(item)}
                >
                  {pendingId === item.id ? "Açılıyor…" : "Aç"}
                </button>
              </li>
            ))}
          </ul>
        )}
        {nextCursor ? (
          <div className={styles.loadMore}>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isLoadingMore}
              onClick={() => void loadMore()}
            >
              {isLoadingMore ? "Bildirimler yükleniyor…" : "Daha fazla göster"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
