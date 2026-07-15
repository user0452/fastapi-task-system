import { afterEach } from 'vitest'
import { config } from '@vue/test-utils'


config.global.stubs = {
  transition: false
}

afterEach(() => {
  document.body.innerHTML = ''
})
