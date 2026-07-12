import type { RoleSummary } from "@/lib/auth-contracts";

import styles from "./users.module.css";

export function RoleChips({ roles, limit }: { roles: RoleSummary[]; limit?: number }) {
  if (roles.length === 0) {
    return <span className={styles.roleEmpty}>Rol atanmamış</span>;
  }

  const visibleRoles = limit === undefined ? roles : roles.slice(0, limit);
  const hiddenRoleCount = roles.length - visibleRoles.length;

  return (
    <span className={styles.roleChipList} aria-label={`Roller: ${roles.map((role) => role.name).join(", ")}`}>
      {visibleRoles.map((role) => (
        <span className={styles.roleChip} key={role.id}>
          {role.name}
        </span>
      ))}
      {hiddenRoleCount > 0 ? (
        <span className={styles.roleChipOverflow} title={roles.slice(visibleRoles.length).map((role) => role.name).join(", ")}>
          +{hiddenRoleCount}
        </span>
      ) : null}
    </span>
  );
}
