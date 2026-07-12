"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type PasswordResetConfirmResponseData,
  passwordResetConfirmErrorPresentation,
} from "@/lib/auth-contracts";
import { postApi } from "@/lib/api-client";
import { tokenFromFragment } from "@/lib/fragment-token";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

export function ResetPasswordForm() {
  const fragmentWasRead = useRef(false);
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [error, setError] = useState<
    ReturnType<typeof passwordResetConfirmErrorPresentation> | null
  >(null);

  useEffect(() => {
    if (fragmentWasRead.current) {
      return;
    }
    fragmentWasRead.current = true;

    const fragment = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const resetToken = tokenFromFragment(fragment);

    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}${window.location.search}`,
    );
    setToken(resetToken);
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    const form = event.currentTarget;
    const formData = new FormData(form);
    const password = String(formData.get("password") ?? "");
    const confirmation = String(formData.get("password_confirmation") ?? "");

    if (password !== confirmation) {
      setError({ message: "Parola alanları eşleşmiyor. İki alanı da kontrol edin." });
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      await postApi<
        { token: string; password: string },
        PasswordResetConfirmResponseData
      >("/api/v1/auth/password-reset/confirm", { token, password });
      form.reset();
      setToken(null);
      setIsCompleted(true);
    } catch (cause) {
      setError(passwordResetConfirmErrorPresentation(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (token === undefined) {
    return (
      <div className={styles.loadingPanel} role="status" aria-live="polite">
        <span className={styles.spinnerDark} aria-hidden="true" />
        Parola yenileme bağlantısı hazırlanıyor…
      </div>
    );
  }

  if (isCompleted) {
    return (
      <div className={styles.resultPanel}>
        <FormAlert
          tone="success"
          title="Parolanız yenilendi"
          message="Yeni parolanız hazır. E-posta adresiniz ve yeni parolanızla giriş yapabilirsiniz."
        />
        <Link className={styles.primaryLink} href="/login">
          Giriş yap
        </Link>
      </div>
    );
  }

  if (!token) {
    return (
      <div className={styles.resultPanel}>
        <FormAlert
          tone="error"
          title="Yenileme bağlantısı bulunamadı"
          message="E-postanızdaki parola yenileme bağlantısını yeniden açın. Bağlantı çalışmıyorsa yeni bir bağlantı isteyin."
        />
        <Link className={styles.primaryLink} href="/forgot-password">
          Yeni bağlantı iste
        </Link>
        <Link className={styles.secondaryLink} href="/login">
          Giriş ekranına dön
        </Link>
      </div>
    );
  }

  return (
    <form
      className={styles.form}
      method="post"
      action="/reset-password"
      onSubmit={handleSubmit}
      aria-busy={isSubmitting}
    >
      {error ? (
        <>
          <FormAlert
            tone="error"
            title="Parola yenilenemedi"
            message={error.message}
            reference={error.reference}
          />
          {error.offerNewRequest ? (
            <Link className={styles.secondaryLink} href="/forgot-password">
              Yeni bağlantı iste
            </Link>
          ) : null}
        </>
      ) : null}

      <fieldset className={styles.fieldset} disabled={isSubmitting}>
        <div className={styles.field}>
          <label htmlFor="password">Yeni parola</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            placeholder="En az 12 karakter"
            required
            minLength={12}
            maxLength={128}
            aria-describedby="reset_password_hint"
            autoFocus
          />
          <small id="reset_password_hint">
            12–128 karakterden oluşan, başka hesaplarda kullanmadığınız bir parola seçin.
          </small>
        </div>

        <div className={styles.field}>
          <label htmlFor="password_confirmation">Yeni parolayı doğrulayın</label>
          <input
            id="password_confirmation"
            name="password_confirmation"
            type="password"
            autoComplete="new-password"
            placeholder="Yeni parolanızı yeniden girin"
            required
            minLength={12}
            maxLength={128}
          />
        </div>

        <button className={styles.primaryButton} type="submit">
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              Parola yenileniyor…
            </>
          ) : (
            "Parolamı yenile"
          )}
        </button>
      </fieldset>
    </form>
  );
}
