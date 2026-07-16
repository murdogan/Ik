import { ManagerTeam } from "@/components/dashboard/manager-team";
import { ApprovalWorkspace } from "@/components/leave/approval-workspace";

import styles from "./self-service.module.css";

export function ManagerPortalScreen() {
  return (
    <div className={styles.managerStack}>
      <ApprovalWorkspace />
      <ManagerTeam />
    </div>
  );
}
