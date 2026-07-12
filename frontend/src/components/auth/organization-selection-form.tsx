"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useOrganizationSelection } from "@/components/auth/organization-selection-provider";
import { postApi } from "@/lib/api-client";
import {
  type AuthenticatedLoginResponseData,
  type OrganizationSelectionErrorPresentation,
  type OrganizationSelectionRequestData,
  organizationSelectionErrorPresentation,
} from "@/lib/auth-contracts";
import { homePathForUser } from "@/lib/authorization";
import { establishSession } from "@/lib/session";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

const EXPIRED_SELECTION_MESSAGE =
  "Güvenli kurum seçiminin süresi doldu. E-posta ve parolanızla yeniden giriş yapın.";

function organizationInitial(displayName: string): string {
  return displayName.trim().charAt(0).toLocaleUpperCase("tr-TR") || "K";
}

export function OrganizationSelectionForm() {
  const router = useRouter();
  const {
    selection,
    unavailableReason,
    invalidateSelection,
    clearSelection,
  } = useOrganizationSelection();
  const [submittingKey, setSubmittingKey] = useState<string | null>(null);
  const [isCompleting, setIsCompleting] = useState(false);
  const [error, setError] =
    useState<OrganizationSelectionErrorPresentation | null>(null);

  useEffect(() => {
    if (!selection && !unavailableReason && !isCompleting) {
      router.replace("/login");
    }
  }, [isCompleting, router, selection, unavailableReason]);

  async function selectOrganization(selectionKey: string) {
    if (!selection || submittingKey) {
      return;
    }

    setError(null);
    setSubmittingKey(selectionKey);
    try {
      const data = await postApi<
        OrganizationSelectionRequestData,
        AuthenticatedLoginResponseData
      >("/api/v1/auth/select-organization", {
        selection_transaction: selection.selectionTransaction,
        selection_key: selectionKey,
      });
      setIsCompleting(true);
      establishSession(data);
      clearSelection();
      router.replace(homePathForUser(data.user));
    } catch (cause) {
      const nextError = organizationSelectionErrorPresentation(cause);
      setError(nextError);
      if (nextError.terminal) {
        invalidateSelection("invalid");
      }
    } finally {
      setSubmittingKey(null);
    }
  }

  function returnToLogin() {
    clearSelection();
    router.replace("/login");
  }

  if (!selection) {
    if (!unavailableReason) {
      return (
        <div className={styles.loadingPanel} role="status" aria-live="polite">
          <span className={styles.spinnerDark} aria-hidden="true" />
          Giriş ekranı açılıyor…
        </div>
      );
    }

    return (
      <section className={styles.selectionPanel} aria-live="polite">
        <FormAlert
          tone="error"
          title="Kurum seçimi tamamlanamadı"
          message={error?.message ?? EXPIRED_SELECTION_MESSAGE}
          reference={error?.reference}
        />
        <button
          className={styles.primaryButton}
          type="button"
          onClick={returnToLogin}
        >
          Yeniden giriş yap
        </button>
      </section>
    );
  }

  return (
    <section
      className={styles.selectionPanel}
      aria-labelledby="organization_selection_title"
      aria-busy={submittingKey !== null}
    >
      <div className={styles.selectionHeading}>
        <span>Kimliğiniz doğrulandı</span>
        <h2 id="organization_selection_title">Çalışacağınız kurumu seçin</h2>
        <p>
          Yetkili olduğunuz şirketlerden biriyle devam edin. Seçiminizi daha sonra çalışma
          alanından güvenle değiştirebilirsiniz.
        </p>
      </div>

      {error ? (
        <FormAlert
          tone="error"
          title="Kurum seçimi tamamlanamadı"
          message={error.message}
          reference={error.reference}
        />
      ) : null}

      <ul className={styles.organizationList} aria-label="Erişilebilir kurumlar">
        {selection.organizations.map((organization) => {
          const isSubmitting = submittingKey === organization.selection_key;
          return (
            <li key={organization.selection_key}>
              <button
                className={styles.organizationCard}
                type="button"
                disabled={submittingKey !== null}
                onClick={() => void selectOrganization(organization.selection_key)}
              >
                <span className={styles.organizationMark} aria-hidden="true">
                  {organizationInitial(organization.display_name)}
                </span>
                <span className={styles.organizationDetails}>
                  <strong>{organization.display_name}</strong>
                  <small>{isSubmitting ? "Açılıyor…" : "Bu kurumla devam et"}</small>
                </span>
                {isSubmitting ? (
                  <span className={styles.spinnerDark} aria-hidden="true" />
                ) : (
                  <span className={styles.organizationArrow} aria-hidden="true">
                    →
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      <button
        className={styles.secondaryButton}
        type="button"
        disabled={submittingKey !== null}
        onClick={returnToLogin}
      >
        Giriş ekranına dön
      </button>
    </section>
  );
}
