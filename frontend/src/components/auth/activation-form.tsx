"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import {
  type ActivationResponseData,
  activationErrorPresentation,
} from "@/lib/auth-contracts";
import { postApi } from "@/lib/api-client";

import styles from "./auth.module.css";
import { FormAlert } from "./form-alert";

interface ActivationSuccess {
  displayName: string;
  tenantName: string;
  tenantSlug: string;
}

function tokenFromFragment(fragment: string): string | null {
  if (!fragment) {
    return null;
  }

  const parameters = new URLSearchParams(fragment);
  const namedToken = parameters.get("token")?.trim();
  if (namedToken) {
    return namedToken;
  }

  if (fragment.includes("=")) {
    return null;
  }

  try {
    return decodeURIComponent(fragment).trim() || null;
  } catch {
    return null;
  }
}

export function ActivationForm() {
  const fragmentWasRead = useRef(false);
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<
    ReturnType<typeof activationErrorPresentation> | null
  >(null);
  const [success, setSuccess] = useState<ActivationSuccess | null>(null);

  useEffect(() => {
    if (fragmentWasRead.current) {
      return;
    }
    fragmentWasRead.current = true;

    const fragment = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const activationToken = tokenFromFragment(fragment);

    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}${window.location.search}`,
    );
    setToken(activationToken);
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
      const data = await postApi<
        { token: string; password: string },
        ActivationResponseData
      >("/api/v1/auth/activate", { token, password });

      form.reset();
      setToken(null);
      setSuccess({
        displayName: data.user.full_name?.trim() || data.user.email,
        tenantName: data.user.tenant.name,
        tenantSlug: data.user.tenant.slug,
      });
    } catch (cause) {
      setError(activationErrorPresentation(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (token === undefined) {
    return (
      <div className={styles.loadingPanel} role="status" aria-live="polite">
        <span className={styles.spinnerDark} aria-hidden="true" />
        Davet bağlantısı hazırlanıyor…
      </div>
    );
  }

  if (success) {
    return (
      <div className={styles.resultPanel}>
        <FormAlert
          tone="success"
          title="Hesabınız hazır"
          message={`${success.displayName}, ${success.tenantName} hesabınız etkinleştirildi. Artık belirlediğiniz parolayla giriş yapabilirsiniz.`}
        />
        <Link
          className={styles.primaryLink}
          href={`/login?tenant=${encodeURIComponent(success.tenantSlug)}`}
        >
          Giriş ekranına git
        </Link>
      </div>
    );
  }

  if (!token) {
    return (
      <div className={styles.resultPanel}>
        <FormAlert
          tone="error"
          title="Davet bağlantısı bulunamadı"
          message="E-postanızdaki davet bağlantısını yeniden açın. Bağlantı çalışmıyorsa yöneticinizden yeni bir davet isteyin."
        />
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
      action="/activate"
      onSubmit={handleSubmit}
      aria-busy={isSubmitting}
    >
      {error ? (
        <>
          <FormAlert
            tone="error"
            title="Hesap etkinleştirilemedi"
            message={error.message}
            reference={error.reference}
          />
          {error.offerLogin ? (
            <Link className={styles.secondaryLink} href="/login">
              Giriş yapmayı dene
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
            aria-describedby="new_password_hint"
          />
          <small id="new_password_hint">
            12–128 karakterden oluşan, size özel bir parola kullanın.
          </small>
        </div>

        <div className={styles.field}>
          <label htmlFor="password_confirmation">Yeni parolayı doğrulayın</label>
          <input
            id="password_confirmation"
            name="password_confirmation"
            type="password"
            autoComplete="new-password"
            placeholder="Parolanızı yeniden girin"
            required
            minLength={12}
            maxLength={128}
          />
        </div>

        <button className={styles.primaryButton} type="submit">
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              Hesap hazırlanıyor…
            </>
          ) : (
            "Hesabımı etkinleştir"
          )}
        </button>
      </fieldset>
    </form>
  );
}
