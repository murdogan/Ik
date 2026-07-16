import { ApiClientError } from "@/lib/api-client";
import type { UnifiedRequestKind } from "@/lib/self-service";

export const REQUEST_KIND_LABELS: Record<UnifiedRequestKind, string> = {
  leave: "İzin talebi",
  profile_change: "Profil değişikliği",
  document: "HR belge talebi",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Taslak",
  published: "Yayında",
  archived: "Arşivlendi",
  submitted: "Gönderildi",
  pending: "Bekliyor",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
  resolved: "Çözüldü",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function requestErrorMessage(cause: unknown, fallback: string): string {
  if (!(cause instanceof ApiClientError)) return fallback;
  if (cause.status === 409) {
    return "Kayıt siz görüntülerken değişti. Güncel veriyi yükleyip yeniden deneyin.";
  }
  if (cause.status === 403) return "Bu işlem için güncel yetkiniz bulunmuyor.";
  if (cause.status === 404) return "Kayıt bulunamadı veya artık erişim kapsamınızda değil.";
  if (cause.status === 422) return "Girilen bilgileri kontrol edip yeniden deneyin.";
  if (cause.code === "network_error") return "Bağlantı kurulamadı. Yeniden deneyin.";
  return fallback;
}

export function isConflict(cause: unknown): boolean {
  return cause instanceof ApiClientError && cause.status === 409;
}
