import type { Metadata } from "next";

import { ApprovalWorkspace } from "@/components/leave/approval-workspace";

export const metadata: Metadata = {
  title: "İzin onayları",
};

export default function LeaveApprovalsPage() {
  return <ApprovalWorkspace />;
}
