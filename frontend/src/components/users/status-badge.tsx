import type { UserStatus } from "@/lib/user-administration";

import styles from "./users.module.css";
import { STATUS_LABELS } from "./user-presentation";

export function StatusBadge({ status }: { status: UserStatus }) {
  return (
    <span className={`${styles.statusBadge} ${styles[`status_${status}`]}`}>
      <span aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  );
}
