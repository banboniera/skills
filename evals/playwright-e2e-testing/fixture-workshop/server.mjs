// Serves the app; every path that is not a file gets index.html. The API is not served here.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'

const root = join(import.meta.dirname, 'src')
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }

createServer(async (req, res) => {
  const { pathname } = new URL(req.url, 'http://localhost')
  if (pathname.startsWith('/api/')) {
    res.writeHead(502, { 'content-type': 'application/json' })
    return res.end(JSON.stringify({ detail: 'No API server in this environment' }))
  }
  const file = normalize(join(root, pathname))
  const path = file.startsWith(root) && extname(file) ? file : join(root, 'index.html')
  try {
    const body = await readFile(path)
    res.writeHead(200, { 'content-type': types[extname(path)] ?? 'application/octet-stream' })
    res.end(body)
  } catch {
    res.writeHead(404)
    res.end()
  }
}).listen(Number(process.env.PORT ?? 4173), '127.0.0.1')
