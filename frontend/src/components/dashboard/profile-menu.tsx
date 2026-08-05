"use client";

import Link from "next/link";
import {
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";

import { TenantIcon } from "./tenant-icons";
import styles from "./tenant-shell.module.css";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const initials =
    parts.length > 1
      ? `${parts[0]?.charAt(0) ?? ""}${parts.at(-1)?.charAt(0) ?? ""}`
      : (parts[0]?.slice(0, 2) ?? "");
  return (initials || "WF").toLocaleUpperCase("tr-TR");
}

function enabledMenuItems(menu: HTMLElement): HTMLElement[] {
  return Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]')).filter(
    (item) =>
      !item.hasAttribute("disabled") && item.getAttribute("aria-disabled") !== "true",
  );
}

export function ProfileMenu() {
  const {
    user,
    isLoggingOut,
    isSwitchingOrganization,
    signOut,
    switchOrganization,
  } = useSession();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isLogoutDialogOpen, setIsLogoutDialogOpen] = useState(false);
  const [isConfirmingLogout, setIsConfirmingLogout] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const initialMenuFocus = useRef<"first" | "last">("first");
  const logoutStarted = useRef(false);
  const dialogBusy = useRef(false);
  const isMounted = useRef(true);
  const menuId = useId();
  const dialogTitleId = useId();
  const dialogDescriptionId = useId();
  const name = displayName(user.full_name, user.email);
  const roleNames = user.roles.map((role) => role.name).join(" · ") || "Rol atanmamış";
  const canOpenProfile = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readOwnEmployee,
  );
  const mutationInProgress = isLoggingOut || isConfirmingLogout;
  dialogBusy.current = mutationInProgress;

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const returnFocusToTrigger = useCallback(() => {
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  const closeMenu = useCallback(
    (returnFocus: boolean) => {
      setIsMenuOpen(false);
      if (returnFocus) returnFocusToTrigger();
    },
    [returnFocusToTrigger],
  );

  useEffect(() => {
    if (!isMenuOpen) return;

    const frame = window.requestAnimationFrame(() => {
      const menu = menuRef.current;
      if (!menu) return;
      const items = enabledMenuItems(menu);
      const target = initialMenuFocus.current === "last" ? items.at(-1) : items[0];
      target?.focus();
    });

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      closeMenu(false);
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeMenu(true);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [closeMenu, isMenuOpen]);

  const closeLogoutDialog = useCallback(() => {
    if (dialogBusy.current) return;
    setIsLogoutDialogOpen(false);
    returnFocusToTrigger();
  }, [returnFocusToTrigger]);

  useEffect(() => {
    if (!isLogoutDialogOpen) return;

    const frame = window.requestAnimationFrame(() => cancelRef.current?.focus());

    const handleDialogKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (dialogBusy.current) return;
        event.preventDefault();
        closeLogoutDialog();
        return;
      }
      if (event.key !== "Tab") return;

      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => !element.hasAttribute("disabled"));

      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };

    document.addEventListener("keydown", handleDialogKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleDialogKeyDown);
    };
  }, [closeLogoutDialog, isLogoutDialogOpen]);

  useEffect(() => {
    if (isLogoutDialogOpen && mutationInProgress) {
      dialogRef.current?.focus();
    }
  }, [isLogoutDialogOpen, mutationInProgress]);

  function handleTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    initialMenuFocus.current = event.key === "ArrowUp" ? "last" : "first";
    setIsMenuOpen(true);
  }

  function handleMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!["ArrowDown", "ArrowUp", "Home", "End", "Tab"].includes(event.key)) {
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      closeMenu(true);
      return;
    }

    const items = enabledMenuItems(event.currentTarget);
    if (items.length === 0) return;
    event.preventDefault();
    const currentIndex = items.findIndex((item) => item === document.activeElement);
    if (event.key === "Home") {
      items[0]?.focus();
      return;
    }
    if (event.key === "End") {
      items.at(-1)?.focus();
      return;
    }
    const direction = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex =
      currentIndex < 0
        ? direction > 0
          ? 0
          : items.length - 1
        : (currentIndex + direction + items.length) % items.length;
    items[nextIndex]?.focus();
  }

  function openLogoutDialog() {
    logoutStarted.current = false;
    setIsMenuOpen(false);
    setIsLogoutDialogOpen(true);
  }

  async function confirmLogout() {
    if (logoutStarted.current || dialogBusy.current) return;
    logoutStarted.current = true;
    dialogBusy.current = true;
    setIsConfirmingLogout(true);
    try {
      await signOut();
    } finally {
      if (!isMounted.current) return;
      logoutStarted.current = false;
      dialogBusy.current = false;
      setIsConfirmingLogout(false);
      setIsLogoutDialogOpen(false);
      returnFocusToTrigger();
    }
  }

  return (
    <div className={styles.profileMenuContainer}>
      <button
        ref={triggerRef}
        className={styles.profileTrigger}
        type="button"
        aria-label="Profil menüsünü aç"
        aria-haspopup="menu"
        aria-expanded={isMenuOpen}
        aria-controls={isMenuOpen ? menuId : undefined}
        onClick={() => {
          initialMenuFocus.current = "first";
          setIsMenuOpen((open) => !open);
        }}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className={styles.avatar} aria-hidden="true">
          {initialsFor(name)}
        </span>
      </button>

      {isMenuOpen ? (
        <div
          ref={menuRef}
          id={menuId}
          className={styles.profileMenu}
          role="menu"
          aria-label="Profil menüsü"
          onKeyDown={handleMenuKeyDown}
        >
          <div className={styles.profileSummary}>
            <strong>{name}</strong>
            <span>{user.email}</span>
            <small>{roleNames}</small>
          </div>
          <div className={styles.profileMenuItems}>
            {canOpenProfile ? (
              <Link
                className={styles.profileMenuItem}
                href="/profile"
                role="menuitem"
                onClick={() => closeMenu(false)}
              >
                <TenantIcon name="profile" />
                Profilim
              </Link>
            ) : null}
            <button
              className={styles.profileMenuItem}
              type="button"
              role="menuitem"
              disabled={isLoggingOut || isSwitchingOrganization}
              onClick={() => {
                closeMenu(false);
                void switchOrganization();
              }}
            >
              <TenantIcon name="organization" />
              {isSwitchingOrganization ? "Kurumlar hazırlanıyor…" : "Kurum değiştir"}
            </button>
            <button
              className={`${styles.profileMenuItem} ${styles.dangerMenuItem}`}
              type="button"
              role="menuitem"
              disabled={isLoggingOut || isSwitchingOrganization}
              onClick={openLogoutDialog}
            >
              <TenantIcon name="logout" />
              Çıkış yap
            </button>
          </div>
        </div>
      ) : null}

      {isLogoutDialogOpen ? (
        <div
          className={styles.dialogBackdrop}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeLogoutDialog();
          }}
        >
          <div
            ref={dialogRef}
            className={styles.logoutDialog}
            role="dialog"
            aria-modal="true"
            aria-labelledby={dialogTitleId}
            aria-describedby={dialogDescriptionId}
            aria-busy={mutationInProgress}
            tabIndex={-1}
          >
            <div className={styles.dialogIcon} aria-hidden="true">
              <TenantIcon name="logout" />
            </div>
            <div className={styles.dialogCopy}>
              <h2 id={dialogTitleId}>Oturumu kapat</h2>
              <p id={dialogDescriptionId}>
                Oturumu kapatmak istediğinize emin misiniz?
              </p>
            </div>
            <div className={styles.dialogActions}>
              <button
                ref={cancelRef}
                className={styles.cancelButton}
                type="button"
                disabled={mutationInProgress}
                onClick={closeLogoutDialog}
              >
                Vazgeç
              </button>
              <button
                className={styles.confirmLogoutButton}
                type="button"
                disabled={mutationInProgress}
                onClick={() => void confirmLogout()}
              >
                {mutationInProgress ? "Çıkış yapılıyor…" : "Çıkış yap"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
