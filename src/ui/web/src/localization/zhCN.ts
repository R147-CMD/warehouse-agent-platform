type LocalizableValue = string | null | undefined;

const EMPTY_LABEL = '未设置';

const statusLabels: Readonly<Record<string, string>> = {
  available: '可用',
  assigned: '已分配',
  charging: '充电中',
  maintenance: '维护中',
  in_progress: '进行中',
  out_of_service: '停用',
  pending: '待处理',
  completed: '已完成',
  failed: '失败',
  online: '在线',
  offline: '离线',
  healthy: '正常',
  unhealthy: '异常',
  open: '待处理',
  resolved: '已解决',
  scheduled: '已计划',
  approved: '已批准',
  rejected: '已驳回',
};

const priorityLabels: Readonly<Record<string, string>> = {
  critical: '紧急',
  low: '低',
  medium: '中',
  high: '高',
  urgent: '紧急',
};

const roleLabels: Readonly<Record<string, string>> = {
  operator: '操作员',
  admin: '管理员',
  user: '用户',
  manager: '经理',
  viewer: '访客',
  supervisor: '主管',
};

const assetTypeLabels: Readonly<Record<string, string>> = {
  forklift: '叉车',
  agv: '自动导引车',
  amr: '自主移动机器人',
  conveyor: '输送机',
  scanner: '扫描仪',
  robot: '机器人',
  humanoid: '人形机器人',
  drone: '无人机',
  sensor: '传感器',
  pallet_jack: '托盘搬运车',
  charger: '充电器',
};

const taskKindLabels: Readonly<Record<string, string>> = {
  picking: '拣货',
  putaway: '上架',
  replenishment: '补货',
  cycle_count: '循环盘点',
  inspection: '巡检',
  loading: '装货',
  unloading: '卸货',
};

const assignmentTypeLabels: Readonly<Record<string, string>> = {
  task: '任务',
  mission: '任务',
  user: '用户',
  operator: '操作员',
  maintenance: '维护',
};

const safetyPolicyNameLabels: Readonly<Record<string, string>> = {
  'Personal Protective Equipment (PPE) Policy': '个人防护装备（PPE）政策',
  'Forklift Operation Safety Guidelines': '叉车操作安全指南',
  'Emergency Evacuation Procedures': '紧急疏散程序',
  'Chemical Handling Safety Protocol': '化学品处理安全规程',
  'Ladder and Elevated Work Safety': '梯具与高处作业安全规范',
};

const safetyPolicySummaryLabels: Readonly<Record<string, string>> = {
  'All personnel must wear appropriate PPE in designated areas': '所有人员在指定区域内必须佩戴适当的个人防护装备',
  'Comprehensive guidelines for safe forklift operation': '叉车安全操作综合指南',
  'Step-by-step emergency evacuation procedures': '分步骤紧急疏散程序',
  'Safe handling and storage procedures for chemicals': '化学品安全处理与储存程序',
  'Safety requirements for working at heights': '高处作业安全要求',
};

const mcpCategoryLabels: Readonly<Record<string, string>> = {
  equipment: '设备',
  operations: '运营',
  safety: '安全',
  data_access: '数据访问',
  forecasting: '预测',
  document: '文档',
  data_modification: '数据修改',
  analysis: '分析',
  reporting: '报告',
  integration: '集成',
  utility: '实用工具',
};

const mcpToolNameTokenLabels: Readonly<Record<string, string>> = {
  get: '获取',
  list: '列出',
  search: '搜索',
  create: '创建',
  update: '更新',
  delete: '删除',
  assign: '分配',
  execute: '执行',
  process: '处理',
  upload: '上传',
  download: '下载',
  check: '检查',
  start: '启动',
  stop: '停止',
  generate: '生成',
  log: '记录',
  broadcast: '广播',
  equipment: '设备',
  asset: '资产',
  assets: '资产',
  task: '任务',
  tasks: '任务',
  inventory: '库存',
  forecast: '预测',
  forecasts: '预测',
  model: '模型',
  performance: '性能',
  status: '状态',
  workforce: '人员',
  safety: '安全',
  procedure: '程序',
  procedures: '程序',
  incident: '事件',
  alert: '警报',
  document: '文档',
  report: '报告',
  recommendations: '建议',
  reorder: '补货',
  business: '业务',
  intelligence: '智能',
  dashboard: '仪表盘',
  utilization: '利用率',
  maintenance: '维护',
  schedule: '计划',
  batch: '批量',
  data: '数据',
  integration: '集成',
  analysis: '分析',
  utility: '实用工具',
  custom: '自定义',
  tool: '工具',
};

