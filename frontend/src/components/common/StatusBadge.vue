<script setup>
defineProps({
  status: { type: String, required: true },
  label: { type: String, default: '' }
})

const statusClasses = {
  todo: 'badge-info',
  doing: 'badge-warning',
  done: 'badge-success',
  low: 'badge-info',
  medium: 'badge-warning',
  high: 'badge-accent'
}
</script>

<template>
  <span class="badge" :class="statusClasses[status] || 'badge-info'">
    {{ label || status }}
  </span>
</template>
