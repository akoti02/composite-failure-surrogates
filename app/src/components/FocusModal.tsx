import { useEffect, useRef, type ReactNode } from "react";
import { COL } from "../lib/constants";

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: string;
}

export function FocusModal({ open, onClose, children, title }: Props) {
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-[60] flex items-center justify-center focus-modal-backdrop"
      style={{
        background: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div
        className="focus-modal-content flex flex-col"
        style={{
          width: "calc(100vw - 80px)",
          height: "calc(100vh - 80px)",
          maxWidth: 1400,
          maxHeight: 900,
          background: COL.bg,
          border: `1px solid ${COL.borderMed}`,
          borderRadius: 16,
          boxShadow: "0 24px 80px rgba(0, 0, 0, 0.6)",
          overflow: "hidden",
        }}
      >
        {/* Modal header */}
        <div
          className="shrink-0 h-10 flex items-center px-4 gap-3"
          style={{
            background: COL.bgDark,
            borderBottom: `1px solid ${COL.border}`,
          }}
        >
          {title && (
            <span className="text-[11px] font-semibold tracking-wide" style={{ color: COL.textMid }}>
              {title}
            </span>
          )}
          <button
            className="ml-auto w-7 h-7 flex items-center justify-center rounded-md btn-press"
            style={{ color: COL.textDim, border: `1px solid ${COL.border}` }}
            onClick={onClose}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Modal body */}
        <div className="flex-1 min-h-0 overflow-auto p-4">
          {children}
        </div>
      </div>
    </div>
  );
}
