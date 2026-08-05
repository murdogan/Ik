"use client";

import Link from "next/link";
import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { usePlatformSession } from "@/components/session/platform-session-provider";
import {
  type UnknownPlatformTenantMutationKind,
  usePlatformOperationSafety,
} from "@/components/session/platform-operation-safety-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type PlatformResponseMeta,
  type PlatformTenant,
  type PlatformTenantErrorPresentation,
  type PlatformTenantFeature,
  type PlatformTenantInitialAdminCorrectionRequest,
  type PlatformTenantInitialAdminManualLinkRead,
  type PlatformTenantStatus,
  type PlatformTenantUpdateRequest,
  PLATFORM_TENANT_LOCALES,
  PLATFORM_TENANT_PLANS,
  PLATFORM_TENANT_REGIONS,
  isAmbiguousPlatformMutationOutcome,
  isPlatformTenantTimezone,
  platformTenantTimezoneOptions,
  platformTenantErrorPresentation,
  correctPlatformTenantInitialAdminInvitation,
  createPlatformTenantInitialAdminManualLink,
  readPlatformTenant,
  readPlatformTenantFeatures,
  resendPlatformTenantInitialAdminInvitation,
  updatePlatformTenant,
  updatePlatformTenantFeatures,
} from "@/lib/platform-tenants";

import { InitialAdminCorrectionDialog } from "./initial-admin-correction-dialog";
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
  | { kind: "feature"; feature: PlatformTenantFeature }
  | { kind: "initial_admin_resend" }
  | { kind: "initial_admin_manual_link" }
  | { kind: "initial_admin_correction" };

const INITIAL_ADMIN_ELIGIBLE_STATUSES: readonly PlatformTenantStatus[] = [
  "provisioning",
  "trial",
  "active",
];

function isInitialAdminActionEligible(
  status: PlatformTenantStatus,
): boolean {
  return INITIAL_ADMIN_ELIGIBLE_STATUSES.includes(status);
}

interface OperationNotice {
  tone: "success" | "warning";
  title: string;
  message: string;
  meta: PlatformResponseMeta;
}

function tenantMatchesUpdate(
  tenant: PlatformTenant,
  update: PlatformTenantUpdateRequest,
): boolean {
  return (
    (!Object.hasOwn(update, "name") || tenant.name === update.name) &&
    (!Object.hasOwn(update, "status") || tenant.status === update.status) &&
    (!Object.hasOwn(update, "plan_code") ||
      tenant.plan_code === update.plan_code) &&
    (!Object.hasOwn(update, "data_region") ||
      tenant.data_region === update.data_region) &&
    (!Object.hasOwn(update, "locale") || tenant.locale === update.locale) &&
    (!Object.hasOwn(update, "timezone") ||
      tenant.timezone === update.timezone) &&
    (!Object.hasOwn(update, "limits") ||
      tenant.limits.active_employees === update.limits?.active_employees)
  );
}

function lifecycleTargetIsAuthoritativelyCommitted(
  status: PlatformTenantStatus,
  target: PlatformTenantStatus,
): boolean {
  return status === target || (target === "offboarding" && status === "closed");
}

