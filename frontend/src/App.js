import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import "@/App.css";
import AppShell from "@/components/layout/AppShell";
import CampaignsList from "@/pages/CampaignsList";
import CampaignForm from "@/pages/CampaignForm";
import CampaignDetail from "@/pages/CampaignDetail";
import SoilWaterCampaign from "@/pages/SoilWaterCampaign";
import UploadPage from "@/pages/UploadPage";
import LimitsPage from "@/pages/LimitsPage";
import LoginPage from "@/pages/LoginPage";
import HomeDashboard from "@/pages/HomeDashboard";
import PortalPage from "@/pages/PortalPage";
import UsersPage from "@/pages/UsersPage";
import ReviewQueue from "@/pages/ReviewQueue";
import StationsPage from "@/pages/StationsPage";
import CoverPhotosPage from "@/pages/CoverPhotosPage";
import SiteSamplesPage from "@/pages/SiteSamplesPage";
import FieldCapture from "@/pages/FieldCapture";
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
          {/* A client link is now a twelve-character code rather than a
              signed token, so it is short enough for the path itself to be
              worth shortening: aeconreport.com/r/K7M2P9XQ4RTW reads as a
              professional link where the old one wrapped across three lines
              of an email. /share/ stays for the links already sent out. */}
          <Route path="/r/:token" element={<PortalPage />} />
          <Route path="/share/:token" element={<PortalPage />} />
          {/* Site capture runs outside the office shell — no navigation, no
              side rail, its own dark theme — because it is used one-handed in
              sunlight. Deleting these two lines and the page file removes the
              feature entirely. */}
          <Route
            path="/field"
            element={<RequireAuth><FieldCapture /></RequireAuth>}
          />
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<HomeDashboard />} />
            <Route path="/campaigns" element={<CampaignsList />} />
            {/* The soil and water flow is its own page. Its work is samples
                and laboratory results, not a time series, so it shares none of
                the air wizard's steps — routing it through CampaignForm would
                have shown an inlet height and a gas units selector. */}
            <Route path="/campaigns/new-soil-water" element={<SoilWaterCampaign />} />
            <Route path="/campaigns/:id/soil-water" element={<SoilWaterCampaign />} />
            <Route path="/campaigns/new" element={<CampaignForm mode="create" />} />
            <Route path="/campaigns/:id" element={<CampaignDetail />} />
            <Route path="/campaigns/:id/edit" element={<CampaignForm mode="edit" />} />
            <Route path="/campaigns/:id/upload" element={<UploadPage />} />
            <Route path="/limits" element={<LimitsPage />} />
            <Route path="/labs" element={<StationsPage />} />
            <Route path="/cover-photos" element={<CoverPhotosPage />} />
            <Route path="/site-samples" element={<SiteSamplesPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/review" element={<ReviewQueue />} />
            <Route path="*" element={<Navigate to="/campaigns" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}
