"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

import { EpochLatchMap } from "@/lib/epoch-latch-map";

export type UnknownPlatformTenantMutationKind = "metadata" | "lifecycle";

interface PlatformOperationSafetyRegistry {
  createSlugs: Set<string>;
  initialAdminTenantIds: EpochLatchMap<string, true>;
  tenantMutations: EpochLatchMap<
    string,
    UnknownPlatformTenantMutationKind
  >;
  featureTenantIds: EpochLatchMap<string, true>;
}

interface PlatformOperationSafetyContextValue {
  revision: number;
  firstUnknownCreateSlug: () => string | null;
  hasUnknownCreateOutcome: (slug?: string) => boolean;
  markCreateOutcomeUnknown: (slug: string) => void;
  clearCreateOutcomeUnknown: (slug: string) => void;
  hasUnknownInitialAdminOutcome: (tenantId: string) => boolean;
  initialAdminOutcomeEpoch: (tenantId: string) => number | null;
  markInitialAdminOutcomeUnknown: (tenantId: string) => void;
  clearInitialAdminOutcomeUnknown: (
    tenantId: string,
    expectedEpoch?: number,
  ) => void;
  unknownTenantMutationKind: (
    tenantId: string,
  ) => UnknownPlatformTenantMutationKind | null;
  tenantMutationOutcomeEpoch: (tenantId: string) => number | null;
  markTenantMutationUnknown: (
    tenantId: string,
    kind: UnknownPlatformTenantMutationKind,
  ) => void;
  clearTenantMutationUnknown: (tenantId: string, expectedEpoch?: number) => void;
  hasUnknownFeatureOutcome: (tenantId?: string) => boolean;
  featureOutcomeEpoch: (tenantId: string) => number | null;
  markFeatureOutcomeUnknown: (tenantId: string) => void;
  clearFeatureOutcomeUnknown: (tenantId: string, expectedEpoch?: number) => void;
}

const PlatformOperationSafetyContext =
  createContext<PlatformOperationSafetyContextValue | null>(null);

