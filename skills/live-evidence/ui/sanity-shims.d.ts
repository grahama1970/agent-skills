declare module "react" {
  export type ReactNode = any;
  export type HTMLAttributes<T> = any;
  export type ButtonHTMLAttributes<T> = any;
  export type InputHTMLAttributes<T> = any;
  export type ComponentPropsWithoutRef<T> = any;
  export type ElementRef<T> = any;
  export type ComponentRef<T> = any;
  export type ForwardedRef<T> = any;
  export type FormEvent<T = Element> = {
    preventDefault(): void;
    currentTarget: T;
    target: T;
  };
  export const StrictMode: any;
  export function useState<T>(value: T): [T, (next: T | ((previous: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: readonly any[]): void;
  export function useMemo<T>(factory: () => T, deps: readonly any[]): T;
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: readonly any[]): T;
  export function useRef<T>(value: T): { current: T };
  export function forwardRef<T = any, P = any>(render: any): any;
  const React: any;
  export default React;
}
declare module "react/jsx-runtime" {
  export const Fragment: any;
  export const jsx: any;
  export const jsxs: any;
}
declare module "react-dom/client" {
  export function createRoot(element: any): { render(node: any): void };
}
declare module "lucide-react" {
  export const AlertTriangle: any;
  export const Sparkles: any;
  export const ScanSearch: any;
  export const Clipboard: any;
  export const PinOff: any;
  export const ShieldAlert: any;
  export const X: any;
  export const History: any;
  export const Binary: any;
  export const Braces: any;
  export const DatabaseZap: any;
  export const SearchCode: any;
  export const CirclePause: any;
  export const CirclePlay: any;
  export const LockKeyhole: any;
  export const MessageSquareText: any;
  export const Activity: any;
  export const ArrowRight: any;
  export const AudioLines: any;
  export const BookOpenText: any;
  export const BrainCircuit: any;
  export const Check: any;
  export const ChevronRight: any;
  export const CircleAlert: any;
  export const CircleDot: any;
  export const Code2: any;
  export const ExternalLink: any;
  export const Globe2: any;
  export const Headphones: any;
  export const LoaderCircle: any;
  export const Mic2: any;
  export const Pause: any;
  export const Pin: any;
  export const Play: any;
  export const Radio: any;
  export const Search: any;
  export const ShieldCheck: any;
  export const Square: any;
  export const Trash2: any;
}
declare module "@radix-ui/react-slot" {
  export const Slot: any;
}
declare module "class-variance-authority" {
  export function cva(base?: string, config?: any): (props?: any) => string;
  export type VariantProps<T> = T extends (props?: infer P) => any ? P : Record<string, unknown>;
}
declare module "clsx" {
  export type ClassValue = string | number | boolean | null | undefined | ClassValue[] | Record<string, any>;
  export function clsx(...inputs: ClassValue[]): string;
}
declare module "tailwind-merge" {
  export function twMerge(...inputs: string[]): string;
}
declare namespace JSX {
  interface IntrinsicElements {
    [elementName: string]: any;
  }
}
