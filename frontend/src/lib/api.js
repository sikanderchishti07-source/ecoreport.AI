import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Operator attribution for the audit trail (Phase 6)
export const getOperator = () => localStorage.getItem("ecoreport_operator") || "";
export const setOperator = (name) =>
  localStorage.setItem("ecoreport_operator", (name || "").trim());
api.interceptors.request.use((config) => {
  const op = getOperator();
  if (op) config.headers["X-User"] = op;
  return config;
});

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
  const res = await api.post(
    `/campaigns/${campaignId}/report`,
    null,
    { params: { lang, format }, responseType: "blob", timeout: 600000 }
  );
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
export const reportDownloadUrl = (reportId) =>
  `${API_BASE}/reports/${reportId}/download`;

// Audit trail & archive search (Phase 6)
export const campaignAudit = (campaignId) =>
  api.get(`/campaigns/${campaignId}/audit`).then((r) => r.data);
export const searchArchive = (q) =>
  api.get(`/search`, { params: { q } }).then((r) => r.data);
