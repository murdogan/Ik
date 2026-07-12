"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type RoleDetail,
  listRoles,
  replaceUserRoles,
} from "@/lib/role-administration";
import { refreshSession } from "@/lib/session";
import {
  type TenantUser,
  type UserStatus,
  type UserUpdateRequest,
  readTenantUser,
  updateTenantUser,
} from "@/lib/user-administration";

import { RoleChips } from "./role-chips";
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
  const dialogRef = useRef<HTMLElement>(null);
  const { user: actor } = useSession();
  const canAssignRoles = hasPermission(actor, AUTHORIZATION_PERMISSIONS.assignRoles);
  const canUpdateUsers = hasPermission(actor, AUTHORIZATION_PERMISSIONS.updateUsers);
  const [user, setUser] = useState<TenantUser | null>(null);
  const [fullName, setFullName] = useState("");
  const [status, setStatus] = useState<UserStatus>("active");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<UserAdminErrorPresentation | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [availableRoles, setAvailableRoles] = useState<RoleDetail[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [isLoadingRoles, setIsLoadingRoles] = useState(canAssignRoles);
  const [isSavingRoles, setIsSavingRoles] = useState(false);
  const [roleError, setRoleError] = useState<UserAdminErrorPresentation | null>(null);
  const [roleSuccess, setRoleSuccess] = useState<string | null>(null);

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
        setSelectedRoleIds(
          loadedUser.roles
            .filter((role) => role.scope_type === "tenant")
            .map((role) => role.id),
        );
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
    if (!canAssignRoles) {
      return;
    }

    let isActive = true;
    void listRoles().then(
      (roles) => {
        if (!isActive) {
          return;
        }
        setAvailableRoles(roles.filter((role) => role.scope_type === "tenant"));
        setRoleError(null);
        setIsLoadingRoles(false);
      },
      (cause) => {
        if (!isActive) {
          return;
        }
        setAvailableRoles([]);
        setRoleError(userAdminErrorPresentation(cause, "role_list"));
        setIsLoadingRoles(false);
      },
    );

    return () => {
      isActive = false;
    };
  }, [canAssignRoles]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving && !isSavingRoles) {
        onClose();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSaving, isSavingRoles, onClose]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("button:not([disabled])")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSaving && !isSavingRoles) {
      onClose();
    }
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") {
      return;
    }
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), " +
          "a[href], [tabindex]:not([tabindex='-1'])",
      ),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function toggleRole(roleId: string) {
    setSelectedRoleIds((currentRoleIds) =>
      currentRoleIds.includes(roleId)
        ? currentRoleIds.filter((currentRoleId) => currentRoleId !== roleId)
        : [...currentRoleIds, roleId],
    );
    setRoleError(null);
    setRoleSuccess(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || !canUpdateUsers || isSaving || isSavingRoles) {
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

  async function handleRoleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || !canAssignRoles || isSavingRoles || isSaving) {
      return;
    }

    const replacementRoleIds = availableRoles
      .filter((role) => selectedRoleIds.includes(role.id))
      .map((role) => role.id);
    const currentRoleIds = user.roles
      .filter((role) => role.scope_type === "tenant")
      .map((role) => role.id)
      .sort();

    if (
      replacementRoleIds.length === currentRoleIds.length &&
      [...replacementRoleIds].sort().every((roleId, index) => roleId === currentRoleIds[index])
    ) {
      setRoleError(null);
      setRoleSuccess("Kaydedilecek yeni bir rol değişikliği yok.");
      return;
    }

    setRoleError(null);
    setRoleSuccess(null);
    setIsSavingRoles(true);
    try {
      const updatedUser = await replaceUserRoles(user.id, replacementRoleIds);
      setUser(updatedUser);
      setSelectedRoleIds(
        updatedUser.roles
          .filter((role) => role.scope_type === "tenant")
          .map((role) => role.id),
      );
      setRoleSuccess("Kullanıcı rolleri güncellendi.");
      onUpdated(updatedUser);

      if (updatedUser.id === actor.id) {
        try {
          await refreshSession();
        } catch {
          // Session invalidation is published centrally and redirects to login when required.
        }
      }
    } catch (cause) {
      setRoleError(userAdminErrorPresentation(cause, "role_update"));
    } finally {
      setIsSavingRoles(false);
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-detail-title"
        aria-busy={isLoading || isSaving || isLoadingRoles || isSavingRoles}
        onKeyDown={keepFocusInDialog}
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
            disabled={isSaving || isSavingRoles}
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
            <>
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

                <div className={styles.assignedRoles}>
                  <span>Atanmış roller</span>
                  <RoleChips roles={user.roles} />
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
                    disabled={isSaving || isSavingRoles || !canUpdateUsers}
                  />
                </div>

                <div className={styles.formField}>
                  <label htmlFor="user_status">Hesap durumu</label>
                  <select
                    id="user_status"
                    name="status"
                    value={status}
                    onChange={(event) => setStatus(event.target.value as UserStatus)}
                    disabled={isSaving || isSavingRoles || !canUpdateUsers}
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
                  <div>
                    <dt>Yetki sürümü</dt>
                    <dd>{user.permission_version}</dd>
                  </div>
                </dl>

                <footer className={styles.dialogActions}>
                  <button
                    className={styles.secondaryButton}
                    type="button"
                    onClick={onClose}
                    disabled={isSaving || isSavingRoles}
                  >
                    Kapat
                  </button>
                  {canUpdateUsers ? (
                    <button
                      className={styles.primaryButton}
                      type="submit"
                      disabled={isSaving || isSavingRoles}
                    >
                      {isSaving ? "Kaydediliyor…" : "Değişiklikleri kaydet"}
                    </button>
                  ) : null}
                </footer>
              </form>

              {canAssignRoles ? (
                <section className={styles.roleSection} aria-labelledby="role-assignment-title">
                  <header className={styles.roleSectionHeader}>
                    <div>
                      <span>Yetkilendirme</span>
                      <h3 id="role-assignment-title">Rol ataması</h3>
                    </div>
                    <small>Seçili roller mevcut atamaların tamamının yerine geçer.</small>
                  </header>

                  {roleError ? (
                    <div className={styles.errorAlert} role="alert">
                      <strong>Rol işlemi tamamlanamadı</strong>
                      <span>{roleError.message}</span>
                      {roleError.reference ? <small>Referans: {roleError.reference}</small> : null}
                    </div>
                  ) : null}
                  {roleSuccess ? (
                    <div className={styles.successAlert} role="status">
                      {roleSuccess}
                    </div>
                  ) : null}

                  {isLoadingRoles ? (
                    <div className={styles.roleLoading} role="status">
                      <span className={styles.spinner} aria-hidden="true" />
                      Roller yükleniyor…
                    </div>
                  ) : availableRoles.length > 0 ? (
                    <form className={styles.roleForm} onSubmit={handleRoleSubmit}>
                      <fieldset
                        className={styles.roleFieldset}
                        disabled={isSavingRoles || isSaving}
                      >
                        <legend className={styles.visuallyHidden}>Kullanıcı rolleri</legend>
                        <div className={styles.roleOptions}>
                          {availableRoles.map((role) => (
                            <label className={styles.roleOption} key={role.id}>
                              <input
                                type="checkbox"
                                checked={selectedRoleIds.includes(role.id)}
                                onChange={() => toggleRole(role.id)}
                              />
                              <span>
                                <strong>{role.name}</strong>
                                <small>
                                  {role.description || `${role.permissions.length} izin içerir.`}
                                </small>
                              </span>
                            </label>
                          ))}
                        </div>
                      </fieldset>
                      <p className={styles.replaceHint}>
                        Hiç rol seçilmemesi kullanıcının uygulama yetkilerini kaldırır. Platform
                        rolleri tenant çalışma alanından atanamaz.
                      </p>
                      <footer className={styles.roleActions}>
                        <button
                          className={styles.primaryButton}
                          type="submit"
                          disabled={isSavingRoles || isSaving}
                        >
                          {isSavingRoles ? "Roller kaydediliyor…" : "Rolleri kaydet"}
                        </button>
                      </footer>
                    </form>
                  ) : roleError ? null : (
                    <p className={styles.roleEmptyState}>Atanabilir tenant rolü bulunamadı.</p>
                  )}
                </section>
              ) : null}
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}
