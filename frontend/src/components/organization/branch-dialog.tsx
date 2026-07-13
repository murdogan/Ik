"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  type Branch,
  type BranchCreateRequest,
  type BranchUpdateRequest,
  type LegalEntity,
  createBranch,
  updateBranch,
} from "@/lib/organization";

import styles from "./organization.module.css";
import {
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
  timezoneOptions,
} from "./organization-presentation";

interface BranchDialogProps {
  legalEntity: LegalEntity;
  branch: Branch | null;
  onClose: () => void;
  onSaved: (branch: Branch, created: boolean) => void;
}

interface BranchDraft {
  code: string;
  name: string;
  timezone: string;
  countryCode: string;
  city: string;
  address: string;
}

function draftFor(legalEntity: LegalEntity, branch: Branch | null): BranchDraft {
  return {
    code: branch?.code ?? "",
    name: branch?.name ?? "",
    timezone: branch?.timezone ?? legalEntity.timezone,
    countryCode: branch?.country_code ?? legalEntity.country_code ?? "",
    city: branch?.city ?? "",
    address: branch?.address ?? "",
  };
}

function nullableValue(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

export function BranchDialog({
  legalEntity,
  branch,
  onClose,
  onSaved,
}: BranchDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const isCreating = branch === null;
  const [draft, setDraft] = useState<BranchDraft>(() => draftFor(legalEntity, branch));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<OrganizationErrorPresentation | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const timezones = useMemo(() => timezoneOptions(draft.timezone), [draft.timezone]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving) {
        onClose();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSaving, onClose]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("input:not([readonly])")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function handleBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSaving) {
      onClose();
    }
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), " +
          "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving || branch?.status === "archived") return;

    const normalized = {
      code: draft.code.trim(),
      name: draft.name.trim(),
      timezone: draft.timezone,
      countryCode: nullableValue(draft.countryCode)?.toUpperCase() ?? null,
      city: nullableValue(draft.city),
      address: nullableValue(draft.address),
    };

    setError(null);
    setSuccess(null);
    setIsSaving(true);
    try {
      let savedBranch: Branch;
      if (isCreating) {
        const create: BranchCreateRequest = {
          legal_entity_id: legalEntity.id,
          code: normalized.code,
          name: normalized.name,
          timezone: normalized.timezone,
          country_code: normalized.countryCode,
          city: normalized.city,
          address: normalized.address,
        };
        savedBranch = await createBranch(create);
      } else {
        const update: BranchUpdateRequest = {};
        if (normalized.name !== branch.name) update.name = normalized.name;
        if (normalized.timezone !== branch.timezone) update.timezone = normalized.timezone;
        if (normalized.countryCode !== branch.country_code) {
          update.country_code = normalized.countryCode;
        }
        if (normalized.city !== branch.city) update.city = normalized.city;
        if (normalized.address !== branch.address) update.address = normalized.address;

        if (Object.keys(update).length === 0) {
          setSuccess("Kaydedilecek yeni bir değişiklik yok.");
          setIsSaving(false);
          return;
        }
        savedBranch = await updateBranch(branch.id, update);
      }

      setDraft(draftFor(legalEntity, savedBranch));
      setSuccess(isCreating ? "Şube oluşturuldu." : "Şube bilgileri güncellendi.");
      onSaved(savedBranch, isCreating);
    } catch (cause) {
      setError(
        organizationErrorPresentation(
          cause,
          isCreating ? "branch_create" : "branch_update",
        ),
      );
    } finally {
      setIsSaving(false);
    }
  }

  const title = isCreating ? "Yeni şube" : branch.name;

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdropClick}>
      <section
        ref={dialogRef}
        className={styles.detailDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-dialog-title"
        aria-busy={isSaving}
        onKeyDown={keepFocusInDialog}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>{isCreating ? "Şube oluştur" : "Şube bilgileri"}</span>
            <h2 id="branch-dialog-title">{title}</h2>
          </div>
          <button
            className={styles.iconButton}
            type="button"
            onClick={onClose}
            disabled={isSaving}
            aria-label="Şube penceresini kapat"
          >
            ×
          </button>
        </header>

        <div className={styles.dialogBody}>
          {error ? (
            <div className={styles.errorAlert} role="alert">
              <strong>{isCreating ? "Şube oluşturulamadı" : "Değişiklik kaydedilemedi"}</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
          ) : null}
          {success ? (
            <div className={styles.successAlert} role="status">{success}</div>
          ) : null}

          <form className={styles.branchForm} onSubmit={handleSubmit}>
            <p>
              Şube <strong>{legalEntity.name}</strong> tüzel kişiliği altında yer alır.
              Saat dilimi çalışan takvimleri ve zaman bazlı işlemler için kullanılır.
            </p>

            <div className={styles.formGrid}>
              <div className={styles.formField}>
                <label htmlFor="branch_code">Sabit kod</label>
                <input
                  id="branch_code"
                  value={draft.code}
                  onChange={(event) => setDraft({ ...draft, code: event.target.value })}
                  readOnly={!isCreating}
                  required
                  minLength={1}
                  maxLength={32}
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                  placeholder="ISTANBUL_MERKEZ"
                  disabled={isSaving}
                />
                <small>
                  {isCreating
                    ? "Harf, sayı, tire ve alt çizgi kullanın."
                    : "Geçmiş kayıtların tutarlılığı için değiştirilemez."}
                </small>
              </div>
              <div className={styles.formField}>
                <label htmlFor="branch_name">Şube adı</label>
                <input
                  id="branch_name"
                  value={draft.name}
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  required
                  minLength={1}
                  maxLength={200}
                  disabled={isSaving}
                />
              </div>
              <div className={styles.formField}>
                <label htmlFor="branch_timezone">Saat dilimi</label>
                <select
                  id="branch_timezone"
                  value={draft.timezone}
                  onChange={(event) => setDraft({ ...draft, timezone: event.target.value })}
                  required
                  disabled={isSaving}
                >
                  {timezones.map((timezone) => (
                    <option value={timezone} key={timezone}>{timezone}</option>
                  ))}
                </select>
              </div>
              <div className={styles.formField}>
                <label htmlFor="branch_country">Ülke kodu</label>
                <input
                  id="branch_country"
                  value={draft.countryCode}
                  onChange={(event) =>
                    setDraft({ ...draft, countryCode: event.target.value.toUpperCase() })
                  }
                  placeholder="TR"
                  minLength={2}
                  maxLength={2}
                  pattern="[A-Za-z]{2}"
                  disabled={isSaving}
                />
              </div>
              <div className={`${styles.formField} ${styles.wideField}`}>
                <label htmlFor="branch_city">Şehir</label>
                <input
                  id="branch_city"
                  value={draft.city}
                  onChange={(event) => setDraft({ ...draft, city: event.target.value })}
                  maxLength={120}
                  disabled={isSaving}
                />
              </div>
              <div className={`${styles.formField} ${styles.wideField}`}>
                <label htmlFor="branch_address">Adres</label>
                <textarea
                  id="branch_address"
                  value={draft.address}
                  onChange={(event) => setDraft({ ...draft, address: event.target.value })}
                  maxLength={500}
                  rows={4}
                  disabled={isSaving}
                />
              </div>
            </div>

            <footer className={styles.dialogActions}>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={onClose}
                disabled={isSaving}
              >
                {success ? "Kapat" : "Vazgeç"}
              </button>
              <button className={styles.primaryButton} type="submit" disabled={isSaving}>
                {isSaving
                  ? "Kaydediliyor…"
                  : isCreating
                    ? "Şube oluştur"
                    : "Değişiklikleri kaydet"}
              </button>
            </footer>
          </form>
        </div>
      </section>
    </div>
  );
}
