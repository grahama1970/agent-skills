import { createWatchApp } from './app'
import { loadWatchServerConfig } from './config'

const config = loadWatchServerConfig()
const app = createWatchApp(config)

app.listen(config.port, () => {
  console.log(`Watch API server running on port ${config.port}`)
})
