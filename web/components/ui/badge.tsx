import * as React from "react";

import { cn } from "@/lib/utils";

function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border border-pine/20 bg-pine/10 px-2.5 py-0.5 text-xs font-medium text-pine-deep", className)}
      {...props}
    />
  );
}

export { Badge };
