"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  createPlatformTenant,
  type PlatformResponseMeta,
  type PlatformTenant,
  type PlatformTenantCreateRequest,
  type PlatformTenantErrorPresentation,
  PLATFORM_TENANT_LOCALES,
  PLATFORM_TENANT_PLANS,
  PLATFORM_TENANT_REGIONS,
  platformTenantErrorPresentation,
} from "@/lib/platform-tenants";

import styles from "./platform-tenant-operations.module.css";
import {
  PLATFORM_PLAN_LABELS,
  PLATFORM_REGION_LABELS,
} from "./platform-tenant-presentation";

const SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$/;

export function CreateTenantDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (tenant: PlatformTenant, meta: PlatformResponseMeta) => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] =
    useState<PlatformTenantErrorPresentation | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current
        ?.querySelector<HTMLInputElement>("input:not([disabled])")
        ?.focus();
    });
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving) onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", closeOnEscape);
      previouslyFocused?.focus();
    };
  }, [isSaving, onClose]);

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled])",
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

  function closeFromBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSaving) onClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving) return;

    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const slug = String(form.get("slug") ?? "").trim();
    const timezone = String(form.get("timezone") ?? "").trim();
    const limitInput = String(form.get("active_employees") ?? "").trim();
    const limit = limitInput ? Number(limitInput) : null;
    const plan = String(form.get("plan_code") ?? "");
    const dataRegion = String(form.get("data_region") ?? "");
    const locale = String(form.get("locale") ?? "");

    if (
      name.length < 1 ||
      name.length > 200 ||
      slug.length < 2 ||
      !SLUG_PATTERN.test(slug) ||
      timezone.length < 1 ||
      timezone.length > 64 ||
      !PLATFORM_TENANT_PLANS.includes(
        plan as PlatformTenantCreateRequest["plan_code"],
      ) ||
      !PLATFORM_TENANT_REGIONS.includes(
        dataRegion as PlatformTenantCreateRequest["data_region"],
      ) ||
      !PLATFORM_TENANT_LOCALES.includes(
        locale as PlatformTenantCreateRequest["locale"],
      ) ||
      (limit !== null &&
        (!Number.isSafeInteger(limit) || limit < 1 || limit > 1_000_000))
    ) {
      setValidationError(
        "Ad, tenant kodu, saat dilimi ve çalışan limiti alanlarını kontrol edin.",
      );
      return;
    }

    const payload: PlatformTenantCreateRequest = {
      name,
      slug,
      plan_code: plan as PlatformTenantCreateRequest["plan_code"],
      data_region:
        dataRegion as PlatformTenantCreateRequest["data_region"],
      locale: locale as PlatformTenantCreateRequest["locale"],
      timezone,
      ...(limit === null ? {} : { limits: { active_employees: limit } }),
    };

    setValidationError(null);
    setError(null);
    setIsSaving(true);
    try {
      const response = await createPlatformTenant(payload);
      onCreated(response.data, response.meta);
    } catch (cause) {
      setError(
        platformTenantErrorPresentation(
          cause,
          "Tenant şu anda oluşturulamıyor. Bilgileri kontrol edip yeniden deneyin.",
        ),
      );
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.dialogBackdrop} onMouseDown={closeFromBackdrop}>
      <section
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-tenant-title"
        aria-describedby="create-tenant-description"
        aria-busy={isSaving}
        onKeyDown={keepFocusInside}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span>Güvenli provisioning</span>
            <h2 id="create-tenant-title">Yeni tenant oluştur</h2>
            <p id="create-tenant-description">
              Tenant sunucu tarafından benzersiz kimlikle ve “Hazırlanıyor”
              durumunda açılır.
            </p>
          </div>
          <button
            type="button"
            aria-label="Yeni tenant penceresini kapat"
            disabled={isSaving}
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <form className={styles.dialogBody} onSubmit={(event) => void submit(event)}>
          {validationError ? (
            <div className={styles.inlineError} role="alert">
              {validationError}
            </div>
          ) : null}
          {error ? (
            <div className={styles.inlineError} role="alert">
              <strong>Tenant oluşturulamadı</strong>
              <span>{error.message}</span>
              {error.reference ? (
                <small>Referans: {error.reference}</small>
              ) : null}
            </div>
          ) : null}

          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>Tenant adı</span>
              <input
                name="name"
                required
                minLength={1}
                maxLength={200}
                autoComplete="organization"
                placeholder="Örn. Acme Türkiye"
                disabled={isSaving}
              />
            </label>
            <label className={styles.field}>
              <span>Tenant kodu</span>
              <input
                name="slug"
                required
                minLength={2}
                maxLength={80}
                pattern="[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?"
                autoCapitalize="none"
                autoCorrect="off"
                placeholder="acme-turkiye"
                aria-describedby="create-slug-help"
                disabled={isSaving}
              />
              <small id="create-slug-help">
                Küçük harf, rakam ve tire; oluşturulduktan sonra değiştirilemez.
              </small>
            </label>
            <label className={styles.field}>
              <span>Plan</span>
              <select name="plan_code" defaultValue="core" disabled={isSaving}>
                <option value="core">{PLATFORM_PLAN_LABELS.core}</option>
                <option value="professional">
                  {PLATFORM_PLAN_LABELS.professional}
                </option>
                <option value="enterprise">
                  {PLATFORM_PLAN_LABELS.enterprise}
                </option>
              </select>
            </label>
            <label className={styles.field}>
              <span>Veri bölgesi</span>
              <select name="data_region" defaultValue="tr-1" disabled={isSaving}>
                <option value="tr-1">{PLATFORM_REGION_LABELS["tr-1"]}</option>
                <option value="eu-1">{PLATFORM_REGION_LABELS["eu-1"]}</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>Dil ve bölge</span>
              <select name="locale" defaultValue="tr-TR" disabled={isSaving}>
                <option value="tr-TR">Türkçe (Türkiye)</option>
                <option value="en-US">English (United States)</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>Saat dilimi</span>
              <input
                name="timezone"
                required
                maxLength={64}
                defaultValue="Europe/Istanbul"
                placeholder="Europe/Istanbul"
                disabled={isSaving}
              />
            </label>
            <label className={styles.field}>
              <span>Tanımlı aktif çalışan limiti</span>
              <input
                name="active_employees"
                type="number"
                inputMode="numeric"
                min={1}
                max={1_000_000}
                step={1}
                placeholder="Opsiyonel"
                aria-describedby="create-limit-help"
                disabled={isSaving}
              />
              <small id="create-limit-help">
                Bu bir ticari metadata limitidir; çalışan kullanımı sayılmaz.
              </small>
            </label>
          </div>

          <footer className={styles.dialogActions}>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isSaving}
              onClick={onClose}
            >
              Vazgeç
            </button>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={isSaving}
            >
              {isSaving ? "Tenant oluşturuluyor…" : "Tenant oluştur"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
