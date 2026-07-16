"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  actOnAnnouncement,
  createAnnouncement,
  listAnnouncements,
  readAnnouncement,
  readAnnouncementTargetOptions,
  updateAnnouncement,
  type AnnouncementDetail,
  type AnnouncementSummary,
  type AnnouncementTargetOptions,
  type AnnouncementTargets,
  type TargetOption,
} from "@/lib/self-service";

import {
  formatDateTime,
  isConflict,
  requestErrorMessage,
  statusLabel,
} from "./presentation";
import styles from "./self-service.module.css";

const EMPTY_TARGETS: AnnouncementTargets = {
  role_ids: [],
  department_ids: [],
  branch_ids: [],
};

function appendUnique(
  current: AnnouncementSummary[],
  incoming: AnnouncementSummary[],
): AnnouncementSummary[] {
  const values = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) values.set(item.id, item);
  return [...values.values()];
}

function TargetCheckboxes({
  label,
  options,
  selected,
  disabled,
  onChange,
}: {
  label: string;
  options: TargetOption[];
  selected: string[];
  disabled: boolean;
  onChange: (ids: string[]) => void;
}) {
  return (
    <fieldset className={styles.checkboxGroup} disabled={disabled}>
      <legend>{label}</legend>
      <div className={styles.checkboxes}>
        {options.length === 0 ? (
          <span className={styles.muted}>Aktif seçenek yok</span>
        ) : (
          options.map((option) => (
            <label key={option.id}>
              <input
                type="checkbox"
                checked={selected.includes(option.id)}
                disabled={selected.length >= 20 && !selected.includes(option.id)}
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [...selected, option.id]
                      : selected.filter((id) => id !== option.id),
                  )
                }
              />
              <span>{option.label}</span>
            </label>
          ))
        )}
      </div>
    </fieldset>
  );
}

