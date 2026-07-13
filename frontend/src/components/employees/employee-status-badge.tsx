import type { EmployeeStatus } from "@/lib/employees";

import styles from "./employees.module.css";
import { EMPLOYEE_STATUS_LABELS } from "./employee-presentation";

export function EmployeeStatusBadge({ status }: { status: EmployeeStatus }) {
  return (
    <span className={`${styles.statusBadge} ${styles[`status_${status}`]}`}>
      <span aria-hidden="true" />
      {EMPLOYEE_STATUS_LABELS[status]}
    </span>
  );
}
