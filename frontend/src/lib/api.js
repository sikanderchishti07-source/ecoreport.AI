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
    // A 401 from the sign-in endpoints is a credential problem the login
    // page handles itself — a wrong code, or a replayed one. Treating it
    // as an expired session here wiped a freshly-issued token and signed
    // people out immediately after a successful login.
    const url = err?.config?.url || "";
    if (err?.response?.status === 401 &&
        !url.includes("/auth/") &&
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
// Names only, and readable by any signed-in account — the field app needs a
// list to choose from, not the user records, which are admin-only.
export const listOperators = () =>
  api.get("/auth/operators").then((r) => r.data);
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
export const generateReport = async (campaignId, lang = "en", format = "docx",
                                    reportingDate = null) => {
  let res;
  try {
    res = await api.post(
      `/campaigns/${campaignId}/report`,
      null,
      { params: { lang, format,
                  // The issue date, carried with the generation that issues
                  // it. The report number encodes the same date, so both are
                  // decided here and cannot disagree.
                  ...(reportingDate ? { reporting_date: reportingDate } : {}) },
        responseType: "blob", timeout: 600000 }
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
  // Content-Disposition is only readable here because the server lists it in
  // expose_headers; a browser hides every other response header from
  // JavaScript, which is why every report arrived under the fallback name
  // however carefully the server had named it.
  //
  // Both forms are handled: the plain one, and the RFC 5987 form the server
  // switches to when a filename contains non-ASCII characters.
  const dispo = res.headers["content-disposition"] || "";
  const utf8 = dispo.match(/filename\*=(?:utf-8'')?([^;]+)/i);
  const plain = dispo.match(/filename="?([^";]+)"?/i);
  const filename = utf8
    ? decodeURIComponent(utf8[1].trim().replace(/^"|"$/g, ""))
    : (plain ? plain[1].trim() : `AAQ_Report.${format}`);
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
  // The server's own name wins. A caller passing one is usually handing over
  // the stored filename, which is the unique internal form rather than the
  // readable one the report should be saved under.
  const dispo = res.headers?.["content-disposition"] || "";
  const m = /filename\*?=(?:utf-8'')?"?([^";]+)/i.exec(dispo);
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = m ? decodeURIComponent(m[1].trim()) : (filename || "report");
  a.click();
  URL.revokeObjectURL(url);
};

// Audit trail & archive search (Phase 6)
export const campaignAudit = (campaignId) =>
  api.get(`/campaigns/${campaignId}/audit`).then((r) => r.data);
export const searchArchive = (q) =>
  api.get(`/search`, { params: { q } }).then((r) => r.data);


// Mobile labs (stations) — Phase 8
export const listStations = (kind) =>
  api.get("/stations", { params: kind ? { kind } : {} }).then((r) => r.data);
export const listStationPhotos = (stationId) =>
  api.get(`/stations/${stationId}/photos`).then((r) => r.data);
export const uploadStationPhotos = (stationId, files, caption) => {
  const fd = new FormData();
  [...files].forEach((f) => fd.append("files", f));
  if (caption) fd.append("caption", caption);
  return api.post(`/stations/${stationId}/photos`, fd, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};
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
// The short path for a short code. Links already issued use /share/ and that
// route is still mounted, so nothing in a client's inbox stops working.
export const shareUrl = (token) => `${window.location.origin}/r/${token}`;


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

// ---- Company documents ----------------------------------------------------
// The environmental licence belongs to BSA, not to any one job, so it is
// held once and every report picks it up.
export const listCompanyDocuments = (kind = "license") =>
  api.get("/company-documents", { params: { kind } }).then((r) => r.data);
export const uploadCompanyDocument = (files, kind = "license", caption) => {
  const fd = new FormData();
  [...files].forEach((f) => fd.append("files", f));
  fd.append("kind", kind);
  if (caption) fd.append("caption", caption);
  return api.post("/company-documents", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};
export const deleteCompanyDocument = (id) =>
  api.delete(`/company-documents/${id}`);

// --- Site samples (water and soil) ----------------------------------------
// Multipart because a sample carries its photograph. The fields are appended
// one at a time so an empty value is simply absent rather than being sent as
// the string "undefined", which the server would then store.
export const listSiteSamples = (params = {}) =>
  api.get("/site-samples", { params }).then((r) => r.data);
export const createSiteSample = (fields, photo) => {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") fd.append(k, v);
  });
  if (photo) fd.append("photo", photo);
  return api.post("/site-samples", fd, {
    headers: { "Content-Type": "multipart/form-data" }, timeout: 120000,
  }).then((r) => r.data);
};
export const updateSiteSample = (id, payload) =>
  api.patch(`/site-samples/${id}`, payload).then((r) => r.data);
