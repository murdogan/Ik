"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  listAnnouncements,
  type AnnouncementSummary,
} from "@/lib/self-service";

import { formatDateTime, requestErrorMessage } from "./presentation";
import styles from "./self-service.module.css";

function appendUnique(
  current: AnnouncementSummary[],
  incoming: AnnouncementSummary[],
): AnnouncementSummary[] {
  const values = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) values.set(item.id, item);
  return [...values.values()];
}

export function AnnouncementsScreen() {
  const { sessionGeneration, user } = useSession();
  const [items, setItems] = useState<AnnouncementSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void listAnnouncements({ scope: "own" }).then(
      (page) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.nextCursor);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setItems([]);
        setNextCursor(null);
        setError(requestErrorMessage(cause, "Duyurular yüklenemedi."));
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
      const page = await listAnnouncements({ scope: "own", cursor: nextCursor });
      setItems((current) => appendUnique(current, page.items));
      setNextCursor(page.nextCursor);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Daha fazla duyuru yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>Yayınlar</span>
          <h1>Duyurular</h1>
          <p>Yalnızca yayın anında hedef kitlesinde olduğunuz tenant duyuruları gösterilir.</p>
        </div>
        <button
          className={styles.secondaryButton}
          type="button"
          disabled={isLoading || isLoadingMore}
          onClick={() => setReloadKey((value) => value + 1)}
        >
          Yenile
        </button>
      </header>

      {error ? <div className={styles.errorBanner} role="alert">{error}</div> : null}

      <section className={styles.sectionCard} aria-labelledby="announcement-list-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Hedeflenmiş içerik</span>
            <h2 id="announcement-list-title">Yayınlanan duyurular</h2>
          </div>
          <strong>{isLoading ? "—" : items.length}</strong>
        </header>
        {isLoading ? (
          <div className={styles.loadingState} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Duyurular yükleniyor</strong>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Görüntülenecek duyuru yok</strong>
            <p>Yeni bir duyurunun hedef kitlesinde olduğunuzda burada görünür.</p>
          </div>
        ) : (
          <ul className={styles.list}>
            {items.map((item) => (
              <li className={styles.listItem} key={item.id}>
                <div>
                  <div className={styles.badges}>
                    {item.is_critical ? (
                      <span className={styles.criticalBadge}>Kritik · onay gerekli</span>
                    ) : null}
                    {item.read_at ? (
                      <span className={styles.badge}>Okundu</span>
                    ) : (
                      <span className={styles.unreadBadge}>Yeni</span>
                    )}
                    {item.acknowledged_at ? (
                      <span className={styles.badge}>Onaylandı</span>
                    ) : null}
                  </div>
                  <h3>{item.title}</h3>
                  <p>
                    {item.published_at ? formatDateTime(item.published_at) : "Yayın zamanı yok"}
                  </p>
                </div>
                <Link href={`/announcements/${item.id}`}>Duyuruyu aç</Link>
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
              {isLoadingMore ? "Duyurular yükleniyor…" : "Daha fazla göster"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
