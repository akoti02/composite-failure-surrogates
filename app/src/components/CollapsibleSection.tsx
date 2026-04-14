import { useState, useRef, useEffect, type ReactNode } from "react";
import { COL } from "../lib/constants";

interface Props {
  title: string;
  icon?: string;
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  onExpand?: () => void;
}

export function CollapsibleSection({ title, icon, summary, defaultOpen = true, children, onExpand }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (contentRef.current) {
      setHeight(contentRef.current.scrollHeight);
    }
  }, [children, open]);

  return (
    <div className="rounded-xl" style={{ background: open ? "rgba(255,255,255,0.02)" : "transparent" }}>
      <div
        className="flex items-center gap-3 py-3.5 px-4 cursor-pointer select-none group rounded-xl transition-colors duration-150 hover:bg-white/[0.03]"
        onClick={() => setOpen((v) => !v)}
      >
        {icon && <span className="text-base" style={{ color: COL.accent, opacity: 0.7 }}>{icon}</span>}
        <div className="text-[14px] font-semibold tracking-wide" style={{ color: COL.text }}>
          {title}
        </div>

        {!open && summary && (
          <span className="text-[13px] ml-1 truncate" style={{ color: COL.textDim, maxWidth: 200 }}>
            — {summary}
          </span>
        )}

        <div className="ml-auto flex items-center gap-1.5">
          {onExpand && (
            <button
              className="w-6 h-6 flex items-center justify-center rounded-md opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity"
              style={{ color: COL.textDim }}
              onClick={(e) => {
                e.stopPropagation();
                onExpand();
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
            </button>
          )}

          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={COL.textDim} strokeWidth="2" strokeLinecap="round"
            className="transition-transform duration-300 ease-out"
            style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </div>
      </div>

      <div
        style={{
          maxHeight: open ? (height ?? 1000) : 0,
          opacity: open ? 1 : 0,
          overflow: "hidden",
          transition: "max-height 0.3s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.25s ease",
        }}
      >
        <div ref={contentRef} className="px-4 pb-4">
          {children}
        </div>
      </div>
    </div>
  );
}
