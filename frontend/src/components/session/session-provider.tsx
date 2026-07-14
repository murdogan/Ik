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
import { useOrganizationSelection } from "@/components/auth/organization-selection-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  logoutSession,
  getSessionGeneration,
  requestOrganizationSelection,
  restoreSession,
  subscribeToSessionChanges,
} from "@/lib/session";

import styles from "./session.module.css";

interface SessionContextValue {
  user: AuthUser;
  sessionGeneration: number;
  isLoggingOut: boolean;
  isSwitchingOrganization: boolean;
  logoutError: string | null;
  organizationSwitchError: string | null;
  signOut: () => Promise<void>;
  switchOrganization: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { beginSelection } = useOrganizationSelection();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [sessionGeneration, setSessionGeneration] = useState(getSessionGeneration);
  const [isChecking, setIsChecking] = useState(true);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isSwitchingOrganization, setIsSwitchingOrganization] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [organizationSwitchError, setOrganizationSwitchError] = useState<
    string | null
  >(null);

  useEffect(
    () =>
      subscribeToSessionChanges((change) => {
        setSessionGeneration(getSessionGeneration());
        if (change.type === "user_updated") {
          setUser(change.user);
          return;
        }
        setUser(null);
        setIsChecking(false);
        router.replace("/login");
      }),
    [router],
  );

  useEffect(() => {
    let isActive = true;

    void restoreSession().then(
      (restoredUser) => {
        if (!isActive) {
          return;
        }
        setSessionGeneration(getSessionGeneration());
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

  useEffect(() => {
    let isActive = true;
    const revalidateAuthorization = () => {
      if (document.visibilityState === "hidden") {
        return;
      }
      void restoreSession().then(
        (restoredUser) => {
          if (isActive) {
            setSessionGeneration(getSessionGeneration());
            setUser(restoredUser);
          }
        },
        () => {
          // Terminal invalidation is published by the session module. Transient focus checks
          // keep the current shell and recover on the next successful request.
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
    if (isLoggingOut || isSwitchingOrganization) {
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
        setSessionGeneration(getSessionGeneration());
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
  }, [isLoggingOut, isSwitchingOrganization, router]);

  const switchOrganization = useCallback(async () => {
    if (isLoggingOut || isSwitchingOrganization) {
      return;
    }

    setLogoutError(null);
    setOrganizationSwitchError(null);
    setIsSwitchingOrganization(true);
    try {
      const data = await requestOrganizationSelection();
      setSessionGeneration(getSessionGeneration());
      beginSelection(data, "switch");
      router.replace("/select-organization");
    } catch (cause) {
      setOrganizationSwitchError(
        cause instanceof ApiClientError &&
          cause.code === "organization_switch_unavailable"
          ? "Hesabınızda geçiş yapabileceğiniz başka bir aktif kurum bulunmuyor."
          : "Kurum değiştirme başlatılamadı. Bağlantınızı kontrol edip yeniden deneyin.",
      );
    } finally {
      setIsSwitchingOrganization(false);
    }
  }, [
    beginSelection,
    isLoggingOut,
    isSwitchingOrganization,
    router,
  ]);

  const contextValue = useMemo<SessionContextValue | null>(
    () =>
      user
        ? {
            user,
            sessionGeneration,
            isLoggingOut,
            isSwitchingOrganization,
            logoutError,
            organizationSwitchError,
            signOut,
            switchOrganization,
          }
        : null,
    [
      isLoggingOut,
      isSwitchingOrganization,
      logoutError,
      organizationSwitchError,
      sessionGeneration,
      signOut,
      switchOrganization,
      user,
    ],
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
