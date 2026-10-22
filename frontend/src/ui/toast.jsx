import { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle2, Info, TriangleAlert } from "lucide-react";

const ToastContext = createContext(() => {});

const ICONS = { green: CheckCircle2, red: TriangleAlert, ink: Info, orange: Info };

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const push = useCallback((message, tone = "green") => {
    const id = crypto.randomUUID();
    setToasts((t) => [...t.slice(-3), { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone] || Info;
          return (
            <div key={t.id} className={`toast toast-${t.tone}`}>
              <Icon size={18} />
              <span>{t.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
