import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import "@/App.css";

import AppShell from "@/components/layout/AppShell";
import CampaignsList from "@/pages/CampaignsList";
import CampaignForm from "@/pages/CampaignForm";
import CampaignDetail from "@/pages/CampaignDetail";
import UploadPage from "@/pages/UploadPage";
import LimitsPage from "@/pages/LimitsPage";
import LoginPage from "@/pages/LoginPage";
import UsersPage from "@/pages/UsersPage";
import { getToken } from "@/lib/api";

function RequireAuth({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/campaigns" replace />} />
            <Route path="/campaigns" element={<CampaignsList />} />
            <Route path="/campaigns/new" element={<CampaignForm mode="create" />} />
            <Route path="/campaigns/:id" element={<CampaignDetail />} />
            <Route path="/campaigns/:id/edit" element={<CampaignForm mode="edit" />} />
            <Route path="/campaigns/:id/upload" element={<UploadPage />} />
            <Route path="/limits" element={<LimitsPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="*" element={<Navigate to="/campaigns" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}
