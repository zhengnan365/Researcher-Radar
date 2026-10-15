<template>
  <div class="page admin-page fade-in">
    <div class="admin-body glass-card">
      <div v-if="$slots.actions" class="admin-actions">
        <slot name="actions" />
      </div>
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({ title: { type: String, required: false, default: '' } })
</script>

<style scoped>
.admin-page {
  height: 100%;
  overflow: auto;
}

.admin-body {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 14px;
  padding: 20px;
  min-width: 0;
}

.admin-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  flex: 0 0 auto;
  min-height: 84px;
}

.admin-body :deep(.admin-metrics) {
  flex: 1 1 520px;
  margin-bottom: 0;
}

.admin-body :deep(.toolbar),
.admin-body :deep(.filter-panel),
.admin-body :deep(.el-table),
.admin-body :deep(.report-grid),
.admin-body :deep(.el-card) {
  flex: 0 0 100%;
  box-sizing: border-box;
  min-width: 0;
}

.admin-body :deep(.toolbar),
.admin-body :deep(.filter-panel) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.admin-body :deep(.toolbar > .filter-item),
.admin-body :deep(.filter-panel > .filter-item) {
  flex: 1 1 11rem !important;
  width: auto !important;
  min-width: 9.5rem;
  max-width: 18rem;
}

.admin-body :deep(.toolbar > .search-input),
.admin-body :deep(.filter-panel > .search-input) {
  flex: 1.3 1 14rem !important;
  width: auto !important;
  min-width: 12rem;
  max-width: 22rem;
}

.admin-body :deep(.toolbar > .publisher-input),
.admin-body :deep(.filter-panel > .publisher-input) {
  flex: 0.9 1 10rem !important;
  width: auto !important;
  max-width: 14rem;
}

.admin-body :deep(.toolbar > .status-select),
.admin-body :deep(.filter-panel > .status-select) {
  flex: 0.75 1 8rem !important;
  width: auto !important;
  min-width: 7rem;
  max-width: 10rem;
}

.admin-body :deep(.toolbar > .el-button),
.admin-body :deep(.filter-panel > .el-button) {
  flex: 0 0 auto !important;
}

.admin-body :deep(.toolbar > .filter-actions),
.admin-body :deep(.filter-panel > .filter-actions) {
  margin-left: auto;
  display: flex;
  flex: 0 1 auto !important;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  min-width: fit-content;
}

@media (max-width: 1440px) {
  .admin-body {
    padding: 16px;
  }

  .admin-body :deep(.admin-metrics) {
    flex-basis: 100%;
  }

  .admin-body :deep(.toolbar > .filter-item),
  .admin-body :deep(.filter-panel > .filter-item) {
    flex-basis: 10rem !important;
    min-width: 8.5rem;
    max-width: none;
  }

  .admin-body :deep(.toolbar > .search-input),
  .admin-body :deep(.filter-panel > .search-input) {
    flex-basis: 13rem !important;
    min-width: 11rem;
    max-width: none;
  }
}

@media (max-width: 900px) {
  .admin-body :deep(.toolbar > .filter-actions),
  .admin-body :deep(.filter-panel > .filter-actions) {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }
}
</style>
