#!/usr/bin/env node

import { randomUUID } from 'node:crypto'

const [baseUrl] = process.argv.slice(2)
if (!baseUrl) throw new Error('missing DSH base URL')

async function rpc(method, payload) {
  const rpcId = randomUUID()
  const response = await fetch(`${baseUrl}/api/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId, method, payload }),
    signal: AbortSignal.timeout(10_000),
  })
  if (response.status !== 200) {
    throw new Error(`${method} returned HTTP ${response.status}`)
  }
  const body = await response.json()
  if (body.rpcId !== rpcId || body.result?.ok !== true) {
    throw new Error(`${method} failed`)
  }
  return body.result.value
}

const sessionId = 'clean-docker-loopx-bootstrap'
await rpc('session.create', { sessionId, cwd: '/tmp/workspace' })
const catalog = await rpc('skill.list', { sessionId })
const names = catalog.skills.map(skill => skill.name).sort()
if (!names.includes('loopx')) {
  throw new Error(`first skill catalog omitted loopx: ${JSON.stringify(names)}`)
}
process.stdout.write(JSON.stringify({
  ok: true,
  sessionId,
  skillCount: names.length,
  loopx: true,
}))
