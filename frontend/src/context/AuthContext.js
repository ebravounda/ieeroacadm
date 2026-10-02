import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);
const ADMIN_KEY = "otec_admin_token";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {
      if (localStorage.getItem(ADMIN_KEY)) return stopImpersonation();
      setUser(false);
    });
  }, []);

  const login = (token, u) => {
    localStorage.setItem("otec_token", token);
    setUser(u);
  };

  const logout = async () => {
    if (localStorage.getItem(ADMIN_KEY)) return stopImpersonation();
    await api.post("/auth/logout").catch(() => {});
    localStorage.removeItem("otec_token");
    setUser(false);
  };

  return <AuthCtx.Provider value={{ user, login, logout }}>{children}</AuthCtx.Provider>;
}

export async function startImpersonation(studentId) {
  const { data } = await api.post(`/users/${studentId}/impersonate`);
  localStorage.setItem(ADMIN_KEY, localStorage.getItem("otec_token") || "");
  localStorage.setItem("otec_token", data.token);
  window.location.assign("/");
}

export function stopImpersonation() {
  const admin = localStorage.getItem(ADMIN_KEY);
  localStorage.removeItem(ADMIN_KEY);
  if (admin) localStorage.setItem("otec_token", admin);
  else localStorage.removeItem("otec_token");
  window.location.assign("/estudiantes");
}

export const useAuth = () => useContext(AuthCtx);
export const isStaff = (u) => u && (u.role === "admin" || u.role === "docente");
