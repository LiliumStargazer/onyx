import { redirect } from "next/navigation";
import { SIMPLIFIED_CHAT_ENABLED } from "@/lib/constants";

export default function Layout({ children }: { children: React.ReactNode }) {
  if (SIMPLIFIED_CHAT_ENABLED) redirect("/app");
  return children;
}