export function TenantDetailScreen({ tenantId }: { tenantId: string }) {
  const { user } = usePlatformSession();
  const {
    clearFeatureOutcomeUnknown,
    clearInitialAdminOutcomeUnknown,
    clearTenantMutationUnknown,
    featureOutcomeEpoch,
    hasUnknownFeatureOutcome,
    hasUnknownInitialAdminOutcome,
    initialAdminOutcomeEpoch,
    markFeatureOutcomeUnknown,
    markInitialAdminOutcomeUnknown,
    markTenantMutationUnknown,
    tenantMutationOutcomeEpoch,
    unknownTenantMutationKind,
  } = usePlatformOperationSafety();
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
  const [operationNotice, setOperationNotice] =
    useState<OperationNotice | null>(null);
  const [manualLinkResult, setManualLinkResult] =
    useState<PlatformTenantInitialAdminManualLinkRead | null>(null);
  const [manualLinkCopyStatus, setManualLinkCopyStatus] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [featureReloadKey, setFeatureReloadKey] = useState(0);
  const [isMutating, setIsMutating] = useState(false);
  const [pendingTenantCommitRefreshes, setPendingTenantCommitRefreshes] =
    useState(0);
  const [pendingFeatureCommitRefreshes, setPendingFeatureCommitRefreshes] =
    useState(0);
  const [selectedStatus, setSelectedStatus] = useState<
    PlatformTenantStatus | ""
  >("");
  const [confirmation, setConfirmation] =
    useState<PendingConfirmation | null>(null);
  const mutationLockRef = useRef(false);
  const mutationGenerationRef = useRef(0);
  const manualLinkStateEpochRef = useRef(0);
  const manualLinkResultRef = useRef<HTMLDivElement>(null);
  const manualLinkTriggerRef = useRef<HTMLButtonElement>(null);
  const operationErrorRef = useRef<HTMLDivElement>(null);
  const lifecycleSelectRef = useRef<HTMLSelectElement>(null);
  const initialAdminActionsEligible =
    tenant !== null && isInitialAdminActionEligible(tenant.status);
  const isInitialAdminOutcomeUnknown =
    hasUnknownInitialAdminOutcome(tenantId);
  const activeUnknownTenantMutationKind =
    unknownTenantMutationKind(tenantId);
  const isTenantMutationOutcomeUnknown =
    activeUnknownTenantMutationKind !== null;
  const isFeatureMutationOutcomeUnknown =
    hasUnknownFeatureOutcome();
  const confirmationIsAuthorized = (() => {
    if (!confirmation) return false;
    if (confirmation.kind === "lifecycle") return canUpdateTenant;
    if (confirmation.kind === "feature") return canUpdateFeatures;
    return canUpdateTenant && initialAdminActionsEligible;
  })();

  useEffect(() => {
    let isActive = true;
    queueMicrotask(() => {
      if (!isActive) return;
      setConfirmation((current) => {
        if (
          (current?.kind === "lifecycle" && !canUpdateTenant) ||
          (current?.kind === "feature" && !canUpdateFeatures)
        ) {
          return null;
        }
        if (
          (current?.kind === "initial_admin_resend" ||
            current?.kind === "initial_admin_manual_link" ||
            current?.kind === "initial_admin_correction") &&
          (!canUpdateTenant || !initialAdminActionsEligible)
        ) {
          return null;
        }
        return current;
      });
      if (!canUpdateTenant || !initialAdminActionsEligible) {
        manualLinkStateEpochRef.current += 1;
        setManualLinkResult(null);
        setManualLinkCopyStatus("");
      }
    });
    return () => {
      isActive = false;
    };
  }, [
    canUpdateFeatures,
    canUpdateTenant,
    initialAdminActionsEligible,
  ]);

  useEffect(() => {
    let isActive = true;
    queueMicrotask(() => {
      if (!isActive) return;
      setConfirmation(null);
      setOperationError(null);
      manualLinkStateEpochRef.current += 1;
      setManualLinkResult(null);
      setManualLinkCopyStatus("");
    });
    return () => {
      isActive = false;
    };
  }, [tenantId]);

  useEffect(() => {
    if (!operationError || confirmation || isMutating) return;
    const frame = window.requestAnimationFrame(() => {
      operationErrorRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [confirmation, isMutating, operationError]);

  useEffect(() => {
    if (!manualLinkResult) return;
    const frame = window.requestAnimationFrame(() => {
      manualLinkResultRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [manualLinkResult]);

  function acquireMutationLock(): boolean {
    if (mutationLockRef.current) return false;
    mutationLockRef.current = true;
    mutationGenerationRef.current += 1;
    setIsMutating(true);
    return true;
  }

  function releaseMutationLock() {
    mutationLockRef.current = false;
    setIsMutating(false);
  }

  function clearManualLinkResult({
    restoreFocus = false,
  }: { restoreFocus?: boolean } = {}): number {
    manualLinkStateEpochRef.current += 1;
    setManualLinkResult(null);
    setManualLinkCopyStatus("");
    if (restoreFocus) {
      window.requestAnimationFrame(() => {
        manualLinkTriggerRef.current?.focus();
      });
    }
    return manualLinkStateEpochRef.current;
  }

  function beginTenantCommitRefresh() {
    setPendingTenantCommitRefreshes((count) => count + 1);
  }

  function endTenantCommitRefresh() {
    setPendingTenantCommitRefreshes((count) => Math.max(0, count - 1));
  }

  function beginFeatureCommitRefresh() {
    setPendingFeatureCommitRefreshes((count) => count + 1);
  }

  function endFeatureCommitRefresh() {
    setPendingFeatureCommitRefreshes((count) => Math.max(0, count - 1));
  }

  function openConfirmation(next: PendingConfirmation) {
    if (mutationLockRef.current) return;
    if (
      (next.kind === "initial_admin_resend" ||
        next.kind === "initial_admin_manual_link" ||
        next.kind === "initial_admin_correction") &&
      hasUnknownInitialAdminOutcome(tenantId)
    ) {
      return;
    }
    if (
      next.kind === "lifecycle" &&
      unknownTenantMutationKind(tenantId) !== null
    ) {
      return;
    }
    if (
      next.kind === "feature" &&
      hasUnknownFeatureOutcome()
    ) {
      return;
    }
    setOperationError(null);
    setConfirmation(next);
  }

  function closeConfirmation() {
    if (mutationLockRef.current) return;
    setConfirmation(null);
    if (
      !hasUnknownInitialAdminOutcome(tenantId) &&
      unknownTenantMutationKind(tenantId) === null &&
      !hasUnknownFeatureOutcome()
    ) {
      setOperationError(null);
    }
  }

  useEffect(() => {
    let isActive = true;
    const initialAdminEpochAtDispatch = initialAdminOutcomeEpoch(tenantId);
    const tenantMutationEpochAtDispatch = tenantMutationOutcomeEpoch(tenantId);
    void readPlatformTenant(tenantId).then(
      (response) => {
        if (!isActive) return;
        setTenant(response.data);
        setSelectedStatus("");
        if (initialAdminEpochAtDispatch !== null) {
          clearInitialAdminOutcomeUnknown(
            tenantId,
            initialAdminEpochAtDispatch,
          );
        }
        if (tenantMutationEpochAtDispatch !== null) {
          clearTenantMutationUnknown(tenantId, tenantMutationEpochAtDispatch);
        }
        if (
          initialAdminOutcomeEpoch(tenantId) === null &&
          tenantMutationOutcomeEpoch(tenantId) === null &&
          featureOutcomeEpoch(tenantId) === null
        ) {
          setOperationError(null);
        }
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
  }, [
    clearInitialAdminOutcomeUnknown,
    clearTenantMutationUnknown,
    featureOutcomeEpoch,
    initialAdminOutcomeEpoch,
    reloadKey,
    tenantId,
    tenantMutationOutcomeEpoch,
  ]);

  useEffect(() => {
    if (!canReadFeatures) {
      return;
    }

    let isActive = true;
    const featureEpochAtDispatch = featureOutcomeEpoch(tenantId);
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
        if (featureEpochAtDispatch !== null) {
          clearFeatureOutcomeUnknown(tenantId, featureEpochAtDispatch);
        }
        if (
          initialAdminOutcomeEpoch(tenantId) === null &&
          tenantMutationOutcomeEpoch(tenantId) === null &&
          featureOutcomeEpoch(tenantId) === null
        ) {
          setOperationError(null);
        }
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
  }, [
    canReadFeatures,
    clearFeatureOutcomeUnknown,
    featureOutcomeEpoch,
    featureReloadKey,
    initialAdminOutcomeEpoch,
    tenantId,
    tenantMutationOutcomeEpoch,
  ]);

  const lifecycleTargets = useMemo(
    () => (tenant ? PLATFORM_LIFECYCLE_TARGETS[tenant.status] : []),
    [tenant],
  );
  const hasHighImpactLifecycleTarget = lifecycleTargets.some((target) =>
    isHighImpactStatus(target),
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
    tenant.status !== "closed" &&
    !isFeatureMutationOutcomeUnknown;
  const timezoneOptions = useMemo(
    () => platformTenantTimezoneOptions(tenant?.timezone),
    [tenant?.timezone],
  );

  function showOperationError(cause: unknown, fallback: string) {
    setOperationNotice(null);
    setOperationError(platformTenantErrorPresentation(cause, fallback));
  }

  function showUnknownInitialAdminOutcome(cause: unknown) {
    const presentation = platformTenantErrorPresentation(cause, "");
    markInitialAdminOutcomeUnknown(tenantId);
    setOperationNotice(null);
    setOperationError({
      message:
        "Yeni bir davet zaten hazırlanmış olabilir; bu pencerede işlemi yeniden göndermek hazırlanmış olabilecek yeni bağlantıyı da geçersiz kılabilir. Başka bir işlem yapmadan önce platform denetim kaydını inceleyin ve sayfayı yenileyin.",
      reference: presentation.reference,
    });
  }

  function markTenantMutationOutcomeUnknown(
    kind: UnknownPlatformTenantMutationKind,
    mutationCause: unknown,
    reconciliationCause: unknown,
  ) {
    const mutationPresentation = platformTenantErrorPresentation(
      mutationCause,
      "",
    );
    const reconciliationPresentation = platformTenantErrorPresentation(
      reconciliationCause,
      "",
    );
    markTenantMutationUnknown(tenantId, kind);
    setOperationNotice(null);
    setConfirmation(null);
    setOperationError({
      message:
        "Değişikliğin uygulanıp uygulanmadığı güvenilir biçimde doğrulanamadı. Çakışan tenant ayarları ve yaşam döngüsü işlemleri kilitlendi. Güncel tenant ayrıntısını Yenile ile doğrulayın.",
      reference:
        mutationPresentation.reference ?? reconciliationPresentation.reference,
    });
  }

  function markFeatureMutationOutcomeUnknown(
    feature: PlatformTenantFeature,
    mutationCause: unknown,
    reconciliationCause: unknown,
  ) {
    const mutationPresentation = platformTenantErrorPresentation(
      mutationCause,
      "",
    );
    const reconciliationPresentation = platformTenantErrorPresentation(
      reconciliationCause,
      "",
    );
    markFeatureOutcomeUnknown(tenantId);
    setOperationNotice(null);
    setConfirmation(null);
    setOperationError({
      message: `${PLATFORM_FEATURE_LABELS[feature.key]} değişikliğinin sonucu doğrulanamadı. Tüm feature değişiklikleri, sunucudan eksiksiz ve doğrulanmış güncel feature verisi alınana kadar kilitlendi.`,
      reference:
        mutationPresentation.reference ?? reconciliationPresentation.reference,
    });
  }

  function showReconciledCommitted(
    title: string,
    message: string,
    meta: PlatformResponseMeta,
  ) {
    setOperationError(null);
    setOperationNotice({
      tone: "success",
      title,
      message,
      meta,
    });
  }

  function showReconciledNotApplied(
    cause: unknown,
    message: string,
  ) {
    const presentation = platformTenantErrorPresentation(cause, "");
    setOperationNotice(null);
    setOperationError({
      message,
      reference: presentation.reference,
    });
  }

  function showCommittedRefreshWarning(
    meta: PlatformResponseMeta,
  ): void {
    setOperationError(null);
    setOperationNotice({
      tone: "warning",
      title: "İşlem uygulandı, güncel görünüm alınamadı",
      message:
        "Değişiklik sunucuda uygulandı. Uygulanan sonuç ekranda korunuyor; güncel görünümü daha sonra Yenile ile alabilirsiniz.",
      meta,
    });
  }

  async function submitMetadata(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !tenant ||
      !metadataMutable ||
      unknownTenantMutationKind(tenantId) !== null ||
      mutationLockRef.current
    ) {
      return;
    }

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
      (!isPlatformTenantTimezone(timezone) &&
        timezone !== tenant.timezone) ||
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
      setOperationNotice(null);
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
      setOperationNotice(null);
      setOperationError({
        message: "Kaydedilecek bir değişiklik bulunamadı.",
        reference: null,
      });
      return;
    }

    if (!acquireMutationLock()) return;
    clearManualLinkResult();
    const mutationGeneration = mutationGenerationRef.current;
    setOperationError(null);
    setOperationNotice(null);
    let response: Awaited<ReturnType<typeof updatePlatformTenant>>;
    try {
      response = await updatePlatformTenant(tenantId, update);
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        try {
          const reconciled = await readPlatformTenant(tenantId);
          if (mutationGenerationRef.current !== mutationGeneration) {
            releaseMutationLock();
            return;
          }
          setTenant(reconciled.data);
          setSelectedStatus("");
          if (tenantMatchesUpdate(reconciled.data, update)) {
            setConfirmation(null);
            showReconciledCommitted(
              "Tenant ayarları güncellendi",
              "Mutation yanıtı doğrulanamadı; istenen metadata güncel tenant ayrıntısından doğrulandı.",
              reconciled.meta,
            );
          } else {
            showReconciledNotApplied(
              cause,
              "İstenen değişiklik sunucuda görülmedi. Güncel tenant ayrıntısı yüklendi; değerleri inceleyip işlemi bilinçli olarak yeniden deneyebilirsiniz.",
            );
          }
        } catch (reconciliationCause) {
          markTenantMutationOutcomeUnknown(
            "metadata",
            cause,
            reconciliationCause,
          );
        }
        releaseMutationLock();
        return;
      }
      showOperationError(
        cause,
        "Tenant ayarları şu anda güncellenemiyor. Veriyi yenileyip yeniden deneyin.",
      );
      releaseMutationLock();
      return;
    }

    setTenant(response.data);
    setSelectedStatus("");
    setConfirmation(null);
    setOperationNotice({
      tone: "success",
      title: "Tenant ayarları güncellendi",
      message:
        "Değişiklik sunucuda uygulandı; güncel görünüm yeniden doğrulanıyor.",
      meta: response.meta,
    });
    beginTenantCommitRefresh();
    releaseMutationLock();

    try {
      const refreshed = await readPlatformTenant(tenantId);
      if (mutationGenerationRef.current === mutationGeneration) {
        setTenant(refreshed.data);
        setOperationNotice({
          tone: "success",
          title: "Tenant ayarları güncellendi",
          message: "Güncel metadata sunucudan yeniden doğrulandı.",
          meta: response.meta,
        });
      }
    } catch {
      if (mutationGenerationRef.current === mutationGeneration) {
        showCommittedRefreshWarning(response.meta);
      }
    } finally {
      endTenantCommitRefresh();
    }
  }

  async function confirmLifecycle(target: PlatformTenantStatus) {
    if (
      !tenant ||
      !canUpdateTenant ||
      unknownTenantMutationKind(tenantId) !== null ||
      !acquireMutationLock()
    ) {
      return;
    }
    clearManualLinkResult();
    const mutationGeneration = mutationGenerationRef.current;
    setOperationError(null);
    setOperationNotice(null);
    let response: Awaited<ReturnType<typeof updatePlatformTenant>>;
    try {
      response = await updatePlatformTenant(tenantId, {
        status: target,
      });
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        try {
          const reconciled = await readPlatformTenant(tenantId);
          if (mutationGenerationRef.current !== mutationGeneration) {
            releaseMutationLock();
            return;
          }
          setTenant(reconciled.data);
          if (
            lifecycleTargetIsAuthoritativelyCommitted(
              reconciled.data.status,
              target,
            )
          ) {
            setSelectedStatus("");
            setConfirmation(null);
            showReconciledCommitted(
              "Yaşam döngüsü güncellendi",
              `${tenant.name} için istenen yaşam döngüsü sonucu güncel tenant ayrıntısından doğrulandı.`,
              reconciled.meta,
            );
          } else {
            if (
              !PLATFORM_LIFECYCLE_TARGETS[
                reconciled.data.status
              ].includes(target)
            ) {
              setSelectedStatus("");
              setConfirmation(null);
            }
            showReconciledNotApplied(
              cause,
              "İstenen değişiklik sunucuda görülmedi. Güncel tenant durumu yüklendi; geçişi inceleyip bilinçli olarak yeniden deneyebilirsiniz.",
            );
          }
        } catch (reconciliationCause) {
          markTenantMutationOutcomeUnknown(
            "lifecycle",
            cause,
            reconciliationCause,
          );
        }
        releaseMutationLock();
        return;
      }
      showOperationError(
        cause,
        "Yaşam döngüsü değiştirilemedi. Tenant durumunu yenileyip yeniden deneyin.",
      );
      releaseMutationLock();
      return;
    }

    setTenant(response.data);
    setSelectedStatus("");
    setOperationNotice({
      tone: "success",
      title: "Yaşam döngüsü güncellendi",
      message: `${tenant.name} artık “${PLATFORM_STATUS_LABELS[target]}” durumunda.`,
      meta: response.meta,
    });
    beginTenantCommitRefresh();
    releaseMutationLock();
    setConfirmation(null);

    try {
      const refreshed = await readPlatformTenant(tenantId);
      if (mutationGenerationRef.current === mutationGeneration) {
        setTenant(refreshed.data);
      }
    } catch {
      if (mutationGenerationRef.current === mutationGeneration) {
        showCommittedRefreshWarning(response.meta);
      }
    } finally {
      endTenantCommitRefresh();
    }
  }

  async function confirmFeature(feature: PlatformTenantFeature) {
    if (
      !tenant ||
      !featuresMutable ||
      hasUnknownFeatureOutcome() ||
      !acquireMutationLock()
    ) {
      return;
    }
    const mutationGeneration = mutationGenerationRef.current;
    const targetEnabled = !feature.enabled;
    setOperationError(null);
    setOperationNotice(null);
    let response: Awaited<
      ReturnType<typeof updatePlatformTenantFeatures>
    >;
    try {
      response = await updatePlatformTenantFeatures(tenantId, [
        { key: feature.key, enabled: targetEnabled },
      ]);
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        try {
          const reconciled = await readPlatformTenantFeatures(tenantId);
          if (mutationGenerationRef.current !== mutationGeneration) {
            releaseMutationLock();
            return;
          }
          setFeatures(reconciled.data.features);
          const authoritativeFeature = reconciled.data.features.find(
            (candidate) => candidate.key === feature.key,
          );
          if (authoritativeFeature?.enabled === targetEnabled) {
            setConfirmation(null);
            showReconciledCommitted(
              "Modül özelliği güncellendi",
              `${PLATFORM_FEATURE_LABELS[feature.key]} için istenen durum güncel feature verisinden doğrulandı.`,
              reconciled.meta,
            );
          } else {
            showReconciledNotApplied(
              cause,
              "İstenen değişiklik sunucuda görülmedi. Güncel feature durumu yüklendi; işlemi bilinçli olarak yeniden deneyebilirsiniz.",
            );
          }
        } catch (reconciliationCause) {
          markFeatureMutationOutcomeUnknown(
            feature,
            cause,
            reconciliationCause,
          );
        }
        releaseMutationLock();
        return;
      }
      showOperationError(
        cause,
        "Modül özelliği güncellenemedi. Güncel tenant durumunu kontrol edip yeniden deneyin.",
      );
      releaseMutationLock();
      return;
    }

    setFeatures(response.data.features);
    setOperationNotice({
      tone: "success",
      title: "Modül özelliği güncellendi",
      message: `${PLATFORM_FEATURE_LABELS[feature.key]} ${
        targetEnabled ? "etkinleştirildi" : "devre dışı bırakıldı"
      }.`,
      meta: response.meta,
    });
    beginFeatureCommitRefresh();
    releaseMutationLock();
    setConfirmation(null);

    try {
      const refreshed = await readPlatformTenantFeatures(tenantId);
      if (mutationGenerationRef.current === mutationGeneration) {
        setFeatures(refreshed.data.features);
      }
    } catch {
      if (mutationGenerationRef.current === mutationGeneration) {
        showCommittedRefreshWarning(response.meta);
      }
    } finally {
      endFeatureCommitRefresh();
    }
  }

  async function confirmInitialAdminResend() {
    if (
      !tenant ||
      !canUpdateTenant ||
      !isInitialAdminActionEligible(tenant.status) ||
      hasUnknownInitialAdminOutcome(tenantId) ||
      !acquireMutationLock()
    ) {
      return;
    }
    clearManualLinkResult();
    setOperationError(null);
    setOperationNotice(null);
    try {
      const response =
        await resendPlatformTenantInitialAdminInvitation(tenantId);
      setOperationNotice({
        tone: "success",
        title: "İlk yönetici daveti yeniden hazırlandı",
        message:
          "Davet gönderim için hazırlandı; teslim edildiği anlamına gelmez. Bu ekranda kimlik veya erişim bağlantısı gösterilmez.",
        meta: response.meta,
      });
      releaseMutationLock();
      setConfirmation(null);
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        showUnknownInitialAdminOutcome(cause);
      } else {
        showOperationError(
          cause,
          "İlk yönetici daveti şu anda yeniden hazırlanamadı. Daha sonra yeniden deneyin.",
        );
      }
      releaseMutationLock();
    }
  }

  async function confirmInitialAdminManualLink() {
    if (
      !tenant ||
      !canUpdateTenant ||
      !isInitialAdminActionEligible(tenant.status) ||
      hasUnknownInitialAdminOutcome(tenantId) ||
      !acquireMutationLock()
    ) {
      return;
    }
    const resultEpoch = clearManualLinkResult();
    setOperationError(null);
    setOperationNotice(null);
    try {
      const response =
        await createPlatformTenantInitialAdminManualLink(tenantId);
      if (manualLinkStateEpochRef.current !== resultEpoch) {
        releaseMutationLock();
        setConfirmation(null);
        return;
      }
      setManualLinkResult({
        status: response.data.status,
        activation_url: response.data.activation_url,
        expires_at: response.data.expires_at,
      });
      setManualLinkCopyStatus("");
      releaseMutationLock();
      setConfirmation(null);
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        showUnknownInitialAdminOutcome(cause);
      } else {
        showOperationError(
          cause,
          "Yeni davet linki şu anda üretilemedi. Tenant ayrıntısını kontrol edip daha sonra yeniden deneyin.",
        );
      }
      releaseMutationLock();
    }
  }

  async function copyManualActivationUrl() {
    if (!manualLinkResult) return;
    const copyEpoch = manualLinkStateEpochRef.current;
    setManualLinkCopyStatus("");
    try {
      await navigator.clipboard.writeText(manualLinkResult.activation_url);
      if (manualLinkStateEpochRef.current !== copyEpoch) return;
      setManualLinkCopyStatus("Davet linki panoya kopyalandı.");
    } catch {
      if (manualLinkStateEpochRef.current !== copyEpoch) return;
      setManualLinkCopyStatus(
        "Link kopyalanamadı. Yukarıdaki alandan seçerek elle kopyalayın.",
      );
    }
  }

  async function confirmInitialAdminCorrection(
    payload: PlatformTenantInitialAdminCorrectionRequest,
  ) {
    if (
      !tenant ||
      !canUpdateTenant ||
      !isInitialAdminActionEligible(tenant.status) ||
      hasUnknownInitialAdminOutcome(tenantId) ||
      !acquireMutationLock()
    ) {
      return;
    }
    clearManualLinkResult();
    setOperationError(null);
    setOperationNotice(null);
    try {
      const response =
        await correctPlatformTenantInitialAdminInvitation(tenantId, payload);
      setOperationNotice({
        tone: "success",
        title: "İlk yönetici bilgileri düzeltildi",
        message:
          "Önceki etkinleştirme bağlantısı geçersiz kılındı ve yeni davet gönderim için hazırlandı; teslim edildiği anlamına gelmez.",
        meta: response.meta,
      });
      releaseMutationLock();
      setConfirmation(null);
    } catch (cause) {
      if (isAmbiguousPlatformMutationOutcome(cause)) {
        showUnknownInitialAdminOutcome(cause);
      } else {
        showOperationError(
          cause,
          "İlk yönetici bilgileri şu anda düzeltilemiyor. Daha sonra yeniden deneyin.",
        );
      }
      releaseMutationLock();
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
        <div className={styles.detailTitle}>
          <span>Tenant ayrıntısı</span>
          <h1 id="tenant-detail-title">{tenant.name}</h1>
          <p>
            <span className={styles.tenantSlug}>{tenant.slug}</span>
            <span aria-hidden="true">·</span>
            <span>{PLATFORM_PLAN_LABELS[tenant.plan_code]}</span>
          </p>
        </div>
        <div className={styles.detailStatus}>
          <span>Yaşam döngüsü</span>
          <span className={styles.statusBadge} data-status={tenant.status}>
            {PLATFORM_STATUS_LABELS[tenant.status]}
          </span>
        </div>
      </header>

      {operationNotice ? (
        <div
          className={
            operationNotice.tone === "warning"
              ? styles.operationWarning
              : styles.successNotice
          }
          role="status"
          aria-live="polite"
        >
          <div>
            <strong>{operationNotice.title}</strong>
            <p>{operationNotice.message}</p>
            <small>
              Referans: {operationNotice.meta.correlation_id}
            </small>
          </div>
          <button
            type="button"
            aria-label="İşlem bildirimini kapat"
            onClick={() => setOperationNotice(null)}
          >
            ×
          </button>
        </div>
      ) : null}

      {operationError && !confirmation ? (
        <div
          ref={operationErrorRef}
          className={styles.operationAlert}
          role="alert"
          tabIndex={-1}
        >
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
            <span>Güvenli platform projeksiyonu</span>
            <h2 id="safe-metadata-title">Tenant metadata’sı</h2>
          </div>
          <button
            className={styles.refreshButton}
            type="button"
            disabled={isMutating || pendingTenantCommitRefreshes > 0}
            onClick={() => {
              clearManualLinkResult();
              setIsLoading(true);
              setDetailError(null);
              setReloadKey((key) => key + 1);
            }}
          >
            Yenile
          </button>
        </div>
        <div className={styles.metadataSections}>
          <section
            className={styles.metadataSection}
            aria-labelledby="identity-status-title"
          >
            <div className={styles.metadataSectionHeader}>
              <h3 id="identity-status-title">Kimlik ve durum</h3>
              <p>Tenant kaydı ve operasyonel sağlık bilgileri</p>
            </div>
            <dl className={styles.metadataList}>
              <div>
                <dt>Tenant kodu</dt>
                <dd>{tenant.slug}</dd>
              </div>
              <div>
                <dt>Tenant kimliği</dt>
                <dd className={styles.monospace}>{tenant.id}</dd>
              </div>
              <div>
                <dt>Yaşam döngüsü</dt>
                <dd>{PLATFORM_STATUS_LABELS[tenant.status]}</dd>
              </div>
              <div>
                <dt>Sağlık</dt>
                <dd>{PLATFORM_HEALTH_LABELS[tenant.health]}</dd>
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

          <section
            className={styles.metadataSection}
            aria-labelledby="commercial-localization-title"
          >
            <div className={styles.metadataSectionHeader}>
              <h3 id="commercial-localization-title">
                Ticari ve bölgesel bilgiler
              </h3>
              <p>Plan, kapasite ve yerel çalışma tercihleri</p>
            </div>
            <dl className={styles.metadataList}>
              <div>
                <dt>Plan</dt>
                <dd>{PLATFORM_PLAN_LABELS[tenant.plan_code]}</dd>
              </div>
              <div>
                <dt>Tanımlı aktif çalışan limiti</dt>
                <dd>
                  {tenant.limits.active_employees?.toLocaleString("tr-TR") ??
                    "Tanımlı değil"}
                </dd>
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
            </dl>
          </section>
        </div>
      </section>

      <section
        className={`${styles.formCard} ${styles.invitationCard}`}
        aria-labelledby="initial-admin-invitation-title"
      >
        <div className={styles.cardHeader}>
          <div>
            <span>Güvenli ilk erişim</span>
            <h2 id="initial-admin-invitation-title">
              İlk yönetici daveti
            </h2>
          </div>
        </div>
        <div className={styles.invitationBody}>
          {manualLinkResult &&
          canUpdateTenant &&
          initialAdminActionsEligible ? (
            <div
              ref={manualLinkResultRef}
              className={styles.manualLinkResult}
              role="region"
              aria-labelledby="manual-link-result-title"
              tabIndex={-1}
            >
              <div className={styles.manualLinkResultHeader}>
                <div>
                  <strong id="manual-link-result-title">
                    Yeni davet linki hazır
                  </strong>
                  <p>
                    Link tek kullanımlıdır ve süresi dolduğunda çalışmaz. Yalnız
                    tenantın ilk yöneticisiyle güvenli bir kanaldan paylaşın.
                  </p>
                </div>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={() =>
                    clearManualLinkResult({ restoreFocus: true })
                  }
                >
                  Paneli kapat
                </button>
              </div>
              <div className={styles.manualLinkField}>
                <label htmlFor="manual-initial-admin-activation-url">
                  Etkinleştirme linki
                </label>
                <div className={styles.manualLinkInputRow}>
                  <input
                    id="manual-initial-admin-activation-url"
                    type="text"
                    value={manualLinkResult.activation_url}
                    readOnly
                    autoComplete="off"
                    spellCheck={false}
                    aria-describedby="manual-link-expiry manual-link-disposal-warning"
                    onFocus={(event) => event.currentTarget.select()}
                  />
                  <button
                    className={styles.primaryButton}
                    type="button"
                    onClick={() => void copyManualActivationUrl()}
                  >
                    Linki kopyala
                  </button>
                </div>
                <p id="manual-link-expiry">
                  Son geçerlilik:{" "}
                  <time dateTime={manualLinkResult.expires_at}>
                    {formatPlatformDate(manualLinkResult.expires_at)}
                  </time>
                </p>
                <p
                  className={styles.manualLinkDisposalWarning}
                  id="manual-link-disposal-warning"
                >
                  Bu paneli kapattığınızda veya sayfayı yenilediğinizde link bu
                  ekranda yeniden gösterilemez.
                </p>
                <span
                  className={styles.manualLinkCopyStatus}
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                >
                  {manualLinkCopyStatus}
                </span>
              </div>
            </div>
          ) : (
            <>
              <div>
                <strong>Yeni bir davet güvenli biçimde hazırlanır</strong>
                <p>
                  Önceki etkinleştirme bağlantısı geçersiz olur. Yeniden gönderme
                  ve bilgi düzeltme işlemlerinde alıcı kimliği veya erişim
                  bağlantısı bu platform ekranında gösterilmez.
                </p>
              </div>
              {canUpdateTenant ? (
                <div className={styles.invitationControls}>
                  {isInitialAdminOutcomeUnknown ? (
                    <div
                      className={styles.cardNotice}
                      id="initial-admin-unknown-outcome"
                      role="alert"
                    >
                      <strong>Davet işleminin sonucu doğrulanamadı</strong>
                      <p>
                        Yeniden gönderme, düzeltme ve yeni link üretme bu tenant
                        için kilitlendi. Platform denetim kaydını inceleyin veya
                        güvenilir güncel ayrıntıyı almak için Tenant
                        metadata’sındaki Yenile düğmesini kullanın.
                      </p>
                    </div>
                  ) : null}
                  <div className={styles.invitationActions}>
                    {initialAdminActionsEligible ? (
                      <button
                        ref={manualLinkTriggerRef}
                        className={styles.primaryButton}
                        type="button"
                        disabled={isInitialAdminOutcomeUnknown || isMutating}
                        aria-describedby={
                          isInitialAdminOutcomeUnknown
                            ? "initial-admin-unknown-outcome"
                            : undefined
                        }
                        onClick={() => {
                          if (hasUnknownInitialAdminOutcome(tenantId)) return;
                          openConfirmation({
                            kind: "initial_admin_manual_link",
                          });
                        }}
                      >
                        Yeni davet linki uret
                      </button>
                    ) : null}
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      disabled={
                        !initialAdminActionsEligible ||
                        isInitialAdminOutcomeUnknown ||
                        isMutating
                      }
                      aria-describedby={
                        isInitialAdminOutcomeUnknown
                          ? "initial-admin-unknown-outcome"
                          : initialAdminActionsEligible
                            ? undefined
                            : "initial-admin-lifecycle-explanation"
                      }
                      onClick={() => {
                        if (
                          !initialAdminActionsEligible ||
                          hasUnknownInitialAdminOutcome(tenantId)
                        ) {
                          return;
                        }
                        openConfirmation({ kind: "initial_admin_resend" });
                      }}
                    >
                      İlk yönetici davetini yeniden gönder
                    </button>
                    <button
                      className={styles.secondaryButton}
                      type="button"
                      disabled={
                        !initialAdminActionsEligible ||
                        isInitialAdminOutcomeUnknown ||
                        isMutating
                      }
                      aria-describedby={
                        isInitialAdminOutcomeUnknown
                          ? "initial-admin-unknown-outcome"
                          : initialAdminActionsEligible
                            ? undefined
                            : "initial-admin-lifecycle-explanation"
                      }
                      onClick={() => {
                        if (
                          !initialAdminActionsEligible ||
                          hasUnknownInitialAdminOutcome(tenantId)
                        ) {
                          return;
                        }
                        openConfirmation({ kind: "initial_admin_correction" });
                      }}
                    >
                      İlk yönetici bilgilerini düzelt
                    </button>
                  </div>
                  {!initialAdminActionsEligible ? (
                    <p
                      className={styles.initialAdminLifecycleExplanation}
                      id="initial-admin-lifecycle-explanation"
                    >
                      İlk yönetici işlemleri yalnız Hazırlanıyor, Deneme veya
                      Aktif yaşam döngüsündeki tenantlarda kullanılabilir.
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className={styles.invitationPermission}>
                  Bu işlemler tenant güncelleme izni gerektirir.
                </p>
              )}
            </>
          )}
        </div>
      </section>

      <div className={styles.operationGrid}>
        <section className={styles.formCard} aria-labelledby="settings-title">
          <div className={styles.cardHeader}>
            <div>
              <span>Allowlist ayarlar</span>
              <h2 id="settings-title">Tenant ayarları</h2>
            </div>
          </div>
          {isTenantMutationOutcomeUnknown ? (
            <div className={styles.cardNotice} role="alert">
              <strong>Tenant değişikliği sonucu doğrulanamadı</strong>
              <p>
                Ayarlar ve yaşam döngüsü işlemleri, güncel tenant ayrıntısı
                güvenilir biçimde yeniden yüklenene kadar kilitlendi.
              </p>
            </div>
          ) : null}
          {metadataMutable ? (
            <form
              className={styles.settingsForm}
              key={tenant.updated_at}
              onSubmit={(event) => void submitMetadata(event)}
            >
              <div className={styles.settingsGroups}>
                <fieldset
                  className={styles.settingsGroup}
                  disabled={isMutating || isTenantMutationOutcomeUnknown}
                >
                  <legend>Organizasyon</legend>
                  <div className={styles.settingsGroupGrid}>
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
                  </div>
                </fieldset>

                <fieldset
                  className={styles.settingsGroup}
                  disabled={isMutating || isTenantMutationOutcomeUnknown}
                >
                  <legend>Ticari ayarlar</legend>
                  <div className={styles.settingsGroupGrid}>
                    <label className={styles.field}>
                      <span>Plan</span>
                      <select
                        name="plan_code"
                        defaultValue={tenant.plan_code}
                      >
                        {tenant.plan_code === "premium" ? (
                          <option value="premium" disabled>
                            {PLATFORM_PLAN_LABELS.premium}
                          </option>
                        ) : null}
                        <option value="core">
                          {PLATFORM_PLAN_LABELS.core}
                        </option>
                        <option value="professional">
                          {PLATFORM_PLAN_LABELS.professional}
                        </option>
                        <option value="enterprise">
                          {PLATFORM_PLAN_LABELS.enterprise}
                        </option>
                      </select>
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
                        defaultValue={
                          tenant.limits.active_employees ?? ""
                        }
                      />
                      <small>
                        Kullanım sayacı değildir; mevcut bir limit boş
                        bırakılamaz.
                      </small>
                    </label>
                  </div>
                </fieldset>

                <fieldset
                  className={styles.settingsGroup}
                  disabled={isMutating || isTenantMutationOutcomeUnknown}
                >
                  <legend>Yerel ayarlar</legend>
                  <div className={styles.settingsGroupGrid}>
                    <label className={styles.field}>
                      <span>Veri bölgesi</span>
                      <select
                        name="data_region"
                        defaultValue={tenant.data_region}
                        disabled={
                          tenant.status !== "provisioning" || isMutating
                        }
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
                        <option value="en-US">
                          English (United States)
                        </option>
                      </select>
                    </label>
                    <label className={styles.field}>
                      <span>Saat dilimi</span>
                      <select
                        name="timezone"
                        required
                        defaultValue={tenant.timezone}
                        aria-describedby="tenant-timezone-help"
                      >
                        {timezoneOptions.map((tenantTimezone) => (
                          <option
                            value={tenantTimezone}
                            key={tenantTimezone}
                          >
                            {tenantTimezone}
                          </option>
                        ))}
                      </select>
                      <small id="tenant-timezone-help">
                        Saat dilimi, yerel tarih ve saatlerin nasıl
                        gösterileceğini ve yorumlanacağını belirler.
                      </small>
                    </label>
                  </div>
                </fieldset>
              </div>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={isMutating || isTenantMutationOutcomeUnknown}
              >
                {isMutating
                  ? "Kaydediliyor…"
                  : isTenantMutationOutcomeUnknown
                    ? "Yenileme bekleniyor"
                    : "Ayarları kaydet"}
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

        <section
          className={`${styles.formCard} ${styles.lifecycleCard}`}
          aria-label="Yaşam döngüsü kontrolleri"
        >
          <div className={styles.cardHeader}>
            <div>
              <span>Kontrollü yaşam döngüsü</span>
              <h2 id="lifecycle-title">Yaşam döngüsü</h2>
            </div>
            <span className={styles.statusBadge} data-status={tenant.status}>
              {PLATFORM_STATUS_LABELS[tenant.status]}
            </span>
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
              <label className={styles.field}>
                <span>Yeni yaşam döngüsü durumu</span>
                <select
                  ref={lifecycleSelectRef}
                  value={selectedStatus}
                  disabled={isMutating || isTenantMutationOutcomeUnknown}
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
              {hasHighImpactLifecycleTarget ? (
                <div className={styles.lifecycleWarning}>
                  <strong>Yüksek etkili geçişler</strong>
                  <p>
                    Askıya alma ve kapatma akışları tenant erişimini
                    kısıtlayabilir. Seçiminiz uygulanmadan önce ayrıca
                    onaylanır.
                  </p>
                </div>
              ) : null}
              <button
                className={
                  selectedStatus && isHighImpactStatus(selectedStatus)
                    ? styles.dangerButton
                    : styles.primaryButton
                }
                type="button"
                disabled={
                  !selectedStatus ||
                  isMutating ||
                  isTenantMutationOutcomeUnknown
                }
                onClick={() => {
                  if (
                    selectedStatus &&
                    unknownTenantMutationKind(tenantId) === null
                  ) {
                    openConfirmation({
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

      <section
        className={styles.featureCard}
        aria-label="Feature kontrolleri"
      >
        <div className={styles.cardHeader}>
          <div>
            <span>Modül dağıtımı</span>
            <h2 id="features-title">Feature flag’ler</h2>
          </div>
          {canReadFeatures ? (
            <button
              className={styles.refreshButton}
              type="button"
              disabled={
                isLoadingFeatures ||
                isMutating ||
                pendingFeatureCommitRefreshes > 0
              }
              onClick={() => setFeatureReloadKey((key) => key + 1)}
            >
              Yenile
            </button>
          ) : null}
        </div>

        {isFeatureMutationOutcomeUnknown ? (
          <div
            className={styles.cardNotice}
            id="feature-mutation-unknown-outcome"
            role="alert"
          >
            <strong>Feature değişikliği sonucu doğrulanamadı</strong>
            <p>
              Tüm feature değişiklikleri kilitlendi. Yeni bir değişiklik
              yapmadan önce Yenile ile eksiksiz ve doğrulanmış güncel feature
              verisini yeniden yükleyin.
            </p>
          </div>
        ) : null}

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
        ) : features.length === 0 ? (
          <div className={styles.cardNotice} role="status">
            <strong>Tanımlı modül özelliği yok</strong>
            <p>Bu tenant için gösterilebilecek bir feature kaydı bulunmuyor.</p>
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
                      disabled={
                        !featuresMutable ||
                        isMutating
                      }
                      aria-describedby={
                        isFeatureMutationOutcomeUnknown
                          ? "feature-mutation-unknown-outcome"
                          : undefined
                      }
                      aria-label={`${PLATFORM_FEATURE_LABELS[feature.key]} özelliğini ${
                        feature.enabled
                          ? "devre dışı bırak"
                          : "etkinleştir"
                      }`}
                      onClick={() => {
                        if (hasUnknownFeatureOutcome()) {
                          return;
                        }
                        openConfirmation({ kind: "feature", feature });
                      }}
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

      {confirmation && confirmationIsAuthorized ? (
        confirmation.kind === "initial_admin_correction" ? (
          <InitialAdminCorrectionDialog
            error={operationError}
            isBusy={isMutating}
            isOutcomeUnknown={isInitialAdminOutcomeUnknown}
            onCancel={closeConfirmation}
            onConfirm={confirmInitialAdminCorrection}
          />
        ) : (
          <PlatformConfirmationDialog
            title={
              confirmation.kind === "lifecycle"
                ? `${PLATFORM_STATUS_LABELS[confirmation.target]} durumuna geçir`
                : confirmation.kind === "feature"
                  ? `${PLATFORM_FEATURE_LABELS[confirmation.feature.key]} özelliğini ${
                      confirmation.feature.enabled
                        ? "devre dışı bırak"
                        : "etkinleştir"
                    }`
                  : confirmation.kind === "initial_admin_manual_link"
                    ? "Yeni davet linki uret"
                    : "İlk yönetici davetini yeniden gönder"
            }
            description={
              confirmation.kind === "lifecycle" ? (
                <p>
                  <strong>{tenant.name}</strong> için yalnız backend’in izin
                  verdiği yaşam döngüsü geçişi uygulanacak. Özellikle askıya
                  alma ve kapatma akışları tenant erişimini kısıtlayabilir.
                </p>
              ) : confirmation.kind === "feature" ? (
                <p>
                  Bu değişiklik tenantın{" "}
                  <strong>
                    {PLATFORM_FEATURE_LABELS[confirmation.feature.key]}
                  </strong>{" "}
                  modül erişimini doğrudan etkiler.
                </p>
              ) : confirmation.kind === "initial_admin_manual_link" ? (
                <p>
                  Yeni link üretildiğinde önceki etkinleştirme linki hemen
                  geçersiz olur. Yeni link süreli ve tek kullanımlıdır; yalnız
                  işlem tamamlandıktan sonra bu ekranda bir kez gösterilir.
                </p>
              ) : (
                <p>
                  Yeni bir davet hazırlanır ve önceki etkinleştirme bağlantısı
                  geçersiz olur. Bu ekranda e-posta adresi veya erişim bağlantısı
                  gösterilmez.
                </p>
              )
            }
            confirmLabel={
              confirmation.kind === "initial_admin_resend"
                ? "Daveti yeniden gönder"
                : confirmation.kind === "initial_admin_manual_link"
                  ? "Yeni linki üret"
                  : "Değişikliği uygula"
            }
            busyLabel={
              confirmation.kind === "initial_admin_resend"
                ? "Davet hazırlanıyor…"
                : confirmation.kind === "initial_admin_manual_link"
                  ? "Link hazırlanıyor…"
                  : "Değişiklik uygulanıyor…"
            }
            danger={
              confirmation.kind === "lifecycle"
                ? isHighImpactStatus(confirmation.target)
                : confirmation.kind === "feature"
                  ? confirmation.feature.enabled
                  : false
            }
            error={operationError}
            errorTitle={
              (confirmation.kind === "initial_admin_resend" ||
                confirmation.kind === "initial_admin_manual_link") &&
              isInitialAdminOutcomeUnknown
                ? "Sonuç doğrulanamadı"
                : undefined
            }
            fallbackFocusRef={
              confirmation.kind === "lifecycle"
                ? lifecycleSelectRef
                : confirmation.kind === "initial_admin_manual_link"
                  ? manualLinkTriggerRef
                  : undefined
            }
            isBusy={isMutating}
            isConfirmDisabled={
              (confirmation.kind === "initial_admin_resend" ||
                confirmation.kind === "initial_admin_manual_link") &&
              isInitialAdminOutcomeUnknown
            }
            onCancel={closeConfirmation}
            onConfirm={() => {
              if (confirmation.kind === "lifecycle") {
                void confirmLifecycle(confirmation.target);
              } else if (confirmation.kind === "feature") {
                void confirmFeature(confirmation.feature);
              } else if (confirmation.kind === "initial_admin_manual_link") {
                void confirmInitialAdminManualLink();
              } else {
                void confirmInitialAdminResend();
              }
            }}
          />
        )
      ) : null}
    </section>
  );
}
