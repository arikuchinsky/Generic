import { useState } from "react";
import SyntaxHighlighter from "react-syntax-highlighter";
import { atomOneDark } from "react-syntax-highlighter/dist/esm/styles/hljs";

interface CodeBlockProps {
  language?: string;
  children: string;
}

const customStyle: Record<string, React.CSSProperties> = {
  ...atomOneDark,
  'hljs': {
    ...atomOneDark['hljs'],
    background: 'transparent',
    padding: 0,
  },
};

export function CodeBlock({ language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{language || "text"}</span>
        <button className="code-block-copy" onClick={handleCopy}>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <div className="code-block-content">
        <SyntaxHighlighter
          language={language || "text"}
          style={customStyle}
          customStyle={{
            background: "transparent",
            padding: 0,
            margin: 0,
            fontSize: "13px",
            lineHeight: "1.5",
          }}
        >
          {children}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}
