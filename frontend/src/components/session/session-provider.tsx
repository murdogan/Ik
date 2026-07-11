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

import type { AuthUser } from "@/lib/auth-contracts";
import { logoutSession, restoreSession } from "@/lib/session";

import styles from "./session.module.css";

interface SessionContextValue {
  user: AuthUser;
  isLoggingOut: boolean;
  logoutError: string | null;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    void restoreSession().then(
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
        router.replace("/login");
      },
    );

    return () => {
      isActive = false;
    };
  }, [router]);

  const signOut = useCallback(async () => {
    if (isLoggingOut) {
      return;
    }

    setLogoutError(null);
    setIsLoggingOut(true);
    try {
      await logoutSession();
      setUser(null);
      router.replace("/login");
    } catch {
      try {
        const restoredUser = await restoreSession();
        setUser(restoredUser);
        setLogoutError(
          "Oturum kapatılamadı. Bağlantınızı kontrol edip yeniden deneyin.",
        );
      } catch {
        setUser(null);
        router.replace("/login");
      }
    } finally {
      setIsLoggingOut(false);
    }
  }, [isLoggingOut, router]);

  const contextValue = useMemo<SessionContextValue | null>(
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
            <strong>{isChecking ? "Oturum doğrulanıyor" : "Girişe yönlendiriliyor"}</strong>
            <p>
              {isChecking
                ? "Güvenli çalışma alanınız hazırlanıyor…"
                : "Bu sayfayı açmak için giriş yapmanız gerekiyor."}
            </p>
          </div>
        </div>
      </main>
    );
  }

  return <SessionContext.Provider value={contextValue}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return context;
}
