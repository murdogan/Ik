import { ApiClientError } from "@/lib/api-client";
import type { UserStatus } from "@/lib/user-administration";

export interface UserAdminErrorPresentation {
  message: string;
  reference?: string | null;
}

export const STATUS_LABELS: Record<UserStatus, string> = {
  invited: "Davet bekliyor",
  active: "Aktif",
  locked: "Kilitli",
  disabled: "Devre dışı",
};

type UserAction = "list" | "read" | "update" | "invite";

const GENERIC_MESSAGES: Record<UserAction, string> = {
  list: "Kullanıcı listesi şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  read: "Kullanıcı ayrıntıları şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  update: "Kullanıcı değişiklikleri kaydedilemedi. Lütfen yeniden deneyin.",
  invite: "Davet şu anda gönderilemedi. Lütfen yeniden deneyin.",
};

export function userAdminErrorPresentation(
  cause: unknown,
  action: UserAction,
): UserAdminErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return { message: GENERIC_MESSAGES[action] };
  }

  let message = GENERIC_MESSAGES[action];
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu kullanıcı yönetimi işlemi için tenant yöneticisi yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Kullanıcı bulunamadı veya artık bu çalışma alanında değil.";
  } else if (cause.status === 409 && action === "invite") {
    message = "Bu e-posta adresi için etkin ya da daha önce etkinleştirilmiş bir hesap var.";
  } else if (cause.status === 409 && action === "update") {
    message =
      "Bu durum değişikliği hesabın mevcut etkinleştirme durumuyla uyumlu değil veya kendi erişiminizi kapatamazsınız.";
  } else if (cause.status === 422) {
    message =
      action === "invite"
        ? "Ad soyad ve e-posta bilgilerini kontrol edin."
        : "Değişiklikleri kontrol edin ve yeniden deneyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }

  return { message, reference: cause.correlationId };
}

export function formatUserDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
