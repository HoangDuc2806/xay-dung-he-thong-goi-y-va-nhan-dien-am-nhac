import { AuthGate } from "@/components/auth-gate";
import { PageHeader } from "@/components/page-header";
import { DiscoveryPanel } from "@/components/discovery-panel";

export default function Page() {
  return <>
    <PageHeader title="Khám phá gu của bạn" description="Gợi ý có lý do, từ những lựa chọn mang dấu ấn của riêng bạn." />
    <AuthGate><DiscoveryPanel /></AuthGate>
  </>;
}
