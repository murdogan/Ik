"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useOrganizationSelection } from "@/components/auth/organization-selection-provider";
import {
  type LoginResponseData,
  loginErrorPresentation,
} from "@/lib/auth-contracts";
import { postApi } from "@/lib/api-client";
import { homePathForUser } from "@/lib/authorization";
import { establishSession } from "@/lib/session";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

export function LoginForm() {
  const router = useRouter();
  const { beginSelection, clearSelection } = useOrganizationSelection();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ReturnType<typeof loginErrorPresentation> | null>(
    null,
  );
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    setError(null);
    setIsSubmitting(true);
    clearSelection();

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
        beginSelection(data, "login");
        router.replace("/select-organization");
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
