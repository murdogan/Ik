"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type {
  OrganizationSelectionOption,
  OrganizationSelectionRequiredData,
} from "@/lib/auth-contracts";

export type OrganizationSelectionOrigin = "login" | "switch";
export type OrganizationSelectionUnavailableReason = "expired" | "invalid";

export interface ActiveOrganizationSelection {
  selectionTransaction: string;
  organizations: OrganizationSelectionOption[];
  expiresAt: number;
  origin: OrganizationSelectionOrigin;
}

interface OrganizationSelectionContextValue {
  selection: ActiveOrganizationSelection | null;
  unavailableReason: OrganizationSelectionUnavailableReason | null;
  beginSelection: (
    data: OrganizationSelectionRequiredData,
    origin: OrganizationSelectionOrigin,
  ) => void;
  invalidateSelection: (reason: OrganizationSelectionUnavailableReason) => void;
  clearSelection: () => void;
}

const OrganizationSelectionContext =
  createContext<OrganizationSelectionContextValue | null>(null);

export function OrganizationSelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<ActiveOrganizationSelection | null>(
    null,
  );
  const [unavailableReason, setUnavailableReason] =
    useState<OrganizationSelectionUnavailableReason | null>(null);

  const beginSelection = useCallback(
    (
      data: OrganizationSelectionRequiredData,
      origin: OrganizationSelectionOrigin,
    ) => {
      setUnavailableReason(null);
      setSelection({
        selectionTransaction: data.selection_transaction,
        organizations: data.organizations,
        expiresAt: Date.now() + Math.max(1, data.expires_in) * 1_000,
        origin,
      });
    },
    [],
  );

  const invalidateSelection = useCallback(
    (reason: OrganizationSelectionUnavailableReason) => {
      setSelection(null);
      setUnavailableReason(reason);
    },
    [],
  );

  const clearSelection = useCallback(() => {
    setSelection(null);
    setUnavailableReason(null);
  }, []);

  useEffect(() => {
    if (!selection) {
      return;
    }

    const timeout = window.setTimeout(
      () => invalidateSelection("expired"),
      Math.max(0, selection.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timeout);
  }, [invalidateSelection, selection]);

  const value = useMemo<OrganizationSelectionContextValue>(
    () => ({
      selection,
      unavailableReason,
      beginSelection,
      invalidateSelection,
      clearSelection,
    }),
    [
      beginSelection,
      clearSelection,
      invalidateSelection,
      selection,
      unavailableReason,
    ],
  );

  return (
    <OrganizationSelectionContext.Provider value={value}>
      {children}
    </OrganizationSelectionContext.Provider>
  );
}

export function useOrganizationSelection(): OrganizationSelectionContextValue {
  const context = useContext(OrganizationSelectionContext);
  if (!context) {
    throw new Error(
      "useOrganizationSelection must be used within OrganizationSelectionProvider",
    );
  }
  return context;
}
