"use client";

import Link from "next/link";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import type { EmployeeAssignment } from "@/lib/employee-assignments";
import {
  type EmployeeEmploymentProfile,
  type EmployeeEmploymentProfileUpdate,
  type EmployeeEmploymentProfileUpdateResult,
  type EmployeeContractType,
  type EmployeePersonalProfile,
  type EmployeePersonalProfileUpdate,
  type EmployeePersonalProfileUpdateResult,
  type EmployeeProfile,
  type EmployeeProfileCore,
  type EmployeeWorkType,
  readEmployeeProfile,
  updateEmployeeEmploymentProfile,
  updateEmployeePersonalProfile,
} from "@/lib/employee-profile";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";

import { formatEmployeeDate } from "./employee-presentation";
import { EmployeeStatusBadge } from "./employee-status-badge";
import styles from "./employees.module.css";

type ProfileTab = "summary" | "personal" | "employment" | "organization";
type ProfileAction = "read" | "personal" | "employment";

interface ProfileErrorPresentation {
  message: string;
  reference: string | null;
  conflict: boolean;
}

const PROFILE_TABS: ReadonlyArray<{ id: ProfileTab; label: string }> = [
  { id: "summary", label: "Özet" },
  { id: "personal", label: "Kişisel" },
  { id: "employment", label: "İstihdam" },
  { id: "organization", label: "Organizasyon" },
];

const CONTRACT_TYPE_LABELS = {
  indefinite: "Belirsiz süreli",
  fixed_term: "Belirli süreli",
} as const;

const WORK_TYPE_LABELS = {
  full_time: "Tam zamanlı",
  part_time: "Yarı zamanlı",
} as const;

function fullName(core: EmployeeProfileCore): string {
  return `${core.first_name} ${core.last_name}`.trim();
}

function optionalText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function profileErrorPresentation(
  cause: unknown,
  action: ProfileAction,
): ProfileErrorPresentation {
  let message =
    action === "read"
      ? "Çalışan profili şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : action === "personal"
        ? "Kişisel bilgiler şu anda kaydedilemiyor. Lütfen yeniden deneyin."
        : "İstihdam bilgileri şu anda kaydedilemiyor. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;

  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message =
      action === "read"
        ? "Tenant çalışan kayıtlarını görüntüleme yetkiniz bulunmuyor."
        : "Bu çalışan profilini güncellemek için gerekli İK yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Çalışan bulunamadı veya artık bu çalışma alanında değil.";
  } else if (cause.status === 409 && cause.code === "concurrent_write_conflict") {
    message =
      "Bu bölüm siz düzenlerken değişti. Güncel veriyi yükleyip değişikliklerinizi yeniden uygulayın.";
    conflict = true;
  } else if (
    cause.status === 409 &&
    (cause.code === "employee_email_conflict" ||
      cause.code === "employee_work_email_conflict")
  ) {
    message = "Bu iş e-postası çalışma alanında başka bir çalışanda kullanılıyor.";
  } else if (cause.status === 409) {
    message = "Çalışan kaydı mevcut verilerle çakışıyor. Güncel veriyi yükleyin.";
    conflict = true;
  } else if (cause.status === 422) {
    message =
      action === "personal"
        ? "Ad, soyad, iş e-postası, doğum tarihi ve telefon alanlarını kontrol edin."
        : action === "employment"
          ? "Başlangıç tarihi, sözleşme türü ve çalışma türünü kontrol edin."
          : "Çalışan bağlantısı geçerli değil. Dizine dönüp kaydı yeniden açın.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference, conflict };
}

