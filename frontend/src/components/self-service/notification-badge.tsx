"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { listNotifications } from "@/lib/self-service";

import styles from "./self-service.module.css";

export function NotificationBadge() {
  const { sessionGeneration, user } = useSession();
  const [unreadCount, setUnreadCount] = useState(0);
  const requestGeneration = useRef(0);

  const refresh = useCallback(() => {
    const generation = ++requestGeneration.current;
    void listNotifications({ limit: 1 }).then(
      (page) => {
        if (generation === requestGeneration.current) setUnreadCount(page.unread_count);
      },
      () => {
        if (generation === requestGeneration.current) setUnreadCount(0);
      },
    );
  }, []);

  useEffect(() => {
    refresh();
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    window.addEventListener("wf:notifications-changed", onFocus);
    return () => {
      requestGeneration.current += 1;
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("wf:notifications-changed", onFocus);
    };
  }, [refresh, sessionGeneration, user.id, user.tenant_id]);

  return (
    <Link
      className={styles.notificationButton}
      href="/notifications"
      aria-label={
        unreadCount > 0 ? `${unreadCount} okunmamış bildirim` : "Bildirim merkezi"
      }
    >
      <span aria-hidden="true">Bildirimler</span>
      {unreadCount > 0 ? (
        <span className={styles.notificationCount} aria-hidden="true">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      ) : null}
    </Link>
  );
}
