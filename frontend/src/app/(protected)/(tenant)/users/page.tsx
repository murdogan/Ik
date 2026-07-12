import type { Metadata } from "next";

import { UserAdminScreen } from "@/components/users/user-admin-screen";

export const metadata: Metadata = {
  title: "Kullanıcı yönetimi",
};

export default function UsersPage() {
  return <UserAdminScreen />;
}