function SummaryPanel({ profile }: { profile: EmployeeProfile }) {
  const assignment = profile.organization.current_assignment;
  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Çalışan ana verisi</span>
          <h2>Genel bakış</h2>
          <p>Temel kimlik, çalışma durumu ve güncel organizasyon özeti.</p>
        </div>
      </header>

      <dl className={styles.profileMetadataGrid}>
        <div>
          <dt>Çalışan numarası</dt>
          <dd>{profile.core.employee_number}</dd>
        </div>
        <div>
          <dt>İş e-postası</dt>
          <dd>{profile.core.email ?? "Eklenmemiş"}</dd>
        </div>
        <div>
          <dt>Tercih edilen ad</dt>
          <dd>{profile.personal.preferred_name ?? "Belirtilmemiş"}</dd>
        </div>
        <div>
          <dt>İşe başlangıç</dt>
          <dd>{formatEmployeeDate(profile.employment.employment_start_date)}</dd>
        </div>
        <div>
          <dt>Sözleşme türü</dt>
          <dd>
            {profile.employment.contract_type
              ? CONTRACT_TYPE_LABELS[profile.employment.contract_type]
              : "Belirtilmemiş"}
          </dd>
        </div>
        <div>
          <dt>Çalışma türü</dt>
          <dd>
            {profile.employment.work_type
              ? WORK_TYPE_LABELS[profile.employment.work_type]
              : "Belirtilmemiş"}
          </dd>
        </div>
      </dl>

      <section className={styles.profileAssignmentSummary} aria-labelledby="profile-summary-org">
        <header>
          <span>Güncel organizasyon</span>
          <h3 id="profile-summary-org">Yapısal atama</h3>
        </header>
        {assignment ? (
          <dl className={styles.profileOrganizationGrid}>
            <div>
              <dt>Tüzel kişilik</dt>
              <dd>{assignment.legal_entity.name}</dd>
              <small>{assignment.legal_entity.code}</small>
            </div>
            <div>
              <dt>Şube</dt>
              <dd>{assignment.branch.name}</dd>
              <small>{assignment.branch.code}</small>
            </div>
            <div>
              <dt>Departman</dt>
              <dd>{assignment.department.name}</dd>
              <small>{assignment.department.code}</small>
            </div>
            <div>
              <dt>Pozisyon</dt>
              <dd>{assignment.position.title}</dd>
              <small>{assignment.position.code}</small>
            </div>
          </dl>
        ) : (
          <div className={styles.profileEmptyState}>
            <span aria-hidden="true">O</span>
            <div>
              <strong>Henüz yapısal atama yok</strong>
              <p>Organizasyon bilgileri mevcut atama çalışma alanında yönetilir.</p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ReadOnlyPersonal({
  core,
  personal,
}: {
  core: EmployeeProfileCore;
  personal: EmployeePersonalProfile;
}) {
  return (
    <dl className={styles.profileMetadataGrid}>
      <div><dt>Ad</dt><dd>{core.first_name}</dd></div>
      <div><dt>Soyad</dt><dd>{core.last_name}</dd></div>
      <div><dt>İş e-postası</dt><dd>{core.email ?? "Eklenmemiş"}</dd></div>
      <div><dt>Tercih edilen ad</dt><dd>{personal.preferred_name ?? "Belirtilmemiş"}</dd></div>
      <div><dt>Doğum tarihi</dt><dd>{formatEmployeeDate(personal.birth_date)}</dd></div>
      <div><dt>Telefon</dt><dd>{personal.phone ?? "Belirtilmemiş"}</dd></div>
    </dl>
  );
}

function PersonalPanel({
  employeeId,
  core,
  personal,
  editable,
  onSaved,
  onReload,
}: {
  employeeId: string;
  core: EmployeeProfileCore;
  personal: EmployeePersonalProfile;
  editable: boolean;
  onSaved: (result: EmployeePersonalProfileUpdateResult) => void;
  onReload: () => void;
}) {
  const requestGeneration = useRef(0);
  const savingLock = useRef(false);
  const [firstName, setFirstName] = useState(core.first_name);
  const [lastName, setLastName] = useState(core.last_name);
  const [email, setEmail] = useState(core.email ?? "");
  const [preferredName, setPreferredName] = useState(personal.preferred_name ?? "");
  const [birthDate, setBirthDate] = useState(personal.birth_date ?? "");
  const [phone, setPhone] = useState(personal.phone ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ProfileErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(
    () => () => {
      requestGeneration.current += 1;
    },
    [],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingLock.current) return;
    const payload: EmployeePersonalProfileUpdate = {
      expected_version: personal.version,
    };
    const normalizedFirstName = firstName.trim();
    const normalizedLastName = lastName.trim();
    const normalizedEmail = optionalText(email);
    const normalizedPreferredName = optionalText(preferredName);
    const normalizedBirthDate = optionalText(birthDate);
    const normalizedPhone = optionalText(phone);
    let coreChanged = false;
    let sectionChanged = false;
    if (normalizedFirstName !== core.first_name) {
      payload.first_name = normalizedFirstName;
      coreChanged = true;
    }
    if (normalizedLastName !== core.last_name) {
      payload.last_name = normalizedLastName;
      coreChanged = true;
    }
    if (normalizedEmail !== core.email) {
      payload.email = normalizedEmail;
      coreChanged = true;
    }
    if (normalizedPreferredName !== personal.preferred_name) {
      payload.preferred_name = normalizedPreferredName;
      sectionChanged = true;
    }
    if (normalizedBirthDate !== personal.birth_date) {
      payload.birth_date = normalizedBirthDate;
      sectionChanged = true;
    }
    if (normalizedPhone !== personal.phone) {
      payload.phone = normalizedPhone;
      sectionChanged = true;
    }
    if (!coreChanged && !sectionChanged) {
      setError(null);
      setNotice("Kaydedilecek değişiklik yok.");
      return;
    }
    if (coreChanged) payload.expected_employee_version = core.employee_version;
    savingLock.current = true;
    const generation = ++requestGeneration.current;
    setIsSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await updateEmployeePersonalProfile(employeeId, payload);
      if (generation !== requestGeneration.current) return;
      setFirstName(result.core.first_name);
      setLastName(result.core.last_name);
      setEmail(result.core.email ?? "");
      setPreferredName(result.personal.preferred_name ?? "");
      setBirthDate(result.personal.birth_date ?? "");
      setPhone(result.personal.phone ?? "");
      onSaved(result);
      setNotice("Kişisel bilgiler güncellendi.");
    } catch (cause) {
      if (generation === requestGeneration.current) {
        setError(profileErrorPresentation(cause, "personal"));
      }
    } finally {
      if (generation === requestGeneration.current) {
        savingLock.current = false;
        setIsSaving(false);
      }
    }
  }

  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Onaylı MVP alanları</span>
          <h2>Kişisel bilgiler</h2>
          <p>Temel iletişim ve tercih bilgilerini güvenli çalışan kaydında tutun.</p>
        </div>
      </header>

      {!editable ? (
        <ReadOnlyPersonal core={core} personal={personal} />
      ) : (
        <form className={styles.profileForm} onSubmit={submit}>
          {error ? (
            <div className={styles.profileErrorAlert} role="alert">
              <div>
                <strong>Kişisel bilgiler kaydedilemedi</strong>
                <span>{error.message}</span>
                {error.reference ? <small>Referans: {error.reference}</small> : null}
              </div>
              {error.conflict ? (
                <button className={styles.secondaryButton} type="button" onClick={onReload}>
                  Güncel veriyi yükle
                </button>
              ) : null}
            </div>
          ) : null}
          {notice ? <div className={styles.profileSuccess} role="status">{notice}</div> : null}

          <div className={styles.formGrid}>
            <div className={styles.formField}>
              <label htmlFor="profile_first_name">Ad</label>
              <input id="profile_first_name" value={firstName} onChange={(event) => setFirstName(event.target.value)} required minLength={1} maxLength={200} autoComplete="given-name" disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_last_name">Soyad</label>
              <input id="profile_last_name" value={lastName} onChange={(event) => setLastName(event.target.value)} required minLength={1} maxLength={200} autoComplete="family-name" disabled={isSaving} />
            </div>
            <div className={`${styles.formField} ${styles.wideField}`}>
              <label htmlFor="profile_work_email">İş e-postası</label>
              <input id="profile_work_email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" inputMode="email" maxLength={320} autoComplete="email" autoCapitalize="none" spellCheck={false} disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_preferred_name">Tercih edilen ad</label>
              <input id="profile_preferred_name" value={preferredName} onChange={(event) => setPreferredName(event.target.value)} maxLength={200} autoComplete="nickname" disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_birth_date">Doğum tarihi</label>
              <input id="profile_birth_date" value={birthDate} onChange={(event) => setBirthDate(event.target.value)} type="date" autoComplete="bday" disabled={isSaving} />
            </div>
            <div className={`${styles.formField} ${styles.wideField}`}>
              <label htmlFor="profile_phone">Telefon</label>
              <input id="profile_phone" value={phone} onChange={(event) => setPhone(event.target.value)} type="tel" inputMode="tel" maxLength={32} autoComplete="tel" disabled={isSaving} />
            </div>
          </div>
          <div className={styles.profileFormActions}>
            <button className={styles.primaryButton} type="submit" disabled={isSaving}>
              {isSaving ? "Kişisel bilgiler kaydediliyor…" : "Kişisel bilgileri kaydet"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function ReadOnlyEmployment({ employment }: { employment: EmployeeEmploymentProfile }) {
  return (
    <dl className={styles.profileMetadataGrid}>
      <div><dt>İşe başlangıç tarihi</dt><dd>{formatEmployeeDate(employment.employment_start_date)}</dd></div>
      <div><dt>Sözleşme türü</dt><dd>{employment.contract_type ? CONTRACT_TYPE_LABELS[employment.contract_type] : "Belirtilmemiş"}</dd></div>
      <div><dt>Çalışma türü</dt><dd>{employment.work_type ? WORK_TYPE_LABELS[employment.work_type] : "Belirtilmemiş"}</dd></div>
    </dl>
  );
}

function EmploymentPanel({
  employeeId,
  core,
  employment,
  editable,
  onSaved,
  onReload,
}: {
  employeeId: string;
  core: EmployeeProfileCore;
  employment: EmployeeEmploymentProfile;
  editable: boolean;
  onSaved: (result: EmployeeEmploymentProfileUpdateResult) => void;
  onReload: () => void;
}) {
  const requestGeneration = useRef(0);
  const savingLock = useRef(false);
  const [startDate, setStartDate] = useState(employment.employment_start_date);
  const [contractType, setContractType] = useState<EmployeeContractType | "">(
    employment.contract_type ?? "",
  );
  const [workType, setWorkType] = useState<EmployeeWorkType | "">(
    employment.work_type ?? "",
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<ProfileErrorPresentation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(
    () => () => {
      requestGeneration.current += 1;
    },
    [],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingLock.current) return;
    const payload: EmployeeEmploymentProfileUpdate = {
      expected_version: employment.version,
    };
    const normalizedContractType = contractType || null;
    const normalizedWorkType = workType || null;
    let coreChanged = false;
    let sectionChanged = false;
    if (startDate !== employment.employment_start_date) {
      payload.employment_start_date = startDate;
      coreChanged = true;
    }
    if (normalizedContractType !== employment.contract_type) {
      payload.contract_type = normalizedContractType;
      sectionChanged = true;
    }
    if (normalizedWorkType !== employment.work_type) {
      payload.work_type = normalizedWorkType;
      sectionChanged = true;
    }
    if (!coreChanged && !sectionChanged) {
      setError(null);
      setNotice("Kaydedilecek değişiklik yok.");
      return;
    }
    if (coreChanged) payload.expected_employee_version = core.employee_version;
    savingLock.current = true;
    const generation = ++requestGeneration.current;
    setIsSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await updateEmployeeEmploymentProfile(employeeId, payload);
      if (generation !== requestGeneration.current) return;
      setStartDate(result.employment.employment_start_date);
      setContractType(result.employment.contract_type ?? "");
      setWorkType(result.employment.work_type ?? "");
      onSaved(result);
      setNotice("İstihdam bilgileri güncellendi.");
    } catch (cause) {
      if (generation === requestGeneration.current) {
        setError(profileErrorPresentation(cause, "employment"));
      }
    } finally {
      if (generation === requestGeneration.current) {
        savingLock.current = false;
        setIsSaving(false);
      }
    }
  }

  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Çalışma ilişkisi</span>
          <h2>İstihdam bilgileri</h2>
          <p>Başlangıç, sözleşme ve çalışma türünü yaşam döngüsü aksiyonu açmadan yönetin.</p>
        </div>
      </header>

      {!editable ? (
        <ReadOnlyEmployment employment={employment} />
      ) : (
        <form className={styles.profileForm} onSubmit={submit}>
          {error ? (
            <div className={styles.profileErrorAlert} role="alert">
              <div>
                <strong>İstihdam bilgileri kaydedilemedi</strong>
                <span>{error.message}</span>
                {error.reference ? <small>Referans: {error.reference}</small> : null}
              </div>
              {error.conflict ? (
                <button className={styles.secondaryButton} type="button" onClick={onReload}>
                  Güncel veriyi yükle
                </button>
              ) : null}
            </div>
          ) : null}
          {notice ? <div className={styles.profileSuccess} role="status">{notice}</div> : null}

          <div className={styles.formGrid}>
            <div className={`${styles.formField} ${styles.wideField}`}>
              <label htmlFor="profile_employment_start">İşe başlangıç tarihi</label>
              <input id="profile_employment_start" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required disabled={isSaving} />
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_contract_type">Sözleşme türü</label>
              <select id="profile_contract_type" value={contractType} onChange={(event) => setContractType(event.target.value as typeof contractType)} disabled={isSaving}>
                <option value="">Belirtilmedi</option>
                <option value="indefinite">Belirsiz süreli</option>
                <option value="fixed_term">Belirli süreli</option>
              </select>
            </div>
            <div className={styles.formField}>
              <label htmlFor="profile_work_type">Çalışma türü</label>
              <select id="profile_work_type" value={workType} onChange={(event) => setWorkType(event.target.value as typeof workType)} disabled={isSaving}>
                <option value="">Belirtilmedi</option>
                <option value="full_time">Tam zamanlı</option>
                <option value="part_time">Yarı zamanlı</option>
              </select>
            </div>
          </div>
          <div className={styles.profileFormActions}>
            <button className={styles.primaryButton} type="submit" disabled={isSaving}>
              {isSaving ? "İstihdam bilgileri kaydediliyor…" : "İstihdam bilgilerini kaydet"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function assignmentStatus(assignment: EmployeeAssignment): string {
  return assignment.is_current ? "Güncel" : "Geçmiş";
}

function OrganizationPanel({ profile }: { profile: EmployeeProfile }) {
  const { current_assignment: current, history, history_limit: limit } = profile.organization;
  return (
    <div className={styles.profilePanelContent}>
      <header className={styles.profileSectionHeader}>
        <div>
          <span>Phase 3 kaynak verisi</span>
          <h2>Organizasyon</h2>
          <p>Güncel atama ve korunmuş geçmiş burada salt okunur sunulur.</p>
        </div>
        <span className={styles.readOnlyBadge}>Salt okunur</span>
      </header>

      {current ? (
        <section className={styles.currentAssignmentCard} aria-labelledby="current-profile-assignment">
          <header>
            <div>
              <span>Güncel atama</span>
              <h3 id="current-profile-assignment">{current.position.title}</h3>
            </div>
            <span className={styles.currentBadge}>Güncel</span>
          </header>
          <dl className={styles.profileOrganizationGrid}>
            <div><dt>Tüzel kişilik</dt><dd>{current.legal_entity.name}</dd><small>{current.legal_entity.code}</small></div>
            <div><dt>Şube</dt><dd>{current.branch.name}</dd><small>{current.branch.code}</small></div>
            <div><dt>Departman</dt><dd>{current.department.name}</dd><small>{current.department.code}</small></div>
            <div><dt>Yönetici</dt><dd>{current.manager?.full_name ?? "Yönetici yok"}</dd><small>{current.manager?.email ?? "—"}</small></div>
          </dl>
        </section>
      ) : (
        <div className={styles.profileEmptyState}>
          <span aria-hidden="true">O</span>
          <div><strong>Henüz yapısal atama yok</strong><p>Atamalar organizasyon çalışma alanında yönetilir.</p></div>
        </div>
      )}

      <section className={styles.assignmentHistorySection} aria-labelledby="profile-assignment-history">
        <header>
          <div>
            <h3 id="profile-assignment-history">Atama geçmişi</h3>
            <p>En fazla {limit} korunmuş atama, en yeniden eskiye gösterilir.</p>
          </div>
        </header>
        {history.length === 0 ? (
          <div className={styles.profileHistoryEmpty}>Gösterilecek atama geçmişi bulunmuyor.</div>
        ) : (
          <div className={styles.profileTableScroller}>
            <table className={styles.profileHistoryTable} aria-label="Atama geçmişi">
              <thead><tr><th scope="col">Yapı</th><th scope="col">Pozisyon</th><th scope="col">Yönetici</th><th scope="col">Yürürlük</th><th scope="col">Neden</th><th scope="col">Durum</th></tr></thead>
              <tbody>
                {history.map((assignment) => (
                  <tr key={assignment.id}>
                    <td data-label="Yapı"><strong>{assignment.department.name}</strong><small>{assignment.legal_entity.code} · {assignment.branch.name}</small></td>
                    <td data-label="Pozisyon"><strong>{assignment.position.title}</strong><small>{assignment.position.code}</small></td>
                    <td data-label="Yönetici"><strong>{assignment.manager?.full_name ?? "Yönetici yok"}</strong><small>{assignment.manager?.email ?? "—"}</small></td>
                    <td data-label="Yürürlük"><strong>{formatEmployeeDate(assignment.effective_from)}</strong><small>{assignment.effective_to ? formatEmployeeDate(assignment.effective_to) : "Devam ediyor"}</small></td>
                    <td data-label="Neden">{assignment.change_reason ?? "İlk atama"}</td>
                    <td data-label="Durum"><span className={assignment.is_current ? styles.currentBadge : styles.historyBadge}>{assignmentStatus(assignment)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {profile.organization.history_truncated ? (
          <div className={styles.historyTruncationNotice} role="note">
            İlk {limit} atama kaydı gösteriliyor. Daha eski kayıtlar bu görünümde sınırlandırıldı.
          </div>
        ) : null}
      </section>
    </div>
  );
}

export function Employee360Screen({ employeeId }: { employeeId: string }) {
  const { user } = useSession();
  const canUpdate = hasPermission(user, AUTHORIZATION_PERMISSIONS.updateEmployees);
  const [profile, setProfile] = useState<EmployeeProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ProfileErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [activeTab, setActiveTab] = useState<ProfileTab>("summary");
  const tabRefs = useRef<Partial<Record<ProfileTab, HTMLButtonElement>>>({});

  useEffect(() => {
    let isActive = true;
    void readEmployeeProfile(employeeId).then(
      (loadedProfile) => {
        if (!isActive) return;
        setProfile(loadedProfile);
        setError(null);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) return;
        setProfile(null);
        setError(profileErrorPresentation(cause, "read"));
        setIsLoading(false);
      },
    );
    return () => {
      isActive = false;
    };
  }, [employeeId, reloadKey]);

  function reload() {
    setProfile(null);
    setError(null);
    setIsLoading(true);
    setReloadKey((key) => key + 1);
  }

  function activateTab(tab: ProfileTab, focus = false) {
    setActiveTab(tab);
    if (focus) {
      window.requestAnimationFrame(() => tabRefs.current[tab]?.focus());
    }
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, tab: ProfileTab) {
    const currentIndex = PROFILE_TABS.findIndex((item) => item.id === tab);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % PROFILE_TABS.length;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + PROFILE_TABS.length) % PROFILE_TABS.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = PROFILE_TABS.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    activateTab(PROFILE_TABS[nextIndex].id, true);
  }

  if (isLoading) {
    return (
      <section className={styles.profilePage} aria-busy="true">
        <Link className={styles.profileBackLink} href="/employees">← Çalışanlara dön</Link>
        <div className={styles.profilePageLoading} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          <div><strong>Çalışan profili yükleniyor</strong><span>Employee 360 bölümleri hazırlanıyor…</span></div>
        </div>
      </section>
    );
  }

  if (error || !profile) {
    return (
      <section className={styles.profilePage}>
        <Link className={styles.profileBackLink} href="/employees">← Çalışanlara dön</Link>
        <div className={styles.profilePageError} role="alert">
          <div><strong>Çalışan profili yüklenemedi</strong><span>{error?.message}</span>{error?.reference ? <small>Referans: {error.reference}</small> : null}</div>
          <button className={styles.secondaryButton} type="button" onClick={reload}>Yeniden dene</button>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.profilePage} aria-labelledby="employee-profile-title">
      <Link className={styles.profileBackLink} href="/employees">← Çalışanlara dön</Link>
      <header className={styles.profileHero}>
        <span className={styles.profileHeroAvatar} aria-hidden="true">{profile.core.first_name.slice(0, 1).toLocaleUpperCase("tr-TR")}</span>
        <div className={styles.profileHeroIdentity}>
          <span>Çalışan 360</span>
          <h1 id="employee-profile-title">{fullName(profile.core)}</h1>
          <p>{profile.personal.preferred_name && profile.personal.preferred_name !== profile.core.first_name ? `${profile.personal.preferred_name} · ` : ""}{profile.core.employee_number}{profile.core.email ? ` · ${profile.core.email}` : ""}</p>
        </div>
        <EmployeeStatusBadge status={profile.core.status} />
      </header>

      <div className={styles.profileWorkspace}>
        <div className={styles.profileTabs} role="tablist" aria-label="Çalışan profil bölümleri">
          {PROFILE_TABS.map((tab) => (
            <button
              ref={(node) => { tabRefs.current[tab.id] = node ?? undefined; }}
              className={styles.profileTab}
              id={`employee-profile-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`employee-profile-panel-${tab.id}`}
              tabIndex={activeTab === tab.id ? 0 : -1}
              onClick={() => activateTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, tab.id)}
              key={tab.id}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <section
          className={styles.profilePanel}
          id={`employee-profile-panel-${activeTab}`}
          role="tabpanel"
          aria-labelledby={`employee-profile-tab-${activeTab}`}
          tabIndex={0}
        >
          {activeTab === "summary" ? <SummaryPanel profile={profile} /> : null}
          {activeTab === "personal" ? (
            <PersonalPanel
              employeeId={employeeId}
              core={profile.core}
              personal={profile.personal}
              editable={canUpdate}
              onReload={reload}
              onSaved={(result) => setProfile((current) => current ? { ...current, core: result.core, personal: result.personal } : current)}
            />
          ) : null}
          {activeTab === "employment" ? (
            <EmploymentPanel
              employeeId={employeeId}
              core={profile.core}
              employment={profile.employment}
              editable={canUpdate}
              onReload={reload}
              onSaved={(result) => setProfile((current) => current ? { ...current, core: result.core, employment: result.employment } : current)}
            />
          ) : null}
          {activeTab === "organization" ? <OrganizationPanel profile={profile} /> : null}
        </section>
      </div>
    </section>
  );
}
