import { Fragment } from "react";

export type KbBlock =
  | { kind: "text"; text: string }
  | { kind: "bullet"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] };

export type KbSource = {
  title: string;
  section?: string | null;
  kicker?: string | null;
  excerpt: string;
  blocks?: KbBlock[];
  anchor?: string | null;
};

/** One knowledge-base section: lead sentence, bullets, and its table, in the order the document gives them. */
export function SectionBody({
  blocks,
  dotClassName = "bg-current opacity-50",
  wide = false,
}: {
  blocks: KbBlock[];
  dotClassName?: string;
  /** Draw tables as tables. Narrow panels such as the chat show each row as a small card instead. */
  wide?: boolean;
}) {
  const out: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = (key: string) => {
    if (!bullets.length) return;
    out.push(
      <ul key={key} className="space-y-1.5">
        {bullets.map((text, index) => (
          <li key={index} className="flex gap-2.5">
            <span className={`mt-[0.55em] size-1.5 shrink-0 rounded-full ${dotClassName}`} aria-hidden="true" />
            <span>{text}</span>
          </li>
        ))}
      </ul>,
    );
    bullets = [];
  };
  blocks.forEach((block, index) => {
    if (block.kind === "bullet") {
      bullets.push(block.text);
      return;
    }
    flush(`b${index}`);
    if (block.kind === "text") {
      out.push(
        <p key={index} className={index === 0 ? "font-medium" : undefined}>
          {block.text}
        </p>,
      );
    } else {
      out.push(<SectionTable key={index} header={block.header} rows={block.rows} wide={wide} />);
    }
  });
  flush("end");
  return <div className="space-y-2.5 text-[13px] leading-6">{out}</div>;
}

function SectionTable({ header, rows, wide }: { header: string[]; rows: string[][]; wide: boolean }) {
  return (
    <>
      <div className={`${wide ? "hidden sm:block" : "hidden"} overflow-x-auto rounded-lg border`} style={{ borderColor: "color-mix(in srgb, currentColor 14%, transparent)" }}>
        <table className="kb-table">
          {header.length > 0 && (
            <thead>
              <tr>
                {header.map((cell, index) => (
                  <th key={index} scope="col">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, index) => (
                  <td key={index}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className={`grid gap-2 ${wide ? "sm:hidden" : ""}`}>
        {rows.map((row, rowIndex) => (
          <div key={rowIndex} className="rounded-lg px-3 py-2" style={{ border: "1px solid color-mix(in srgb, currentColor 14%, transparent)" }}>
            <dt className="font-medium">{row[0]}</dt>
            {row.slice(1).map((cell, index) => (
              <dd key={index} className="mt-0.5 flex justify-between gap-3 text-xs leading-5">
                <span className="shrink-0 opacity-60">{header[index + 1] || ""}</span>
                <span className="text-right font-medium">{cell}</span>
              </dd>
            ))}
          </div>
        ))}
      </dl>
    </>
  );
}

/** Answer text with "• " lines drawn as a list. */
export function AnswerText({ text, dotClassName = "bg-current opacity-50" }: { text: string; dotClassName?: string }) {
  const paragraphs = text.split(/\n{2,}/).map((part) => part.split("\n").filter((line) => line.trim()));
  return (
    <div className="space-y-3 text-sm leading-6">
      {paragraphs.map((lines, index) => {
        const lead = lines.filter((line) => !line.trimStart().startsWith("•"));
        const items = lines.filter((line) => line.trimStart().startsWith("•")).map((line) => line.replace(/^\s*•\s*/, ""));
        return (
          <Fragment key={index}>
            {lead.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
            {items.length > 0 && (
              <ul className="space-y-1.5">
                {items.map((item, at) => (
                  <li key={at} className="flex gap-2.5">
                    <span className={`mt-[0.6em] size-1.5 shrink-0 rounded-full ${dotClassName}`} aria-hidden="true" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
