import * as React from "react";

import { cn } from "@/lib/utils";

function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("inline-flex items-center rounded-full border border-line bg-desk px-2 py-0.5 text-xs text-ink", className)}
      {...props}
    />
  );
}

export { Badge };
