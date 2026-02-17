# Frontend Rules (Next.js 14)

## App Router

- Use the Next.js 14 App Router (`src/app/` directory).
- Pages are `page.tsx` files inside route directories.
- Layouts are `layout.tsx` files for shared UI shells.
- Use `"use client"` directive only on components that need browser APIs or state.
- Server Components are the default — prefer them when possible.

## TypeScript

- Strict mode enabled — no `any` types.
- Define interfaces for all API response shapes in `src/lib/api.ts`.
- Use `interface` for object shapes, `type` for unions/intersections.
- Export types alongside the functions that use them.

## Styling

- Tailwind CSS only — no CSS modules, styled-components, or inline `style`.
- Use CSS variables in `globals.css` for theme colors.
- Use `cn()` utility (clsx + twMerge) if class merging is needed.
- Responsive design: mobile-first with `sm:`, `md:`, `lg:` breakpoints.

## State Management

- Use React `useState` and `useEffect` for local component state.
- Use `useCallback` for event handlers passed as props.
- Poll job status with `setInterval` in `useEffect` with proper cleanup.
- No global state library — prop drilling is fine for this app's complexity.

## API Calls

- All API functions live in `src/lib/api.ts`.
- Use native `fetch` — no axios.
- Always handle loading, error, and success states.
- Show toast or inline error messages on API failures.
- Use `NEXT_PUBLIC_API_URL` environment variable for the backend base URL.
