"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { usePlatformSession } from "@/components/session/platform-session-provider";
import { restorePlatformSession } from "@/lib/platform-session";

import styles from "./session.module.css";

export function PlatformWorkspaceBoundary({
  children,
}: {
  children: ReactNode;
}) {
  const router = useRouter();
  const { user } = usePlatformSession();
  const isAllowed = user.workspace_scope === "platform";

  useEffect(() => {
    if (!isAllowed) {
      router.replace("/platform/login");
    }
  }, [isAllowed, router]);

  if (!isAllowed) {
    return (
      <main className={styles.loadingPage}>
        <div className={styles.loadingCard} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Platform oturumu gerekli</strong>
            <p>Bu çalışma alanı tenant oturumlarından ayrı tutulur.</p>
          </div>
        </div>
      </main>
    );
  }

  return children;
}

export function PlatformPermissionBoundary({
  children,
  permission,
}: {
  children: ReactNode;
  permission: string;
}) {
  const router = useRouter();
  const { user } = usePlatformSession();
  const isAllowed = user.permissions.includes(permission);

  useEffect(() => {
    if (isAllowed) {
      return;
    }

    let isActive = true;
    void restorePlatformSession().then(
      (restoredUser) => {
        if (isActive && !restoredUser.permissions.includes(permission)) {
          router.replace("/platform");
        }
      },
      () => {
        if (isActive) {
          router.replace("/platform/login");
        }
      },
    );
    return () => {
      isActive = false;
    };
  }, [isAllowed, permission, router]);

  if (!isAllowed) {
    return (
      <section
        className={styles.authorizationNotice}
        role="status"
        aria-live="polite"
      >
        <span className={styles.spinner} aria-hidden="true" />
        <div>
          <strong>Platform ana sayfası açılıyor</strong>
          <p>Bu işlem mevcut platform rolünüz için kullanılabilir değil.</p>
        </div>
      </section>
    );
  }

  return children;
}
