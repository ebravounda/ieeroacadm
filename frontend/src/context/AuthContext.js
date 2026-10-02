import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false));
  }, []);

  const login = (token, u) => {
    localStorage.setItem("otec_token", token);
    setUser(u);
  };

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    localStorage.removeItem("otec_token");
    setUser(false);
  };

  return <AuthCtx.Provider value={{ user, login, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
export const isStaff = (u) => u && (u.role === "admin" || u.role === "docente");
