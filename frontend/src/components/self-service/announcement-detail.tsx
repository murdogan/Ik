"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  actOnAnnouncement,
  readAnnouncement,
  type AnnouncementDetail,
} from "@/lib/self-service";

import { formatDateTime, isConflict, requestErrorMessage } from "./presentation";
import styles from "./self-service.module.css";

export function AnnouncementDetailScreen({ announcementId }: { announcementId: string }) {
  const { sessionGeneration, user } = useSession();
  const [announcement, setAnnouncement] = useState<AnnouncementDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void readAnnouncement(announcementId, "own").then(
      async (result) => {
        if (!active) return;
        if (result.read_at === null) {
          try {
            const readResult = await actOnAnnouncement(
              announcementId,
              "read",
              result.version,
            );
            if (active) setAnnouncement(readResult);
          } catch (cause) {
            if (!active) return;
            if (isConflict(cause)) {
              setReloadKey((value) => value + 1);
              return;
            }
            setAnnouncement(result);
            setError(requestErrorMessage(cause, "Duyuru okundu olarak işaretlenemedi."));
          }
        } else {
          setAnnouncement(result);
        }
        if (active) setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setAnnouncement(null);
        setError(requestErrorMessage(cause, "Duyuru yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [announcementId, reloadKey, sessionGeneration, user.tenant_id]);

  async function acknowledge() {
    if (!announcement || isAcknowledging || announcement.acknowledged_at) return;
    setIsAcknowledging(true);
    setError(null);
    setNotice(null);
    try {
      const result = await actOnAnnouncement(
        announcement.id,
        "ack",
        announcement.version,
      );
      setAnnouncement(result);
      setNotice("Kritik duyuruyu okuduğunuz kaydedildi. Bu onay geri alınamaz.");
    } catch (cause) {
      setError(requestErrorMessage(cause, "Duyuru onaylanamadı."));
      if (isConflict(cause)) setReloadKey((value) => value + 1);
    } finally {
      setIsAcknowledging(false);
    }
  }

  if (isLoading) {
    return (
      <section className={styles.loadingState} role="status">
        <span className={styles.spinner} aria-hidden="true" />
        <strong>Duyuru yükleniyor</strong>
      </section>
    );
  }

  if (!announcement) {
    return (
      <section className={styles.errorState} role="alert">
        <strong>Duyuru açılamadı</strong>
        <p>{error ?? "Bu duyuru artık erişim kapsamınızda değil."}</p>
        <Link className={styles.secondaryButton} href="/announcements">Duyurulara dön</Link>
      </section>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>Tenant duyurusu</span>
          <h1>{announcement.title}</h1>
          <p>
            {announcement.published_at
              ? formatDateTime(announcement.published_at)
              : "Yayın zamanı bulunmuyor"}
          </p>
        </div>
        <Link className={styles.secondaryButton} href="/announcements">Duyurulara dön</Link>
      </header>

      {error ? <div className={styles.errorBanner} role="alert">{error}</div> : null}
      {notice ? <div className={styles.successBanner} role="status">{notice}</div> : null}

      <article className={styles.detailCard}>
        <div className={styles.badges}>
          {announcement.is_critical ? (
            <span className={styles.criticalBadge}>Kritik duyuru</span>
          ) : (
            <span className={styles.badge}>Bilgilendirme</span>
          )}
          {announcement.read_at ? <span className={styles.badge}>Okundu</span> : null}
          {announcement.acknowledged_at ? (
            <span className={styles.badge}>Onaylandı</span>
          ) : null}
        </div>
        <p className={styles.bodyText}>{announcement.body}</p>
        {announcement.is_critical ? (
          <div className={styles.actions}>
            <button
              className={styles.primaryButton}
              type="button"
              disabled={isAcknowledging || announcement.acknowledged_at !== null}
              onClick={() => void acknowledge()}
            >
              {announcement.acknowledged_at
                ? "Okuduğunuz onaylandı"
                : isAcknowledging
                  ? "Onay kaydediliyor…"
                  : "Okudum ve onaylıyorum"}
            </button>
          </div>
        ) : null}
      </article>
    </div>
  );
}
