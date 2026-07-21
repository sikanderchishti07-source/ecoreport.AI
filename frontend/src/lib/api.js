import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// ---- Auth (Phase 7) ----
export const getToken = () => localStorage.getItem("ecoreport_token") || "";
export const getUser = () => {
  try {
    return JSON.parse(localStorage.getItem("ecoreport_user") || "null");
  } catch {
    return null;
  }
};
export const setSession = (token, user) => {
  localStorage.setItem("ecoreport_token", token);
  localStorage.setItem("ecoreport_user", JSON.stringify(user));
};
export const clearSession = () => {
  localStorage.removeItem("ecoreport_token");
  localStorage.removeItem("ecoreport_user");
};

api.interceptors.request.use((config) => {
  const t = getToken();
  if (t) config.headers["Authorization"] = `Bearer ${t}`;
  return config;
});
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 &&
        !window.location.pathname.startsWith("/login")) {
      clearSession();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export const authStatus = () => api.get("/auth/status").then((r) => r.data);
export const authSetup = (payload) =>
  api.post("/auth/setup", payload).then((r) => r.data);
export const authLogin = (payload) =>
  api.post("/auth/login", payload).then((r) => r.data);
export const listUsers = () => api.get("/auth/users").then((r) => r.data);
export const createUser = (payload) =>
  api.post("/auth/users", payload).then((r) => r.data);
export const updateUser = (id, payload) =>
  api.patch(`/auth/users/${id}`, payload).then((r) => r.data);

// Campaigns
export const listCampaigns = () => api.get("/campaigns").then((r) => r.data);
export const getCampaign = (id) => api.get(`/campaigns/${id}`).then((r) => r.data);
export const createCampaign = (payload) => api.post("/campaigns", payload).then((r) => r.data);
export const updateCampaign = (id, payload) =>
  api.put(`/campaigns/${id}`, payload).then((r) => r.data);
export const deleteCampaign = (id) => api.delete(`/campaigns/${id}`);

// Readings
export const listReadings = (campaignId, params = {}) =>
  api.get(`/campaigns/${campaignId}/readings`, { params }).then((r) => r.data);
export const flagReading = (readingId, payload) =>
  api.patch(`/readings/${readingId}`, payload).then((r) => r.data);
export const clearReadings = (campaignId) =>
  api.delete(`/campaigns/${campaignId}/readings`);
export const listUploads = (campaignId) =>
  api.get(`/campaigns/${campaignId}/uploads`).then((r) => r.data);

export const uploadReadings = (campaignId, file) => {
  const form = new FormData();
  form.append("file", file);
  return api
    .post(`/campaigns/${campaignId}/upload`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
};

// Limits
export const listLimits = () => api.get("/limits").then((r) => r.data);


// Reports (Phase 5/6)
export const generateReport = async (campaignId, lang = "en", format = "docx") => {
  let res;
  try {
    res = await api.post(
      `/campaigns/${campaignId}/report`,
      null,
      { params: { lang, format }, responseType: "blob", timeout: 600000 }
    );
  } catch (e) {
    // Error bodies arrive as Blobs in blob mode — decode so the real
    // message (e.g. the window-mismatch explanation) reaches the user.
    if (e?.response?.data instanceof Blob) {
      try {
        e.response.data = JSON.parse(await e.response.data.text());
      } catch {}
    }
    throw e;
  }
  const dispo = res.headers["content-disposition"] || "";
  const m = dispo.match(/filename="?([^";]+)"?/);
  const filename = m ? m[1] : `AAQ_Report.${format}`;
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  return filename;
};
export const listReports = (campaignId) =>
  api.get(`/campaigns/${campaignId}/reports`).then((r) => r.data);
export const downloadReportVersion = async (reportId, filename) => {
  const res = await api.get(`/reports/${reportId}/download`, {
    responseType: "blob", timeout: 300000,
  });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "report";
  a.click();
  URL.revokeObjectURL(url);
};

// Audit trail & archive search (Phase 6)
export const campaignAudit = (campaignId) =>
  api.get(`/campaigns/${campaignId}/audit`).then((r) => r.data);
export const searchArchive = (q) =>
  api.get(`/search`, { params: { q } }).then((r) => r.data);
