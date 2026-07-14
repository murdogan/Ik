"use client";

import {
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useSession } from "@/components/session/session-provider";
import { ApiClientError } from "@/lib/api-client";
import {
  type AccountMembershipStatus,
  type AccountUserStatus,
  type EmployeeAccountLinkState,
  type EmployeeAccountMembership,
  readEmployeeAccountLink,
  searchEligibleEmployeeMemberships,
  updateEmployeeAccountLink,
} from "@/lib/employee-account-links";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import { isSessionGenerationCurrent } from "@/lib/session";

import styles from "./employee-account-link-card.module.css";

interface AccountLinkBoundary {
  sessionGeneration: number;
  userId: string;
  membershipId: string;
  tenantId: string;
  permissionVersion: number;
  permissionGranted: boolean;
  employeeId: string;
}

interface LinkLoadState {
  boundary: AccountLinkBoundary;
  data: EmployeeAccountLinkState | null;
  error: AccountLinkError | null;
  isLoading: boolean;
}

interface SearchState {
  boundary: AccountLinkBoundary;
  query: string;
  results: EmployeeAccountMembership[];
  error: AccountLinkError | null;
  isLoading: boolean;
  hasSearched: boolean;
}

interface AccountLinkError {
  message: string;
  reference: string | null;
  conflict: boolean;
}

type PendingAction =
  | { type: "link"; membership: EmployeeAccountMembership }
  | { type: "unlink"; membership: EmployeeAccountMembership };

type LinkAction = "read" | "search" | "mutation";

const MEMBERSHIP_STATUS_LABELS: Record<AccountMembershipStatus, string> = {
  invited: "Davet bekliyor",
  active: "Aktif",
  locked: "Kilitli",
  disabled: "Devre dışı",
};

const USER_STATUS_LABELS: Record<AccountUserStatus, string> = {
  invited: "Davet bekliyor",
  active: "Aktif",
  locked: "Kilitli",
  disabled: "Devre dışı",
};

function isCurrentBoundary(
  expected: AccountLinkBoundary,
  current: AccountLinkBoundary,
): boolean {
  return (
    isSessionGenerationCurrent(expected.sessionGeneration) &&
    expected.sessionGeneration === current.sessionGeneration &&
    expected.userId === current.userId &&
    expected.membershipId === current.membershipId &&
    expected.tenantId === current.tenantId &&
    expected.permissionVersion === current.permissionVersion &&
    expected.permissionGranted === current.permissionGranted &&
    expected.employeeId === current.employeeId
  );
}

function accountLinkError(cause: unknown, action: LinkAction): AccountLinkError {
  let message =
    action === "read"
      ? "Hesap bağlantısı şu anda yüklenemiyor. Lütfen yeniden deneyin."
      : action === "search"
        ? "Bağlanabilir hesaplar şu anda aranamadı. Lütfen yeniden deneyin."
        : "Hesap bağlantısı şu anda değiştirilemedi. Lütfen yeniden deneyin.";
  let reference: string | null = null;
  let conflict = false;

  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Hesap bağlantılarını yönetmek için gerekli İK yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Çalışan kaydı bulunamadı veya artık bu çalışma alanında değil.";
  } else if (cause.status === 409) {
    message =
      cause.code === "concurrent_write_conflict"
        ? "Hesap bağlantısı siz işlem yaparken değişti. Güncel bağlantıyı yükleyin."
        : "Seçilen hesap artık bağlanabilir değil veya başka bir çalışanla bağlantılı. Güncel durumu yükleyin.";
    conflict = true;
  } else if (cause.status === 422) {
    message =
      action === "search"
        ? "Arama ifadesini kontrol edin ve en az üç karakter girin."
        : "Hesap bağlantısı isteği geçerli değil. Güncel durumu yükleyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }
  return { message, reference, conflict };
}

