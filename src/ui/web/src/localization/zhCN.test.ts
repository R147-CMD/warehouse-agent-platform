import {
  formatZhDate,
  formatZhDateTime,
  translateAssignmentType,
  translateAssetType,
  translateMcpCapability,
  translateMcpCategory,
  translateMcpDescription,
  translateMcpAgentNote,
  translateMcpParameterDescription,
  translateMcpToolName,
  translatePriority,
  translateRole,
  translateSafetyPolicyName,
  translateSafetyPolicySummary,
  translateStatus,
  translateTaskKind,
  translateTrainingMessage,
  translateWarehouseLocation,
} from './zhCN';

describe('中文界面动态值翻译', () => {
  test('将常用仓储状态翻译为中文', () => {
    expect(translateStatus('maintenance')).toBe('维护中');
    expect(translateStatus('in_progress')).toBe('进行中');
    expect(translateStatus('out_of_service')).toBe('停用');
  });

  test('将优先级、角色和设备类型翻译为中文', () => {
    expect(translatePriority('critical')).toBe('紧急');
    expect(translateRole('operator')).toBe('操作员');
    expect(translateAssetType('forklift')).toBe('叉车');
  });

  test.each([
    ['available', '可用'],
    ['assigned', '已分配'],
    ['charging', '充电中'],
    ['pending', '待处理'],
    ['completed', '已完成'],
    ['failed', '失败'],
    ['online', '在线'],
    ['offline', '离线'],
    ['healthy', '正常'],
    ['unhealthy', '异常'],
    ['open', '待处理'],
    ['resolved', '已解决'],
    ['scheduled', '已计划'],
    ['approved', '已批准'],
    ['rejected', '已驳回'],
  ])('完整状态映射：%s → %s', (source, expected) => {
    expect(translateStatus(source)).toBe(expected);
  });

  test.each([
    ['low', '低'],
    ['medium', '中'],
    ['high', '高'],
    ['urgent', '紧急'],
  ])('完整优先级映射：%s → %s', (source, expected) => {
    expect(translatePriority(source)).toBe(expected);
  });

  test.each([
    ['admin', '管理员'],
    ['user', '用户'],
    ['manager', '经理'],
    ['viewer', '访客'],
    ['supervisor', '主管'],
  ])('完整角色映射：%s → %s', (source, expected) => {
    expect(translateRole(source)).toBe(expected);
  });

  test.each([
    ['agv', '自动导引车'],
    ['amr', '自主移动机器人'],
    ['conveyor', '输送机'],
    ['scanner', '扫描仪'],
    ['robot', '机器人'],
    ['humanoid', '人形机器人'],
    ['drone', '无人机'],
    ['sensor', '传感器'],
    ['pallet_jack', '托盘搬运车'],
    ['charger', '充电器'],
  ])('完整设备类型映射：%s → %s', (source, expected) => {
    expect(translateAssetType(source)).toBe(expected);
  });

  test.each([
    ['picking', '拣货'],
    ['putaway', '上架'],
    ['replenishment', '补货'],
    ['cycle_count', '循环盘点'],
    ['inspection', '巡检'],
    ['loading', '装货'],
    ['unloading', '卸货'],
  ])('任务类型映射：%s → %s', (source, expected) => {
    expect(translateTaskKind(source)).toBe(expected);
  });

  test.each([
    ['task', '任务'],
    ['user', '用户'],
    ['maintenance', '维护'],
    ['mission', '任务'],
  ])('分配类型映射：%s → %s', (source, expected) => {
    expect(translateAssignmentType(source)).toBe(expected);
  });

  test('安全政策名称和摘要使用中文', () => {
    expect(translateSafetyPolicyName('Forklift Operation Safety Guidelines')).toBe('叉车操作安全指南');
    expect(translateSafetyPolicySummary('Comprehensive guidelines for safe forklift operation')).toBe(
      '叉车安全操作综合指南',
    );
  });

  test('MCP 元数据显示中文说明，同时保留技术标识', () => {
    expect(translateMcpCategory('equipment')).toBe('设备');
    expect(translateMcpCapability('parameterized')).toBe('支持参数');
    expect(
      translateMcpDescription(
        'Get equipment status and availability information',
        'get_equipment_status',
      ),
    ).toBe('获取设备状态和可用性信息');
    expect(translateMcpDescription('Unknown English description', 'custom_tool')).toBe(
      '自定义工具（MCP 工具：custom_tool）',
    );
    expect(translateMcpToolName('update_inventory_report')).toBe('更新库存报告');
    expect(translateMcpParameterDescription('Specific equipment asset ID to check', 'asset_id')).toBe(
      '要检查的设备资产 ID',
    );
    expect(translateMcpCategory('document')).toBe('文档');
    expect(translateMcpCategory('data_modification')).toBe('数据修改');
    expect(translateMcpCategory('analysis')).toBe('分析');
    expect(translateMcpCategory('reporting')).toBe('报告');
    expect(translateMcpCategory('integration')).toBe('集成');
    expect(translateMcpCategory('utility')).toBe('实用工具');
    expect(translateMcpAgentNote('Document processing uses direct API endpoints')).toBe(
      '文档处理使用直接 API 端点',
    );
  });

  test('仓库区域使用中文显示', () => {
    expect(translateWarehouseLocation('Zone A')).toBe('A 区');
    expect(translateWarehouseLocation('Loading Dock')).toBe('装卸口');
  });

  test('训练阶段和未知英文日志不会直接显示英文界面文案', () => {
    expect(translateTrainingMessage('Database Connection Established')).toBe('数据库连接已建立');
    expect(translateTrainingMessage('✅ Database connection established')).toBe('数据库连接已建立');
    expect(translateTrainingMessage('Some unexpected English-only log')).toBe(
      '训练日志已更新，详细技术信息请查看服务端日志。',
    );
  });

  test('未知动态值保留原文并安全处理空值', () => {
    expect(translateStatus('custom-state')).toBe('custom-state');
    expect(translatePriority('')).toBe('未设置');
    expect(translateRole(null)).toBe('未设置');
  });

  test('日期和时间使用中文区域格式', () => {
    const value = '2026-07-29T08:05:00Z';
    expect(formatZhDate(value, 'UTC')).toBe('2026/7/29');
    expect(formatZhDateTime(value, 'UTC')).toContain('2026/7/29');
    expect(formatZhDateTime(value, 'UTC')).toContain('08:05');
  });
});
