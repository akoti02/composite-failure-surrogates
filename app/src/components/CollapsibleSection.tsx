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
    <div>
      <div
        className="flex items-center gap-2 py-2 px-1 cursor-pointer select-none group"
        onClick={() => setOpen((v) => !v)}
      >
        {icon && <span className="text-xs" style={{ color: COL.textDim }}>{icon}</span>}
        <div className="text-[10px] font-semibold tracking-[0.06em] uppercase" style={{ color: COL.textDim }}>
          {title}
        </div>

        {/* Summary when collapsed */}
        {!open && summary && (
          <span className="text-[10px] ml-1 truncate" style={{ color: COL.textDim, opacity: 0.7, maxWidth: 180 }}>
            — {summary}
          </span>
        )}

        <div className="ml-auto flex items-center gap-1">
          {/* Expand to modal button */}
          {onExpand && (
            <button
              className="w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity"
              style={{ color: COL.textDim }}
              onClick={(e) => {
                e.stopPropagation();
                onExpand();
              }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
            </button>
          )}

          {/* Chevron */}
          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={COL.textDim} strokeWidth="2" strokeLinecap="round"
            className="transition-transform duration-200"
            style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </div>
      </div>

      <div
        className="section-collapse-wrapper"
        style={{
          maxHeight: open ? (height ?? 1000) : 0,
          opacity: open ? 1 : 0,
          overflow: "hidden",
          transition: "max-height 0.25s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.2s ease",
        }}
      >
        <div ref={contentRef}>
          {children}
        </div>
      </div>
    </div>
  );
}
