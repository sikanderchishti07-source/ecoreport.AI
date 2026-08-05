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
// Both of these now return a CHALLENGE, not a session: the password is only
// the first of two steps. Pass the challenge to authVerify with the code.
export const authSetup = (payload) =>
  api.post("/auth/setup", payload).then((r) => r.data);
export const authLogin = (payload) =>
  api.post("/auth/login", payload).then((r) => r.data);
export const authVerify = (payload) =>
  api.post("/auth/login/verify", payload).then((r) => r.data);

export const listUsers = () => api.get("/auth/users").then((r) => r.data);
export const createUser = (payload) =>
  api.post("/auth/users", payload).then((r) => r.data);
export const updateUser = (id, payload) =>
  api.patch(`/auth/users/${id}`, payload).then((r) => r.data);
// Lost phone: clears the authenticator setup so their next sign-in shows a
// fresh QR code and issues new recovery codes.
export const resetUserTwoFactor = (id) =>
  api.post(`/auth/users/${id}/reset-2fa`).then((r) => r.data);
// Frees someone locked out by failed attempts, without waiting out the timer.
export const unlockUser = (id) =>
  api.post(`/auth/users/${id}/unlock`).then((r) => r.data);

// Campaigns
export const listCampaigns = () => api.get("/campaigns").then((r) => r.data);
export const getCampaign = (id) => api.get(`/campaigns/${id}`).then((r) => r.data);
export const createCampaign = (payload) => api.post("/campaigns", payload).then((r) => r.data);
export const updateCampaign = (id, payload) =>
  api.put(`/campaigns/${id}`, payload).then((r) => r.data);
export const deleteCampaign = (id) => api.delete(`/campaigns/${id}`);

// Readings
export const getSummary = (campaignId) =>
  api.get(`/campaigns/${campaignId}/summary`).then((r) => r.data);

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
  // Field operators get the version record instead of the bytes: the report
  // is built and stored, but only an admin takes the file off the system.
  // In blob mode a JSON body still arrives as a Blob, so read the content
  // type rather than the shape of the data.
  const ctype = res.headers["content-type"] || "";
  if (ctype.includes("application/json")) {
    let meta = {};
    try {
      meta = JSON.parse(await res.data.text());
    } catch {}
    return { downloaded: false, ...meta };
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
  return { downloaded: true, filename };
};
export const previewReport = (campaignId) =>
  api.get(`/campaigns/${campaignId}/report-preview`).then((r) => r.data);

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


// Mobile labs (stations) — Phase 8
export const listStations = () => api.get("/stations").then((r) => r.data);
export const createStation = (p) => api.post("/stations", p).then((r) => r.data);
export const updateStation = (id, p) =>
  api.put(`/stations/${id}`, p).then((r) => r.data);
export const deleteStation = (id) => api.delete(`/stations/${id}`);
export const loadStationIntoCampaign = (campaignId, stationId) =>
  api.post(`/campaigns/${campaignId}/load-station/${stationId}`).then((r) => r.data);

// Attachments — photos, certificates, licence, site map
export const listAttachments = (campaignId, kind) =>
  api.get(`/campaigns/${campaignId}/attachments`, { params: kind ? { kind } : {} })
    .then((r) => r.data);
export const uploadAttachments = (campaignId, kind, files, extra = {}) => {
  const fd = new FormData();
  fd.append("kind", kind);
  if (extra.caption) fd.append("caption", extra.caption);
  if (extra.instrument_sn) fd.append("instrument_sn", extra.instrument_sn);
  Array.from(files).forEach((f) => fd.append("files", f));
  return api.post(`/campaigns/${campaignId}/attachments`, fd, {
    headers: { "Content-Type": "multipart/form-data" }, timeout: 300000,
  }).then((r) => r.data);
};
export const updateAttachment = (id, p) =>
  api.patch(`/attachments/${id}`, p).then((r) => r.data);
export const deleteAttachment = (id) => api.delete(`/attachments/${id}`);

// Cover photos — one shared library, each campaign picks from it
export const listCoverPhotos = () =>
  api.get("/cover-photos").then((r) => r.data);
