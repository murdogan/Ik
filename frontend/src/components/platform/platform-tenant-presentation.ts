import type {
  PlatformFeatureKey,
  PlatformTenantHealth,
  PlatformTenantPlan,
  PlatformTenantRegion,
  PlatformTenantStatus,
} from "@/lib/platform-tenants";

export const PLATFORM_STATUS_LABELS: Record<PlatformTenantStatus, string> = {
  provisioning: "Hazırlanıyor",
  trial: "Deneme",
  active: "Aktif",
  suspended: "Askıya alınmış",
  offboarding: "Kapatılıyor",
  closed: "Kapalı",
};

export const PLATFORM_HEALTH_LABELS: Record<PlatformTenantHealth, string> = {
  provisioning: "Kurulum sürüyor",
  healthy: "Sağlıklı",
  restricted: "Kısıtlı",
  offboarding: "Kapatma sürecinde",
  closed: "Kapalı",
};

export const PLATFORM_PLAN_LABELS: Record<
  PlatformTenantPlan | "premium",
  string
> = {
  core: "Core",
  professional: "Professional",
  enterprise: "Enterprise",
  premium: "Premium (eski plan)",
};

export const PLATFORM_REGION_LABELS: Record<PlatformTenantRegion, string> = {
  "tr-1": "Türkiye",
  "eu-1": "Avrupa Birliği",
};

export const PLATFORM_FEATURE_LABELS: Record<PlatformFeatureKey, string> = {
  organization: "Organizasyon",
  employees: "Çalışan yönetimi",
  documents: "Dokümanlar",
  leave: "İzin yönetimi",
  self_service: "Çalışan self servis",
  reporting: "Raporlama",
  notifications: "Bildirimler",
};

export const PLATFORM_FEATURE_DESCRIPTIONS: Record<
  PlatformFeatureKey,
  string
> = {
  organization: "Organizasyon yapısı ve pozisyon kataloğu",
  employees: "Tenant içindeki çalışan yönetimi modülü",
  documents: "Çalışan dokümanı ve belge türü akışları",
  leave: "İzin talebi, onay ve bakiye yönetimi",
  self_service: "Çalışanın kendi hizmetlerine erişimi",
  reporting: "Yetki kapsamlı operasyonel raporlar",
  notifications: "Uygulama içi bildirim teslimi",
};

export const PLATFORM_LIFECYCLE_TARGETS: Record<
  PlatformTenantStatus,
  readonly PlatformTenantStatus[]
> = {
  provisioning: ["trial", "active", "closed"],
  trial: ["active", "suspended", "offboarding"],
  active: ["suspended", "offboarding"],
  suspended: ["trial", "active", "offboarding"],
  offboarding: ["closed"],
  closed: [],
};

const dateFormatter = new Intl.DateTimeFormat("tr-TR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Istanbul",
});

export function formatPlatformDate(value: string): string {
  return dateFormatter.format(new Date(value));
}

export function isHighImpactStatus(status: PlatformTenantStatus): boolean {
  return ["suspended", "offboarding", "closed"].includes(status);
}
