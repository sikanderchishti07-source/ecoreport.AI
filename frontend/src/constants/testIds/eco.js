// Test IDs for the EcoReport AI Phase 1 skeleton.
// Naming: kebab-case, feature-prefixed. Add new keys, do not rename existing ones.

export const NAV = {
  brand: "nav-brand",
  campaigns: "nav-campaigns",
  limits: "nav-limits",
};

export const CAMPAIGNS_LIST = {
  root: "campaigns-list-root",
  createBtn: "campaigns-list-create-btn",
  emptyState: "campaigns-list-empty",
  row: (id) => `campaigns-list-row-${id}`,
  rowOpen: (id) => `campaigns-list-row-open-${id}`,
  rowDelete: (id) => `campaigns-list-row-delete-${id}`,
};

export const CAMPAIGN_FORM = {
  root: "campaign-form-root",
  projectName: "campaign-form-project-name",
  client: "campaign-form-client",
  provider: "campaign-form-provider",
  siteName: "campaign-form-site-name",
  latitude: "campaign-form-latitude",
  longitude: "campaign-form-longitude",
  inletHeight: "campaign-form-inlet-height",
  monitoringStart: "campaign-form-monitoring-start",
  monitoringEnd: "campaign-form-monitoring-end",
  preparedBy: "campaign-form-prepared-by",
  projectSupervision: "campaign-form-project-supervision",
  reportNumber: "campaign-form-report-number",
  revision: "campaign-form-revision",
  reportingDate: "campaign-form-reporting-date",
  submitBtn: "campaign-form-submit-btn",
  cancelBtn: "campaign-form-cancel-btn",
};

export const CAMPAIGN_DETAIL = {
  root: "campaign-detail-root",
  editBtn: "campaign-detail-edit-btn",
  uploadBtn: "campaign-detail-upload-btn",
  tabOverview: "campaign-detail-tab-overview",
  tabReadings: "campaign-detail-tab-readings",
  tabSettings: "campaign-detail-tab-settings",
  tabReports: "campaign-detail-tab-reports",
  readingsTable: "campaign-detail-readings-table",
  readingRow: (id) => `campaign-detail-reading-row-${id}`,
  readingFlagToggle: (id) => `campaign-detail-reading-flag-${id}`,
  clearAllReadings: "campaign-detail-clear-all-readings",
  binAddBtn: "campaign-detail-bin-add",
  binRow: (idx) => `campaign-detail-bin-row-${idx}`,
  binRemove: (idx) => `campaign-detail-bin-remove-${idx}`,
  binLabel: (idx) => `campaign-detail-bin-label-${idx}`,
  binMin: (idx) => `campaign-detail-bin-min-${idx}`,
  binMax: (idx) => `campaign-detail-bin-max-${idx}`,
  binSaveBtn: "campaign-detail-bin-save-btn",
  binResetBtn: "campaign-detail-bin-reset-btn",
};

export const UPLOAD = {
  root: "upload-root",
  dropzone: "upload-dropzone",
  fileInput: "upload-file-input",
  submitBtn: "upload-submit-btn",
  resultOk: "upload-result-ok",
  resultErrors: "upload-result-errors",
};

export const LIMITS = {
  root: "limits-root",
  table: "limits-table",
  row: (pol, avg) => `limits-row-${pol}-${avg.replace(/\s+/g, "-")}`,
};
