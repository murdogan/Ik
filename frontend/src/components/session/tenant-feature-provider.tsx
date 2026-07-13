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
import { ApiClientError } from "@/lib/api-client";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
  homePathForUser,
} from "@/lib/authorization";
import {
  listLegalEntities,
} from "@/lib/organization";
import {
  TENANT_FEATURES,
  type TenantFeatureKey,
} from "@/lib/feature-rollout";

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
  const canReadOrganization = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readOrganization,
  );

  useEffect(() => {
    let isActive = true;
    const tenantId = user.tenant_id;
    const permissionVersion = user.permission_version;
    if (!canReadOrganization) {
      return () => {
        isActive = false;
      };
    }

    void listLegalEntities({ limit: 1 }).then(
      () => {
        if (!isActive) {
          return;
        }
        setState({
          tenantId,
          permissionVersion,
          status: "ready",
          enabledFeatures: new Set([TENANT_FEATURES.organization]),
        });
      },
      (cause) => {
        if (!isActive) {
          return;
        }
        const isDisabled =
          cause instanceof ApiClientError &&
          cause.code === "organization_feature_unavailable";
        setState({
          tenantId,
          permissionVersion,
          status: isDisabled ? "ready" : "error",
          enabledFeatures: new Set<TenantFeatureKey>(),
        });
      },
    );

    return () => {
      isActive = false;
    };
  }, [canReadOrganization, user.permission_version, user.tenant_id]);

  const stateMatchesTenant =
    state.tenantId === user.tenant_id &&
    state.permissionVersion === user.permission_version;
  const status = !canReadOrganization
    ? "ready"
    : stateMatchesTenant
      ? state.status
      : "loading";
  const isEnabled = useCallback(
    (feature: TenantFeatureKey) =>
      canReadOrganization &&
      stateMatchesTenant &&
      state.status === "ready" &&
      state.enabledFeatures.has(feature),
    [canReadOrganization, state, stateMatchesTenant],
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
      router.replace(homePathForUser(user));
    }
  }, [isAllowed, router, status, user]);

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
