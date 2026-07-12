"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import {
  type LoginResponseData,
  loginErrorPresentation,
} from "@/lib/auth-contracts";
import { postApi } from "@/lib/api-client";
import { homePathForUser } from "@/lib/authorization";
import { establishSession } from "@/lib/session";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

interface LoginFormProps {
  initialTenantSlug?: string;
}

export function LoginForm({ initialTenantSlug = "" }: LoginFormProps) {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<ReturnType<typeof loginErrorPresentation> | null>(
    null,
  );
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const tenantSlug = String(formData.get("tenant_slug") ?? "")
      .trim()
      .toLowerCase();
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    setError(null);
    setIsSubmitting(true);

    try {
      const data = await postApi<
        { tenant_slug: string; email: string; password: string },
        LoginResponseData
      >("/api/v1/auth/login", {
        tenant_slug: tenantSlug,
        email,
        password,
      });

      form.reset();
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
          <label htmlFor="tenant_slug">Kurum kodu</label>
          <input
            id="tenant_slug"
            name="tenant_slug"
            type="text"
            autoComplete="organization"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="ornek-sirket"
            required
            maxLength={80}
            defaultValue={initialTenantSlug}
            aria-describedby="tenant_slug_hint"
          />
          <small id="tenant_slug_hint">
            Yöneticinizin paylaştığı kısa kurum kodunu girin.
          </small>
        </div>

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
