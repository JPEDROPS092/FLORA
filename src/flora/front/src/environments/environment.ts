/**
 * Single switch between the mock study and the Python API.
 *
 * useMocks: true  → realistic 16S study, no backend required.
 * useMocks: false → HttpFloraRepository calls apiBaseUrl + /api/...
 *
 * Leave apiBaseUrl empty when the SPA is served by `flora ui` (same origin).
 * Set it to the server origin when the SPA runs on another host, for example
 * http://127.0.0.1:8765
 */
export const environment = {
  useMocks: true,
  apiBaseUrl: ''
};
