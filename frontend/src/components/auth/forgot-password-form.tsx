"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import {
  type PasswordResetRequestResponseData,
  passwordResetRequestErrorPresentation,
} from "@/lib/auth-contracts";
import { postApi } from "@/lib/api-client";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

export function ForgotPasswordForm() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAccepted, setIsAccepted] = useState(false);
  const [error, setError] = useState<
    ReturnType<typeof passwordResetRequestErrorPresentation> | null
  >(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const email = String(formData.get("email") ?? "").trim();

    setError(null);
    setIsSubmitting(true);

    try {
      await postApi<{ email: string }, PasswordResetRequestResponseData>(
        "/api/v1/auth/password-reset/request",
        { email },
      );
      form.reset();
      setIsAccepted(true);
    } catch (cause) {
      setError(passwordResetRequestErrorPresentation(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isAccepted) {
    return (
      <div className={styles.resultPanel}>
        <FormAlert
          tone="success"
          title="İsteğiniz alındı"
          message="Bu e-posta adresiyle eşleşen bir hesap varsa parola yenileme bağlantısını gönderdik. Gelen kutunuzu ve istenmeyen e-posta klasörünü kontrol edin."
        />
        <Link className={styles.primaryLink} href="/login">
          Giriş ekranına dön
        </Link>
        <button
          className={styles.secondaryButton}
          type="button"
          onClick={() => setIsAccepted(false)}
        >
          Başka bir e-posta için iste
        </button>
      </div>
    );
  }

  return (
    <form
      className={styles.form}
      method="post"
      action="/forgot-password"
      onSubmit={handleSubmit}
      aria-busy={isSubmitting}
    >
      {error ? (
        <FormAlert
          tone="error"
          title="İstek gönderilemedi"
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
            autoFocus
          />
        </div>

        <button className={styles.primaryButton} type="submit">
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              İstek gönderiliyor…
            </>
          ) : (
            "Yenileme bağlantısı iste"
          )}
        </button>

        <Link className={styles.secondaryLink} href="/login">
          Giriş ekranına dön
        </Link>
      </fieldset>
    </form>
  );
}