function AccountLinkConfirmation({
  action,
  currentMembership,
  isSaving,
  onCancel,
  onConfirm,
}: {
  action: PendingAction;
  currentMembership: EmployeeAccountMembership | null;
  isSaving: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const isUnlink = action.type === "unlink";
  const isRelink = action.type === "link" && currentMembership !== null;

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !isSaving) onCancel();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isSaving, onCancel]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>("button:not([disabled])")?.focus();
    });
    return () => {
      window.cancelAnimationFrame(frame);
      previouslyFocused?.focus();
    };
  }, []);

  function handleBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !isSaving) onCancel();
  }

  function keepFocusInDialog(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("button:not([disabled])"),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  const title = isUnlink
    ? "Hesap bağlantısı kaldırılsın mı?"
    : isRelink
      ? "Bağlı hesap değiştirilsin mi?"
      : "Hesap çalışana bağlansın mı?";

  return (
    <div className={styles.dialogBackdrop} onMouseDown={handleBackdrop}>
      <section
        ref={dialogRef}
        className={styles.confirmDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-link-confirm-title"
        aria-describedby="account-link-confirm-description"
        aria-busy={isSaving}
        onKeyDown={keepFocusInDialog}
      >
        <header>
          <span>Hesap bağlantısı onayı</span>
          <h2 id="account-link-confirm-title">{title}</h2>
        </header>
        <div className={styles.confirmBody}>
          <div className={isUnlink ? styles.dangerNotice : styles.confirmNotice}>
            <span aria-hidden="true">!</span>
            <div id="account-link-confirm-description">
              <strong>{action.membership.full_name}</strong>
              <p>
                {isUnlink
                  ? "Bu işlem Profilim erişimini kaldırır; çalışan ve hesap kayıtlarını silmez."
                  : isRelink
                    ? "Mevcut hesap bağlantısı bu hesapla değiştirilecek. Çalışan kaydı korunur."
                    : "Bu hesap yalnızca bu çalışan kaydının Profilim görünümüne bağlanacak."}
              </p>
            </div>
          </div>
          <footer>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={onCancel}
              disabled={isSaving}
            >
              Vazgeç
            </button>
            <button
              className={isUnlink ? styles.dangerButton : styles.primaryButton}
              type="button"
              onClick={onConfirm}
              disabled={isSaving}
            >
              {isSaving
                ? "Bağlantı güncelleniyor…"
                : isUnlink
                  ? "Bağlantıyı kaldır"
                  : isRelink
                    ? "Hesabı değiştir"
                    : "Hesabı bağla"}
            </button>
          </footer>
        </div>
      </section>
    </div>
  );
}

export function EmployeeAccountLinkCard({ employeeId }: { employeeId: string }) {
  const { user, sessionGeneration } = useSession();
  const canManage = hasPermission(user, AUTHORIZATION_PERMISSIONS.updateEmployees);
  const boundary = useMemo<AccountLinkBoundary>(
    () => ({
      sessionGeneration,
      userId: user.id,
      membershipId: user.membership_id,
      tenantId: user.tenant_id,
      permissionVersion: user.permission_version,
      permissionGranted: canManage,
      employeeId,
    }),
    [
      canManage,
      employeeId,
      sessionGeneration,
      user.id,
      user.membership_id,
      user.permission_version,
      user.tenant_id,
    ],
  );
  const latestBoundary = useRef(boundary);
  const loadRequest = useRef(0);
  const searchRequest = useRef(0);
  const mutationRequest = useRef(0);
  const mutationLock = useRef(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [linkState, setLinkState] = useState<LinkLoadState>(() => ({
    boundary,
    data: null,
    error: null,
    isLoading: false,
  }));
  const [draftQuery, setDraftQuery] = useState("");
  const [searchState, setSearchState] = useState<SearchState>(() => ({
    boundary,
    query: "",
    results: [],
    error: null,
    isLoading: false,
    hasSearched: false,
  }));
  const [selectedMembershipId, setSelectedMembershipId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [mutationError, setMutationError] = useState<AccountLinkError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useLayoutEffect(() => {
    latestBoundary.current = boundary;
    return () => {
      loadRequest.current += 1;
      searchRequest.current += 1;
      mutationRequest.current += 1;
      mutationLock.current = false;
    };
  }, [boundary]);

  useEffect(() => {
    if (!isExpanded || !boundary.permissionGranted) return;
    const requestId = ++loadRequest.current;
    const requestBoundary = boundary;

    void readEmployeeAccountLink(requestBoundary.employeeId).then(
      (data) => {
        if (
          requestId !== loadRequest.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setLinkState({
          boundary: requestBoundary,
          data,
          error: null,
          isLoading: false,
        });
      },
      (cause) => {
        if (
          requestId !== loadRequest.current ||
          !isCurrentBoundary(requestBoundary, latestBoundary.current)
        ) {
          return;
        }
        setLinkState({
          boundary: requestBoundary,
          data: null,
          error: accountLinkError(cause, "read"),
          isLoading: false,
        });
      },
    );
    return () => {
      loadRequest.current += 1;
    };
  }, [boundary, isExpanded, reloadKey]);

  const linkStateIsCurrent = isCurrentBoundary(linkState.boundary, boundary);
  const currentData = linkStateIsCurrent ? linkState.data : null;
  const loadError = linkStateIsCurrent ? linkState.error : null;
  const isLoading =
    isExpanded &&
    (!linkStateIsCurrent ||
      linkState.isLoading ||
      (linkState.data === null && linkState.error === null));
  const currentMembership = currentData?.link?.membership ?? null;

  const searchStateIsCurrent = isCurrentBoundary(searchState.boundary, boundary);
  const searchResults = searchStateIsCurrent ? searchState.results : [];
  const searchError = searchStateIsCurrent ? searchState.error : null;
  const isSearching = searchStateIsCurrent && searchState.isLoading;
  const hasSearched = searchStateIsCurrent && searchState.hasSearched;
  const selectedMembership = searchResults.find(
    (membership) => membership.membership_id === selectedMembershipId,
  );

  function reload() {
    setSelectedMembershipId(null);
    setMutationError(null);
    setNotice(null);
    setLinkState({
      boundary,
      data: null,
      error: null,
      isLoading: true,
    });
    setReloadKey((key) => key + 1);
  }

  function toggleExpanded() {
    if (!isExpanded) {
      setLinkState({
        boundary,
        data: null,
        error: null,
        isLoading: true,
      });
      setMutationError(null);
      setNotice(null);
    }
    setIsExpanded((expanded) => !expanded);
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = draftQuery.trim();
    const requestBoundary = boundary;
    if (!requestBoundary.permissionGranted || query.length < 3) return;
    const requestId = ++searchRequest.current;
    setSelectedMembershipId(null);
    setMutationError(null);
    setNotice(null);
    setSearchState({
      boundary: requestBoundary,
      query,
      results: [],
      error: null,
      isLoading: true,
      hasSearched: true,
    });
    try {
      const results = await searchEligibleEmployeeMemberships(
        requestBoundary.employeeId,
        query,
      );
      if (
        requestId !== searchRequest.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setSearchState({
        boundary: requestBoundary,
        query,
        results,
        error: null,
        isLoading: false,
        hasSearched: true,
      });
    } catch (cause) {
      if (
        requestId === searchRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setSearchState({
          boundary: requestBoundary,
          query,
          results: [],
          error: accountLinkError(cause, "search"),
          isLoading: false,
          hasSearched: true,
        });
      }
    }
  }

  async function applyPendingAction() {
    if (
      !pendingAction ||
      !currentData ||
      !boundary.permissionGranted ||
      mutationLock.current
    ) {
      return;
    }
    const action = pendingAction;
    const requestBoundary = boundary;
    const requestId = ++mutationRequest.current;
    mutationLock.current = true;
    setIsSaving(true);
    setMutationError(null);
    setNotice(null);
    try {
      const updated = await updateEmployeeAccountLink(requestBoundary.employeeId, {
        membership_id:
          action.type === "unlink" ? null : action.membership.membership_id,
        expected_version: currentData.link?.version ?? null,
      });
      if (
        requestId !== mutationRequest.current ||
        !isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        return;
      }
      setLinkState({
        boundary: requestBoundary,
        data: updated,
        error: null,
        isLoading: false,
      });
      setPendingAction(null);
      setSelectedMembershipId(null);
      setDraftQuery("");
      setSearchState({
        boundary: requestBoundary,
        query: "",
        results: [],
        error: null,
        isLoading: false,
        hasSearched: false,
      });
      setNotice(
        action.type === "unlink"
          ? "Hesap bağlantısı kaldırıldı."
          : currentData.link
            ? "Bağlı hesap değiştirildi."
            : "Hesap çalışana bağlandı.",
      );
    } catch (cause) {
      if (
        requestId === mutationRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        setPendingAction(null);
        setMutationError(accountLinkError(cause, "mutation"));
      }
    } finally {
      if (
        requestId === mutationRequest.current &&
        isCurrentBoundary(requestBoundary, latestBoundary.current)
      ) {
        mutationLock.current = false;
        setIsSaving(false);
      }
    }
  }

  return (
    <section className={styles.card} aria-labelledby="employee-account-link-title">
      <header className={styles.cardHeader}>
        <div>
          <span>Çalışan hesabı</span>
          <h2 id="employee-account-link-title">Hesap bağlantısı</h2>
          <p>Çalışanın kendi Profilim alanına hangi tenant hesabıyla erişeceğini yönetin.</p>
        </div>
        <button
          className={styles.secondaryButton}
          type="button"
          aria-expanded={isExpanded}
          aria-controls="employee-account-link-content"
          onClick={toggleExpanded}
        >
          {isExpanded ? "Yönetimi kapat" : "Hesap bağlantısını yönet"}
        </button>
      </header>

      {isExpanded ? (
        <div id="employee-account-link-content" className={styles.cardBody}>
          {isLoading ? (
            <div className={styles.loadingState} role="status">
              <span className={styles.spinner} aria-hidden="true" />
              <div>
                <strong>Hesap bağlantısı yükleniyor</strong>
                <span>Güncel tenant üyeliği denetleniyor…</span>
              </div>
            </div>
          ) : loadError || !currentData ? (
            <div className={styles.errorAlert} role="alert">
              <div>
                <strong>Hesap bağlantısı yüklenemedi</strong>
                <span>{loadError?.message}</span>
                {loadError?.reference ? <small>Referans: {loadError.reference}</small> : null}
              </div>
              <button className={styles.secondaryButton} type="button" onClick={reload}>
                Yeniden dene
              </button>
            </div>
          ) : (
            <>
              {mutationError ? (
                <div className={styles.errorAlert} role="alert">
                  <div>
                    <strong>Hesap bağlantısı güncellenemedi</strong>
                    <span>{mutationError.message}</span>
                    {mutationError.reference ? (
                      <small>Referans: {mutationError.reference}</small>
                    ) : null}
                  </div>
                  {mutationError.conflict ? (
                    <button className={styles.secondaryButton} type="button" onClick={reload}>
                      Güncel bağlantıyı yükle
                    </button>
                  ) : null}
                </div>
              ) : null}
              {notice ? <div className={styles.successAlert} role="status">{notice}</div> : null}

              <section className={styles.currentSection} aria-labelledby="current-account-title">
                <header>
                  <div>
                    <span>Güncel durum</span>
                    <h3 id="current-account-title">Bağlı hesap</h3>
                  </div>
                  {currentMembership ? (
                    <span
                      className={
                        currentMembership.eligible
                          ? styles.eligibleBadge
                          : styles.ineligibleBadge
                      }
                    >
                      {currentMembership.eligible
                        ? "Profilim erişimine uygun"
                        : "Erişime uygun değil"}
                    </span>
                  ) : (
                    <span className={styles.neutralBadge}>Bağlantı yok</span>
                  )}
                </header>

                {currentMembership ? (
                  <div className={styles.currentAccount}>
                    <div className={styles.accountIdentity}>
                      <span aria-hidden="true">
                        {currentMembership.full_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
                      </span>
                      <div>
                        <strong>{currentMembership.full_name}</strong>
                        <small>{currentMembership.email}</small>
                      </div>
                    </div>
                    <dl className={styles.statusGrid}>
                      <div>
                        <dt>Tenant üyeliği</dt>
                        <dd>{MEMBERSHIP_STATUS_LABELS[currentMembership.membership_status]}</dd>
                      </div>
                      <div>
                        <dt>Hesap durumu</dt>
                        <dd>{USER_STATUS_LABELS[currentMembership.user_status]}</dd>
                      </div>
                    </dl>
                    {!currentMembership.eligible ? (
                      <p className={styles.warningText} role="note">
                        Bağlantı korunuyor ancak bu hesap şu anda Profilim erişimi için etkin değil.
                      </p>
                    ) : null}
                    <button
                      className={styles.dangerTextButton}
                      type="button"
                      onClick={() =>
                        setPendingAction({ type: "unlink", membership: currentMembership })
                      }
                    >
                      Hesap bağlantısını kaldır
                    </button>
                  </div>
                ) : (
                  <div className={styles.emptyCurrent}>
                    <span aria-hidden="true">P</span>
                    <div>
                      <strong>Bu çalışana bağlı hesap yok</strong>
                      <p>Etkin ve uygun bir tenant hesabı arayarak Profilim erişimini başlatın.</p>
                    </div>
                  </div>
                )}
              </section>

              <section className={styles.searchSection} aria-labelledby="eligible-account-title">
                <header>
                  <span>Bağlanabilir tenant hesapları</span>
                  <h3 id="eligible-account-title">
                    {currentMembership ? "Bağlı hesabı değiştir" : "Hesap seç"}
                  </h3>
                  <p>Sonuçlar tenant ile sınırlıdır; yalnızca üyelik seçimi bağlantıya gönderilir.</p>
                </header>
                <form className={styles.searchForm} role="search" onSubmit={search}>
                  <label htmlFor="eligible_account_search">Ad soyad veya e-posta</label>
                  <div>
                    <input
                      id="eligible_account_search"
                      type="search"
                      value={draftQuery}
                      onChange={(event) => setDraftQuery(event.target.value)}
                      minLength={3}
                      maxLength={100}
                      placeholder="En az 3 karakter"
                      disabled={isSearching || isSaving}
                    />
                    <button
                      className={styles.primaryButton}
                      type="submit"
                      disabled={isSearching || isSaving}
                    >
                      {isSearching ? "Aranıyor…" : "Uygun hesapları ara"}
                    </button>
                  </div>
                </form>

                {searchError ? (
                  <div className={styles.compactError} role="alert">
                    <strong>Hesaplar aranamadı</strong>
                    <span>{searchError.message}</span>
                    {searchError.reference ? <small>Referans: {searchError.reference}</small> : null}
                  </div>
                ) : isSearching ? (
                  <div className={styles.searchLoading} role="status">
                    <span className={styles.spinner} aria-hidden="true" />
                    Bağlanabilir hesaplar aranıyor…
                  </div>
                ) : hasSearched && searchResults.length === 0 ? (
                  <div className={styles.searchEmpty}>
                    <strong>Bağlanabilir hesap bulunamadı</strong>
                    <p>Farklı bir ad veya e-posta parçasıyla yeniden arayın.</p>
                  </div>
                ) : searchResults.length > 0 ? (
                  <fieldset className={styles.resultList}>
                    <legend className={styles.visuallyHidden}>Bağlanacak hesabı seçin</legend>
                    {searchResults.map((membership) => {
                      const isCurrent =
                        membership.membership_id === currentMembership?.membership_id;
                      const selectable = membership.eligible && !isCurrent;
                      return (
                        <label
                          className={`${styles.resultOption} ${!selectable ? styles.disabledOption : ""}`}
                          key={membership.membership_id}
                        >
                          <input
                            type="radio"
                            name="eligible_membership"
                            value={membership.membership_id}
                            checked={selectedMembershipId === membership.membership_id}
                            onChange={() => setSelectedMembershipId(membership.membership_id)}
                            disabled={!selectable || isSaving}
                          />
                          <span className={styles.resultAvatar} aria-hidden="true">
                            {membership.full_name.slice(0, 1).toLocaleUpperCase("tr-TR")}
                          </span>
                          <span className={styles.resultIdentity}>
                            <strong>{membership.full_name}</strong>
                            <small>{membership.email}</small>
                          </span>
                          <span className={selectable ? styles.eligibleBadge : styles.ineligibleBadge}>
                            {isCurrent
                              ? "Zaten bağlı"
                              : membership.eligible
                                ? "Bağlanabilir"
                                : "Uygun değil"}
                          </span>
                        </label>
                      );
                    })}
                  </fieldset>
                ) : null}

                {selectedMembership ? (
                  <div className={styles.selectionActions}>
                    <span>
                      <strong>{selectedMembership.full_name}</strong> seçildi
                    </span>
                    <button
                      className={styles.primaryButton}
                      type="button"
                      onClick={() =>
                        setPendingAction({ type: "link", membership: selectedMembership })
                      }
                      disabled={isSaving}
                    >
                      {currentMembership ? "Bağlı hesabı değiştir" : "Hesabı bağla"}
                    </button>
                  </div>
                ) : null}
              </section>
            </>
          )}
        </div>
      ) : null}

      {pendingAction ? (
        <AccountLinkConfirmation
          action={pendingAction}
          currentMembership={currentMembership}
          isSaving={isSaving}
          onCancel={() => {
            if (!isSaving) setPendingAction(null);
          }}
          onConfirm={() => void applyPendingAction()}
        />
      ) : null}
    </section>
  );
}
