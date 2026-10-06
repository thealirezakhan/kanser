import { cn } from "@/lib/cn";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "outline";
}

export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "rounded-lg px-4 py-2 text-sm font-semibold transition disabled:opacity-50",
        variant === "primary"
          ? "bg-primary-container text-white hover:opacity-90 shadow-sm"
          : "border border-outline-variant bg-white text-on-surface hover:bg-surface-container-low shadow-xs",
        className,
      )}
      {...props}
    />
  );
}
