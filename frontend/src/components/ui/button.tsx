import { cn } from "@/lib/cn";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "outline";
}

export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "rounded-md px-4 py-2 text-sm font-medium transition disabled:opacity-50",
        variant === "primary"
          ? "bg-blue-600 text-white hover:bg-blue-700"
          : "border border-neutral-300 bg-white text-neutral-800 hover:bg-neutral-50",
        className,
      )}
      {...props}
    />
  );
}
