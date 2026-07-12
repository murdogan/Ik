"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import {
  type LoginResponseData,
  type OrganizationSelectionOption,
  loginErrorPresentation,
} from "@/lib/auth-contracts";
import { postApi } from "@/lib/api-client";
import { homePathForUser } from "@/lib/authorization";
import { establishSession } from "@/lib/session";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

interface OrganizationSelectionState {
  selectionTransaction: string;
  expiresIn: number;
  organizations: OrganizationSelectionOption[];
}

const EXPIRED_SELECTION_MESSAGE =
  "Güvenli kurum seçimi süresi doldu. E-posta ve parolanızla yeniden giriş yapın.";

export function LoginForm() {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ReturnType<typeof loginErrorPresentation> | null>(
    null,
  );
  const [organizationSelection, setOrganizationSelection] =
    useState<OrganizationSelectionState | null>(null);

  useEffect(() => {
    if (!organizationSelection) {
      return;
    }

    const timeout = window.setTimeout(() => {
      setOrganizationSelection(null);
      setError({ message: EXPIRED_SELECTION_MESSAGE });
    }, Math.max(1, organizationSelection.expiresIn) * 1_000);

    return () => window.clearTimeout(timeout);
  }, [organizationSelection]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    setError(null);
    setIsSubmitting(true);

    try {
      const data = await postApi<
        { email: string; password: string },
        LoginResponseData
      >("/api/v1/auth/login", {
        email,
        password,
      });

      form.reset();
      if (data.status === "organization_selection_required") {
        setOrganizationSelection({
          selectionTransaction: data.selection_transaction,
          expiresIn: data.expires_in,
          organizations: data.organizations,
        });
        return;
      }

      establishSession(data);
      router.replace(homePathForUser(data.user));
    } catch (cause) {
      setError(loginErrorPresentation(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  function returnToCredentials() {
    setOrganizationSelection(null);
    setError(null);
  }

  if (organizationSelection) {
    return (
      <section
        className={styles.selectionPanel}
        aria-labelledby="organization_selection_title"
      >
        <div className={styles.selectionHeading}>
          <span>Kimliğiniz doğrulandı</span>
          <h2 id="organization_selection_title">Kurum seçimi gerekiyor</h2>
          <p>
            Hesabınız birden fazla kurumla eşleşiyor. Devam etmek için güvenli kurum
            seçimi gerekiyor; bu adım şu anda kullanılamıyor.
          </p>
        </div>

        <ul className={styles.organizationList} aria-label="Erişilebilir kurumlar">
          {organizationSelection.organizations.map((organization) => (
            <li key={organization.selection_key}>{organization.display_name}</li>
          ))}
        </ul>

        <button
          className={styles.secondaryButton}
          type="button"
          onClick={returnToCredentials}
        >
          Giriş ekranına dön
        </button>
      </section>
    );
  }

  return (
    <form
      className={styles.form}
      method="post"
      action="/login"
      onSubmit={handleSubmit}
      aria-busy={isSubmitting}
    >
      {error ? (
        <FormAlert
          tone="error"
          title="Giriş tamamlanamadı"
          message={error.message}
          reference={error.reference}
        />
      ) : null}

      <fieldset className={styles.fieldset} disabled={isSubmitting}>
        <div className={styles.field}>
          <label htmlFor="email">E-posta adresi</label>
          <input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="ad@ornek.com"
            required
            maxLength={320}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="password">Parola</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="Parolanız"
            required
            maxLength={128}
          />
        </div>

        <button className={styles.primaryButton} type="submit">
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              Giriş yapılıyor…
            </>
          ) : (
            "Giriş yap"
          )}
        </button>
      </fieldset>
    </form>
  );
}
