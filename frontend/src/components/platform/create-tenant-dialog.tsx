"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import Link from "next/link";

import { usePlatformOperationSafety } from "@/components/session/platform-operation-safety-provider";
import {
  createPlatformTenant,
  isAmbiguousPlatformMutationOutcome,
  type PlatformResponseMeta,
  type PlatformTenant,
  type PlatformTenantCreateRequest,
  type PlatformTenantErrorPresentation,
  PLATFORM_TENANT_LOCALES,
  PLATFORM_TENANT_PLANS,
  PLATFORM_TENANT_REGIONS,
  isPlatformTenantTimezone,
  platformTenantTimezoneOptions,
  platformTenantErrorPresentation,
  reconcilePlatformTenantCreateBySlug,
} from "@/lib/platform-tenants";

import styles from "./platform-tenant-operations.module.css";
import {
  PLATFORM_PLAN_LABELS,
  PLATFORM_REGION_LABELS,
} from "./platform-tenant-presentation";

const SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+$/;
const UNKNOWN_CREATE_MESSAGE =
  "Tenant oluşturma isteğinin uygulanıp uygulanmadığı doğrulanamadı. Aynı oluşturma isteğini yeniden göndermeyin. Sonucu yeniden doğrulayın veya pencereyi kapatıp platform denetim kaydını inceleyin.";