export function PlatformOperationSafetyProvider({
  children,
}: {
  children: ReactNode;
}) {
  const registryRef = useRef<PlatformOperationSafetyRegistry>({
    createSlugs: new Set(),
    initialAdminTenantIds: new EpochLatchMap(),
    tenantMutations: new EpochLatchMap(),
    featureTenantIds: new EpochLatchMap(),
  });
  const [revision, setRevision] = useState(0);
  const publishChange = useCallback(() => {
    setRevision((current) => current + 1);
  }, []);

  const firstUnknownCreateSlug = useCallback(
    () => registryRef.current.createSlugs.values().next().value ?? null,
    [],
  );
  const hasUnknownCreateOutcome = useCallback(
    (slug?: string) =>
      slug
        ? registryRef.current.createSlugs.has(slug)
        : registryRef.current.createSlugs.size > 0,
    [],
  );
  const markCreateOutcomeUnknown = useCallback(
    (slug: string) => {
      const outcomes = registryRef.current.createSlugs;
      if (!outcomes.has(slug)) {
        outcomes.add(slug);
        publishChange();
      }
    },
    [publishChange],
  );
  const clearCreateOutcomeUnknown = useCallback(
    (slug: string) => {
      if (registryRef.current.createSlugs.delete(slug)) {
        publishChange();
      }
    },
    [publishChange],
  );

  const hasUnknownInitialAdminOutcome = useCallback(
    (tenantId: string) =>
      registryRef.current.initialAdminTenantIds.has(tenantId),
    [],
  );
  const initialAdminOutcomeEpoch = useCallback(
    (tenantId: string) =>
      registryRef.current.initialAdminTenantIds.epoch(tenantId),
    [],
  );
  const markInitialAdminOutcomeUnknown = useCallback(
    (tenantId: string) => {
      registryRef.current.initialAdminTenantIds.mark(tenantId, true);
      publishChange();
    },
    [publishChange],
  );
  const clearInitialAdminOutcomeUnknown = useCallback(
    (tenantId: string, expectedEpoch?: number) => {
      if (
        registryRef.current.initialAdminTenantIds.clear(
          tenantId,
          expectedEpoch,
        )
      ) {
        publishChange();
      }
    },
    [publishChange],
  );

  const unknownTenantMutationKind = useCallback(
    (tenantId: string) =>
      registryRef.current.tenantMutations.value(tenantId),
    [],
  );
  const tenantMutationOutcomeEpoch = useCallback(
    (tenantId: string) =>
      registryRef.current.tenantMutations.epoch(tenantId),
    [],
  );
  const markTenantMutationUnknown = useCallback(
    (tenantId: string, kind: UnknownPlatformTenantMutationKind) => {
      registryRef.current.tenantMutations.mark(tenantId, kind);
      publishChange();
    },
    [publishChange],
  );
  const clearTenantMutationUnknown = useCallback(
    (tenantId: string, expectedEpoch?: number) => {
      if (
        registryRef.current.tenantMutations.clear(tenantId, expectedEpoch)
      ) {
        publishChange();
      }
    },
    [publishChange],
  );

  const hasUnknownFeatureOutcome = useCallback(
    (tenantId?: string) =>
      tenantId
        ? registryRef.current.featureTenantIds.has(tenantId)
        : registryRef.current.featureTenantIds.size > 0,
    [],
  );
  const featureOutcomeEpoch = useCallback(
    (tenantId: string) =>
      registryRef.current.featureTenantIds.epoch(tenantId),
    [],
  );
  const markFeatureOutcomeUnknown = useCallback(
    (tenantId: string) => {
      registryRef.current.featureTenantIds.mark(tenantId, true);
      publishChange();
    },
    [publishChange],
  );
  const clearFeatureOutcomeUnknown = useCallback(
    (tenantId: string, expectedEpoch?: number) => {
      if (
        registryRef.current.featureTenantIds.clear(tenantId, expectedEpoch)
      ) {
        publishChange();
      }
    },
    [publishChange],
  );

  const value = useMemo<PlatformOperationSafetyContextValue>(
    () => ({
      revision,
      firstUnknownCreateSlug,
      hasUnknownCreateOutcome,
      markCreateOutcomeUnknown,
      clearCreateOutcomeUnknown,
      hasUnknownInitialAdminOutcome,
      initialAdminOutcomeEpoch,
      markInitialAdminOutcomeUnknown,
      clearInitialAdminOutcomeUnknown,
      unknownTenantMutationKind,
      tenantMutationOutcomeEpoch,
      markTenantMutationUnknown,
      clearTenantMutationUnknown,
      hasUnknownFeatureOutcome,
      featureOutcomeEpoch,
      markFeatureOutcomeUnknown,
      clearFeatureOutcomeUnknown,
    }),
    [
      clearCreateOutcomeUnknown,
      clearFeatureOutcomeUnknown,
      clearInitialAdminOutcomeUnknown,
      clearTenantMutationUnknown,
      firstUnknownCreateSlug,
      hasUnknownCreateOutcome,
      hasUnknownFeatureOutcome,
      hasUnknownInitialAdminOutcome,
      initialAdminOutcomeEpoch,
      tenantMutationOutcomeEpoch,
      featureOutcomeEpoch,
      markCreateOutcomeUnknown,
      markFeatureOutcomeUnknown,
      markInitialAdminOutcomeUnknown,
      markTenantMutationUnknown,
      revision,
      unknownTenantMutationKind,
    ],
  );

  return (
    <PlatformOperationSafetyContext.Provider value={value}>
      {children}
    </PlatformOperationSafetyContext.Provider>
  );
}

export function usePlatformOperationSafety(): PlatformOperationSafetyContextValue {
  const context = useContext(PlatformOperationSafetyContext);
  if (!context) {
    throw new Error(
      "usePlatformOperationSafety must be used within PlatformOperationSafetyProvider",
    );
  }
  return context;
}
