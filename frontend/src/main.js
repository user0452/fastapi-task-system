import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

import './styles/tokens.css'
import './styles/base.css'
import './styles/layout.css'
import './styles/components.css'
import './styles/surfaces.css'
import './styles/pages.css'
import './styles/reference-aesthetic.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
