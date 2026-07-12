"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { PlatformAuthUser } from "@/lib/auth-contracts";
import {
  logoutPlatformSession,
  restorePlatformSession,
  subscribeToPlatformSessionChanges,
} from "@/lib/platform-session";

import styles from "./session.module.css";

interface PlatformSessionContextValue {
  user: PlatformAuthUser;
  isLoggingOut: boolean;
  logoutError: string | null;
  signOut: () => Promise<void>;
}

const PlatformSessionContext =
  createContext<PlatformSessionContextValue | null>(null);

export function PlatformSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<PlatformAuthUser | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  useEffect(
    () =>
      subscribeToPlatformSessionChanges((change) => {
        if (change.type === "user_updated") {
          setUser(change.user);
          return;
        }
        setUser(null);
        setIsChecking(false);
        router.replace("/platform/login");
      }),
    [router],
  );

  useEffect(() => {
    let isActive = true;

    void restorePlatformSession().then(
      (restoredUser) => {
        if (!isActive) {
          return;
        }
        setUser(restoredUser);
        setIsChecking(false);
      },
      () => {
        if (!isActive) {
          return;
        }
        setUser(null);
        setIsChecking(false);
        router.replace("/platform/login");
      },
    );

    return () => {
      isActive = false;
    };
  }, [router]);

  useEffect(() => {
    let isActive = true;
    const revalidateAuthorization = () => {
      if (document.visibilityState === "hidden") {
        return;
      }
      void restorePlatformSession().then(
        (restoredUser) => {
          if (isActive) {
            setUser(restoredUser);
          }
        },
        () => {
          // Terminal invalidation is published by the platform session module.
        },
      );
    };

    window.addEventListener("focus", revalidateAuthorization);
    document.addEventListener("visibilitychange", revalidateAuthorization);
    return () => {
      isActive = false;
      window.removeEventListener("focus", revalidateAuthorization);
      document.removeEventListener("visibilitychange", revalidateAuthorization);
    };
  }, []);

  const signOut = useCallback(async () => {
    if (isLoggingOut) {
      return;
    }

    setLogoutError(null);
    setIsLoggingOut(true);
    try {
      await logoutPlatformSession();
      setUser(null);
      router.replace("/platform/login");
    } catch {
      try {
        const restoredUser = await restorePlatformSession();
        setUser(restoredUser);
        setLogoutError(
          "Platform oturumu kapatılamadı. Bağlantınızı kontrol edip yeniden deneyin.",
        );
      } catch {
        setUser(null);
        router.replace("/platform/login");
      }
    } finally {
      setIsLoggingOut(false);
    }
  }, [isLoggingOut, router]);

  const contextValue = useMemo<PlatformSessionContextValue | null>(
    () =>
      user
        ? {
            user,
            isLoggingOut,
            logoutError,
            signOut,
          }
        : null,
    [isLoggingOut, logoutError, signOut, user],
  );

  if (isChecking || !contextValue) {
    return (
      <main className={styles.loadingPage}>
        <div className={styles.loadingCard} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <div>
            <strong>
              {isChecking
                ? "Platform oturumu doğrulanıyor"
                : "Platform girişine yönlendiriliyor"}
            </strong>
            <p>
              {isChecking
                ? "Ayrı yönetim çalışma alanınız hazırlanıyor…"
                : "Bu alan için yetkili bir platform oturumu gerekiyor."}
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <PlatformSessionContext.Provider value={contextValue}>
      {children}
    </PlatformSessionContext.Provider>
  );
}

export function usePlatformSession(): PlatformSessionContextValue {
  const context = useContext(PlatformSessionContext);
  if (!context) {
    throw new Error(
      "usePlatformSession must be used within PlatformSessionProvider",
    );
  }
  return context;
}
