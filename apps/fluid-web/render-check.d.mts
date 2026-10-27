import type { Plugin } from 'vite'
export const ENTRY: string
export const FILE: string
export const OPTIONS: Record<string, unknown>
export function renderCheckBundle(entry?: string): Promise<string>
export default function renderCheck(): Plugin
