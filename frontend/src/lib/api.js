import axios from "axios";

export const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("otec_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || "Ocurrió un error";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  return String(d);
}

export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString("es-CL", { dateStyle: "medium", timeStyle: "short" }) : "—";

export const fmtDay = (iso) =>
  iso ? new Date(iso).toLocaleDateString("es-CL", { day: "numeric", month: "long", year: "numeric" }) : "—";
