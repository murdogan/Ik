import { ApiClientError } from "@/lib/api-client";
import type {
  AuditMetadataValue,
  AuditScope,
} from "@/lib/audit-events";

export interface AuditErrorPresentation {
  message: string;
  reference?: string | null;
}

const EVENT_LABELS: Record<string, string> = {
  "auth.login.succeeded": "Giriş başarılı",
  "auth.login.failed": "Giriş başarısız",
  "platform.auth.login.succeeded": "Platform girişi başarılı",
  "platform.auth.login.failed": "Platform girişi başarısız",
  "platform.auth.login.denied": "Platform rolü reddedildi",
  "auth.activation.completed": "Kullanıcı etkinleştirildi",
  "authentication.login_succeeded": "Giriş başarılı",
  "authentication.login_failed": "Giriş başarısız",
  "invitation.created": "Kullanıcı davet edildi",
  "user.invited": "Kullanıcı davet edildi",
  "user.invitation.created": "Kullanıcı davet edildi",
  "role.assignment.replaced": "Kullanıcı rolleri değiştirildi",
  "user.roles_replaced": "Kullanıcı rolleri değiştirildi",
  "user.roles.replaced": "Kullanıcı rolleri değiştirildi",
  "user.status.changed": "Kullanıcı durumu değiştirildi",
  "session.started": "Oturum başlatıldı",
  "session.refreshed": "Oturum yenilendi",
  "session.reuse_detected": "Oturum yeniden kullanım girişimi",
  "session.revoked": "Oturum sonlandırıldı",
  "platform.session.started": "Platform oturumu başlatıldı",
  "platform.session.refreshed": "Platform oturumu yenilendi",
  "platform.session.reuse_detected": "Platform oturumunda tekrar kullanım algılandı",
  "platform.session.revoked": "Platform oturumu sonlandırıldı",
  "session.logout": "Oturum kapatıldı",
  "platform.tenant.created": "Tenant oluşturuldu",
  "platform.tenant.status_changed": "Tenant durumu değiştirildi",
  "platform.tenant.setting_changed": "Tenant ayarları değiştirildi",
  "platform.feature_flag.changed": "Özellik bayrağı değiştirildi",
  "tenant.setting.changed": "Tenant ayarları değiştirildi",
  "privacy.notice.published": "Çalışan aydınlatma metni yayınlandı",
  "privacy.notice.acknowledged": "Aydınlatma metni okuma kaydı oluşturuldu",
  "privacy.consent.granted": "İsteğe bağlı onay verildi",
  "privacy.consent.withdrawn": "İsteğe bağlı onay geri çekildi",
  "retention.policy.mutated": "Saklama politikası değiştirildi",
  "retention.dry_run": "Saklama envanteri önizlendi",
  "legal_entity.created": "Tüzel kişilik oluşturuldu",
  "legal_entity.updated": "Tüzel kişilik güncellendi",
  "branch.created": "Şube oluşturuldu",
  "branch.updated": "Şube güncellendi",
  "branch.archived": "Şube arşivlendi",
  "platform.tenant.updated": "Tenant güncellendi",
};

const CATEGORY_LABELS: Record<string, string> = {
  auth: "Kimlik doğrulama",
  authentication: "Kimlik doğrulama",
  invitation: "Davet",
  identity: "Kimlik",
  role: "Rol yönetimi",
  authorization: "Yetkilendirme",
  session: "Oturum",
  platform: "Platform",
  tenant: "Tenant",
  tenant_security: "Tenant güvenliği",
  tenant_admin: "Tenant yönetimi",
  hr_operations: "İK operasyonları",
  platform_operations: "Platform operasyonları",
};

const RESULT_LABELS: Record<string, string> = {
  success: "Başarılı",
  succeeded: "Başarılı",
  failure: "Başarısız",
  failed: "Başarısız",
  denied: "Reddedildi",
};

const ACTOR_LABELS: Record<string, string> = {
  user: "Kullanıcı",
  system: "Sistem",
  worker: "Arka plan görevi",
  platform_admin: "Platform yöneticisi",
  support_session: "Destek oturumu",
};

type AuditAction = "list" | "detail";

export function auditErrorPresentation(
  cause: unknown,
  action: AuditAction,
): AuditErrorPresentation {
  const genericMessage =
    action === "list"
      ? "Denetim kayıtları şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : "Denetim kaydı ayrıntıları şu anda yüklenemiyor. Lütfen yeniden deneyin.";
  if (!(cause instanceof ApiClientError)) {
    return { message: genericMessage };
  }

  let message = genericMessage;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu denetim kayıtlarını görüntüleme yetkiniz bulunmuyor.";
  } else if (cause.status === 404 && action === "detail") {
    message = "Denetim kaydı bulunamadı veya artık erişim kapsamınızda değil.";
  } else if (cause.status === 422) {
    message = "Filtreleri kontrol edip yeniden deneyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference: cause.correlationId };
}

export function formatAuditDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

export function auditEventLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? humanizeIdentifier(eventType);
}

export function auditCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? humanizeIdentifier(category);
}

export function auditResultLabel(result: string): string {
  return RESULT_LABELS[result] ?? humanizeIdentifier(result);
}

export function auditActorLabel(actorType: string): string {
  return ACTOR_LABELS[actorType] ?? humanizeIdentifier(actorType);
}

export function auditScopeLabel(scope: AuditScope): string {
  return scope === "tenant" ? "Tenant kaydı" : "Platform kaydı";
}

export function shortIdentifier(value: string | null): string {
  if (!value) {
    return "—";
  }
  return value.length > 14 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

export function metadataValueLabel(value: AuditMetadataValue): string {
  if (Array.isArray(value)) {
    return value.length === 0 ? "—" : value.map(scalarLabel).join(", ");
  }
  return scalarLabel(value);
}

export function humanizeIdentifier(value: string): string {
  const normalized = value.replace(/[._-]+/g, " ").trim();
  if (!normalized) {
    return "—";
  }
  return `${normalized.slice(0, 1).toLocaleUpperCase("tr-TR")}${normalized.slice(1)}`;
}

function scalarLabel(value: string | number | boolean | null): string {
  if (value === null || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "Evet" : "Hayır";
  }
  return String(value);
}
