"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { usePlatformSession } from "@/components/session/platform-session-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type PlatformResponseMeta,
  type PlatformTenant,
  type PlatformTenantErrorPresentation,
  type PlatformTenantFeature,
  type PlatformTenantStatus,
  type PlatformTenantUpdateRequest,
  PLATFORM_TENANT_LOCALES,
  PLATFORM_TENANT_PLANS,
  PLATFORM_TENANT_REGIONS,
  platformTenantErrorPresentation,
  readPlatformTenant,
  readPlatformTenantFeatures,
  updatePlatformTenant,
  updatePlatformTenantFeatures,
} from "@/lib/platform-tenants";

import { PlatformConfirmationDialog } from "./platform-confirmation-dialog";
import styles from "./platform-tenant-operations.module.css";
import {
  formatPlatformDate,
  isHighImpactStatus,
  PLATFORM_FEATURE_DESCRIPTIONS,
  PLATFORM_FEATURE_LABELS,
  PLATFORM_HEALTH_LABELS,
  PLATFORM_LIFECYCLE_TARGETS,
  PLATFORM_PLAN_LABELS,
  PLATFORM_REGION_LABELS,
  PLATFORM_STATUS_LABELS,
} from "./platform-tenant-presentation";

type PendingConfirmation =
  | { kind: "lifecycle"; target: PlatformTenantStatus }
  | { kind: "feature"; feature: PlatformTenantFeature };

interface OperationSuccess {
  title: string;
  message: string;
  meta: PlatformResponseMeta;
}

