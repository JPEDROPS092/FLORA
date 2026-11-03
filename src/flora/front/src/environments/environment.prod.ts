/**
 * Production build (`flora ui`): the SPA is served by the Python backend on the same origin,
 * so it talks to the real API. `ng serve` keeps `environment.ts` (mock study, no backend).
 */
export const environment = {
  useMocks: false,
  apiBaseUrl: ''
};
