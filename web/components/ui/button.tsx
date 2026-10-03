import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-pine/25 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-pine text-white shadow-sm shadow-pine/30 hover:bg-pine-deep hover:shadow-md hover:shadow-pine/30",
        outline: "border border-line bg-card text-ink shadow-sm hover:border-pine/50 hover:bg-desk hover:text-pine-deep",
        ghost: "text-pine-deep hover:bg-pine/10",
        dark: "bg-night text-white shadow-sm hover:bg-ink",
        gold: "bg-gradient-to-b from-pine-soft to-pine text-night shadow-sm shadow-pine/40 hover:from-pine-soft hover:to-pine-deep hover:text-white",
        danger: "border border-red-200 bg-card text-red-700 shadow-sm hover:border-red-300 hover:bg-red-50",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 px-6 text-base",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