const warehouseLocationLabels: Readonly<Record<string, string>> = {
  'zone a': 'A 区',
  'zone b': 'B 区',
  'loading dock': '装卸口',
  'assembly line': '装配线',
  'charging station': '充电站',
};

const mcpCapabilityLabels: Readonly<Record<string, string>> = {
  executable: '可执行',
  parameterized: '支持参数',
  function: '函数工具',
};

const mcpDescriptionLabels: Readonly<Record<string, string>> = {
  'Get equipment status and availability information': '获取设备状态和可用性信息',
  'Assign equipment to a user or task': '将设备分配给用户或任务',
  'Get equipment utilization metrics and performance data': '获取设备利用率指标和性能数据',
  'Get maintenance schedule and upcoming maintenance tasks': '获取维护计划和即将执行的维护任务',
  'Create a new task for warehouse operations': '创建新的仓储运营任务',
  'Assign a task to a worker. If worker_id is not provided, task will remain queued for manual assignment.':
    '将任务分配给工作人员；未提供 worker_id 时，任务将保留在队列中等待手动分配。',
  'Get status of tasks': '获取任务状态',
  'Get workforce status and availability': '获取人员状态和可用性',
  'Log a safety incident': '记录安全事件',
  'Start a safety checklist': '启动安全检查表',
  'Broadcast a safety alert': '广播安全警报',
  'Get safety procedures and policies': '获取安全程序和政策',
  'Get demand forecast for a specific SKU': '获取指定 SKU 的需求预测',
  'Get demand forecasts for multiple SKUs': '获取多个 SKU 的需求预测',
  'Get automated reorder recommendations based on forecasts': '根据预测获取自动补货建议',
  'Get model performance metrics for all forecasting models': '获取所有预测模型的性能指标',
  'Get comprehensive forecasting dashboard data': '获取综合预测仪表盘数据',
  'Get business intelligence summary for forecasting': '获取预测业务智能摘要',
};

const mcpParameterDescriptionLabels: Readonly<Record<string, string>> = {
  asset_id: '要检查或操作的设备资产 ID',
  equipment_type: '设备类型',
  zone: '要检查或操作的区域',
  status: '按状态筛选',
  user_id: '要分配设备的用户 ID',
  task_id: '要检查或分配的任务 ID',
  assignment_type: '分配类型',
  time_period: '利用率数据的时间范围（日、周或月）',
  maintenance_type: '维护类型',
  days_ahead: '向后查询维护计划的天数',
  task_type: '任务类型',
  sku: '库存单位 SKU 标识',
  skus: '库存单位 SKU 标识列表',
  quantity: '任务数量',
  priority: '任务优先级',
  worker_id: '工作人员 ID',
  shift: '要检查的班次',
  severity: '事件严重程度',
  description: '事件描述',
  location: '事件发生位置',
  reporter: '事件报告人',
  attachments: '附件文件路径列表',
  checklist_type: '检查表类型',
  assignee: '检查表负责人',
  due_in: '检查表剩余小时数',
  message: '要广播的警报消息',
  channels: '广播渠道（PA、电子邮件或短信）',
  procedure_type: '安全程序类型',
  category: '安全程序类别',
  horizon_days: '预测天数（默认 30 天）',
};

const trainingMessageLabels: Readonly<Record<string, string>> = {
  'Starting training...': '正在启动训练…',
  'Initializing RAPIDS GPU training...': '正在初始化 RAPIDS GPU 训练…',
  'RAPIDS GPU Initialization': '正在初始化 RAPIDS GPU',
  'Database Connection Established': '数据库连接已建立',
  'Database connection established': '数据库连接已建立',
  'Extracting Historical Data': '正在提取历史数据',
  'Feature Engineering': '正在构建特征',
  'Training ML Models': '正在训练机器学习模型',
  'Generating Forecasts': '正在生成预测',
  'Processing SKUs': '正在处理 SKU',
  'Training Completed': '训练已完成',
  'Training script failed': '训练脚本执行失败',
  '🚀 RAPIDS GPU acceleration enabled': '🚀 已启用 RAPIDS GPU 加速',
  '✅ Database connection established': '数据库连接已建立',
};

const translateFromMap = (
  value: LocalizableValue,
  labels: Readonly<Record<string, string>>,
): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }

  const normalized = value.trim().toLowerCase();
  return labels[normalized] ?? value;
};

export const translateStatus = (value: LocalizableValue): string =>
  translateFromMap(value, statusLabels);

export const translatePriority = (value: LocalizableValue): string =>
  translateFromMap(value, priorityLabels);

