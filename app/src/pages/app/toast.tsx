import { createContext, type ReactNode, useCallback, useContext, useRef, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';

type Tone = 'ok' | 'error';
const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => undefined);

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ text: string; tone: Tone; shown: boolean }>({
    text: '',
    tone: 'ok',
    shown: false,
  });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const show = useCallback((text: string, tone: Tone = 'ok') => {
    setToast({ text, tone, shown: true });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast((t) => ({ ...t, shown: false })), 3200);
  }, []);
  return (
    <ToastContext value={show}>
      {children}
      <div className={`toast${toast.shown ? ' show' : ''}`} data-tone={toast.tone} role="status">
        <Icon name="check" />
        <span>{toast.text}</span>
      </div>
    </ToastContext>
  );
}
