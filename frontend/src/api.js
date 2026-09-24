import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export const api = axios.create({ baseURL: `${API_URL}/api/v1` });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Access tokens expire after 30 minutes (ACCESS_TOKEN_EXPIRE_MINUTES). Rather
// than let every page break silently once that happens, transparently
// refresh once on a 401 and retry the original request. Concurrent 401s
// share a single in-flight refresh call instead of each firing their own.
let refreshPromise = null;

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) throw new Error("No refresh token stored.");
  const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
    refresh_token: refreshToken,
  });
  storeSession(data);
  return data.access_token;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { config, response } = error;
    const isAuthEndpoint = config?.url?.includes("/auth/");
    if (response?.status === 401 && !config._retried && !isAuthEndpoint) {
      config._retried = true;
      try {
        if (!refreshPromise) refreshPromise = refreshAccessToken().finally(() => (refreshPromise = null));
        const newToken = await refreshPromise;
        config.headers.Authorization = `Bearer ${newToken}`;
        return api(config);
      } catch {
        clearSession();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || API_URL;

export function getStoredUser() {
  const raw = localStorage.getItem("user");
  return raw ? JSON.parse(raw) : null;
}

export function storeSession({ access_token, refresh_token, user_id, role, name }) {
  localStorage.setItem("access_token", access_token);
  localStorage.setItem("refresh_token", refresh_token);
  localStorage.setItem("user", JSON.stringify({ id: user_id, role, name }));
}

export function clearSession() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
}
