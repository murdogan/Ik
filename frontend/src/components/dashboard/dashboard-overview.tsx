"use client";

import Link from "next/link";

import { useSession } from "@/components/session/session-provider";
import { useTenantFeatures } from "@/components/session/tenant-feature-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { TENANT_FEATURES } from "@/lib/feature-rollout";

import { ManagerTeam } from "./manager-team";
import styles from "./tenant-shell.module.css";

function displayName(fullName: string | null, email: string): string {
  return fullName?.trim() || email;
}

export function DashboardOverview() {
  const { user } = useSession();
  const { status: featureStatus, isEnabled } = useTenantFeatures();
  const name = displayName(user.full_name, user.email);
  const canReadTeam = hasPermission(
    user,
    AUTHORIZATION_PERMISSIONS.readTeamEmployees,
  );
  const canOpenOrganization =
    hasPermission(user, AUTHORIZATION_PERMISSIONS.readOrganization) &&
    featureStatus === "ready" &&
    isEnabled(TENANT_FEATURES.organization);

  return (
    <section aria-labelledby="dashboard-title">
      <div className={styles.welcome}>
        <span>Tenant çalışma alanı</span>
        <h1 id="dashboard-title">Merhaba, {name}</h1>
        <p>
          {user.tenant.name} çalışma alanına güvenli biçimde giriş yaptınız. Wealthy Falcon HR
          ana ekranınız kullanıma hazır.
        </p>
      </div>

      <div className={styles.cards}>
        <article className={styles.card}>
          <span className={styles.cardIcon} aria-hidden="true">
            ✓
          </span>
          <div>
            <small>Oturum durumu</small>
            <h2>Güvenli oturum etkin</h2>
            <p>Kısa ömürlü erişim ve yenilenen güvenli oturum ile bağlısınız.</p>
          </div>
        </article>

        <article className={styles.card}>
          <span className={`${styles.cardIcon} ${styles.blueIcon}`} aria-hidden="true">
            W
          </span>
          <div>
            <small>Kurum</small>
            <h2>{user.tenant.name}</h2>
            <p>Çalışma alanınız: {user.tenant.name}</p>
          </div>
        </article>

        {canOpenOrganization ? (
          <Link
            className={`${styles.card} ${styles.cardLink}`}
            href="/organization"
          >
            <span className={styles.cardIcon} aria-hidden="true">
              O
            </span>
            <div>
              <small>Organizasyon</small>
              <h2>Organizasyon çalışma alanını aç</h2>
              <p>
                Şemayı, tüzel kişilikleri, şubeleri, departmanları ve pozisyonları
                tek alanda inceleyin.
              </p>
            </div>
            <span className={styles.cardArrow} aria-hidden="true">
              →
            </span>
          </Link>
        ) : null}
      </div>

      {canReadTeam ? <ManagerTeam /> : null}
    </section>
  );
}