export function TenantDetailScreen({ tenantId }: { tenantId: string }) {
  const { user } = usePlatformSession();
  const canUpdateTenant = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.updatePlatformTenants,
  );
  const canReadFeatures = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readPlatformFeatures,
  );
  const canUpdateFeatures =
    canReadFeatures &&
    hasPermission(user, AUTHORIZATION_PERMISSIONS.updatePlatformFeatures);

  const [tenant, setTenant] = useState<PlatformTenant | null>(null);
  const [features, setFeatures] = useState<PlatformTenantFeature[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingFeatures, setIsLoadingFeatures] = useState(canReadFeatures);
  const [detailError, setDetailError] =
    useState<PlatformTenantErrorPresentation | null>(null);
  const [featureError, setFeatureError] =
    useState<PlatformTenantErrorPresentation | null>(null);
  const [operationError, setOperationError] =
    useState<PlatformTenantErrorPresentation | null>(null);
  const [operationSuccess, setOperationSuccess] =
    useState<OperationSuccess | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [featureReloadKey, setFeatureReloadKey] = useState(0);
  const [isMutating, setIsMutating] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<
    PlatformTenantStatus | ""
  >("");
  const [confirmation, setConfirmation] =
    useState<PendingConfirmation | null>(null);

  useEffect(() => {
    let isActive = true;
    void readPlatformTenant(tenantId).then(
      (response) => {
        if (!isActive) return;
        setTenant(response.data);
        setSelectedStatus("");
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setTenant(null);
        setDetailError(
          platformTenantErrorPresentation(
            cause,
            "Tenant ayrıntısı şu anda yüklenemiyor. Yeniden deneyin.",
          ),
        );
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [reloadKey, tenantId]);

  useEffect(() => {
    if (!canReadFeatures) {
      return;
    }

    let isActive = true;
    void Promise.resolve().then(() => {
      if (isActive) {
        setIsLoadingFeatures(true);
        setFeatureError(null);
      }
      return readPlatformTenantFeatures(tenantId);
    }).then(
      (response) => {
        if (!isActive) return;
        setFeatures(response.data.features);
        setIsLoadingFeatures(false);
      },
      (cause) => {
        if (!isActive) return;
        setFeatures([]);
        setFeatureError(
          platformTenantErrorPresentation(
            cause,
            "Modül özellikleri şu anda yüklenemiyor. Yeniden deneyin.",
          ),
        );
        setIsLoadingFeatures(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [canReadFeatures, featureReloadKey, tenantId]);

  const lifecycleTargets = useMemo(
    () => (tenant ? PLATFORM_LIFECYCLE_TARGETS[tenant.status] : []),
    [tenant],
  );
  const metadataMutable =
    canUpdateTenant &&
    tenant !== null &&
    tenant.status !== "offboarding" &&
    tenant.status !== "closed";
  const featuresMutable =
    canUpdateFeatures &&
    tenant !== null &&
    tenant.status !== "offboarding" &&
    tenant.status !== "closed";

  function showOperationError(cause: unknown, fallback: string) {
    setOperationSuccess(null);
    setOperationError(platformTenantErrorPresentation(cause, fallback));
  }

  async function refreshTenantAfterMutation(
    mutationTenant: PlatformTenant,
  ): Promise<void> {
    setTenant(mutationTenant);
    const refreshed = await readPlatformTenant(tenantId);
    setTenant(refreshed.data);
    setSelectedStatus("");
  }

  async function submitMetadata(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenant || !metadataMutable || isMutating) return;

    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const plan = String(form.get("plan_code") ?? tenant.plan_code);
    const dataRegion = String(
      form.get("data_region") ?? tenant.data_region,
    );
    const locale = String(form.get("locale") ?? tenant.locale);
    const timezone = String(form.get("timezone") ?? "").trim();
    const limitInput = String(form.get("active_employees") ?? "").trim();
    const limit = limitInput ? Number(limitInput) : null;
    const update: PlatformTenantUpdateRequest = {};

    if (
      name.length < 1 ||
      name.length > 200 ||
      timezone.length < 1 ||
      timezone.length > 64 ||
      (plan === "premium"
        ? tenant.plan_code !== "premium"
        : !PLATFORM_TENANT_PLANS.includes(
            plan as NonNullable<PlatformTenantUpdateRequest["plan_code"]>,
          )) ||
      !PLATFORM_TENANT_REGIONS.includes(
        dataRegion as NonNullable<
          PlatformTenantUpdateRequest["data_region"]
        >,
      ) ||
      !PLATFORM_TENANT_LOCALES.includes(
        locale as NonNullable<PlatformTenantUpdateRequest["locale"]>,
      ) ||
      (limit !== null &&
        (!Number.isSafeInteger(limit) || limit < 1 || limit > 1_000_000)) ||
      (tenant.limits.active_employees !== null && limit === null)
    ) {
      setOperationSuccess(null);
      setOperationError({
        message:
          "Ad, saat dilimi ve tanımlı çalışan limiti alanlarını kontrol edin. Mevcut limit API üzerinden temizlenemez.",
        reference: null,
      });
      return;
    }

    if (name !== tenant.name) update.name = name;
    if (plan !== tenant.plan_code) {
      update.plan_code = plan as NonNullable<
        PlatformTenantUpdateRequest["plan_code"]
      >;
    }
    if (dataRegion !== tenant.data_region) {
      update.data_region = dataRegion as NonNullable<
        PlatformTenantUpdateRequest["data_region"]
      >;
    }
    if (locale !== tenant.locale) {
      update.locale = locale as NonNullable<
        PlatformTenantUpdateRequest["locale"]
      >;
    }
    if (timezone !== tenant.timezone) update.timezone = timezone;
    if (limit !== null && limit !== tenant.limits.active_employees) {
      update.limits = { active_employees: limit };
    }

    if (Object.keys(update).length === 0) {
      setOperationSuccess(null);
      setOperationError({
        message: "Kaydedilecek bir değişiklik bulunamadı.",
        reference: null,
      });
      return;
    }

    setIsMutating(true);
    setOperationError(null);
    setOperationSuccess(null);
    try {
      const response = await updatePlatformTenant(tenantId, update);
      await refreshTenantAfterMutation(response.data);
      setOperationSuccess({
        title: "Tenant ayarları güncellendi",
        message: "Güncel metadata sunucudan yeniden doğrulandı.",
        meta: response.meta,
      });
    } catch (cause) {
      showOperationError(
        cause,
        "Tenant ayarları şu anda güncellenemiyor. Veriyi yenileyip yeniden deneyin.",
      );
    } finally {
      setIsMutating(false);
    }
  }

  async function confirmLifecycle(target: PlatformTenantStatus) {
    if (!tenant || !canUpdateTenant || isMutating) return;
    setIsMutating(true);
    setOperationError(null);
    setOperationSuccess(null);
    try {
      const response = await updatePlatformTenant(tenantId, {
        status: target,
      });
      await refreshTenantAfterMutation(response.data);
      setOperationSuccess({
        title: "Yaşam döngüsü güncellendi",
        message: `${tenant.name} artık “${PLATFORM_STATUS_LABELS[target]}” durumunda.`,
        meta: response.meta,
      });
      setConfirmation(null);
    } catch (cause) {
      showOperationError(
        cause,
        "Yaşam döngüsü değiştirilemedi. Tenant durumunu yenileyip yeniden deneyin.",
      );
    } finally {
      setIsMutating(false);
    }
  }

  async function confirmFeature(feature: PlatformTenantFeature) {
    if (!tenant || !featuresMutable || isMutating) return;
    const targetEnabled = !feature.enabled;
    setIsMutating(true);
    setOperationError(null);
    setOperationSuccess(null);
    try {
      const response = await updatePlatformTenantFeatures(tenantId, [
        { key: feature.key, enabled: targetEnabled },
      ]);
      setFeatures(response.data.features);
      const refreshed = await readPlatformTenantFeatures(tenantId);
      setFeatures(refreshed.data.features);
      setOperationSuccess({
        title: "Modül özelliği güncellendi",
        message: `${PLATFORM_FEATURE_LABELS[feature.key]} ${
          targetEnabled ? "etkinleştirildi" : "devre dışı bırakıldı"
        } ve sunucudan yeniden doğrulandı.`,
        meta: response.meta,
      });
      setConfirmation(null);
    } catch (cause) {
      showOperationError(
        cause,
        "Modül özelliği güncellenemedi. Güncel tenant durumunu kontrol edip yeniden deneyin.",
      );
    } finally {
      setIsMutating(false);
    }
  }

  if (isLoading) {
    return (
      <section className={styles.page} aria-labelledby="tenant-detail-loading">
        <div className={styles.loadingState} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <strong id="tenant-detail-loading">Tenant ayrıntısı yükleniyor</strong>
          <p>Yalnız platform için güvenli metadata hazırlanıyor…</p>
        </div>
      </section>
    );
  }

  if (detailError || !tenant) {
    return (
      <section className={styles.page} aria-labelledby="tenant-detail-error">
        <Link className={styles.backLink} href="/platform/tenants">
          ← Tenant yönetimine dön
        </Link>
        <div className={styles.errorState} role="alert">
          <div>
            <strong id="tenant-detail-error">Tenant ayrıntısı yüklenemedi</strong>
            <p>{detailError?.message ?? "Tenant bulunamadı."}</p>
            {detailError?.reference ? (
              <small>Referans: {detailError.reference}</small>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => {
              setIsLoading(true);
              setDetailError(null);
              setReloadKey((key) => key + 1);
            }}
          >
            Yeniden dene
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className={styles.page}
      aria-labelledby="tenant-detail-title"
      aria-busy={isMutating}
    >
      <Link className={styles.backLink} href="/platform/tenants">
        ← Tenant yönetimine dön
      </Link>

      <header className={styles.detailHeader}>
        <div>
          <span>Tenant ayrıntısı</span>
          <h1 id="tenant-detail-title">{tenant.name}</h1>
          <p>{tenant.slug}</p>
        </div>
        <span className={styles.statusBadge} data-status={tenant.status}>
          {PLATFORM_STATUS_LABELS[tenant.status]}
        </span>
      </header>

      {operationSuccess ? (
        <div className={styles.successNotice} role="status" aria-live="polite">
          <div>
            <strong>{operationSuccess.title}</strong>
            <p>{operationSuccess.message}</p>
            <small>
              Referans: {operationSuccess.meta.correlation_id}
            </small>
          </div>
          <button
            type="button"
            aria-label="Başarı bildirimini kapat"
            onClick={() => setOperationSuccess(null)}
          >
            ×
          </button>
        </div>
      ) : null}

      {operationError ? (
        <div className={styles.operationAlert} role="alert">
          <strong>İşlem tamamlanamadı</strong>
          <span>{operationError.message}</span>
          {operationError.reference ? (
            <small>Referans: {operationError.reference}</small>
          ) : null}
        </div>
      ) : null}

      <section
        className={styles.detailCard}
        aria-labelledby="safe-metadata-title"
      >
        <div className={styles.cardHeader}>
          <div>
            <span>Salt güvenli projeksiyon</span>
            <h2 id="safe-metadata-title">Tenant metadata’sı</h2>
          </div>
          <button
            className={styles.refreshButton}
            type="button"
            disabled={isMutating}
            onClick={() => {
              setIsLoading(true);
              setDetailError(null);
              setReloadKey((key) => key + 1);
            }}
          >
            Yenile
          </button>
        </div>
        <dl className={styles.metadataGrid}>
          <div>
            <dt>Tenant kimliği</dt>
            <dd className={styles.monospace}>{tenant.id}</dd>
          </div>
          <div>
            <dt>Sağlık</dt>
            <dd>{PLATFORM_HEALTH_LABELS[tenant.health]}</dd>
          </div>
          <div>
            <dt>Plan</dt>
            <dd>{PLATFORM_PLAN_LABELS[tenant.plan_code]}</dd>
          </div>
          <div>
            <dt>Veri bölgesi</dt>
            <dd>{PLATFORM_REGION_LABELS[tenant.data_region]}</dd>
          </div>
          <div>
            <dt>Dil ve bölge</dt>
            <dd>{tenant.locale}</dd>
          </div>
          <div>
            <dt>Saat dilimi</dt>
            <dd>{tenant.timezone}</dd>
          </div>
          <div>
            <dt>Tanımlı aktif çalışan limiti</dt>
            <dd>
              {tenant.limits.active_employees?.toLocaleString("tr-TR") ??
                "Tanımlı değil"}
            </dd>
          </div>
          <div>
            <dt>Oluşturuldu</dt>
            <dd>
              <time dateTime={tenant.created_at}>
                {formatPlatformDate(tenant.created_at)}
              </time>
            </dd>
          </div>
          <div>
            <dt>Son güncelleme</dt>
            <dd>
              <time dateTime={tenant.updated_at}>
                {formatPlatformDate(tenant.updated_at)}
              </time>
            </dd>
          </div>
        </dl>
      </section>

      <div className={styles.operationGrid}>
        <section className={styles.formCard} aria-labelledby="settings-title">
          <div className={styles.cardHeader}>
            <div>
              <span>Allowlist ayarlar</span>
              <h2 id="settings-title">Tenant ayarları</h2>
            </div>
          </div>
          {metadataMutable ? (
            <form
              className={styles.settingsForm}
              key={tenant.updated_at}
              onSubmit={(event) => void submitMetadata(event)}
            >
              <fieldset disabled={isMutating}>
                <label className={styles.field}>
                  <span>Tenant adı</span>
                  <input
                    name="name"
                    required
                    minLength={1}
                    maxLength={200}
                    defaultValue={tenant.name}
                  />
                </label>
                <label className={styles.field}>
                  <span>Plan</span>
                  <select name="plan_code" defaultValue={tenant.plan_code}>
                    {tenant.plan_code === "premium" ? (
                      <option value="premium" disabled>
                        {PLATFORM_PLAN_LABELS.premium}
                      </option>
                    ) : null}
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
                    defaultValue={tenant.data_region}
                    disabled={tenant.status !== "provisioning" || isMutating}
                  >
                    <option value="tr-1">
                      {PLATFORM_REGION_LABELS["tr-1"]}
                    </option>
                    <option value="eu-1">
                      {PLATFORM_REGION_LABELS["eu-1"]}
                    </option>
                  </select>
                  <small>
                    Yalnız tenant hazırlanırken değiştirilebilir.
                  </small>
                </label>
                <label className={styles.field}>
                  <span>Dil ve bölge</span>
                  <select name="locale" defaultValue={tenant.locale}>
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
                    defaultValue={tenant.timezone}
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
                    defaultValue={tenant.limits.active_employees ?? ""}
                  />
                  <small>
                    Kullanım sayacı değildir; mevcut bir limit boş bırakılamaz.
                  </small>
                </label>
              </fieldset>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={isMutating}
              >
                {isMutating ? "Kaydediliyor…" : "Ayarları kaydet"}
              </button>
            </form>
          ) : (
            <div className={styles.cardNotice}>
              <strong>
                {canUpdateTenant
                  ? "Bu yaşam döngüsünde metadata değiştirilemez"
                  : "Güncelleme yetkiniz yok"}
              </strong>
              <p>
                {canUpdateTenant
                  ? "Kapatma sürecindeki veya kapalı tenantlar backend politikası gereği salt okunurdur."
                  : "Tenant metadata’sı yalnız tenant güncelleme iznine sahip platform rolleri tarafından değiştirilebilir."}
              </p>
            </div>
          )}
        </section>

        <section className={styles.formCard} aria-labelledby="lifecycle-title">
          <div className={styles.cardHeader}>
            <div>
              <span>Kontrollü geçiş</span>
              <h2 id="lifecycle-title">Yaşam döngüsü</h2>
            </div>
          </div>
          {!canUpdateTenant ? (
            <div className={styles.cardNotice}>
              <strong>Yaşam döngüsü güncelleme yetkiniz yok</strong>
              <p>Geçiş kontrolleri varsayılan olarak kapalı tutulur.</p>
            </div>
          ) : lifecycleTargets.length === 0 ? (
            <div className={styles.cardNotice}>
              <strong>Kapalı tenant terminal durumdadır</strong>
              <p>Backend yaşam döngüsü kapalı durumdan yeni bir geçiş sunmaz.</p>
            </div>
          ) : (
            <div className={styles.lifecycleBody}>
              <p>
                Mevcut durum:{" "}
                <strong>{PLATFORM_STATUS_LABELS[tenant.status]}</strong>
              </p>
              <label className={styles.field}>
                <span>Yeni yaşam döngüsü durumu</span>
                <select
                  value={selectedStatus}
                  disabled={isMutating}
                  onChange={(event) =>
                    setSelectedStatus(
                      event.target.value as PlatformTenantStatus | "",
                    )
                  }
                >
                  <option value="">Geçerli bir durum seçin</option>
                  {lifecycleTargets.map((target) => (
                    <option value={target} key={target}>
                      {PLATFORM_STATUS_LABELS[target]}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={
                  selectedStatus && isHighImpactStatus(selectedStatus)
                    ? styles.dangerButton
                    : styles.primaryButton
                }
                type="button"
                disabled={!selectedStatus || isMutating}
                onClick={() => {
                  if (selectedStatus) {
                    setConfirmation({
                      kind: "lifecycle",
                      target: selectedStatus,
                    });
                  }
                }}
              >
                Geçişi incele
              </button>
            </div>
          )}
        </section>
      </div>

      <section className={styles.featureCard} aria-labelledby="features-title">
        <div className={styles.cardHeader}>
          <div>
            <span>Modül dağıtımı</span>
            <h2 id="features-title">Feature flag’ler</h2>
          </div>
          {canReadFeatures ? (
            <button
              className={styles.refreshButton}
              type="button"
              disabled={isLoadingFeatures || isMutating}
              onClick={() => setFeatureReloadKey((key) => key + 1)}
            >
              Yenile
            </button>
          ) : null}
        </div>

        {!canReadFeatures ? (
          <div className={styles.cardNotice}>
            <strong>Modül özelliklerini okuma yetkiniz yok</strong>
            <p>
              Feature metadata’sı yalnız açık feature okuma izniyle yüklenir.
            </p>
          </div>
        ) : featureError ? (
          <div className={styles.cardNotice} role="alert">
            <strong>Modül özellikleri yüklenemedi</strong>
            <p>{featureError.message}</p>
            {featureError.reference ? (
              <small>Referans: {featureError.reference}</small>
            ) : null}
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={() => setFeatureReloadKey((key) => key + 1)}
            >
              Yeniden dene
            </button>
          </div>
        ) : isLoadingFeatures ? (
          <div className={styles.cardNotice} role="status" aria-live="polite">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Modül özellikleri yükleniyor</strong>
          </div>
        ) : (
          <div className={styles.featureList}>
            {features.map((feature) => (
              <article key={feature.key}>
                <div>
                  <strong>{PLATFORM_FEATURE_LABELS[feature.key]}</strong>
                  <p>{PLATFORM_FEATURE_DESCRIPTIONS[feature.key]}</p>
                  <small>
                    Kaynak:{" "}
                    {feature.source === "default"
                      ? "Platform varsayılanı"
                      : "Tenant override"}
                  </small>
                </div>
                <div className={styles.featureAction}>
                  <span data-enabled={feature.enabled}>
                    {feature.enabled ? "Etkin" : "Devre dışı"}
                  </span>
                  {canUpdateFeatures ? (
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      disabled={!featuresMutable || isMutating}
                      aria-label={`${PLATFORM_FEATURE_LABELS[feature.key]} özelliğini ${
                        feature.enabled
                          ? "devre dışı bırak"
                          : "etkinleştir"
                      }`}
                      onClick={() =>
                        setConfirmation({ kind: "feature", feature })
                      }
                    >
                      {feature.enabled ? "Devre dışı bırak" : "Etkinleştir"}
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <aside className={styles.securityBoundary} aria-label="Tenant veri sınırı">
        <span aria-hidden="true">✓</span>
        <div>
          <strong>Müşteri HR verisi bu ekrana yüklenmez</strong>
          <p>
            Tenant kimliği path üzerinde yalnız kaynak seçer; tenant
            impersonation, tenant-scoped token veya çalışan endpoint’i
            kullanılmaz.
          </p>
        </div>
      </aside>

      {confirmation ? (
        <PlatformConfirmationDialog
          title={
            confirmation.kind === "lifecycle"
              ? `${PLATFORM_STATUS_LABELS[confirmation.target]} durumuna geçir`
              : `${PLATFORM_FEATURE_LABELS[confirmation.feature.key]} özelliğini ${
                  confirmation.feature.enabled
                    ? "devre dışı bırak"
                    : "etkinleştir"
                }`
          }
          description={
            confirmation.kind === "lifecycle" ? (
              <p>
                <strong>{tenant.name}</strong> için yalnız backend’in izin
                verdiği yaşam döngüsü geçişi uygulanacak. Özellikle askıya alma
                ve kapatma akışları tenant erişimini kısıtlayabilir.
              </p>
            ) : (
              <p>
                Bu değişiklik tenantın{" "}
                <strong>
                  {PLATFORM_FEATURE_LABELS[confirmation.feature.key]}
                </strong>{" "}
                modül erişimini doğrudan etkiler.
              </p>
            )
          }
          confirmLabel="Değişikliği uygula"
          busyLabel="Değişiklik uygulanıyor…"
          danger={
            confirmation.kind === "lifecycle"
              ? isHighImpactStatus(confirmation.target)
              : confirmation.feature.enabled
          }
          isBusy={isMutating}
          onCancel={() => {
            if (!isMutating) setConfirmation(null);
          }}
          onConfirm={() => {
            if (confirmation.kind === "lifecycle") {
              void confirmLifecycle(confirmation.target);
            } else {
              void confirmFeature(confirmation.feature);
            }
          }}
        />
      ) : null}
    </section>
  );
}
