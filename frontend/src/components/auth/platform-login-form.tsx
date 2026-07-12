"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import {
  type PlatformLoginResponseData,
  platformLoginErrorPresentation,
} from "@/lib/auth-contracts";
import { ApiClientError, postApi } from "@/lib/api-client";
import { establishPlatformSession } from "@/lib/platform-session";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

export function PlatformLoginForm() {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<
    ReturnType<typeof platformLoginErrorPresentation> | null
  >(null);

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
        PlatformLoginResponseData
      >("/api/v1/platform/auth/login", { email, password });

      if (
        data.status !== "authenticated" ||
        data.user.workspace_scope !== "platform"
      ) {
        throw new ApiClientError({ status: 200, code: "invalid_response" });
      }

      form.reset();
      establishPlatformSession(data);
      router.replace("/platform");
    } catch (cause) {
      setError(platformLoginErrorPresentation(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form
      className={styles.form}
      method="post"
      action="/platform/login"
      onSubmit={handleSubmit}
      aria-busy={isSubmitting}
    >
      {error ? (
        <FormAlert
          tone="error"
          title="Platform girişi tamamlanamadı"
          message={error.message}
          reference={error.reference}
        />
      ) : null}

      <fieldset className={styles.fieldset} disabled={isSubmitting}>
        <div className={styles.field}>
          <label htmlFor="platform_email">E-posta adresi</label>
          <input
            id="platform_email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="yonetici@ornek.com"
            required
            maxLength={320}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="platform_password">Parola</label>
          <input
            id="platform_password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="Parolanız"
            required
            maxLength={128}
          />
        </div>

        <button
          className={`${styles.primaryButton} ${styles.platformPrimaryButton}`}
          type="submit"
        >
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              Platform oturumu açılıyor…
            </>
          ) : (
            "Platform yönetimine gir"
          )}
        </button>
      </fieldset>

      <p className={styles.realmSwitch}>
        Kurum çalışma alanına mı gireceksiniz? <Link href="/login">Standart giriş</Link>
      </p>
    </form>
  );
}
