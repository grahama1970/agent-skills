/**
 * zip helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { ZipFileEntry } from '../types'
import { textEncoder } from '../constants'
import { assetExtension, dreamAssetUrl } from './asset'
import { crc32, writeUint16, writeUint32 } from './binary'

export function sanitizeZipName(value: string): string {
  return value
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 120) || 'asset'
}

export function createStoredZip(entries: ZipFileEntry[]): Blob {
  const local: number[] = []
  const central: number[] = []
  const now = new Date()
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | Math.floor(now.getSeconds() / 2)
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()
  let offset = 0

  for (const entry of entries) {
    const name = textEncoder.encode(entry.name)
    const checksum = crc32(entry.data)
    const size = entry.data.length
    const localOffset = offset

    writeUint32(local, 0x04034b50)
    writeUint16(local, 20)
    writeUint16(local, 0)
    writeUint16(local, 0)
    writeUint16(local, dosTime)
    writeUint16(local, dosDate)
    writeUint32(local, checksum)
    writeUint32(local, size)
    writeUint32(local, size)
    writeUint16(local, name.length)
    writeUint16(local, 0)
    local.push(...name, ...entry.data)
    offset += 30 + name.length + size

    writeUint32(central, 0x02014b50)
    writeUint16(central, 20)
    writeUint16(central, 20)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint16(central, dosTime)
    writeUint16(central, dosDate)
    writeUint32(central, checksum)
    writeUint32(central, size)
    writeUint32(central, size)
    writeUint16(central, name.length)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint16(central, 0)
    writeUint32(central, 0)
    writeUint32(central, localOffset)
    central.push(...name)
  }

  const centralOffset = local.length
  writeUint32(central, 0x06054b50)
  writeUint16(central, 0)
  writeUint16(central, 0)
  writeUint16(central, entries.length)
  writeUint16(central, entries.length)
  writeUint32(central, central.length)
  writeUint32(central, centralOffset)
  writeUint16(central, 0)

  return new Blob([new Uint8Array(local), new Uint8Array(central)], { type: 'application/zip' })
}

export async function fetchZipAsset(rawPath: string, zipPath: string): Promise<ZipFileEntry | null> {
  const url = dreamAssetUrl(rawPath)
  if (!url) return null
  const response = await fetch(url)
  if (!response.ok) return null
  const blob = await response.blob()
  const data = new Uint8Array(await blob.arrayBuffer())
  const extension = assetExtension(rawPath, blob.type)
  const normalized = zipPath.includes('.') ? zipPath : `${zipPath}.${extension}`
  return { name: normalized, data }
}

export async function copyPanelBundleToDesktopClipboard(filename: string, entries: Array<Record<string, string>>): Promise<boolean> {
  const response = await fetch('/api/projects/dream/panel-prompt-bundle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, entries }),
  })
  if (!response.ok) return false
  const result = await response.json()
  return result?.status === 'ok' && result?.copiedToClipboard === true
}
