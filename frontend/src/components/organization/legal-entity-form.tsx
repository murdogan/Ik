"use client";

import { type FormEvent, useMemo, useState } from "react";

import {
  type LegalEntity,
  type LegalEntityStatus,
  type LegalEntityUpdateRequest,
  updateLegalEntity,
} from "@/lib/organization";

import styles from "./organization.module.css";
import {
  formatOrganizationDate,
  LEGAL_ENTITY_STATUS_LABELS,
  type OrganizationErrorPresentation,
  organizationErrorPresentation,
  timezoneOptions,
} from "./organization-presentation";

interface LegalEntityFormProps {
  entity: LegalEntity;
  canEdit: boolean;
  onUpdated: (entity: LegalEntity) => void;
}

interface LegalEntityDraft {
  name: string;
  registeredName: string;
  countryCode: string;
  taxNumber: string;
  timezone: string;
  status: LegalEntityStatus;
}

function draftFor(entity: LegalEntity): LegalEntityDraft {
  return {
    name: entity.name,
    registeredName: entity.registered_name,
    countryCode: entity.country_code ?? "",
    taxNumber: entity.tax_number ?? "",
    timezone: entity.timezone,
    status: entity.status,
  };
}

function nullableValue(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

export function LegalEntityForm({
  entity,
  canEdit,
  onUpdated,
}: LegalEntityFormProps) {
  const [draft, setDraft] = useState<LegalEntityDraft>(() => draftFor(entity));
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<OrganizationErrorPresentation | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const timezones = useMemo(() => timezoneOptions(draft.timezone), [draft.timezone]);

  function resetDraft() {
    setDraft(draftFor(entity));
    setError(null);
    setSuccess(null);
    setIsEditing(false);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit || !isEditing || isSaving) {
      return;
    }

    const name = draft.name.trim();
    const registeredName = draft.registeredName.trim();
    const countryCode = nullableValue(draft.countryCode)?.toUpperCase() ?? null;
    const taxNumber = nullableValue(draft.taxNumber);
    const update: LegalEntityUpdateRequest = {};
    if (name !== entity.name) update.name = name;
    if (registeredName !== entity.registered_name) update.registered_name = registeredName;
    if (countryCode !== entity.country_code) update.country_code = countryCode;
    if (taxNumber !== entity.tax_number) {
      update.tax_number = taxNumber;
    }
    if (draft.timezone !== entity.timezone) update.timezone = draft.timezone;
    if (draft.status !== entity.status) update.status = draft.status;

    if (Object.keys(update).length === 0) {
      setError(null);
      setSuccess("Kaydedilecek yeni bir değişiklik yok.");
      setIsEditing(false);
      return;
    }

    setError(null);
    setSuccess(null);
    setIsSaving(true);
    try {
      const updatedEntity = await updateLegalEntity(entity.id, update);
      setDraft(draftFor(updatedEntity));
      setSuccess("Tüzel kişilik bilgileri güncellendi.");
      setIsEditing(false);
      onUpdated(updatedEntity);
    } catch (cause) {
      setError(organizationErrorPresentation(cause, "legal_update"));
    } finally {
      setIsSaving(false);
    }
  }

  const controlsDisabled = !isEditing || isSaving;

  return (
    <article className={styles.entityCard} aria-labelledby="legal-entity-title">
      <header className={styles.cardHeader}>
        <div>
          <span>Tüzel kişilik ayarları</span>
          <h2 id="legal-entity-title">{entity.name}</h2>
          <p>Sabit kod: <strong>{entity.code}</strong></p>
        </div>
        {canEdit && !isEditing ? (
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={() => {
              setError(null);
              setSuccess(null);
              setIsEditing(true);
            }}
          >
            Bilgileri düzenle
          </button>
        ) : null}
      </header>

      {error ? (
        <div className={styles.errorAlert} role="alert">
          <strong>Değişiklik kaydedilemedi</strong>
          <span>{error.message}</span>
          {error.reference ? <small>Referans: {error.reference}</small> : null}
        </div>
      ) : null}
      {success ? (
        <div className={styles.successAlert} role="status">{success}</div>
      ) : null}

      <form className={styles.entityForm} onSubmit={handleSubmit}>
        <div className={styles.formGrid}>
          <div className={styles.formField}>
            <label htmlFor="legal_entity_code">Sabit kod</label>
            <input id="legal_entity_code" value={entity.code} readOnly />
            <small>Geçmiş kayıtların tutarlılığı için değiştirilemez.</small>
          </div>
          <div className={styles.formField}>
            <label htmlFor="legal_entity_name">Görünen ad</label>
            <input
              id="legal_entity_name"
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              required
              minLength={1}
              maxLength={200}
              disabled={controlsDisabled}
            />
          </div>
          <div className={`${styles.formField} ${styles.wideField}`}>
            <label htmlFor="legal_entity_registered_name">Tescilli unvan</label>
            <input
              id="legal_entity_registered_name"
              value={draft.registeredName}
              onChange={(event) =>
                setDraft({ ...draft, registeredName: event.target.value })
              }
              required
              minLength={1}
              maxLength={240}
              disabled={controlsDisabled}
            />
          </div>
          <div className={styles.formField}>
            <label htmlFor="legal_entity_country">Ülke kodu</label>
            <input
              id="legal_entity_country"
              value={draft.countryCode}
              onChange={(event) =>
                setDraft({ ...draft, countryCode: event.target.value.toUpperCase() })
              }
              placeholder="TR"
              minLength={2}
              maxLength={2}
              pattern="[A-Za-z]{2}"
              disabled={controlsDisabled}
            />
          </div>
          <div className={styles.formField}>
            <label htmlFor="legal_entity_tax_number">Vergi numarası</label>
            <input
              id="legal_entity_tax_number"
              value={draft.taxNumber}
              onChange={(event) =>
                setDraft({ ...draft, taxNumber: event.target.value })
              }
              maxLength={64}
              disabled={controlsDisabled}
            />
          </div>
          <div className={styles.formField}>
            <label htmlFor="legal_entity_timezone">Varsayılan saat dilimi</label>
            <select
              id="legal_entity_timezone"
              value={draft.timezone}
              onChange={(event) => setDraft({ ...draft, timezone: event.target.value })}
              required
              disabled={controlsDisabled}
            >
              {timezones.map((timezone) => (
                <option value={timezone} key={timezone}>{timezone}</option>
              ))}
            </select>
          </div>
          <div className={styles.formField}>
            <label htmlFor="legal_entity_status">Durum</label>
            <select
              id="legal_entity_status"
              value={draft.status}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  status: event.target.value as LegalEntityStatus,
                })
              }
              disabled={controlsDisabled || entity.is_default}
            >
              {Object.entries(LEGAL_ENTITY_STATUS_LABELS).map(([status, label]) => (
                <option value={status} key={status}>{label}</option>
              ))}
            </select>
            {entity.is_default ? (
              <small>Varsayılan tüzel kişilik etkin kalmalıdır.</small>
            ) : null}
          </div>
        </div>

        <footer className={styles.entityFooter}>
          <div className={styles.entityMetadata}>
            <span>{entity.is_default ? "Varsayılan tüzel kişilik" : "Tüzel kişilik"}</span>
            <small>Son güncelleme: {formatOrganizationDate(entity.updated_at)}</small>
          </div>
          {isEditing ? (
            <div className={styles.formActions}>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={resetDraft}
                disabled={isSaving}
              >
                Vazgeç
              </button>
              <button className={styles.primaryButton} type="submit" disabled={isSaving}>
                {isSaving ? "Kaydediliyor…" : "Değişiklikleri kaydet"}
              </button>
            </div>
          ) : null}
        </footer>
      </form>
    </article>
  );
}