export const deleteSiteSample = (id) => api.delete(`/site-samples/${id}`);
// Fetched through the app's client, not as a plain <img src>: the route sits
// behind the Bearer token, and a browser fetching an image never sends it.
export async function fetchSiteSamplePhotoBlob(id) {
  const res = await api.get(`/site-samples/${id}/photo`, { responseType: "blob" });
  return res.data;
}

// --- Soil and water reporting ----------------------------------------------
// Distinct from the site-samples helpers above. Those record what the field
// operator captures during a visit; these carry what the laboratory reports
// afterwards, and the limits it is judged against.
export const listAnalytes = (medium) =>
  api.get("/analytes", { params: medium ? { medium } : {} }).then((r) => r.data);
export const listSampleStandards = () =>
  api.get("/standards").then((r) => r.data);

export const listParameterProfiles = (params = {}) =>
  api.get("/parameter-profiles", { params }).then((r) => r.data);
export const createParameterProfile = (payload) =>
  api.post("/parameter-profiles", payload).then((r) => r.data);
export const updateParameterProfile = (id, payload) =>
  api.put(`/parameter-profiles/${id}`, payload).then((r) => r.data);
export const deleteParameterProfile = (id) =>
  api.delete(`/parameter-profiles/${id}`);

export const getSampleSettings = (campaignId) =>
  api.get(`/campaigns/${campaignId}/sample-settings`).then((r) => r.data);
export const saveSampleSettings = (campaignId, payload) =>
  api.put(`/campaigns/${campaignId}/sample-settings`, payload).then((r) => r.data);

export const listLabSamples = (campaignId) =>
  api.get(`/campaigns/${campaignId}/samples`).then((r) => r.data);
export const createLabSample = (campaignId, payload) =>
  api.post(`/campaigns/${campaignId}/samples`, payload).then((r) => r.data);
export const updateLabSample = (sampleId, payload) =>
  api.put(`/samples/${sampleId}`, payload).then((r) => r.data);
export const deleteLabSample = (sampleId) => api.delete(`/samples/${sampleId}`);

export const ingestResultsGrid = (campaignId, payload) =>
  api.post(`/campaigns/${campaignId}/results-grid`, payload).then((r) => r.data);
// The CSV goes up as multipart, so the JSON content type set on the shared
// client has to be overridden here or the server rejects the body.
export const ingestResultsCsv = (campaignId, file, addParametersToScope = true) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post(`/campaigns/${campaignId}/results-csv`, fd, {
    params: { add_parameters_to_scope: addParametersToScope },
    headers: { "Content-Type": "multipart/form-data" }, timeout: 120000,
  }).then((r) => r.data);
};

// The laboratory's own Certificate of Analysis workbook, one sheet per
// sample, in the format they already produce for every job. Nothing is
// retyped: the sample code, the dates and the site are read from the header
// block, and the parameters from the rows beneath it.
//
// Longer timeout than the CSV route: a workbook is parsed sheet by sheet and
// a job with eight samples takes appreciably longer than one flat file.
export const ingestResultsCoa = (campaignId, file, addParametersToScope = true) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post(`/campaigns/${campaignId}/results-coa`, fd, {
    params: { add_parameters_to_scope: addParametersToScope },
    headers: { "Content-Type": "multipart/form-data" }, timeout: 180000,
  }).then((r) => r.data);
};

