import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Button,
  Chip,
  List,
  ListItem,
  ListItemText,
  Alert,
  AlertTitle,
  Breadcrumbs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  Code as CodeIcon,
  Cloud as CloudIcon,
  BugReport as BugReportIcon,
  Api as ApiIcon,
  Dashboard as DashboardIcon,
  ArrowBack as ArrowBackIcon,
  CheckCircle as CheckCircleIcon,
  GitHub as GitHubIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { CodeBlock, SectionAccordion, InfoCard, MethodChip, StatusChip } from '../components/common';

const APIReference: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const apiCategories = [
    {
      name: "核心聊天",
      description: "主聊天界面与智能体路由",
      endpoints: [
        { method: "POST", path: "/api/v1/chat", description: "带智能体路由的主聊天界面", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/health", description: "系统健康检查", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/metrics", description: "Prometheus 指标", status: "✅ 正常" }
      ]
    },
    {
      name: "智能体操作",
      description: "专业智能体操作与工具执行",
      endpoints: [
        { method: "GET", path: "/api/v1/equipment/assignments", description: "获取设备分配", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/operations/waves", description: "创建拣货波次", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/safety/incidents", description: "记录安全事件", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/equipment/status", description: "获取设备状态", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/operations/tasks", description: "向工作人员分配任务", status: "✅ 正常" }
      ]
    },
    {
      name: "MCP 框架",
      description: "模型上下文协议的工具发现与执行",
      endpoints: [
        { method: "GET", path: "/api/v1/mcp/tools", description: "发现可用工具", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/mcp/status", description: "MCP 系统状态", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/mcp/execute", description: "执行 MCP 工具", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/mcp/adapters", description: "列出已注册的适配器", status: "✅ 正常" }
      ]
    },
    {
      name: "推理引擎",
      description: "高级推理能力与分析",
      endpoints: [
        { method: "POST", path: "/api/v1/reasoning/analyze", description: "深度推理分析", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/reasoning/types", description: "可用的推理类型", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/reasoning/chat-with-reasoning", description: "带推理的聊天", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/reasoning/insights", description: "获取推理洞察", status: "⚠️ 部分可用" }
      ]
    },
    {
      name: "身份验证",
      description: "用户身份验证与授权",
      endpoints: [
        { method: "POST", path: "/api/v1/auth/login", description: "用户登录", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/auth/logout", description: "用户退出", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/auth/profile", description: "获取用户资料", status: "✅ 正常" },
        { method: "POST", path: "/api/v1/auth/refresh", description: "刷新 JWT 令牌", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/auth/users/public", description: "获取用于下拉选择的用户列表（公开，无需身份验证）", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/auth/users", description: "获取所有用户（仅限管理员）", status: "✅ 正常" }
      ]
    },
    {
      name: "监控",
      description: "系统监控与可观测性",
      endpoints: [
        { method: "GET", path: "/api/v1/monitoring/health", description: "详细健康检查", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/monitoring/metrics", description: "系统指标", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/monitoring/logs", description: "系统日志", status: "✅ 正常" },
        { method: "GET", path: "/api/v1/monitoring/alerts", description: "活动告警", status: "✅ 正常" }
      ]
    }
  ];

  const requestExamples = [
    {
      title: "聊天请求",
      description: "向聊天界面发送消息",
      method: "POST",
      path: "/api/v1/chat",
      request: {
        "message": "Dispatch forklift FL-02 to Zone A for pick operations",
        "session_id": "user_session_123",
        "context": {
          "user_id": "user_456",
          "role": "operator"
        }
      },
      response: {
        "response_id": "resp_789",
        "message": "Forklift FL-02 has been successfully dispatched to Zone A for pick operations. Estimated arrival time is 5 minutes.",
        "agent": "equipment_agent",
        "confidence": 0.92,
        "structured_data": {
          "equipment_id": "FL-02",
          "destination": "Zone A",
          "operation": "pick operations",
          "status": "dispatched",
          "eta": "5 minutes"
        },
        "actions_taken": [
          {
            "action": "dispatch_equipment",
            "equipment_id": "FL-02",
            "destination": "Zone A"
          }
        ]
      }
    },
    {
      title: "工具发现",
      description: "发现可用的 MCP 工具",
      method: "GET",
      path: "/api/v1/mcp/tools",
      request: null,
      response: {
        "tools": [
          {
            "name": "check_stock",
            "adapter": "equipment_asset_tools",
            "description": "Check inventory levels for specific SKUs",
            "parameters": {
              "sku": "string",
              "site": "string",
              "locations": "array"
            },
            "return_type": "StockInfo"
          },
          {
            "name": "dispatch_equipment",
            "adapter": "operations_action_tools", 
            "description": "Dispatch equipment to specific locations",
            "parameters": {
              "equipment_id": "string",
              "destination": "string",
              "operation": "string"
            },
            "return_type": "DispatchResult"
          }
        ],
        "total_tools": 23,
        "adapters": ["equipment_asset_tools", "operations_action_tools", "safety_action_tools"]
      }
    },
    {
      title: "推理分析",
      description: "执行深度推理分析",
      method: "POST",
      path: "/api/v1/reasoning/analyze",
      request: {
        "query": "What factors should be considered when optimizing warehouse layout?",
        "reasoning_types": ["chain_of_thought", "scenario_analysis"],
        "context": {
          "warehouse_type": "distribution_center",
          "current_layout": "zone_based"
        }
      },
      response: {
        "analysis_id": "analysis_456",
        "reasoning_chains": [
          {
            "type": "chain_of_thought",
            "steps": [
              "Analyze current warehouse layout efficiency",
              "Identify bottlenecks in material flow",
              "Consider space utilization optimization",
              "Evaluate impact on worker productivity"
            ],
            "conclusion": "Zone-based layout with dynamic routing optimization"
          }
        ],
        "confidence": 0.87,
        "recommendations": [
          "Implement dynamic routing algorithms",
          "Optimize zone boundaries based on order patterns",
          "Consider vertical space utilization"
        ]
      }
    }
  ];

  const statusCodes = [
    { code: 200, description: "成功", meaning: "请求已成功完成" },
    { code: 201, description: "已创建", meaning: "资源已成功创建" },
    { code: 400, description: "错误请求", meaning: "请求参数无效" },
    { code: 401, description: "未授权", meaning: "需要身份验证" },
    { code: 403, description: "禁止访问", meaning: "权限不足" },
    { code: 404, description: "未找到", meaning: "未找到资源" },
    { code: 422, description: "无法处理的实体", meaning: "验证错误" },
    { code: 500, description: "服务器内部错误", meaning: "服务器发生错误" }
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          文档
        </Button>
        <Typography color="text.primary">API 参考</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          API 参考
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          完整的 API 文档
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          多智能体智慧仓储系统所有 API 端点的完整参考。
          本文档涵盖身份验证、智能体操作、MCP 框架、推理引擎和监控 API。
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="REST API" color="primary" />
          <Chip label="OpenAPI/Swagger" color="secondary" />
          <Chip label="JWT 身份验证" color="info" />
          <Chip label="实时" color="warning" />
          <Chip label="生产就绪" color="success" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="success" sx={{ mb: 4 }}>
        <AlertTitle>✅ 所有核心 API 均正常运行</AlertTitle>
        所有关键 API 端点均已投入运行并通过测试。系统提供完整的 REST API 覆盖，
        并具备完善的身份验证、错误处理和文档。
      </Alert>

      {/* Base URL */}
      <SectionAccordion
        id="base"
        expanded={expandedSection}
        onChange={handleChange}
        icon={CloudIcon}
        title="基础 URL 与身份验证"
      >
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <InfoCard title="🌐 基础 URL">
              <List>
                <ListItem>
                  <ListItemText 
                    primary="开发环境（仅 localhost）" 
                    secondary="http://localhost:8002"
                  />
                  {/* Security: HTTP protocol is acceptable for localhost in development/testing only.
                      Production deployments must use HTTPS to encrypt API communications.
                      SonarQube may flag HTTP usage, but it's acceptable for:
                      - localhost (127.0.0.1, 0.0.0.0) - development/testing only
                      Production external services must use HTTPS */}
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="预发布环境" 
                    secondary="https://staging-api.warehouse-assistant.com"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="生产环境" 
                    secondary="https://api.warehouse-assistant.com"
                  />
                </ListItem>
              </List>
            </InfoCard>
          </Grid>
          <Grid item xs={12} md={6}>
            <InfoCard title="🔐 身份验证">
              <Typography variant="body2" sx={{ mb: 2 }}>
                所有 API 请求都需要通过 Authorization 标头进行 JWT 身份验证：
              </Typography>
              <CodeBlock>
{`Authorization: Bearer <jwt_token>

# Example
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  -H "Content-Type: application/json"
  https://api.warehouse-assistant.com/api/v1/chat`}
              </CodeBlock>
            </InfoCard>
          </Grid>
        </Grid>
      </SectionAccordion>

      {/* API Categories */}
      <SectionAccordion
        id="endpoints"
        expanded={expandedSection}
        onChange={handleChange}
        icon={ApiIcon}
        title="API 端点"
      >
        <Grid container spacing={3}>
          {apiCategories.map((category, index) => (
            <Grid item xs={12} md={6} key={index}>
              <InfoCard title={category.name} description={category.description} sx={{ height: '100%' }}>
                <List dense>
                  {category.endpoints.map((endpoint, epIndex) => (
                    <ListItem key={epIndex} sx={{ px: 0 }}>
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <MethodChip method={endpoint.method} />
                            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                              {endpoint.path}
                            </Typography>
                            <StatusChip status={endpoint.status} />
                          </Box>
                        }
                        secondary={endpoint.description}
                      />
                    </ListItem>
                  ))}
                </List>
              </InfoCard>
            </Grid>
          ))}
        </Grid>
      </SectionAccordion>

      {/* Request Examples */}
      <SectionAccordion
        id="examples"
        expanded={expandedSection}
        onChange={handleChange}
        icon={CodeIcon}
        title="请求示例"
      >
        <Grid container spacing={3}>
          {requestExamples.map((example, index) => (
            <Grid item xs={12} key={index}>
              <InfoCard title={example.title} description={example.description}>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" gutterBottom>
                      请求（{example.method} {example.path}）
                    </Typography>
                    <CodeBlock>
                      {example.request ? JSON.stringify(example.request, null, 2) : 'No request body'}
                    </CodeBlock>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" gutterBottom>
                      响应
                    </Typography>
                    <CodeBlock>
                      {JSON.stringify(example.response, null, 2)}
                    </CodeBlock>
                  </Grid>
                </Grid>
              </InfoCard>
            </Grid>
          ))}
        </Grid>
      </SectionAccordion>

      {/* Status Codes */}
      <SectionAccordion
        id="status"
        expanded={expandedSection}
        onChange={handleChange}
        icon={CheckCircleIcon}
        title="HTTP 状态码"
      >
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>代码</TableCell>
                <TableCell>说明</TableCell>
                <TableCell>含义</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {statusCodes.map((status, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Chip 
                      label={status.code} 
                      color={status.code < 300 ? 'success' : status.code < 400 ? 'warning' : 'error'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{status.description}</TableCell>
                  <TableCell>{status.meaning}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionAccordion>

      {/* Error Handling */}
      <SectionAccordion
        id="errors"
        expanded={expandedSection}
        onChange={handleChange}
        icon={BugReportIcon}
        title="错误处理"
      >
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <InfoCard title="🚨 错误响应格式">
              <CodeBlock sx={{ mb: 2 }}>
{`{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "sku",
      "issue": "SKU must be alphanumeric"
    },
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_123456"
  }
}`}
              </CodeBlock>
            </InfoCard>
          </Grid>
          <Grid item xs={12} md={6}>
            <InfoCard title="🔧 常见错误代码">
              <List dense>
                <ListItem>
                  <ListItemText 
                    primary="VALIDATION_ERROR" 
                    secondary="请求验证失败"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="AUTHENTICATION_REQUIRED" 
                    secondary="需要有效的 JWT 令牌"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="INSUFFICIENT_PERMISSIONS" 
                    secondary="用户缺少所需权限"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="RESOURCE_NOT_FOUND" 
                    secondary="请求的资源不存在"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="RATE_LIMIT_EXCEEDED" 
                    secondary="请求过多"
                  />
                </ListItem>
              </List>
            </InfoCard>
          </Grid>
        </Grid>
      </SectionAccordion>

      {/* Footer */}
      <Box sx={{ mt: 4, pt: 3, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary" align="center">
          API 参考——多智能体智慧仓储系统
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

export default APIReference;
