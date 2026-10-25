import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { SessionProvider, useSession } from "./lib/session";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import Onboarding from "./features/onboarding/Onboarding";
import Tour from "./features/onboarding/Tour";
import { Help, Home } from "./features/pages/Pages";

// Route-level code splitting: only the shell, onboarding and home load up front.
const lots = () => import("./features/lots/Lots");
const ops = () => import("./features/ops/Ops");
const pages = () => import("./features/pages/Pages");
const LotDetail = lazy(() => lots().then((m) => ({ default: m.LotDetail })));
const LotList = lazy(() => lots().then((m) => ({ default: m.LotList })));
const NewLot = lazy(() => lots().then((m) => ({ default: m.NewLot })));
const Scan = lazy(() => lots().then((m) => ({ default: m.Scan })));
const Crowd = lazy(() => ops().then((m) => ({ default: m.Crowd })));
const Rescue = lazy(() => ops().then((m) => ({ default: m.Rescue })));
const Storage = lazy(() => ops().then((m) => ({ default: m.Storage })));
const Admin = lazy(() => pages().then((m) => ({ default: m.Admin })));
const Evidence = lazy(() => pages().then((m) => ({ default: m.Evidence })));
const ReportProblem = lazy(() => pages().then((m) => ({ default: m.ReportProblem })));

const Lab = lazy(() => import("./features/lab/Lab").then((m) => ({ default: m.Lab })));
const Advisor = lazy(() => import("./features/lab/Lab").then((m) => ({ default: m.Advisor })));
const GuidedDemo = lazy(() => import("./features/demo/GuidedDemo"));

function RequireUser({ children, roles }: { children: ReactNode; roles?: string[] }) {
  const { user, ready } = useSession();
  if (!ready) return <div className="p-4"><Loading /></div>;
  if (!user) return <Navigate to="/welcome" replace />;
  if (roles && !roles.includes(user.role) && user.role !== "ADMIN") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="p-4"><Loading /></div>}>
          <Routes>
            <Route path="/welcome" element={<Onboarding />} />
            <Route element={<Layout />}>
              <Route index element={<RequireUser><Home /></RequireUser>} />
              <Route path="tour" element={<RequireUser><Tour /></RequireUser>} />
              <Route path="scan" element={<RequireUser><Scan /></RequireUser>} />
              <Route path="lots" element={<RequireUser><LotList /></RequireUser>} />
              <Route path="lots/new" element={<RequireUser roles={["FARMER", "SUPERVISOR", "WAREHOUSE", "DISPATCHER"]}><NewLot /></RequireUser>} />
              <Route path="lots/:id" element={<RequireUser><LotDetail /></RequireUser>} />
              <Route path="storage" element={<RequireUser roles={["SUPERVISOR", "WAREHOUSE"]}><Storage /></RequireUser>} />
              <Route path="crowd" element={<RequireUser><Crowd /></RequireUser>} />
              <Route path="rescue" element={<RequireUser roles={["SUPERVISOR", "WAREHOUSE", "DISPATCHER", "NGO"]}><Rescue /></RequireUser>} />
              <Route path="advisor" element={<RequireUser roles={["DISPATCHER", "SUPERVISOR"]}><Advisor /></RequireUser>} />
              <Route path="lab" element={<RequireUser roles={["DISPATCHER"]}><Lab /></RequireUser>} />
              <Route path="admin" element={<RequireUser roles={["ADMIN"]}><Admin /></RequireUser>} />
              <Route path="demo" element={<GuidedDemo />} />
              <Route path="evidence" element={<Evidence />} />
              <Route path="help" element={<Help />} />
              <Route path="report-problem" element={<ReportProblem />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </SessionProvider>
  );
}