// Set a campaign's monitoring window to the range of its stored readings.
// What "use the file's dates" calls after an upload reported a disagreement.
export const adoptDataWindow = (campaignId) =>
  api.post(`/campaigns/${campaignId}/adopt-data-window`).then((r) => r.data);

export const getSampleSummary = (campaignId) =>
  api.get(`/campaigns/${campaignId}/sample-summary`).then((r) => r.data);
export const getSampleReadiness = (campaignId) =>
  api.get(`/campaigns/${campaignId}/sample-readiness`).then((r) => r.data);
export const getLandUseComparison = (campaignId) =>
  api.get(`/campaigns/${campaignId}/land-use-comparison`).then((r) => r.data);

// The soil and water report has its own endpoint rather than a branch inside
// /campaigns/{id}/report: it needs none of what that route collects. Storage,
// versioning and the review workflow downstream are the same.
export const generateSampleReport = async (campaignId, format = "docx") => {
  const res = await api.post(`/campaigns/${campaignId}/sample-report`, null, {
    params: { format },
    // A member gets JSON explaining that the reviewing engineer handles
    // downloads; an admin gets the file. Both arrive as a blob, so the type
    // is inspected rather than assumed.
    responseType: "blob",
    timeout: 600000,
  });
  const type = res.data?.type || "";
  if (type.includes("application/json")) {
    return { file: null, info: JSON.parse(await res.data.text()) };
  }
  const disposition = res.headers?.["content-disposition"] || "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(disposition);
  return {
    file: res.data,
    filename: match ? decodeURIComponent(match[1]) : `report.${format}`,
    info: null,
  };
};

// --- Clients ---------------------------------------------------------------
// A client record is optional. A campaign keeps the client name typed on it,
// and gains a link only when someone makes one; reports fall back to the text
// wherever no record exists.
export const listClients = (params = {}) =>
  api.get("/clients", { params }).then((r) => r.data);
export const createClient = (payload) =>
  api.post("/clients", payload).then((r) => r.data);
export const updateClient = (id, payload) =>
  api.put(`/clients/${id}`, payload).then((r) => r.data);
export const deleteClient = (id) => api.delete(`/clients/${id}`);
export const getClient = (id) => api.get(`/clients/${id}`).then((r) => r.data);
export const clientCampaigns = (id) =>
  api.get(`/clients/${id}/campaigns`).then((r) => r.data);

// Client names typed on campaigns that have no record behind them, with the
// record each one probably means.
export const listClientSuggestions = () =>
  api.get("/clients/suggestions").then((r) => r.data);

// Adopt a spelling as an alias and link every campaign that uses it.
export const absorbSpelling = (clientId, text) =>
  api.post(`/clients/${clientId}/absorb`,
           { apply_to_matching_text: text }).then((r) => r.data);

// Link or unlink one campaign. Passing applyToMatchingText links every other
// campaign carrying the same client text in the same action.
export const linkCampaignClient = (campaignId, clientId, applyToMatchingText) =>
  api.post(`/clients/link/${campaignId}`, {
    client_id: clientId,
    apply_to_matching_text: applyToMatchingText || null,
  }).then((r) => r.data);

// --- Reports archive -------------------------------------------------------
// Every issued version across every campaign, joined to its campaign and its
// client. Read-only.
//
// Named apart from listReports above, which returns the versions of a single
// campaign; the two answer different questions and a shared name would make
// the wrong one easy to reach for.
export const listReportArchive = (params = {}) =>
  api.get("/reports", { params }).then((r) => r.data);

// Delete report versions. Admin only, and the server refuses approved
// reports unless includeApproved is set — deleting a document that went to a
// client is a deliberate act, not a mis-click.
export const deleteReports = (reportIds, includeApproved = false) =>
  api.post("/reports/delete", {
    report_ids: reportIds,
    include_approved: includeApproved,
  }).then((r) => r.data);
