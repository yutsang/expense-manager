import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./utils";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "destructive";
  children: ReactNode;
}

const variantClasses: Record<NonNullable<BadgeProps["variant"]>, string> = {
  default:     "bg-primary/10 text-primary",
  secondary:   "bg-secondary text-secondary-foreground",
  success:     "bg-green-100 text-green-800",
  warning:     "bg-yellow-100 text-yellow-800",
  destructive: "bg-destructive/10 text-destructive",
};

export function Badge({ variant = "default", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
