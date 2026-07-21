import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
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
