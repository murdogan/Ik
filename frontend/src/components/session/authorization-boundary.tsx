"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { useSession } from "@/components/session/session-provider";
import type { WorkspaceScope } from "@/lib/auth-contracts";
import {
  hasPermission,
  homePathForUser,
  isWorkspace,
} from "@/lib/authorization";
import { restoreSession } from "@/lib/session";

import styles from "./session.module.css";

export function WorkspaceBoundary({
  children,
  scope,
}: {
  children: ReactNode;
  scope: WorkspaceScope;
}) {
  const router = useRouter();
  const { user } = useSession();
  const isAllowed = isWorkspace(user, scope);

  useEffect(() => {
    if (!isAllowed) {
      router.replace(homePathForUser(user));
    }
  }, [isAllowed, router, user]);

  if (!isAllowed) {
    return (
      <main className={styles.loadingPage}>
        <div className={styles.loadingCard} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>Doğru çalışma alanı açılıyor</strong>
            <p>Oturumunuza uygun uygulama kabuğuna yönlendiriliyorsunuz.</p>
          </div>
        </div>
      </main>
    );
  }

  return children;
}

export function PermissionBoundary({
  children,
  permission,
}: {
  children: ReactNode;
  permission: string;
}) {
  const router = useRouter();
  const { user } = useSession();
  const isAllowed = hasPermission(user, permission);

  useEffect(() => {
    if (isAllowed) {
      return;
    }

    let isActive = true;
    void restoreSession().then(
      (restoredUser) => {
        if (!isActive) {
          return;
        }
        if (!hasPermission(restoredUser, permission)) {
          router.replace(homePathForUser(restoredUser));
        }
      },
      () => {
        if (isActive) {
          router.replace(homePathForUser(user));
        }
      },
    );
    return () => {
      isActive = false;
    };
  }, [isAllowed, permission, router, user]);

  if (!isAllowed) {
    return (
      <section className={styles.authorizationNotice} role="status" aria-live="polite">
        <span className={styles.spinner} aria-hidden="true" />
        <div>
          <strong>Yetkili ana sayfanız açılıyor</strong>
          <p>Bu alan mevcut rolleriniz için kullanılabilir değil.</p>
        </div>
      </section>
    );
  }

  return children;
}

export function AnyPermissionBoundary({
  children,
  permissions,
}: {
  children: ReactNode;
  permissions: readonly string[];
}) {
  const router = useRouter();
  const { user } = useSession();
  const isAllowed = permissions.some((permission) => hasPermission(user, permission));

  useEffect(() => {
    if (isAllowed) return;
    let isActive = true;
    void restoreSession().then(
      (restoredUser) => {
        if (
          isActive &&
          !permissions.some((permission) => hasPermission(restoredUser, permission))
        ) {
          router.replace(homePathForUser(restoredUser));
        }
      },
      () => {
        if (isActive) router.replace(homePathForUser(user));
      },
    );
    return () => {
      isActive = false;
    };
  }, [isAllowed, permissions, router, user]);

  if (!isAllowed) {
    return (
      <section className={styles.authorizationNotice} role="status" aria-live="polite">
        <span className={styles.spinner} aria-hidden="true" />
        <div>
          <strong>Yetkili ana sayfanız açılıyor</strong>
          <p>Bu alan mevcut rolleriniz için kullanılabilir değil.</p>
        </div>
      </section>
    );
  }

  return children;
}
