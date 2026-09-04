import { Check, Copy } from "lucide-react";
import Prism from "prismjs";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-go";
import "prismjs/components/prism-json";
import "prismjs/components/prism-python";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-typescript";
import { useEffect, useRef, useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";

Prism.manual = true;

interface CodeBlockProps {
  code: string;
  language?: string;
  isStreaming?: boolean;
}

export function CodeBlock({ code, language = "python", isStreaming = false }: CodeBlockProps) {
  const codeRef = useRef<HTMLElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const [userHasScrolledUp, setUserHasScrolledUp] = useState(false);
  const [copied, setCopied] = useState(false);
  useRegisterAction({
    element_id: "codeblock-copy",
    app: "live-evidence",
    action: "copy_code",
    label: "Copy code snippet",
    description: "Copy the visible code block to the clipboard.",
  });

  useEffect(() => {
    if (codeRef.current) {
      Prism.highlightElement(codeRef.current);
    }
  }, [code, language]);

  const handleScroll = () => {
    if (!preRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = preRef.current;
    setUserHasScrolledUp(scrollHeight - scrollTop - clientHeight >= 24);
  };

  useEffect(() => {
    if (isStreaming && preRef.current && !userHasScrolledUp) {
      preRef.current.scrollTo({ top: preRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [code, isStreaming, userHasScrolledUp]);

  const handleCopy = () => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  const normalizedLanguage = language.toLowerCase();

  return (
    <div className="group relative my-4 overflow-hidden rounded-xl border border-slate-800 bg-[#06070c] shadow-2xl">
      <div className="flex select-none items-center justify-between border-b border-slate-800/80 bg-[#0e101a] px-4 py-1.5 font-mono text-[11px] text-slate-400">
        <div className="flex items-center gap-2">
          <span className="font-semibold uppercase tracking-wider text-indigo-400">{normalizedLanguage}</span>
          {isStreaming ? (
            <span className="ml-2 flex items-center gap-1.5 font-sans text-[10px] font-semibold text-blue-400">
              <span className="size-1.5 animate-ping rounded-full bg-blue-400" />
              STREAMING CODE…
            </span>
          ) : null}
        </div>
        <button
          type="button"
          data-qid="codeblock-copy"
          data-qs-action="copy_code"
          onClick={handleCopy}
          className="flex cursor-pointer items-center gap-1 rounded-md border border-slate-700/60 bg-[#161826] px-2.5 py-1 font-sans text-[11px] font-medium text-slate-300 transition-colors hover:bg-[#202336]"
          title="Copy snippet"
        >
          {copied ? (
            <>
              <Check className="size-3 text-emerald-400" aria-hidden="true" />
              <span className="font-semibold text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="size-3 text-slate-400" aria-hidden="true" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre
        ref={preRef}
        onScroll={handleScroll}
        className="!m-0 max-h-[380px] scroll-smooth overflow-x-auto overflow-y-auto bg-[#06070c] p-4 font-mono text-sm leading-relaxed text-slate-100"
      >
        <code ref={codeRef} className={`language-${normalizedLanguage}`}>
          {code.trim()}
        </code>
      </pre>
    </div>
  );
}
