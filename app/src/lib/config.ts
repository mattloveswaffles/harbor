// Build-time settings (build.ts). Empty = the site and API share one origin at /.
declare const HARBOR_API_URL: string | undefined;
declare const HARBOR_BASE_PATH: string | undefined;

/** Where the Harbor API lives, e.g. a deployed server for the GitHub Pages build. */
export const API_ORIGIN = (typeof HARBOR_API_URL === 'string' ? HARBOR_API_URL : '').replace(/\/$/, '');

/** The path the site is served under, e.g. "/harbor" on GitHub Pages. */
export const BASE_PATH = (typeof HARBOR_BASE_PATH === 'string' ? HARBOR_BASE_PATH : '').replace(/\/$/, '');
