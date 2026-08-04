<template>
  <div class="page-header">
    <div class="page-header-text">
      <h2 class="page-header-title">{{ title }}</h2>
      <p v-if="subtitle" class="page-header-sub">{{ subtitle }}</p>
    </div>
    <div class="page-header-actions">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>
