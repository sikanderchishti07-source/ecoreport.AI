// constants/testIds/ — central registry of data-testid values used by the
// end-to-end testing agent (qabot) to locate and interact with UI elements
// during automated tests. UI without testids cannot be automatically verified.
//
// Structure: each feature lives in its own file (auth.js, eco.js, ...) and
// is re-exported from here, so consumers can do a single import like
// `import { NAV, CAMPAIGNS_LIST } from '@/constants/testIds'`.

export * from './auth';
export * from './home';
export * from './eco';