export const translateRole = (value: LocalizableValue): string =>
  translateFromMap(value, roleLabels);

export const translateAssetType = (value: LocalizableValue): string =>
  translateFromMap(value, assetTypeLabels);

export const translateTaskKind = (value: LocalizableValue): string =>
  translateFromMap(value, taskKindLabels);

export const translateAssignmentType = (value: LocalizableValue): string =>
  translateFromMap(value, assignmentTypeLabels);

export const translateSafetyPolicyName = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }
  const name = value.trim();
  return safetyPolicyNameLabels[name] ?? (/[\u3400-\u9fff]/u.test(name) ? name : '安全政策');
};

export const translateSafetyPolicySummary = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }
  const summary = value.trim();
  return safetyPolicySummaryLabels[summary]
    ?? (/[\u3400-\u9fff]/u.test(summary) ? summary : '请遵守此项安全政策的相关要求。');
};

export const translateMcpCategory = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }
  return mcpCategoryLabels[value.trim().toLowerCase()] ?? '其他工具';
};

export const translateMcpCapability = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }
  return mcpCapabilityLabels[value.trim().toLowerCase()] ?? '扩展能力';
};

export const translateMcpToolName = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return 'MCP 工具';
  }
  return value
    .trim()
    .toLowerCase()
    .split(/[_\-\s]+/u)
    .filter(Boolean)
    .map((token) => mcpToolNameTokenLabels[token] ?? token)
    .join('');
};

export const translateMcpDescription = (
  value: LocalizableValue,
  toolName?: LocalizableValue,
): string => {
  if (!value?.trim()) {
    return toolName?.trim()
      ? `${translateMcpToolName(toolName)}（MCP 工具：${toolName.trim()}）`
      : '暂无工具说明';
  }
  const description = value.trim();
  if (mcpDescriptionLabels[description]) {
    return mcpDescriptionLabels[description];
  }
  if (/[\u3400-\u9fff]/u.test(description)) {
    return description;
  }
  return toolName?.trim()
    ? `${translateMcpToolName(toolName)}（MCP 工具：${toolName.trim()}）`
    : '暂无工具说明';
};

export const translateMcpParameterDescription = (
  value: LocalizableValue,
  parameterName: LocalizableValue,
): string => {
  const name = parameterName?.trim();
  if (name && mcpParameterDescriptionLabels[name]) {
    if (name === 'asset_id' && value?.trim() === 'Specific equipment asset ID to check') {
      return '要检查的设备资产 ID';
    }
    return mcpParameterDescriptionLabels[name];
  }
  if (value?.trim() && /[\u3400-\u9fff]/u.test(value)) {
    return value.trim();
  }
  return name ? `参数 ${name} 的说明` : '参数说明';
};

export const translateMcpAgentNote = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }
  const note = value.trim();
  if (note === 'Document processing uses direct API endpoints') {
    return '文档处理使用直接 API 端点';
  }
  return /[\u3400-\u9fff]/u.test(note) ? note : '智能体通过专用服务接口提供能力';
};

export const translateWarehouseLocation = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }
  const location = value.trim();
  return warehouseLocationLabels[location.toLowerCase()] ?? location;
};

export const translateTrainingMessage = (value: LocalizableValue): string => {
  if (!value?.trim()) {
    return EMPTY_LABEL;
  }

  const message = value.trim();
  const withoutStatusIcon = message.replace(/^[✅⚠️❌🚀📊📦📈🔧🤖🔮🎯🎉💾🌲🌳🏆💡]+\s*/u, '');
  const exact = trainingMessageLabels[message] ?? trainingMessageLabels[withoutStatusIcon];
  if (exact) {
    return exact;
  }
  if (/[\u3400-\u9fff]/u.test(message)) {
    return message;
  }
  return '训练日志已更新，详细技术信息请查看服务端日志。';
};

type DateValue = string | number | Date | null | undefined;

const parseDate = (value: DateValue): Date | null => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

export const formatZhDate = (value: DateValue, timeZone?: string): string => {
  const date = parseDate(value);
  return date
    ? new Intl.DateTimeFormat('zh-CN', { timeZone }).format(date)
    : EMPTY_LABEL;
};

export const formatZhDateTime = (value: DateValue, timeZone?: string): string => {
  const date = parseDate(value);
  return date
    ? new Intl.DateTimeFormat('zh-CN', {
        dateStyle: 'short',
        timeStyle: 'short',
        hour12: false,
        timeZone,
      }).format(date)
    : EMPTY_LABEL;
};
