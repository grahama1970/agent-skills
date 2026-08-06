import { createContext, useContext, useState, type ReactNode } from 'react'

export type SpartaRole =
  | 'junior_analyst'
  | 'senior_security_engineer'
  | 'lead_systems_architect'
  | 'compliance_auditor'
  | 'webgpt_daemon'

export interface SpartaUser {
  id: string
  name: string
  role: SpartaRole
  roleLabel: string
  permissions: string[]
}

export const ROLE_PROFILES = {
  JUNIOR: {
    id: 'eng_9921',
    name: 'Jordan Lee',
    role: 'junior_analyst',
    roleLabel: 'Junior Analyst',
    permissions: ['read:matrix', 'read:timeline:limited', 'propose:mapping', 'search:datalake'],
  },
  SENIOR: {
    id: 'eng_7742',
    name: 'Graham Marzban',
    role: 'senior_security_engineer',
    roleLabel: 'Senior Security Engineer',
    permissions: ['read:matrix', 'read:timeline', 'propose:mapping', 'search:datalake', 'write:mapping', 'write:custom_req'],
  },
  LEAD: {
    id: 'arch_001',
    name: 'Morgan Chen',
    role: 'lead_systems_architect',
    roleLabel: 'Lead Architect',
    permissions: ['*'],
  },
  AUDITOR: {
    id: 'aud_554',
    name: 'Riley Patel',
    role: 'compliance_auditor',
    roleLabel: 'Compliance Auditor',
    permissions: ['read:matrix', 'read:timeline:full', 'export:compliance'],
  },
  WEBGPT: {
    id: 'webgpt-daemon',
    name: 'WebGPT Daemon',
    role: 'webgpt_daemon',
    roleLabel: 'WebGPT Daemon',
    permissions: ['write:partial_candidate', 'write:covered_candidate'],
  },
} as const satisfies Record<string, SpartaUser>

const ROLE_PERMISSIONS: Record<SpartaRole, string[]> = {
  junior_analyst: ROLE_PROFILES.JUNIOR.permissions,
  senior_security_engineer: ROLE_PROFILES.SENIOR.permissions,
  lead_systems_architect: ROLE_PROFILES.LEAD.permissions,
  compliance_auditor: ROLE_PROFILES.AUDITOR.permissions,
  webgpt_daemon: ROLE_PROFILES.WEBGPT.permissions,
}

interface RBACContextValue {
  user: SpartaUser
  setUser: (user: SpartaUser) => void
  hasPermission: (requiredPermission: string) => boolean
}

const DEFAULT_USER = ROLE_PROFILES.SENIOR

const RBACContext = createContext<RBACContextValue>({
  user: DEFAULT_USER,
  setUser: () => undefined,
  hasPermission: (requiredPermission: string) => (DEFAULT_USER.permissions as readonly string[]).includes(requiredPermission),
})

export function RBACProvider({ initialUser = DEFAULT_USER, children }: { initialUser?: SpartaUser; children: ReactNode }) {
  const [user, setUser] = useState<SpartaUser>(initialUser)

  const hasPermission = (requiredPermission: string) => {
    if (user.permissions.includes('*')) return true
    return user.permissions.includes(requiredPermission)
  }

  return <RBACContext.Provider value={{ user, setUser, hasPermission }}>{children}</RBACContext.Provider>
}

export function useRBAC() {
  const ctx = useContext(RBACContext)
  return { ...ctx, roleLabel: ctx.user.roleLabel }
}

export function permissionsForRole(role: SpartaRole): string[] {
  return ROLE_PERMISSIONS[role] ?? []
}
