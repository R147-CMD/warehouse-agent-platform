import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Link,
  Alert,
  AlertTitle,
  Breadcrumbs,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Code as CodeIcon,
  Architecture as ArchitectureIcon,
  Security as SecurityIcon,
  Speed as SpeedIcon,
  Storage as StorageIcon,
  Cloud as CloudIcon,
  BugReport as BugReportIcon,
  Rocket as RocketIcon,
  School as SchoolIcon,
  GitHub as GitHubIcon,
  Article as ArticleIcon,
  Build as BuildIcon,
  Api as ApiIcon,
  Dashboard as DashboardIcon,
  ArrowBack as ArrowBackIcon,
  CheckCircle as CheckIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const MCPIntegrationGuide: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const mcpPhases = [
    {
      phase: "阶段 1：基础建设",
      status: "✅ 已完成",
      description: "核心 MCP 基础设施和基础工具发现",
      components: [
        "MCP 服务端实现",
        "MCP 客户端实现", 
        "支持 MCP 的基类",
        "ERP 适配器迁移",
        "完整测试框架",
        "完整文档"
      ]
    },
    {
      phase: "阶段 2：智能体集成", 
      status: "✅ 已完成",
      description: "动态工具发现与智能体集成",
      components: [
        "动态工具发现",
        "支持 MCP 的智能体",
        "动态工具绑定",
        "基于 MCP 的路由",
        "工具验证"
      ]
    },
    {
      phase: "阶段 3：全面迁移",
      status: "✅ 已完成", 
      description: "完成适配器迁移和生产部署",
      components: [
        "完成适配器迁移",
        "服务发现与注册中心",
        "MCP 监控与管理",
        "端到端测试",
        "部署配置",
        "安全集成"
      ]
    }
  ];

  const mcpComponents = [
    {
      name: "MCP 服务端",
      description: "完全符合协议的工具注册、发现与执行",
      features: ["工具注册", "协议合规", "错误处理", "健康监控"],
      status: "✅ 生产就绪"
    },
    {
      name: "MCP 客户端", 
      description: "支持 HTTP 和 WebSocket 的多服务器通信",
      features: ["多服务器通信", "HTTP/WebSocket 支持", "资源访问", "提示词管理"],
      status: "✅ 生产就绪"
    },
    {
      name: "工具发现服务",
      description: "具备智能搜索能力的自动工具发现与注册系统",
      features: ["动态注册", "智能搜索", "工具元数据", "健康检查"],
      status: "✅ 生产就绪"
    },
    {
      name: "工具绑定服务",
      description: "支持多种策略的智能工具绑定与执行框架",
      features: ["上下文感知绑定", "多种策略", "执行规划", "性能优化"],
      status: "✅ 生产就绪"
    },
    {
      name: "工具路由服务",
      description: "具备上下文感知能力的高级路由与工具选择逻辑",
      features: ["性能路由", "精度路由", "成本路由", "延迟路由"],
      status: "✅ 生产就绪"
    },
    {
      name: "服务发现注册中心",
      description: "集中式服务发现与健康监控",
      features: ["服务注册", "健康监控", "负载均衡", "故障转移"],
      status: "✅ 生产就绪"
    }
  ];

  const apiEndpoints = [
    {
      category: "工具发现",
      endpoints: [
        { method: "GET", path: "/api/v1/mcp/tools", description: "发现所有适配器中的可用工具" },
        { method: "GET", path: "/api/v1/mcp/tools/{adapter_id}", description: "获取指定适配器的工具" },
        { method: "POST", path: "/api/v1/mcp/tools/register", description: "向 MCP 服务端注册新工具" }
      ]
    },
    {
      category: "工具执行",
      endpoints: [
        { method: "POST", path: "/api/v1/mcp/execute", description: "使用参数执行 MCP 工具" },
        { method: "POST", path: "/api/v1/mcp/execute/batch", description: "批量执行多个工具" },
        { method: "GET", path: "/api/v1/mcp/execute/{execution_id}", description: "获取执行状态和结果" }
      ]
    },
    {
      category: "服务管理",
      endpoints: [
        { method: "GET", path: "/api/v1/mcp/status", description: "获取 MCP 系统状态和健康信息" },
        { method: "GET", path: "/api/v1/mcp/adapters", description: "列出所有已注册的适配器" },
        { method: "POST", path: "/api/v1/mcp/adapters/register", description: "注册新的 MCP 适配器" }
      ]
    }
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          文档
        </Button>
        <Typography color="text.primary">MCP 集成指南</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          MCP 集成指南
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          完整的模型上下文协议框架文档
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          多智能体智慧仓储系统中模型上下文协议（MCP）实现的完整指南。
          该框架通过动态工具发现与执行，实现 AI 智能体和外部系统之间的无缝通信。
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="阶段 3 已完成" color="success" />
          <Chip label="生产就绪" color="success" />
          <Chip label="动态工具发现" color="primary" />
          <Chip label="多服务器通信" color="secondary" />
          <Chip label="高级路由" color="info" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="success" sx={{ mb: 4 }}>
        <AlertTitle>🎉 MCP 框架已完成</AlertTitle>
        模型上下文协议集成的全部 3 个阶段均已顺利完成。
        系统现已具备动态工具发现、智能执行和全面监控能力。
      </Alert>

      {/* Overview */}
      <Accordion expanded={expandedSection === 'overview'} onChange={handleChange('overview')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ArchitectureIcon color="primary" />
            MCP 框架概览
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              什么是 MCP？
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              模型上下文协议（MCP）是一种用于 AI 智能体与外部系统之间进行工具发现、执行和通信的标准化协议。
              它为动态工具管理与执行提供统一接口。
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {mcpComponents.map((component, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <BuildIcon color="primary" />
                      <Typography variant="h6">{component.name}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {component.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>主要功能：</Typography>
                      <List dense>
                        {component.features.map((feature, featureIndex) => (
                          <ListItem key={featureIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CodeIcon fontSize="small" />
                            </ListItemIcon>
                            <ListItemText primary={feature} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Chip 
                      label={component.status} 
                      color={component.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Implementation Phases */}
      <Accordion expanded={expandedSection === 'phases'} onChange={handleChange('phases')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RocketIcon color="primary" />
            实施阶段
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {mcpPhases.map((phase, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {phase.phase}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {phase.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>组件：</Typography>
                      <List dense>
                        {phase.components.map((component, compIndex) => (
                          <ListItem key={compIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CheckIcon fontSize="small" />
                            </ListItemIcon>
                            <ListItemText primary={component} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Chip 
                      label={phase.status} 
                      color={phase.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* API Reference */}
      <Accordion expanded={expandedSection === 'api'} onChange={handleChange('api')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ApiIcon color="primary" />
            MCP API 参考
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {apiEndpoints.map((category, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {category.category}
                    </Typography>
                    <List dense>
                      {category.endpoints.map((endpoint, epIndex) => (
                        <ListItem key={epIndex} sx={{ px: 0 }}>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Chip 
                                  label={endpoint.method} 
                                  size="small" 
                                  color={endpoint.method === 'GET' ? 'success' : 'primary'}
                                />
                                <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                                  {endpoint.path}
                                </Typography>
                              </Box>
                            }
                            secondary={endpoint.description}
                          />
                        </ListItem>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Usage Examples */}
      <Accordion expanded={expandedSection === 'examples'} onChange={handleChange('examples')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CodeIcon color="primary" />
            使用示例
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    工具发现
                  </Typography>
                  <Paper sx={{ p: 2, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: '0.875rem', mb: 2 }}>
{`# Discover all available tools
GET /api/v1/mcp/tools

# Response
{
  "tools": [
    {
      "name": "check_stock",
      "adapter": "equipment_asset_tools",
      "description": "Check inventory levels",
      "parameters": {
        "sku": "string",
        "site": "string"
      }
    }
  ]
}`}
                  </Paper>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    工具执行
                  </Typography>
                  <Paper sx={{ p: 2, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: '0.875rem', mb: 2 }}>
{`# Execute a tool
POST /api/v1/mcp/execute
{
  "tool_name": "check_stock",
  "adapter": "equipment_asset_tools",
  "parameters": {
    "sku": "ABC123",
    "site": "warehouse_1"
  }
}

# Response
{
  "execution_id": "exec_123",
  "status": "completed",
  "result": {
    "sku": "ABC123",
    "on_hand": 150,
    "available": 120
  }
}`}
                  </Paper>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Best Practices */}
      <Accordion expanded={expandedSection === 'practices'} onChange={handleChange('practices')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SchoolIcon color="primary" />
            最佳实践
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🚀 性能优化
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="使用批量执行" 
                        secondary="批量执行多个工具以获得更佳性能"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="实施缓存" 
                        secondary="缓存工具结果以减少重复执行"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="监控工具性能" 
                        secondary="跟踪执行时间并优化缓慢的工具"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="使用合适的路由" 
                        secondary="根据用例选择路由策略（性能或精度）"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🔒 安全注意事项
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="验证工具参数" 
                        secondary="执行工具前始终验证输入参数"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="实施访问控制" 
                        secondary="控制不同用户可以执行的工具"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="审计工具使用情况" 
                        secondary="记录所有工具执行以便进行安全审计"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="妥善处理错误" 
                        secondary="实施适当的错误处理和回滚机制"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Footer */}
      <Box sx={{ mt: 4, pt: 3, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary" align="center">
          MCP 集成指南——多智能体智慧仓储系统
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mt: 2 }}>
          <Button 
            variant="outlined" 
            startIcon={<GitHubIcon />}
            href="https://github.com/T-DevH/warehouse-operational-assistant"
            target="_blank"
            rel="noopener noreferrer"
          >
            查看源代码
          </Button>
          <Button variant="outlined" startIcon={<DashboardIcon />}>
            在线演示
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

export default MCPIntegrationGuide;
