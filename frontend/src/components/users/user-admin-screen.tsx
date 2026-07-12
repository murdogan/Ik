"use client";

import { type FormEvent, useEffect, useState } from "react";

import { useSession } from "@/components/session/session-provider";
import {
  AUTHORIZATION_PERMISSIONS,
  hasPermission,
} from "@/lib/authorization";
import {
  type TenantUser,
  type UserStatus,
  USER_STATUSES,
  listTenantUsers,
} from "@/lib/user-administration";

import { InvitationDialog } from "./invitation-dialog";
import { RoleChips } from "./role-chips";
import { StatusBadge } from "./status-badge";
import { UserDetailDialog } from "./user-detail-dialog";
import styles from "./users.module.css";
import {
  formatUserDate,
  STATUS_LABELS,
  type UserAdminErrorPresentation,
  userAdminErrorPresentation,
} from "./user-presentation";

const PAGE_LIMIT = 25;

interface UserFilters {
  search: string;
  status: UserStatus | "";
}

const EMPTY_FILTERS: UserFilters = { search: "", status: "" };

function userInitial(user: TenantUser): string {
  return (user.full_name.trim() || user.email).slice(0, 1).toLocaleUpperCase("tr-TR");
}

export function UserAdminScreen() {
  const { user: actor } = useSession();
  const canInviteUsers = hasPermission(actor, AUTHORIZATION_PERMISSIONS.inviteUsers);
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [filters, setFilters] = useState<UserFilters>(EMPTY_FILTERS);
  const [draftSearch, setDraftSearch] = useState("");
  const [draftStatus, setDraftStatus] = useState<UserStatus | "">("");
  const [currentCursor, setCurrentCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<UserAdminErrorPresentation | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [isInvitationOpen, setIsInvitationOpen] = useState(false);

  useEffect(() => {
    let isActive = true;

    void listTenantUsers({
      search: filters.search,
      status: filters.status,
      limit: PAGE_LIMIT,
      cursor: currentCursor,
    }).then(
      (page) => {
        if (!isActive) {
          return;
        }
        setUsers(page.data);
        setNextCursor(page.meta.next_cursor);
        setIsLoading(false);
      },
      (cause) => {
        if (!isActive) {
          return;
        }
        setUsers([]);
        setNextCursor(null);
        setError(userAdminErrorPresentation(cause, "list"));
        setIsLoading(false);
      },
    );

    return () => {
      isActive = false;
    };
  }, [currentCursor, filters.search, filters.status, reloadKey]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setSelectedUserId(null);
    setCurrentCursor(null);
    setCursorHistory([]);
    setFilters({ search: draftSearch.trim(), status: draftStatus });
    setReloadKey((key) => key + 1);
  }

  function clearFilters() {
    setIsLoading(true);
    setError(null);
    setDraftSearch("");
    setDraftStatus("");
    setFilters(EMPTY_FILTERS);
    setCurrentCursor(null);
    setCursorHistory([]);
    setSelectedUserId(null);
    setReloadKey((key) => key + 1);
  }

  function showNextPage() {
    if (!nextCursor || isLoading) {
      return;
    }
    setIsLoading(true);
    setError(null);
    setCursorHistory((history) => [...history, currentCursor]);
    setCurrentCursor(nextCursor);
    setSelectedUserId(null);
  }

  function showPreviousPage() {
    if (cursorHistory.length === 0 || isLoading) {
      return;
    }
    setIsLoading(true);
    setError(null);
    const previousCursor = cursorHistory[cursorHistory.length - 1] ?? null;
    setCursorHistory((history) => history.slice(0, -1));
    setCurrentCursor(previousCursor);
    setSelectedUserId(null);
  }

  function applyUpdatedUser(updatedUser: TenantUser) {
    setUsers((currentUsers) =>
      currentUsers.map((user) => (user.id === updatedUser.id ? updatedUser : user)),
    );
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }

  function handleInvitedUser() {
    setIsLoading(true);
    setError(null);
    setCurrentCursor(null);
    setCursorHistory([]);
    setSelectedUserId(null);
    setReloadKey((key) => key + 1);
  }

  const hasFilters = Boolean(filters.search || filters.status);

  return (
    <section className={styles.page} aria-labelledby="users-title">
      <header className={styles.pageHeader}>
        <div>
          <span>Tenant yönetimi</span>
          <h1 id="users-title">Kullanıcılar</h1>
          <p>
            Çalışma alanınızdaki kullanıcıları bulun, hesap durumlarını yönetin ve yeni
            kullanıcı davetleri oluşturun.
          </p>
        </div>
        {canInviteUsers ? (
          <button
            className={styles.primaryButton}
            type="button"
            onClick={() => setIsInvitationOpen(true)}
          >
            <span aria-hidden="true">＋</span>
            Kullanıcı davet et
          </button>
        ) : null}
      </header>

      <form className={styles.filterBar} role="search" onSubmit={applyFilters}>
        <div className={styles.searchField}>
          <label htmlFor="user_search">Kullanıcı ara</label>
          <div>
            <span aria-hidden="true">⌕</span>
            <input
              id="user_search"
              type="search"
              value={draftSearch}
              onChange={(event) => setDraftSearch(event.target.value)}
              placeholder="Ad soyad veya e-posta"
              minLength={3}
              maxLength={100}
            />
          </div>
        </div>

        <div className={styles.statusFilter}>
          <label htmlFor="status_filter">Durum</label>
          <select
            id="status_filter"
            value={draftStatus}
            onChange={(event) => setDraftStatus(event.target.value as UserStatus | "")}
          >
            <option value="">Tüm durumlar</option>
            {USER_STATUSES.map((status) => (
              <option value={status} key={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>

        <button className={styles.filterButton} type="submit" disabled={isLoading}>
          Filtrele
        </button>
        {(hasFilters || draftSearch || draftStatus) && (
          <button className={styles.clearButton} type="button" onClick={clearFilters}>
            Temizle
          </button>
        )}
      </form>

      <div className={styles.listCard} aria-busy={isLoading}>
        <div className={styles.listHeader}>
          <div>
            <h2>Kullanıcı listesi</h2>
            <span>
              {isLoading
                ? "Liste güncelleniyor…"
                : `${users.length} kullanıcı bu sayfada gösteriliyor`}
            </span>
          </div>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={() => {
              setIsLoading(true);
              setError(null);
              setReloadKey((key) => key + 1);
            }}
            disabled={isLoading}
          >
            Yenile
          </button>
        </div>

        {error ? (
          <div className={styles.listError} role="alert">
            <div>
              <strong>Kullanıcılar yüklenemedi</strong>
              <span>{error.message}</span>
              {error.reference ? <small>Referans: {error.reference}</small> : null}
            </div>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={() => {
                setIsLoading(true);
                setError(null);
                setReloadKey((key) => key + 1);
              }}
            >
              Yeniden dene
            </button>
          </div>
        ) : isLoading && users.length === 0 ? (
          <div className={styles.listLoading} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            <strong>Kullanıcılar yükleniyor</strong>
            <span>Tenant kullanıcı dizini hazırlanıyor…</span>
          </div>
        ) : users.length === 0 ? (
          <div className={styles.emptyState}>
            <div aria-hidden="true">K</div>
            <h3>{hasFilters ? "Eşleşen kullanıcı bulunamadı" : "Henüz kullanıcı yok"}</h3>
            <p>
              {hasFilters
                ? "Arama ifadenizi veya durum filtresini değiştirin."
                : "İlk kullanıcı davetini oluşturarak başlayın."}
            </p>
            {hasFilters ? (
              <button className={styles.secondaryButton} type="button" onClick={clearFilters}>
                Filtreleri temizle
              </button>
            ) : canInviteUsers ? (
              <button
                className={styles.primaryButton}
                type="button"
                onClick={() => setIsInvitationOpen(true)}
              >
                Kullanıcı davet et
              </button>
            ) : null}
          </div>
        ) : (
          <div className={styles.tableScroller}>
            <table className={styles.userTable}>
              <thead>
                <tr>
                  <th scope="col">Kullanıcı</th>
                  <th scope="col">Durum</th>
                  <th scope="col">Roller</th>
                  <th scope="col">Oluşturulma</th>
                  <th scope="col">
                    <span className={styles.visuallyHidden}>İşlemler</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td data-label="Kullanıcı">
                      <button
                        className={styles.userIdentity}
                        type="button"
                        onClick={() => setSelectedUserId(user.id)}
                      >
                        <span className={styles.tableAvatar} aria-hidden="true">
                          {userInitial(user)}
                        </span>
                        <span>
                          <strong>{user.full_name}</strong>
                          <small>{user.email}</small>
                        </span>
                      </button>
                    </td>
                    <td data-label="Durum">
                      <StatusBadge status={user.status} />
                    </td>
                    <td data-label="Roller">
                      <RoleChips roles={user.roles} limit={2} />
                    </td>
                    <td data-label="Oluşturulma">{formatUserDate(user.created_at)}</td>
                    <td className={styles.actionCell}>
                      <button
                        className={styles.inspectButton}
                        type="button"
                        onClick={() => setSelectedUserId(user.id)}
                        aria-label={`${user.full_name} kullanıcısını incele`}
                      >
                        İncele
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!error && (users.length > 0 || cursorHistory.length > 0) ? (
          <footer className={styles.pagination}>
            <span>Sayfa {cursorHistory.length + 1}</span>
            <div>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={showPreviousPage}
                disabled={isLoading || cursorHistory.length === 0}
              >
                Önceki
              </button>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={showNextPage}
                disabled={isLoading || !nextCursor}
              >
                Sonraki
              </button>
            </div>
          </footer>
        ) : null}
      </div>

      {selectedUserId ? (
        <UserDetailDialog
          key={selectedUserId}
          userId={selectedUserId}
          onClose={() => setSelectedUserId(null)}
          onUpdated={applyUpdatedUser}
        />
      ) : null}

      {isInvitationOpen && canInviteUsers ? (
        <InvitationDialog
          onClose={() => setIsInvitationOpen(false)}
          onInvited={handleInvitedUser}
        />
      ) : null}
    </section>
  );
}
