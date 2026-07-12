"use client";

import { type FormEvent, type MouseEvent, useEffect, useState } from "react";

import {
  type TenantUser,
  type UserStatus,
  type UserUpdateRequest,
  readTenantUser,
  updateTenantUser,
} from "@/lib/user-administration";

import { StatusBadge } from "./status-badge";
import styles from "./users.module.css";
import {
  formatUserDate,
  STATUS_LABELS,
  type UserAdminErrorPresentation,
  userAdminErrorPresentation,
} from "./user-presentation";

interface UserDetailDialogProps {
  userId: string;
  onClose: () => void;
  onUpdated: (user: TenantUser) => void;
}

function allowedStatusOptions(currentStatus: UserStatus): UserStatus[] {
  if (currentStatus === "invited") {
    return ["invited", "disabled"];
  }
  if (currentStatus === "disabled") {
    return ["active", "disabled", "invited"];
  }
  return ["active", "locked", "disabled"];
}

export function UserDetailDialog({
  userId,
  onClose,
  onUpdated,
}: UserDetailDialogProps) {
  const [user, setUser] = useState<TenantUser | null>(null);
  const [fullName, setFullName] = useState("");
  const [status, setStatus] = useState<UserStatus>("active");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<UserAdminErrorPresentation | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    void readTenantUser(userId).then(
      (loadedUser) => {
        if (!isActive) {
          return;
        }
        setUser(loadedUser);
        setFullName(loadedUser.full_name);
        setStatus(loadedUser.status);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) {
          return;
        }
        setError(userAdminErrorPresentation(cause, "read"));
        setIsLoading(false);
      },
    );

    return () => {
      isActive = false;
    };
  }, [userId]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving) {
        onClose();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSaving, onClose]);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSaving) {
      onClose();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || isSaving) {
      return;
    }

    const normalizedName = fullName.trim();
    const update: UserUpdateRequest = {};
    if (normalizedName !== user.full_name) {
      update.full_name = normalizedName;
    }
    if (status !== user.status) {
      update.status = status;
    }

    if (Object.keys(update).length === 0) {
      setError(null);
      setSuccess("Kaydedilecek yeni bir değişiklik yok.");
      return;
    }

    setError(null);
    setSuccess(null);
    setIsSaving(true);
    try {
      const updatedUser = await updateTenantUser(user.id, update);
      setUser(updatedUser);
      setFullName(updatedUser.full_name);
      setStatus(updatedUser.status);
      setSuccess("Kullanıcı bilgileri güncellendi.");
      onUpdated(updatedUser);
    } catch (cause) {
      setError(userAdminErrorPresentation(cause, "update"));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-detail-title"
        aria-busy={isLoading || isSaving}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>Kullanıcı ayrıntısı</span>
            <h2 id="user-detail-title">{user?.full_name || "Kullanıcı yükleniyor"}</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSaving}
            aria-label="Kullanıcı ayrıntısını kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>İşlem tamamlanamadı</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}
          {success ? (
            <div className={styles.successAlert} role="status">
              {success}
            </div>
          ) : null}

          {isLoading ? (
            <div className={styles.dialogLoading} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              Kullanıcı bilgileri yükleniyor…
            </div>
          ) : user ? (
            <form className={styles.editForm} onSubmit={handleSubmit}>
              <div className={styles.identitySummary}>
                <div className={styles.avatar} aria-hidden="true">
                  {user.full_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
                </div>
                <div>
                  <strong>{user.full_name}</strong>
                  <span>{user.email}</span>
                </div>
                <StatusBadge status={user.status} />
              </div>

              <div className={styles.formField}>
                <label htmlFor="user_full_name">Ad soyad</label>
                <input
                  id="user_full_name"
                  name="full_name"
                  type="text"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  required
                  minLength={1}
                  maxLength={200}
                  disabled={isSaving}
                />
              </div>

              <div className={styles.formField}>
                <label htmlFor="user_status">Hesap durumu</label>
                <select
                  id="user_status"
                  name="status"
                  value={status}
                  onChange={(event) => setStatus(event.target.value as UserStatus)}
                  disabled={isSaving}
                >
                  {allowedStatusOptions(user.status).map((userStatus) => (
                    <option value={userStatus} key={userStatus}>
                      {STATUS_LABELS[userStatus]}
                    </option>
                  ))}
                </select>
                <small>Durum değişiklikleri kullanıcının hesap erişimini etkiler.</small>
              </div>

              <div className={styles.readOnlyField}>
                <span>E-posta</span>
                <strong>{user.email}</strong>
                <small>E-posta adresi bu ekrandan değiştirilemez.</small>
              </div>

              <dl className={styles.userMetadata}>
                <div>
                  <dt>Oluşturulma</dt>
                  <dd>{formatUserDate(user.created_at)}</dd>
                </div>
                <div>
                  <dt>Son güncelleme</dt>
                  <dd>{formatUserDate(user.updated_at)}</dd>
                </div>
              </dl>

              <footer className={styles.dialogActions}>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={onClose}
                  disabled={isSaving}
                >
                  Kapat
                </button>
                <button className={styles.primaryButton} type="submit" disabled={isSaving}>
                  {isSaving ? "Kaydediliyor…" : "Değişiklikleri kaydet"}
                </button>
              </footer>
            </form>
          ) : null}
        </div>
      </section>
    </div>
  );
}