export function CreateTenantDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (
    tenant: PlatformTenant,
    meta: PlatformResponseMeta,
    source: "response" | "reconciliation",
  ) => void;
}) {
  const operationSafety = usePlatformOperationSafety();
  const resumedUnknownSlug = operationSafety.firstUnknownCreateSlug();
  const dialogRef = useRef<HTMLElement>(null);
  const submitLockRef = useRef(false);
  const outcomeUnknownRef = useRef(resumedUnknownSlug !== null);
  const pendingReconciliationSlugRef = useRef<string | null>(
    resumedUnknownSlug,
  );
  const [isSaving, setIsSaving] = useState(false);
  const [isOutcomeUnknown, setIsOutcomeUnknown] = useState(
    resumedUnknownSlug !== null,
  );
  const [possibleTenant, setPossibleTenant] =
    useState<PlatformTenant | null>(null);
  const [error, setError] =
    useState<PlatformTenantErrorPresentation | null>(
      resumedUnknownSlug
        ? { message: UNKNOWN_CREATE_MESSAGE, reference: null }
        : null,
    );
  const [validationError, setValidationError] = useState<string | null>(null);
  const [timezoneOptions] = useState(() =>
    platformTenantTimezoneOptions(),
  );

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
    return () => {
      window.cancelAnimationFrame(frame);
      if (previouslyFocused?.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, []);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving) {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [isSaving, onClose]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (isSaving) {
        dialog.focus();
      } else if (document.activeElement === dialog) {
        dialog
          .querySelector<HTMLElement>(
            "button:not([disabled]), input:not([disabled]), select:not([disabled])",
          )
          ?.focus();
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isSaving]);

  function keepFocusInside(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled])",
      ),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      event.currentTarget.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (document.activeElement === event.currentTarget) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && document.activeElement === first) {
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

  function markOutcomeUnknown(slug: string, cause: unknown) {
    const presentation = platformTenantErrorPresentation(cause, "");
    operationSafety.markCreateOutcomeUnknown(slug);
    outcomeUnknownRef.current = true;
    setIsOutcomeUnknown(true);
    setError({
      message: UNKNOWN_CREATE_MESSAGE,
      reference: presentation.reference,
    });
  }

  async function reconcileSubmittedSlug(
    slug: string,
  ): Promise<"found" | "absent" | "unknown"> {
    try {
      const reconciliation =
        await reconcilePlatformTenantCreateBySlug(slug);
      if (reconciliation.tenant) {
        operationSafety.markCreateOutcomeUnknown(slug);
        outcomeUnknownRef.current = true;
        setIsOutcomeUnknown(true);
        setPossibleTenant(reconciliation.tenant);
        setError({
          message:
            "Tam tenant listesinde aynı kodla bir kayıt bulundu; ancak bu kayıt bu isteğin sonucu olduğunu kanıtlamaz. Aynı oluşturma isteğini yeniden göndermeyin. Mevcut veya bu istekle oluşmuş olabilecek kaydı tenant ayrıntısı ve platform denetim kaydından doğrulayın.",
          reference: reconciliation.meta.correlation_id,
        });
        return "found";
      }

      outcomeUnknownRef.current = false;
      operationSafety.clearCreateOutcomeUnknown(slug);
      pendingReconciliationSlugRef.current = null;
      setIsOutcomeUnknown(false);
      setPossibleTenant(null);
      setError({
        message:
          "Tam tenant listesi doğrulandı ve bu tenant koduyla bir kayıt bulunamadı. Bilgileriniz korundu; oluşturmayı güvenle yeniden deneyebilirsiniz.",
        reference: reconciliation.meta.correlation_id,
      });
      return "absent";
    } catch (cause) {
      markOutcomeUnknown(slug, cause);
      return "unknown";
    }
  }

  async function retryReconciliation() {
    const slug = pendingReconciliationSlugRef.current;
    if (!slug || isSaving || submitLockRef.current) return;

    submitLockRef.current = true;
    setIsSaving(true);
    setError(null);
    try {
      await reconcileSubmittedSlug(slug);
    } finally {
      submitLockRef.current = false;
      setIsSaving(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      isSaving ||
      submitLockRef.current ||
      outcomeUnknownRef.current ||
      operationSafety.hasUnknownCreateOutcome()
    ) {
      return;
    }

    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const slug = String(form.get("slug") ?? "").trim();
    const initialAdminFullName = String(
      form.get("initial_admin_full_name") ?? "",
    ).trim();
    const initialAdminEmail = String(
      form.get("initial_admin_email") ?? "",
    )
      .trim()
      .toLowerCase();
    const timezone = String(form.get("timezone") ?? "").trim();
    const limitInput = String(form.get("active_employees") ?? "").trim();
    const limit = limitInput ? Number(limitInput) : null;
    const plan = String(form.get("plan_code") ?? "");
    const dataRegion = String(form.get("data_region") ?? "");
    const locale = String(form.get("locale") ?? "");

    let invalidField: { name: string; message: string } | null = null;
    if (name.length < 1 || name.length > 200) {
      invalidField = { name: "name", message: "Tenant adını kontrol edin." };
    } else if (slug.length < 2 || !SLUG_PATTERN.test(slug)) {
      invalidField = {
        name: "slug",
        message:
          "Tenant kodu 2-80 karakter olmalı; yalnız küçük harf, rakam ve tire içermelidir.",
      };
    } else if (
      initialAdminFullName.length < 1 ||
      initialAdminFullName.length > 200
    ) {
      invalidField = {
        name: "initial_admin_full_name",
        message: "İlk yönetici tam adını kontrol edin.",
      };
    } else if (
      initialAdminEmail.length < 3 ||
      initialAdminEmail.length > 320 ||
      !EMAIL_PATTERN.test(initialAdminEmail)
    ) {
      invalidField = {
        name: "initial_admin_email",
        message: "İlk yönetici e-posta adresini kontrol edin.",
      };
    } else if (!isPlatformTenantTimezone(timezone)) {
      invalidField = {
        name: "timezone",
        message: "Geçerli bir saat dilimi seçin.",
      };
    } else if (
      !PLATFORM_TENANT_PLANS.includes(
        plan as PlatformTenantCreateRequest["plan_code"],
      )
    ) {
      invalidField = { name: "plan_code", message: "Geçerli bir plan seçin." };
    } else if (
      !PLATFORM_TENANT_REGIONS.includes(
        dataRegion as PlatformTenantCreateRequest["data_region"],
      )
    ) {
      invalidField = {
        name: "data_region",
        message: "Geçerli bir veri bölgesi seçin.",
      };
    } else if (
      !PLATFORM_TENANT_LOCALES.includes(
        locale as PlatformTenantCreateRequest["locale"],
      )
    ) {
      invalidField = {
        name: "locale",
        message: "Geçerli bir dil ve bölge seçin.",
      };
    } else if (
      limit !== null &&
      (!Number.isSafeInteger(limit) || limit < 1 || limit > 1_000_000)
    ) {
      invalidField = {
        name: "active_employees",
        message:
          "Aktif çalışan limiti 1 ile 1.000.000 arasında bir tam sayı olmalıdır.",
      };
    }

    if (invalidField) {
      setValidationError(invalidField.message);
      const invalidControl = event.currentTarget.elements.namedItem(
        invalidField.name,
      );
      if (invalidControl instanceof HTMLElement) {
        invalidControl.focus();
      }
      return;
    }

    const payload: PlatformTenantCreateRequest = {
      name,
      slug,
      initial_admin: {
        full_name: initialAdminFullName,
        email: initialAdminEmail,
      },
      plan_code: plan as PlatformTenantCreateRequest["plan_code"],
      data_region:
        dataRegion as PlatformTenantCreateRequest["data_region"],
      locale: locale as PlatformTenantCreateRequest["locale"],
      timezone: timezone as PlatformTenantCreateRequest["timezone"],
      ...(limit === null ? {} : { limits: { active_employees: limit } }),
    };

    setValidationError(null);
    setError(null);
    outcomeUnknownRef.current = false;
    pendingReconciliationSlugRef.current = null;
    setIsOutcomeUnknown(false);
    setPossibleTenant(null);
    submitLockRef.current = true;
    setIsSaving(true);
    try {
      const response = await createPlatformTenant(payload);
      onCreated(response.data, response.meta, "response");
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        pendingReconciliationSlugRef.current = payload.slug;
        markOutcomeUnknown(payload.slug, cause);
        await reconcileSubmittedSlug(payload.slug);
      } else {
        setError(
          platformTenantErrorPresentation(
            cause,
            "Tenant şu anda oluşturulamıyor. Bilgileri kontrol edip yeniden deneyin.",
          ),
        );
      }
    } finally {
      submitLockRef.current = false;
      setIsSaving(false);
    }
  }

  return (
    <div
      className={`${styles.dialogBackdrop} ${styles.createDialogBackdrop}`}
      onMouseDown={closeFromBackdrop}
    >
      <section
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-tenant-title"
        aria-describedby="create-tenant-description"
        aria-busy={isSaving}
        tabIndex={-1}
        onKeyDown={keepFocusInside}
      >
        <header className={styles.dialogHeader}>
          <div>
            <span className={styles.dialogEyebrow}>Güvenli provisioning</span>
            <h2 id="create-tenant-title">Yeni tenant oluştur</h2>
            <p id="create-tenant-description">
              Tenant sunucu tarafından benzersiz kimlikle ve “Hazırlanıyor”
              durumunda açılır.
            </p>
          </div>
          <button
            className={styles.dialogCloseButton}
            type="button"
            aria-label="Yeni tenant penceresini kapat"
            disabled={isSaving}
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <form
          className={styles.dialogForm}
          onSubmit={(event) => void submit(event)}
        >
          <div className={styles.dialogBody}>
            {validationError || error ? (
              <div className={styles.dialogFeedback}>
                {validationError ? (
                  <div className={styles.inlineError} role="alert">
                    {validationError}
                  </div>
                ) : null}
                {error ? (
                  <div className={styles.inlineError} role="alert">
                    <strong>
                      {isOutcomeUnknown
                        ? "Tenant oluşturma sonucu doğrulanamadı"
                        : "Tenant oluşturulamadı"}
                    </strong>
                    <span>{error.message}</span>
                    {possibleTenant ? (
                      <>
                        <span>
                          Mevcut veya oluşmuş olabilecek kayıt:{" "}
                          <strong>{possibleTenant.name}</strong> (
                          {possibleTenant.slug})
                        </span>
                        <Link
                          className={styles.secondaryLink}
                          href={`/platform/tenants/${encodeURIComponent(possibleTenant.id)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Bulunan tenantı yeni sekmede incele
                        </Link>
                      </>
                    ) : null}
                    {error.reference ? (
                      <small>Referans: {error.reference}</small>
                    ) : null}
                    {isOutcomeUnknown ? (
                      <button
                        className={styles.secondaryButton}
                        type="button"
                        disabled={isSaving}
                        onClick={() => void retryReconciliation()}
                      >
                        {isSaving
                          ? "Sonuç doğrulanıyor…"
                          : "Sonucu yeniden doğrula"}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className={styles.formSections}>
              <fieldset className={styles.formSection}>
                <legend>Organizasyon bilgileri</legend>
                <p className={styles.formSectionDescription}>
                  Tenantın platformda görünen kimliğini ve kalıcı kodunu
                  tanımlayın.
                </p>
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
                      disabled={isSaving || isOutcomeUnknown}
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
                      disabled={isSaving || isOutcomeUnknown}
                    />
                    <small id="create-slug-help">
                      Küçük harf, rakam ve tire; oluşturulduktan sonra
                      değiştirilemez.
                    </small>
                  </label>
                </div>
              </fieldset>

              <fieldset className={styles.formSection}>
                <legend>İlk yönetici</legend>
                <p className={styles.formSectionDescription}>
                  İlk erişim daveti bu yönetici için hazırlanır.
                </p>
                <div className={styles.formGrid}>
                  <label className={styles.field}>
                    <span>İlk yönetici tam adı</span>
                    <input
                      name="initial_admin_full_name"
                      required
                      minLength={1}
                      maxLength={200}
                      autoComplete="name"
                      placeholder="Örn. Deniz Yönetici"
                      disabled={isSaving || isOutcomeUnknown}
                    />
                  </label>
                  <label className={styles.field}>
                    <span>İlk yönetici e-posta adresi</span>
                    <input
                      name="initial_admin_email"
                      type="email"
                      inputMode="email"
                      required
                      minLength={3}
                      maxLength={320}
                      autoComplete="email"
                      autoCapitalize="none"
                      spellCheck={false}
                      placeholder="deniz.yonetici@ornek.com"
                      disabled={isSaving || isOutcomeUnknown}
                    />
                  </label>
                </div>
              </fieldset>

              <fieldset className={styles.formSection}>
                <legend>Bölgesel ve ticari ayarlar</legend>
                <p className={styles.formSectionDescription}>
                  Plan, veri yerleşimi, yerel saatler ve tanımlı ticari limiti
                  yapılandırın.
                </p>
                <div className={styles.formGrid}>
                  <label className={styles.field}>
                    <span>Plan</span>
                    <select
                      name="plan_code"
                      defaultValue="core"
                      disabled={isSaving || isOutcomeUnknown}
                    >
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
                    <select
                      name="data_region"
                      defaultValue="tr-1"
                      disabled={isSaving || isOutcomeUnknown}
                    >
                      <option value="tr-1">
                        {PLATFORM_REGION_LABELS["tr-1"]}
                      </option>
                      <option value="eu-1">
                        {PLATFORM_REGION_LABELS["eu-1"]}
                      </option>
                    </select>
                  </label>
                  <label className={styles.field}>
                    <span>Dil ve bölge</span>
                    <select
                      name="locale"
                      defaultValue="tr-TR"
                      disabled={isSaving || isOutcomeUnknown}
                    >
                      <option value="tr-TR">Türkçe (Türkiye)</option>
                      <option value="en-US">English (United States)</option>
                    </select>
                  </label>
                  <label className={styles.field}>
                    <span>Saat dilimi</span>
                    <select
                      name="timezone"
                      required
                      defaultValue="Europe/Istanbul"
                      aria-describedby="create-timezone-help"
                      disabled={isSaving || isOutcomeUnknown}
                    >
                      {timezoneOptions.map((tenantTimezone) => (
                        <option value={tenantTimezone} key={tenantTimezone}>
                          {tenantTimezone}
                        </option>
                      ))}
                    </select>
                    <small id="create-timezone-help">
                      Saat dilimi, yerel tarih ve saatlerin nasıl
                      gösterileceğini ve yorumlanacağını belirler.
                    </small>
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
                      disabled={isSaving || isOutcomeUnknown}
                    />
                    <small id="create-limit-help">
                      Bu bir ticari metadata limitidir; çalışan kullanımı
                      sayılmaz.
                    </small>
                  </label>
                </div>
              </fieldset>
            </div>
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
              disabled={isSaving || isOutcomeUnknown}
            >
              {isSaving ? "Tenant oluşturuluyor…" : "Tenant oluştur"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
