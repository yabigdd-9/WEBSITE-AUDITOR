import { execFile } from 'node:child_process'
import { resolve } from 'node:path'
import { promisify } from 'node:util'
import { defineTool } from '@deepseek-ai/dsh-tools'

const execFileAsync = promisify(execFile)

export const name = 'website-auditor-tools'
export const inject = ['tools']

function root() {
  return resolve(process.env.WEBSITE_AUDITOR_ROOT || process.cwd())
}

function cleanEnv() {
  const env = { ...process.env }
  delete env.PYTHONSTARTUP
  delete env.BASH_ENV
  return env
}

function parseBridge(stdout) {
  const text = String(stdout || '').trim()
  if (!text) return { bridge: 'deepseek-harness/mm-v1', error: 'bridge produced no output' }
  const lines = text.split(/\r?\n/).filter(Boolean)
  const last = lines.at(-1)
  try {
    return JSON.parse(last)
  } catch {
    return { bridge: 'deepseek-harness/mm-v1', error: 'bridge returned non-JSON output', raw: text.slice(-8000) }
  }
}

async function runBridge(args) {
  const bridge = resolve(root(), 'integrations/deepseek-harness/scripts/dsh_mm_bridge.py')
  const python = process.env.WEBSITE_AUDITOR_PYTHON || 'python3'
  const timeout = Math.max(5000, Math.min(Number(process.env.DSH_MM_TIMEOUT_MS || 180000), 600000))
  try {
    const result = await execFileAsync(python, [bridge, ...args], {
      cwd: root(),
      env: cleanEnv(),
      timeout,
      maxBuffer: 8 * 1024 * 1024,
      windowsHide: true,
    })
    return parseBridge(result.stdout)
  } catch (error) {
    const parsed = parseBridge(error?.stdout)
    if (!parsed.error || parsed.blocked) return parsed
    return {
      bridge: 'deepseek-harness/mm-v1',
      error: String(error?.message || error),
      stderr: String(error?.stderr || '').slice(-8000),
      returncode: error?.code ?? null,
    }
  }
}

const jsonOutput = {
  schema: { type: 'json' },
  render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
}

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'website_auditor_status',
    description: 'Read deterministic WEBSITE-AUDITOR/MoneyMachine runtime, health, polish, or queue status. This tool does not send messages.',
    parameters: {
      view: {
        type: 'string',
        required: true,
        enum: ['runtime', 'status', 'polish-status', 'doctor'],
        description: 'Read-only status view to request.',
      },
    },
    output: jsonOutput,
    async execute(args) {
      return runBridge([args.view])
    },
  }))

  ctx.tools.register(defineTool({
    name: 'website_auditor_audit_site',
    description: 'Run the deterministic public-data Website Auditor against one public HTTP(S) site and return JSON evidence. No outreach is sent.',
    parameters: {
      url: { type: 'string', required: true, description: 'Absolute public http(s) website URL.' },
      output: { type: 'string', description: 'Optional output path inside the WEBSITE-AUDITOR repository.' },
    },
    output: jsonOutput,
    async execute(args) {
      const argv = ['audit-site', '--url', args.url]
      if (args.output) argv.push('--output', args.output)
      return runBridge(argv)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'website_auditor_email_status',
    description: 'Read Email Finder V2 status and provenance for one existing business ID. This does not discover a new address and does not send anything.',
    parameters: {
      businessId: { type: 'number', required: true, description: 'MoneyMachine business ID.' },
    },
    output: jsonOutput,
    async execute(args) {
      return runBridge(['email-status', '--business-id', String(args.businessId)])
    },
  }))

  ctx.tools.register(defineTool({
    name: 'website_auditor_outreach_plan',
    description: 'Generate the existing local outreach review plan from a brief inside the repository. This is planning only and cannot send or approve outreach.',
    parameters: {
      brief: { type: 'string', required: true, description: 'Path to a brief file inside WEBSITE-AUDITOR.' },
    },
    output: jsonOutput,
    async execute(args) {
      return runBridge(['outreach-plan', '--brief', args.brief])
    },
  }))

  ctx.tools.register(defineTool({
    name: 'website_auditor_email_find',
    description: 'Run one bounded Email Finder V2 discovery. Disabled by default; supervised runs must explicitly set DSH_MM_ALLOW_BOUNDED_WRITES=1. Never sends outreach.',
    parameters: {
      businessId: { type: 'number', required: true, description: 'MoneyMachine business ID.' },
    },
    output: jsonOutput,
    async execute(args) {
      return runBridge(['email-find', '--business-id', String(args.businessId)])
    },
  }))

  ctx.tools.register(defineTool({
    name: 'website_auditor_demo_qa',
    description: 'Run deterministic QA over a local demo file. Disabled by default because it records QA state; supervised runs must set DSH_MM_ALLOW_BOUNDED_WRITES=1.',
    parameters: {
      businessId: { type: 'number', required: true, description: 'MoneyMachine business ID.' },
      path: { type: 'string', required: true, description: 'Demo file path inside WEBSITE-AUDITOR.' },
    },
    output: jsonOutput,
    async execute(args) {
      return runBridge(['demo-qa', '--business-id', String(args.businessId), '--path', args.path])
    },
  }))
}