export const uploadCoverPhotos = (files, caption) => {
  const fd = new FormData();
  if (caption) fd.append("caption", caption);
  Array.from(files).forEach((f) => fd.append("files", f));
  return api.post("/cover-photos", fd, {
    headers: { "Content-Type": "multipart/form-data" }, timeout: 300000,
  }).then((r) => r.data);
};
export const deleteCoverPhoto = (id) => api.delete(`/cover-photos/${id}`);
export const selectCoverPhoto = (campaignId, photoId) =>
  api.post(`/campaigns/${campaignId}/cover-photo/${photoId}`)
    .then((r) => r.data);
export const clearCoverPhoto = (campaignId) =>
  api.delete(`/campaigns/${campaignId}/cover-photo`);
export const attachmentFileUrl = (id) => `${API_BASE}/attachments/${id}/file`;
export async function fetchAttachmentBlob(id) {
  const res = await api.get(`/attachments/${id}/file`, { responseType: "blob" });
  return res.data;
}


// Home dashboard and client portal — shipment 3
export const homeDashboard = () => api.get("/dashboard").then((r) => r.data);

export const createShare = (payload) =>
  api.post("/shares", payload).then((r) => r.data);
export const listShares = (campaignId) =>
  api.get(`/campaigns/${campaignId}/shares`).then((r) => r.data);
export const revokeShare = (id) => api.delete(`/shares/${id}`);

// Portal calls carry their own signed token, so they bypass the session.
export const portalView = (token) =>
  api.get(`/portal/${token}`).then((r) => r.data);
export const portalDownloadUrl = (token, reportId) =>
  `${API_BASE}/portal/${token}/reports/${reportId}`;
export const shareUrl = (token) => `${window.location.origin}/share/${token}`;


// Calibration certificates held against a mobile lab
export const listStationCertificates = (stationId) =>
  api.get(`/stations/${stationId}/certificates`).then((r) => r.data);
export const uploadStationCertificate = (stationId, file, fields = {}) => {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") fd.append(k, v);
  });
  fd.append("files", file);
  return api.post(`/stations/${stationId}/certificates`, fd, {
    headers: { "Content-Type": "multipart/form-data" }, timeout: 300000,
  }).then((r) => r.data);
};


// ---- Roles and review workflow ------------------------------------------
// The browser hides what an operator cannot use; the server refuses it. Both
// are needed — the first is courtesy, the second is the control.
export const isAdmin = () => getUser()?.role === "admin";

export const submitForReview = (campaignId, comment, reportId) =>
  api.post(`/campaigns/${campaignId}/submit`,
           { comment: comment || null, report_id: reportId || null })
     .then((r) => r.data);
export const approveCampaign = (campaignId, comment) =>
  api.post(`/campaigns/${campaignId}/approve`, { comment: comment || null })
     .then((r) => r.data);
export const returnCampaign = (campaignId, comment) =>
  api.post(`/campaigns/${campaignId}/return`, { comment })
     .then((r) => r.data);
export const reviewQueue = () =>
  api.get("/review-queue").then((r) => r.data);

export const listNotifications = (limit = 30) =>
  api.get("/notifications", { params: { limit } }).then((r) => r.data);
export const markNotificationRead = (id) =>
  api.post(`/notifications/${id}/read`).then((r) => r.data);
export const markAllNotificationsRead = () =>
  api.post("/notifications/read-all").then((r) => r.data);

// ---- On-screen report reader --------------------------------------------
// Pages are images, not a PDF: there is no document in the browser to save,
// and no viewer toolbar offering to download one. Every request carries the
// Bearer token, so they cannot be fetched with a plain <img src>.
export const reportPageCount = (reportId) =>
  api.get(`/reports/${reportId}/page-count`).then((r) => r.data);
export const fetchReportPage = async (reportId, page) => {
  const res = await api.get(`/reports/${reportId}/page/${page}`, {
    responseType: "blob", timeout: 180000,
  });
  return res.data;
};

// ---- Noise campaigns ------------------------------------------------------
export const uploadNoiseReadings = (campaignId, file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post(`/campaigns/${campaignId}/noise-readings`, fd, {
    headers: { "Content-Type": "multipart/form-data" }, timeout: 300000,
  }).then((r) => r.data);
};
export const listNoiseReadings = (campaignId, params = {}) =>
  api.get(`/campaigns/${campaignId}/noise-readings`, { params })
     .then((r) => r.data);
export const noiseSummary = (campaignId) =>
  api.get(`/campaigns/${campaignId}/noise-summary`).then((r) => r.data);