export function AnnouncementManagementScreen() {
  const { sessionGeneration, user } = useSession();
  const [items, setItems] = useState<AnnouncementSummary[]>([]);
  const [options, setOptions] = useState<AnnouncementTargetOptions | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [editing, setEditing] = useState<AnnouncementDetail | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [isCritical, setIsCritical] = useState(false);
  const [targets, setTargets] = useState<AnnouncementTargets>(EMPTY_TARGETS);
  const saveCommand = useRef<{ fingerprint: string; key: string } | null>(null);
  const lifecycleCommand = useRef<{ fingerprint: string; key: string } | null>(null);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setIsLoading(true);
      setError(null);
    });
    void Promise.all([
      listAnnouncements({ scope: "manage" }),
      readAnnouncementTargetOptions(),
    ]).then(
      ([page, targetOptions]) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.nextCursor);
        setOptions(targetOptions);
        setIsLoading(false);
      },
      (cause) => {
        if (!active) return;
        setItems([]);
        setNextCursor(null);
        setOptions(null);
        setError(requestErrorMessage(cause, "Duyuru yönetimi yüklenemedi."));
        setIsLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey, sessionGeneration, user.tenant_id]);

  function resetForm() {
    setEditing(null);
    setTitle("");
    setBody("");
    setIsCritical(false);
    setTargets(EMPTY_TARGETS);
  }

  async function edit(item: AnnouncementSummary) {
    if (pendingId || item.status !== "draft") return;
    setPendingId(item.id);
    setError(null);
    try {
      const detail = await readAnnouncement(item.id, "manage");
      setEditing(detail);
      setTitle(detail.title);
      setBody(detail.body);
      setIsCritical(detail.is_critical);
      setTargets(detail.targets ?? EMPTY_TARGETS);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (cause) {
      setError(requestErrorMessage(cause, "Taslak yüklenemedi."));
    } finally {
      setPendingId(null);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving || title.trim() === "" || body.trim() === "") return;
    setIsSaving(true);
    setError(null);
    setNotice(null);
    try {
      const input = {
        title: title.trim(),
        body: body.trim(),
        is_critical: isCritical,
        targets,
      };
      const fingerprint = JSON.stringify({
        tenantId: user.tenant_id,
        announcementId: editing?.id ?? null,
        version: editing?.version ?? null,
        input,
      });
      const previousCommand = saveCommand.current;
      const command =
        previousCommand?.fingerprint === fingerprint
          ? previousCommand
          : { fingerprint, key: crypto.randomUUID() };
      saveCommand.current = command;
      if (editing) {
        await updateAnnouncement(editing.id, editing.version, input, command.key);
        setNotice("Duyuru taslağı güncellendi.");
      } else {
        await createAnnouncement(input, command.key);
        setNotice("Duyuru taslağı oluşturuldu.");
      }
      saveCommand.current = null;
      resetForm();
      setReloadKey((value) => value + 1);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Duyuru taslağı kaydedilemedi."));
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status >= 400 &&
        cause.status < 500
      ) {
        saveCommand.current = null;
      }
      if (isConflict(cause)) {
        resetForm();
        setReloadKey((value) => value + 1);
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function lifecycleAction(
    item: AnnouncementSummary,
    action: "publish" | "archive",
  ) {
    if (pendingId) return;
    setPendingId(item.id);
    setError(null);
    setNotice(null);
    const fingerprint = JSON.stringify({
      tenantId: user.tenant_id,
      announcementId: item.id,
      version: item.version,
      action,
    });
    const previousCommand = lifecycleCommand.current;
    const command =
      previousCommand?.fingerprint === fingerprint
        ? previousCommand
        : { fingerprint, key: crypto.randomUUID() };
    lifecycleCommand.current = command;
    try {
      await actOnAnnouncement(item.id, action, item.version, command.key);
      lifecycleCommand.current = null;
      setNotice(
        action === "publish"
          ? "Duyuru hedef kitlesi sabitlenerek yayınlandı."
          : "Duyuru arşivlendi.",
      );
      if (editing?.id === item.id) resetForm();
      setReloadKey((value) => value + 1);
    } catch (cause) {
      setError(
        requestErrorMessage(
          cause,
          action === "publish" ? "Duyuru yayınlanamadı." : "Duyuru arşivlenemedi.",
        ),
      );
      if (
        cause instanceof ApiClientError &&
        cause.status !== null &&
        cause.status >= 400 &&
        cause.status < 500
      ) {
        lifecycleCommand.current = null;
      }
      if (isConflict(cause)) setReloadKey((value) => value + 1);
    } finally {
      setPendingId(null);
    }
  }

  async function loadMore() {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setError(null);
    try {
      const page = await listAnnouncements({ scope: "manage", cursor: nextCursor });
      setItems((current) => appendUnique(current, page.items));
      setNextCursor(page.nextCursor);
    } catch (cause) {
      setError(requestErrorMessage(cause, "Daha fazla duyuru yüklenemedi."));
    } finally {
      setIsLoadingMore(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>HR duyuru yönetimi</span>
          <h1>Duyurular</h1>
          <p>
            Taslağı hazırlayın, rol/departman/şube hedefini belirleyin ve yayın anında görünür
            alıcıları sabitleyin.
          </p>
        </div>
      </header>

      {error ? <div className={styles.errorBanner} role="alert">{error}</div> : null}
      {notice ? <div className={styles.successBanner} role="status">{notice}</div> : null}

      <form className={styles.formCard} onSubmit={(event) => void save(event)}>
        <div>
          <span className={styles.eyebrow}>{editing ? "Taslağı düzenle" : "Yeni taslak"}</span>
          <h2>{editing ? editing.title : "Duyuru hazırlayın"}</h2>
          <p className={styles.muted}>
            Metin düz yazı olarak saklanır. Boş bırakılan tüm hedef boyutları tenant genelini
            kapsar; dolu boyutlar kendi içinde VEYA, boyutlar arasında VE uygulanır.
          </p>
        </div>
        <div className={styles.formGrid}>
          <div className={`${styles.field} ${styles.fieldFull}`}>
            <label htmlFor="announcement-title">Başlık</label>
            <input
              id="announcement-title"
              maxLength={200}
              value={title}
              disabled={isSaving}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>
          <div className={`${styles.field} ${styles.fieldFull}`}>
            <label htmlFor="announcement-body">Duyuru metni</label>
            <textarea
              id="announcement-body"
              maxLength={10000}
              value={body}
              disabled={isSaving}
              onChange={(event) => setBody(event.target.value)}
            />
            <span className={styles.muted}>{body.length}/10000</span>
          </div>
          <label className={`${styles.criticalCheck} ${styles.fieldFull}`}>
            <input
              type="checkbox"
              checked={isCritical}
              disabled={isSaving}
              onChange={(event) => setIsCritical(event.target.checked)}
            />
            Çalışanın tek yönlü okudum onayı vermesi gereken kritik duyuru
          </label>
          <TargetCheckboxes
            label="Roller"
            options={options?.roles ?? []}
            selected={targets.role_ids}
            disabled={isSaving || !options}
            onChange={(roleIds) => setTargets((value) => ({ ...value, role_ids: roleIds }))}
          />
          <TargetCheckboxes
            label="Departmanlar"
            options={options?.departments ?? []}
            selected={targets.department_ids}
            disabled={isSaving || !options}
            onChange={(departmentIds) =>
              setTargets((value) => ({ ...value, department_ids: departmentIds }))
            }
          />
          <TargetCheckboxes
            label="Şubeler"
            options={options?.branches ?? []}
            selected={targets.branch_ids}
            disabled={isSaving || !options}
            onChange={(branchIds) =>
              setTargets((value) => ({ ...value, branch_ids: branchIds }))
            }
          />
        </div>
        <div className={styles.actions}>
          {editing ? (
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isSaving}
              onClick={resetForm}
            >
              Düzenlemeyi kapat
            </button>
          ) : null}
          <button
            className={styles.primaryButton}
            type="submit"
            disabled={isSaving || !options || title.trim() === "" || body.trim() === ""}
          >
            {isSaving ? "Taslak kaydediliyor…" : editing ? "Taslağı güncelle" : "Taslak oluştur"}
          </button>
        </div>
      </form>

      <section className={styles.sectionCard} aria-labelledby="managed-announcement-list-title">
        <header className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Yaşam döngüsü</span>
            <h2 id="managed-announcement-list-title">Duyuru kayıtları</h2>
          </div>
          <strong>{isLoading ? "—" : items.length}</strong>
        </header>
        {isLoading ? (
          <div className={styles.loadingState} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Duyurular yükleniyor</strong>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>Henüz duyuru yok</strong>
            <p>İlk taslağı yukarıdaki formdan oluşturabilirsiniz.</p>
          </div>
        ) : (
          <ul className={styles.list}>
            {items.map((item) => (
              <li className={styles.listItem} key={item.id}>
                <div>
                  <div className={styles.badges}>
                    <span className={styles.badge}>{statusLabel(item.status)}</span>
                    {item.is_critical ? (
                      <span className={styles.criticalBadge}>Kritik</span>
                    ) : null}
                  </div>
                  <h3>{item.title}</h3>
                  <p>
                    {item.published_at
                      ? `Yayın: ${formatDateTime(item.published_at)}`
                      : `Taslak: ${formatDateTime(item.updated_at)}`}
                  </p>
                </div>
                <div className={styles.actions}>
                  {item.status === "draft" ? (
                    <>
                      <button
                        className={styles.textButton}
                        type="button"
                        disabled={pendingId !== null}
                        onClick={() => void edit(item)}
                      >
                        Düzenle
                      </button>
                      <button
                        className={styles.primaryButton}
                        type="button"
                        disabled={pendingId !== null}
                        onClick={() => void lifecycleAction(item, "publish")}
                      >
                        {pendingId === item.id ? "Yayınlanıyor…" : "Yayınla"}
                      </button>
                    </>
                  ) : null}
                  {item.status === "published" ? (
                    <button
                      className={styles.dangerButton}
                      type="button"
                      disabled={pendingId !== null}
                      onClick={() => void lifecycleAction(item, "archive")}
                    >
                      {pendingId === item.id ? "Arşivleniyor…" : "Arşivle"}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
        {nextCursor ? (
          <div className={styles.loadMore}>
            <button
              className={styles.secondaryButton}
              type="button"
              disabled={isLoadingMore}
              onClick={() => void loadMore()}
            >
              {isLoadingMore ? "Duyurular yükleniyor…" : "Daha fazla göster"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
