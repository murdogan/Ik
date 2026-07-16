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

import { useSession } from "@/components/session/session-provider";
import { homePathForUser } from "@/lib/authorization";
import {
  TENANT_FEATURES,
  type TenantFeatureKey,
} from "@/lib/feature-rollout";
import { readTenantFeatures } from "@/lib/tenant-features";

import styles from "./session.module.css";

type TenantFeatureLoadStatus = "loading" | "ready" | "error";

interface TenantFeatureContextValue {
  status: TenantFeatureLoadStatus;
  isEnabled: (feature: TenantFeatureKey) => boolean;
}

interface TenantFeatureState {
  tenantId: string;
  permissionVersion: number;
  status: TenantFeatureLoadStatus;
  enabledFeatures: ReadonlySet<TenantFeatureKey>;
}

const TenantFeatureContext = createContext<TenantFeatureContextValue | null>(null);

export function TenantFeatureProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const [state, setState] = useState<TenantFeatureState>(() => ({
    tenantId: user.tenant_id,
    permissionVersion: user.permission_version,
    status: "loading",
    enabledFeatures: new Set<TenantFeatureKey>(),
  }));
  useEffect(() => {
    let isActive = true;
    const tenantId = user.tenant_id;
    const permissionVersion = user.permission_version;
    void readTenantFeatures().then(
      (features) => {
        if (!isActive) {
          return;
        }
        setState({
          tenantId,
          permissionVersion,
          status: "ready",
          enabledFeatures: new Set(
            features
              .filter((feature) => feature.enabled)
              .map((feature) => feature.key)
              .filter(
                (key): key is TenantFeatureKey =>
                  Object.values(TENANT_FEATURES).includes(
                    key as TenantFeatureKey,
                  ),
              ),
          ),
        });
      },
      () => {
        if (!isActive) {
          return;
        }
        setState({
          tenantId,
          permissionVersion,
          status: "error",
          enabledFeatures: new Set<TenantFeatureKey>(),
        });
      },
    );

    return () => {
      isActive = false;
    };
  }, [user.permission_version, user.tenant_id]);

  const stateMatchesTenant =
    state.tenantId === user.tenant_id &&
    state.permissionVersion === user.permission_version;
  const status = stateMatchesTenant ? state.status : "loading";
  const isEnabled = useCallback(
    (feature: TenantFeatureKey) =>
      stateMatchesTenant &&
      state.status === "ready" &&
      state.enabledFeatures.has(feature),
    [state, stateMatchesTenant],
  );
  const contextValue = useMemo<TenantFeatureContextValue>(
    () => ({ status, isEnabled }),
    [isEnabled, status],
  );

  return (
    <TenantFeatureContext.Provider value={contextValue}>
      {children}
    </TenantFeatureContext.Provider>
  );
}

export function TenantFeatureBoundary({
  children,
  feature,
}: {
  children: ReactNode;
  feature: TenantFeatureKey;
}) {
  const router = useRouter();
  const { user } = useSession();
  const { status, isEnabled } = useTenantFeatures();
  const isAllowed = status === "ready" && isEnabled(feature);

  useEffect(() => {
    if (status !== "loading" && !isAllowed) {
      router.replace(
        feature === TENANT_FEATURES.selfService ? "/dashboard" : homePathForUser(user),
      );
    }
  }, [feature, isAllowed, router, status, user]);

  if (!isAllowed) {
    return (
      <section className={styles.authorizationNotice} role="status" aria-live="polite">
        <span className={styles.spinner} aria-hidden="true" />
        <div>
          <strong>Yetkili ana sayfanız açılıyor</strong>
          <p>Bu özellik çalışma alanınızda kullanıma açık değil.</p>
        </div>
      </section>
    );
  }

  return children;
}

export function useTenantFeatures(): TenantFeatureContextValue {
  const context = useContext(TenantFeatureContext);
  if (!context) {
    throw new Error("useTenantFeatures must be used within TenantFeatureProvider");
  }
  return context;
}
