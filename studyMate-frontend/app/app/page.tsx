import type { Metadata } from "next";
import { Workspace } from "@/components/workspace/Workspace";

export const metadata: Metadata = {
  title: "Workspace",
  robots: { index: false },
};

export default function AppPage() {
  return <Workspace />;
}
