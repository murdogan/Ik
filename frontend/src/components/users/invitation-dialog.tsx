"use client";

import { type FormEvent, type MouseEvent, useEffect, useState } from "react";

import {
  type UserInvitation,
  inviteTenantUser,
} from "@/lib/user-administration";

import styles from "./users.module.css";
import {
  formatUserDate,
  type UserAdminErrorPresentation,
  userAdminErrorPresentation,
} from "./user-presentation";

interface InvitationDialogProps {
  onClose: () => void;
  onInvited: () => void;
}

export function InvitationDialog({ onClose, onInvited }: InvitationDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<UserAdminErrorPresentation | null>(null);
  const [invitation, setInvitation] = useState<UserInvitation | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSubmitting) {
        onClose();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSubmitting, onClose]);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSubmitting) {
      onClose();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }

    const formData = new FormData(event.currentTarget);
    const fullName = String(formData.get("full_name") ?? "").trim();
    const email = String(formData.get("email") ?? "")
      .trim()
      .toLowerCase();

    setError(null);
    setCopyMessage(null);
    setIsSubmitting(true);
    try {
      const createdInvitation = await inviteTenantUser({
        email,
        full_name: fullName,
      });
      setInvitation(createdInvitation);
      onInvited();
    } catch (cause) {
      setError(userAdminErrorPresentation(cause, "invite"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function copyActivationUrl() {
    if (!invitation) {
      return;
    }
    try {
      await navigator.clipboard.writeText(invitation.activation_url);
      setCopyMessage("Davet bağlantısı panoya kopyalandı.");
    } catch {
      setCopyMessage("Bağlantıyı aşağıdaki alandan elle kopyalayabilirsiniz.");
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        className={`${styles.detailDialog} ${styles.invitationDialog}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="invitation-title"
        aria-busy={isSubmitting}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>Yeni kullanıcı</span>
            <h2 id="invitation-title">
              {invitation ? "Davet hazır" : "Kullanıcı davet et"}
            </h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Davet penceresini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>Davet gönderilemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}

          {invitation ? (
            <div className={styles.invitationResult}>
              <div className={styles.successMark} aria-hidden="true">
                ✓
              </div>
              <div className={styles.resultHeading}>
                <h3>{invitation.user.full_name} için davet oluşturuldu</h3>
                <p>
                  Kullanıcı davet bekliyor. Güvenli etkinleştirme bağlantısını kullanıcıyla
                  paylaşın.
                </p>
              </div>

              <div className={styles.activationField}>
                <label htmlFor="activation_url">Etkinleştirme bağlantısı</label>
                <div>
                  <input
                    id="activation_url"
                    type="text"
                    value={invitation.activation_url}
                    readOnly
                    onFocus={(event) => event.currentTarget.select()}
                  />
                  <button className={styles.secondaryButton} type="button" onClick={copyActivationUrl}>
                    Kopyala
                  </button>
                </div>
                <small>Son geçerlilik: {formatUserDate(invitation.expires_at)}</small>
                {copyMessage ? <span role="status">{copyMessage}</span> : null}
              </div>

              <footer className={styles.dialogActions}>
                <button className={styles.primaryButton} type="button" onClick={onClose}>
                  Tamam
                </button>
              </footer>
            </div>
          ) : (
            <form className={styles.invitationForm} onSubmit={handleSubmit}>
              <p>
                Kullanıcı yalnızca bu çalışma alanına davet edilir. Hesabını bağlantı üzerinden
                etkinleştirdikten sonra giriş yapabilir.
              </p>

              <div className={styles.formField}>
                <label htmlFor="invite_full_name">Ad soyad</label>
                <input
                  id="invite_full_name"
                  name="full_name"
                  type="text"
                  autoComplete="name"
                  placeholder="Örn. Deniz Yılmaz"
                  required
                  minLength={1}
                  maxLength={200}
                  disabled={isSubmitting}
                  autoFocus
                />
              </div>

              <div className={styles.formField}>
                <label htmlFor="invite_email">İş e-postası</label>
                <input
                  id="invite_email"
                  name="email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="deniz@ornek.com"
                  required
                  maxLength={320}
                  disabled={isSubmitting}
                />
              </div>

              <footer className={styles.dialogActions}>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={onClose}
                  disabled={isSubmitting}
                >
                  Vazgeç
                </button>
                <button className={styles.primaryButton} type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Davet hazırlanıyor…" : "Davet gönder"}
                </button>
              </footer>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
